#!/usr/bin/env python3
"""
work_generator_large_d114.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Charity Engine / BOINC Work Generator for the LARGE-m regime:
    |m| ∈ [10^20, 10^30]

Deploys the GMP C binary worker_large_d114 on 500k CE volunteer nodes.

Strategy:
  ┌───────────────────────────────────────────────────────────────┐
  │ 1. PARAMETRIC SWEEP (instant):                                │
  │    Enumerate the known infinite family x=19k, m=12996k³       │
  │    via parametric_enum_d114.py — no WUs needed.               │
  │                                                               │
  │ 2. ANOMALOUS SOLUTION SIEVE (GMP C worker, distributed):      │
  │    For each m in [M_LO, M_HI], run the shift-sieve t ∈ [-T,T]│
  │    checking for solutions outside the parametric family.       │
  │    Splits into WUs covering BATCH_M m-values each.            │
  └───────────────────────────────────────────────────────────────┘

WU file format (for worker_large_d114 binary):
    m_start  <big int>
    m_end    <big int>
    t_max    500

Each WU covers BATCH_M = 200 consecutive m values.
At T_MAX=500: ~2000 GMP operations × 5 candidates × 200 m = 2M ops/WU → ~5s/WU.
With 500k nodes: covers ≈ 10^11 m-values / day.

Usage:
    python3 work_generator_large_d114.py \\
        --m_lo 1e20 --m_hi 1e30 \\
        --wu_dir ./wu_large --dry_run

    python3 work_generator_large_d114.py \\
        --m_lo 1e20 --m_hi 1e30 \\
        --boinc_project_dir /home/boincadm/projects/s3c114diff \\
        --app_name d114_large \\
        --daemon
"""

from __future__ import annotations
import os
import sys
import math
import time
import sqlite3
import argparse
import subprocess
import shutil
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────
M_LO              = 10**20         # search floor
M_HI              = 10**30         # search ceiling
BATCH_M           = 200            # m values per WU
T_MAX             = 500            # shift range |t| ≤ T_MAX
APP_NAME          = "d114_large"
FANOUT            = 2
MAX_OUTSTANDING   = 500_000        # to saturate 500k CE nodes
DELAY_BOUND       = 86400 * 14     # 14-day deadline
POLL_INTERVAL     = 60             # seconds between daemon loops
DB_FILE           = "wg_large_d114_state.db"
WU_DIR            = Path("wu_large")

# ─────────────────────────────────────────────────────────────────────
# State database (stores m values as TEXT for arbitrary precision)
# ─────────────────────────────────────────────────────────────────────

