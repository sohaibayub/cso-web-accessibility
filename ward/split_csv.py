#!/usr/bin/env python3
"""
Split a large CSV (e.g. the UK 800,000-site list) into fixed-size chunk files
so ward_civil_chunk.py can process it piece by piece.

Usage:
    python split_csv.py uk_all.csv 5000
    (chunk size defaults to 5000 rows if omitted)

Output:
    chunks/uk_all_chunk_0001.csv, chunks/uk_all_chunk_0002.csv, ...
"""

import csv
import math
import os
import sys


def split_csv(in_csv, chunk_size=5000, out_dir="chunks"):
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(in_csv))[0]

    with open(in_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    n_chunks = math.ceil(len(rows) / chunk_size)
    print(f"{len(rows)} rows -> {n_chunks} chunks of up to {chunk_size} rows each")

    for i in range(n_chunks):
        chunk_rows = rows[i * chunk_size:(i + 1) * chunk_size]
        out_path = os.path.join(out_dir, f"{stem}_chunk_{i + 1:04d}.csv")
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(chunk_rows)

    print(f"Done. Chunk files written to ./{out_dir}/")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python split_csv.py <input.csv> [chunk_size]")
        sys.exit(1)
    in_csv = sys.argv[1]
    chunk_size = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
    split_csv(in_csv, chunk_size)
