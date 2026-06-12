#!/usr/bin/env python3
"""Attribute SV-COMP portfolio verdicts to selection/restart/parallel components.

The parser is intentionally log-format tolerant: missing signals become "unknown" instead of
raising. It accepts either a single CPAchecker log or a directory containing logs.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

VERDICT_RE = re.compile(r"Verification result:\s*([A-Za-z]+)")
FINISHED_RE = re.compile(r"([^\s()]+\.properties) finished successfully\.")
PREFIX_PROP_RE = re.compile(r"(?:Analysis|Parallel analysis) ([^:)]+\.properties)")
LLM_ROUND_RE = re.compile(r"VGuide LLM round #")


def iter_logs(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.exists():
        raise SystemExit(f"input does not exist: {path}")
    logs = sorted(path.glob("*.log"))
    logs.extend(sorted(p for p in path.glob("*/cpa.log") if p.is_file()))
    logs.extend(sorted(p for p in path.glob("*/logs/*.log") if p.is_file()))
    if not logs:
        logs = sorted(path.rglob("*.log"))
    return logs


def task_name(log: Path) -> str:
    if log.name == "cpa.log":
        return log.parent.name
    return log.stem


def basename(path_text: str) -> str:
    return Path(path_text.strip("'\" ")).name


def selection_branch(text: str) -> str:
    basenames = {basename(m.group(1)) for m in PREFIX_PROP_RE.finditer(text)}
    joined = "\n".join(sorted(basenames))
    if "recursion.properties" in joined:
        # Recursion can be reached via a restart condition after loop-free selection; keep branch
        # attribution for top-level heuristic below if a more specific branch is also visible.
        pass
    if "singleLoopConfig.properties" in joined:
        return "single_loop"
    if "multipleLoopsConfig.properties" in joined:
        return "multiple_loops"
    if "configselection-restart-valueAnalysis-fallbacks.properties" in joined:
        return "complex_loop"
    if "configselection-restart-bmc-fallbacks.properties" in joined:
        return "loop_free"
    if "recursion.properties" in joined:
        return "recursion"
    if "concurrency.properties" in joined:
        return "concurrency"
    return "unknown"


def restart_stage(text: str) -> str:
    basenames = [basename(m.group(1)) for m in PREFIX_PROP_RE.finditer(text)]
    joined = "\n".join(basenames)
    # Prefer later/specific restart stages over the top-level selection wrapper.
    if "recursion.properties" in joined and "Ignoring restart configuration" not in joined:
        return "recursion"
    if "concurrency.properties" in joined and "Ignoring restart configuration" not in joined:
        return "concurrency"
    if "configselection-restartcomponent-predicateAnalysis-end.properties" in joined:
        return "predicate_end"
    if "configselection-singleconfig-bmc.properties" in joined:
        return "bmc"
    if "parallel-singleLoop.properties" in joined:
        return "parallel_single_loop"
    if "parallel-multipleLoops.properties" in joined:
        return "parallel_multiple_loops"
    if "configselection-restart-bmc-fallbacks.properties" in joined:
        return "bmc_fallbacks"
    if "configselection-restart-valueAnalysis-fallbacks.properties" in joined:
        return "value_fallbacks"
    return "unknown"


def deciding_component(text: str) -> str:
    matches = FINISHED_RE.findall(text)
    if matches:
        return basename(matches[-1])
    # Non-parallel/restart cases often lack the explicit ParallelAlgorithm success message.
    if "BAMPredicateCPA" in text and "recursion.properties" in text:
        return "svcomp27--recursion.properties"
    if "Verification result:" in text:
        stage = restart_stage(text)
        if stage != "unknown":
            return stage
    return "unknown"


def parse_log(log: Path) -> dict[str, str | int | bool]:
    text = log.read_text(errors="replace")
    verdict_match = VERDICT_RE.search(text)
    verdict = verdict_match.group(1).upper() if verdict_match else "unknown"
    llm_rounds = len(LLM_ROUND_RE.findall(text))
    vguide_fired = (
        "Unified VGuide CEGAR enabled" in text
        or "VGuide LLM round #" in text
        or "VGuide predicate" in text
        or "VGuide precision-injected" in text
    )
    return {
        "task": task_name(log),
        "verdict": verdict,
        "selection_branch": selection_branch(text),
        "restart_stage": restart_stage(text),
        "deciding_component": deciding_component(text),
        "vguide_fired": str(vguide_fired).lower(),
        "llm_rounds": llm_rounds,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="CPAchecker log file or directory of logs")
    parser.add_argument("--out", type=Path, help="CSV output path (default: stdout)")
    args = parser.parse_args(argv)

    logs = iter_logs(args.input)
    rows = [parse_log(log) for log in logs]
    fieldnames = [
        "task",
        "verdict",
        "selection_branch",
        "restart_stage",
        "deciding_component",
        "vguide_fired",
        "llm_rounds",
    ]
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    else:
        writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
