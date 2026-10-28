#!/usr/bin/env python3
"""
Recomputes the figures reported in the paper from the files in results/.

    python replicate_tables.py            (expects results/ next to this script)
    python replicate_tables.py --results path/to/results

It prints the headline numbers, Table 2, Table 3, Table 4, the values plotted in
Figures 1 to 3, the WCAG 2.2 transition figures and the reachability breakdown,
each next to the value printed in the paper, and flags any that differ.

Definitions, as used in the paper
---------------------------------
Frame        one record per organization after removing exact duplicate URLs
             within each country (first occurrence kept).
Audited      records with status "tested". Everything else (connection
             failures, HTTP errors, timeouts, TLS and server errors, parse
             errors) counts as unreachable.
Extended     the full itemized list in issues_2_2: the 18 criteria of the
             WCAG 2.1 AA set plus the four criteria WCAG 2.2 introduces
             (2.4.11, 3.2.6, 3.3.7, 3.3.8), with 4.1.1 still included.
WCAG 2.1 AA  the extended list without the four WCAG 2.2 criteria.
WCAG 2.0     issues_2_0.
WCAG 2.2     the extended list without 4.1.1, which WCAG 2.2 removed.
"""

import argparse
import collections
import gzip
import json
import os
import sys

COUNTRIES = [("uk", "United Kingdom"), ("nz", "New Zealand"), ("aus", "Australia"),
             ("irl", "Ireland"), ("usa", "United States")]
NEW22 = {"2.4.11", "3.2.6", "3.3.7", "3.3.8"}
PRINCIPLE = {"1": "perceivable", "2": "operable", "3": "understandable", "4": "robust"}
# Official W3C conformance levels for the evaluated criteria (the paper uses these,
# not the level field stored in the issue records).
LEVEL_A = {"1.1.1", "1.3.1", "1.4.1", "2.1.1", "2.4.1", "2.4.2", "2.4.4", "2.5.3", "3.1.1", "3.2.6", "3.3.7", "4.1.1", "4.1.2"}

EXPECTED = {
    "frame": 161220, "unreachable": 25616, "unreachable_pct": 15.9, "generous_pct": 13.6,
    "err_connection": 15628, "err_404": 3660, "err_403": 3614, "err_timeout": 1112, "err_other": 1602,
    "audited": 135604, "total21": 1325591, "mean21": 9.8, "median21": 6,
    "zero21": 1850, "zero21_pct": 1.36, "zero20_pct": 3.06, "levelA_pct": 71.0, "sites_levelA_pct": 89.2,
    "p90": 19, "p99": 64, "max": 3332, "worst_decile_pct": 40.8,
    "bins": {"0": 1850, "1-4": 49567, "5-9": 44408, "10-19": 26621, "20-49": 10849, "50+": 2309},
    "principles": {"perceivable": 49.4, "operable": 29.7, "robust": 18.4, "understandable": 2.5},
    "table3": {"4.1.1": (241131, 31.8), "1.1.1": (208129, 24.8), "2.4.4": (164596, 33.3), "1.3.1": (163186, 58.7),
               "1.4.13": (85441, 17.3), "1.4.12": (83868, 61.8), "2.4.6": (77734, 57.3), "2.5.3": (74627, 13.2),
               "1.4.4": (69907, 51.6), "1.3.5": (49639, 15.7), "2.4.11": (49080, 36.2), "2.4.1": (20879, 15.4)},
    "alt_missing": 208129, "form_label": 99177, "generic_links": 136343,
    "table4": {"uk": (66428, 9.20, 3.55, 1.51, 1.61), "nz": (12206, 9.36, 2.78, 1.65, 1.85),
               "aus": (32792, 9.49, 2.41, 1.01, 1.16), "irl": (1844, 10.89, 2.33, 0.87, 1.03),
               "usa": (22334, 12.04, 2.79, 1.34, 1.54)},
    "fig3_22": {"uk": 8.1, "nz": 8.1, "aus": 8.2, "irl": 9.7, "usa": 10.3},
    "decay": {"aus": 10.2, "irl": 10.2, "usa": 12.4, "uk": 18.0, "nz": 24.6},
    "new22_sites_pct": 48.2, "c2411_pct": 36.2, "c326_pct": 17.1,
    "total22": 1158122, "drop_pct": 12.6, "worse_pct": 35.2, "better_pct": 25.4,
    "kw_h": 1368, "kw_eps2": 0.010, "max_delta": 0.16,
}


