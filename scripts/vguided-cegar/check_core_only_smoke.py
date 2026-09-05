#!/usr/bin/env python3
"""Validate frozen core-only evidence; diagnostic disputes never waive official wrongs.

Require --manifest and adjacent run_meta.json for each arm. Integrity and smoke
eligibility are separate gates; paired exploration can retain failures without
claiming that the smoke passed. Paths in records/metadata refer to original evidence.
"""

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

from core_only_config_diff import config_sha256
from core_only_records import load_manifest, manifest_rows, record_from_run, sha256_file

HASH_FIELDS = (
    "task_sha256",
    "source_sha256",
    "config_sha256",
    "manifest_sha256",
    "spec_sha256",
    "runtime_sha256",
    "log_sha256",
)
FAILURES = {
    "ok",
    "unknown",
    "timeout",
    "crash",
    "out_of_memory",
    "smt_hang",
    "provider_failure",
    "analysis_failure",
    "incomplete",
    "no_log",
    "infrastructure_error",
}
REQUIRED_FIELDS = (
    "task",
    "source",
    "property",
    "expected_verdict",
    "data_model",
    "arm",
    "commit",
    "verdict",
    "reported_verdict",
    "failure_category",
    "log",
    "execution",
    "exit_code",
    "signal",
    "termination_reason",
    "raw_wall_s",
    "wall_s",
    "cpu_s",
    "memory_mb",
    "refinements",
    "dump_status",
    "dump_parse_errors",
    "dump_files",
    "provider_failures",
    "analysis_failure_messages",
    "dump_dir",
    "execution_file",
    "execution_sha256",
    *HASH_FIELDS,
)


def wrong_verdict(expected, verdict):
    label = str(expected).lower()
    return (
        label in ("true", "false")
        and verdict in ("TRUE", "FALSE")
        and verdict.lower() != label
    )


