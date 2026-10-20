#!/usr/bin/env python3
"""
scrape_nz_final.py
==================
Downloads NZ civil society organization websites from the Charities
Services NZ OData API using the confirmed working endpoint.

API endpoint (no authentication required, no registration needed):
    http://www.odata.charities.govt.nz/Organisations
    
Open data info page:
    https://www.charities.govt.nz/charities-in-new-zealand/the-charities-register/open-data

Columns used: Name, WebSiteURL
Output: nz_orgs.csv  (same folder as this script)

Usage
-----
    pip install requests
    python scrape_nz_final.py
"""

import csv, io, os, sys
from urllib.parse import urlparse
try:
    import requests
except ImportError:
    print("ERROR: pip install requests"); sys.exit(1)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT  = os.path.join(HERE, "nz_orgs.csv")

BASE = "http://www.odata.charities.govt.nz/Organisations"
HDRS = {"User-Agent":
    "Mozilla/5.0 (research accessibility audit; "
    "contact: muhammadsohaib.ayub@universityofgalway.ie)"}

def clean_url(raw):
    if not raw or str(raw).strip().lower() in ('','nan','n/a','none','-','null'):
        return ''
    u = str(raw).strip().rstrip('/')
    if not u.startswith('http'): u = 'https://' + u
    try:
        p = urlparse(u)
        return u.lower() if p.netloc and '.' in p.netloc else ''
    except: return ''

def main():
    print("=" * 60)
    print("New Zealand – Charities Services OData Scraper")
    print(f"Endpoint: {BASE}")
    print("=" * 60)

    print("\nDownloading full register ($returnall=true)...")
    try:
        r = requests.get(BASE,
            params={'$format':'csv','$returnall':'true',
                    '$select':'Name,WebSiteURL'},
            headers=HDRS, timeout=300, stream=True)
        r.raise_for_status()
    except Exception as e:
        print(f"ERROR: {e}")
        print("\nManual alternative:")
        print("  Open in browser: http://www.odata.charities.govt.nz/Organisations?$format=csv&$returnall=true&$select=Name,WebSiteURL")
        print("  Save file as: nz_raw.csv, then re-run with the file present")
        sys.exit(1)

    content = b''
    for chunk in r.iter_content(65536):
        content += chunk
        if len(content) % (1024*1024) < 65536:
            print(f"  Downloaded {len(content)//1024//1024} MB ...")

    print(f"  Complete: {len(content)/1e6:.1f} MB")

    rows = list(csv.DictReader(io.StringIO(
        content.decode('utf-8-sig', errors='replace'))))
    print(f"  Total rows: {len(rows):,}")

    records = []; seen = set()
    for row in rows:
        name = (row.get('Name') or '').strip()
        web  = clean_url(row.get('WebSiteURL') or '')
        if not name or not web: continue
        domain = urlparse(web).netloc.lstrip('www.')
        if domain in seen: continue
        seen.add(domain)
        records.append({'name': name, 'url': web,
                        'country': 'NZ',
                        'source': 'Charities Services NZ OData API'})

    with open(OUT, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['name','url','country','source'])
        w.writeheader(); w.writerows(records)

    print(f"\nUnique orgs with websites: {len(records):,}")
    print(f"Saved: {OUT}")
    print("\nSample (first 10):")
    for r in records[:10]:
        print(f"  {r['name'][:50]:50s}  {r['url']}")

if __name__ == '__main__':
    main()
