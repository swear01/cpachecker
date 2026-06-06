#!/usr/bin/env python3
"""Rebuild <set>_summary.csv from logs (fix duplicates, missing rows, bad result tokens).

The batch script used awk '{print $NF}' on Verification result lines, which
mis-parsed TRUE/.../configuration as 'configuration' and UNKNOWN,...,analysis as 'analysis'.
"""
from __future__ import annotations

import argparse
import csv
import re
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SET_DIR = REPO / "docs/vguided-cegar/benchmark_sets"

RE_VER = re.compile(r"Verification result:\s*(\w+)", re.I)
RE_REFS = re.compile(r"Number of predicate refinements:\s+(\d+)")
RE_WALL = re.compile(r"Total time for CPAchecker:\s+([\d.]+)")


def parse_manifest(set_name: str) -> list[tuple[str, str]]:
    path = SET_DIR / f"{set_name}.list"
    rows: list[tuple[str, str]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rel = line.split("#", 1)[0].strip()
        task = Path(rel).stem
        rows.append((task, rel))
    return rows


def parse_log(log_path: Path) -> tuple[str, int, float, str]:
    if not log_path.is_file():
        return "MISSING_LOG", 0, 0.0, "no_log"
    text = log_path.read_text(errors="replace")
    m = RE_VER.search(text)
    if m:
        result = m.group(1).upper()
    elif "Exception" in text or "java.lang." in text:
        result = "ERROR"
    else:
        result = "UNKNOWN"
    rm = RE_REFS.search(text)
    refs = int(rm.group(1)) if rm else 0
    wm = RE_WALL.search(text)
    wall = float(wm.group(1)) if wm else 0.0
    note = ""
    if result == "ERROR":
        note = "exception"
    elif result == "UNKNOWN" and refs == 0 and wall < 5:
        note = "fast_unknown"
    return result, refs, wall, note


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--set", default="full_scalar", help="benchmark set name")
    ap.add_argument(
        "--out-base",
        type=Path,
        default=REPO / "output/vguide/experiments/full_scalar_vguide",
    )
    ap.add_argument("--no-backup", action="store_true")
    args = ap.parse_args()

    out_base = args.out_base.resolve()
    log_dir = out_base / "logs"
    summary = out_base / f"{args.set}_summary.csv"
    if not summary.is_file() and args.set == "full_scalar":
        summary = out_base / "full_scalar_summary.csv"

    manifest = parse_manifest(args.set)
    if not manifest:
        raise SystemExit(f"empty manifest for set={args.set}")

    if summary.is_file() and not args.no_backup:
        bak = summary.with_suffix(".csv.bak")
        shutil.copy2(summary, bak)
        print(f"backup: {bak}")

    rows_out: list[dict[str, str]] = []
    stats = {"ok": 0, "missing": 0, "error": 0}
    for task, rel in manifest:
        log = log_dir / f"{task}.log"
        result, refs, wall, note = parse_log(log)
        if result == "MISSING_LOG":
            stats["missing"] += 1
        elif result == "ERROR":
            stats["error"] += 1
        else:
            stats["ok"] += 1
        rows_out.append(
            {
                "task": task,
                "rel_path": rel,
                "result": result,
                "refinements": str(refs),
                "wall_s": f"{wall:.3f}".rstrip("0").rstrip("."),
                "log": str(log),
                "note": note,
            }
        )

    fieldnames = ["task", "rel_path", "result", "refinements", "wall_s", "log", "note"]
    with summary.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows_out)

    print(f"wrote {summary} ({len(rows_out)} tasks)")
    print(f"stats: {stats}")
    from collections import Counter

    print("result:", dict(Counter(r["result"] for r in rows_out)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
