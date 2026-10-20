#!/usr/bin/env python3
"""
Windows-friendly version of run_all_chunks.sh - runs ward_civil_chunk.py over
every chunk file in .\chunks, one after another. Works the same on Windows,
Mac, or Linux since it's plain Python instead of a shell script.

Safe to stop (Ctrl+C) and re-run later - each chunk resumes from its own
_results.csv and already-finished chunks are skipped automatically.

Usage (from a terminal in this folder):
    python run_all_chunks.py            (15 workers per chunk, default)
    python run_all_chunks.py 20         (20 workers per chunk)

For a long run you can close the terminal without stopping it using
Windows' start /b, or just leave the terminal window open/minimised.
"""

import csv
import glob
import os
import subprocess
import sys


def count_data_rows(csv_path):
    with open(csv_path, encoding="utf-8") as f:
        return sum(1 for _ in csv.reader(f)) - 1  # minus header


def main():
    workers = sys.argv[1] if len(sys.argv) > 1 else "15"

    chunk_files = sorted(
        f for f in glob.glob(os.path.join("chunks", "*.csv"))
        if not f.endswith("_results.csv")
    )

    if not chunk_files:
        print("No chunk files found in .\\chunks\\ - run prepare_resume.py or split_csv.py first.")
        return

    for chunk in chunk_files:
        out_csv = os.path.splitext(chunk)[0] + "_results.csv"
        if os.path.exists(out_csv):
            total = count_data_rows(chunk)
            done = count_data_rows(out_csv)
            if done >= total:
                print(f"=== {chunk} already complete ({done}/{total}), skipping ===")
                continue

        print(f"=== {chunk} ===")
        result = subprocess.run(
            [sys.executable, "ward_civil_chunk.py", chunk, "--workers", str(workers)]
        )
        if result.returncode != 0:
            print(f"Chunk {chunk} exited with an error (code {result.returncode}). Stopping.")
            print("Fix the issue and re-run this script - completed chunks will be skipped.")
            sys.exit(result.returncode)

    print("All chunks processed.")


if __name__ == "__main__":
    main()
