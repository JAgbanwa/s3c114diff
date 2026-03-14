#!/usr/bin/env python3
"""
worker_d114.py  —  Charity Engine / BOINC Python wrapper

Equation:
    Y² = 36·x³ + 36·m²·x² + 12·m³·x + m⁴ − 19·m

where m, x, Y are integers and m ≠ 0.

Strategy:
    Weierstrass-lift to Ê(m): Ŷ² = X̂³ + 36m²X̂² + 432m³X̂ + 1296m⁴ − 24624m
    then call PARI/GP's ellintegralpoints() — provably finds ALL integer
    points.  Filter those with 36|X̂ and 36|Ŷ to recover (x, Y).

Work-unit file format (wu.txt):
    m_start  <int>
    m_end    <int>
    batch    <int>   (m values per gp subprocess; default 20)

Output (result.txt):  one line per solution:  m  x  Y

Checkpoint (checkpoint_d114.json):
    {"last_m": <int>}

Usage (standalone):
    python3 worker_d114.py wu.txt result.txt [checkpoint_d114.json]

BOINC/CE:
    Same invocation.  Set BOINC=1 in environment for heartbeat thread.

Dependencies:
    gp (PARI/GP ≥ 2.11)  —  apt-get install pari-gp
    Python 3.8+
"""

import sys
import os
import json
import time
import subprocess
import threading
import argparse
import re
from pathlib import Path

# ── optional in-process PARI via cypari2 ──────────────────────────────
try:
    import cypari2 as _cpmod
    _PARI = _cpmod.Pari()
    _PARI.default("stacksize", 512 * 1024 * 1024)       # 512 MB
    HAS_CYPARI = True
except Exception:
    HAS_CYPARI = False

# ── BOINC heartbeat ────────────────────────────────────────────────────
_BOINC_MODE = (os.environ.get("BOINC", "0") == "1")

def _heartbeat():
    while True:
        try:
            Path("fraction_done").write_text("0.5\n")
        except Exception:
            pass
        time.sleep(10)

if _BOINC_MODE:
    threading.Thread(target=_heartbeat, daemon=True).start()

# ── Paths ──────────────────────────────────────────────────────────────
_HERE      = Path(__file__).parent
_GP_SCRIPT = _HERE / "worker_d114.gp"
_GP_BIN    = os.environ.get("GP_BIN", "gp")
_GP_STACK  = os.environ.get("GP_STACK_MB", "512")       # MB

# ── Pure-Python equation helpers (for fallback and verification) ────────

def ec_rhs_weierstrass(m: int, Xh: int) -> int:
    """RHS of the Weierstrass lift."""
    return Xh**3 + 36*m**2*Xh**2 + 432*m**3*Xh + 1296*m**4 - 24624*m

def ec_rhs_orig(m: int, x: int) -> int:
    """RHS of the original equation."""
    return 36*x**3 + 36*m**2*x**2 + 12*m**3*x + m**4 - 19*m

def verify(m: int, x: int, Y: int) -> bool:
    return Y*Y == ec_rhs_orig(m, x)


# ══════════════════════════════════════════════════════════════════════
# cypari2 path (fast, in-process)
# ══════════════════════════════════════════════════════════════════════

def _cypari_search_one(m: int) -> list[tuple[int,int,int]]:
    """Find integer solutions for a single m using cypari2."""
    solutions = []
    a2 = 36   * m**2
    a4 = 432  * m**3
    a6 = 1296 * m**4 - 24624 * m

    try:
        E = _PARI.ellinit([0, a2, 0, a4, a6])
        if _PARI.ellisoncurve(E, E) == 0:          # sanity
            pass
        if _PARI(E).disc == 0:
            return solutions
        pts = _PARI.ellintegralpoints(E)
        for pt in pts:
            Xh = int(pt[0])
            Yh = int(pt[1])
            if Xh % 36 != 0 or Yh % 36 != 0:
                continue
            x = Xh // 36
            Yv = Yh // 36
            if not verify(m, x, Yv):
                continue
            solutions.append((m, x,  Yv))
            if Yv != 0:
                solutions.append((m, x, -Yv))
    except Exception as e:
        # Fall back to gp subprocess on cypari failure
        pass
    return solutions


