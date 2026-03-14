#!/usr/bin/env python3
"""
local_parallel_search_d114.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Runs the d114 elliptic-curve search on all local CPU cores.
Splits the integer m-axis into bands and dispatches each band to a
subprocess running worker_d114.py.  Results are merged into
solutions_d114.txt in real time.

Equation:
    Y² = 36·x³ + 36·m²·x² + 12·m³·x + m⁴ − 19·m   (m ≠ 0)

Usage:
    # Search m ∈ [1, 10000] ∪ [−10000, −1]
    python3 local_parallel_search_d114.py --limit 10000

    # Open-ended search (grows until Ctrl-C)
    python3 local_parallel_search_d114.py --no_limit

    # Override CPU count
    python3 local_parallel_search_d114.py --limit 50000 --workers 8

Output files (auto-created):
    output/solutions_d114.txt    — all verified integer solutions
    output/checkpoint_d114.json  — per-worker checkpoints
    output/search_log_d114.txt   — timestamped progress log
"""

from __future__ import annotations
import os
import sys
import time
import json
import argparse
import subprocess
import threading
import multiprocessing
import tempfile
import signal
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime

# ── locations ──────────────────────────────────────────────────────────
_HERE        = Path(__file__).parent
_WORKER_PY   = _HERE / "worker_d114.py"
_OUTPUT_DIR  = _HERE / "output"
_MASTER_FILE = _OUTPUT_DIR / "solutions_d114.txt"
_LOG_FILE    = _OUTPUT_DIR / "search_log_d114.txt"
_CHKPT_DIR   = _OUTPUT_DIR / "checkpoints"

# ── constants ──────────────────────────────────────────────────────────
DEFAULT_BAND   = 20      # m values per worker invocation
SOLUTIONS_LOCK = threading.Lock()
LOG_LOCK       = threading.Lock()

# ── Python path to use ─────────────────────────────────────────────────
_PYTHON = sys.executable


def _log(msg: str) -> None:
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with LOG_LOCK:
        with open(_LOG_FILE, "a") as f:
            f.write(line + "\n")


def ec_rhs(m: int, x: int) -> int:
    return (36 * x**3 + 36*m**2*x**2 + 12*m**3*x + m**4 - 19*m)


def verify(m: int, x: int, Y: int) -> bool:
    return Y * Y == ec_rhs(m, x)


def _merge_result_file(result_path: Path) -> int:
    """Merge a worker result file into the master.  Returns # new solutions."""
    new = 0
    if not result_path.exists():
        return 0

    # Load existing keys (deduplicate on |Y|)
    existing: set[tuple[int,int,int]] = set()
    if _MASTER_FILE.exists():
        with open(_MASTER_FILE) as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) == 3:
                    try:
                        existing.add((int(parts[0]), int(parts[1]), abs(int(parts[2]))))
                    except ValueError:
                        pass

    with open(result_path) as f:
        lines = f.readlines()

    with SOLUTIONS_LOCK:
        with open(_MASTER_FILE, "a") as out:
            for line in lines:
                parts = line.strip().split()
                if len(parts) != 3:
                    continue
                try:
                    m, x, Y = int(parts[0]), int(parts[1]), int(parts[2])
                except ValueError:
                    continue
                key = (m, x, abs(Y))
                if key in existing:
                    continue
                if not verify(m, x, Y):
                    _log(f"  !! verify FAIL: m={m} x={x} Y={Y}")
                    continue
                out.write(f"{m} {x} {Y}\n")
                out.flush()
                existing.add(key)
                _log(f"  *** SOLUTION FOUND: m={m}  x={x}  Y={Y} ***")
                new += 1
    return new


def _run_band(m_start: int, m_end: int, band_id: int) -> tuple[int, int, list]:
    """Run worker_d114.py on [m_start, m_end].  Returns (m_start, m_end, solutions)."""
    _CHKPT_DIR.mkdir(parents=True, exist_ok=True)
    wu_file   = _CHKPT_DIR / f"wu_{band_id}.txt"
    res_file  = _CHKPT_DIR / f"result_{band_id}.txt"
    chk_file  = _CHKPT_DIR / f"checkpoint_{band_id}.json"

    wu_file.write_text(
        f"m_start  {m_start}\n"
        f"m_end    {m_end}\n"
        f"batch    {DEFAULT_BAND}\n"
    )
    res_file.unlink(missing_ok=True)   # fresh result each call

    cmd = [
        _PYTHON, str(_WORKER_PY),
        str(wu_file), str(res_file), str(chk_file)
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=int(os.environ.get("BAND_TIMEOUT", "7200")),
        )
    except subprocess.TimeoutExpired:
        _log(f"  TIMEOUT band [{m_start},{m_end}]")
        return m_start, m_end, []

    solutions = []
    for line in proc.stdout.splitlines():
        if line.startswith("[SOLUTION]"):
            # e.g. "[SOLUTION] m x Y"
            parts = line.replace("[SOLUTION]", "").strip().split()
            if len(parts) == 3:
                try:
                    solutions.append((int(parts[0]), int(parts[1]), int(parts[2])))
                except ValueError:
                    pass

    return m_start, m_end, solutions


