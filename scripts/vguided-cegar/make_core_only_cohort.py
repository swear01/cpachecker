#!/usr/bin/env python3
"""Create an ordered core-only cohort by excluding annotated tasks."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path


def load_exclusions(path: Path) -> tuple[list[str], str]:
    raw = path.read_bytes()
    tasks = []
    for line in raw.decode("utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        tasks.append(line.split("\t", 1)[0].strip())
    if len(tasks) != len(set(tasks)):
        raise SystemExit(f"duplicate exclusion in {path}")
    return tasks, hashlib.sha256(raw).hexdigest()


def make_cohort(manifest_path: Path, exclusions_path: Path, limit: int | None = None) -> dict:
    raw_manifest = manifest_path.read_bytes()
    manifest = json.loads(raw_manifest.decode("utf-8-sig"))
    if not isinstance(manifest, dict):
        raise SystemExit("manifest is not a JSON object")
    tasks = manifest.get("tasks")
    if not isinstance(tasks, list):
        raise SystemExit("manifest has no tasks list")
    for task in tasks:
        if not isinstance(task, dict) or not isinstance(task.get("task"), str):
            raise SystemExit(
                "manifest task must be an object with a string 'task' key: " + repr(task)
            )
    task_ids = [task["task"] for task in tasks]
    if len(task_ids) != len(set(task_ids)):
        raise SystemExit("manifest contains duplicate task IDs")
    exclusions, exclusion_sha256 = load_exclusions(exclusions_path)
    available = {task.get("task") for task in tasks}
    unknown = sorted(set(exclusions) - available)
    if unknown:
        raise SystemExit("excluded tasks are not in manifest: " + ", ".join(unknown))
    excluded = set(exclusions)
    result = copy.deepcopy(manifest)
    result["tasks"] = [task for task in result["tasks"] if task.get("task") not in excluded]
    if limit is not None:
        if limit <= 0:
            raise SystemExit("limit must be positive")
        result["tasks"] = result["tasks"][:limit]
    result["task_count"] = len(result["tasks"])
    result["parent_manifest_sha256"] = hashlib.sha256(raw_manifest).hexdigest()
    result["cohort_exclusion_file_sha256"] = exclusion_sha256
    result["excluded_tasks"] = exclusions
    if limit is not None:
        result["cohort_limit"] = limit
    result["selection_rule"] = (
        f"{manifest.get('selection_rule', 'frozen manifest')} minus {len(exclusions)} tasks"
        + (f", limited to {limit}" if limit is not None else "")
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument(
        "--exclude", required=True, type=Path,
        help="complete exclusion list; unknown tasks fail closed",
    )
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    cohort = make_cohort(args.manifest, args.exclude, args.limit)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(cohort, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {cohort['task_count']} tasks to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
