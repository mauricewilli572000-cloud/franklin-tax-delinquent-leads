# Franklin County, OH — Tax Delinquent Leads

Motivated-seller leads from parcels with **unpaid prior-year property tax**, built like
`hamilton-tax-delinquent-leads`.

**Sources (Franklin County Auditor, official, free):**
- Monthly *Tax Accounting* data drop — `apps.franklincountyauditor.com/Outside_User_Files/`
  (`TaxDetail.txt` balances, `Parcel.txt` owner/addresses/CDQ, `Value.txt`, `RentalContact.txt` phones)
- Annual advertised delinquent list — `auditor.franklincountyohio.gov/Real-Estate/Delinquent-List-to-Publish`

**Outputs:** `docs/index.html` dashboard · `docs/franklin_tax_delinquent.json` (also read by
ohio-lead-stacker) · `data/ghl_franklin_tax_delinquent.csv` for GoHighLevel.

A parcel is a lead when it owes $250+ that is past due (a prior-year balance, or a balance already charged a late penalty) and it isn't government,
exempt or utility property. Parcels that pay off are kept but marked `removed`.

Runs daily (~6:23 AM ET) and only rebuilds when the Auditor posts a new drop.

```powershell
python run_pipeline.py --force
python -m pytest -q
```
