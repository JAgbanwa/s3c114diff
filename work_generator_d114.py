#!/usr/bin/env python3
"""
work_generator_d114.py  —  Charity Engine / BOINC Work Generator

Equation:
    Y² = 36·x³ + 36·m²·x² + 12·m³·x + m⁴ − 19·m   (m ≠ 0)

Produces work-units covering all non-zero integers m, expanding
outward from ±1 in both directions simultaneously.

Each WU covers BATCH_SIZE consecutive m values.
WU files land in wu_queue/ and (optionally) are submitted via
BOINC's `bin/create_work`.

── State DB ─────────────────────────────────────────────────────────
SQLite3 file `wg_d114_state.db` records every submitted range so the
generator can be safely restarted / rate-limited.

── Usage ─────────────────────────────────────────────────────────────
Standalone / dry-run:
    python3 work_generator_d114.py --wu_dir ./wu_queue --count 500

With BOINC project:
    python3 work_generator_d114.py \\
        --boinc_project_dir /home/boincadm/projects/s3c114diff \\
        --app_name d114 --count 5000

Continuous daemon (grows until killed):
    python3 work_generator_d114.py --daemon --wu_dir ./wu_queue
"""

from __future__ import annotations
import os
import sys
import time
import sqlite3
import argparse
import subprocess
import shutil
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────
BATCH_SIZE        = 20           # m values per work-unit
GP_TIMEOUT_PER_M  = 300          # seconds per m in WU
GP_STACK_MB       = 512
APP_NAME          = "d114"
FANOUT            = 2            # redundant copies per WU
MAX_OUTSTANDING   = 8000         # pause submission above this
DELAY_BOUND       = 86400 * 14   # 14-day deadline
DB_FILE           = "wg_d114_state.db"
WU_DIR            = Path("wu_queue")
POLL_INTERVAL     = 30           # seconds between daemon loops

# ─────────────────────────────────────────────────────────────────────
# State database
# ─────────────────────────────────────────────────────────────────────

