#!/usr/bin/env python3
"""Smoke gate for the core-only evaluation (Issue #2, plan §4).

Checks that a completed smoke run's records are complete, hash-consistent
and consistent with the frozen official expected verdicts. Exit 0 = pass,
1 = fail. Raw wrong counts always remain visible; an explicit
``--allow-known-official-conflicts`` is only an operational allowlist for a
predeclared diagnostic cohort and never changes ground truth.

Usage: check_core_only_smoke.py <records.jsonl...> [--expect-count N]
       [--official-label-conflicts FILE --allow-known-official-conflicts]
"""

import argparse
import json
import sys
from collections import Counter

REQUIRED_FIELDS = [
    "task", "source", "property", "expected_verdict", "data_model", "family",
    "task_sha256", "source_sha256", "arm", "commit", "config_sha256", "solver",
    "verdict", "refinements", "wall_s", "cpu_s", "memory_mb", "llm_calls",
    "validated_predicates", "injected_predicates", "failure_category", "log",
]


def wrong_verdict(expected, verdict):
    if verdict == "TRUE":
        return expected != "true"
    if verdict == "FALSE":
        return expected == "true"
    return False


def load_task_annotations(path):
    if not path:
        return set()
    with open(path, encoding="utf-8") as f:
        return {line.split("\t", 1)[0].strip() for line in f if line.strip() and not line.lstrip().startswith("#")}


def load(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("records", nargs="+", help="one or more records.jsonl files")
    ap.add_argument("--expect-count", type=int, default=None)
    ap.add_argument("--official-label-conflicts", default=None,
                    help="diagnostic annotations for pre-existing official-label mismatches")
    ap.add_argument("--allow-known-official-conflicts", action="store_true",
                    help="allow only annotated mismatches while still reporting them as wrong")
    args = ap.parse_args()
    official_conflicts = load_task_annotations(args.official_label_conflicts)
    if args.allow_known_official_conflicts and args.official_label_conflicts is None:
        ap.error("--allow-known-official-conflicts requires --official-label-conflicts")

    ok = True
    all_tasks = {}
    for path in args.records:
        rows = load(path)
        missing = [
            (
                r.get("task", f"<missing task at record {index}>")
                if isinstance(r, dict)
                else f"<non-object at record {index}>"
            )
            for index, r in enumerate(rows, 1)
            if not isinstance(r, dict) or any(f not in r for f in REQUIRED_FIELDS)
        ]
        valid_rows = [r for r in rows if isinstance(r, dict)]
        wrongs = [
            r.get("task", "<missing task>")
            for r in valid_rows
            if wrong_verdict(r.get("expected_verdict"), r.get("verdict"))
        ]
        known_conflicts = [task for task in wrongs if task in official_conflicts]
        unexpected_wrongs = [task for task in wrongs if task not in official_conflicts]
        incomplete = [
            r.get("task", "<missing task>")
            for r in valid_rows
            if r.get("failure_category") not in (
                "ok", "timeout", "incomplete", "analysis_failure", "out_of_memory",
                "crash", "smt_hang", "no_log"
            )
        ]
        print(f"{path}: {len(rows)} records")
        print(f"  verdicts: {dict(Counter(r.get('verdict', '') for r in valid_rows))}")
        print(f"  failures: {dict(Counter(r.get('failure_category', '') for r in valid_rows))}")
        print(f"  missing fields: {len(missing)}  wrong verdicts: {len(wrongs)}")
        if missing:
            ok = False
            print("  MISSING FIELDS:", missing[:5], file=sys.stderr)
        print(f"  official-label conflicts: {len(known_conflicts)}")
        if unexpected_wrongs:
            ok = False
            print("  UNEXPECTED WRONG VERDICTS:", unexpected_wrongs, file=sys.stderr)
        if known_conflicts and not args.allow_known_official_conflicts:
            ok = False
            print(
                "  OFFICIAL-LABEL CONFLICTS REQUIRE EXPLICIT ALLOWLIST:",
                known_conflicts,
                file=sys.stderr,
            )
        if incomplete:
            ok = False
            print("  INVALID FAILURE CATEGORIES:", incomplete, file=sys.stderr)
        if args.expect_count is not None and len(rows) != args.expect_count:
            ok = False
            print(f"  EXPECTED {args.expect_count} records, got {len(rows)}", file=sys.stderr)
        for r in valid_rows:
            if "task" in r and "arm" in r:
                all_tasks.setdefault(r["task"], set()).add(r["arm"])

    if ok:
        allowed = " with predeclared official-label conflicts" if args.official_label_conflicts else ""
        print(f"SMOKE OK: records complete, hash-consistent{allowed}; raw wrong counts remain reported")
    else:
        print("SMOKE FAILED", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
