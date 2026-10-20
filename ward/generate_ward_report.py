#!/usr/bin/env python3
"""
generate_ward_report.py
=======================
Generates a formatted Excel accessibility audit report from a WARD v2
JSON results file. Works for any country dataset produced by ward_civil.py.

Usage
-----
    python generate_ward_report.py results_usa_orgs.json
    python generate_ward_report.py ward_civil_results.json
    python generate_ward_report.py results_uk_orgs.json

The output Excel file is saved in the same folder as the input JSON,
named:  WARD_Report_<stem>.xlsx

Requirements
------------
    pip install openpyxl

Context
-------
Part of a cross-national web accessibility study (Ayub & ul Hassan,
University of Galway, Insight Research Ireland Centre for Data Analytics).
Contact: muhammadsohaib.ayub@universityofgalway.ie
"""

import json
import os
import sys
from collections import Counter, defaultdict

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    print("ERROR: openpyxl is required.  Run:  pip install openpyxl")
    sys.exit(1)


# ── Constants ─────────────────────────────────────────────────────────────────

PRINCIPLES = {
    'Perceivable':    {'1.1.1','1.3.1','1.3.4','1.3.5','1.4.1','1.4.4',
                       '1.4.10','1.4.12','1.4.13'},
    'Operable':       {'2.1.1','2.4.1','2.4.2','2.4.4','2.4.6'},
    'Understandable': {'3.1.1'},
    'Robust':         {'4.1.1','4.1.2'},
}
LEVEL_A = {'1.1.1','1.3.1','1.4.1','2.1.1','2.4.1','2.4.2','2.4.4',
           '3.1.1','4.1.1','4.1.2'}
CRIT_NAMES = {
    '1.1.1': 'Non-text Content (alt text)',
    '1.3.1': 'Info & Relationships (form labels)',
    '1.3.4': 'Orientation',
    '1.3.5': 'Input Purpose (autocomplete)',
    '1.4.1': 'Use of Color',
    '1.4.4': 'Resize Text (fixed px fonts)',
    '1.4.10':'Reflow',
    '1.4.12':'Text Spacing',
    '1.4.13':'Content on Hover/Focus',
    '2.1.1': 'Keyboard Accessible',
    '2.4.1': 'Bypass Blocks (skip nav)',
    '2.4.2': 'Page Titled',
    '2.4.4': 'Link Purpose',
    '2.4.6': 'Headings & Labels',
    '3.1.1': 'Language of Page',
    '4.1.1': 'Parsing (duplicate IDs)',
    '4.1.2': 'Name, Role, Value (ARIA)',
}

# Colour palette
NAVY  = "1B4F72"; TEAL  = "0E6655"; RED   = "C0392B"
GREEN = "117A65"; AMBER = "F39C12"; DGREY = "5D6D7E"
WHITE = "FFFFFF"


# ── Style helpers ─────────────────────────────────────────────────────────────

def bdr(c="CCCCCC"):
    s = Side(style="thin", color=c)
    return Border(top=s, bottom=s, left=s, right=s)

def fill(h):
    return PatternFill("solid", fgColor=h)

def ctr(wrap=False):
    return Alignment(horizontal="center", vertical="center", wrap_text=wrap)

def lft(wrap=True):
    return Alignment(horizontal="left", vertical="center", wrap_text=wrap)

def hrow(ws, row, cols, bg=NAVY, fg=WHITE, sz=11):
    for ci, v in enumerate(cols, 1):
        c = ws.cell(row=row, column=ci, value=v)
        c.font      = Font(name="Arial", bold=True, color=fg, size=sz)
        c.fill      = fill(bg)
        c.alignment = ctr(True)
        c.border    = bdr()
    ws.row_dimensions[row].height = 20

def sec(ws, row, val, span, bg=NAVY):
    ws.merge_cells(start_row=row, start_column=1,
                   end_row=row, end_column=span)
    c = ws.cell(row=row, column=1, value=val)
    c.font      = Font(name="Arial", bold=True, color=WHITE, size=12)
    c.fill      = fill(bg)
    c.alignment = ctr()
    ws.row_dimensions[row].height = 22

