#!/usr/bin/env python3
"""
Runs ward_civil_chunk_json.py (full detail, .jsonl output) over every chunk
file in .\chunks, one after another. Same chunk files already used for the
counts-only pass - this just re-fetches them to capture the full itemized
issue lists this time.

Safe to stop and re-run - each chunk resumes from its own _results.jsonl.

Usage:
    python run_all_chunks_json.py           (15 workers per chunk, default)
    python run_all_chunks_json.py 20        (20 workers per chunk)
"""

import csv
import glob
import json
import os
import subprocess
import sys


def count_data_rows(csv_path):
    with open(csv_path, encoding="utf-8") as f:
        return sum(1 for _ in csv.reader(f)) - 1


def count_jsonl_rows(jsonl_path):
    n = 0
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    json.loads(line)
                    n += 1
                except json.JSONDecodeError:
                    pass
    return n


def main():
    workers = sys.argv[1] if len(sys.argv) > 1 else "15"

    chunk_files = sorted(
        f for f in glob.glob(os.path.join("chunks", "*.csv"))
        if not f.endswith("_results.csv") and not f.endswith("_results.jsonl")
    )

    if not chunk_files:
        print("No chunk files found in .\\chunks\\")
        return

    for chunk in chunk_files:
        out_jsonl = os.path.splitext(chunk)[0] + "_results.jsonl"
        if os.path.exists(out_jsonl):
            total = count_data_rows(chunk)
            done = count_jsonl_rows(out_jsonl)
            if done >= total:
                print(f"=== {chunk} already complete ({done}/{total}), skipping ===")
                continue

        print(f"=== {chunk} ===")
        result = subprocess.run(
            [sys.executable, "ward_civil_chunk_json.py", chunk, "--workers", str(workers)]
        )
        if result.returncode != 0:
            print(f"Chunk {chunk} exited with an error (code {result.returncode}). Stopping.")
            print("Fix the issue and re-run this script - completed chunks will be skipped.")
            sys.exit(result.returncode)

    print("All chunks processed.")


if __name__ == "__main__":
    main()
