import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import verify_precision_consumer as gate


def compiler_row():
    compiler = {
        "schema_version": "cfa-precision-compiler-v2",
        "candidates": [
            {
                "abstraction_role": "PRECISION_ONLY",
                "consequent_head": "N24",
                "antecedent_formula": "(assert x)",
            }
        ],
        "rejections": [],
    }
    compiler["sha256"] = hashlib.sha256(
        json.dumps(compiler, ensure_ascii=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "precision_compiler": compiler,
        "precision_local_after": {"N24": ["(assert x) "]},
    }


def test_complete_compiler_lowering_and_hash():
    row = compiler_row()
    assert gate.verify_compiler(row) == 1
    row["precision_local_after"] = {"N25": ["(assert x)"]}
    with pytest.raises(ValueError, match="lowering"):
        gate.verify_compiler(row)
    row = compiler_row()
    row["precision_compiler"]["candidates"][0]["consequent_head"] = "N25"
    with pytest.raises(ValueError, match="hash"):
        gate.verify_compiler(row)


def test_replay_requires_all_calls_and_all_candidates():
    calls = [
        {
            "refinement_index": 1,
            "request_hash": "q",
            "response_hash": "r",
            "prompt_hash": "p",
            "response_raw": "{}",
            "response_parse_ok": False,
            "predicates_raw": [],
            "predicates_rejected": [],
            "usage": None,
        }
    ]
    row = {
        "refinement_index": 1,
        "llm_called": True,
        "validated_predicates": [],
        "candidate_rejections": [],
        "precision_injected": [],
        "precision_compiler": None,
        "native_predicate_context": {"predicates": []},
    }
    gate.verify_replay(calls, [row], copy.deepcopy(calls), [copy.deepcopy(row)])
    with pytest.raises(ValueError, match="calls"):
        gate.verify_replay(calls, [row], [], [])
    mutated = copy.deepcopy(row)
    mutated["candidate_rejections"] = ["dropped candidate"]
    with pytest.raises(ValueError, match="call-site"):
        gate.verify_replay(calls, [row], calls, [mutated])


def test_native_context_requires_actual_prompt_exposure():
    context = {
        "predicates": [{"scope": "local N24", "origin": "native", "smt": "(assert x)"}],
        "omitted": 0,
    }
    assert (
        gate.verify_native_context({"predicates": [], "omitted": 0}, "first prompt")
        == 0
    )
    prompt = "NATIVE CEGAR PRECISION (read-only):\n[local N24 | native] (assert x)"
    assert gate.verify_native_context(context, prompt) == 1
    with pytest.raises(ValueError, match="exposure"):
        gate.verify_native_context(context, "prompt without native block")


def test_missing_and_empty_dump_are_not_success(tmp_path):
    with pytest.raises(ValueError, match="exactly one"):
        gate.verify_dump(tmp_path, compiler=True, source="none", max_calls=0)
    task = tmp_path / "tasks" / "x"
    task.mkdir(parents=True)
    (task / "task_summary.json").write_text('{"verdict":"UNKNOWN","llm_api_calls":0}')
    (task / "refinements.jsonl").write_text("")
    with pytest.raises(ValueError, match="empty"):
        gate.verify_dump(tmp_path, compiler=True, source="none", max_calls=0)


def test_native_true_is_counted_as_not_lowered():
    row = compiler_row()
    payload = row["precision_compiler"]
    payload.pop("sha256")
    payload["candidates"][0]["antecedent_formula"] = "(assert true)"
    payload["sha256"] = hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode()
    ).hexdigest()
    row["precision_local_after"] = {}
    assert gate.verify_compiler(row) == 0


def recorded_dump(tmp_path):
    task = tmp_path / "tasks" / "x"
    task.mkdir(parents=True)
    prompt = "first prompt"
    response = '{"schema_version":"loop-head-candidate-v1","candidates":[]}'
    call = {
        "refinement_index": 1,
        "request_hash": "a" * 64,
        "prompt_path": "prompt.txt",
        "prompt_hash": gate.sha256(prompt.encode()),
        "response_raw": response,
        "response_hash": gate.sha256(response.encode()),
        "response_source": "live_recorded",
        "usage": None,
    }
    row = {
        "refinement_index": 1,
        "llm_called": True,
        "precision_compiler": None,
        "native_predicate_context": {"predicates": [], "omitted": 0},
        "validated_predicates": [],
        "candidate_rejections": [],
        "precision_injected": [],
    }
    (task / "prompt.txt").write_text(prompt)
    (task / "llm_rounds.jsonl").write_text(json.dumps(call) + "\n")
    (task / "refinements.jsonl").write_text(json.dumps(row) + "\n")
    (task / "task_summary.json").write_text('{"verdict":"UNKNOWN","llm_api_calls":1}')
    return task


def test_unknown_cost_and_tampered_prompt(tmp_path):
    task = recorded_dump(tmp_path)
    result = gate.verify_dump(tmp_path, False, "live_recorded", 1)
    assert result["usage_complete"] is False
    assert result["usage"]["total_tokens"] is None
    (task / "prompt.txt").write_text("changed")
    with pytest.raises(ValueError, match="prompt hash"):
        gate.verify_dump(tmp_path, False, "live_recorded", 1)


def test_compiler_only_does_not_accept_recorded_call(tmp_path):
    recorded_dump(tmp_path)
    with pytest.raises(ValueError, match="call ledger/budget"):
        gate.verify_dump(tmp_path, True, "none", 0)