def load(results_dir, code):
    path = os.path.join(results_dir, f"results_{code}_orgs.json.gz")
    with gzip.open(path, "rt", encoding="utf-8") as f:
        records = json.load(f)
    seen = {}
    for r in records:
        seen.setdefault(r["url"], r)
    return list(seen.values())


def ext(r):
    return r["issues_2_2"]


def set21(r):
    return [i for i in r["issues_2_2"] if i["criterion"] not in NEW22]


def set22(r):
    return [i for i in r["issues_2_2"] if i["criterion"] != "4.1.1"]


def classify(error):
    e = error or ""
    if e.startswith("Connection"):
        return "connection"
    if e.startswith("HTTP 404"):
        return "404"
    if e.startswith("HTTP 403"):
        return "403"
    if e.startswith("Timeout"):
        return "timeout"
    return "other"


def pct(a, b):
    return 100.0 * a / b if b else 0.0


def percentile(sorted_values, p):
    k = (len(sorted_values) - 1) * p / 100.0
    lo, hi = int(k), min(int(k) + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (k - lo)


def kruskal_wallis(groups):
    """H statistic with tie correction and epsilon-squared, as in scipy.stats.kruskal."""
    allv = sorted((v, g) for g, vals in enumerate(groups) for v in vals)
    n = len(allv)
    ranks = [0.0] * n
    i = 0
    tie_term = 0
    while i < n:
        j = i
        while j + 1 < n and allv[j + 1][0] == allv[i][0]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[k] = avg
        t = j - i + 1
        tie_term += t ** 3 - t
        i = j + 1
    rank_sum = [0.0] * len(groups)
    for (v, g), r in zip(allv, ranks):
        rank_sum[g] += r
    h = 12.0 / (n * (n + 1)) * sum(rs * rs / len(groups[g]) for g, rs in enumerate(rank_sum)) - 3 * (n + 1)
    h /= 1 - tie_term / (n ** 3 - n)
    k = len(groups)
    return h, (h - k + 1) / (n - k)


def cliffs_delta(a, b):
    """Probability that a value from a exceeds one from b, minus the reverse."""
    import bisect
    sb = sorted(b)
    m = len(sb)
    more = less = 0
    for v in a:
        lo = bisect.bisect_left(sb, v)
        hi = bisect.bisect_right(sb, v)
        more += lo
        less += m - hi
    return (more - less) / (len(a) * m)


class Report:
    def __init__(self):
        self.mismatches = 0

    def line(self, label, value, expected=None, fmt="{:,}", tol=0.0):
        if isinstance(value, float):
            text = f"{value:,.2f}" if fmt == "{:,}" else fmt.format(value)
        else:
            text = fmt.format(value)
        mark = ""
        if expected is not None:
            ok = abs(float(value) - float(expected)) <= tol
            mark = "   paper: " + (f"{expected:,}" if isinstance(expected, int) else f"{expected}") + ("" if ok else "   <-- differs")
            if not ok:
                self.mismatches += 1
        print(f"  {label:<62s} {text:>14s}{mark}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "results"))
    args = ap.parse_args()
    rep = Report()
    E = EXPECTED

    data = {code: load(args.results, code) for code, _ in COUNTRIES}
    frame = sum(len(v) for v in data.values())
    audited = {c: [r for r in v if r["status"] == "tested"] for c, v in data.items()}
    tested = [r for v in audited.values() for r in v]
    unreachable = [r for v in data.values() for r in v if r["status"] != "tested"]

    print("\nReachability (RQ1)")
    rep.line("Organizations in the frame", frame, E["frame"])
    rep.line("Unreachable websites", len(unreachable), E["unreachable"])
    rep.line("Unreachable share (percent)", pct(len(unreachable), frame), E["unreachable_pct"], "{:.1f}", 0.05)
    errs = collections.Counter(classify(r["error"]) for r in unreachable)
    rep.line("  connection failures", errs["connection"], E["err_connection"])
    rep.line("  HTTP 404", errs["404"], E["err_404"])
    rep.line("  HTTP 403", errs["403"], E["err_403"])
    rep.line("  timeouts", errs["timeout"], E["err_timeout"])
    rep.line("  TLS, server and other errors", errs["other"], E["err_other"])
    rep.line("Unreachable if every 403 is treated as reachable (percent)",
             pct(len(unreachable) - errs["403"], frame), E["generous_pct"], "{:.1f}", 0.05)
    for code, name in sorted(COUNTRIES, key=lambda x: pct(len(data[x[0]]) - len(audited[x[0]]), len(data[x[0]]))):
        rep.line(f"  decay, {name} (percent)", pct(len(data[code]) - len(audited[code]), len(data[code])), E["decay"][code], "{:.1f}", 0.05)

    print("\nConformance (RQ2), WCAG 2.1 AA set")
    n21 = [len(set21(r)) for r in tested]
    n21s = sorted(n21)
    total21 = sum(n21)
    rep.line("Audited sites", len(tested), E["audited"])
    rep.line("Violation instances", total21, E["total21"])
    rep.line("Mean per homepage", total21 / len(tested), E["mean21"], "{:.1f}", 0.05)
    rep.line("Median per homepage", n21s[len(n21s) // 2], E["median21"])
    zero21 = sum(1 for n in n21 if n == 0)
    rep.line("Sites with no detectable violation", zero21, E["zero21"])
    rep.line("  share (percent)", pct(zero21, len(tested)), E["zero21_pct"], "{:.2f}", 0.005)
    zero20 = sum(1 for r in tested if len(r["issues_2_0"]) == 0)
    rep.line("Clean share under the WCAG 2.0 subset (percent)", pct(zero20, len(tested)), E["zero20_pct"], "{:.2f}", 0.005)
    levelA = sum(1 for r in tested for i in set21(r) if i["criterion"] in LEVEL_A)
    rep.line("Level A share of instances (percent)", pct(levelA, total21), E["levelA_pct"], "{:.1f}", 0.05)
    sitesA = sum(1 for r in tested if any(i["criterion"] in LEVEL_A for i in set21(r)))
    rep.line("Sites failing at least one Level A criterion (percent)", pct(sitesA, len(tested)), E["sites_levelA_pct"], "{:.1f}", 0.05)
    rep.line("90th percentile site", int(round(percentile(n21s, 90))), E["p90"])
    rep.line("99th percentile site", int(round(percentile(n21s, 99))), E["p99"])
    rep.line("Maximum", n21s[-1], E["max"])
    worst = sum(n21s[-(len(n21s) // 10):])
    rep.line("Worst decile share of instances (percent)", pct(worst, total21), E["worst_decile_pct"], "{:.1f}", 0.05)

    print("\nTable 2. Violations per audited site")
    bins = [("0", 0, 0), ("1-4", 1, 4), ("5-9", 5, 9), ("10-19", 10, 19), ("20-49", 20, 49), ("50+", 50, 10**9)]
    for label, lo, hi in bins:
        count = sum(1 for n in n21 if lo <= n <= hi)
        rep.line(f"  {label:<6s} sites ({pct(count, len(tested)):.1f} percent)", count, E["bins"][label])

    print("\nViolations by WCAG principle (extended evaluation, percent of instances)")
    pr = collections.Counter(PRINCIPLE[i["criterion"][0]] for r in tested for i in ext(r))
    tot_ext = sum(pr.values())
    for name in ["perceivable", "operable", "robust", "understandable"]:
        rep.line(f"  {name}", pct(pr[name], tot_ext), E["principles"][name], "{:.1f}", 0.05)

    print("\nTable 3. Most affected criteria (extended evaluation): instances, share of sites")
    inst = collections.Counter(); sites = collections.Counter()
    for r in tested:
        crits = collections.Counter(i["criterion"] for i in ext(r))
        for c, k in crits.items():
            inst[c] += k; sites[c] += 1
    for c, k in inst.most_common():
        exp = E["table3"].get(c)
        rep.line(f"  {c:<7s} instances", k, exp[0] if exp else None)
        rep.line(f"  {c:<7s} sites affected (percent)", pct(sites[c], len(tested)), exp[1] if exp else None, "{:.1f}", 0.05)

    print("\nMost frequent defect texts")
    texts = collections.Counter(i["issue"] for r in tested for i in ext(r))
    rep.line("  Image missing alt attribute", texts["Image missing alt attribute"], E["alt_missing"])
    rep.line("  Form input missing label", texts["Form input missing label"], E["form_label"])
    generic = texts['Non-descriptive link text: "read more"'] + texts['Non-descriptive link text: "learn more"']
    rep.line('  "read more" and "learn more" links', generic, E["generic_links"])

    print("\nTable 4 and Figure 3. National outcomes")
    for code, name in COUNTRIES:
        t = audited[code]
        a21 = [len(set21(r)) for r in t]; a22 = [len(set22(r)) for r in t]
        e = E["table4"][code]
        rep.line(f"  {name}: audited", len(t), e[0])
        rep.line(f"  {name}: mean violations, WCAG 2.1 AA", sum(a21) / len(t), e[1], "{:.2f}", 0.005)
        rep.line(f"  {name}: zero-violation share, 2.0 subset (percent)", pct(sum(1 for r in t if len(r["issues_2_0"]) == 0), len(t)), e[2], "{:.2f}", 0.005)
        rep.line(f"  {name}: zero-violation share, 2.1 (percent)", pct(sum(1 for n in a21 if n == 0), len(t)), e[3], "{:.2f}", 0.005)
        rep.line(f"  {name}: zero-violation share, 2.2 strict (percent)", pct(sum(1 for n in a22 if n == 0), len(t)), e[4], "{:.2f}", 0.005)
        rep.line(f"  {name}: mean violations, WCAG 2.2 strict (Fig. 3)", sum(a22) / len(t), E["fig3_22"][code], "{:.1f}", 0.05)

    print("\nCross-country test on per-site WCAG 2.1 AA counts (RQ3)")
    groups = [[len(set21(r)) for r in audited[code]] for code, _ in COUNTRIES]
    h, eps2 = kruskal_wallis(groups)
    rep.line("Kruskal-Wallis H", h, E["kw_h"], "{:,.0f}", 0.5)
    rep.line("Epsilon-squared (share of variance explained by country)", eps2, E["kw_eps2"], "{:.3f}", 0.0005)
    deltas = {}
    for i in range(len(COUNTRIES)):
        for j in range(i + 1, len(COUNTRIES)):
            deltas[(COUNTRIES[i][1], COUNTRIES[j][1])] = cliffs_delta(groups[i], groups[j])
    pair, d = max(deltas.items(), key=lambda kv: abs(kv[1]))
    rep.line(f"Largest pairwise Cliff's delta ({pair[0]} vs {pair[1]})", abs(d), E["max_delta"], "{:.2f}", 0.005)

    print("\nWCAG 2.2 transition (RQ3)")
    n22 = [len(set22(r)) for r in tested]
    new_sites = sum(1 for r in tested if any(i["criterion"] in NEW22 for i in ext(r)))
    rep.line("Sites acquiring violations from the new criteria (percent)", pct(new_sites, len(tested)), E["new22_sites_pct"], "{:.1f}", 0.05)
    rep.line("  2.4.11 focus not obscured, sites (percent)", pct(sites["2.4.11"], len(tested)), E["c2411_pct"], "{:.1f}", 0.05)
    rep.line("  3.2.6 consistent help, sites (percent)", pct(sites["3.2.6"], len(tested)), E["c326_pct"], "{:.1f}", 0.05)
    rep.line("Total instances under strict WCAG 2.2", sum(n22), E["total22"])
    rep.line("Change from the WCAG 2.1 total (percent)", pct(total21 - sum(n22), total21), E["drop_pct"], "{:.1f}", 0.05)
    rep.line("Sites formally worse under 2.2 (percent)", pct(sum(1 for a, b in zip(n21, n22) if b > a), len(tested)), E["worse_pct"], "{:.1f}", 0.05)
    rep.line("Sites formally better under 2.2 (percent)", pct(sum(1 for a, b in zip(n21, n22) if b < a), len(tested)), E["better_pct"], "{:.1f}", 0.05)

    print("\nFigure 1 data: sites per WCAG 2.1 AA violation count (0 to 39), then 40-49, 50-59, 60-79, 80+")
    hist = collections.Counter(n21)
    print("  " + " ".join(f"{k}:{hist[k]}" for k in range(0, 40)))
    print(f"  40-49:{sum(hist[k] for k in range(40, 50))} 50-59:{sum(hist[k] for k in range(50, 60))} "
          f"60-79:{sum(hist[k] for k in range(60, 80))} 80+:{sum(v for k, v in hist.items() if k >= 80)}")

    print()
    if rep.mismatches:
        print(f"{rep.mismatches} value(s) differ from the paper.")
        sys.exit(1)
    print("Every value matches the paper.")


if __name__ == "__main__":
    main()