def _generate_bands(limit: int, band_size: int):
    """Yield (m_start, m_end) pairs expanding ±1 … ±limit."""
    m = 1
    while True:
        pos_end = min(m + band_size - 1, limit)
        yield  m,      pos_end
        yield -pos_end, -m
        m = pos_end + 1
        if m > limit:
            break


def _generate_bands_infinite(band_size: int):
    """Yield bands forever, expanding outward."""
    m = 1
    while True:
        yield  m,          m + band_size - 1
        yield -(m + band_size - 1), -m
        m += band_size


# ── Global state for open-ended search checkpoint ─────────────────────
_OE_CHECKPOINT = _OUTPUT_DIR / "oe_d114_frontier.json"

def _oe_load_frontier() -> int:
    if _OE_CHECKPOINT.exists():
        try:
            return int(json.loads(_OE_CHECKPOINT.read_text()).get("frontier", 1))
        except Exception:
            pass
    return 1


def _oe_save_frontier(m: int):
    _OE_CHECKPOINT.write_text(json.dumps({"frontier": m}))


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Local parallel d114 elliptic-curve search"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--limit", type=int, default=None,
                       help="Search |m| ≤ limit")
    group.add_argument("--no_limit", action="store_true",
                       help="Open-ended search growing forever")
    parser.add_argument("--workers", type=int,
                        default=max(1, multiprocessing.cpu_count() - 1),
                        help="Parallel workers (default = CPUs - 1)")
    parser.add_argument("--band", type=int, default=DEFAULT_BAND,
                        help=f"m values per band (default {DEFAULT_BAND})")
    args = parser.parse_args()

    if args.limit is None and not args.no_limit:
        args.limit = 5000           # sensible default

    n_workers = args.workers
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _MASTER_FILE.touch(exist_ok=True)

    _log(f"Starting d114 local search  workers={n_workers}  "
         f"band={args.band}  "
         f"{'open-ended' if args.no_limit else 'limit='+str(args.limit)}")

    total_solutions = 0

    if args.no_limit:
        # Open-ended: continuously dispatch bands
        frontier = _oe_load_frontier()
        _log(f"Resuming from frontier m={frontier}")

        with ProcessPoolExecutor(max_workers=n_workers) as pool:
            futures = {}
            band_id = 0

            def _submit_next(m_pos):
                nonlocal band_id
                m_e = m_pos + args.band - 1
                f1 = pool.submit(_run_band, m_pos, m_e, band_id)
                futures[f1] = (m_pos, m_e, band_id, "+")
                band_id += 1
                f2 = pool.submit(_run_band, -m_e, -m_pos, band_id)
                futures[f2] = (-m_e, -m_pos, band_id, "-")
                band_id += 1
                return m_e + 1

            # Seed initial work
            cur = frontier
            while len(futures) < n_workers * 2 and len(futures) < 200:
                cur = _submit_next(cur)

            try:
                while True:
                    for fut in list(as_completed(list(futures.keys()), timeout=5)):
                        ms, me, bid, sgn = futures.pop(fut)
                        try:
                            _, _, sols = fut.result()
                            if sols:
                                for sv in sols:
                                    _log(f"*** SOLUTION: m={sv[0]} x={sv[1]} Y={sv[2]}")
                                total_solutions += len(sols)
                        except Exception as e:
                            _log(f"  Band [{ms},{me}] error: {e}")

                        # Merge result file
                        res_p = _CHKPT_DIR / f"result_{bid}.txt"
                        new = _merge_result_file(res_p)
                        total_solutions += new

                        _log(f"  Done band [{ms},{me}]  total_solutions={total_solutions}")
                        _oe_save_frontier(cur)

                        # Submit another band
                        cur = _submit_next(cur)

            except KeyboardInterrupt:
                _log("Interrupted — saving state.")
                _oe_save_frontier(cur)

    else:
        # Bounded search
        bands = list(_generate_bands(args.limit, args.band))
        _log(f"Total bands: {len(bands)}")

        with ProcessPoolExecutor(max_workers=n_workers) as pool:
            fmap = {
                pool.submit(_run_band, ms, me, i): (ms, me, i)
                for i, (ms, me) in enumerate(bands)
            }
            done = 0
            for fut in as_completed(fmap):
                ms, me, i = fmap[fut]
                try:
                    _, _, sols = fut.result()
                    new = _merge_result_file(_CHKPT_DIR / f"result_{i}.txt")
                    total_solutions += new
                except Exception as e:
                    _log(f"  Band [{ms},{me}] error: {e}")
                done += 1
                if done % 10 == 0 or done == len(bands):
                    _log(f"  Progress {done}/{len(bands)}  solutions={total_solutions}")

    _log(f"Search complete.  Total solutions: {total_solutions}")
    _log(f"Solutions written to: {_MASTER_FILE}")


if __name__ == "__main__":
    main()
