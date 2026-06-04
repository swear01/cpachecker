#!/usr/bin/env python3
"""Compare VGuide batch logs vs a baseline (same config, no LLM).

Preferred baseline: local stock batch logs (--baseline-logs), e.g.:

  ./run.sh cpa --set full_scalar --mode stock --parallel 8 --timelimit 300 \\
    --out output/vguide/experiments/full_scalar_stock_interval15

Legacy optional: FMPA2 BenchExec predicate-abstraction @300s (--baseline fmpa2).

Buckets: TRUE / FALSE / INCOMPLETE (UNKNOWN, ERROR, missing → INCOMPLETE).

Usage:
  python3 compare_official_reference.py \\
    --vguide-logs output/vguide/experiments/full_scalar_vguide_interval15/logs \\
    --baseline-logs output/vguide/experiments/full_scalar_stock_interval15/logs \\
    --manifest docs/vguided-cegar/benchmark_sets/full_scalar.list
"""
from __future__ import annotations

import argparse
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path


def load_manifest(path: Path) -> list[str]:
    tasks = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        tasks.append(Path(line).stem)
    return tasks


def load_fmpa2_predicate_results(path: Path) -> dict[str, str]:
    text = path.read_text()
    m = re.search(r"^predicate-abstraction\n", text, re.M)
    if not m:
        raise SystemExit(f"No predicate-abstraction section in {path}")
    rest = text[m.start() :]
    m2 = re.search(r"^k-induction\n", rest, re.M)
    section = rest[: m2.start()] if m2 else rest
    out: dict[str, str] = {}
    for line in section.splitlines():
        parts = line.split()
        if len(parts) < 2 or not parts[0].endswith((".yml", ".i", ".c")):
            continue
        out[Path(parts[0]).stem] = parts[1]
    return out


def load_svcomp_xml(path: Path) -> dict[str, str]:
    root = ET.parse(path).getroot()
    ns = {
        "r": "https://gitlab.com/sosy-lab/benchexec/tree/HEAD/src/org/sosy_lab/benchexec/results/result.xsd"
    }
    out: dict[str, str] = {}
    for run in root.findall(".//r:run", ns):
        name = run.get("name", "")
        task = Path(name).stem
        status = run.find("r:status", ns)
        if status is not None and status.text:
            out[task] = status.text.strip()
    return out


def parse_cpa_log(path: Path) -> tuple[str, int, int]:
    text = path.read_text(errors="replace")
    m = re.search(r"Verification result:\s*(\w+)", text)
    res = m.group(1).upper() if m else "UNKNOWN"
    m2 = re.search(r"Number of predicate refinements:\s*(\d+)", text)
    refs = int(m2.group(1)) if m2 else 0
    llm = len(re.findall(r"VGuide LLM round #", text))
    if "IllegalArgumentException" in text or "Exception in thread" in text:
        if res == "UNKNOWN" and not m:
            res = "ERROR"
    return res, refs, llm


def bucket(status: str) -> str:
    s = status.lower()
    if s == "true":
        return "TRUE"
    if s == "false":
        return "FALSE"
    return "INCOMPLETE"


def score(b: str) -> int:
    return {"TRUE": 3, "FALSE": 2, "INCOMPLETE": 1}.get(b, 0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vguide-logs", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument(
        "--baseline",
        choices=("stock", "fmpa2", "svcomp-xml"),
        default="stock",
        help="stock=--baseline-logs (default); fmpa2/svcomp-xml=legacy external tables",
    )
    ap.add_argument(
        "--baseline-logs",
        type=Path,
        default=Path("output/vguide/experiments/full_scalar_stock_interval15/logs"),
        help="CPA logs for stock baseline (same --config, useVocabularyGuide=false)",
    )
    ap.add_argument(
        "--baseline-txt",
        type=Path,
        default=Path(
            "/home/swear01/FMPA2/part2/results/20260421-231129/"
            "pa2_reachsafety_light.2026-04-21_23-11-30.results.txt"
        ),
    )
    ap.add_argument("--svcomp-xml", type=Path, default=None)
    args = ap.parse_args()

    tasks = load_manifest(args.manifest)
    baseline_kind = args.baseline
    if baseline_kind == "stock":
        baseline_name = f"local stock logs ({args.baseline_logs})"
    elif baseline_kind == "svcomp-xml":
        if not args.svcomp_xml:
            raise SystemExit("--baseline svcomp-xml requires --svcomp-xml PATH")
        baseline_name = f"SV-COMP XML {args.svcomp_xml.name}"
    else:
        baseline_name = f"FMPA2 predicate-abstraction @300s ({args.baseline_txt.name})"

    rows = []
    for task in tasks:
        vg_log = args.vguide_logs / f"{task}.log"
        if not vg_log.is_file():
            continue

        if baseline_kind == "stock":
            bl_log = args.baseline_logs / f"{task}.log"
            if not bl_log.is_file():
                continue
            bl_res, bl_refs, _ = parse_cpa_log(bl_log)
            bl_raw = bl_res
        elif baseline_kind == "svcomp-xml":
            baseline = load_svcomp_xml(args.svcomp_xml)
            if task not in baseline:
                continue
            bl_raw = baseline[task]
            bl_res = bl_raw
            bl_refs = 0
        else:
            baseline = load_fmpa2_predicate_results(args.baseline_txt)
            if task not in baseline:
                continue
            bl_raw = baseline[task]
            bl_res = bl_raw
            bl_refs = 0

        vg_res, vg_refs, vg_llm = parse_cpa_log(vg_log)
        rows.append(
            {
                "task": task,
                "baseline": bl_raw,
                "vguide": vg_res,
                "b_bucket": bucket(bl_res),
                "v_bucket": bucket(vg_res),
                "b_refs": bl_refs,
                "refs": vg_refs,
                "llm": vg_llm,
            }
        )

    print(f"Baseline: {baseline_name}")
    print(f"VGuide logs: {args.vguide_logs} ({len(list(args.vguide_logs.glob('*.log')))} files)")
    if baseline_kind == "stock":
        print(
            f"Baseline logs: {args.baseline_logs} "
            f"({len(list(args.baseline_logs.glob('*.log')))} files)"
        )
    print(f"Compared tasks: {len(rows)} / {len(tasks)} manifest\n")

    bc = Counter(r["b_bucket"] for r in rows)
    vc = Counter(r["v_bucket"] for r in rows)
    print("Baseline buckets:", dict(bc))
    print("VGuide buckets:    ", dict(vc))

    imp = deg = same = 0
    improved, degraded = [], []
    for r in rows:
        bs, vs = score(r["b_bucket"]), score(r["v_bucket"])
        if vs > bs:
            imp += 1
            improved.append(r)
        elif vs < bs:
            deg += 1
            degraded.append(r)
        else:
            same += 1

    print(f"\nOutcome vs baseline: improved={imp} same={same} degraded={deg}")
    if improved:
        print("\nImproved (first 20):")
        for r in improved[:20]:
            print(
                f"  {r['task']}: {r['baseline']} -> {r['vguide']} "
                f"(base_refs={r['b_refs']}, vg_refs={r['refs']}, llm={r['llm']})"
            )
    if degraded:
        print("\nDegraded:")
        for r in degraded:
            print(
                f"  {r['task']}: {r['baseline']} -> {r['vguide']} "
                f"(base_refs={r['b_refs']}, vg_refs={r['refs']})"
            )


if __name__ == "__main__":
    main()
