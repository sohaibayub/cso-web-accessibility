#!/usr/bin/env python3
"""
parse_aus_csv.py
================
Parses the ACNC charity register CSV downloaded from data.gov.au and
produces aus_orgs.csv ready for ward_civil.py.

The CSV has these key columns (confirmed from datadotgov_main.csv):
  Charity_Legal_Name   - organisation name
  Charity_Website      - website URL
  Country              - always "Australia" (pre-filtered to AUS)

Download the CSV from:
  https://data.gov.au/dataset/ds-dga-b050b242-4487-4306-abf5-07ca073e5594/details

Usage
-----
    pip install pandas
    python parse_aus_csv.py datadotgov_main.csv
    python parse_aus_csv.py            # looks for datadotgov_main.csv in same folder
"""

import csv
import os
import sys
from urllib.parse import urlparse

try:
    import pandas as pd
except ImportError:
    print("ERROR: pandas required. Run: pip install pandas")
    sys.exit(1)

HERE = os.path.dirname(os.path.abspath(__file__))


def clean_url(raw):
    if not raw or str(raw).strip().lower() in ('nan','n/a','na','none','-','','null'):
        return ''
    u = str(raw).strip().rstrip('/')
    if not u.startswith('http'):
        u = 'https://' + u
    try:
        p = urlparse(u)
        if not p.netloc or '.' not in p.netloc:
            return ''
    except Exception:
        return ''
    return u.lower()


def main():
    # Accept filename as argument or look for default
    if len(sys.argv) >= 2:
        csv_in = sys.argv[1]
        if not os.path.isabs(csv_in):
            csv_in = os.path.join(HERE, csv_in)
    else:
        csv_in = os.path.join(HERE, 'datadotgov_main.csv')

    if not os.path.exists(csv_in):
        print(f"ERROR: file not found: {csv_in}")
        print("Download from: https://data.gov.au/dataset/ds-dga-b050b242-4487-4306-abf5-07ca073e5594/details")
        sys.exit(1)

    print(f"Reading: {csv_in}")
    df = pd.read_csv(csv_in, encoding='utf-8', encoding_errors='replace',
                     low_memory=False)
    print(f"  Total rows: {len(df):,}")
    print(f"  Columns: {list(df.columns[:6])} ...")

    records       = []
    seen_domains  = set()
    seen_names    = set()

    for _, row in df.iterrows():
        name = str(row.get('Charity_Legal_Name', '') or '').strip()
        web  = clean_url(row.get('Charity_Website', ''))
        if not name or not web:
            continue
        domain = urlparse(web).netloc.lstrip('www.')
        if domain in seen_domains or name.lower() in seen_names:
            continue
        seen_domains.add(domain)
        seen_names.add(name.lower())
        records.append({
            'name':    name,
            'url':     web,
            'country': 'AUS',
            'source':  'ACNC Australian Charity Register (data.gov.au)'
        })

    out = os.path.join(HERE, 'aus_orgs.csv')
    with open(out, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['name','url','country','source'])
        w.writeheader()
        w.writerows(records)

    print(f"\nUnique organizations with websites: {len(records):,}")
    print(f"Saved: {out}")

    print("\nSample (first 10):")
    for r in records[:10]:
        print(f"  {r['name'][:50]:50s}  {r['url']}")


if __name__ == '__main__':
    main()
