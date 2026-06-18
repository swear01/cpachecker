#!/usr/bin/env python3
"""Offline reproduction of the termination ranking-function result (report Table 3).

Reads only the recorded experiment outputs in data/ -- no API key, no network, no
CPAchecker run required. Regenerates: stock 80 -> VGuide 84 (+4 / 0 lost / 0 wrong).

Usage:  python3 reproduce_termination.py
"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")


def load_expected(list_path):
    exp = {}
    with open(list_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            path = line.split()[0]
            task = os.path.basename(path)
            task = task[:-2] if task.endswith(".c") else task
            verdict = [t for t in line.split() if t.startswith("expected=")]
            exp[task] = verdict[0].split("=")[1] if verdict else "?"
    return exp


def load_results(csv_path):
    out = {}
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            out[row["task"]] = row["result"]
    return out


def solved(res, exp):
    return (res == "TRUE" and exp == "true") or (res == "FALSE" and exp == "false")


def wrong(res, exp):
    return (res == "TRUE" and exp == "false") or (res == "FALSE" and exp == "true")


def summarize(name, results, exp):
    nsolved = sum(1 for t in results if solved(results[t], exp.get(t, "?")))
    ntrue = sum(1 for t, r in results.items() if r == "TRUE" and exp.get(t) == "true")
    nfalse = sum(1 for t, r in results.items() if r == "FALSE" and exp.get(t) == "false")
    nwrong = sum(1 for t in results if wrong(results[t], exp.get(t, "?")))
    print(f"  {name:32s} solved={nsolved:3d}  TRUE={ntrue:3d}  FALSE={nfalse:3d}  wrong={nwrong}")
    return nsolved, nwrong


def main():
    exp = load_expected(os.path.join(DATA, "termination_scalar.list"))
    stock = load_results(os.path.join(DATA, "termination_scalar_300_stock.csv"))
    vguide = load_results(os.path.join(DATA, "termination_scalar_300_vguide.csv"))

    print(f"termination_scalar: {len(exp)} tasks "
          f"({sum(1 for v in exp.values() if v == 'true')} terminating / "
          f"{sum(1 for v in exp.values() if v == 'false')} non-terminating)\n")
    s_solved, s_wrong = summarize("lasso analysis (stock)", stock, exp)
    v_solved, v_wrong = summarize("  + VGuide ranking oracle", vguide, exp)

    new_wins = [t for t in vguide
                if solved(vguide[t], exp.get(t, "?")) and not solved(stock.get(t, ""), exp.get(t, "?"))]
    lost = [t for t in stock
            if solved(stock[t], exp.get(t, "?")) and not solved(vguide.get(t, ""), exp.get(t, "?"))]
    print(f"\n  NET {v_solved - s_solved:+d}   new wins={len(new_wins)}   lost={len(lost)}   "
          f"wrong={v_wrong}")
    for t in new_wins:
        print(f"    +WIN  {t}  (expected={exp.get(t)})")

    ok = (s_solved == 80 and v_solved == 84 and v_wrong == 0 and len(lost) == 0)
    print("\nMatches report Table 3 (stock 80 -> VGuide 84, +4, 0 lost, 0 wrong): "
          + ("YES" if ok else "NO"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
