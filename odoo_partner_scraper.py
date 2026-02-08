"""
Odoo Implementation Partners Scraper (Clean + Correct Columns + Profile Extras + FIXED RI_* industries)
- Scrapes partner rows from https://www.odoo.com/partners/
- Filters out non-partner UI rows like "Find Best Match"
- Correct column/value alignment
- Exports BOTH CSV and Excel (.xlsx)

Profile Extras (per partner Profile URL):
- Certified Versions (e.g., v19:1; v18:4; v17:2)
- References Total
- Customer Retention %
- References Sizes (Largest / Average users)
- Reference Industries (bounded, and ONLY the 22 known industries)

RI_* Columns:
- Exactly 22 fixed RI columns, one per industry in ALLOWED_INDUSTRIES
- Missing industry => 0
"""

import re
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin


# =========================
# Config
# =========================
BASE = "https://www.odoo.com"
PAGE_URL = "https://www.odoo.com/partners/page/{}?country_all=True"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Connection": "keep-alive",
}

# =========================
# List-page regex patterns
# =========================
TIER_RE = re.compile(r"\b(Gold|Silver|Ready)\b")
REFS_RE = re.compile(r"\b(\d+)\s+References?\b")
EXPERTS_RE = re.compile(r"\b(\d+)\s+Certified Experts?\b")
LOC_RE = re.compile(r"%\s+(.+?)\s+Average Project:", re.DOTALL)

# =========================
# Fixed industries (22)
# =========================
ALLOWED_INDUSTRIES = [
    "Agriculture",
    "Construction & Renovation",
    "ECO liable to deduct TCS u/s 52",
    "ECO liable to pay GST u/s 9(5)",
    "Education",
    "Entertainment / Media",
    "Finance / Legal / Insurance",
    "Food / Hospitality / Tourism / Beverage",
    "Government",
    "HR / Administrative / Consulting",
    "Health / Social Welfare / Pharmaceutical",
    "Households",
    "IT / Communication / Marketing",
    "Manufacturing / Maintenance",
    "Mining & Quarrying",
    "NGO",
    "Other Services",
    "Real Estate",
    "Science & Technology",
    "Transportation/Logistics",
    "Utilities / Energy / Water supply",
    "Wholesale / Retail",
]


# =========================
# Helpers: fixed RI columns
# =========================
def make_safe_ri_column(label: str) -> str:
    """
    Fixed safe column names for the 22 industries.
    """
    lab = label.strip()
    lab = re.sub(r"\s+", " ", lab)
    lab = re.sub(r"[^A-Za-z0-9]+", "_", lab)
    lab = re.sub(r"_+", "_", lab).strip("_")
    return f"RI_{lab}"


ALLOWED_LABEL_TO_RI_COL = {lab: make_safe_ri_column(lab) for lab in ALLOWED_INDUSTRIES}
ALLOWED_RI_COLS = [ALLOWED_LABEL_TO_RI_COL[lab] for lab in ALLOWED_INDUSTRIES]


def init_ri_zero_dict() -> dict:
    return {col: 0 for col in ALLOWED_RI_COLS}


# =========================
# Core parsing (list page)
# =========================
def parse_partner_text(text: str):
    """
    Parse one candidate anchor's visible text into structured fields.
    Returns dict with required columns or None if not a valid partner row.
    """
    text = " ".join(text.split()).strip()

    m_tier = TIER_RE.search(text)
    if not m_tier:
        return None

    tier = m_tier.group(1)
    name = text[:m_tier.start()].strip()

    if not name or name.lower() == "find best match":
        return None

    m_loc = LOC_RE.search(text)
    location = m_loc.group(1).strip(" ,") if m_loc else "N/A"

    m_refs = REFS_RE.search(text)
    refs = m_refs.group(1) if m_refs else "0"

    m_exp = EXPERTS_RE.search(text)
    experts = m_exp.group(1) if m_exp else "0"

    if location == "N/A" and refs == "0" and experts == "0":
        return None

    return {
        "Partner Name": name,
        "Tier": tier,
        "Location": location,
        "References": refs,
        "Certified Experts": experts,
    }


