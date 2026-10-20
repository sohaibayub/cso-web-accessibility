#!/usr/bin/env python3
"""
scrape_aus.py
=============
Collects Australian civil society organization websites from the
Australian Charities and Not-for-profits Commission (ACNC) open register.

Two methods (tried in order):
  1. ACNC API via data.gov.au  (automatic, no download needed)
  2. Manual CSV from data.gov.au (if API is blocked on your network)

MANUAL DOWNLOAD FALLBACK
--------------------------
If Method 1 fails, download the CSV manually:
  1. Go to: https://data.gov.au/dataset/ds-dga-b050b242-4487-4306-abf5-07ca073e5594/details
  2. Click the CSV download link for the charity register
  3. Save the file as: acnc_charities.csv  (in the same folder as this script)
  4. Re-run: python scrape_aus.py --csv acnc_charities.csv

Output: aus_orgs.csv  (same folder as script)

Usage
-----
    pip install requests
    python scrape_aus.py               # tries API automatically
    python scrape_aus.py --csv acnc_charities.csv   # use manual CSV
"""

import argparse
import csv
import os
import sys
import time
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    print("ERROR: requests is required. Run: pip install requests")
    sys.exit(1)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT  = os.path.join(HERE, "aus_orgs.csv")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (research accessibility audit; "
        "contact: muhammadsohaib.ayub@universityofgalway.ie)"
    )
}

# data.gov.au CKAN API for ACNC charity register
ACNC_API      = "https://data.gov.au/api/3/action/datastore_search"
ACNC_RESOURCE = "f6e33999-f56c-4d68-f0ca-c4f75be6b5cd"
PAGE_SIZE     = 1000

# Known possible column name variants in the ACNC CSV
NAME_COLS    = ["Charity_Legal_Name", "charity_legal_name", "Name", "legal_name"]
WEB_COLS     = ["Website", "website", "Website_Address", "website_address"]
STATUS_COLS  = ["Registration_status", "registration_status",
                "Status", "RegistrationStatus"]


def clean_url(raw):
    if not raw:
        return ""
    u = str(raw).strip().rstrip("/ ")
    junk = {"n/a","na","none","www","-","tbc","null","NULL","http://","https://","#"}
    if u.lower() in junk:
        return ""
    if not u.startswith("http"):
        u = "https://" + u
    try:
        p = urlparse(u)
        if not p.netloc or "." not in p.netloc:
            return ""
    except Exception:
        return ""
    return u.lower()


def first(d, keys, default=""):
    for k in keys:
        if k in d and d[k]:
            return str(d[k]).strip()
    return default


# ── Method 1: data.gov.au CKAN API ───────────────────────────────────────────

def scrape_via_api():
    print("Method 1: Fetching ACNC register via data.gov.au API ...")
    print(f"  URL: {ACNC_API}?resource_id={ACNC_RESOURCE}")

    records = []
    offset  = 0
    total   = None

    while True:
        try:
            r = requests.get(
                ACNC_API,
                params={
                    "resource_id": ACNC_RESOURCE,
                    "limit": PAGE_SIZE,
                    "offset": offset,
                    "fields": ("Charity_Legal_Name,Website,"
                               "Registration_status,Charity_ABN")
                },
                headers=HEADERS,
                timeout=30,
                allow_redirects=True
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"  ERROR at offset {offset}: {e}")
            return None          # signal caller to try manual CSV

        if not data.get("success"):
            print(f"  API error: {data.get('error', data)}")
            return None

        result = data.get("result", {})
        if total is None:
            total = result.get("total", 0)
            print(f"  Total charities in register: {total:,}")

        batch = result.get("records", [])
        if not batch:
            break

        for row in batch:
            status = first(row, STATUS_COLS).lower()
            if status and "register" not in status:
                continue
            name = first(row, NAME_COLS)
            web  = clean_url(first(row, WEB_COLS))
            if name and web:
                records.append({
                    "name":    name,
                    "url":     web,
                    "country": "AUS",
                    "source":  "ACNC Australian Charity Register (data.gov.au)"
                })

        offset += len(batch)
        print(f"  {offset:>6,} / {total:,}  |  with websites: {len(records):,}")
        time.sleep(0.3)

        if offset >= total:
            break

    return records


# ── Method 2: parse manually downloaded CSV ────────────────────────────────────

def scrape_from_csv(csv_path):
    print(f"Method 2: Parsing manually downloaded ACNC CSV: {csv_path}")
    records = []
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        print(f"  Columns: {reader.fieldnames[:6]} ...")
        for row in reader:
            status = first(row, STATUS_COLS).lower()
            if status and "register" not in status:
                continue
            name = first(row, NAME_COLS)
            web  = clean_url(first(row, WEB_COLS))
            if name and web:
                records.append({
                    "name":    name,
                    "url":     web,
                    "country": "AUS",
                    "source":  "ACNC Australian Charity Register (manual CSV)"
                })
    return records


# ── Deduplicate ───────────────────────────────────────────────────────────────

def dedup(records):
    seen, out = set(), []
    for r in records:
        domain = urlparse(r["url"]).netloc.lstrip("www.")
        if domain not in seen:
            seen.add(domain)
            out.append(r)
    return out


# ── Save CSV ──────────────────────────────────────────────────────────────────

def save(records):
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f, fieldnames=["name","url","country","source"],
            extrasaction="ignore"
        )
        w.writeheader()
        w.writerows(records)
    print(f"\nSaved: {OUT}  ({len(records):,} organizations)")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Scrape ACNC charity register")
    parser.add_argument(
        "--csv", default=None, metavar="PATH",
        help="Path to manually downloaded ACNC CSV (skips API)"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Australia – ACNC Charity Register Scraper")
    print("=" * 60)

    if args.csv:
        csv_path = args.csv
        if not os.path.isabs(csv_path):
            csv_path = os.path.join(HERE, csv_path)
        records = scrape_from_csv(csv_path)
    else:
        records = scrape_via_api()
        if records is None:
            print()
            print("API failed. Manual download instructions:")
            print("  1. Go to: https://data.gov.au/dataset/ds-dga-b050b242-4487-4306-abf5-07ca073e5594/details")
            print("  2. Download the CSV charity register file")
            print("  3. Save as acnc_charities.csv in this folder")
            print("  4. Run: python scrape_aus.py --csv acnc_charities.csv")
            sys.exit(1)

    records = dedup(records)
    print(f"\nUnique organizations with websites: {len(records):,}")
    save(records)

    print("\nSample (first 10):")
    for r in records[:10]:
        print(f"  {r['name'][:50]:50s}  {r['url']}")


if __name__ == "__main__":
    main()