def load_disputes(path):
    if not path:
        return set()
    return {
        line.split("\t", 1)[0].strip()
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def load(path):
    rows = []
    with Path(path).open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError as error:
                raise ValueError(f"{path}:{number}: {error}") from error
            if not isinstance(row, dict):
                raise TypeError(f"{path}:{number}: record must be an object")
            rows.append(row)
    return rows


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def validate_metadata(meta):
    required = {
        "config": str,
        "spec": str,
        "sv_benchmarks": str,
        "timelimit_s": int,
        "timeout_grace": int,
        "parallel": int,
        "heap": str,
        "cpu_list": str,
        "evidence_tier": str,
        "timing_claims_allowed": bool,
        "model": str,
        "thinking": str,
        "llm_provider": str,
        "llm_api_format": str,
        "llm_api_url": str,
        "llm_max_completion_tokens": str,
        "resource_snapshot": dict,
        "reasoning_effort": (str, type(None)),
    }
    invalid = [
        key
        for key, kind in required.items()
        if key not in meta
        or (
            type(meta[key]) not in kind
            if isinstance(kind, tuple)
            else type(meta[key]) is not kind
        )
    ]
    if invalid:
        return ["missing/invalid metadata fields: " + ", ".join(invalid)]
    errors = []
    for key in (
        "config",
        "spec",
        "sv_benchmarks",
        "heap",
        "model",
        "thinking",
        "llm_api_format",
    ):
        if not meta[key]:
            errors.append("empty metadata field: " + key)
    cpus = meta["cpu_list"].split(",")
    if (
        not set(cpus) <= {str(cpu) for cpu in range(0, 16, 2)}
        or len(cpus) != len(set(cpus))
        or not 1 <= meta["parallel"] <= len(cpus)
    ):
        errors.append("invalid metadata CPU allocation")
    if meta["timelimit_s"] <= 0 or meta["timeout_grace"] < 0:
        errors.append("invalid metadata time budget")
    if meta["evidence_tier"] not in ("performance", "exploratory") or meta[
        "timing_claims_allowed"
    ] != (meta["evidence_tier"] == "performance"):
        errors.append("inconsistent metadata evidence tier/timing claims")
    if meta["llm_provider"] not in ("meta", "deepseek") or not re.fullmatch(
        r"[1-9][0-9]*", meta["llm_max_completion_tokens"]
    ):
        errors.append("invalid metadata provider/token budget")
    resource = meta["resource_snapshot"]
    if not isinstance(resource.get("host"), str) or not resource["host"]:
        errors.append("missing/invalid metadata resource host")
    loadavg = resource.get("loadavg")
    if (
        not isinstance(loadavg, list)
        or len(loadavg) != 3
        or not all(map(finite_number, loadavg))
    ):
        errors.append("missing/invalid metadata load snapshot")
    for key in ("meminfo", "memory_pressure"):
        value = resource.get(key)
        if not (isinstance(value, str) and value) and not (
            isinstance(value, dict)
            and isinstance(value.get("unavailable"), str)
            and value["unavailable"]
        ):
            errors.append("missing/invalid metadata resource: " + key)
    return errors


def validate(paths, manifest_path):
    """One structural validator shared by smoke and paired harvest."""
    manifest, manifest_sha = load_manifest(manifest_path)
    expected = {r["task"]: r for r in manifest_rows(manifest)}
    errors, arms, metas = [], {}, {}
    for path in paths:
        path = Path(path)
        rows = load(path)
        meta = json.loads((path.parent / "run_meta.json").read_text(encoding="utf-8"))
        if not isinstance(meta, dict) or meta.get("arm") not in ("stock", "augmented"):
            raise ValueError(f"{path}: invalid run metadata/arm")
        arm = meta["arm"]
        if arm in arms:
            errors.append(f"duplicate arm: {arm}")
        arms[arm], metas[arm] = rows, meta
        metadata_errors = validate_metadata(meta)
        if metadata_errors:
            errors.extend(f"{arm}: {error}" for error in metadata_errors)
            continue
        if meta.get("manifest_sha256") != manifest_sha:
            errors.append(f"{arm}: manifest hash mismatch")
        for field, actual in (
            ("config_sha256", config_sha256(Path(meta["config"]))),
            ("spec_sha256", sha256_file(Path(meta["spec"]))),
        ):
            if meta.get(field) != actual:
                errors.append(f"{arm}: {field} does not match artifact")
        runtime_files = meta.get("runtime_files")
        if not isinstance(runtime_files, dict) or not runtime_files:
            errors.append(f"{arm}: missing runtime_files")
        else:
            digest = hashlib.sha256(
                json.dumps(runtime_files, sort_keys=True).encode()
            ).hexdigest()
            if digest != meta.get("runtime_sha256"):
                errors.append(f"{arm}: runtime hash mismatch")
            for filename, digest in runtime_files.items():
                if (
                    not Path(filename).is_file()
                    or sha256_file(Path(filename)) != digest
                ):
                    errors.append(f"{arm}: runtime artifact mismatch: {filename}")
        tasks = [r.get("task") for r in rows]
        if any(not isinstance(t, str) for t in tasks):
            errors.append(f"{arm}: invalid task identity")
        else:
            if len(tasks) != len(set(tasks)):
                errors.append(f"{arm}: duplicate task records")
            if set(tasks) != set(expected):
                errors.append(f"{arm}: task set differs from frozen manifest")
        for index, row in enumerate(rows, 1):
            tag = f"{arm}:{index}:{row.get('task')}"
            missing = set(REQUIRED_FIELDS) - row.keys()
            if missing:
                errors.append(f"{tag}: missing fields {sorted(missing)}")
                continue
            for field in HASH_FIELDS:
                if not isinstance(row[field], str) or not re.fullmatch(
                    r"[0-9a-f]{64}", row[field]
                ):
                    errors.append(f"{tag}: invalid {field}")
            if not isinstance(row["commit"], str) or not re.fullmatch(
                r"[0-9a-f]{40}", row["commit"]
            ):
                errors.append(f"{tag}: invalid commit")
            task = expected.get(row["task"]) if isinstance(row["task"], str) else None
            if task and any(row.get(k) != v for k, v in task.items()):
                errors.append(f"{tag}: task identity/label mismatch")
            for field in (
                "arm",
                "commit",
                "config_sha256",
                "manifest_sha256",
                "spec_sha256",
                "runtime_sha256",
            ):
                if row[field] != meta.get(field):
                    errors.append(f"{tag}: metadata mismatch: {field}")
            if (
                row["property"] != "unreach-call"
                or row["failure_category"] not in FAILURES
            ):
                errors.append(f"{tag}: invalid property/failure")
            if row["verdict"] not in ("", "TRUE", "FALSE", "UNKNOWN") or row[
                "reported_verdict"
            ] not in ("", "TRUE", "FALSE", "UNKNOWN"):
                errors.append(f"{tag}: invalid verdict")
            if (
                row["failure_category"] not in ("ok", "unknown", "timeout")
                and row["verdict"]
            ):
                errors.append(f"{tag}: failed process masquerades as verdict")
            execution_path = Path(row["execution_file"])
            if (
                not execution_path.is_file()
                or sha256_file(execution_path) != row["execution_sha256"]
                or json.loads(execution_path.read_text(encoding="utf-8"))
                != row["execution"]
            ):
                errors.append(f"{tag}: execution artifact mismatch")
            execution = row["execution"]
            if not isinstance(execution, dict) or any(
                row[k] != execution.get(k)
                for k in (
                    "exit_code",
                    "signal",
                    "termination_reason",
                    "raw_wall_s",
                    "log_sha256",
                )
            ):
                errors.append(f"{tag}: execution mismatch")
            elif row["termination_reason"] not in (
                "exit",
                "wall_timeout",
                "launch_error",
                "interrupted",
            ):
                errors.append(f"{tag}: invalid termination reason")
            command = execution.get("command") if isinstance(execution, dict) else None
            if (
                not isinstance(command, list)
                or not command
                or any(not isinstance(v, str) for v in command)
            ):
                errors.append(f"{tag}: missing/invalid captured argv")
            else:
                # The runner freezes absolute paths; the harvester's cwd is irrelevant.
                for flag, value in (
                    ("--config", meta["config"]),
                    ("--spec", meta["spec"]),
                    ("--heap", meta["heap"]),
                    ("--timelimit", f"{meta['timelimit_s']}s"),
                ):
                    positions = [i for i, v in enumerate(command) if v == flag]
                    if (
                        len(positions) != 1
                        or positions[0] + 1 >= len(command)
                        or command[positions[0] + 1] != value
                    ):
                        errors.append(f"{tag}: captured command mismatch: {flag}")
                if command[:3] != ["taskset", "-c", meta["cpu_list"]]:
                    errors.append(f"{tag}: captured CPU allocation mismatch")
                if command[-1] != str(Path(meta["sv_benchmarks"]) / row["source"]):
                    errors.append(f"{tag}: captured source mismatch")
                guide = f"cpa.predicate.refinement.useVocabularyGuide={'true' if arm == 'augmented' else 'false'}"
                if command.count(guide) != 1:
                    errors.append(f"{tag}: captured augmentation setting mismatch")
                machine_model = {"ILP32": "Linux32", "LP64": "Linux64"}.get(
                    row["data_model"]
                )
                if [
                    value
                    for value in command
                    if value.startswith("analysis.machineModel=")
                ] != [f"analysis.machineModel={machine_model}"]:
                    errors.append(f"{tag}: captured machine model mismatch")
            code = row["exit_code"]
            if code is not None and type(code) is not int:
                errors.append(f"{tag}: invalid exit code")
            elif row["signal"] != (-code if code is not None and code < 0 else None):
                errors.append(f"{tag}: inconsistent exit/signal")
            if isinstance(execution, dict) and task:
                parsed = record_from_run(
                    task,
                    Path(row["log"]),
                    Path(row["dump_dir"]) if row["dump_dir"] else None,
                    row["config_sha256"],
                    row["commit"],
                    arm,
                    meta["timelimit_s"],
                    execution=execution,
                    run_meta=meta,
                )
                for field in (
                    "verdict",
                    "reported_verdict",
                    "failure_category",
                    "wall_s",
                    "cpu_s",
                    "memory_mb",
                    "refinements",
                    "provider_failures",
                    "analysis_failure_messages",
                    "dump_status",
                    "dump_parse_errors",
                    "dump_files",
                    "llm_calls",
                    "llm_response_parse_failures",
                    "llm_empty_responses",
                    "validated_predicates",
                    "injected_predicates",
                ):
                    if row.get(field) != parsed[field]:
                        errors.append(
                            f"{tag}: harvested field disagrees with raw evidence: {field}"
                        )
            if not finite_number(row["raw_wall_s"]):
                errors.append(f"{tag}: missing/invalid measured elapsed time")
            for field in ("wall_s", "cpu_s", "memory_mb", "refinements"):
                if row[field] is not None and not finite_number(row[field]):
                    errors.append(f"{tag}: invalid measurement {field}")
            for filename, digest in {
                row["log"]: row["log_sha256"],
                str(Path(meta["sv_benchmarks"]) / row["source"]): row["source_sha256"],
                str(Path(meta["sv_benchmarks"]) / row["task"].removeprefix("c/")): row[
                    "task_sha256"
                ],
                **row["dump_files"],
            }.items():
                if (
                    not isinstance(filename, str)
                    or not Path(filename).is_file()
                    or sha256_file(Path(filename)) != digest
                ):
                    errors.append(f"{tag}: missing/changed artifact: {filename}")
            if row["dump_status"] == "malformed" or row["dump_parse_errors"]:
                errors.append(f"{tag}: malformed dump")
    if len(arms) == 2 and not errors:
        for field in (
            "commit",
            "manifest_sha256",
            "spec_sha256",
            "runtime_sha256",
            "timelimit_s",
            "heap",
            "timeout_grace",
            "parallel",
            "cpu_list",
            "evidence_tier",
            "timing_claims_allowed",
            "llm_provider",
            "llm_api_format",
            "model",
            "thinking",
            "reasoning_effort",
            "llm_api_url",
            "llm_max_completion_tokens",
        ):
            if metas["stock"].get(field) != metas["augmented"].get(field):
                errors.append(f"pair: inconsistent {field}")
        if metas["stock"].get("resource_snapshot", {}).get("host") != metas[
            "augmented"
        ].get("resource_snapshot", {}).get("host"):
            errors.append("pair: inconsistent resource host")
    return arms, errors


def summarize(rows, disputes=()):
    wrong = sorted(
        r["task"]
        for r in rows
        if wrong_verdict(r.get("expected_verdict"), r.get("reported_verdict"))
    )
    ineligible = [
        r["task"]
        for r in rows
        if r.get("failure_category") not in ("ok", "unknown", "timeout")
        or r.get("provider_failures")
        or r.get("analysis_failure_messages")
        or (r.get("arm") == "augmented" and r.get("dump_status") != "present")
    ]
    return {
        "records": len(rows),
        "verdicts": dict(Counter(r.get("verdict") for r in rows)),
        "failures": dict(Counter(r.get("failure_category") for r in rows)),
        "official_correct": sum(
            r.get("failure_category") == "ok"
            and r.get("verdict") in ("TRUE", "FALSE")
            and not wrong_verdict(r.get("expected_verdict"), r.get("verdict"))
            for r in rows
        ),
        "provider_failures": sum(r.get("provider_failures", 0) for r in rows),
        "llm_response_parse_failures": (
            sum(r["llm_response_parse_failures"] for r in rows)
            if all(r.get("llm_response_parse_failures") is not None for r in rows)
            else None
        ),
        "llm_empty_responses": (
            sum(r["llm_empty_responses"] for r in rows)
            if all(r.get("llm_empty_responses") is not None for r in rows)
            else None
        ),
        "official_wrong": len(wrong),
        "wrong_tasks": wrong,
        "annotated_wrong_tasks": sorted(set(wrong) & set(disputes)),
        "smoke_ineligible_tasks": ineligible,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records", nargs="+", type=Path)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--expect-count", type=int)
    parser.add_argument(
        "--known-disputes", type=Path, help="annotation only; never a wrong waiver"
    )
    args = parser.parse_args()
    try:
        arms, errors = validate(args.records, args.manifest)
        summaries = {
            arm: summarize(rows, load_disputes(args.known_disputes))
            for arm, rows in arms.items()
        }
        if args.expect_count is not None and any(
            len(rows) != args.expect_count for rows in arms.values()
        ):
            errors.append("record count mismatch")
        eligible = bool(arms) and all(
            not s["official_wrong"] and not s["smoke_ineligible_tasks"]
            for s in summaries.values()
        )
        print(
            json.dumps(
                {
                    "integrity_ok": not errors,
                    "smoke_ok": not errors and eligible,
                    "errors": errors,
                    "arms": summaries,
                },
                indent=2,
            )
        )
        return 0 if not errors and eligible else 1
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"SMOKE FAILED: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
