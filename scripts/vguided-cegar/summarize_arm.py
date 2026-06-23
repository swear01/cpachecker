#!/usr/bin/env python3
"""Print solved / PAR-2 / wrong for one experiment arm (summary CSV + manifest expected)."""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

RE_YML_VERDICT = re.compile(r"^expected_verdict:\s*(\S+)", re.M | re.I)


def load_expected(manifest: Path, bench_root: Path) -> dict[str, str]:
    expected: dict[str, str] = {}
    for line in manifest.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rel = line.split("#", 1)[0].strip()
        task = Path(rel).stem
        yml = bench_root / rel
        yml = yml.with_suffix(".yml") if yml.suffix != ".yml" else yml
        if not yml.is_file():
            found = list(bench_root.rglob(f"{task}.yml"))
            yml = found[0] if found else yml
        if yml.is_file():
            m = RE_YML_VERDICT.search(yml.read_text(errors="replace"))
            if m:
                expected[task] = m.group(1).upper()
    return expected


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--set", required=True)
    p.add_argument("--timelimit", type=float, default=300.0)
    p.add_argument(
        "--manifest",
        type=Path,
        default=Path("docs/vguided-cegar/benchmark_sets"),
    )
    p.add_argument("--bench-root", type=Path, default=Path.home() / "sv-benchmarks/c")
    args = p.parse_args()
    repo = Path(__file__).resolve().parents[2]
    manifest = args.manifest
    if not manifest.is_file():
        manifest = repo / args.manifest / f"{args.set}.list"
    summary = args.out / f"{args.set}_summary.csv"
    if not summary.is_file():
        raise SystemExit(f"missing {summary}")

    exp = load_expected(manifest, args.bench_root)
    runs: dict[str, str] = {}
    walls: dict[str, float] = {}
    with summary.open(newline="") as f:
        for row in csv.DictReader(f):
            task = row["task"]
            runs[task] = (row.get("result") or "UNKNOWN").upper()
            walls[task] = float(row.get("wall_s") or 0)

    wrong = 0
    for task, got in runs.items():
        want = exp.get(task)
        if want and got in ("TRUE", "FALSE") and got != want:
            wrong += 1

    solved = sum(1 for r in runs.values() if r in ("TRUE", "FALSE"))
    par2 = sum(
        walls[t] if runs[t] in ("TRUE", "FALSE") else 2 * args.timelimit for t in runs
    ) / max(len(runs), 1)

    print(f"arm={args.out.name}")
    print(f"tasks={len(runs)} solved={solved} wrong={wrong} par2_avg={par2:.1f}s")
    print(f"summary={summary}")


if __name__ == "__main__":
    main()
