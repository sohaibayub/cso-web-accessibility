#!/usr/bin/env python3
"""
scrape_four_countries.py
========================
Collects civil society organization websites from four countries to complement
the Ireland dataset collected from the national member directory (irl_orgs.csv).

Each country's output is saved as a CSV in the same format:
    name, url, country, source

Sources used
------------
UK  (England & Wales)
    Charity Commission for England and Wales (CCEW) open register bulk data
    URL: https://register-of-charities.charitycommission.gov.uk/register/full-register-download
    Data: ~170,000 registered charities, filtered to those with website URLs
    Licence: Open Government Licence v3.0

USA (Minnesota)
    Minnesota Council of Nonprofits (MCN) public member list
    URL: https://minnesotanonprofits.org/membership/membership-lists/nonprofit-member-list
    Data: ~2,100 nonprofit members, inline name + URL
    Note: MCN is the largest statewide nonprofit membership association in the US

Australia
    Australian Charities and Not-for-profits Commission (ACNC) open register
    API: https://data.gov.au/data/api/3/action/datastore_search
         resource_id=f6e33999-f56c-4d68-f0ca-c4f75be6b5cd
    Data: ~60,000 registered charities with website URLs
    Licence: Creative Commons Attribution 3.0 Australia

New Zealand
    Charities Services New Zealand public register
    API: https://www.charities.govt.nz/api/charities
    Data: ~28,000 registered charities
    Licence: Creative Commons Attribution 4.0 International

Usage
-----
    pip install requests beautifulsoup4 openpyxl
    python scrape_four_countries.py

    # Scrape only specific countries:
    python scrape_four_countries.py --countries UK USA
    python scrape_four_countries.py --countries AUS NZ

Output files (same directory as this script)
    uk_orgs.csv          - England & Wales charities with websites
    usa_orgs.csv         - Minnesota nonprofits
    aus_orgs.csv         - Australian charities with websites
    nz_orgs.csv          - New Zealand charities with websites
    all_countries.csv    - Combined file with country column

Context
-------
Part of a cross-national web accessibility study examining civil society
organization websites (Ayub & ul Hassan, University of Galway, 2026).
Complements the Ireland dataset (scrape_irl_directory.py).
Contact: muhammadsohaib.ayub@universityofgalway.ie
"""

import argparse
import csv
import io
import os
import re
import sys
import time
import zipfile
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

# ── Shared config ─────────────────────────────────────────────────────────────

HERE = os.path.dirname(os.path.abspath(__file__))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (research accessibility audit; "
        "contact: muhammadsohaib.ayub@universityofgalway.ie)"
    )
}
TIMEOUT = 30


# ── URL helpers ───────────────────────────────────────────────────────────────

def clean_url(raw):
    """Normalise a raw URL string; return empty string if unusable."""
    if not raw:
        return ""
    u = str(raw).strip().rstrip("/ ")
    junk = {"n/a", "na", "none", "www", "-", "tbc", "no.website",
            "http://", "https://", "#", "null", "NULL"}
    if u.lower() in junk:
        return ""
    if u.startswith("//"):
        u = "https:" + u
    if not u.startswith("http"):
        u = "https://" + u
    try:
        parsed = urlparse(u)
        if not parsed.netloc or "." not in parsed.netloc:
            return ""
    except Exception:
        return ""
    return u.lower()


def dedup(records):
    """Deduplicate by domain, keeping first occurrence."""
    seen, out = set(), []
    for r in records:
        domain = urlparse(r["url"]).netloc.lstrip("www.")
        if domain not in seen and r["url"]:
            seen.add(domain)
            out.append(r)
    return out