# =========================
# Profile parsing (extras)
# =========================
def fetch_profile_extras(session: requests.Session, profile_url: str, sleep_s: float = 0.0):
    """
    Extracts profile extras + fills fixed RI columns.
    Industries:
    - bounded to the "References - N" section
    - only matches your 22 industries (prevents garbage)
    """
    extras = {
        "Certified Versions": "",
        "References Total": None,
        "Customer Retention %": None,
        "Largest Reference Users": None,
        "Average Reference Users": None,
        "Reference Industries": "",
    }
    extras.update(init_ri_zero_dict())

    if not profile_url:
        return extras

    try:
        r = session.get(profile_url, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            return extras
    except Exception:
        return extras

    soup = BeautifulSoup(r.text, "html.parser")
    raw_space = soup.get_text(" ", strip=True)
    norm = re.sub(r"\s+", " ", raw_space).strip()

    if sleep_s:
        time.sleep(sleep_s)

    # ---- Certified versions ----
    cert_pairs = re.findall(r"\b(\d+)\s+Certified\s+v(\d+)\b", norm, flags=re.IGNORECASE)
    if cert_pairs:
        agg = {}
        for cnt, ver in cert_pairs:
            key = f"v{ver}"
            agg[key] = agg.get(key, 0) + int(cnt)
        extras["Certified Versions"] = "; ".join(
            f"{k}:{agg[k]}" for k in sorted(agg.keys(), key=lambda x: int(x[1:]), reverse=True)
        )

    # ---- References Total ----
    m_total = re.search(r"\bReferences\s*-\s*(\d+)\b", norm, flags=re.IGNORECASE)
    if m_total:
        extras["References Total"] = int(m_total.group(1))

    # ---- Customer Retention ----
    m_ret = re.search(r"\bCustomer\s+Retention\b.*?\b(\d{1,3})\s*%?\b", norm, flags=re.IGNORECASE)
    if m_ret:
        extras["Customer Retention %"] = int(m_ret.group(1))

    # ---- References Sizes: Largest / Average ----
    m_largest = re.search(
        r"\bReferences\s+Sizes\b.*?\bLargest:\s*~?\s*(\d+)\s*\+?\s*users?\b",
        norm, flags=re.IGNORECASE
    )
    if m_largest:
        extras["Largest Reference Users"] = int(m_largest.group(1))

    m_avg = re.search(
        r"\bReferences\s+Sizes\b.*?\bAverage:\s*~?\s*(\d+)\s*\+?\s*users?\b",
        norm, flags=re.IGNORECASE
    )
    if m_avg:
        extras["Average Reference Users"] = int(m_avg.group(1))

    # ---- Industries block (bounded) ----
    if not m_total:
        return extras

    tail = norm[m_total.end():].strip()

    stop_markers = [
        r"\bReferences\s+Sizes\b",
        r"\bCustomer\s+Retention\b",
        r"\bCertified\s+Experts?\b",
        r"\bAverage\s+Project\b",
        r"\bIndustries\b",
        r"\bAbout\b",
        r"\bGold\b",
        r"\bSilver\b",
        r"\bReady\b",
    ]
    stop_re = re.compile("|".join(stop_markers), flags=re.IGNORECASE)
    m_stop = stop_re.search(tail)
    block = tail[:m_stop.start()].strip() if m_stop else tail

    # Match ONLY the 22 industries preceded by a number, anywhere in the block
    label_alt = "|".join(re.escape(x) for x in sorted(ALLOWED_INDUSTRIES, key=len, reverse=True))
    patt = re.compile(rf"\b(\d{{1,6}})\s+({label_alt})\b")

    found = patt.findall(block)
    if found:
        dedup = {}
        order = []
        for n_str, lab in found:
            n = int(n_str)
            if lab not in dedup:
                order.append(lab)
                dedup[lab] = n
            else:
                dedup[lab] = max(dedup[lab], n)

        # text cell for debugging/human inspection
        extras["Reference Industries"] = " ".join([f"{lab} {dedup[lab]}" for lab in order])

        # fixed RI columns
        for lab, cnt in dedup.items():
            col = ALLOWED_LABEL_TO_RI_COL.get(lab)
            if col:
                extras[col] = int(cnt)

    return extras


# =========================
# Scraper
# =========================
def scrape_partners(page_start=1, page_end=188, sleep_s=1.0, profile_sleep_s=0.0):
    """
    Scrape partners from page_start..page_end inclusive.
    Adds profile extras for each partner URL (cached).
    """
    session = requests.Session()
    all_rows = []
    profile_cache = {}

    for page_num in range(page_start, page_end + 1):
        url = PAGE_URL.format(page_num)
        print(f"Fetching page {page_num}: {url}")

        r = session.get(url, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            print(f"  -> HTTP {r.status_code}. Skipping.")
            continue

        soup = BeautifulSoup(r.text, "html.parser")

        for a in soup.find_all("a"):
            t = a.get_text(" ", strip=True)
            if not t or not TIER_RE.search(t):
                continue

            parsed = parse_partner_text(t)
            if not parsed:
                continue

            href = a.get("href") or ""
            profile_url = urljoin(BASE, href) if href.startswith("/") else ""
            parsed["Profile URL"] = profile_url

            if profile_url:
                if profile_url not in profile_cache:
                    profile_cache[profile_url] = fetch_profile_extras(
                        session, profile_url, sleep_s=profile_sleep_s
                    )
                parsed.update(profile_cache[profile_url])
            else:
                # ensure RI columns exist even without profile
                parsed.update(init_ri_zero_dict())

            all_rows.append(parsed)

        time.sleep(sleep_s)

    return pd.DataFrame(all_rows)


# =========================
# Clean + Export
# =========================
def clean_and_export(df: pd.DataFrame,
                     csv_path="odoo_partners_full_list_clean.csv",
                     xlsx_path="odoo_partners_full_list_clean.xlsx"):
    """
    Ensure correct types, correct columns, remove duplicates, export.
    """
    base_cols = [
        "Partner Name", "Tier", "Location", "References", "Certified Experts", "Profile URL",
        "Certified Versions", "References Total", "Customer Retention %",
        "Largest Reference Users", "Average Reference Users",
        "Reference Industries",
    ]
    expected_cols = base_cols + ALLOWED_RI_COLS

    df = df.reindex(columns=expected_cols)

    df["Partner Name"] = df["Partner Name"].fillna("").astype(str).str.strip()
    df = df[df["Partner Name"].ne("")]
    df = df[~df["Partner Name"].str.fullmatch(r"Find Best Match", case=False, na=False)]

    for col in ["References", "Certified Experts"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    for col in ["References Total", "Customer Retention %", "Largest Reference Users", "Average Reference Users"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in ALLOWED_RI_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    df = df[(df["References"] > 0) | (df["Certified Experts"] > 0)]
    df = df.drop_duplicates(subset=["Partner Name", "Tier", "Location"]).reset_index(drop=True)

    df.to_csv(csv_path, index=False)
    df.to_excel(xlsx_path, index=False)

    print(f"\n✅ Exported CSV : {csv_path}")
    print(f"✅ Exported XLSX: {xlsx_path}")
    print(f"✅ Rows: {len(df)}")
    print(f"✅ Fixed RI columns: {len(ALLOWED_RI_COLS)}")

    return df


# =========================
# Run
# =========================
if __name__ == "__main__":
    # Quick test:
    df_raw = scrape_partners(page_start=1, page_end=188, sleep_s=1.0, profile_sleep_s=0.0)

    # Full run later:
    # df_raw = scrape_partners(page_start=1, page_end=186, sleep_s=1.0, profile_sleep_s=0.0)

    df_final = clean_and_export(
        df_raw,
        csv_path="odoo_partners_full_list_clean.csv",
        xlsx_path="odoo_partners_full_list_clean.xlsx"
    )

    print("\nPreview:")
    print(df_final.head(15).to_string(index=False))
