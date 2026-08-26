#!/usr/bin/env python3
"""Tests for the core-only evaluation harness (Issue #2)."""

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core_only_config_diff as diff
import core_only_records as rec


def test_formal_runner_uses_meta_contributor_with_canonical_completion_budget():
    runner = (Path(__file__).resolve().parents[1] / "run_core_only.sh").read_text()
    assert 'VGUIDE_LLM_PROVIDER:-meta' in runner
    assert 'VGUIDE_LLM_MODEL:-muse-spark-1.2-contributor' in runner
    assert 'LLM_MAX_COMPLETION_TOKENS="1024"' in runner
    worker_exports = re.search(r"export OUT .*", runner).group(0)
    assert "LLM_MAX_COMPLETION_TOKENS" in worker_exports
    assert 'vguide.llmMaxCompletionTokens=$LLM_MAX_COMPLETION_TOKENS' in runner
    assert "VGUIDE_LLM_MAX_COMPLETION_TOKENS" not in runner
    assert 'THINKING="required"' not in runner


def test_formal_runner_uses_five_sample_median_without_psr_veto():
    runner = (Path(__file__).resolve().parents[1] / "run_core_only.sh").read_text()
    assert 'mpstat -P "$P_CORE_RANGE" 1 5' in runner
    assert "median busy" in runner
    assert "ps -eo user,pgid,psr,pcpu,comm" not in runner


def test_deepseek_is_replay_only_in_active_runners():
    script_dir = Path(__file__).resolve().parents[1]
    for name in ("run.sh", "run_benchmark_set.sh", "run_core_only.sh"):
        runner = (script_dir / name).read_text()
        assert "DEEPSEEK_API_KEY" not in runner
        assert "DeepSeek live requests are disabled; set VGUIDE_LLM_REPLAY_DIR" in runner


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
        "Verification result: UNKNOWN, incomplete analysis.\n"
    )
    dump_root = tmp_path / "dumps"
    dump = dump_root / "tasks" / "a"
    dump.mkdir(parents=True)
    (dump / "llm_rounds.jsonl").write_text("{}\n{}\n")
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
    assert r["llm_calls"] == 2
    assert r["validated_predicates"] == 2
    assert r["injected_predicates"] == 1
    assert r["failure_category"] == "timeout"  # wall_s >= timelimit


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
