#!/usr/bin/env python3
"""Core-only evaluation helpers for the hard-case two-arm run (Issue #2).

- ``tasks_from_manifest``: emits one row per task (task, source path,
  expected verdict, data model, family, task/source sha256) after
  verifying the source files against the frozen manifest hashes.
- ``record_from_run``: builds the per-task record JSONL row from a CPA
  log (and the VGuide analysis dump for the augmented arm).
- ``config_sha256`` / ``commit_sha``: provenance hashes.

The manifest is the immutable authority (Hard-case Dataset v2 final
release); augmented outcomes must never alter it.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

SOLVER_RE = re.compile(r"Using predicate analysis with (\S+) version (\S+)")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tasks_from_manifest(manifest_path: Path, sv_benchmarks: Path, verify: bool = True):
    """Yield dicts of the frozen 224 tasks; verify source hashes by default."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tasks = manifest["tasks"]
    if manifest.get("task_count") is not None and len(tasks) != manifest["task_count"]:
        raise SystemExit(
            f"manifest task_count mismatch: declared {manifest['task_count']}, got {len(tasks)}"
        )
    rows = []
    for t in tasks:
        source = t["source_paths"][0]
        # Manifest paths carry the sv-benchmarks 'c/' prefix; SV_BENCHMARKS is the c/ root.
        source = source[2:] if source.startswith("c/") else source
        source_file = sv_benchmarks / source
        if verify:
            if not source_file.is_file():
                raise SystemExit(
                    f"source missing for {t['task']}: {source_file} (expected by manifest)"
                )
            got = sha256_file(source_file)
            expected = t["source_sha256"][0]
            if got != expected:
                raise SystemExit(
                    f"source hash mismatch for {t['task']}: got {got}, expected {expected}"
                )
        rows.append(
            {
                "task": t["task"],
                "source": source,
                "expected_verdict": t["expected_verdict"],
                "data_model": t.get("data_model", ""),
                "family": t.get("family", ""),
                "task_sha256": t["task_sha256"],
                "source_sha256": t["source_sha256"][0],
            }
        )
    return rows


