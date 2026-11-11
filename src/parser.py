"""Parse the Auditor's tab-delimited files (streamed - they are 50-300 MB)."""
from __future__ import annotations

import csv
import datetime as dt
import re
from pathlib import Path

csv.field_size_limit(10_000_000)

CSZ_RE = re.compile(r"^(.*?)[\s,]+([A-Z]{2})\s+(\d{5})(?:-?\d{4})?$")


def rows(path: Path):
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as f:
        yield from csv.DictReader(f, delimiter="\t")


def num(v) -> float:
    try:
        return float(str(v).replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


def clean(v) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()


def split_csz(text: str) -> tuple[str, str, str]:
    """'COLUMBUS OH 43215-1486' -> ('COLUMBUS', 'OH', '43215')."""
    t = clean(text).upper()
    m = CSZ_RE.match(t)
    return (m.group(1).strip(" ,"), m.group(2), m.group(3)) if m else (t, "", "")


def split_site(site: str) -> tuple[str, str, str]:
    """'872 - 874 SUMMIT ST, COLUMBUS, OH 43215' -> ('872 - 874 SUMMIT ST', 'COLUMBUS', '43215')."""
    parts = [p.strip() for p in clean(site).split(",")]
    street = parts[0] if parts else ""
    city = parts[1] if len(parts) > 2 else ""
    m = re.search(r"\b(\d{5})(?:-\d{4})?\s*$", clean(site))
    return street, city, (m.group(1) if m else "")


def iso(d: str) -> str:
    d = clean(d)
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%Y %H:%M:%S"):
        try:
            return dt.datetime.strptime(d[:19], fmt).date().isoformat()
        except ValueError:
            pass
    return ""


def hyphen_parcel(p: str) -> str:
    """'01008314500' or '010-083145-00' -> '010-083145-00'."""
    d = re.sub(r"\D", "", p or "")
    if len(d) == 11:
        return f"{d[:3]}-{d[3:9]}-{d[9:]}"
    if len(d) == 9:
        return f"{d[:3]}-{d[3:]}-00"
    return clean(p).strip('"')


def delinquent_balances(path: Path, min_amount: float) -> dict[str, dict]:
    """TaxDetail.txt -> {parcel: {...}} for parcels with an unpaid prior-year balance."""
    out = {}
    for r in rows(path):
        prior = num(r.get("TotPrior"))
        if prior < min_amount:
            continue
        pid = hyphen_parcel(r.get("Parcel Id", ""))
        out[pid] = {
            "prior": round(prior, 2),
            "delinquent": round(prior + max(0.0, num(r.get("TotInterest"))), 2),
            "total": round(max(0.0, num(r.get("TotTotal"))), 2),
            "penalty": round(num(r.get("TotPenalty")), 2),
        }
    return out


def parcel_info(path: Path, wanted: set[str]) -> dict[str, dict]:
    out = {}
    for r in rows(path):
        pid = hyphen_parcel(r.get("PARCEL ID", ""))
        if pid not in wanted:
            continue
        street, city, zipc = split_site(r.get("SiteAddress", ""))
        m_city, m_state, m_zip = split_csz(r.get("OwnerAddress2", ""))
        mail1 = clean(r.get("OwnerAddress1"))
        if not mail1:                                   # fall back to the tax-bill address
            mail1 = clean(r.get("TaxpayerAddress1"))
            m_city, m_state, m_zip = split_csz(r.get("TaxpayerAddress2", ""))
        out[pid] = {
            "owner_name": clean(r.get("OwnerName1")),
            "owner_name_2": clean(r.get("OwnerName2")),
            "mailing_address": mail1,
            "mailing_city": m_city,
            "mailing_state": m_state,
            "mailing_zip": m_zip,
            "property_address": street,
            "property_city": city or clean(r.get("City")),
            "property_zip": zipc or clean(r.get("ZipCode"))[:5],
            "tax_year": clean(r.get("CDQ")) if clean(r.get("CDQ")) not in ("0", "") else "",
            "land_use": clean(r.get("LUC")),
            "land_use_desc": clean(r.get("LUCDesc")),
            "homestead": clean(r.get("IsHomestead")).upper() in ("TRUE", "Y", "YES", "1"),
            "has_mortgage": bool(clean(r.get("BankCode")).strip("0")),
            "last_sale_date": iso(r.get("LastSaleDate", "")),
            "last_sale_amount": num(r.get("LastSaleAmount")) or None,
            "exempt": clean(r.get("ExemptStatus")),
        }
    return out


def market_values(path: Path, wanted: set[str]) -> dict[str, float]:
    best: dict[str, tuple[int, float]] = {}
    for r in rows(path):
        pid = hyphen_parcel(r.get("Parcel Id", ""))
        if pid not in wanted or clean(r.get("ValueType")).upper() != "BASE":
            continue
        yr = int(num(r.get("TaxYear")))
        val = num(r.get("MarketLand")) + num(r.get("MarketImpr"))
        if pid not in best or yr > best[pid][0]:
            best[pid] = (yr, val)
    return {k: v for k, (_, v) in best.items()}


def rental_contacts(path: Path, wanted: set[str]) -> dict[str, dict]:
    out = {}
    for r in rows(path):
        pid = hyphen_parcel(r.get("PARCEL ID", ""))
        if pid not in wanted:
            continue
        phone = clean(r.get("Owner_PhoneNumber")) or clean(r.get("MgmtCont_PhoneNumber"))
        out[pid] = {"phone": phone, "units": int(num(r.get("NumUnits")))}
    return out


def advertised_parcels(path: Path) -> set[str]:
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    it = ws.iter_rows(values_only=True)
    header = [clean(c).upper() for c in next(it)]
    col = next((i for i, h in enumerate(header) if "PARCEL" in h), 0)
    return {hyphen_parcel(str(r[col])) for r in it if r and r[col]}
