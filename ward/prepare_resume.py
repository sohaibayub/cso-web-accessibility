#!/usr/bin/env python3
"""
Prepare a resume from an existing ward_civil.py JSON output (e.g. results_uk_orgs.json,
~40,000 sites already done) so the remaining sites can be run through
ward_civil_chunk.py without redoing work.

Does two things:

1. Converts the existing JSON results into a flat CSV in the same schema
   ward_civil_chunk.py writes (results_uk_orgs_done.csv), so it can be merged
   with new chunk output later with a single concat.

2. Reads the master UK CSV (name/url or Organization/Website columns), drops
   any row whose URL already appears in the JSON, and splits what's left into
   chunk files under ./chunks/, same as split_csv.py.

Usage:
    python prepare_resume.py uk_all.csv results_uk_orgs.json 5000

Output:
    results_uk_orgs_done.csv       (40,000 already-done sites, flat schema)
    chunks/uk_all_chunk_0001.csv   (remaining sites, chunked)
    chunks/uk_all_chunk_0002.csv
    ...
"""

import csv
import json
import math
import os
import sys

FIELDNAMES = [
    "organization", "url", "final_url", "country", "status", "error",
    "count_2_0", "count_2_1", "count_2_2",
    "accessibility_score", "compliance_pct", "severity_score",
]


def convert_done_json(done_json, out_csv):
    with open(done_json, encoding="utf-8") as f:
        results = json.load(f)

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        w.writeheader()
        for r in results:
            row = {k: r.get(k, "") for k in FIELDNAMES}
            row["error"] = row["error"] or ""
            w.writerow(row)

    done_urls = {r["url"] for r in results if r.get("url")}
    print(f"Converted {len(results)} already-done results -> {out_csv}")
    return done_urls


def split_remaining(master_csv, done_urls, chunk_size, out_dir="chunks"):
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(master_csv))[0]

    with open(master_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        all_rows = list(reader)

    def row_url(r):
        return (r.get("url") or r.get("Website") or r.get("website") or "").strip()

    remaining = [r for r in all_rows if row_url(r) not in done_urls]
    skipped = len(all_rows) - len(remaining)
    print(f"Master CSV: {len(all_rows)} rows, {skipped} already done, {len(remaining)} remaining")

    n_chunks = math.ceil(len(remaining) / chunk_size) if remaining else 0
    print(f"Splitting into {n_chunks} chunks of up to {chunk_size} rows each")

    for i in range(n_chunks):
        chunk_rows = remaining[i * chunk_size:(i + 1) * chunk_size]
        out_path = os.path.join(out_dir, f"{stem}_chunk_{i + 1:04d}.csv")
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(chunk_rows)

    print(f"Done. Chunk files written to ./{out_dir}/")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python prepare_resume.py <master_csv> <done_json> [chunk_size]")
        sys.exit(1)

    master_csv = sys.argv[1]
    done_json = sys.argv[2]
    chunk_size = int(sys.argv[3]) if len(sys.argv) > 3 else 5000

    done_csv = os.path.splitext(os.path.basename(done_json))[0] + "_done.csv"
    done_urls = convert_done_json(done_json, done_csv)
    split_remaining(master_csv, done_urls, chunk_size)
