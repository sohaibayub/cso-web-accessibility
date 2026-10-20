"""
scrape_wheel_members.py
=======================
Scrapes the full member directory of The Wheel (wheel.ie), the national
umbrella body for Ireland's community and voluntary sector, and produces:

  1. wheel_members_all.csv       - every entry found (with or without URL)
  2. wheel_members_with_url.csv  - entries that have a usable website URL
  3. Wheel_Member_Websites.xlsx  - cleaned, deduplicated Excel workbook with
                                   a WCAG Audit Status column ready for
                                   pre/post accessibility audit tracking

Usage
-----
    pip install requests beautifulsoup4 openpyxl
    python scrape_wheel_members.py

The script respects the site with a polite crawl delay (DELAY seconds between
requests). Total runtime is roughly 90 seconds for all 57 pages.

Context
-------
Written to support a research project on web accessibility in Irish civil
society organizations (Ayub & ul Hassan, University of Galway, Insight
Research Ireland Centre for Data Analytics).

Source URL : https://www.wheel.ie/membership/member-directory
Collected  : June 2026
Contact    : muhammadsohaib.ayub@universityofgalway.ie
"""

import csv
import sys
import time
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

try:
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    XLSX = True
except ImportError:
    print("openpyxl not found - CSV outputs will still be produced.")
    XLSX = False


# ── Configuration ─────────────────────────────────────────────────────────────

BASE_URL  = "https://www.wheel.ie/membership/member-directory"
LAST_PAGE = 56      # pages 0-56  (2,735 members at 48 per page = 57 pages)
DELAY     = 1.2     # seconds between requests - polite crawl rate
HEADERS   = {
    "User-Agent": (
        "Mozilla/5.0 (research accessibility audit; "
        "contact: muhammadsohaib.ayub@universityofgalway.ie)"
    )
}

# h2 text values that belong to site navigation, not member org names
NAV_HEADINGS = {
    "header navigation", "mobile header navigation", "our other websites",
    "social links", "siblings navigation", "breadcrumb", "main navigation",
    "join us", "quick links", "contact the wheel", "newsletters",
    "privacy & notices", "pagination",
}

OUT_ALL      = "wheel_members_all.csv"
OUT_WITH_URL = "wheel_members_with_url.csv"
OUT_XLSX     = "Wheel_Member_Websites.xlsx"


# ── Scraping ──────────────────────────────────────────────────────────────────

def fetch_page(page_num):
    """Fetch one directory page; return list of {name, url, page} dicts."""
    url = BASE_URL if page_num == 0 else f"{BASE_URL}?page={page_num}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except requests.RequestException as exc:
        print(f"  page {page_num}: FAILED - {exc}", file=sys.stderr)
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    orgs = []

    for h2 in soup.find_all("h2"):
        name = h2.get_text(strip=True)
        if not name or name.lower() in NAV_HEADINGS:
            continue

        # The next sibling element may contain the URL as a hyperlink or plain text
        nxt = h2.find_next_sibling()
        website = ""
        if nxt:
            anchor = nxt.find("a")
            if anchor and anchor.get("href"):
                href = anchor["href"].strip()
                if href.startswith("http") or ("." in href and not href.startswith("#")):
                    website = href
            else:
                # Some members list their URL as plain text with no anchor tag
                raw = nxt.get_text(strip=True)
                if (
                    raw
                    and "." in raw
                    and "@" not in raw          # exclude email addresses
                    and len(raw) < 120
                    and raw.lower() not in ("n/a", "na", "tbc", "-")
                ):
                    website = raw

        orgs.append({"name": name, "url": website, "page": page_num})

    return orgs


def scrape_all():
    """Scrape all pages and return every member record."""
    all_records = []
    for page in range(0, LAST_PAGE + 1):
        records = fetch_page(page)
        all_records.extend(records)
        print(f"  page {page:>2}: {len(records):>2} entries  "
              f"(running total {len(all_records):,})")
        time.sleep(DELAY)
    return all_records


# ── URL Cleaning ──────────────────────────────────────────────────────────────