# ══════════════════════════════════════════════════════════════════════
# gp subprocess path (robust, handles huge stacks)
# ══════════════════════════════════════════════════════════════════════

def _gp_search_batch(m_start: int, m_end: int) -> list[tuple[int,int,int]]:
    """Run gp on [m_start, m_end] and parse solutions."""
    solutions = []
    cmd = (
        f'read("{_GP_SCRIPT}"); '
        f'd114_search({m_start}, {m_end})'
    )
    try:
        proc = subprocess.run(
            [_GP_BIN, "-q", f"--stacksize={_GP_STACK}m"],
            input=cmd,
            capture_output=True,
            text=True,
            timeout=int(os.environ.get("GP_TIMEOUT", "3600")),
        )
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) == 3:
                try:
                    m, x, Y = int(parts[0]), int(parts[1]), int(parts[2])
                    if verify(m, x, Y):
                        solutions.append((m, x, Y))
                except ValueError:
                    pass
        if proc.returncode != 0 and proc.stderr:
            print(f"[gp stderr] {proc.stderr[:500]}", file=sys.stderr)
    except subprocess.TimeoutExpired:
        print(f"[worker_d114] GP timeout for m=[{m_start},{m_end}]",
              file=sys.stderr)
    return solutions


# ══════════════════════════════════════════════════════════════════════
# Main search loop
# ══════════════════════════════════════════════════════════════════════

def search_range(
    m_start: int,
    m_end: int,
    batch: int,
    result_path: str,
    checkpoint_path: str,
) -> None:

    # ── Load checkpoint ──────────────────────────────────────────────
    last_m = m_start - 1
    if os.path.exists(checkpoint_path):
        try:
            data = json.loads(Path(checkpoint_path).read_text())
            last_m = int(data.get("last_m", last_m))
            print(f"[worker_d114] Resuming from m={last_m+1}", flush=True)
        except Exception:
            pass

    resume_start = last_m + 1
    if resume_start > m_end:
        print("[worker_d114] Already complete.", flush=True)
        return

    # ── Open result file (append) ────────────────────────────────────
    with open(result_path, "a") as out:
        m = resume_start
        while m <= m_end:
            chunk_end = min(m + batch - 1, m_end)

            # Choose engine.
            if HAS_CYPARI and (chunk_end - m + 1) == 1:
                # Single-m case: cypari is fast
                sols = _cypari_search_one(m)
            else:
                sols = _gp_search_batch(m, chunk_end)

            for (mv, xv, Yv) in sols:
                line = f"{mv} {xv} {Yv}\n"
                out.write(line)
                print(f"[SOLUTION] {line.strip()}", flush=True)
            out.flush()

            # ── Checkpoint ───────────────────────────────────────────
            Path(checkpoint_path).write_text(
                json.dumps({"last_m": chunk_end})
            )
            print(f"[worker_d114] Done m=[{m}, {chunk_end}]", flush=True)
            m = chunk_end + 1


# ══════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════

def _parse_wu(wu_path: str) -> dict:
    params = {}
    with open(wu_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                params[parts[0]] = parts[1]
    return params


def main(argv=None):
    parser = argparse.ArgumentParser(description="s3c114diff CE worker")
    parser.add_argument("wu_file",         help="Work-unit input file")
    parser.add_argument("result_file",     help="Result output file")
    parser.add_argument("checkpoint_file", nargs="?",
                        default="checkpoint_d114.json",
                        help="Checkpoint JSON (default: checkpoint_d114.json)")
    args = parser.parse_args(argv)

    params    = _parse_wu(args.wu_file)
    m_start   = int(params["m_start"])
    m_end     = int(params["m_end"])
    batch     = int(params.get("batch", 20))

    print(
        f"[worker_d114] m=[{m_start}, {m_end}]  batch={batch}  "
        f"cypari={'yes' if HAS_CYPARI else 'no'}",
        flush=True
    )

    search_range(m_start, m_end, batch, args.result_file, args.checkpoint_file)
    print("[worker_d114] Complete.", flush=True)


if __name__ == "__main__":
    main()
