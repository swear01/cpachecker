#!/usr/bin/env python3
"""Harvest a manifest-exact exploratory pair, retaining failures and official wrongs.

Exit 1 means an integrity failure or a new augmentation-only wrong/disagreement.
No timing/PAR-2 claims: ordinary background load is permitted for exploration.
"""

import argparse
import json
import sys
from pathlib import Path

from check_core_only_smoke import load_disputes, summarize, validate, wrong_verdict


def official_correct(row):
    return (
        row.get("failure_category") == "ok"
        and row.get("verdict") in ("TRUE", "FALSE")
        and not wrong_verdict(row.get("expected_verdict"), row.get("verdict"))
    )


def harvest(paths, manifest, disputes=()):
    arms, errors = validate(paths, manifest)
    if set(arms) != {"stock", "augmented"}:
        errors.append("paired harvest requires exactly stock and augmented arms")
    result = {
        "integrity_ok": not errors,
        "errors": errors,
        "arms": {arm: summarize(rows, disputes) for arm, rows in arms.items()},
        "comparison_usable": False,
    }
    if errors:
        return result
    stock, augmented = (
        {r["task"]: r for r in arms[arm]} for arm in ("stock", "augmented")
    )
    new_wrong = sorted(
        task
        for task in stock
        if wrong_verdict(
            augmented[task]["expected_verdict"], augmented[task]["reported_verdict"]
        )
        and not wrong_verdict(
            stock[task]["expected_verdict"], stock[task]["reported_verdict"]
        )
    )
    result.update(
        cohort_size=len(stock),
        new_officially_correct=sorted(
            t
            for t in stock
            if not official_correct(stock[t]) and official_correct(augmented[t])
        ),
        lost_officially_correct=sorted(
            t
            for t in stock
            if official_correct(stock[t]) and not official_correct(augmented[t])
        ),
        augmentation_only_wrong_tasks=new_wrong,
        comparison_usable=not new_wrong,
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock-records", required=True, type=Path)
    parser.add_argument("--augmented-records", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--official-label-conflicts", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = harvest(
            [args.stock_records, args.augmented_records],
            args.manifest,
            load_disputes(args.official_label_conflicts),
        )
    except (ValueError, OSError, KeyError, TypeError) as error:
        result = {
            "integrity_ok": False,
            "comparison_usable": False,
            "errors": [str(error)],
        }
    # A report is a new artifact; never overwrite a frozen result.
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(result, indent=2))
    return 0 if result["comparison_usable"] else 1


if __name__ == "__main__":
    sys.exit(main())
