"""Adversarial behavior checks for truthful capture and manifest-exact pairing."""

import hashlib
import json
import signal
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import analyze_core_only_pair as pair
import check_core_only_smoke as smoke
import core_only_records as records
from core_only_config_diff import config_sha256


def task_row():
    return {
        "task": "c/f/a.yml",
        "source": "f/a.c",
        "expected_verdict": "true",
        "data_model": "ILP32",
        "family": "f",
        "task_sha256": "a" * 64,
        "source_sha256": "b" * 64,
    }


def record(tmp_path, text, code=0, arm="stock", execution=None):
    log = tmp_path / "run.log"
    log.write_text(text)
    return records.record_from_run(
        task_row(), log, None, "c" * 64, "d" * 40, arm, 10, code, execution
    )


@pytest.mark.parametrize(
    "text,code,category,verdict",
    [
        ("*** stack smashing detected ***\n", 134, "crash", ""),
        ('Exception in thread "main" java.lang.AssertionError\n', 1, "crash", ""),
        (
            "Verification result: UNKNOWN\nTotal time for CPAchecker: 99s\n",
            0,
            "unknown",
            "UNKNOWN",
        ),
        (
            "Using the following resource limits: CPU-time limit of 10s\nVerification result: UNKNOWN\n",
            0,
            "unknown",
            "UNKNOWN",
        ),
        (
            "The CPU-time limit of 10s has elapsed.\nVerification result: UNKNOWN\n",
            0,
            "timeout",
            "UNKNOWN",
        ),
        ("no summary\n", 124, "timeout", ""),
        (
            "VGuide LLM call failed\nVerification result: UNKNOWN\n",
            0,
            "provider_failure",
            "",
        ),
        (
            "Refinement failed: solver error\nVerification result: UNKNOWN\n",
            0,
            "analysis_failure",
            "",
        ),
        ("java.lang.OutOfMemoryError\n", 1, "out_of_memory", ""),
        (
            (
                "Warning: Could not analyze loop structure of program due to memory problems (Java heap space)\n"
                "Error: Block-ends at loop heads cannot be determined without loop-structure information in CFA.\n"
            ),
            0,
            "out_of_memory",
            "",
        ),
        (
            "Verification result: TRUE\n*** stack smashing detected ***\n",
            134,
            "crash",
            "",
        ),
    ],
)
def test_failure_precedes_synthetic_or_decisive_summary(
    tmp_path, text, code, category, verdict
):
    row = record(tmp_path, text, code)
    assert (row["failure_category"], row["verdict"]) == (category, verdict)
    assert row["exit_code"] == code
    assert row["cpu_s"] is None and row["memory_mb"] is None
    assert row["wall_s"] is None or row["wall_s"] == 99


@pytest.mark.parametrize(
    "code,limit,reason,signum",
    [
        (
            "import os, signal; os.kill(os.getpid(), signal.SIGABRT)",
            30,
            "exit",
            signal.SIGABRT,
        ),
        ("import time; time.sleep(10)", 0.05, "wall_timeout", signal.SIGTERM),
        ('raise RuntimeError("deliberate")', 30, "exit", None),
        ('print("Verification result: UNKNOWN")', 30, "exit", None),
    ],
)
def test_real_subprocess_capture(tmp_path, code, limit, reason, signum):
    log, status = tmp_path / "raw.log", tmp_path / "execution.json"
    # Disable core files for this test process and inherited children.
    import resource

    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    outcome = records.capture_run([sys.executable, "-c", code], log, status, limit)
    assert outcome["termination_reason"] == reason and outcome["signal"] == signum
    assert outcome["raw_wall_s"] > 0
    assert json.loads(status.read_text()) == outcome
    assert b"runner post-process" not in log.read_bytes()
    if "print(" not in code:
        assert b"Verification result:" not in log.read_bytes()
    before = log.read_bytes()
    with pytest.raises(FileExistsError):
        records.capture_run(
            [sys.executable, "-c", "print('overwritten')"], log, status, 1
        )
    assert log.read_bytes() == before


def test_launch_failure_is_retained(tmp_path):
    result = records.capture_run(
        [str(tmp_path / "absent")], tmp_path / "log", tmp_path / "status", 1
    )
    assert result["termination_reason"] == "launch_error"
    assert result["exit_code"] is None and result["launch_error"]


