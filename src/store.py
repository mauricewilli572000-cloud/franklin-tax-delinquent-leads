"""Accumulate leads across runs (merge by doc_num = parcel) and export."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from .schema import LeadRecord

BUSINESS_RE = re.compile(r"\b(LLC|INC|CORP|CO|LTD|LP|TRUST|ESTATE|BANK|CHURCH|ASSN|ASSOCIATION|HEIRS)\b")


def load(path: Path) -> dict[str, LeadRecord]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data["records"] if isinstance(data, dict) else data
    return {d["doc_num"]: LeadRecord.from_dict(d) for d in items}


def save(path: Path, leads: dict[str, LeadRecord], meta: dict | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(leads.values(), key=lambda l: (l.status != "active", -l.score, -(l.delinquent_amount or 0)))
    payload = {"meta": meta or {}, "records": [l.to_dict() for l in rows]}
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")


def split_name(owner: str) -> tuple[str, str]:
    """Auditor names are 'LAST FIRST M'. Returns (first, last)."""
    name = (owner or "").strip()
    if not name or BUSINESS_RE.search(name):
        return "", name.title()
    name = re.split(r"\s+(?:&|AND)\s+", name)[0]
    parts = name.replace(",", " ").split()
    if len(parts) == 1:
        return "", parts[0].title()
    return " ".join(parts[1:]).title(), parts[0].title()


GHL_COLUMNS = [
    "First Name", "Last Name", "Full Name", "Owner 2", "Phone", "Address", "City", "State", "Postal Code",
    "Property Address", "Property City", "Property Zip", "Property Type", "Property Detail", "Lead Type",
    "Delinquent Amount", "Amount Owed", "Market Value", "Last Sale Date", "Score", "Tier", "Parcel",
    "Certified Delinquent", "Advertised Years", "Absentee", "Date Added", "Tags",
]


def export_ghl(path: Path, leads: dict[str, LeadRecord], county: str) -> int:
    rows = [l for l in leads.values() if l.status == "active" and l.has_address()]
    rows.sort(key=lambda l: -l.score)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(GHL_COLUMNS)
        for l in rows:
            first, last = split_name(l.owner_name)
            addr = l.mailing_address or l.property_address
            city = l.mailing_city if l.mailing_address else l.property_city
            state = l.mailing_state if l.mailing_address else "OH"
            zipc = l.mailing_zip if l.mailing_address else l.property_zip
            tags = ["tax delinquent", f"{county.lower()} county", l.tier.lower()]
            if l.property_category:
                tags.append(l.property_category.lower())
            if l.tax_year:
                tags.append("certified delinquent")
            if l.advertised_years:
                tags.append("advertised delinquent")
            if l.absentee_owner:
                tags.append("absentee")
            if l.rental_registered:
                tags.append("rental")
            w.writerow([
                first, last, l.owner_name.title(), l.owner_name_2.title(), l.owner_phone, addr, city.title(),
                state, zipc, l.property_address, l.property_city.title(), l.property_zip, l.property_category,
                l.property_type, l.lead_type,
                f"{l.delinquent_amount:.2f}" if l.delinquent_amount is not None else "",
                f"{l.amount_owed:.2f}" if l.amount_owed is not None else "",
                f"{l.market_value:.0f}" if l.market_value else "", l.last_sale_date,
                l.score, l.tier, l.parcel_id, l.tax_year, " ".join(l.advertised_years),
                "Yes" if l.absentee_owner else "No", l.date_added, ",".join(tags),
            ])
    return len(rows)


DASHBOARD_FIELDS = (
    "doc_num", "owner_name", "owner_name_2", "owner_phone", "mailing_address", "mailing_city", "mailing_state",
    "mailing_zip", "property_address", "property_city", "property_zip", "amount_owed", "delinquent_amount",
    "tax_year", "advertised_years", "absentee_owner", "market_value", "homestead", "has_mortgage",
    "rental_registered", "rental_units", "last_sale_date", "property_category", "property_type",
    "last_sale_amount", "land_use", "flags", "score", "tier", "auditor_url", "date_added", "last_seen",
    "status", "removed_date",
)


def export_dashboard(path: Path, leads: dict[str, LeadRecord], meta: dict) -> None:
    rows = [{k: getattr(l, k) for k in DASHBOARD_FIELDS}
            for l in sorted(leads.values(), key=lambda l: -l.score) if l.has_address()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"meta": meta, "records": rows}, separators=(",", ":")), encoding="utf-8")
