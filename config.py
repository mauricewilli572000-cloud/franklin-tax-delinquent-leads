"""
Franklin County, OH - Tax Delinquent lead scraper configuration.

Sources (all official Franklin County Auditor files, no login, no captcha):

* Monthly "Tax Accounting" data drop
  https://apps.franklincountyauditor.com/Outside_User_Files/{year}/{date} Tax Accounting/Tab-Delimited.zip
    TaxDetail.txt     every parcel's tax charges, payments and balances
                      (TotPrior > 0  ->  unpaid prior-year = delinquent)
    Parcel.txt        site address, owner, owner mailing address, CDQ (certified
                      delinquent year), land use, homestead, last sale
    Value.txt         market value
    RentalContact.txt rental registration with owner / manager phone numbers
* Annual advertised delinquent list (published each fall)
  https://auditor.franklincountyohio.gov/Real-Estate/Delinquent-List-to-Publish
"""
from pathlib import Path

COUNTY = "Franklin"
STATE = "OH"
LEAD_TYPE = "Tax Delinquent"

# --------------------------------------------------------------------------
# Source URLs
# --------------------------------------------------------------------------
APPS_BASE = "https://apps.franklincountyauditor.com"
OUTSIDE_FILES = f"{APPS_BASE}/Outside_User_Files/"
TAB_ZIP_NAME = "Tab-Delimited.zip"
# Files we need from the monthly drop. Newer drops sometimes contain only some
# of them, so each file is taken from the newest drop that has it.
NEEDED_FILES = ("TaxDetail.txt", "Parcel.txt", "Value.txt", "RentalContact.txt")
REQUIRED_FILES = ("TaxDetail.txt", "Parcel.txt")
MAX_DROPS_TO_SCAN = 5

ADVERTISED_PAGE = "https://auditor.franklincountyohio.gov/Real-Estate/Delinquent-List-to-Publish"
# Parcel page on the Auditor's property search (dashboard link)
AUDITOR_PARCEL_URL = "https://property.franklincountyauditor.com/_web/propertycard/propertycard.aspx?pin={parcel}"

HTTP_TIMEOUT = 300
HTTP_RETRIES = 4

# --------------------------------------------------------------------------
# Filtering
# --------------------------------------------------------------------------
# Minimum unpaid prior-year balance to count as a lead.
MIN_DELINQUENT = 250.00
# Land use codes that are never sellers: exempt/government (600s), utilities (800s).
EXCLUDE_LUC_RANGES = [(600, 699), (800, 899)]
EXCLUDE_OWNER_PATTERNS = [
    r"\bCITY OF\b", r"\bVILLAGE OF\b", r"\bTOWNSHIP\b", r"\bBOARD OF\b", r"\bCOUNTY COMM",
    r"\bFRANKLIN COUNTY\b", r"\bSTATE OF OHIO\b", r"\bUNITED STATES\b", r"\bLAND REUTILIZATION\b",
    r"\bLAND BANK\b", r"\bCENTRAL OHIO COMMUNITY IMPROVEMENT\b", r"\bPORT AUTHORITY\b",
    r"\bMETROPOLITAN HOUSING\b", r"\bSCHOOL DIST", r"\bRAILROAD\b", r"\bRAILWAY\b",
    r"\bBOARD OF EDUCATION\b", r"\bCOLUMBUS CITY SCHOOL",
]

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "raw"                      # downloads (gitignored)
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"
RECORDS_JSON = DATA_DIR / "records.json"
PENDING_JSON = DATA_DIR / "pending_records.json"   # leads missing an address
STATE_JSON = DATA_DIR / "state.json"
GHL_CSV = DATA_DIR / "ghl_franklin_tax_delinquent.csv"
DASHBOARD_JSON = DOCS_DIR / "franklin_tax_delinquent.json"
DASHBOARD_CSV = DOCS_DIR / "franklin_tax_delinquent_ghl.csv"