def commit_sha(repo: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def record_from_run(
    task_row: dict,
    log: Path,
    dump_dir: Path,
    config_sha: str,
    commit: str,
    arm: str,
    timelimit: int,
    exit_code: int = 0,
) -> dict:
    """One JSONL record per task: hashes, commit, resource use, verdict, metrics."""
    result = ""
    refs = 0
    wall_s = 0.0
    cpu_s = 0.0
    memory_mb = ""
    solver = ""
    saw_result = False
    has_oom = has_hang = has_exc = has_cpu = False
    if log.is_file():
        # Single line-by-line pass: logs can be huge, never read them whole.
        with open(log, encoding="utf-8", errors="replace") as f:
            for line in f:
                if not saw_result and line.startswith("Verification result:"):
                    m = re.search(r"Verification result:\s*([A-Za-z]+)", line)
                    if m:
                        result = m.group(1).upper()
                        saw_result = True
                elif line.startswith("Number of predicate refinements:"):
                    m = re.search(r"Number of predicate refinements:\s*(\d+)", line)
                    if m:
                        refs = int(m.group(1))
                elif line.startswith("Total time for CPAchecker:"):
                    m = re.search(r"Total time for CPAchecker:\s*([0-9.]+)", line)
                    if m:
                        wall_s = float(m.group(1))
                elif line.startswith("Total CPU time for CPAchecker:"):
                    m = re.search(r"Total CPU time for CPAchecker:\s*([0-9.]+)", line)
                    if m:
                        cpu_s = float(m.group(1))
                elif line.startswith("Memory consumption for CPAchecker:"):
                    m = re.search(r"Memory consumption for CPAchecker:\s*([0-9.]+)\s*MB", line)
                    if m:
                        memory_mb = m.group(1)
                elif line.startswith("Using predicate analysis with"):
                    m = SOLVER_RE.search(line)
                    if m:
                        solver = f"{m.group(1)} {m.group(2)}"
                if "OutOfMemoryError" in line or "Out of memory" in line:
                    has_oom = True
                elif "forcing immediate termination" in line:
                    has_hang = True
                elif "Exception in thread" in line or re.search(
                    r"java\.lang\.\w*(Exception|Error)\b", line
                ):
                    has_exc = True
                elif "CPU-time limit of" in line:
                    has_cpu = True

    llm_calls = 0
    validated = 0
    injected = 0
    if dump_dir is not None and str(dump_dir) and dump_dir.is_dir():
        # VGuideAnalysisDumper writes <dump_dir>/tasks/<benchmark base name>/...
        # Locate by iteration so multi-extension benchmark names resolve robustly.
        task_dump = None
        tasks_root = dump_dir / "tasks"
        if tasks_root.is_dir():
            stem = Path(task_row["source"]).stem
            cand = tasks_root / stem
            if cand.is_dir():
                task_dump = cand
            else:
                for d in tasks_root.iterdir():
                    if d.is_dir() and d.name.startswith(stem + "."):
                        task_dump = d
                        break
        llm_file = (
            task_dump / "llm_rounds.jsonl" if task_dump is not None else dump_dir / "none"
        )
        if llm_file.is_file():
            with open(llm_file, encoding="utf-8", errors="replace") as f:
                llm_calls = sum(1 for _ in f)
        ref_file = (
            task_dump / "refinements.jsonl" if task_dump is not None else dump_dir / "none"
        )
        if ref_file.is_file():
            with open(ref_file, encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(row, dict):
                        continue
                    validated += len(row.get("validated_predicates") or [])
                    injected += len(row.get("precision_injected") or [])

    failure = "ok"
    if not log.is_file() or log.stat().st_size == 0:
        failure = "no_log"
    elif exit_code == 124:
        failure = "timeout"
    elif saw_result and result in ("TRUE", "FALSE"):
        failure = "ok"
    else:
        if has_oom:
            failure = "out_of_memory"
        elif has_hang:
            failure = "smt_hang"
        elif has_exc:
            failure = "crash"
        elif has_cpu or wall_s >= timelimit:
            failure = "timeout"
        else:
            failure = "incomplete"

    return {
        "task": task_row["task"],
        "source": task_row["source"],
        "property": "unreach-call",
        "expected_verdict": task_row["expected_verdict"],
        "data_model": task_row["data_model"],
        "family": task_row["family"],
        "task_sha256": task_row["task_sha256"],
        "source_sha256": task_row["source_sha256"],
        "arm": arm,
        "commit": commit,
        "config_sha256": config_sha,
        "solver": solver,
        "verdict": result,
        "refinements": refs,
        "wall_s": round(wall_s, 3),
        "cpu_s": round(cpu_s, 3),
        "memory_mb": memory_mb,
        "llm_calls": llm_calls,
        "validated_predicates": validated,
        "injected_predicates": injected,
        "failure_category": failure,
        "log": str(log),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_tasks = sub.add_parser("tasks", help="emit tasks.tsv rows from the frozen manifest")
    p_tasks.add_argument("--manifest", required=True, type=Path)
    p_tasks.add_argument("--sv-benchmarks", required=True, type=Path)
    p_tasks.add_argument("--no-verify", action="store_true")
    p_tasks.add_argument("--out", required=True, type=Path)
    p_record = sub.add_parser("record", help="emit one JSONL record from a CPA log")
    p_record.add_argument("--task-row", required=True, help="tab-separated tasks.tsv row")
    p_record.add_argument("--log", required=True, type=Path)
    p_record.add_argument("--dump-dir", type=Path, default=None)
    p_record.add_argument("--config-sha", required=True)
    p_record.add_argument("--commit", required=True)
    p_record.add_argument("--arm", required=True, choices=["stock", "augmented"])
    p_record.add_argument("--timelimit", type=int, default=300)
    p_record.add_argument("--exit-code", type=int, default=0)
    p_record.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    if args.cmd == "tasks":
        rows = tasks_from_manifest(
            args.manifest, args.sv_benchmarks, verify=not args.no_verify
        )
        with open(args.out, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(
                    "\t".join(
                        [
                            r["task"],
                            r["source"],
                            r["expected_verdict"],
                            r["data_model"],
                            r["family"],
                            r["task_sha256"],
                            r["source_sha256"],
                        ]
                    )
                    + "\n"
                )
        print(f"wrote {len(rows)} tasks to {args.out}")
        return 0

    if args.cmd == "record":
        header = [
            "task",
            "source",
            "expected_verdict",
            "data_model",
            "family",
            "task_sha256",
            "source_sha256",
        ]
        task_row = dict(zip(header, args.task_row.rstrip("\n").split("\t")))
        record = record_from_run(
            task_row,
            args.log,
            args.dump_dir,
            args.config_sha,
            args.commit,
            args.arm,
            args.timelimit,
            args.exit_code,
        )
        with open(args.out, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