def save_csv(path, records, country_code):
    """Save records to CSV, returning the count written."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "url", "country", "source"],
                                extrasaction="ignore")
        writer.writeheader()
        for r in records:
            r["country"] = country_code
            writer.writerow(r)
    return len(records)


# ─────────────────────────────────────────────────────────────────────────────
# COUNTRY 1: UK – Charity Commission for England & Wales (CCEW) bulk CSV
# ─────────────────────────────────────────────────────────────────────────────

UK_ZIP_URL = (
    "https://ccewuksprdoneregsadata1.blob.core.windows.net"
    "/data/txt/publicextract.charity.zip"
)
UK_DOWNLOAD_PAGE = (
    "https://register-of-charities.charitycommission.gov.uk"
    "/register/full-register-download"
)


def scrape_uk(sample=None):
    """
    Download CCEW bulk charity data and extract registered charities with websites.
    Returns list of {name, url, source} dicts.

    Parameters
    ----------
    sample : int or None
        If set, return only the first N records (for testing).
    """
    print("\n[UK] Downloading CCEW bulk charity register ...")
    print(f"     Source: {UK_DOWNLOAD_PAGE}")
    print(f"     File  : {UK_ZIP_URL}")
    print("     Size  : ~44 MB  (full England & Wales register)")

    try:
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        r = requests.get(UK_ZIP_URL, headers=HEADERS, timeout=300, stream=True)
        r.raise_for_status()
        downloaded = 0
        for chunk in r.iter_content(65536):
            tmp.write(chunk)
            downloaded += len(chunk)
            if downloaded % 10_000_000 < 65536:
                print(f"     ... {downloaded // 1_000_000} MB")
        tmp.close()
        print(f"     Download complete: {downloaded / 1_000_000:.1f} MB")
    except Exception as e:
        print(f"[UK] ERROR downloading: {e}")
        print("     Manually download from:")
        print(f"     {UK_DOWNLOAD_PAGE}")
        return []

    records = []
    z = None
    try:
        z = zipfile.ZipFile(tmp.name)
        with z.open(z.namelist()[0]) as f:
            reader = csv.DictReader(
                io.TextIOWrapper(f, encoding="utf-8", errors="replace"),
                delimiter="\t"
            )
            for row in reader:
                if row.get("charity_registration_status", "") != "Registered":
                    continue
                web = clean_url(row.get("charity_contact_web", ""))
                if not web:
                    continue
                name = row.get("charity_name", "").strip()
                if not name:
                    continue
                records.append({
                    "name": name,
                    "url": web,
                    "source": "CCEW England & Wales open register"
                })
                if sample and len(records) >= sample:
                    break
    except Exception as e:
        print(f"[UK] ERROR parsing ZIP: {e}")
    finally:
        if z is not None:
            try: z.close()
            except Exception: pass
        try: os.unlink(tmp.name)
        except Exception: pass   # Windows may briefly hold the file

    records = dedup(records)
    print(f"[UK] {len(records):,} registered charities with unique website URLs")
    return records


# ─────────────────────────────────────────────────────────────────────────────
# COUNTRY 2: USA – Minnesota Council of Nonprofits (MCN) member list
# ─────────────────────────────────────────────────────────────────────────────

MCN_URL = (
    "https://minnesotanonprofits.org/membership/membership-lists/nonprofit-member-list"
)


def scrape_usa():
    """
    Scrape the MCN public member list.
    Returns list of {name, url, source} dicts.

    The page format is:
        Organization Name – City http://www.url.org
        Organization Name – City https://www.url.org
        Organization Name – City www.url.org    (no scheme)
    """
    print(f"\n[USA] Scraping Minnesota Council of Nonprofits member list ...")
    print(f"      Source: {MCN_URL}")
    print(f"      Note: MCN is the largest statewide nonprofit membership "
          f"association in the US (~2,100 members)")

    try:
        r = requests.get(MCN_URL, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
    except Exception as e:
        print(f"[USA] ERROR: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    content = (soup.find("div", class_="entry-content")
               or soup.find("main")
               or soup.body)

    records = []
    if content:
        text = content.get_text(separator="\n")
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            # Match: "Name – City http://url" or "Name – City www.url.org"
            m = re.search(r"(https?://\S+|www\.\S+)", line)
            if m:
                raw_url = m.group(1).rstrip(".,;)(")
                url = clean_url(raw_url)
                if not url:
                    continue
                # Extract name (before the URL, strip city suffix after –)
                prefix = line[: m.start()].strip().rstrip(" –-").strip()
                name_parts = re.split(r"\s[–\-]\s", prefix)
                name = name_parts[0].strip() if name_parts else prefix
                if name and len(name) > 2:
                    records.append({
                        "name": name,
                        "url": url,
                        "source": "Minnesota Council of Nonprofits member list"
                    })

    records = dedup(records)
    print(f"[USA] {len(records):,} nonprofit members with website URLs")
    return records


# ─────────────────────────────────────────────────────────────────────────────
# COUNTRY 3: Australia – ACNC charity register via data.gov.au API
# ─────────────────────────────────────────────────────────────────────────────

ACNC_API_BASE  = "https://data.gov.au/data/api/3/action/datastore_search"
ACNC_RESOURCE  = "f6e33999-f56c-4d68-f0ca-c4f75be6b5cd"
ACNC_PAGE_SIZE = 1000
ACNC_INFO_PAGE = "https://data.gov.au/dataset/ds-dga-b050b242-4487-4306-abf5-07ca073e5594/details"


def scrape_aus(max_records=None):
    """
    Download ACNC charity register via data.gov.au CKAN API.
    Returns list of {name, url, source} dicts.

    Parameters
    ----------
    max_records : int or None
        Cap total records returned. None = all charities with websites.
    """
    print(f"\n[AUS] Fetching ACNC charity register from data.gov.au ...")
    print(f"      Info: {ACNC_INFO_PAGE}")
    print(f"      API : {ACNC_API_BASE}?resource_id={ACNC_RESOURCE}")

    records = []
    offset = 0
    total_api = None

    while True:
        params = {
            "resource_id": ACNC_RESOURCE,
            "limit": ACNC_PAGE_SIZE,
            "offset": offset,
            "fields": "Charity_Legal_Name,Website,Registration_status"
        }
        try:
            r = requests.get(ACNC_API_BASE, params=params,
                             headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"[AUS] ERROR at offset {offset}: {e}")
            print(f"      If this keeps failing, manually download from:")
            print(f"      {ACNC_INFO_PAGE}")
            print(f"      Then use scrape_aus_from_csv('path/to/acnc_data.csv')")
            break

        if not data.get("success"):
            print(f"[AUS] API returned success=false: {data.get('error','?')}")
            break

        result = data.get("result", {})
        if total_api is None:
            total_api = result.get("total", 0)
            print(f"      Total charities in register: {total_api:,}")

        batch = result.get("records", [])
        if not batch:
            break

        for row in batch:
            status = row.get("Registration_status", "").strip()
            if status and status.lower() not in ("registered", ""):
                continue
            web = clean_url(row.get("Website", ""))
            if not web:
                continue
            name = row.get("Charity_Legal_Name", "").strip()
            if name:
                records.append({
                    "name": name,
                    "url": web,
                    "source": "ACNC Australian Charity Register (data.gov.au)"
                })

        offset += len(batch)
        print(f"      Fetched {offset:,} / {total_api:,} | "
              f"with websites so far: {len(records):,}")
        time.sleep(0.3)

        if max_records and len(records) >= max_records:
            records = records[:max_records]
            break
        if offset >= (total_api or 0):
            break

    records = dedup(records)
    print(f"[AUS] {len(records):,} registered charities with unique website URLs")
    return records


def scrape_aus_from_csv(csv_path):
    """
    Fallback: parse ACNC data from a manually downloaded CSV file.
    Download the CSV from: https://data.gov.au/dataset/ds-dga-b050b242-4487-4306-abf5-07ca073e5594/details
    """
    print(f"\n[AUS] Parsing manually downloaded ACNC CSV: {csv_path}")
    records = []
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            status = (row.get("Registration_status") or
                      row.get("registration_status") or "").strip().lower()
            if status and status not in ("registered", ""):
                continue
            name = (row.get("Charity_Legal_Name") or
                    row.get("charity_legal_name") or "").strip()
            web = clean_url(row.get("Website") or row.get("website") or "")
            if name and web:
                records.append({
                    "name": name,
                    "url": web,
                    "source": "ACNC Australian Charity Register (manual CSV)"
                })
    records = dedup(records)
    print(f"[AUS] {len(records):,} records from CSV")
    return records


# ─────────────────────────────────────────────────────────────────────────────
# COUNTRY 4: New Zealand – Charities Services NZ public register
# ─────────────────────────────────────────────────────────────────────────────

NZ_API_BASE  = "https://www.charities.govt.nz/api/charities"
NZ_PAGE_SIZE = 200
NZ_INFO_PAGE = "https://www.charities.govt.nz/charities-search/"


def scrape_nz(max_records=None):
    """
    Fetch NZ Charities Services register via their public API.
    Returns list of {name, url, source} dicts.
    """
    print(f"\n[NZ]  Fetching Charities Services NZ register ...")
    print(f"      Info: {NZ_INFO_PAGE}")
    print(f"      API : {NZ_API_BASE}")

    records = []
    page = 1

    while True:
        params = {"pageSize": NZ_PAGE_SIZE, "pageNumber": page}
        try:
            r = requests.get(NZ_API_BASE, params=params,
                             headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"[NZ]  ERROR at page {page}: {e}")
            print(f"      Manually download the register bulk data from:")
            print(f"      https://www.charities.govt.nz/tools-and-resources/"
                  f"open-data-and-api/")
            print(f"      Then use scrape_nz_from_csv('path/to/nz_charities.csv')")
            break

        # API may return list directly or wrapped in an object
        if isinstance(data, list):
            batch = data
        elif isinstance(data, dict):
            batch = (data.get("charities") or data.get("data") or
                     data.get("results") or data.get("items") or [])
            if not batch and "items" not in data and "data" not in data:
                # Try top-level values that are lists
                for v in data.values():
                    if isinstance(v, list):
                        batch = v
                        break

        if not batch:
            print(f"[NZ]  No more records at page {page}")
            break

        for org in batch:
            status = (org.get("registrationStatus") or
                      org.get("registration_status") or
                      org.get("status") or "").lower()
            if status and "register" not in status:
                continue
            name = (org.get("name") or org.get("charityName") or
                    org.get("legal_name") or "").strip()
            web = clean_url(
                org.get("website") or org.get("websiteAddress") or
                org.get("web_address") or ""
            )
            if name and web:
                records.append({
                    "name": name,
                    "url": web,
                    "source": "Charities Services New Zealand public register"
                })

        print(f"      Page {page}: {len(batch)} records | "
              f"with websites so far: {len(records):,}")
        page += 1
        time.sleep(0.3)

        if len(batch) < NZ_PAGE_SIZE:
            break
        if max_records and len(records) >= max_records:
            records = records[:max_records]
            break

    records = dedup(records)
    print(f"[NZ]  {len(records):,} registered charities with unique website URLs")
    return records


def scrape_nz_from_csv(csv_path):
    """
    Fallback: parse NZ Charities data from a manually downloaded CSV file.
    Download from: https://www.charities.govt.nz/tools-and-resources/open-data-and-api/
    """
    print(f"\n[NZ]  Parsing manually downloaded NZ Charities CSV: {csv_path}")
    records = []
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            status = (row.get("Registration Status") or
                      row.get("registration_status") or "").lower()
            if status and "register" not in status:
                continue
            name = (row.get("Legal Name") or row.get("legal_name") or
                    row.get("Charity Name") or "").strip()
            web = clean_url(
                row.get("Website") or row.get("website") or
                row.get("Web Address") or ""
            )
            if name and web:
                records.append({
                    "name": name,
                    "url": web,
                    "source": "Charities Services NZ (manual CSV)"
                })
    records = dedup(records)
    print(f"[NZ]  {len(records):,} records from CSV")
    return records


# ─────────────────────────────────────────────────────────────────────────────
# Excel output
# ─────────────────────────────────────────────────────────────────────────────

def save_xlsx(path, all_records):
    """Save combined dataset to a formatted Excel workbook."""
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        print("openpyxl not installed – skipping Excel output")
        return

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "All Countries"

    thin    = Side(style="thin", color="CCCCCC")
    bdr     = Border(top=thin, bottom=thin, left=thin, right=thin)
    center  = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left    = Alignment(horizontal="left",   vertical="center", wrap_text=True)
    hdr_f   = Font(name="Arial", bold=True, color="FFFFFF", size=11)
    hdr_bg  = PatternFill("solid", fgColor="1B4F72")
    body_f  = Font(name="Arial", size=10)
    link_f  = Font(name="Arial", size=10, color="1155CC", underline="single")
    alt_bg  = PatternFill("solid", fgColor="EBF5FB")

    # Title
    ws.merge_cells("A1:E1")
    ws["A1"].value = "Civil Society Organization Websites – Cross-National Dataset"
    ws["A1"].font  = Font(name="Arial", bold=True, size=13, color="1B4F72")
    ws["A1"].alignment = center
    ws.row_dimensions[1].height = 28

    # Subtitle
    ws.merge_cells("A2:E2")
    ws["A2"].value = (
        f"Total: {len(all_records):,} organizations across 4 countries  |  "
        f"Data collected: June 2026  |  "
        f"Part of cross-national web accessibility study (University of Galway)"
    )
    ws["A2"].font      = Font(name="Arial", italic=True, size=9, color="555555")
    ws["A2"].alignment = left
    ws.row_dimensions[2].height = 16

    # Headers
    col_config = [
        ("#",              5),
        ("Organization Name", 42),
        ("Website URL",    38),
        ("Country",        12),
        ("WCAG Audit Status", 20),
    ]
    for ci, (header, width) in enumerate(col_config, 1):
        c = ws.cell(row=3, column=ci, value=header)
        c.font = hdr_f; c.fill = hdr_bg
        c.alignment = center; c.border = bdr
        ws.column_dimensions[get_column_letter(ci)].width = width
    ws.row_dimensions[3].height = 20
    ws.freeze_panes = "A4"

    # Country summary sheet
    ws2 = wb.create_sheet("Summary")
    ws2.column_dimensions["A"].width = 35
    ws2.column_dimensions["B"].width = 18

    country_counts = {}
    for rec in all_records:
        country_counts[rec["country"]] = country_counts.get(rec["country"], 0) + 1

    summary = [
        ("CROSS-NATIONAL DATASET SUMMARY", None),
        ("", None),
        ("Country", "Organizations"),
        ("Ireland (national member directory)", "~2,000 (separate file)"),
    ] + [(f"{c}", f"{n:,}") for c, n in sorted(country_counts.items())] + [
        ("", None),
        ("TOTAL (ex. Ireland)", f"{len(all_records):,}"),
    ]

    section_fill = PatternFill("solid", fgColor="D6EAF8")
    section_font = Font(name="Arial", bold=True, size=11, color="1B4F72")
    tbl_hdr_fill = PatternFill("solid", fgColor="1B4F72")
    tbl_hdr_font = Font(name="Arial", bold=True, size=10, color="FFFFFF")

    for ri, (label, val) in enumerate(summary, 1):
        lc = ws2.cell(row=ri, column=1, value=label)
        vc = ws2.cell(row=ri, column=2, value=val)
        ws2.row_dimensions[ri].height = 18
        if label == "CROSS-NATIONAL DATASET SUMMARY":
            lc.font = section_font; lc.fill = section_fill
            ws2.merge_cells(f"A{ri}:B{ri}")
        elif label == "Country":
            lc.font = tbl_hdr_font; lc.fill = tbl_hdr_fill
            lc.alignment = Alignment(horizontal="center")
            vc.font = tbl_hdr_font; vc.fill = tbl_hdr_fill
            vc.alignment = Alignment(horizontal="center")
        elif label:
            lc.font = Font(name="Arial", size=10)
            vc.font = Font(name="Arial", bold=True, size=10)

    # Data rows
    for i, rec in enumerate(all_records, 1):
        row_idx = i + 3
        row_data = [
            (1, i,           center, body_f),
            (2, rec["name"], left,   body_f),
            (3, rec["url"],  left,   link_f),
            (4, rec["country"], center, body_f),
            (5, "Pending",   center, body_f),
        ]
        for ci, val, aln, fnt in row_data:
            c = ws.cell(row=row_idx, column=ci, value=val)
            c.font = fnt; c.alignment = aln; c.border = bdr
            if i % 2 == 0:
                c.fill = alt_bg
        ws.row_dimensions[row_idx].height = 14

    ws.auto_filter.ref = f"A3:E{len(all_records) + 3}"
    wb.save(path)
    print(f"\nExcel saved: {path}  ({len(all_records):,} rows, 2 sheets)")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scrape civil society org websites from UK, USA, AUS, NZ"
    )
    parser.add_argument(
        "--countries",
        nargs="+",
        choices=["UK", "USA", "AUS", "NZ"],
        default=["UK", "USA", "AUS", "NZ"],
        help="Which countries to scrape (default: all four)"
    )
    parser.add_argument(
        "--aus-csv",
        default=None,
        metavar="PATH",
        help="Path to manually downloaded ACNC CSV (fallback for AUS)"
    )
    parser.add_argument(
        "--nz-csv",
        default=None,
        metavar="PATH",
        help="Path to manually downloaded NZ Charities CSV (fallback for NZ)"
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        metavar="N",
        help="Limit each country to first N records (for quick testing)"
    )
    args = parser.parse_args()

    print("=" * 65)
    print("Cross-National Civil Society Website Scraper")
    print("=" * 65)
    print(f"Countries : {', '.join(args.countries)}")
    if args.sample:
        print(f"Sample    : first {args.sample} per country (test mode)")

    all_records = []
    country_files = []

    if "UK" in args.countries:
        recs = scrape_uk(sample=args.sample)
        for r in recs:
            r["country"] = "UK"
        path = os.path.join(HERE, "uk_orgs.csv")
        save_csv(path, recs, "UK")
        print(f"  -> {path}")
        country_files.append(path)
        all_records.extend(recs)

    if "USA" in args.countries:
        recs = scrape_usa()
        if args.sample:
            recs = recs[:args.sample]
        for r in recs:
            r["country"] = "USA"
        path = os.path.join(HERE, "usa_orgs.csv")
        save_csv(path, recs, "USA")
        print(f"  -> {path}")
        country_files.append(path)
        all_records.extend(recs)

    if "AUS" in args.countries:
        if args.aus_csv:
            recs = scrape_aus_from_csv(args.aus_csv)
        else:
            recs = scrape_aus(max_records=args.sample)
        for r in recs:
            r["country"] = "AUS"
        path = os.path.join(HERE, "aus_orgs.csv")
        save_csv(path, recs, "AUS")
        print(f"  -> {path}")
        country_files.append(path)
        all_records.extend(recs)

    if "NZ" in args.countries:
        if args.nz_csv:
            recs = scrape_nz_from_csv(args.nz_csv)
        else:
            recs = scrape_nz(max_records=args.sample)
        for r in recs:
            r["country"] = "NZ"
        path = os.path.join(HERE, "nz_orgs.csv")
        save_csv(path, recs, "NZ")
        print(f"  -> {path}")
        country_files.append(path)
        all_records.extend(recs)

    if all_records:
        # Combined CSV
        combined_path = os.path.join(HERE, "all_countries.csv")
        with open(combined_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["name", "url", "country", "source"],
                               extrasaction="ignore")
            w.writeheader()
            w.writerows(all_records)
        print(f"\nCombined CSV: {combined_path}  ({len(all_records):,} rows)")

        # Excel workbook
        xlsx_path = os.path.join(HERE, "Civil_Society_Websites_All_Countries.xlsx")
        save_xlsx(xlsx_path, all_records)

    print("\n" + "=" * 65)
    print(f"Done.  {len(all_records):,} organizations across {len(args.countries)} countries.")
    print("=" * 65)

    if not any(c in args.countries for c in ["AUS", "NZ"]) or not all_records:
        print("\nNOTE for AUS / NZ fallback:")
        print("  If the ACNC or NZ APIs are unreachable, download the data")
        print("  manually and re-run with:")
        print("    python scrape_four_countries.py --countries AUS --aus-csv path/to/acnc.csv")
        print("    python scrape_four_countries.py --countries NZ  --nz-csv  path/to/nz.csv")
        print()
        print("  AUS manual download:")
        print(f"    {ACNC_INFO_PAGE}")
        print("  NZ  manual download:")
        print("    https://www.charities.govt.nz/tools-and-resources/open-data-and-api/")


if __name__ == "__main__":
    main()
