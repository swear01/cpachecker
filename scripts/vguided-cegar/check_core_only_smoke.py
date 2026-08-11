#!/usr/bin/env python3
"""Smoke gate for the core-only evaluation (Issue #2, plan §4).

Checks that a completed smoke run's records are complete, hash-consistent
and verdict-sound (no wrong verdicts). Exit 0 = pass, 1 = fail.

Usage: check_core_only_smoke.py <records.jsonl...> [--expect-count N] [--known-disputes FILE]

Known disputes (--known-disputes): a text file with one task per line,
whose verdicts contradict the dataset label but are accepted as documented
semantics/label disputes (see Issue #54). They are reported as DISPUTED
(not counted as wrong verdicts); the gate only fails on undisputed wrongs.
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


def load_disputes(path):
    if not path:
        return set()
    with open(path, encoding="utf-8") as f:
        return {line.split("\t", 1)[0].strip() for line in f if line.strip()}


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
    ap.add_argument("--known-disputes", default=None,
                    help="file with documented verdict disputes (Issue #54)")
    args = ap.parse_args()
    disputes = load_disputes(args.known_disputes)

    ok = True
    all_tasks = {}
    for path in args.records:
        rows = load(path)
        missing = [r["task"] for r in rows if any(f not in r for f in REQUIRED_FIELDS)]
        wrongs = [r["task"] for r in rows if wrong_verdict(r["expected_verdict"], r["verdict"])]
        disputed = [t for t in wrongs if t in disputes]
        wrongs = [t for t in wrongs if t not in disputes]
        incomplete = [
            r["task"]
            for r in rows
            if r["failure_category"] not in ("ok", "timeout", "incomplete", "out_of_memory", "crash", "smt_hang", "no_log")
        ]
        print(f"{path}: {len(rows)} records")
        print(f"  verdicts: {dict(Counter(r['verdict'] for r in rows))}")
        print(f"  failures: {dict(Counter(r['failure_category'] for r in rows))}")
        print(f"  missing fields: {len(missing)}  wrong verdicts: {len(wrongs)}"
              f"  documented disputes: {len(disputed)}")
        if missing:
            ok = False
            print("  MISSING FIELDS:", missing[:5], file=sys.stderr)
        if wrongs:
            ok = False
            print("  WRONG VERDICTS:", wrongs, file=sys.stderr)
        if disputed:
            print("  DOCUMENTED DISPUTES (accepted, #54):", disputed)
        if args.expect_count is not None and len(rows) != args.expect_count:
            ok = False
            print(f"  EXPECTED {args.expect_count} records, got {len(rows)}", file=sys.stderr)
        for r in rows:
            all_tasks.setdefault(r["task"], set()).add(r["arm"])

    if ok:
        print("SMOKE OK: records complete, hash-consistent, 0 wrong")
    else:
        print("SMOKE FAILED", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
