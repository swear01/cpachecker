#!/usr/bin/env python3
"""Regenerate docs/vguided-cegar/benchmark_sets/*.list from classifier CSV + SV_BENCHMARKS tree."""
from __future__ import annotations

import csv
import os
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
# Produced by reclassify_benchmarks.sh from ~/sv-benchmarks (official tree).
CSV_PATH = REPO / "results/vguided-cegar/classifier/scalar_classified.csv"
LEGACY_CSV = REPO / "results/vguided-cegar/classifier/scalar_classified_fmpa2_legacy.csv"
OUT_DIR = REPO / "docs/vguided-cegar/benchmark_sets"
BENCH = Path(os.environ.get("SV_BENCHMARKS", os.path.expanduser("~/sv-benchmarks/c")))

# Tier S sample (hand-curated; paths resolved at regen time)
SAMPLE_TASKS = [
    "up",
    "down",
    "string_concat-noarr",
    "array_3-1",
    "large_const",
    "heapsort",
    "array_3-2",
    "array_4",
]
RESCUE_CORE = [
    "up",
    "down",
    "string_concat-noarr",
    "large_const",
    "heapsort",
    "array_3-1",
]
FROZEN_EXCEPTION = ["half_2", "seq-3"]
# Excluded from full_scalar main-path list (still on official tree)
FULL_EXCLUDE = {"id_build", "half_2", "seq-3"}
# FMPA2-only tasks (not in sosy-lab/sv-benchmarks main); do not sync from FMPA2
FMPA2_LEGACY_REMOVED = [
    "as2013-hybrid",
    "bh2017-ex-add",
    "bh2017-ex1-poly",
    "bh2017-ex3",
    "hh2012-ex1b",
    "hh2012-ex2b",
    "hh2012-ex3",
    "mine2017-ex4.10",
    "mine2017-ex4.6",
    "mine2017-ex4.7",
    "mine2017-ex4.8",
]


