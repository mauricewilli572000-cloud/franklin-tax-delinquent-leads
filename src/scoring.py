"""Motivated-seller scoring for tax delinquent parcels (0-100). Mirrors Hamilton."""
from __future__ import annotations

import datetime as dt
import re

from .property_type import HOUSE_CATEGORIES, classify
from .schema import LeadRecord

ESTATE_RE = re.compile(r"(?<!REAL )\b(ESTATE|EST OF|HEIRS|DECEASED|DECD|UNKNOWN HEIRS|SURVIVING)\b")
TRUST_RE = re.compile(r"\b(TRUST|TRUSTEE|TR)\b")
BUSINESS_RE = re.compile(r"\b(LLC|L L C|INC|CORP|CORPORATION|COMPANY|CO|LTD|LP|LLP|PARTNERSHIP|BANK|"
                         r"ASSOCIATION|ASSN|CHURCH|MINISTRIES)\b")


def _norm_street(s: str) -> str:
    s = re.sub(r"^\s*(\d+)\s*-\s*\d+\b", r"\1", (s or "").upper())   # '803 - 805 SUMMIT' -> '803 SUMMIT'
    s = re.sub(r"[^A-Z0-9 ]", "", s)
    s = re.sub(r"\b(STREET|ST|AVENUE|AVE|AV|ROAD|RD|DRIVE|DR|LANE|LN|COURT|CT|PLACE|PL|BOULEVARD|BLVD)\b", "", s)
    return re.sub(r"\s+", " ", s).strip()


def score(lead: LeadRecord, today: dt.date | None = None) -> LeadRecord:
    today = today or dt.date.today()
    pts = 0
    flags: list[str] = []
    amt = lead.delinquent_amount or 0

    if amt >= 15000:
        pts += 30; flags.append("$15k+ delinquent")
    elif amt >= 7500:
        pts += 24; flags.append("$7.5k+ delinquent")
    elif amt >= 3000:
        pts += 16; flags.append("$3k+ delinquent")
    elif amt >= 1000:
        pts += 9

    if lead.tax_year.isdigit():
        pts += 12; flags.append(f"Certified delinquent {lead.tax_year}")
        yrs = max(0, today.year - int(lead.tax_year))
        if yrs >= 3:
            pts += 8; flags.append(f"{yrs}+ yrs delinquent")
    if lead.advertised_years:
        pts += 10
        flags.append("Advertised " + ",".join(lead.advertised_years))

    if lead.mailing_address and lead.property_address:
        lead.absentee_owner = (_norm_street(lead.mailing_address) != _norm_street(lead.property_address)
                               and not lead.homestead)
    if lead.absentee_owner:
        pts += 14; flags.append("Absentee owner")
    lead.out_of_state = bool(lead.mailing_state) and lead.mailing_state != "OH"
    if lead.out_of_state:
        pts += 6; flags.append(f"Out of state ({lead.mailing_state})")

    owner = f"{lead.owner_name} {lead.owner_name_2}"
    if ESTATE_RE.search(owner):
        pts += 14; flags.append("Estate / heirs")
    elif TRUST_RE.search(owner):
        pts += 4; flags.append("Trust")
    if BUSINESS_RE.search(owner):
        pts -= 6; flags.append("Business owner")

    if lead.rental_registered:
        pts += 6; flags.append("Registered rental")
    if not lead.has_mortgage and lead.property_address:
        pts += 4; flags.append("No mortgage escrow")
    mv = lead.market_value or 0
    if mv >= 10000 and amt:
        ratio = amt / mv
        if ratio >= 0.10:
            pts += 8; flags.append(f"Owes {ratio:.0%} of value")
        elif ratio >= 0.05:
            pts += 4
    if lead.last_sale_date[:4].isdigit():
        held = today.year - int(lead.last_sale_date[:4])
        if held >= 15:
            pts += 6; flags.append(f"Owned since {lead.last_sale_date[:4]}")

    lead.property_category, lead.property_type = classify(lead.land_use)
    if lead.land_use_desc and lead.property_type.startswith(("Unknown", "Other")):
        lead.property_type = lead.land_use_desc.title()
    if lead.property_category == "Vacant Land":
        pts -= 12; flags.append("Vacant land")
    if lead.property_category in HOUSE_CATEGORIES:
        pts += 6; flags.append(lead.property_category)
    elif lead.property_category == "Apartments (5+)":
        pts += 3; flags.append("Apartments")

    lead.score = max(0, min(100, pts))
    lead.tier = "Hot" if lead.score >= 55 else "Warm" if lead.score >= 32 else "Cold"
    lead.flags = flags
    return lead
