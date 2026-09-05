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

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

SOLVER_RE = re.compile(r"Using predicate analysis with (\S+) version (\S+)")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    manifest = json.loads(raw)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("tasks"), list):
        raise TypeError("manifest must contain a tasks list")
    tasks = manifest["tasks"]
    if not tasks or manifest.get("task_count", len(tasks)) != len(tasks):
        raise ValueError("empty manifest or task_count mismatch")
    seen = set()
    for task in tasks:
        if not isinstance(task, dict):
            raise TypeError("manifest task must be an object")
        name = task.get("task")
        if not isinstance(name, str) or not name or name in seen:
            raise ValueError(f"invalid/duplicate manifest task: {name!r}")
        seen.add(name)
        if str(task.get("expected_verdict")).lower() not in ("true", "false"):
            raise ValueError(f"invalid expected label: {name}")
        if task.get("data_model") not in ("ILP32", "LP64"):
            raise ValueError(f"invalid data model: {name}")
        sources, hashes = task.get("source_paths"), task.get("source_sha256")
        if (
            not isinstance(sources, list)
            or len(sources) != 1
            or not isinstance(hashes, list)
            or len(hashes) != 1
        ):
            raise ValueError(f"expected exactly one source/hash: {name}")
        for filename in (name, sources[0]):
            if (
                not isinstance(filename, str)
                or Path(filename).is_absolute()
                or ".." in Path(filename).parts
                or any(c in filename for c in "\t\n\r")
            ):
                raise ValueError(f"unsafe manifest path: {filename!r}")
        for value in (task.get("task_sha256"), hashes[0]):
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
                raise ValueError(f"invalid hash: {name}")
    return manifest, hashlib.sha256(raw).hexdigest()


def manifest_rows(manifest):
    return [
        {
            "task": task["task"],
            "source": task["source_paths"][0].removeprefix("c/"),
            "expected_verdict": str(task["expected_verdict"]).lower(),
            "data_model": task["data_model"],
            "family": task.get("family", ""),
            "task_sha256": task["task_sha256"],
            "source_sha256": task["source_sha256"][0],
        }
        for task in manifest["tasks"]
    ]


def tasks_from_manifest(manifest_path: Path, sv_benchmarks: Path, verify: bool = True):
    """Verify task YAML and source bytes against the frozen manifest."""
    manifest, _ = load_manifest(manifest_path)
    rows = manifest_rows(manifest)
    for task in manifest["tasks"]:
        source = task["source_paths"][0].removeprefix("c/")
        if verify:
            for relative, expected in (
                (source, task["source_sha256"][0]),
                (task["task"].removeprefix("c/"), task["task_sha256"]),
            ):
                path = sv_benchmarks / relative
                if not path.is_file() or sha256_file(path) != expected:
                    raise SystemExit(
                        f"missing file or hash mismatch for {task['task']}: {path}"
                    )
    return rows