def clean_url(raw):
    """Normalise a raw URL string; return empty string if unusable."""
    u = raw.strip().rstrip("/")
    if not u:
        return ""
    junk = {"n/a", "na", "none", "www", "-", "tbc", "http://", "https://", "#"}
    if u.lower() in junk:
        return ""
    if not u.startswith("http"):
        u = "https://" + u
    parsed = urlparse(u)
    if not parsed.netloc or "." not in parsed.netloc:
        return ""
    if "wheel.ie" in parsed.netloc:   # drop self-referential links
        return ""
    return u.lower()


def deduplicate(records):
    """Keep records with usable URLs, deduplicated by domain and org name."""
    seen_domains = set()
    seen_names   = set()
    out = []
    for rec in records:
        url  = clean_url(rec["url"])
        name = rec["name"].strip()
        if not url:
            continue
        domain = urlparse(url).netloc.lstrip("www.")
        if domain in seen_domains or name.lower() in seen_names:
            continue
        seen_domains.add(domain)
        seen_names.add(name.lower())
        out.append({"name": name, "url": url, "page": rec["page"]})
    return out


# ── CSV Output ────────────────────────────────────────────────────────────────

def save_csv(path, records, fields):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    print(f"  Saved: {path}  ({len(records):,} rows)")


# ── Excel Output ──────────────────────────────────────────────────────────────

