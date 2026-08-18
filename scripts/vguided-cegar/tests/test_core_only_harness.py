#!/usr/bin/env python3
"""Tests for the core-only evaluation harness (Issue #2)."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import analyze_core_only_pair as pair
import check_core_only_smoke as smoke
import core_only_config_diff as diff
import core_only_records as rec
import make_core_only_cohort as cohort


# ---------------------------------------------------------------- config diff


def write(path: Path, content: str):
    path.write_text(content)
    return path


def test_resolve_config_follows_includes(tmp_path):
    (tmp_path / "inc.properties").write_text("alpha = 1\nbeta = 2\n")
    top = write(
        tmp_path / "top.properties",
        "# comment\n#include inc.properties\ngamma = 3\n",
    )
    cfg = diff.resolve_config(top)
    assert cfg == {"alpha": "1", "beta": "2", "gamma": "3"}


def test_resolve_config_last_wins(tmp_path):
    (tmp_path / "inc.properties").write_text("x = 1\n")
    top = write(tmp_path / "top.properties", "#include inc.properties\nx = 2\n")
    assert diff.resolve_config(top) == {"x": "2"}


def test_diff_accepts_only_augmentation(tmp_path):
    stock = write(tmp_path / "stock.properties", "cpa.predicate.x = 1\nsolver = z3\n")
    augmented = write(
        tmp_path / "augmented.properties",
        "cpa.predicate.x = 1\nsolver = z3\nvguide.enable = true\n",
    )
    diffs = diff.diff_configs(stock, augmented)
    assert len(diffs) == 1
    assert diffs[0][0] == "vguide.enable"
    assert diffs[0][3] is True


def test_diff_rejects_non_augmentation_change(tmp_path):
    stock = write(tmp_path / "stock.properties", "solver = z3\ncpa.predicate.x = 1\n")
    augmented = write(tmp_path / "augmented.properties", "solver = mathsat\ncpa.predicate.x = 1\n")
    diffs = diff.diff_configs(stock, augmented)
    assert any(d[0] == "solver" and not d[3] for d in diffs)


def test_resolve_config_fails_closed_on_unresolved_include(tmp_path):
    top = write(tmp_path / "top.properties", "#include nope.properties\n")
    with pytest.raises(SystemExit, match="unresolved #include"):
        diff.resolve_config(top)


def test_diff_accepts_use_vocabulary_guide_key(tmp_path):
    stock = write(tmp_path / "stock.properties", "a = 1\n")
    augmented = write(
        tmp_path / "augmented.properties",
        "a = 1\ncpa.predicate.refinement.useVocabularyGuide = true\n",
    )
    diffs = diff.diff_configs(stock, augmented)
    assert diffs and all(d[3] for d in diffs)


# ---------------------------------------------------------------- records


def test_tasks_from_manifest_verifies_hashes(tmp_path):
    src = tmp_path / "f" / "a.c"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"int main() { return 0; }\n")
    import hashlib

    sha = hashlib.sha256(src.read_bytes()).hexdigest()
    manifest = {
        "task_count": 1,
        "tasks": [
            {
                "task": "c/f/a.yml",
                "source_paths": ["c/f/a.c"],
                "expected_verdict": "true",
                "data_model": "ILP32",
                "family": "f",
                "task_sha256": "x" * 64,
                "source_sha256": [sha],
            }
        ],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    rows = rec.tasks_from_manifest(tmp_path / "manifest.json", tmp_path)
    assert rows[0]["source"] == "f/a.c"
    assert rows[0]["expected_verdict"] == "true"


def test_make_cohort_excludes_tasks_and_preserves_order(tmp_path):
    manifest = {
        "task_count": 2,
        "selection_rule": "frozen",
        "tasks": [
            {"task": "c/f/a.yml", "source_paths": ["c/f/a.c"]},
            {"task": "c/f/b.yml", "source_paths": ["c/f/b.c"]},
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    exclude_path = tmp_path / "exclude.list"
    exclude_path.write_text("  # reason\n c/f/a.yml \tknown crash\n")

    result = cohort.make_cohort(manifest_path, exclude_path)

    assert result["task_count"] == 1
    assert [task["task"] for task in result["tasks"]] == ["c/f/b.yml"]
    assert result["excluded_tasks"] == ["c/f/a.yml"]
    assert result["parent_manifest_sha256"]


def test_make_cohort_rejects_unknown_exclusion(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"tasks": [{"task": "c/f/a.yml"}]}))
    exclude_path = tmp_path / "exclude.list"
    exclude_path.write_text("c/f/missing.yml\n")

    with pytest.raises(SystemExit, match="not in manifest"):
        cohort.make_cohort(manifest_path, exclude_path)


def test_tasks_from_manifest_rejects_hash_mismatch(tmp_path):
    src = tmp_path / "f" / "a.c"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"int main() { return 0; }\n")
    manifest = {
        "task_count": 1,
        "tasks": [
            {
                "task": "c/f/a.yml",
                "source_paths": ["c/f/a.c"],
                "expected_verdict": "true",
                "data_model": "ILP32",
                "family": "f",
                "task_sha256": "x" * 64,
                "source_sha256": ["y" * 64],
            }
        ],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(SystemExit, match="hash mismatch"):
        rec.tasks_from_manifest(tmp_path / "manifest.json", tmp_path)


def test_record_from_run_parses_log_and_dump(tmp_path):
    log = tmp_path / "t.log"
    log.write_text(
        "Using predicate analysis with MathSAT5 version 5.6.11 and JFactory 1.21.\n"
        "Number of predicate refinements:                   47\n"
        "Total time for CPAchecker:      300.796s\n"
        "Total CPU time for CPAchecker:  300.250s\n"
        "Memory consumption for CPAchecker: 512.0 MB\n"
        "Refinement failed: Interpolation failed\n"
        "Verification result: UNKNOWN, incomplete analysis.\n"
    )
    dump_root = tmp_path / "dumps"
    dump = dump_root / "tasks" / "a"
    dump.mkdir(parents=True)
    (dump / "llm_rounds.jsonl").write_text("{}\nnull\n[]\n")
    (dump / "refinements.jsonl").write_text(
        json.dumps({"validated_predicates": [1, 2], "precision_injected": [1]}) + "\n"
    )
    task_row = {
        "task": "c/f/a.yml",
        "source": "f/a.c",
        "expected_verdict": "true",
        "data_model": "ILP32",
        "family": "f",
        "task_sha256": "x" * 64,
        "source_sha256": "y" * 64,
    }
    r = rec.record_from_run(task_row, log, dump_root, "cfgsha", "commitsha", "augmented", 300)
    assert r["solver"] == "MathSAT5 5.6.11"
    assert r["refinements"] == 47
    assert r["wall_s"] == 300.0  # capped at timelimit (issue #71)
    assert r["cpu_s"] == 300.25
    assert r["memory_mb"] == "512.0"
    assert r["verdict"] == "UNKNOWN"
    assert r["llm_calls"] == 3
    assert r["validated_predicates"] == 2
    assert r["injected_predicates"] == 1
    assert r["failure_category"] == "analysis_failure"
    assert r["analysis_failure_messages"] == ["Refinement failed: Interpolation failed"]
    assert r["provider_failures"] == 0
    assert r["llm_response_parse_failures"] == 0
    assert r["llm_empty_responses"] == 0


def test_record_from_run_records_provider_and_symbol_diagnostics(tmp_path):
    log = tmp_path / "t.log"
    log.write_text(
        "VGuide LLM call failed (DeepSeek API 500)\n"
        "IllegalArgumentException: A symbol with name `SIZE@3' already exists\n"
    )
    task_row = {
        "task": "c/f/a.yml",
        "source": "f/a.c",
        "expected_verdict": "true",
        "data_model": "ILP32",
        "family": "f",
        "task_sha256": "x" * 64,
        "source_sha256": "y" * 64,
    }
    r = rec.record_from_run(task_row, log, None, "s", "c", "augmented", 300)
    assert r["provider_failures"] == 1
    assert r["crash_detail"] == "symbol_conflict"


def test_pair_analysis_counts_official_correctness_and_exclusions(tmp_path):
    rows = [
        {
            "task": "a", "expected_verdict": True, "verdict": "TRUE",
            "failure_category": "ok", "wall_s": 2,
        },
        {
            "task": "b", "expected_verdict": "true", "verdict": "FALSE",
            "failure_category": "ok", "wall_s": 3,
        },
        {
            "task": "c", "expected_verdict": "true", "verdict": "UNKNOWN",
            "failure_category": "timeout", "wall_s": 300,
        },
    ]
    stock = tmp_path / "stock.jsonl"
    augmented = tmp_path / "augmented.jsonl"
    stock.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    augmented.write_text(
        "\n".join(
            json.dumps({**row, "verdict": "TRUE" if row["task"] == "c" else row["verdict"]})
            for row in rows
        )
        + "\n"
    )
    excluded = tmp_path / "exclude.list"
    excluded.write_text("b\n")
    conflicts = tmp_path / "conflicts.list"
    conflicts.write_text("b\treason\n")
    output = tmp_path / "result.json"

    import subprocess

    subprocess.run(
        [
            sys.executable,
            str(Path(pair.__file__)),
            "--stock-records", str(stock),
            "--augmented-records", str(augmented),
            "--exclude-tasks", str(excluded),
            "--official-label-conflicts", str(conflicts),
            "--out", str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(output.read_text())
    assert result["cohort_size"] == 2
    assert result["stock"]["official_correct"] == 1
    assert result["augmented"]["official_correct"] == 2
    assert result["new_officially_correct"] == ["c"]
    assert result["official_label_conflicts_in_cohort"] == []


def test_official_conflicts_require_explicit_allowlist(tmp_path, monkeypatch):
    records = tmp_path / "records.jsonl"
    row = {field: "" for field in smoke.REQUIRED_FIELDS}
    row.update({
        "task": "c/f/a.yml", "expected_verdict": "true", "verdict": "FALSE",
        "failure_category": "ok",
    })
    records.write_text(json.dumps(row) + "\n")
    conflicts = tmp_path / "conflicts.list"
    conflicts.write_text("c/f/a.yml\treason\n")

    monkeypatch.setattr(
        sys,
        "argv",
        ["check_core_only_smoke.py", str(records), "--official-label-conflicts", str(conflicts)],
    )
    assert smoke.main() == 1

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_core_only_smoke.py", str(records),
            "--official-label-conflicts", str(conflicts),
            "--allow-known-official-conflicts",
        ],
    )
    assert smoke.main() == 0


def test_smoke_gate_reports_non_object_records(tmp_path, monkeypatch):
    records = tmp_path / "records.jsonl"
    records.write_text("null\n")
    monkeypatch.setattr(sys, "argv", ["check_core_only_smoke.py", str(records)])
    assert smoke.main() == 1


def test_record_from_run_detects_crash_and_timeout(tmp_path):
    log = tmp_path / "t.log"
    log.write_text("Exception in thread \"main\" java.lang.OutOfMemoryError\n")
    task_row = {
        "task": "c/f/a.yml",
        "source": "f/a.c",
        "expected_verdict": "true",
        "data_model": "ILP32",
        "family": "f",
        "task_sha256": "x" * 64,
        "source_sha256": "y" * 64,
    }
    r = rec.record_from_run(task_row, log, None, "s", "c", "stock", 300)
    assert r["failure_category"] == "out_of_memory"
    assert r["verdict"] == ""
    assert r["llm_calls"] == 0