def commit_sha(repo: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def runtime_identity(repo: Path) -> dict:
    """Fingerprint existing runtime bytes; never build or redirect another checkout."""
    repo = repo.resolve()
    if (
        os.environ.get("CLASSPATH")
        or os.environ.get("JAVA_TOOL_OPTIONS")
        or os.environ.get("JDK_JAVA_OPTIONS")
    ):
        raise ValueError(
            "external classpath/JVM options need a separately frozen runtime"
        )
    if (
        os.environ.get("PATH_TO_CPACHECKER")
        and Path(os.environ["PATH_TO_CPACHECKER"]).resolve() != repo
    ):
        raise ValueError("PATH_TO_CPACHECKER redirects this isolated runtime")
    if (
        not (repo / "classes/org/sosy_lab/cpachecker/cmdline/CPAMain.class").is_file()
        and not (repo / "cpachecker.jar").is_file()
    ):
        raise ValueError("no built CPAchecker runtime; build an isolated runtime first")
    paths = [repo / "scripts/cpa.sh", repo / "bin/cpachecker"]
    paths += [p for p in (repo / "classes").rglob("*") if p.is_file()]
    paths += [p for p in (repo / "lib").rglob("*") if p.is_file()]
    if (repo / "cpachecker.jar").is_file():
        paths.append(repo / "cpachecker.jar")
    java = os.environ.get("JAVA")
    if not java:
        java = next(
            (
                str(p)
                for p in sorted(Path("/usr/lib/jvm").glob("java-21-openjdk-*/bin/java"))
                if os.access(p, os.X_OK)
            ),
            "java",
        )
    executable = shutil.which(java)
    if executable is None:
        raise ValueError(f"Java executable missing: {java}")
    java_path = Path(executable).resolve()
    paths.append(java_path)
    for relative in ("release", "lib/modules", "lib/server/libjvm.so"):
        path = java_path.parent.parent / relative
        if path.is_file():
            paths.append(path)
    files = {str(p): sha256_file(p) for p in sorted(set(paths))}
    return {
        "runtime_files": files,
        "runtime_sha256": hashlib.sha256(
            json.dumps(files, sort_keys=True).encode()
        ).hexdigest(),
    }


def capture_run(command: list[str], log: Path, status: Path, wall_limit: float) -> dict:
    """Capture an actual process outcome without writing synthetic verifier output."""
    if status.exists():
        raise FileExistsError(status)
    started = time.monotonic()
    outcome = {
        "command": command,
        "exit_code": None,
        "signal": None,
        "termination_reason": "exit",
        "launch_error": None,
    }
    with log.open("xb") as stream:
        try:
            proc = subprocess.Popen(
                command, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True
            )
        except OSError as error:
            outcome.update(termination_reason="launch_error", launch_error=str(error))
        else:
            try:
                proc.wait(timeout=wall_limit)
            except subprocess.TimeoutExpired:
                outcome["termination_reason"] = "wall_timeout"
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    proc.wait()
            outcome["exit_code"] = proc.returncode
            outcome["signal"] = -proc.returncode if proc.returncode < 0 else None
    outcome["raw_wall_s"] = time.monotonic() - started
    outcome["log_sha256"] = sha256_file(log)
    with status.open("x", encoding="utf-8") as stream:
        json.dump(outcome, stream)
        stream.write("\n")
    return outcome


def dump_metrics(task_row: dict, dump_dir: Path | None, arm: str) -> dict:
    metrics = {
        "llm_calls": None,
        "validated_predicates": None,
        "injected_predicates": None,
        "llm_response_parse_failures": None,
        "llm_empty_responses": None,
        "dump_status": "missing",
        "dump_parse_errors": [],
        "dump_files": {},
    }
    if arm == "stock":
        metrics.update(
            {
                key: 0
                for key in metrics
                if key not in {"dump_status", "dump_parse_errors", "dump_files"}
            }
        )
        metrics["dump_status"] = "not_applicable"
        return metrics
    if dump_dir is None or not (dump_dir / "tasks").is_dir():
        return metrics
    stem = Path(task_row["source"]).stem
    candidates = sorted(
        p
        for p in (dump_dir / "tasks").iterdir()
        if p.is_dir()
        and (p.name == stem or re.fullmatch(re.escape(stem) + r"__b[0-9]+", p.name))
    )
    if not candidates:
        return metrics
    # Multiple bridge dumps are all evidence; never choose the first match silently.
    llm_rows, ref_rows, summaries = [], [], []
    seen_llm = seen_ref = False
    metrics["dump_files"] = {
        str(p): sha256_file(p) for p in sorted(dump_dir.rglob("*")) if p.is_file()
    }
    for task_dump in candidates:
        summary = task_dump / "task_summary.json"
        if summary.is_file():
            try:
                value = json.loads(summary.read_text(encoding="utf-8"))
                if not isinstance(value, dict) or any(
                    type(value.get(k)) is not int or value[k] < 0
                    for k in ("refinements", "llm_api_calls")
                ):
                    raise ValueError(
                        "task_summary needs nonnegative refinements/llm_api_calls"
                    )
                summaries.append(value)
            except (ValueError, TypeError, UnicodeError) as error:
                metrics["dump_parse_errors"].append(
                    {"file": str(summary), "line": None, "reason": str(error)}
                )
        for filename, target in (
            ("llm_rounds.jsonl", llm_rows),
            ("refinements.jsonl", ref_rows),
        ):
            path = task_dump / filename
            if not path.is_file():
                continue
            seen_llm |= filename == "llm_rounds.jsonl"
            seen_ref |= filename == "refinements.jsonl"
            metrics["dump_files"][str(path)] = sha256_file(path)
            with path.open("rb") as stream:
                for number, line in enumerate(stream, 1):
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                        if not isinstance(row, dict):
                            raise TypeError("expected JSON object")
                        if filename == "refinements.jsonl":
                            for key in ("validated_predicates", "precision_injected"):
                                if key not in row and row.get("llm_called") is False:
                                    row[key] = []
                                if not isinstance(row.get(key), list):
                                    raise TypeError(
                                        f"{key} must be a list when LLM was called"
                                    )
                        target.append(row)
                    except (ValueError, TypeError, UnicodeError) as error:
                        metrics["dump_parse_errors"].append(
                            {"file": str(path), "line": number, "reason": str(error)}
                        )
    complete = len(summaries) == len(candidates)
    metrics["dump_status"] = "present" if complete else "partial"
    if complete:
        calls = sum(r["llm_api_calls"] for r in summaries)
        if calls != len(llm_rows):
            metrics["dump_parse_errors"].append(
                {
                    "file": str(dump_dir),
                    "line": None,
                    "reason": "LLM call count does not match task summaries",
                }
            )
        if calls == 0 and not seen_llm:
            metrics.update(
                llm_calls=0, llm_response_parse_failures=0, llm_empty_responses=0
            )
        if not seen_ref and all(r["refinements"] == 0 for r in summaries):
            metrics.update(validated_predicates=0, injected_predicates=0)
        elif not seen_ref:
            metrics["dump_status"] = "missing"
    if metrics["dump_parse_errors"]:
        metrics["dump_status"] = "malformed"
        return metrics
    if seen_llm:
        metrics.update(
            llm_calls=len(llm_rows),
            llm_response_parse_failures=(
                sum(r["response_parse_ok"] is False for r in llm_rows)
                if all(type(r.get("response_parse_ok")) is bool for r in llm_rows)
                else None
            ),
            llm_empty_responses=(
                sum(r["response_raw"] == "" for r in llm_rows)
                if all(isinstance(r.get("response_raw"), str) for r in llm_rows)
                else None
            ),
        )
    if seen_ref:
        metrics.update(
            validated_predicates=sum(len(r["validated_predicates"]) for r in ref_rows),
            injected_predicates=sum(len(r["precision_injected"]) for r in ref_rows),
        )
    return metrics


def record_from_run(
    task_row: dict,
    log: Path,
    dump_dir: Path | None,
    config_sha: str,
    commit: str,
    arm: str,
    timelimit: int,
    exit_code: int = 0,
    execution: dict | None = None,
    run_meta: dict | None = None,
) -> dict:
    """Keep reported verdict, failure cause and missing measurements separate."""
    log = log.resolve()
    dump_dir = dump_dir.resolve() if dump_dir else None
    result = ""
    refs = wall_s = cpu_s = memory_mb = None
    solver = ""
    has_oom = has_hang = has_exc = has_cpu = has_wall = has_native = False
    provider_failures = analysis_failures = 0
    if log.is_file():
        with log.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                if line.startswith("Verification result:"):
                    match = re.search(
                        r"Verification result:\s*(TRUE|FALSE|UNKNOWN)\b", line
                    )
                    if match:
                        result = match.group(1)
                for prefix, name in (
                    ("Number of predicate refinements:", "refs"),
                    ("Total time for CPAchecker:", "wall"),
                    ("Total CPU time for CPAchecker:", "cpu"),
                    ("Memory consumption for CPAchecker:", "memory"),
                ):
                    if line.startswith(prefix):
                        match = re.match(r"\s*(\d+(?:\.\d+)?)", line[len(prefix) :])
                        if match:
                            value = float(match.group(1))
                            if name == "refs":
                                refs = int(value)
                            elif name == "wall":
                                wall_s = value
                            elif name == "cpu":
                                cpu_s = value
                            else:
                                memory_mb = value
                match = SOLVER_RE.search(line)
                if match:
                    solver = f"{match.group(1)} {match.group(2)}"
                has_oom |= (
                    "OutOfMemoryError" in line
                    or "Out of memory" in line
                    or "memory problems (Java heap space)" in line
                )
                has_hang |= "forcing immediate termination" in line
                has_exc |= bool(
                    "Exception in thread" in line
                    or re.search(r"java\.lang\.\w*(Exception|Error)\b", line)
                )
                has_native |= any(
                    token in line
                    for token in (
                        "stack smashing detected",
                        "SIGSEGV",
                        "SIGABRT",
                        "A fatal error has been detected by the Java Runtime Environment",
                    )
                )
                has_cpu |= "CPU-time limit of" in line and "has elapsed" in line
                has_wall |= (
                    "walltime limit of" in line.lower() and "has elapsed" in line
                )
                provider_failures += line.count("VGuide LLM call failed")
                analysis_failures += line.count("Refinement failed:")
    execution = execution or {
        "exit_code": exit_code,
        "signal": -exit_code if exit_code < 0 else None,
        "termination_reason": "wall_timeout" if exit_code == 124 else "exit",
        "raw_wall_s": None,
    }
    code = execution["exit_code"]
    reason = execution["termination_reason"]
    if reason == "launch_error" or code in (125, 126, 127):
        failure = "infrastructure_error"
    elif has_oom:
        failure = "out_of_memory"
    elif (
        has_native
        or (code not in (None, 0, 124) and reason != "wall_timeout")
        or has_exc
    ):
        failure = "crash"
    elif reason == "wall_timeout" or has_cpu or has_wall:
        failure = "timeout"
    elif not log.is_file() or log.stat().st_size == 0:
        failure = "no_log"
    elif has_hang:
        failure = "smt_hang"
    elif analysis_failures:
        failure = "analysis_failure"
    elif provider_failures:
        failure = "provider_failure"
    elif result == "UNKNOWN":
        failure = "unknown"
    elif result in ("TRUE", "FALSE"):
        failure = "ok"
    else:
        failure = "incomplete"
    meta = run_meta or {}
    if arm == "stock":
        dump_dir = None
    return {
        **task_row,
        "property": "unreach-call",
        "arm": arm,
        "commit": commit,
        "config_sha256": config_sha,
        **{
            key: meta.get(key)
            for key in ("manifest_sha256", "spec_sha256", "runtime_sha256")
        },
        "solver": solver,
        "reported_verdict": result,
        "verdict": result if failure in ("ok", "unknown", "timeout") else "",
        "exit_code": code,
        "signal": execution.get("signal"),
        "termination_reason": reason,
        "raw_wall_s": execution.get("raw_wall_s"),
        "refinements": refs,
        "wall_s": wall_s,
        "score_wall_s": min(wall_s, timelimit) if wall_s is not None else None,
        "cpu_s": cpu_s,
        "memory_mb": memory_mb,
        "provider_failures": provider_failures,
        "analysis_failure_messages": analysis_failures,
        **dump_metrics(task_row, dump_dir, arm),
        "failure_category": failure,
        "log": str(log),
        "log_sha256": sha256_file(log) if log.is_file() else None,
        "execution": execution,
        "dump_dir": str(dump_dir) if dump_dir else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_tasks = sub.add_parser(
        "tasks", help="emit tasks.tsv rows from the frozen manifest"
    )
    p_tasks.add_argument("--manifest", required=True, type=Path)
    p_tasks.add_argument("--sv-benchmarks", required=True, type=Path)
    p_tasks.add_argument("--no-verify", action="store_true")
    p_tasks.add_argument("--out", required=True, type=Path)
    p_record = sub.add_parser("record", help="emit one JSONL record from a CPA log")
    p_record.add_argument(
        "--task-row", required=True, help="tab-separated tasks.tsv row"
    )
    p_record.add_argument("--log", required=True, type=Path)
    p_record.add_argument("--dump-dir", type=Path, default=None)
    p_record.add_argument("--config-sha", required=True)
    p_record.add_argument("--commit", required=True)
    p_record.add_argument("--arm", required=True, choices=["stock", "augmented"])
    p_record.add_argument("--timelimit", type=int, default=300)
    p_record.add_argument("--exit-code", type=int, default=0)
    p_record.add_argument("--out", required=True, type=Path)
    p_record.add_argument("--execution", type=Path)
    p_record.add_argument("--run-meta", type=Path)
    p_capture = sub.add_parser(
        "capture", help="capture untouched log and process status"
    )
    p_capture.add_argument("--log", required=True, type=Path)
    p_capture.add_argument("--status", required=True, type=Path)
    p_capture.add_argument("--wall-limit", required=True, type=float)
    p_capture.add_argument("command", nargs=argparse.REMAINDER)
    p_runtime = sub.add_parser("runtime", help="hash the existing isolated runtime")
    p_runtime.add_argument("--repo", required=True, type=Path)
    args = ap.parse_args()
    if args.cmd == "runtime":
        print(json.dumps(runtime_identity(args.repo)))
        return 0

    if args.cmd == "capture":
        command = args.command[1:] if args.command[:1] == ["--"] else args.command
        if not command or args.wall_limit <= 0:
            ap.error("capture needs a command and positive wall limit")
        capture_run(command, args.log, args.status, args.wall_limit)
        return 0

    if args.cmd == "tasks":
        rows = tasks_from_manifest(
            args.manifest, args.sv_benchmarks, verify=not args.no_verify
        )
        with open(args.out, "w", encoding="utf-8") as f:
            f.writelines(
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
                for r in rows
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
            json.loads(args.execution.read_text(encoding="utf-8"))
            if args.execution
            else None,
            json.loads(args.run_meta.read_text(encoding="utf-8"))
            if args.run_meta
            else None,
        )
        if args.execution:
            record["execution_file"] = str(args.execution.resolve())
            record["execution_sha256"] = sha256_file(args.execution)
        with open(args.out, "x", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
