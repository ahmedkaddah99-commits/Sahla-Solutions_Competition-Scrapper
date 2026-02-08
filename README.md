# Odoo Partners Scraper

Python scraper for collecting Odoo implementation partner data from the public partners directory and exporting clean results to CSV and Excel.

## What it does

- Scrapes partner rows from `https://www.odoo.com/partners/`
- Filters out non-partner UI rows (for example, "Find Best Match")
- Extracts core partner fields:
  - Partner Name
  - Tier
  - Location
  - References
  - Certified Experts
  - Profile URL
- Visits each partner profile and extracts extras:
  - Certified Versions
  - References Total
  - Customer Retention %
  - Largest Reference Users
  - Average Reference Users
  - Reference Industries
- Adds 22 fixed `RI_*` industry columns and fills missing values with `0`
- Exports to:
  - `odoo_partners_full_list_clean.csv`
  - `odoo_partners_full_list_clean.xlsx`

## Project files

- `odoo_partner_scraper.py`: main scraper script
- `requirements.txt`: Python dependencies
- `odoo_partners_full_list_clean.csv`: latest CSV output
- `odoo_partners_full_list_clean.xlsx`: latest Excel output

## Requirements

- Python 3.10+ (recommended)
- Internet connection

Install dependencies:

```powershell
pip install -r requirements.txt
```

## Run

```powershell
python odoo_partner_scraper.py
```

The default run in the script scrapes pages `1..188` and then writes both output files in the repo root.

## Configuration

Edit the `scrape_partners(...)` call in `odoo_partner_scraper.py` to tune behavior:

- `page_start`: first directory page (default `1`)
- `page_end`: last directory page (default `188`)
- `sleep_s`: delay between list pages in seconds (default `1.0`)
- `profile_sleep_s`: delay between profile fetches in seconds (default `0.0`)

Example:

```python
df_raw = scrape_partners(page_start=1, page_end=50, sleep_s=1.0, profile_sleep_s=0.1)
```

## Output schema

Core columns:

- `Partner Name`
- `Tier`
- `Location`
- `References`
- `Certified Experts`
- `Profile URL`
- `Certified Versions`
- `References Total`
- `Customer Retention %`
- `Largest Reference Users`
- `Average Reference Users`
- `Reference Industries`

Plus fixed `RI_*` columns for 22 known industries.

## Notes

- Scraping behavior and site structure may change over time.
- Respect the target website's terms and rate limits.
