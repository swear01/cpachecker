#!/usr/bin/env python3
"""Harvest a paired core-only stock/augmented run against official labels."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def load_records(path: Path) -> dict[str, dict]:
    rows = []
    with open(path, encoding="utf-8", errors="replace") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise SystemExit(f"invalid JSON in {path}:{line_number}: {error}") from error
            if not isinstance(row, dict) or not isinstance(row.get("task"), str):
                raise SystemExit(f"record is not an object with a task in {path}:{line_number}")
            rows.append(row)
    result = {row["task"]: row for row in rows}
    if len(result) != len(rows):
        raise SystemExit(f"duplicate task records in {path}")
    return result


def load_task_list(path: Path) -> set[str]:
    return {
        line.split("\t", 1)[0].strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def decisive(row: dict) -> bool:
    return row.get("verdict") in {"TRUE", "FALSE"}


def official_correct(row: dict) -> bool:
    verdict = row.get("verdict")
    expected = str(row.get("expected_verdict")).lower()
    return (expected == "true" and verdict == "TRUE") or (
        expected == "false" and verdict == "FALSE"
    )


def par2(row: dict, timelimit: float, correct_only: bool = False) -> float:
    solved = official_correct(row) if correct_only else decisive(row)
    wall = row.get("wall_s")
    return float(wall) if solved and wall is not None else 2 * timelimit


def log_diagnostics(row: dict) -> dict:
    if all(key in row for key in ("provider_failures", "analysis_failure_messages", "crash_detail")):
        return {
            "provider_failures": row.get("provider_failures") or 0,
            "analysis_failure": bool(row.get("analysis_failure_messages")),
            "crash_detail": row.get("crash_detail") or "",
        }
    path = Path(row.get("log") or "")
    if not path.is_file():
        return {"provider_failures": 0, "analysis_failure": False, "crash_detail": ""}
    provider_failures = 0
    analysis_failure = False
    has_classpath = False
    has_symbol_conflict = False
    with open(path, encoding="utf-8", errors="replace") as stream:
        for line in stream:
            provider_failures += line.count("VGuide LLM call failed")
            if "Refinement failed:" in line:
                analysis_failure = True
            if "NoClassDefFoundError" in line or "ClassNotFoundException" in line:
                has_classpath = True
            if "symbol with name" in line and "already exists" in line:
                has_symbol_conflict = True
    if has_classpath:
        detail = "classpath"
    elif has_symbol_conflict:
        detail = "symbol_conflict"
    else:
        detail = ""
    return {
        "provider_failures": provider_failures,
        "analysis_failure": analysis_failure,
        "crash_detail": detail,
    }


def arm_summary(rows: dict[str, dict], tasks: set[str], timelimit: float) -> dict:
    cohort = [rows[task] for task in tasks]
    diagnostics = [log_diagnostics(row) for row in cohort]
    wrong = [row for row in cohort if decisive(row) and not official_correct(row)]
    denominator = len(cohort) or 1
    return {
        "records": len(cohort),
        "decisive": sum(decisive(row) for row in cohort),
        "official_correct": sum(official_correct(row) for row in cohort),
        "wrong": len(wrong),
        "verdicts": dict(Counter(row.get("verdict", "") for row in cohort)),
        "failure_categories": dict(Counter(row.get("failure_category", "") for row in cohort)),
        "provider_failures": sum(item["provider_failures"] for item in diagnostics),
        "analysis_failure_records": sum(item["analysis_failure"] for item in diagnostics),
        "symbol_conflict_records": sum(item["crash_detail"] == "symbol_conflict" for item in diagnostics),
        "llm_response_parse_failures": sum(row.get("llm_response_parse_failures") or 0 for row in cohort),
        "llm_empty_responses": sum(row.get("llm_empty_responses") or 0 for row in cohort),
        "par2_decisive_avg_s": sum(par2(row, timelimit) for row in cohort) / denominator,
        "par2_official_correct_avg_s": sum(par2(row, timelimit, True) for row in cohort) / denominator,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock-records", required=True, type=Path)
    parser.add_argument("--augmented-records", required=True, type=Path)
    parser.add_argument(
        "--exclude-tasks", type=Path,
        help="tasks excluded from the full paired cohort; absent tasks fail closed",
    )
    parser.add_argument("--official-label-conflicts", type=Path)
    parser.add_argument("--timelimit", type=float, default=300.0)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    stock = load_records(args.stock_records)
    augmented = load_records(args.augmented_records)
    if set(stock) != set(augmented):
        raise SystemExit("stock and augmented records do not contain the same tasks")
    excluded = load_task_list(args.exclude_tasks) if args.exclude_tasks else set()
    unknown = excluded - set(stock)
    if unknown:
        raise SystemExit("excluded tasks are absent from records: " + ", ".join(sorted(unknown)))
    tasks = set(stock) - excluded
    if not tasks:
        raise SystemExit("empty comparison cohort")

    conflicts = load_task_list(args.official_label_conflicts) if args.official_label_conflicts else set()
    new_correct = sorted(
        task for task in tasks if not official_correct(stock[task]) and official_correct(augmented[task])
    )
    lost_correct = sorted(
        task for task in tasks if official_correct(stock[task]) and not official_correct(augmented[task])
    )
    new_decisive = sorted(task for task in tasks if not decisive(stock[task]) and decisive(augmented[task]))
    lost_decisive = sorted(task for task in tasks if decisive(stock[task]) and not decisive(augmented[task]))

    result = {
        "cohort_size": len(tasks),
        "excluded_tasks": sorted(excluded),
        "official_label_conflicts_in_cohort": sorted(tasks & conflicts),
        "stock": arm_summary(stock, tasks, args.timelimit),
        "augmented": arm_summary(augmented, tasks, args.timelimit),
        "new_officially_correct": new_correct,
        "lost_officially_correct": lost_correct,
        "new_decisive": new_decisive,
        "lost_decisive": lost_decisive,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
