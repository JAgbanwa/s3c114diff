#!/usr/bin/env python3
"""
validator_d114.py  —  Charity Engine / BOINC Validator

Checks that two result files for the same WU agree on integer solutions to:

    Y² = 36·x³ + 36·m²·x² + 12·m³·x + m⁴ − 19·m   (m ≠ 0)

Exit codes (BOINC convention):
    0  — valid (results agree)
    1  — invalid / disagreement
    2  — error  (can't read or parse files)

Called by BOINC as:
    python3 validator_d114.py <result1_file> <result2_file>
"""

import sys


def ec_rhs(m: int, x: int) -> int:
    return (36 * x**3
            + 36 * m**2 * x**2
            + 12 * m**3 * x
            + m**4
            - 19 * m)


def verify(m: int, x: int, Y: int) -> bool:
    return Y * Y == ec_rhs(m, x)


def parse_file(path: str) -> set | None:
    """Returns set of (m, x, |Y|) triples, or None on I/O error."""
    sols: set[tuple[int,int,int]] = set()
    try:
        with open(path) as f:
            for ln in f:
                ln = ln.strip()
                if not ln or ln.startswith("#"):
                    continue
                parts = ln.split()
                if len(parts) != 3:
                    continue
                try:
                    m, x, Y = int(parts[0]), int(parts[1]), int(parts[2])
                    sols.add((m, x, abs(Y)))
                except ValueError:
                    pass
    except OSError as e:
        print(f"[validator] cannot read {path}: {e}", file=sys.stderr)
        return None
    return sols


def main():
    if len(sys.argv) < 3:
        print("Usage: validator_d114.py <result1> <result2>", file=sys.stderr)
        sys.exit(2)

    r1 = parse_file(sys.argv[1])
    r2 = parse_file(sys.argv[2])

    if r1 is None or r2 is None:
        sys.exit(2)

    # Algebraic check on every claimed solution
    for (m, x, Y) in r1 | r2:
        if not verify(m, x, Y):
            print(f"[validator] ALGEBRAIC FAIL: m={m} x={x} Y={Y}",
                  file=sys.stderr)
            sys.exit(1)

    if r1 == r2:
        print(f"[validator] VALID — both results agree ({len(r1)} solutions)")
        sys.exit(0)
    else:
        only_r1 = r1 - r2
        only_r2 = r2 - r1
        print(f"[validator] MISMATCH — only_r1={only_r1}  only_r2={only_r2}",
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