def score_bg(s):
    if s is None:  return "F2F3F4"
    if s >= 90:    return "D5F5E3"
    if s >= 80:    return "EAF4FB"
    if s >= 70:    return "FEF9E7"
    if s >= 60:    return "FDEBD0"
    return "FADBD8"

def score_color(s):
    if s is None or s < 60: return RED
    if s < 80:              return AMBER
    return GREEN


# ── Data helpers ──────────────────────────────────────────────────────────────

def avg(lst):
    lst = [x for x in lst if x is not None]
    return round(sum(lst) / len(lst), 1) if lst else 0

def med(lst):
    lst = sorted(x for x in lst if x is not None)
    return lst[len(lst) // 2] if lst else 0

def safe_get(r, key, default=0):
    v = r.get(key)
    return v if v is not None else default


# ── Detect country / source label from data ───────────────────────────────────

def detect_label(data, stem):
    """Return a (country_label, source_label) tuple for report headers."""
    sample = next((r for r in data if r.get('country')), None)
    country = (sample or {}).get('country', '').strip()

    label_map = {
        'Ireland': ('Ireland',  'national member directory of community and voluntary organizations'),
        'UK':      ('UK',       'Charity Commission for England & Wales (CCEW) open register'),
        'USA':     ('USA',      'Minnesota Council of Nonprofits (MCN) member list'),
        'AUS':     ('Australia','Australian Charities & Not-for-profits Commission (ACNC)'),
        'NZ':      ('New Zealand','Charities Services New Zealand public register'),
    }
    if country in label_map:
        return label_map[country]

    # Fallback: infer from filename
    sl = stem.lower()
    if 'ireland' in sl or 'wheel' in sl: return label_map['Ireland']
    if 'uk' in sl or 'ccew' in sl:       return label_map['UK']
    if 'usa' in sl or 'mcn' in sl:       return label_map['USA']
    if 'aus' in sl or 'acnc' in sl:      return label_map['AUS']
    if 'nz' in sl or 'nzchar' in sl:     return label_map['NZ']
    return (stem, stem)


# ══════════════════════════════════════════════════════════════════════════════
# Main report builder
# ══════════════════════════════════════════════════════════════════════════════

def build_report(json_path, out_path):

    # ── Load ─────────────────────────────────────────────────────────────────
    print(f"Loading: {json_path}")
    with open(json_path, encoding='utf-8') as f:
        data = json.load(f)

    tested  = [r for r in data if r['status'] == 'tested']
    errors  = [r for r in data if r['status'] != 'tested']
    scored  = [r for r in tested if r.get('accessibility_score') is not None]
    N       = len(tested)

    if N == 0:
        print("ERROR: no tested records found in JSON.")
        return

    stem          = os.path.splitext(os.path.basename(json_path))[0]
    country, src  = detect_label(data, stem)

    scores   = [r['accessibility_score'] for r in scored]
    issues21 = [safe_get(r, 'count_2_1') for r in tested]
    issues22 = [safe_get(r, 'count_2_2') for r in tested]
    sevs     = [r['severity_score'] for r in tested if r.get('severity_score') is not None]
    comp     = [r['compliance_pct']  for r in tested if r.get('compliance_pct')  is not None]

    # Aggregate violation stats
    crit_count = Counter()
    crit_sites = defaultdict(set)
    pcounts    = defaultdict(int)
    lcounts    = defaultdict(int)

    for idx, r in enumerate(tested):
        for issue in r.get('issues_2_1', []):
            c = issue['criterion']
            crit_count[c] += 1
            crit_sites[c].add(idx)
            lcounts[issue['level']] += 1
            for p, cs in PRINCIPLES.items():
                if c in cs:
                    pcounts[p] += 1
                    break

    total_v    = sum(crit_count.values())
    zero_sites = [r for r in tested if safe_get(r, 'count_2_1') == 0]
    extra22    = sum(issues22) - sum(issues21)

    print(f"  Country  : {country}")
    print(f"  Tested   : {N:,}   Errors: {len(errors):,}")
    print(f"  Mean score: {avg(scores)}   Mean issues: {avg(issues21)}")
    print(f"  Total violations: {total_v:,}")

    wb = openpyxl.Workbook()

    # ══════════════════════════════════════════════════════════════════════════
    # SHEET 1 – Executive Summary
    # ══════════════════════════════════════════════════════════════════════════
    ws1 = wb.active
    ws1.title = "Executive Summary"
    ws1.sheet_view.showGridLines = False

    ws1.merge_cells("A1:H1")
    ws1["A1"].value = (f"WARD v2  ·  Web Accessibility Audit  ·  "
                       f"{country} Civil Society Websites")
    ws1["A1"].font  = Font(name="Arial", bold=True, size=14, color=WHITE)
    ws1["A1"].fill  = fill(NAVY)
    ws1["A1"].alignment = ctr()
    ws1.row_dimensions[1].height = 32

    ws1.merge_cells("A2:H2")
    ws1["A2"].value = (f"Source: {src}  ·  {len(data):,} organisations  ·  "
                       f"Tested: {N:,}  ·  WCAG 2.0 / 2.1 / 2.2 AA  ·  June 2026")
    ws1["A2"].font      = Font(name="Arial", italic=True, size=10, color=DGREY)
    ws1["A2"].alignment = ctr()
    ws1.row_dimensions[2].height = 16
    ws1.row_dimensions[3].height = 8

    # Key metrics
    sec(ws1, 4, "KEY METRICS", 8)
    hrow(ws1, 5,
         ["Sites Tested","Unreachable","Total Violations","Avg Issues/Site",
          "Mean Score","Median Score","Mean Compliance %","Full Compliance"],
         bg="2E4057")
    mv = [f"{N:,}", f"{len(errors):,}", f"{total_v:,}", f"{avg(issues21)}",
          f"{avg(scores)} / 100", f"{med(scores)} / 100",
          f"{avg(comp)}%",
          f"{len(zero_sites)} ({len(zero_sites)/N*100:.1f}%)"]
    for ci, v in enumerate(mv, 1):
        c = ws1.cell(row=6, column=ci, value=v)
        c.font      = Font(name="Arial", bold=True, size=12, color=NAVY)
        c.alignment = ctr()
        c.border    = bdr()
        c.fill      = fill("EBF5FB")
    ws1.row_dimensions[6].height = 26
    ws1.row_dimensions[7].height = 8

    # Issue distribution
    sec(ws1, 8, "ISSUE DISTRIBUTION (WCAG 2.1)", 8, bg=TEAL)
    hrow(ws1, 9, ["Range","Classification","Sites","% of Tested","Cumulative %"],
         bg=TEAL)
    dist_def = [("0","Perfect",0,0), ("1–4","Excellent",1,4),
                ("5–9","Good",5,9),  ("10–19","Fair",10,19),
                ("20–49","Poor",20,49), ("50+","Critical",50,9999)]
    cls_bg = {"Perfect":"D5F5E3","Excellent":"D5F5E3","Good":"EAF4FB",
              "Fair":"FEF9E7","Poor":"FDEBD0","Critical":"FADBD8"}
    cumul = 0
    for di, (rng, cls, lo, hi) in enumerate(dist_def):
        cnt = sum(1 for r in tested if lo <= safe_get(r,'count_2_1') <= hi)
        pct = cnt / N * 100; cumul += pct; row = 10 + di
        for ci, v in enumerate([rng, cls, cnt, round(pct,1), round(cumul,1)], 1):
            c = ws1.cell(row=row, column=ci, value=v)
            c.fill = fill(cls_bg[cls]); c.border = bdr(); c.alignment = ctr()
            c.font = Font(name="Arial", bold=(cls in ("Perfect","Critical")), size=10)
            if ci in (4, 5): c.number_format = '0.0"%"'
    ws1.row_dimensions[16].height = 8

    # WCAG principle breakdown
    sec(ws1, 17, "VIOLATIONS BY WCAG PRINCIPLE", 8, bg="4A235A")
    hrow(ws1, 18, ["Principle","Violations","% of Total","Description"], bg="4A235A")
    pcol  = {"Perceivable":"D2B4DE","Operable":"AED6F1",
             "Understandable":"A9DFBF","Robust":"F9E79F"}
    pdesc = {"Perceivable":"Information must be presentable to users",
             "Operable":"Interface components must be operable",
             "Understandable":"Information and UI must be understandable",
             "Robust":"Content must be interpreted by assistive tech"}
    for pi, p in enumerate(["Perceivable","Operable","Understandable","Robust"]):
        cnt = pcounts[p]; row = 19 + pi
        for ci, v in enumerate([p, cnt, round(cnt/total_v*100,1) if total_v else 0,
                                 pdesc[p]], 1):
            c = ws1.cell(row=row, column=ci, value=v)
            c.fill = fill(pcol[p]); c.border = bdr()
            c.alignment = ctr() if ci in (2, 3) else lft()
            c.font = Font(name="Arial", bold=(ci==1), size=10)
            if ci == 3: c.number_format = '0.0"%"'
    ws1.row_dimensions[23].height = 8

    # Conformance level
    sec(ws1, 24, "CONFORMANCE LEVEL BREAKDOWN", 8, bg=TEAL)
    hrow(ws1, 25, ["Level","Violations","% of Total","Description"], bg=TEAL)
    for li, (lv, desc) in enumerate([
            ("A (Minimum)", "Fundamental — cannot use site without addressing these"),
            ("AA (Standard)","Required by ADA, Section 508, EN 301 549, DDA, AODA")]):
        cnt = lcounts["A"] if li == 0 else lcounts["AA"]
        row = 26 + li
        bg  = "FADBD8" if li == 0 else "FDEBD0"
        for ci, v in enumerate([lv, cnt,
                                 round(cnt/total_v*100,1) if total_v else 0,
                                 desc], 1):
            c = ws1.cell(row=row, column=ci, value=v)
            c.fill = fill(bg); c.border = bdr()
            c.alignment = ctr() if ci in (2, 3) else lft()
            c.font = Font(name="Arial", bold=(ci==1), size=10)
            if ci == 3: c.number_format = '0.0"%"'
    ws1.row_dimensions[28].height = 8

    # WCAG 2.1 vs 2.2
    sec(ws1, 29, "WCAG 2.1 vs WCAG 2.2 COMPARISON", 8, bg="1A5276")
    hrow(ws1, 30,
         ["Standard","Total Violations","Mean/Site","Full Compliance","Sites Affected"],
         bg="1A5276")
    for ri, (std, tot, mn, full, aff) in enumerate([
            ("WCAG 2.1 AA",
             f"{sum(issues21):,}", f"{avg(issues21)}",
             f"{len(zero_sites)} ({len(zero_sites)/N*100:.1f}%)",
             f"{sum(1 for r in tested if safe_get(r,'count_2_1')>0):,}"),
            ("WCAG 2.2 AA (+7 criteria)",
             f"{sum(issues22):,}", f"{avg(issues22)}",
             f"{sum(1 for r in tested if safe_get(r,'count_2_2')==0)} "
             f"({sum(1 for r in tested if safe_get(r,'count_2_2')==0)/N*100:.1f}%)",
             f"{sum(1 for r in tested if safe_get(r,'count_2_2')>0):,}"),
            ("Additional (2.2 over 2.1)",
             f"+{extra22:,}",
             f"+{round(extra22/N,1)}",
             "—",
             f"{sum(1 for a,b in zip(issues22,issues21) if a>b):,}"),
    ], 1):
        row = 30 + ri
        bg  = "EAF4FB" if ri % 2 == 0 else "FFFFFF"
        for ci, v in enumerate([std, tot, mn, full, aff], 1):
            c = ws1.cell(row=row, column=ci, value=v)
            c.fill = fill(bg); c.alignment = ctr(); c.border = bdr()
            c.font = Font(name="Arial", bold=(ci==1 or ri==3), size=10)

    for col, w in zip("ABCDEFGH", [28,18,18,16,14,14,14,32]):
        ws1.column_dimensions[col].width = w

    # ══════════════════════════════════════════════════════════════════════════
    # SHEET 2 – Top Violations
    # ══════════════════════════════════════════════════════════════════════════
    ws2 = wb.create_sheet("Top Violations")
    ws2.sheet_view.showGridLines = False
    ws2.merge_cells("A1:H1")
    ws2["A1"].value = (f"Top Accessibility Violations — "
                       f"{country} Civil Society Websites")
    ws2["A1"].font  = Font(name="Arial", bold=True, size=13, color=WHITE)
    ws2["A1"].fill  = fill(NAVY)
    ws2["A1"].alignment = ctr()
    ws2.row_dimensions[1].height = 26
    ws2.row_dimensions[2].height = 8

    hrow(ws2, 3,
         ["Rank","Criterion","Level","Description","Total Violations",
          "Sites Affected","% Sites","Principle"],
         bg=TEAL)
    for ri, (crit, cnt) in enumerate(crit_count.most_common(17), 1):
        row  = 3 + ri
        sn   = len(crit_sites[crit])
        level = "A" if crit in LEVEL_A else "AA"
        prin  = next((p for p, cs in PRINCIPLES.items() if crit in cs), "Other")
        alt   = "F2F3F4" if ri % 2 == 0 else "FFFFFF"
        for ci, v in enumerate([ri, crit, level, CRIT_NAMES.get(crit, crit),
                                 cnt, sn, round(sn/N*100,1), prin], 1):
            c = ws2.cell(row=row, column=ci, value=v)
            c.fill      = fill("FADBD8" if (ci==3 and level=="A") else
                               ("FDEBD0" if ci==3 else alt))
            c.alignment = ctr() if ci in (1,2,3,5,6,7) else lft()
            c.border    = bdr()
            c.font      = Font(name="Arial", bold=(ci in (1,2)), size=10)
            if ci == 7: c.number_format = '0.0"%"'
        ws2.row_dimensions[row].height = 18

    for col, w in zip("ABCDEFGH", [8,12,10,38,16,14,10,16]):
        ws2.column_dimensions[col].width = w

    # ══════════════════════════════════════════════════════════════════════════
    # SHEET 3 – Per-Site Results
    # ══════════════════════════════════════════════════════════════════════════
    ws3 = wb.create_sheet("Per-Site Results")
    ws3.sheet_view.showGridLines = False
    ws3.merge_cells("A1:I1")
    ws3["A1"].value = (f"Per-Site Accessibility Results — "
                       f"{N:,} Tested Sites ({country})")
    ws3["A1"].font  = Font(name="Arial", bold=True, size=13, color=WHITE)
    ws3["A1"].fill  = fill(NAVY)
    ws3["A1"].alignment = ctr()
    ws3.row_dimensions[1].height = 24
    ws3.row_dimensions[2].height = 6

    hrow(ws3, 3,
         ["#","Organization","Website URL","Issues (2.0)","Issues (2.1)",
          "Issues (2.2)","Score /100","Compliance %","Severity"],
         bg="2E4057")

    sorted_tested = sorted(
        tested,
        key=lambda r: -(r.get('accessibility_score') or 0)
    )
    for ri, r in enumerate(sorted_tested, 1):
        row = 3 + ri
        s   = r.get('accessibility_score')
        alt = "F8F9FA" if ri % 2 == 0 else "FFFFFF"
        vals = [ri,
                r.get('organization',''),
                r.get('final_url') or r.get('url',''),
                safe_get(r, 'count_2_0', safe_get(r,'count_2_1')),
                safe_get(r, 'count_2_1'),
                safe_get(r, 'count_2_2'),
                s,
                r.get('compliance_pct'),
                r.get('severity_score')]
        for ci, v in enumerate(vals, 1):
            c = ws3.cell(row=row, column=ci, value=v)
            c.border = bdr()
            c.font   = Font(name="Arial", size=9)
            if ci == 7:
                c.fill      = fill(score_bg(s))
                c.alignment = ctr()
                c.font      = Font(name="Arial", size=9, bold=True,
                                   color=score_color(s))
            elif ci in (4, 5, 6, 8, 9):
                c.fill      = fill(alt)
                c.alignment = ctr()
            elif ci == 3:
                c.fill      = fill(alt)
                c.alignment = lft(False)
                c.font      = Font(name="Arial", size=9,
                                   color="1155CC", underline="single")
            else:
                c.fill      = fill(alt)
                c.alignment = lft()
            if ci == 8: c.number_format = '0.0"%"'
        ws3.row_dimensions[row].height = 14

    ws3.freeze_panes = "A4"
    ws3.auto_filter.ref = f"A3:I{N+3}"
    for col, w in zip("ABCDEFGHI", [6,42,36,10,10,10,10,12,10]):
        ws3.column_dimensions[col].width = w
    ws3.row_dimensions[3].height = 20

    # ══════════════════════════════════════════════════════════════════════════
    # SHEET 4 – Best & Worst Performers
    # ══════════════════════════════════════════════════════════════════════════
    ws4 = wb.create_sheet("Best & Worst Performers")
    ws4.sheet_view.showGridLines = False
    ws4.merge_cells("A1:F1")
    ws4["A1"].value = f"Best & Worst Performing Organizations — {country}"
    ws4["A1"].font  = Font(name="Arial", bold=True, size=13, color=WHITE)
    ws4["A1"].fill  = fill(NAVY)
    ws4["A1"].alignment = ctr()
    ws4.row_dimensions[1].height = 24

    sec(ws4, 3, "TOP 20 BEST — Lowest Violation Count", 6, bg=GREEN)
    hrow(ws4, 4,
         ["Rank","Organization","URL","WCAG 2.1 Issues","Score","Severity"],
         bg=TEAL)
    best20  = sorted(tested,
                     key=lambda r: (safe_get(r,'count_2_1'),
                                    -(r.get('accessibility_score') or 0)))[:20]
    worst20 = sorted(tested,
                     key=lambda r: (-safe_get(r,'count_2_1'),
                                    r.get('accessibility_score') or 0))[:20]

    for ri, r in enumerate(best20, 1):
        row = 4 + ri
        bg  = "D5F5E3" if ri <= 3 else ("EAF4FB" if ri <= 10 else "F2F3F4")
        for ci, v in enumerate([ri, r.get('organization',''),
                                 r.get('final_url', r.get('url','')),
                                 safe_get(r,'count_2_1'),
                                 r.get('accessibility_score'),
                                 r.get('severity_score')], 1):
            c = ws4.cell(row=row, column=ci, value=v)
            c.fill      = fill(bg); c.border = bdr()
            c.alignment = ctr() if ci in (1,4,5,6) else lft()
            c.font      = Font(name="Arial",
                               bold=(ci==2 and ri<=3), size=10)
        ws4.row_dimensions[row].height = 16

    ws4.row_dimensions[25].height = 10
    sec(ws4, 26, "TOP 20 WORST — Highest Violation Count", 6, bg=RED)
    hrow(ws4, 27,
         ["Rank","Organization","URL","WCAG 2.1 Issues","Score","Severity"],
         bg="922B21")
    for ri, r in enumerate(worst20, 1):
        row = 27 + ri
        bg  = "FADBD8" if ri <= 3 else ("FDEBD0" if ri <= 10 else "F9F9F9")
        n21 = safe_get(r, 'count_2_1')
        for ci, v in enumerate([ri, r.get('organization',''),
                                 r.get('final_url', r.get('url','')),
                                 n21,
                                 r.get('accessibility_score'),
                                 r.get('severity_score')], 1):
            c = ws4.cell(row=row, column=ci, value=v)
            c.fill      = fill(bg); c.border = bdr()
            c.alignment = ctr() if ci in (1,4,5,6) else lft()
            c.font      = Font(name="Arial",
                               bold=(ci in (2,4) and ri<=3),
                               color=(RED if n21 >= 50 else "000000"),
                               size=10)
        ws4.row_dimensions[row].height = 16

    for col, w in zip("ABCDEF", [6,44,36,14,10,10]):
        ws4.column_dimensions[col].width = w

    # ══════════════════════════════════════════════════════════════════════════
    # SHEET 5 – Zero-Violation & Errors
    # ══════════════════════════════════════════════════════════════════════════
    ws5 = wb.create_sheet("Zero-Violation & Errors")
    ws5.sheet_view.showGridLines = False
    ws5.merge_cells("A1:E1")
    ws5["A1"].value = (f"Sites with Zero Violations & "
                       f"Unreachable Sites — {country}")
    ws5["A1"].font  = Font(name="Arial", bold=True, size=13, color=WHITE)
    ws5["A1"].fill  = fill(NAVY)
    ws5["A1"].alignment = ctr()
    ws5.row_dimensions[1].height = 24

    sec(ws5, 3,
        f"{len(zero_sites)} SITES WITH ZERO WCAG 2.1 VIOLATIONS",
        5, bg=GREEN)
    hrow(ws5, 4,
         ["#","Organization","Website URL","WCAG 2.1 Issues","WCAG 2.2 Issues"],
         bg=TEAL)
    for ri, r in enumerate(zero_sites, 1):
        row = 4 + ri
        for ci, v in enumerate([ri, r.get('organization',''),
                                 r.get('final_url', r.get('url','')),
                                 safe_get(r,'count_2_1'),
                                 safe_get(r,'count_2_2')], 1):
            c = ws5.cell(row=row, column=ci, value=v)
            c.fill      = fill("D5F5E3"); c.border = bdr()
            c.alignment = ctr() if ci in (1,4,5) else lft()
            c.font      = Font(name="Arial", bold=(ci==2), size=10)
        ws5.row_dimensions[row].height = 16

    err_start = 4 + len(zero_sites) + 2
    sec(ws5, err_start, f"{len(errors)} UNREACHABLE SITES", 5, bg="7F8C8D")
    hrow(ws5, err_start+1,
         ["#","Organization","URL Attempted","Error Type","Status"],
         bg="717D7E")
    for ri, r in enumerate(errors, 1):
        row = err_start + 1 + ri
        err = (r.get('error') or 'Unknown')[:55]
        bg  = "EAECEE" if ri % 2 == 0 else "F8F9FA"
        for ci, v in enumerate([ri, r.get('organization',''),
                                 r.get('url',''), err,
                                 r.get('status','')], 1):
            c = ws5.cell(row=row, column=ci, value=v)
            c.fill      = fill(bg); c.border = bdr()
            c.alignment = lft() if ci in (2,3,4) else ctr()
            c.font      = Font(name="Arial", size=9)
        ws5.row_dimensions[row].height = 14

    for col, w in zip("ABCDE", [6,44,36,35,14]):
        ws5.column_dimensions[col].width = w

    # ══════════════════════════════════════════════════════════════════════════
    # SHEET 6 – Score Distribution
    # ══════════════════════════════════════════════════════════════════════════
    ws6 = wb.create_sheet("Score Distribution")
    ws6.sheet_view.showGridLines = False
    ws6.merge_cells("A1:F1")
    ws6["A1"].value = (f"Accessibility Score Distribution — "
                       f"{country} Civil Society Websites")
    ws6["A1"].font  = Font(name="Arial", bold=True, size=13, color=WHITE)
    ws6["A1"].fill  = fill(NAVY)
    ws6["A1"].alignment = ctr()
    ws6.row_dimensions[1].height = 24
    ws6.row_dimensions[2].height = 8

    sec(ws6, 3, "SCORE BAND BREAKDOWN", 6, bg=TEAL)
    hrow(ws6, 4,
         ["Score Band","Classification","Sites","% of Tested",
          "Cumulative %","Notes"],
         bg="154360")
    band_defs = [
        (100,100,"Perfect",       "D5F5E3","Zero WCAG 2.1 violations"),
        (90, 99, "Excellent",     "D5F5E3","Broadly accessible with minor gaps"),
        (80, 89, "Good",          "EAF4FB","Accessible with some improvements needed"),
        (70, 79, "Fair",          "FEF9E7","Notable barriers for some users"),
        (60, 69, "Needs Work",    "FDEBD0","Significant accessibility barriers"),
        (50, 59, "Poor",          "FAD7A0","Substantial issues across criteria"),
        (0,  49, "Critical",      "FADBD8","Major barriers — likely unusable with AT"),
    ]
    cumul = 0
    for ri, (lo, hi, lbl, bg_, note) in enumerate(band_defs):
        cnt = sum(1 for r in scored
                  if (r['accessibility_score'] == lo if lo == hi
                      else lo <= r['accessibility_score'] <= hi))
        pct = cnt / N * 100; cumul += pct; row = 5 + ri
        band_str = f"{lo}" if lo == hi else f"{lo}–{hi}"
        for ci, v in enumerate([band_str, lbl, cnt,
                                 round(pct,1), round(cumul,1), note], 1):
            c = ws6.cell(row=row, column=ci, value=v)
            c.fill      = fill(bg_); c.border = bdr()
            c.alignment = ctr() if ci in (1,2,3,4,5) else lft()
            c.font      = Font(name="Arial",
                               bold=(lbl in ("Perfect","Critical")),
                               size=10)
            if ci in (4, 5): c.number_format = '0.0"%"'

    ws6.row_dimensions[12].height = 8
    sec(ws6, 13, "SCORE DECILES", 4, bg="154360")
    hrow(ws6, 14,
         ["Percentile","Score","Interpretation",""],
         bg=TEAL)
    s_sorted = sorted(scores)
    for ri, p in enumerate([10,20,25,30,40,50,60,70,75,80,90,95]):
        idx = int(p / 100 * len(s_sorted))
        sv  = s_sorted[min(idx, len(s_sorted)-1)]
        interp = ("Bottom quartile" if p <= 25 else
                  "Median"          if p == 50 else
                  "Top quartile"    if p >= 75 else "")
        row = 15 + ri
        bg  = "EAF4FB" if ri % 2 == 0 else "FFFFFF"
        for ci, v in enumerate([f"{p}th", sv, interp, ""], 1):
            c = ws6.cell(row=row, column=ci, value=v)
            c.fill      = fill(bg); c.border = bdr()
            c.alignment = ctr() if ci in (1, 2) else lft()
            c.font      = Font(name="Arial",
                               bold=(p in (25, 50, 75)), size=10)

    for col, w in zip("ABCDEF", [14,16,16,14,14,35]):
        ws6.column_dimensions[col].width = w

    # ── Save ──────────────────────────────────────────────────────────────────
    wb.save(out_path)
    print(f"\nReport saved: {out_path}")
    print(f"Sheets: {', '.join(wb.sheetnames)}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("Usage: python generate_ward_report.py <results_file.json>")
        sys.exit(1)

    json_path = sys.argv[1]

    # Support relative paths — look next to the script if not found
    if not os.path.isabs(json_path):
        here = os.path.dirname(os.path.abspath(__file__))
        candidate = os.path.join(here, json_path)
        if os.path.exists(candidate):
            json_path = candidate

    if not os.path.exists(json_path):
        print(f"ERROR: file not found: {json_path}")
        sys.exit(1)

    stem     = os.path.splitext(os.path.basename(json_path))[0]
    # Save report in the same folder as this script (works on Windows)
    here     = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(here, f"WARD_Report_{stem}.xlsx")

    build_report(json_path, out_path)


if __name__ == "__main__":
    main()
