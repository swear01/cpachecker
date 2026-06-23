#!/usr/bin/env python3
"""Offline check of report Table 2 reachability numbers from recorded summaries.

Reads artifact/data/reachsafety_*_summary.csv — no API key, no CPAchecker run.
"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

EXPECTED_PORTFOLIO = [
    ("ii", "0", 486, 0, 222.5),
    ("ii", "1", 493, 7, 217.9),
    ("ii", "2", 505, 19, 209.0),
    ("ii", "3", 505, 19, 211.3),
]

EXPECTED_ISOLATION = [
    ("i", "stock", 224, 0, 428.4),
    ("i", "source_prior", 224, 0, 427.1),
    ("i", "fire1", 253, 29, 406.5),
    ("i", "skip1", 252, 28, 407.4),
    ("i", "v171", 236, 12, 418.8),
]


def load_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def check_portfolio(rows):
    ok = True
    by_step = {r["step"]: r for r in rows}
    for track, step, solved, delta, par2 in EXPECTED_PORTFOLIO:
        r = by_step.get(step)
        if not r:
            print(f"  MISSING step {step}")
            ok = False
            continue
        for label, got, want in (
            ("solved", int(r["solved"]), solved),
            ("delta", int(r["delta_vs_stock"]), delta),
            ("par2", float(r["par2_s"]), par2),
            ("wrong", int(r["wrong"]), 0),
        ):
            if got != want:
                print(f"  step {step} {label}: got {got}, want {want}")
                ok = False
    return ok


def check_isolation(rows):
    ok = True
    by_arm = {r["arm"]: r for r in rows}
    for track, arm, solved, delta, par2 in EXPECTED_ISOLATION:
        r = by_arm.get(arm)
        if not r:
            print(f"  MISSING arm {arm}")
            ok = False
            continue
        for label, got, want in (
            ("solved", int(r["solved"]), solved),
            ("delta", int(r["delta_vs_stock"]), delta),
            ("par2", float(r["par2_s"]), par2),
            ("wrong", int(r["wrong"]), 0),
        ):
            if got != want:
                print(f"  arm {arm} {label}: got {got}, want {want}")
                ok = False
    return ok


def main():
    port_path = os.path.join(DATA, "reachsafety_svcomp26_deploy_20260623_summary.csv")
    iso_path = os.path.join(DATA, "reachsafety_pure_predicate_decomposition_summary.csv")

    print("Table 2 track (ii) svcomp26 portfolio deployment:")
    p_ok = check_portfolio(load_csv(port_path))

    print("\nTable 2 track (i) pure predicate decomposition:")
    i_ok = check_isolation(load_csv(iso_path))

    ok = p_ok and i_ok
    print("\nMatches report Table 2 (764 tasks, 0 wrong): " + ("YES" if ok else "NO"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
