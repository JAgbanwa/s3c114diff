#!/usr/bin/env python3
"""
parametric_enum_d114.py
━━━━━━━━━━━━━━━━━━━━━━━
Enumerate the infinite parametric family of the d114 equation
INSTANTLY via the closed-form formula — no search needed.

Equation:  Y² = 36x³ + 36m²x² + 12m³x + m⁴ − 19m

Factored:  Y² = (m² + 6mx)² + D,   D = 36x³ − 19m

Family:    D = 0  ⟺  36x³ = 19m  ⟺  x = 19k, m = 12996k³
           Then Y = ±(m² + 6mx)  =  ±m(m + 6x)

Generates all k ∈ [k_start, k_end] and both ±k (→ ±m, ±x accordingly).

Usage:
    # All solutions with m ∈ [10^20, 10^30]:
    python3 parametric_enum_d114.py \\
        --m_lo 1e20 --m_hi 1e30 \\
        --output output/solutions_parametric_d114.txt

    # Custom k range:
    python3 parametric_enum_d114.py --k_start 1 --k_end 1000000

    # Count only (fast estimate):
    python3 parametric_enum_d114.py --m_lo 1e20 --m_hi 1e30 --count_only
"""

from __future__ import annotations
import sys
import math
import argparse
from pathlib import Path


# ── Equation ──────────────────────────────────────────────────────────

def verify(m: int, x: int, Y: int) -> bool:
    return Y * Y == (36*x**3 + 36*m**2*x**2 + 12*m**3*x + m**4 - 19*m)


# ── Parametric family formulas ─────────────────────────────────────────
#
#  For any integer k ≠ 0:
#      m = 12996 · k³
#      x = 19 · k
#      Y = ± (m² + 6mx)  = ± m(m + 6x)
#
#  Negative k gives  m < 0, x < 0 — also valid solutions.
#  By symmetry we can generate k ≥ 1  and include ±Y.
#
CM = 12996   # = 36 * 19²
CX = 19


def param_solution(k: int) -> tuple[int, int, int]:
    """Return (m, x, Y_positive) for parameter k."""
    m = CM * k**3
    x = CX * k
    Y = m * (m + 6 * x)   # = m² + 6mx, always ≥ 0 for k > 0
    return m, x, Y


# ── Range helpers ──────────────────────────────────────────────────────

def k_range_for_m(m_lo: int, m_hi: int, positive_m: bool = True) -> tuple[int, int]:
    """
    Return the inclusive k range [k_start, k_end] such that
    CM * k³ ∈ [m_lo, m_hi] (positive k for positive m).
    """
    k_start = math.ceil((m_lo / CM) ** (1/3))
    k_end   = int((m_hi / CM) ** (1/3))
    # Exact integer arithmetic adjustment
    while CM * k_start**3 < m_lo:
        k_start += 1
    while k_end > 0 and CM * k_end**3 > m_hi:
        k_end -= 1
    return k_start, k_end


# ── Main ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Enumerate d114 parametric family solutions"
    )
    parser.add_argument("--m_lo",    type=float, default=None,
                        help="Lower bound on |m| (e.g. 1e20)")
    parser.add_argument("--m_hi",    type=float, default=None,
                        help="Upper bound on |m| (e.g. 1e30)")
    parser.add_argument("--k_start", type=int,   default=None,
                        help="Start k value (overrides m_lo)")
    parser.add_argument("--k_end",   type=int,   default=None,
                        help="End k value (overrides m_hi)")
    parser.add_argument("--output",  default="output/solutions_parametric_d114.txt",
                        help="Output file (appended)")
    parser.add_argument("--count_only", action="store_true",
                        help="Just print counts, don't write file")
    parser.add_argument("--verify_sample", type=int, default=5,
                        help="Verify this many random samples (0 = skip)")
    parser.add_argument("--negative_m", action="store_true",
                        help="Also include m < 0 solutions (k < 0)")
    args = parser.parse_args()

    # Determine k range
    if args.k_start is not None:
        k_lo = args.k_start
        k_hi = args.k_end if args.k_end else args.k_start
    elif args.m_lo is not None:
        m_lo = int(args.m_lo)
        m_hi = int(args.m_hi) if args.m_hi else 10**100
        k_lo, k_hi = k_range_for_m(m_lo, m_hi)
        print(f"m ∈ [{m_lo:.2e}, {m_hi:.2e}]  →  k ∈ [{k_lo:,}, {k_hi:,}]")
    else:
        k_lo, k_hi = 1, 1_000_000
        print(f"Default: k ∈ [{k_lo:,}, {k_hi:,}]")

    total_k = k_hi - k_lo + 1
    if total_k <= 0:
        print("No k values in range.")
        return

    print(f"Total k values: {total_k:,}")
    print(f"Total solutions (±Y for each k, positive m only): {total_k * 2:,}")
    if args.negative_m:
        print(f"With negative m (±k): {total_k * 4:,} total solutions")

    if args.count_only:
        return

    # Sample verification
    if args.verify_sample > 0:
        import random
        step = max(1, total_k // args.verify_sample)
        print(f"\nVerifying {args.verify_sample} samples...")
        all_ok = True
        for i, k in enumerate(range(k_lo, k_hi+1, step)):
            if i >= args.verify_sample:
                break
            m, x, Y = param_solution(k)
            ok = verify(m, x, Y) and verify(m, x, -Y)
            if not ok:
                print(f"  FAIL k={k}: m={m} x={x} Y={Y}")
                all_ok = False
            else:
                print(f"  OK   k={k}: m={m:.4e} x={x:.4e} Y={Y:.4e}")
        if all_ok:
            print("All samples verified ✓")

    # Enumerate
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    REPORT_EVERY = max(1, total_k // 100)

    print(f"\nWriting to {out_path} ...")
    written = 0
    with open(out_path, "a") as f:
        # Positive m (k > 0)
        for k in range(k_lo, k_hi + 1):
            m, x, Y = param_solution(k)
            f.write(f"{m} {x} {Y}\n")
            if Y != 0:
                f.write(f"{m} {x} {-Y}\n")
                written += 2
            else:
                written += 1

            if args.negative_m:
                # k < 0  →  m < 0, x < 0
                mn = -m
                xn = -x
                Yn =  m * m + 6 * m * x   # same |Y|
                f.write(f"{mn} {xn} {Yn}\n")
                if Yn != 0:
                    f.write(f"{mn} {xn} {-Yn}\n")
                    written += 2
                else:
                    written += 1

            if k % REPORT_EVERY == 0:
                pct = (k - k_lo + 1) / total_k * 100
                print(f"  {pct:.1f}%  k={k:,}  written={written:,}", flush=True)

    print(f"\nDone. Written {written:,} solutions to {out_path}")


if __name__ == "__main__":
    main()