def find_rel(task: str) -> str | None:
    for sub in (
        "loop-invgen",
        "loop-acceleration",
        "loop-crafted",
        "loops",
        "loop-lit",
        "loop-invariants",
        "loop-new",
        "loops-crafted",
    ):
        for ext in (".i", ".c"):
            p = BENCH / sub / f"{task}{ext}"
            if p.is_file():
                return f"{sub}/{task}{ext}"
    # Prefer .i (preprocessed) over .c when both exist
    for ext in (".i", ".c"):
        try:
            out = subprocess.run(
                ["find", str(BENCH), "-name", f"{task}{ext}", "-type", "f"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            hits = [h for h in out.stdout.strip().split("\n") if h]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            hits = []
        if len(hits) == 1:
            return str(Path(hits[0]).relative_to(BENCH))
        if len(hits) > 1:
            for h in sorted(hits):
                rel = str(Path(h).relative_to(BENCH))
                if rel.startswith("loop") or rel.startswith("loops"):
                    return rel
            return str(Path(hits[0]).relative_to(BENCH))
    return None


def load_classifier() -> tuple[dict[str, OrderedDict[str, dict]], Path | None]:
    by_cls: dict[str, OrderedDict[str, dict]] = {}
    path = CSV_PATH if CSV_PATH.is_file() else LEGACY_CSV
    if not path.is_file():
        print(f"WARN: missing {CSV_PATH} — run: run.sh bench-reclassify", file=sys.stderr)
        return by_cls, None
    with path.open() as f:
        for row in csv.DictReader(f):
            by_cls.setdefault(row["classification"], OrderedDict())[row["task"]] = row
    return by_cls, path


def write_list(name: str, rel_paths: list[str], header: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{name}.list"
    with path.open("w") as f:
        f.write(header + "\n")
        for rel in rel_paths:
            f.write(rel + "\n")
    print(f"  {name}.list: {len(rel_paths)} entries -> {path}")


def resolve_tasks(tasks: list[str]) -> tuple[list[str], list[str]]:
    ok, missing = [], []
    for t in tasks:
        rel = find_rel(t)
        if rel:
            ok.append(rel)
        else:
            missing.append(t)
    return ok, missing


def legacy_fmpa2_only_tasks() -> list[str]:
    """RUN_SCALAR in FMPA2 legacy CSV that are absent from official SV_BENCHMARKS tree."""
    if not LEGACY_CSV.is_file():
        return list(FMPA2_LEGACY_REMOVED)
    legacy_scalar: set[str] = set()
    with LEGACY_CSV.open() as f:
        for row in csv.DictReader(f):
            if row.get("classification") == "RUN_SCALAR":
                legacy_scalar.add(row["task"])
    gone = sorted(t for t in legacy_scalar if find_rel(t) is None)
    return gone


def write_excluded_legacy(removed: list[str]) -> None:
    path = OUT_DIR / "excluded_fmpa2_legacy.list"
    with path.open("w") as f:
        f.write("# Not in github.com/sosy-lab/sv-benchmarks (main); removed from full_scalar\n")
        f.write("# Do NOT copy from FMPA2; use bench-reclassify on ~/sv-benchmarks only\n")
        for t in removed:
            f.write(f"{t}\n")
    print(f"  excluded_fmpa2_legacy.list: {len(removed)} tasks -> {path}")


def main() -> int:
    if not BENCH.is_dir():
        print(f"ERROR: SV_BENCHMARKS not found: {BENCH}", file=sys.stderr)
        print("Run: scripts/vguided-cegar/setup_benchmarks.sh", file=sys.stderr)
        return 1

    by_cls, cls_src = load_classifier()
    report = OUT_DIR / "regen_report.txt"
    removed_fmpa2 = legacy_fmpa2_only_tasks()
    write_excluded_legacy(removed_fmpa2)

    lines = [
        f"SV_BENCHMARKS={BENCH}",
        f"classifier_csv={cls_src or 'NONE'}",
        f"programs under bench: {sum(1 for _ in BENCH.rglob('*.i'))} .i, "
        f"{sum(1 for _ in BENCH.rglob('*.c'))} .c",
        f"fmpa2_legacy_removed: {len(removed_fmpa2)} ({', '.join(removed_fmpa2[:5])}...)",
        "",
    ]

    # sample / rescue / frozen
    for setname, tasks in [
        ("sample", SAMPLE_TASKS),
        ("rescue_core", RESCUE_CORE),
        ("frozen_exception", FROZEN_EXCEPTION),
    ]:
        ok, miss = resolve_tasks(tasks)
        write_list(setname, ok, f"# {setname}: {len(ok)} tasks under {BENCH}")
        if miss:
            lines.append(f"{setname} missing: {miss}")

    for cls, setname in [
        ("RUN_SCALAR", "full_scalar"),
    ]:
        tasks = list(by_cls.get(cls, {}).keys())
        tasks = [t for t in tasks if t not in FULL_EXCLUDE]
        ok, miss = resolve_tasks(tasks)
        write_list(
            setname,
            ok,
            f"# {setname}: {cls} minus {sorted(FULL_EXCLUDE)}; {len(ok)}/{len(tasks)} resolved",
        )
        lines.extend(
            [
                f"{setname}: classifier tasks={len(tasks)} resolved={len(ok)} missing={len(miss)}",
                "",
            ]
        )
        if miss:
            miss_path = OUT_DIR / f"{setname}_missing.txt"
            miss_path.write_text("\n".join(miss) + "\n")
            print(f"  {setname}_missing.txt: {len(miss)} tasks (unexpected — run bench-reclassify)")
        elif (OUT_DIR / f"{setname}_missing.txt").is_file():
            (OUT_DIR / f"{setname}_missing.txt").unlink()

    report.write_text("\n".join(lines))
    print(f"Report: {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