def save_xlsx(path, orgs, total_scraped):
    """Write a formatted Excel workbook: directory sheet + summary sheet."""
    wb = openpyxl.Workbook()

    # shared style objects
    thin      = Side(style="thin", color="CCCCCC")
    bdr       = Border(top=thin, bottom=thin, left=thin, right=thin)
    center    = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left      = Alignment(horizontal="left",   vertical="center", wrap_text=True)
    hdr_fill  = PatternFill("solid", fgColor="1B4F72")
    alt_fill  = PatternFill("solid", fgColor="EBF5FB")
    hdr_font  = Font(name="Arial", bold=True, color="FFFFFF", size=11)
    body_font = Font(name="Arial", size=10)
    link_font = Font(name="Arial", size=10, color="1155CC", underline="single")

    # ── Sheet 1: Member Directory ─────────────────────────────────────────────
    ws = wb.active
    ws.title = "Member Directory"

    # title row
    ws.merge_cells("A1:E1")
    ws["A1"].value     = "Wheel.ie Member Organizations - Website Directory"
    ws["A1"].font      = Font(name="Arial", bold=True, size=13, color="1B4F72")
    ws["A1"].alignment = center
    ws.row_dimensions[1].height = 28

    # subtitle row
    ws.merge_cells("A2:E2")
    ws["A2"].value = (
        f"Source: wheel.ie/membership/member-directory  |  "
        f"Unique organizations with website: {len(orgs):,}  |  "
        f"Data collected: June 2026"
    )
    ws["A2"].font      = Font(name="Arial", italic=True, size=9, color="555555")
    ws["A2"].alignment = left
    ws.row_dimensions[2].height = 16

    # column headers (row 3)
    col_config = [
        ("#",                    5),
        ("Organization Name",   42),
        ("Website URL",         38),
        ("WCAG Audit Status",   20),
        ("Notes",               28),
    ]
    for ci, (header, width) in enumerate(col_config, 1):
        c = ws.cell(row=3, column=ci, value=header)
        c.font      = hdr_font
        c.fill      = hdr_fill
        c.alignment = center
        c.border    = bdr
        ws.column_dimensions[get_column_letter(ci)].width = width
    ws.row_dimensions[3].height = 20
    ws.freeze_panes = "A4"

    # data rows
    for i, org in enumerate(orgs, 1):
        row_idx = i + 3
        use_alt = (i % 2 == 0)
        row_data = [
            (1, i,           center, body_font),
            (2, org["name"], left,   body_font),
            (3, org["url"],  left,   link_font),
            (4, "Pending",   center, body_font),
            (5, "",          left,   body_font),
        ]
        for ci, val, aln, fnt in row_data:
            c = ws.cell(row=row_idx, column=ci, value=val)
            c.font      = fnt
            c.alignment = aln
            c.border    = bdr
            if use_alt:
                c.fill = alt_fill
        ws.row_dimensions[row_idx].height = 15

    ws.auto_filter.ref = f"A3:E{len(orgs) + 3}"

    # ── Sheet 2: Summary ──────────────────────────────────────────────────────
    ws2 = wb.create_sheet("Summary")
    ws2.column_dimensions["A"].width = 40
    ws2.column_dimensions["B"].width = 22

    section_font  = Font(name="Arial", bold=True, size=11, color="1B4F72")
    section_fill  = PatternFill("solid", fgColor="D6EAF8")
    tbl_hdr_font  = Font(name="Arial", bold=True, size=10, color="FFFFFF")
    tbl_hdr_fill  = PatternFill("solid", fgColor="1B4F72")
    step_val_font = Font(name="Arial", size=10, italic=True, color="117A65")

    summary = [
        ("WHEEL.IE MEMBER DIRECTORY SUMMARY",        None),
        ("",                                          None),
        ("Statistic",                                 "Value"),
        ("Total member entries scraped",              total_scraped),
        ("Unique organizations with website",         len(orgs)),
        ("Entries without usable URL",                total_scraped - len(orgs)),
        ("Data source",          "wheel.ie/membership/member-directory"),
        ("Date collected",       "June 2026"),
        ("Crawl delay (seconds)", DELAY),
        ("Pages scraped",         LAST_PAGE + 1),
        ("",                                          None),
        ("WCAG AUDIT WORKFLOW",                       None),
        ("Step 1 - Use this list as input",           f"{len(orgs):,} URLs available"),
        ("Step 2 - Reachability pre-filter",          "requests.head() pass"),
        ("Step 3 - Run automated axe-core audit",     "Selenium crawler (50 pages/site)"),
        ("Step 4 - Generate task records",            "Technical + Non-technical"),
        ("Step 5 - Crowdsource remediation",          "Volunteer contributors"),
        ("Step 6 - Verify outputs",                   "Auto + human review"),
        ("Step 7 - Measure improvement",              "Pre/post accessibility score"),
    ]

    for ri, (label, val) in enumerate(summary, 1):
        lc = ws2.cell(row=ri, column=1, value=label)
        vc = ws2.cell(row=ri, column=2, value=val)
        ws2.row_dimensions[ri].height = 18

        if label in ("WHEEL.IE MEMBER DIRECTORY SUMMARY", "WCAG AUDIT WORKFLOW"):
            lc.font = section_font
            lc.fill = section_fill
            ws2.merge_cells(f"A{ri}:B{ri}")
        elif label == "Statistic":
            for c in (lc, vc):
                c.font      = tbl_hdr_font
                c.fill      = tbl_hdr_fill
                c.alignment = Alignment(horizontal="center")
        elif label.startswith("Step"):
            lc.font = Font(name="Arial", size=10)
            vc.font = step_val_font
        elif label:
            lc.font = Font(name="Arial", size=10)
            vc.font = Font(name="Arial", bold=True, size=10)

    wb.save(path)
    print(f"  Saved: {path}  ({len(orgs):,} organizations, 2 sheets)")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Wheel.ie Member Directory Scraper")
    print("=" * 60)

    print(f"\nStep 1 - Scraping {LAST_PAGE + 1} pages from wheel.ie ...")
    all_records = scrape_all()

    print(f"\nStep 2 - Saving raw list to CSV ...")
    save_csv(OUT_ALL, all_records, ["name", "url", "page"])

    print(f"\nStep 3 - Cleaning and deduplicating ...")
    cleaned = deduplicate(all_records)
    print(f"  Raw entries          : {len(all_records):,}")
    print(f"  After clean + dedup  : {len(cleaned):,}")

    print(f"\nStep 4 - Saving filtered CSV ...")
    save_csv(OUT_WITH_URL, cleaned, ["name", "url", "page"])

    if XLSX:
        print(f"\nStep 5 - Building Excel workbook ...")
        save_xlsx(OUT_XLSX, cleaned, len(all_records))
    else:
        print("\nSkipping Excel output (openpyxl not installed).")

    print("\n" + "=" * 60)
    print(f"Done.  {len(cleaned):,} unique organizations with websites.")
    print("=" * 60)


if __name__ == "__main__":
    main()
