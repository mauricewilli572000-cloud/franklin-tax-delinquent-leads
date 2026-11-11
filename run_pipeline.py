#!/usr/bin/env python3
"""Franklin County, OH tax delinquent leads.

1. Download the newest Auditor monthly data drop (TaxDetail, Parcel, Value, RentalContact)
   and the annual advertised delinquent list.
2. Keep parcels with an unpaid prior-year balance (TotPrior >= MIN_DELINQUENT).
3. Enrich from Parcel / Value / RentalContact, score, merge with earlier runs
   (parcels no longer delinquent are marked removed), export JSON + GHL CSV.

Usage:
    python run_pipeline.py            # normal (skips if the drop hasn't changed)
    python run_pipeline.py --force    # rebuild anyway
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import re
import shutil
import sys

import config
from src import downloader, parser, store
from src.schema import LeadRecord
from src.scoring import score

log = logging.getLogger("franklin_tax_delinquent")
EXCLUDE_RE = re.compile("|".join(config.EXCLUDE_OWNER_PATTERNS))
MERGE_FIELDS = ("owner_name", "owner_name_2", "mailing_address", "mailing_city", "mailing_state", "mailing_zip",
                "property_address", "property_city", "property_zip", "tax_year", "land_use", "land_use_desc",
                "homestead", "has_mortgage", "last_sale_date", "last_sale_amount")


def excluded(info: dict) -> bool:
    luc = re.sub(r"\D", "", info.get("land_use", ""))[:3]
    if luc and any(lo <= int(luc) <= hi for lo, hi in config.EXCLUDE_LUC_RANGES):
        return True
    return bool(EXCLUDE_RE.search(f"{info.get('owner_name', '')} {info.get('owner_name_2', '')}"))


def load_state() -> dict:
    return json.loads(config.STATE_JSON.read_text()) if config.STATE_JSON.exists() else {}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    today = dt.date.today().isoformat()
    state = load_state()

    # ------------------------------------------------------------ 1. download
    drops = downloader.list_drops()
    if not drops:
        log.error("No Tax Accounting drops found at %s", config.OUTSIDE_FILES)
        return 2
    if drops[0][0] == state.get("newest_drop") and not args.force:
        log.info("Newest drop %s already processed - nothing to do (use --force).", drops[0][0])
        return 0
    got = downloader.fetch_drop_files(config.RAW_DIR)
    advertised = downloader.fetch_advertised(config.RAW_DIR)
    snapshot = got["snapshot"]
    files = got["files"]

    # ------------------------------------------------------------ 2. parse
    balances = parser.delinquent_balances(files["TaxDetail.txt"], config.MIN_DELINQUENT)
    log.info("TaxDetail: %d parcels with >= $%.0f past-due tax", len(balances), config.MIN_DELINQUENT)
    wanted = set(balances)
    info = parser.parcel_info(files["Parcel.txt"], wanted)
    values = parser.market_values(files["Value.txt"], wanted) if "Value.txt" in files else {}
    rentals = parser.rental_contacts(files["RentalContact.txt"], wanted) if "RentalContact.txt" in files else {}
    adv: dict[str, set[str]] = {}
    for year, path in advertised:
        try:
            for p in parser.advertised_parcels(path):
                adv.setdefault(p, set()).add(year)
        except Exception as e:  # noqa: BLE001
            log.warning("Could not read advertised list %s: %s", path, e)
    log.info("Parcel info for %d, values %d, rentals %d, advertised %d", len(info), len(values), len(rentals),
             len(adv))

    current = {p: b for p, b in balances.items() if p in info and not excluded(info[p])}
    log.info("Kept %d delinquent parcels after excluding government/exempt/utility", len(current))

    # ------------------------------------------------------------ 3. merge
    leads = store.load(config.RECORDS_JSON)
    leads.update(store.load(config.PENDING_JSON))
    prev_active = sum(1 for l in leads.values() if l.status == "active")
    if prev_active > 500 and len(current) < 0.3 * prev_active:
        log.error("Only %d delinquent parcels vs %d active before - file layout probably changed. Aborting "
                  "so leads are not wrongly marked removed.", len(current), prev_active)
        return 2

    added = 0
    for pid, bal in current.items():
        lead = leads.get(pid)
        if lead is None:
            lead = LeadRecord(doc_num=pid, date_added=today)
            leads[pid] = lead
            added += 1
        elif lead.delinquent_amount != bal["delinquent"]:
            lead.amount_history.append({"date": snapshot, "amount": bal["delinquent"]})
        for k in MERGE_FIELDS:
            setattr(lead, k, info[pid][k])
        lead.parcel_id = pid
        lead.delinquent_amount = bal["delinquent"]
        lead.amount_owed = bal["total"]
        lead.market_value = values.get(pid) or lead.market_value
        r = rentals.get(pid)
        lead.rental_registered = bool(r)
        lead.rental_units = r["units"] if r else 0
        lead.owner_phone = (r or {}).get("phone", "") or lead.owner_phone
        lead.advertised_years = sorted(set(lead.advertised_years) | adv.get(pid, set()), reverse=True)
        lead.lead_type = config.LEAD_TYPE + (" - Advertised" if lead.advertised_years else "")
        lead.county = config.COUNTY
        lead.source_url = config.OUTSIDE_FILES
        lead.auditor_url = config.AUDITOR_PARCEL_URL.format(parcel=pid)
        if not lead.amount_history:
            lead.amount_history.append({"date": snapshot, "amount": bal["delinquent"]})
        lead.last_seen = snapshot
        lead.status = "active"
        lead.removed_date = ""

    removed = 0
    for pid, lead in leads.items():
        if pid not in current and lead.status == "active":
            lead.status, lead.removed_date = "removed", snapshot
            removed += 1
    log.info("Merge: new=%d removed=%d", added, removed)

    # ------------------------------------------------------------ 4. score + save
    for lead in leads.values():
        score(lead)
    with_addr = {k: l for k, l in leads.items() if l.has_address()}
    pending = {k: l for k, l in leads.items() if not l.has_address() and l.status == "active"}
    active = [l for l in with_addr.values() if l.status == "active"]
    meta = {
        "county": config.COUNTY, "lead_type": config.LEAD_TYPE, "source": config.OUTSIDE_FILES,
        "snapshot": snapshot, "drops": got["drops"],
        "advertised_lists": [y for y, _ in advertised],
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "active": len(active), "hot": sum(1 for l in active if l.tier == "Hot"),
        "warm": sum(1 for l in active if l.tier == "Warm"),
        "removed": sum(1 for l in with_addr.values() if l.status == "removed"),
        "pending_no_address": len(pending), "added_this_run": added,
    }
    store.save(config.RECORDS_JSON, with_addr, meta)
    store.save(config.PENDING_JSON, pending, {"note": "active parcels with no address - retried each run"})
    n_csv = store.export_ghl(config.GHL_CSV, with_addr, config.COUNTY)
    shutil.copyfile(config.GHL_CSV, config.DASHBOARD_CSV)
    store.export_dashboard(config.DASHBOARD_JSON, with_addr, meta)
    state.update({"newest_drop": drops[0][0], "signature": got["signature"], "snapshot": snapshot,
                  "last_processed": today})
    config.STATE_JSON.write_text(json.dumps(state, indent=2), encoding="utf-8")
    log.info("Saved: active=%d (hot %d / warm %d), removed=%d, pending=%d, GHL rows=%d",
             meta["active"], meta["hot"], meta["warm"], meta["removed"], len(pending), n_csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