def init_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wu_state (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            wu_name    TEXT UNIQUE,
            m_start    INTEGER NOT NULL,
            m_end      INTEGER NOT NULL,
            direction  TEXT NOT NULL,   -- 'pos' or 'neg'
            sent_at    REAL,
            status     TEXT DEFAULT 'sent'
        )
    """)
    conn.commit()
    return conn


def frontier(conn: sqlite3.Connection) -> tuple[int, int]:
    """Return (pos_frontier, neg_frontier): next unsent m in each direction."""
    row = conn.execute(
        "SELECT MAX(m_end) FROM wu_state WHERE direction='pos'"
    ).fetchone()
    pos = (row[0] + 1) if row[0] is not None else 1

    row = conn.execute(
        "SELECT MIN(m_start) FROM wu_state WHERE direction='neg'"
    ).fetchone()
    neg = (row[0] - 1) if row[0] is not None else -1

    return pos, neg


def outstanding(conn: sqlite3.Connection) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM wu_state WHERE status='sent'"
    ).fetchone()[0]


def record_wu(conn, wu_name, m_start, m_end, direction):
    conn.execute(
        "INSERT OR IGNORE INTO wu_state (wu_name,m_start,m_end,direction,sent_at) "
        "VALUES (?,?,?,?,?)",
        (wu_name, m_start, m_end, direction, time.time())
    )
    conn.commit()


# ─────────────────────────────────────────────────────────────────────
# WU file writing
# ─────────────────────────────────────────────────────────────────────

def write_wu_file(wu_dir: Path, wu_name: str, m_start: int, m_end: int) -> Path:
    wu_dir.mkdir(parents=True, exist_ok=True)
    path = wu_dir / f"{wu_name}.txt"
    path.write_text(
        f"m_start  {m_start}\n"
        f"m_end    {m_end}\n"
        f"batch    {BATCH_SIZE}\n"
        f"timeout_per_m  {GP_TIMEOUT_PER_M}\n"
        f"gp_stack_mb    {GP_STACK_MB}\n"
    )
    return path


# ─────────────────────────────────────────────────────────────────────
# BOINC submission
# ─────────────────────────────────────────────────────────────────────

def submit_boinc(
    boinc_dir: str,
    app_name: str,
    wu_name: str,
    wu_file: Path,
) -> bool:
    create_work = Path(boinc_dir) / "bin" / "create_work"
    if not create_work.exists():
        print(f"[wg] create_work not found: {create_work}", file=sys.stderr)
        return False
    cmd = [
        str(create_work),
        "--appname",       app_name,
        "--wu_name",       wu_name,
        "--wu_template",   str(Path(boinc_dir) / "templates" / "d114_wu.xml"),
        "--result_template", str(Path(boinc_dir) / "templates" / "d114_result.xml"),
        "--fanout",        str(FANOUT),
        "--delay_bound",   str(DELAY_BOUND),
        str(wu_file),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            print(f"[wg] create_work failed: {r.stderr[:200]}", file=sys.stderr)
            return False
        return True
    except Exception as e:
        print(f"[wg] create_work exception: {e}", file=sys.stderr)
        return False


# ─────────────────────────────────────────────────────────────────────
# Main generation loop
# ─────────────────────────────────────────────────────────────────────

def generate_batch(
    conn,
    count: int,
    wu_dir: Path,
    boinc_dir: str | None,
    app_name: str,
    dry_run: bool,
) -> int:
    """Generate up to `count` new WUs.  Returns number submitted."""
    submitted = 0
    pos, neg = frontier(conn)

    for _ in range(count // 2 + 1):
        if submitted >= count:
            break

        # — positive direction —
        ms, me = pos, pos + BATCH_SIZE - 1
        wu_name = f"d114_p_{ms}_to_{me}"
        path = write_wu_file(wu_dir, wu_name, ms, me)
        if not dry_run and boinc_dir:
            ok = submit_boinc(boinc_dir, app_name, wu_name, path)
            if not ok:
                break
        record_wu(conn, wu_name, ms, me, "pos")
        print(f"[wg] SUBMIT pos m=[{ms},{me}]  wu={wu_name}")
        pos = me + 1
        submitted += 1

        if submitted >= count:
            break

        # — negative direction —
        me_n, ms_n = neg, neg - BATCH_SIZE + 1
        wu_name_n = f"d114_n_{ms_n}_to_{me_n}"
        path_n = write_wu_file(wu_dir, wu_name_n, ms_n, me_n)
        if not dry_run and boinc_dir:
            ok = submit_boinc(boinc_dir, app_name, wu_name_n, path_n)
            if not ok:
                break
        record_wu(conn, wu_name_n, ms_n, me_n, "neg")
        print(f"[wg] SUBMIT neg m=[{ms_n},{me_n}]  wu={wu_name_n}")
        neg = ms_n - 1
        submitted += 1

    return submitted


def main():
    parser = argparse.ArgumentParser(
        description="Work generator for d114 elliptic curve search"
    )
    parser.add_argument("--wu_dir",     default="wu_queue")
    parser.add_argument("--db",         default=DB_FILE)
    parser.add_argument("--count",      type=int, default=200,
                        help="WUs to submit per invocation")
    parser.add_argument("--app_name",   default=APP_NAME)
    parser.add_argument("--boinc_project_dir", default=None,
                        help="BOINC project root (enables submission)")
    parser.add_argument("--dry_run",    action="store_true",
                        help="Write WU files but do not call create_work")
    parser.add_argument("--daemon",     action="store_true",
                        help="Run forever, polling every %ds" % POLL_INTERVAL)
    args = parser.parse_args()

    wu_dir = Path(args.wu_dir)
    conn   = init_db(args.db)

    if args.daemon:
        print(f"[wg] Daemon mode — polling every {POLL_INTERVAL}s")
        while True:
            outs = outstanding(conn)
            if outs < MAX_OUTSTANDING:
                need = min(args.count, MAX_OUTSTANDING - outs)
                n = generate_batch(
                    conn, need, wu_dir,
                    args.boinc_project_dir, args.app_name,
                    args.dry_run
                )
                print(f"[wg] Submitted {n} WUs  ({outstanding(conn)} outstanding)")
            else:
                print(f"[wg] {outs} outstanding — waiting…")
            time.sleep(POLL_INTERVAL)
    else:
        n = generate_batch(
            conn, args.count, wu_dir,
            args.boinc_project_dir, args.app_name,
            args.dry_run
        )
        print(f"[wg] Done. Submitted {n} WUs.")


if __name__ == "__main__":
    main()
