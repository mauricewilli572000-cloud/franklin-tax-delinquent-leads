"""Lead record schema - same field names as hamilton-tax-delinquent-leads."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class LeadRecord:
    # --- shared core schema (same names as the other scrapers) ---
    doc_num: str                     # unique key -> parcel number, e.g. 010-000034-00
    owner_name: str = ""
    mailing_address: str = ""
    mailing_city: str = ""
    mailing_state: str = ""
    mailing_zip: str = ""
    property_address: str = ""
    property_city: str = ""
    property_zip: str = ""
    lead_type: str = "Tax Delinquent"
    case_number: str = ""
    filing_date: str = ""
    amount_owed: float | None = None          # total balance due now (TotTotal)
    county: str = "Franklin"
    source_url: str = ""

    # --- tax-delinquent specific ---
    parcel_id: str = ""
    owner_name_2: str = ""
    owner_phone: str = ""                     # from rental registration, when registered
    delinquent_amount: float | None = None    # unpaid prior-year balance (TotPrior + interest)
    tax_year: str = ""                        # CDQ: year certified delinquent ("" if not yet certified)
    land_use: str = ""
    land_use_desc: str = ""
    property_category: str = ""
    property_type: str = ""
    market_value: float | None = None
    homestead: bool = False
    has_mortgage: bool = False                # a bank/escrow code on the parcel
    rental_registered: bool = False
    rental_units: int = 0
    last_sale_date: str = ""
    last_sale_amount: float | None = None
    advertised_years: list[str] = field(default_factory=list)
    absentee_owner: bool = False
    out_of_state: bool = False
    flags: list[str] = field(default_factory=list)
    score: int = 0
    tier: str = "Cold"
    auditor_url: str = ""

    # --- tracking across runs ---
    date_added: str = ""
    last_seen: str = ""
    status: str = "active"                    # active | removed (paid / dropped off)
    removed_date: str = ""
    amount_history: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "LeadRecord":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def has_address(self) -> bool:
        return bool(self.mailing_address.strip() or self.property_address.strip())