@pytest.mark.parametrize(
    "bad", ["null\n", "[]\n", "{bad\n", '{"validated_predicates": 3}\n', b"\xff\n"]
)
def test_malformed_dump_not_silently_zero(tmp_path, bad):
    root = tmp_path / "dumps" / "tasks" / "a"
    root.mkdir(parents=True)
    (root / "refinements.jsonl").write_bytes(
        bad.encode() if isinstance(bad, str) else bad
    )
    metrics = records.dump_metrics(task_row(), tmp_path / "dumps", "augmented")
    assert metrics["dump_status"] == "malformed"
    assert metrics["dump_parse_errors"][0]["line"] == 1
    assert metrics["validated_predicates"] is None


def test_absent_dump_is_unobserved(tmp_path):
    metrics = records.dump_metrics(task_row(), tmp_path, "augmented")
    assert metrics["dump_status"] == "missing" and metrics["llm_calls"] is None


@pytest.mark.parametrize(
    "attempts,rows,status",
    [(2, 0, "partial"), (2, 1, "partial"), (1, 1, "present"), (1, 2, "malformed")],
)
def test_refinement_rows_do_not_certify_unobserved_attempts(
    tmp_path, attempts, rows, status
):
    root = tmp_path / "tasks" / "a"
    root.mkdir(parents=True)
    (root / "task_summary.json").write_text(
        json.dumps({"refinements": attempts, "llm_api_calls": 0})
    )
    (root / "refinements.jsonl").write_text(
        (json.dumps({"llm_called": False}) + "\n") * rows
    )
    metrics = records.dump_metrics(task_row(), tmp_path, "augmented")
    assert metrics["dump_status"] == status
    assert bool(metrics["dump_parse_errors"]) == (status == "malformed")


def test_runtime_rejects_launcher_argument_injection(tmp_path, monkeypatch):
    monkeypatch.setenv("CPACHECKER_ARGUMENTS", "--option analysis.machineModel=Linux64")
    with pytest.raises(ValueError, match="external launcher"):
        records.runtime_identity(tmp_path)


def fixture_pair(tmp_path, verdict="TRUE", category="ok"):
    cfg, spec, runtime = (tmp_path / name for name in ("config", "spec", "binary"))
    cfg.write_text("solver = MathSAT5\n")
    spec.write_text("CHECK unreach-call\n")
    runtime.write_bytes(b"fixture binary")
    task = task_row()
    (tmp_path / "f").mkdir()
    (tmp_path / "f/a.c").write_text("int main() { return 0; }\n")
    (tmp_path / "f/a.yml").write_text("input_files: a.c\n")
    task["source_sha256"] = records.sha256_file(tmp_path / "f/a.c")
    task["task_sha256"] = records.sha256_file(tmp_path / "f/a.yml")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "task_count": 1,
                "tasks": [
                    {
                        "task": task["task"],
                        "source_paths": ["c/" + task["source"]],
                        "expected_verdict": "true",
                        "data_model": "ILP32",
                        "family": "f",
                        "task_sha256": task["task_sha256"],
                        "source_sha256": [task["source_sha256"]],
                    }
                ],
            }
        )
    )
    runtime_files = {str(runtime): records.sha256_file(runtime)}
    paths = []
    for arm in ("stock", "augmented"):
        root = tmp_path / arm
        root.mkdir()
        meta = {
            "arm": arm,
            "commit": "d" * 40,
            "config": str(cfg),
            "sv_benchmarks": str(tmp_path),
            "config_sha256": config_sha256(cfg),
            "manifest_sha256": records.sha256_file(manifest),
            "spec": str(spec),
            "spec_sha256": records.sha256_file(spec),
            "runtime_files": runtime_files,
            "runtime_sha256": hashlib.sha256(
                json.dumps(runtime_files, sort_keys=True).encode()
            ).hexdigest(),
            "timelimit_s": 10,
            "heap": "1000M",
            "timeout_grace": 5,
            "parallel": 1,
            "cpu_list": "4",
            "evidence_tier": "exploratory",
            "timing_claims_allowed": False,
            "model": "fixture-model",
            "thinking": "disabled",
            "reasoning_effort": None,
            "llm_provider": "meta",
            "llm_api_format": "meta-chat-completions-json-schema-v1",
            "llm_api_url": "",
            "llm_max_completion_tokens": "1024",
            "resource_snapshot": {
                "host": "fixture-host",
                "loadavg": [0, 0, 0],
                "meminfo": {"unavailable": "offline fixture"},
                "memory_pressure": {"unavailable": "offline fixture"},
            },
        }
        (root / "run_meta.json").write_text(json.dumps(meta))
        log = root / "raw.log"
        log.write_text(
            f"Verification result: {verdict}\n"
            + ("*** stack smashing detected ***\n" if category == "crash" else "")
        )
        execution = {
            "exit_code": 0,
            "signal": None,
            "termination_reason": "exit",
            "raw_wall_s": 0.2,
            "log_sha256": records.sha256_file(log),
            "command": [
                "taskset",
                "-c",
                "4",
                "fixture",
                "--heap",
                "1000M",
                "--config",
                str(cfg),
                "--spec",
                str(spec),
                "--timelimit",
                "10s",
                "--option",
                "analysis.machineModel=Linux32",
                "--option",
                f"cpa.predicate.refinement.useVocabularyGuide={'true' if arm == 'augmented' else 'false'}",
                str(tmp_path / task["source"]),
            ],
        }
        dump_dir = None
        if arm == "augmented":
            dump_dir = root / "dumps"
            task_dump = dump_dir / "tasks/a"
            task_dump.mkdir(parents=True)
            (task_dump / "task_summary.json").write_text(
                json.dumps({"refinements": 0, "llm_api_calls": 0})
            )
        row = records.record_from_run(
            task,
            log,
            dump_dir,
            meta["config_sha256"],
            meta["commit"],
            arm,
            10,
            execution=execution,
            run_meta=meta,
        )
        execution_path = root / "execution.json"
        execution_path.write_text(json.dumps(execution))
        row["execution_file"] = str(execution_path)
        row["execution_sha256"] = records.sha256_file(execution_path)
        path = root / "records.jsonl"
        path.write_text(json.dumps(row) + "\n")
        paths.append(path)
    return paths, manifest