def init_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wu_state (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            wu_name    TEXT UNIQUE,
            m_start    TEXT NOT NULL,
            m_end      TEXT NOT NULL,
            direction  TEXT NOT NULL,   -- 'pos' or 'neg'
            sent_at    REAL,
            status     TEXT DEFAULT 'sent'
        )
    """)
    conn.commit()
    return conn


def get_frontier(conn: sqlite3.Connection, m_lo: int, m_hi: int) -> tuple[int, int]:
    """Return (pos_frontier, neg_frontier) — next m to submit in each direction."""
    row = conn.execute(
        "SELECT MAX(CAST(m_end AS INTEGER)) FROM wu_state WHERE direction='pos'"
    ).fetchone()
    pos = int(row[0]) + 1 if row[0] is not None else m_lo

    row = conn.execute(
        "SELECT MIN(CAST(m_start AS INTEGER)) FROM wu_state WHERE direction='neg'"
    ).fetchone()
    neg = int(row[0]) - 1 if row[0] is not None else -m_lo

    return pos, neg


def outstanding(conn: sqlite3.Connection) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM wu_state WHERE status='sent'"
    ).fetchone()[0]


def record_wu(conn, wu_name, m_start, m_end, direction):
    conn.execute(
        "INSERT OR IGNORE INTO wu_state "
        "(wu_name,m_start,m_end,direction,sent_at) VALUES (?,?,?,?,?)",
        (wu_name, str(m_start), str(m_end), direction, time.time())
    )
    conn.commit()


# ─────────────────────────────────────────────────────────────────────
# WU file creation
# ─────────────────────────────────────────────────────────────────────

def write_wu(wu_dir: Path, wu_name: str, m_start: int, m_end: int) -> Path:
    wu_dir.mkdir(parents=True, exist_ok=True)
    p = wu_dir / f"{wu_name}.txt"
    p.write_text(
        f"m_start  {m_start}\n"
        f"m_end    {m_end}\n"
        f"t_max    {T_MAX}\n"
    )
    return p


# ─────────────────────────────────────────────────────────────────────
# BOINC submission
# ─────────────────────────────────────────────────────────────────────

def submit_boinc(boinc_dir: str, app_name: str,
                 wu_name: str, wu_file: Path) -> bool:
    create_work = Path(boinc_dir) / "bin" / "create_work"
    wu_template  = Path(boinc_dir) / "templates" / "d114_large_wu.xml"
    res_template = Path(boinc_dir) / "templates" / "d114_large_result.xml"

    # Copy WU input to BOINC download hierarchy
    dl = Path(boinc_dir) / "download"
    dl.mkdir(exist_ok=True)
    shutil.copy(wu_file, dl / wu_file.name)

    cmd = [
        str(create_work),
        "--appname",         app_name,
        "--wu_name",         wu_name,
        "--wu_template",     str(wu_template),
        "--result_template", str(res_template),
        "--delay_bound",     str(DELAY_BOUND),
        "--min_quorum",      str(FANOUT),
        "--target_nresults", str(FANOUT),
        wu_file.name,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           cwd=boinc_dir, timeout=30)
        if r.returncode == 0:
            return True
        print(f"[wg_large] create_work FAIL {wu_name}: {r.stderr[:200]}",
              file=sys.stderr)
        return False
    except Exception as e:
        print(f"[wg_large] create_work exception: {e}", file=sys.stderr)
        return False


# ─────────────────────────────────────────────────────────────────────
# Coverage reporting
# ─────────────────────────────────────────────────────────────────────

def coverage_report(conn, m_lo, m_hi):
    total_range = m_hi - m_lo
    row = conn.execute(
        "SELECT MAX(CAST(m_end AS INTEGER)) FROM wu_state WHERE direction='pos'"
    ).fetchone()
    pos_max = int(row[0]) if row[0] else m_lo - 1
    covered = max(0, pos_max - m_lo + 1)
    pct = 100.0 * covered / total_range if total_range > 0 else 0
    print(f"[wg_large] Coverage: pos m up to {pos_max:.4e} "
          f"({covered:.4e}/{total_range:.4e} = {pct:.6f}%)")


# ─────────────────────────────────────────────────────────────────────
# Batch generation
# ─────────────────────────────────────────────────────────────────────

def generate_batch(
    conn,
    count: int,
    wu_dir: Path,
    boinc_dir: str | None,
    app_name: str,
    dry_run: bool,
    m_lo: int,
    m_hi: int,
) -> int:
    pos, neg = get_frontier(conn, m_lo, m_hi)
    submitted = 0

    for _ in range(count // 2 + 1):
        if submitted >= count:
            break

        # ── positive direction ──────────────────────────────────────
        if pos <= m_hi:
            ms, me = pos, min(pos + BATCH_M - 1, m_hi)
            wu_name = f"d114L_p_{ms}_{me}"
            path    = write_wu(wu_dir, wu_name, ms, me)
            if not dry_run and boinc_dir:
                if not submit_boinc(boinc_dir, app_name, wu_name, path):
                    break
            record_wu(conn, wu_name, ms, me, "pos")
            print(f"[wg_large] SUBMIT pos m=[{ms:.4e},{me:.4e}]  wu={wu_name}")
            pos = me + 1
            submitted += 1

        if submitted >= count:
            break

        # ── negative direction ──────────────────────────────────────
        if neg >= -m_hi:
            ms_n, me_n = neg - BATCH_M + 1, neg
            ms_n = max(ms_n, -m_hi)
            wu_name_n = f"d114L_n_{ms_n}_{me_n}"
            path_n    = write_wu(wu_dir, wu_name_n, ms_n, me_n)
            if not dry_run and boinc_dir:
                if not submit_boinc(boinc_dir, app_name, wu_name_n, path_n):
                    break
            record_wu(conn, wu_name_n, ms_n, me_n, "neg")
            print(f"[wg_large] SUBMIT neg m=[{ms_n:.4e},{me_n:.4e}]  wu={wu_name_n}")
            neg = ms_n - 1
            submitted += 1

    return submitted


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Large-m work generator for d114 CE search"
    )
    parser.add_argument("--m_lo",   type=float, default=1e20,
                        help="Search floor |m| (default 1e20)")
    parser.add_argument("--m_hi",   type=float, default=1e30,
                        help="Search ceiling |m| (default 1e30)")
    parser.add_argument("--wu_dir", default="wu_large")
    parser.add_argument("--db",     default=DB_FILE)
    parser.add_argument("--count",  type=int, default=10_000,
                        help="WUs to submit per invocation")
    parser.add_argument("--app_name", default=APP_NAME)
    parser.add_argument("--boinc_project_dir", default=None)
    parser.add_argument("--dry_run", action="store_true")
    parser.add_argument("--daemon",  action="store_true",
                        help="Run forever, aiming to saturate 500k CE nodes")
    parser.add_argument("--t_max",   type=int, default=None,
                        help=f"Override T_MAX (default {T_MAX})")
    args = parser.parse_args()

    global T_MAX, BATCH_M
    if args.t_max:
        T_MAX = args.t_max

    m_lo = int(args.m_lo)
    m_hi = int(args.m_hi)

    wu_dir = Path(args.wu_dir)
    conn   = init_db(args.db)

    print(f"[wg_large] m range: [{m_lo:.4e}, {m_hi:.4e}]")
    print(f"[wg_large] Total m values: {m_hi - m_lo:.4e}")
    print(f"[wg_large] Batch: {BATCH_M} m/WU   T_MAX: {T_MAX}")

    if args.daemon:
        print(f"[wg_large] Daemon mode — targeting 500k CE nodes, "
              f"polling every {POLL_INTERVAL}s")
        while True:
            outs = outstanding(conn)
            if outs < MAX_OUTSTANDING:
                need = min(args.count, MAX_OUTSTANDING - outs)
                n = generate_batch(conn, need, wu_dir,
                                   args.boinc_project_dir, args.app_name,
                                   args.dry_run, m_lo, m_hi)
                outs2 = outstanding(conn)
                coverage_report(conn, m_lo, m_hi)
                print(f"[wg_large] Submitted {n} WUs  ({outs2:,} outstanding)")
            else:
                print(f"[wg_large] {outs:,} WUs outstanding — waiting…")
            time.sleep(POLL_INTERVAL)
    else:
        n = generate_batch(conn, args.count, wu_dir,
                           args.boinc_project_dir, args.app_name,
                           args.dry_run, m_lo, m_hi)
        coverage_report(conn, m_lo, m_hi)
        print(f"[wg_large] Done. Submitted {n} WUs.")


if __name__ == "__main__":
    main()
