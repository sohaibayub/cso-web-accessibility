#!/usr/bin/env bash
# Runs ward_civil_chunk.py over every chunk file in ./chunks, one after another.
# Safe to stop (Ctrl+C) and re-run later - each chunk resumes from its own
# _results.csv and already-finished chunks are skipped automatically.
#
# Usage:
#   ./run_all_chunks.sh              # 15 workers per chunk (default)
#   ./run_all_chunks.sh 25           # 25 workers per chunk
#
# For an overnight/multi-day run, launch with nohup so it survives you closing
# the terminal:
#   nohup ./run_all_chunks.sh 20 > run_log.txt 2>&1 &

WORKERS=${1:-15}

for f in chunks/*.csv; do
    # skip chunk files that are themselves _results.csv outputs
    [[ "$f" == *_results.csv ]] && continue

    out="${f%.csv}_results.csv"
    if [[ -f "$out" ]]; then
        total_rows=$(($(wc -l < "$f") - 1))
        done_rows=$(($(wc -l < "$out") - 1))
        if [[ "$done_rows" -ge "$total_rows" ]]; then
            echo "=== $f already complete ($done_rows/$total_rows), skipping ==="
            continue
        fi
    fi

    echo "=== $f ==="
    python3 ward_civil_chunk.py "$f" --workers "$WORKERS"
done

echo "All chunks processed."
