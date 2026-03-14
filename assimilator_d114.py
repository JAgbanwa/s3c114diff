#!/usr/bin/env python3
"""
assimilator_d114.py  —  Charity Engine / BOINC Assimilator

Watches a results directory for new result files, verifies each
claimed solution algebraically, and merges into a master file.

Equation:
    Y² = 36·x³ + 36·m²·x² + 12·m³·x + m⁴ − 19·m   (m ≠ 0)

Usage:
    python3 assimilator_d114.py \\
        --results_dir ./results \\
        --master      solutions_d114.txt

Continuous (systemd / screen):
    while true; do python3 assimilator_d114.py ...; sleep 5; done
"""

import os
import sys
import time
import argparse
import hashlib
from pathlib import Path


# ══════════════════════════════════════════════════════════════════════
# Equation helpers
# ══════════════════════════════════════════════════════════════════════

def ec_rhs(m: int, x: int) -> int:
    return (36 * x**3
            + 36 * m**2 * x**2
            + 12 * m**3 * x
            + m**4
            - 19 * m)


def verify(m: int, x: int, Y: int) -> bool:
    return Y * Y == ec_rhs(m, x)


# ══════════════════════════════════════════════════════════════════════
# State helpers
# ══════════════════════════════════════════════════════════════════════

PROCESSED_LOG = "assimilated_d114.log"


def load_processed(log_path: str) -> set:
    s = set()
    if os.path.exists(log_path):
        with open(log_path) as f:
            for line in f:
                s.add(line.strip())
    return s


def file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_existing(master_path: str) -> set:
    seen: set[tuple[int,int,int]] = set()
    if not os.path.exists(master_path):
        return seen
    with open(master_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 3:
                try:
                    m, x, Y = int(parts[0]), int(parts[1]), int(parts[2])
                    seen.add((m, x, abs(Y)))
                except ValueError:
                    pass
    return seen


# ══════════════════════════════════════════════════════════════════════
# Process one result file
# ══════════════════════════════════════════════════════════════════════

def process_file(
    result_path: str,
    master_path: str,
    existing: set,
    stats: dict,
) -> None:
    new_solutions = []
    fail_count    = 0

    with open(result_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 3:
                continue
            try:
                m, x, Y = int(parts[0]), int(parts[1]), int(parts[2])
            except ValueError:
                continue

            key = (m, x, abs(Y))
            if key in existing:
                continue

            if not verify(m, x, Y):
                print(f"[assimilator] FAIL verify: m={m} x={x} Y={Y}",
                      file=sys.stderr)
                fail_count += 1
                continue

            new_solutions.append((m, x, Y))
            existing.add(key)
            # Also add −Y variant if not present
            neg_key = (m, x, abs(-Y))
            if neg_key not in existing and Y != 0:
                existing.add(neg_key)

    if new_solutions:
        with open(master_path, "a") as out:
            for (m, x, Y) in new_solutions:
                out.write(f"{m} {x} {Y}\n")
                print(f"[assimilator] NEW SOLUTION m={m} x={x} Y={Y}")
        stats["new"] += len(new_solutions)

    stats["verified"] += len(new_solutions)
    stats["failed"]   += fail_count


# ══════════════════════════════════════════════════════════════════════
# Main loop
# ══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Assimilator for d114 elliptic curve search"
    )
    parser.add_argument("--results_dir", default="results",
                        help="Directory containing result files")
    parser.add_argument("--master",      default="solutions_d114.txt",
                        help="Master solutions file")
    parser.add_argument("--log",         default=PROCESSED_LOG)
    parser.add_argument("--once",        action="store_true",
                        help="Process once then exit (default: loop)")
    parser.add_argument("--sleep",       type=int, default=10,
                        help="Seconds between scans (default 10)")
    args = parser.parse_args()

    processed_log = args.log

    # Ensure master file exists
    Path(args.master).touch(exist_ok=True)

    while True:
        processed = load_processed(processed_log)
        existing  = load_existing(args.master)
        stats     = {"new": 0, "verified": 0, "failed": 0}

        result_files = sorted(Path(args.results_dir).glob("*.txt"))
        for rp in result_files:
            fh = file_hash(str(rp))
            if fh in processed:
                continue
            print(f"[assimilator] Processing {rp.name}")
            process_file(str(rp), args.master, existing, stats)
            with open(processed_log, "a") as lg:
                lg.write(fh + "\n")

        if stats["new"] or stats["failed"]:
            print(
                f"[assimilator] new={stats['new']}  "
                f"verified={stats['verified']}  "
                f"failed={stats['failed']}"
            )

        if args.once:
            break
        time.sleep(args.sleep)


if __name__ == "__main__":
    main()