def test_positive_pair(tmp_path):
    paths, manifest = fixture_pair(tmp_path)
    report = pair.harvest(paths, manifest)
    assert report["integrity_ok"] and report["comparison_usable"]
    assert report["cohort_size"] == 1 and report["arms"]["stock"]["official_wrong"] == 0


@pytest.mark.parametrize("missing", [True, False])
def test_capped_score_requires_raw_evidence(tmp_path, missing):
    paths, manifest = fixture_pair(tmp_path)
    row = json.loads(paths[0].read_text())
    if missing:
        del row["score_wall_s"]
    else:
        row["score_wall_s"] = 17.0
    paths[0].write_text(json.dumps(row) + "\n")
    report = pair.harvest(paths, manifest)
    assert not report["integrity_ok"]
    assert any("score_wall_s" in error for error in report["errors"])


def test_captured_model_must_match_manifest_even_with_consistent_hashes(tmp_path):
    paths, manifest = fixture_pair(tmp_path)
    row = json.loads(paths[0].read_text())
    command = row["execution"]["command"]
    command[command.index("analysis.machineModel=Linux32")] = (
        "analysis.machineModel=Linux64"
    )
    execution = Path(row["execution_file"])
    execution.write_text(json.dumps(row["execution"]))
    row["execution_sha256"] = records.sha256_file(execution)
    paths[0].write_text(json.dumps(row) + "\n")
    report = pair.harvest(paths, manifest)
    assert not report["integrity_ok"]
    assert any("captured machine model mismatch" in error for error in report["errors"])


