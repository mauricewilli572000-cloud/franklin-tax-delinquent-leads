import datetime as dt
from pathlib import Path

from src import parser
from src.schema import LeadRecord
from src.scoring import score

FX = Path(__file__).parent / "fixtures"


def test_parcel_formats():
    assert parser.hyphen_parcel("01008314500") == "010-083145-00"
    assert parser.hyphen_parcel('"010-000034-00"') == "010-000034-00"


def test_address_splitting():
    assert parser.split_site("872 - 874 SUMMIT ST, COLUMBUS, OH 43215") == ("872 - 874 SUMMIT ST", "COLUMBUS", "43215")
    assert parser.split_csz("DAYTON OH 45402-1234") == ("DAYTON", "OH", "45402")
    assert parser.split_csz("COLUMBUS OH    43215") == ("COLUMBUS", "OH", "43215")


def test_delinquent_filter_and_enrichment():
    bal = parser.delinquent_balances(FX / "TaxDetail.txt", 250)
    assert set(bal) == {"010-000034-00", "600-000001-00"}   # paid, not-yet-late and tiny balances dropped
    assert bal["010-000034-00"]["delinquent"] == 3382.07   # late current-year balance
    assert bal["600-000001-00"]["delinquent"] == 5000.00   # prior-year balance
    info = parser.parcel_info(FX / "Parcel.txt", set(bal))
    p = info["010-000034-00"]
    assert p["property_address"] == "1645 E GREENWAY AV" and p["property_zip"] == "43203"
    assert (p["mailing_city"], p["mailing_state"], p["mailing_zip"]) == ("DAYTON", "OH", "45402")
    assert p["tax_year"] == "2021"


def test_exclusions():
    import run_pipeline
    info = parser.parcel_info(FX / "Parcel.txt", {"600-000001-00"})
    assert run_pipeline.excluded(info["600-000001-00"])


def test_scoring():
    lead = LeadRecord(doc_num="x", owner_name="SMITH JOHN ESTATE", delinquent_amount=8000, tax_year="2021",
                      property_address="1 MAIN ST", mailing_address="9 ELM ST", mailing_state="OH",
                      land_use="510", market_value=60000)
    score(lead, dt.date(2026, 11, 10))
    assert lead.absentee_owner and lead.tier == "Hot"
    assert "Estate / heirs" in lead.flags
