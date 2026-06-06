#!/usr/bin/env python3
"""Discover loop-category programs under SV_BENCHMARKS for classifier pipeline."""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

BENCH = Path(os.environ.get("SV_BENCHMARKS", os.path.expanduser("~/sv-benchmarks/c")))
OUT = Path(
    os.environ.get(
        "VGUIDE_CANDIDATES_CSV",
        Path(__file__).resolve().parents[2]
        / "results/vguided-cegar/classifier/sv_benchmarks_candidates.csv",
    )
)

# All loop* / loops* under official sv-benchmarks c/ (see setup_benchmarks.sh sparse set)
LOOP_DIR_PREFIXES = ("loop-", "loops", "loops-")


def main() -> int:
    if not BENCH.is_dir():
        print(f"ERROR: {BENCH} not found", file=sys.stderr)
        return 1
    # task -> (category, path); prefer .i over .c
    best: dict[tuple[str, str], Path] = {}
    for sub in sorted(BENCH.iterdir()):
        if not sub.is_dir():
            continue
        name = sub.name
        if not (name.startswith("loop-") or name == "loops" or name.startswith("loops-")):
            continue
        for path in sorted(sub.iterdir()):
            if path.suffix not in (".c", ".i"):
                continue
            task = path.stem
            key = (task, name)
            prev = best.get(key)
            if prev is None or (prev.suffix == ".c" and path.suffix == ".i"):
                best[key] = path
    rows = [
        {"task": task, "input_file": str(p.resolve()), "category": cat}
        for (task, cat), p in sorted(best.items())
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["task", "input_file", "category"])
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} programs -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