def test_record_paths_survive_a_different_harvest_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("raw.log").write_text("Verification result: UNKNOWN\n")
    Path("dumps").mkdir()
    row = records.record_from_run(
        task_row(), Path("raw.log"), Path("dumps"), "c" * 64, "d" * 40, "augmented", 10
    )
    monkeypatch.chdir(tmp_path.parent)
    assert Path(row["log"]).is_absolute() and Path(row["dump_dir"]).is_absolute()
    assert records.sha256_file(Path(row["log"])) == row["log_sha256"]
    assert Path(row["dump_dir"]).is_dir()


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate",
        "missing",
        "hash",
        "label",
        "runtime",
        "arm",
        "missing_field",
        "null",
        "log",
        "relative_source",
    ],
)
def test_gate_rejects_adversarial_evidence(tmp_path, mutation):
    paths, manifest = fixture_pair(tmp_path)
    row = json.loads(paths[0].read_text())
    if mutation == "duplicate":
        paths[0].write_text(paths[0].read_text() * 2)
    elif mutation == "missing":
        paths[0].write_text("")
    elif mutation == "log":
        Path(row["log"]).write_text("tampered\n")
    else:
        if mutation == "hash":
            row["source_sha256"] = "invalid"
        if mutation == "label":
            row["expected_verdict"] = "false"
        if mutation == "runtime":
            row["runtime_sha256"] = "f" * 64
        if mutation == "arm":
            row["arm"] = "augmented"
        if mutation == "missing_field":
            del row["failure_category"]
        if mutation == "null":
            row = None
        if mutation == "relative_source":
            row["execution"]["command"][-1] = row["source"]
            execution = Path(row["execution_file"])
            execution.write_text(json.dumps(row["execution"]))
            row["execution_sha256"] = records.sha256_file(execution)
        paths[0].write_text(json.dumps(row) + "\n")
    result = subprocess.run(
        [
            sys.executable,
            str(Path(smoke.__file__)),
            *map(str, paths),
            "--manifest",
            str(manifest),
            "--expect-count",
            "1",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, result.stdout
    assert "Traceback" not in result.stderr


def test_crashes_are_valid_evidence_but_fail_smoke(tmp_path, monkeypatch):
    paths, manifest = fixture_pair(tmp_path, category="crash")
    monkeypatch.setattr(
        sys, "argv", ["smoke", *map(str, paths), "--manifest", str(manifest)]
    )
    assert smoke.main() == 1
    assert pair.harvest(paths, manifest)["arms"]["stock"]["failures"] == {"crash": 1}


def test_disputes_never_waive_official_wrong(tmp_path, monkeypatch):
    paths, manifest = fixture_pair(tmp_path, verdict="FALSE")
    disputes = tmp_path / "disputes"
    disputes.write_text("  # comment\nc/f/a.yml\n")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "smoke",
            *map(str, paths),
            "--manifest",
            str(manifest),
            "--known-disputes",
            str(disputes),
        ],
    )
    assert smoke.main() == 1
    report = pair.harvest(paths, manifest, smoke.load_disputes(disputes))
    assert report["comparison_usable"]
    assert report["arms"]["stock"]["official_wrong"] == 1
    assert report["arms"]["augmented"]["annotated_wrong_tasks"] == ["c/f/a.yml"]


def test_crash_cannot_be_relabeled_unknown(tmp_path):
    paths, manifest = fixture_pair(tmp_path, category="crash")
    row = json.loads(paths[0].read_text())
    row.update(failure_category="unknown", verdict="UNKNOWN")
    paths[0].write_text(json.dumps(row) + "\n")
    _, errors = smoke.validate(paths, manifest)
    assert any("harvested field" in error for error in errors)


def test_augmented_only_wrong_stops_comparison(tmp_path):
    paths, manifest = fixture_pair(tmp_path)
    row = json.loads(paths[1].read_text())
    log = Path(row["log"])
    log.write_text("Verification result: FALSE\n")
    row.update(
        verdict="FALSE", reported_verdict="FALSE", log_sha256=records.sha256_file(log)
    )
    row["execution"]["log_sha256"] = row["log_sha256"]
    execution = Path(row["execution_file"])
    execution.write_text(json.dumps(row["execution"]))
    row["execution_sha256"] = records.sha256_file(execution)
    paths[1].write_text(json.dumps(row) + "\n")
    result = pair.harvest(paths, manifest)
    assert result["integrity_ok"] and not result["comparison_usable"]
    assert result["augmentation_only_wrong_tasks"] == ["c/f/a.yml"]


