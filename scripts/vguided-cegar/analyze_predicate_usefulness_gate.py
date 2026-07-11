#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

PEEL = re.compile(
    r"VGuide peel: refinement #(\d+) loopHeadVisits=(\d+) traceLen=(\d+)"
)


@dataclass(frozen=True)
class FirstCallFeatures:
    loop_head_visits: int
    unique_multiplicative_predicates: int


@dataclass(frozen=True)
class GateSimulation:
    tasks: int
    original_solved: int
    gated_solved: int
    original_lost: int
    gated_lost: int
    rejected: int
    rescued: int
    sacrificed_wins: int
    gated_par2_s: float


def parse_first_call(text: str) -> FirstCallFeatures | None:
    round_start = text.find("VGuide LLM round")
    if round_start < 0:
        return None
    peel = PEEL.findall(text[:round_start])
    if not peel:
        return None
    injection = text.find("VGuide precision-injected", round_start)
    block = text[round_start : injection if injection >= 0 else None]
    predicates = {
        line.strip()
        for line in block.splitlines()
        if "VGuide predicate  " in line and "bvmul" in line
    }
    return FirstCallFeatures(
        loop_head_visits=int(peel[-1][1]),
        unique_multiplicative_predicates=len(predicates),
    )


def should_reject(features: FirstCallFeatures) -> bool:
    return (
        features.loop_head_visits <= 8
        and features.unique_multiplicative_predicates >= 2
    )


def load_summary(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="") as file:
        return {row["task"]: row for row in csv.DictReader(file)}


def simulate(
    stock: Mapping[str, Mapping[str, str]],
    vguide: Mapping[str, Mapping[str, str]],
    logs: Path,
    timelimit: float,
) -> GateSimulation:
    if stock.keys() != vguide.keys():
        raise ValueError("stock and VGuide summaries contain different tasks")

    def solved(row: Mapping[str, str]) -> bool:
        return row["result"] in {"TRUE", "FALSE"}

    rejected: set[str] = set()
    for task in stock:
        log = logs / f"{task}.log"
        if not log.is_file():
            continue
        features = parse_first_call(log.read_text(errors="replace"))
        if features is not None and should_reject(features):
            rejected.add(task)

    chosen = {
        task: stock[task] if task in rejected else vguide[task] for task in stock
    }
    original_lost = sum(
        solved(stock[task]) and not solved(vguide[task]) for task in stock
    )
    gated_lost = sum(
        solved(stock[task]) and not solved(chosen[task]) for task in stock
    )
    rescued = sum(
        task in rejected and solved(stock[task]) and not solved(vguide[task])
        for task in stock
    )
    sacrificed = sum(
        task in rejected and not solved(stock[task]) and solved(vguide[task])
        for task in stock
    )
    par2 = sum(
        float(row["wall_s"]) if solved(row) else 2 * timelimit
        for row in chosen.values()
    ) / len(chosen)
    return GateSimulation(
        tasks=len(stock),
        original_solved=sum(solved(row) for row in vguide.values()),
        gated_solved=sum(solved(row) for row in chosen.values()),
        original_lost=original_lost,
        gated_lost=gated_lost,
        rejected=len(rejected),
        rescued=rescued,
        sacrificed_wins=sacrificed,
        gated_par2_s=par2,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stock-summary", type=Path, required=True)
    parser.add_argument("--vguide-summary", type=Path, required=True)
    parser.add_argument("--vguide-logs", type=Path, required=True)
    parser.add_argument("--timelimit", type=float, default=300)
    args = parser.parse_args()
    result = simulate(
        load_summary(args.stock_summary),
        load_summary(args.vguide_summary),
        args.vguide_logs,
        args.timelimit,
    )
    print(json.dumps(asdict(result), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
