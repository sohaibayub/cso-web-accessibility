#!/usr/bin/env python3
"""
Run this after run_all_chunks_json.py finishes. Merges the original
results_uk_orgs.json (38,817 sites, full detail) with the newly re-fetched
chunks/*_results.jsonl (42,161 sites, full detail) into one JSON array in the
same format as the original file.

Usage:
    python merge_detailed_results.py
"""

import glob
import json
import os

with open("results_uk_orgs.json", encoding="utf-8") as f:
    original = json.load(f)

merged = list(original)
seen = {r["url"] for r in original}

added = 0
incomplete_chunks = []
for jsonl_path in sorted(glob.glob(os.path.join("chunks", "*_results.jsonl"))):
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                incomplete_chunks.append(jsonl_path)
                continue
            if r.get("url") in seen:
                continue
            seen.add(r["url"])
            merged.append(r)
            added += 1

with open("results_uk_orgs_full.json", "w", encoding="utf-8") as f:
    json.dump(merged, f, indent=2)

print(f"Original entries: {len(original)}")
print(f"Added from chunks: {added}")
print(f"Total: {len(merged)}")
if incomplete_chunks:
    print(f"Note: skipped a malformed line in {len(set(incomplete_chunks))} file(s), "
          f"likely from a run that was interrupted mid-write: {sorted(set(incomplete_chunks))}")