def test_runner_failure_capture_and_resume_preserve_logs(tmp_path):
    import os
    import re
    import resource

    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    paths, manifest = fixture_pair(tmp_path)
    root = tmp_path / "runner"
    (root / "logs").mkdir(parents=True)
    (root / "run_meta.json").write_bytes(
        (paths[0].parent / "run_meta.json").read_bytes()
    )
    meta = json.loads((root / "run_meta.json").read_text())
    executable = tmp_path / "abort-verifier"
    executable.write_text(
        f'#!{sys.executable}\nimport os,signal\nprint("*** stack smashing detected ***",flush=True)\nos.kill(os.getpid(),signal.SIGABRT)\n'
    )
    executable.chmod(0o755)
    runner = (Path(records.__file__).parent / "run_core_only.sh").read_text()
    functions = "\n".join(
        re.search(rf"^{name}\(\) \{{.*?^\}}", runner, re.MULTILINE | re.DOTALL).group()
        for name in ("read_task_row", "machine_model_for", "build_command", "task_name_of", "run_one")
    )
    frozen, _ = records.load_manifest(manifest)
    row = records.manifest_rows(frozen)[0]
    env = dict(
        os.environ,
        OUT=str(root),
        ARM="stock",
        USE_VGUIDE="false",
        REPO=str(tmp_path),
        CPA_SH=str(executable),
        SV_BENCHMARKS=str(tmp_path),
        RECORDS_PY=records.__file__,
        CONFIG="config",
        SPEC=str(tmp_path / "spec"),
        TIMELIMIT="30",
        TIMEOUT_GRACE="5",
        HEAP="1000M",
        COMMIT=meta["commit"],
        CONFIG_SHA=meta["config_sha256"],
        P_CORE_LIST=str(min(os.sched_getaffinity(0))),
        DRY="0",
        TASK_ROW="\t".join(str(v) for v in row.values()),
    )
    command = ["bash", "-c", functions + '\nrun_one "$TASK_ROW"']
    first = subprocess.run(
        command, env=env, capture_output=True, text=True, check=False
    )
    assert first.returncode == 0, first.stderr
    status = next((root / "logs").glob("*.execution.json"))
    captured = json.loads(status.read_text())
    assert captured["exit_code"] == -signal.SIGABRT
    log = next((root / "logs").glob("*.log"))
    assert log.read_bytes() == b"*** stack smashing detected ***\n"
    record_path = next(p for p in (root / "logs").glob("*.json") if p != status)
    record_row = json.loads(record_path.read_text())
    assert record_row["failure_category"] == "crash" and record_row["verdict"] == ""
    before = {p: p.read_bytes() for p in (root / "logs").iterdir()}
    second = subprocess.run(
        command, env=env, capture_output=True, text=True, check=False
    )
    assert second.returncode == 0 and "skip" in second.stdout
    assert before == {p: p.read_bytes() for p in (root / "logs").iterdir()}
    record_path.write_text("{truncated")
    third = subprocess.run(
        command, env=env, capture_output=True, text=True, check=False
    )
    assert third.returncode != 0 and log.read_bytes() == before[log]


def test_runtime_hash_tracks_existing_binary_without_build(tmp_path, monkeypatch):
    main_class = tmp_path / "classes/org/sosy_lab/cpachecker/cmdline/CPAMain.class"
    main_class.parent.mkdir(parents=True)
    main_class.write_bytes(b"fixture class v1")
    for relative in ("scripts/cpa.sh", "bin/cpachecker", "jdk/bin/java"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture executable")
        path.chmod(0o755)
    monkeypatch.setenv("JAVA", str(tmp_path / "jdk/bin/java"))
    for key in (
        "CLASSPATH",
        "JAVA_TOOL_OPTIONS",
        "JDK_JAVA_OPTIONS",
        "PATH_TO_CPACHECKER",
    ):
        monkeypatch.delenv(key, raising=False)
    first = records.runtime_identity(tmp_path)
    assert first == records.runtime_identity(tmp_path)
    main_class.write_bytes(b"fixture class v2")
    assert (
        records.runtime_identity(tmp_path)["runtime_sha256"] != first["runtime_sha256"]
    )


def test_capture_preserves_status_when_process_exits_before_sigkill(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace

    waits = iter([False, False, True])

    def wait(timeout=None):
        if not next(waits):
            raise subprocess.TimeoutExpired("fixture", timeout)
        return 0

    def killpg(pid, sig):
        if sig == signal.SIGKILL:
            raise ProcessLookupError(pid)

    proc = SimpleNamespace(pid=12345, returncode=0, wait=wait)
    monkeypatch.setattr(records.subprocess, "Popen", lambda *args, **kwargs: proc)
    monkeypatch.setattr(records.os, "killpg", killpg)
    outcome = records.capture_run(["fixture"], tmp_path / "log", tmp_path / "status", 1)
    assert outcome["termination_reason"] == "wall_timeout" and outcome["exit_code"] == 0
    assert json.loads((tmp_path / "status").read_text()) == outcome


def test_missing_execution_sidecar_is_an_integrity_error(tmp_path):
    paths, manifest = fixture_pair(tmp_path)
    Path(json.loads(paths[0].read_text())["execution_file"]).unlink()
    arms, errors = smoke.validate(paths, manifest)
    assert set(arms) == {"stock", "augmented"}
    assert any("execution artifact mismatch" in error for error in errors)


def test_utf8_evidence_is_read_under_ascii_locale(tmp_path):
    import os

    paths, manifest = fixture_pair(tmp_path)
    for path in paths:
        meta_path = path.parent / "run_meta.json"
        meta = json.loads(meta_path.read_text())
        meta["note"] = "證據"
        meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    disputes = tmp_path / "disputes"
    disputes.write_text("# 註記\nc/f/a.yml\n", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(Path(smoke.__file__)),
            *map(str, paths),
            "--manifest",
            str(manifest),
            "--known-disputes",
            str(disputes),
        ],
        env=dict(os.environ, LC_ALL="C", PYTHONUTF8="0", PYTHONCOERCECLOCALE="0"),
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
