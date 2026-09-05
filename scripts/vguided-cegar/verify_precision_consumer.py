#!/usr/bin/env python3
"""Audit complete precision-compiler lowering and strict consumer record/replay evidence.

Run on an intact analysis dump with --compiler for compiler-enabled arms and
--source live_recorded/replay for model arms. --replay-of requires every recorded
call and every call-site candidate, rejection, injection and native-context field
in the replay. CPU-limit endpoint refinement counts are descriptive, not equalities.
Native TRUE candidates are retained in dumps and counted separately: the native
getPredicateFor API rejects tautologies, so they are not effective injections.
This checks evidence integrity, not soundness, labels or population performance.
"""

import argparse
import hashlib
import json
from pathlib import Path


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_rows(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def canonical(formula):
    return " ".join(formula.split())


def verify_compiler(row):
    compiler = row.get("precision_compiler")
    require(isinstance(compiler, dict), "missing compiler dump")
    payload = {k: v for k, v in compiler.items() if k != "sha256"}
    actual = sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    )
    require(compiler.get("sha256") == actual, "compiler hash mismatch")
    require(
        compiler["schema_version"] == "cfa-precision-compiler-v2",
        "compiler schema mismatch",
    )
    lowered = 0
    for candidate in compiler["candidates"]:
        require(
            candidate["abstraction_role"] == "PRECISION_ONLY", "compiler role mismatch"
        )
        if canonical(candidate["antecedent_formula"]) == "(assert true)":
            continue
        lowered += 1
        head = candidate["consequent_head"]
        after = row["precision_local_after"].get(head, [])
        require(
            canonical(candidate["antecedent_formula"]) in map(canonical, after),
            f"compiler lowering missing at {head}",
        )
    return lowered


def verify_native_context(context, prompt):
    require(isinstance(context, dict), "missing native context")
    if context["predicates"]:
        require(
            "NATIVE CEGAR PRECISION (read-only):" in prompt,
            "native exposure block missing",
        )
    for entry in context["predicates"]:
        line = f"[{entry['scope']} | {entry['origin']}] {entry['smt']}"
        require(line in prompt, "native exposure entry missing")
    require(
        type(context["omitted"]) is int and context["omitted"] >= 0,
        "invalid native omission count",
    )
    return len(context["predicates"])


def verify_replay(record_calls, record_rows, replay_calls, replay_rows):
    call_fields = (
        "refinement_index",
        "request_hash",
        "response_hash",
        "prompt_hash",
        "response_raw",
        "response_parse_ok",
        "predicates_raw",
        "predicates_rejected",
        "usage",
    )
    require(
        [[r[k] for k in call_fields] for r in record_calls]
        == [[r[k] for k in call_fields] for r in replay_calls],
        "replay calls differ",
    )
    fields = (
        "refinement_index",
        "validated_predicates",
        "candidate_rejections",
        "precision_injected",
        "precision_compiler",
        "native_predicate_context",
    )
    require(
        [[r[k] for k in fields] for r in record_rows if r["llm_called"]]
        == [[r[k] for k in fields] for r in replay_rows if r["llm_called"]],
        "replay call-site evidence differs",
    )


def task_data(dump):
    summaries = list(dump.glob("tasks/*/task_summary.json"))
    require(len(summaries) == 1, "expected exactly one task summary")
    task = summaries[0].parent
    summary = json.loads(summaries[0].read_text(encoding="utf-8"))
    rows = read_rows(task / "refinements.jsonl")
    require(bool(rows), "empty refinement ledger")
    calls_path = task / "llm_rounds.jsonl"
    calls = read_rows(calls_path) if calls_path.exists() else []
    return task, summary, rows, calls


def verify_dump(dump, compiler, source, max_calls, cache=None, replay_of=None):
    task, summary, rows, calls = task_data(dump)
    require(summary["verdict"] in {"TRUE", "FALSE", "UNKNOWN"}, "missing real verdict")
    require(
        summary["llm_api_calls"] == len(calls) <= max_calls,
        "call ledger/budget mismatch",
    )
    require(source != "none" or not calls, "nonzero compiler-only model calls")
    called = [r for r in rows if r["llm_called"]]
    require(
        [r["refinement_index"] for r in called]
        == [r["refinement_index"] for r in calls],
        "call/refinement alignment mismatch",
    )
    require(
        not any(r.get("llm_skip_reason") == "llm_failed" for r in rows),
        "provider/replay failure",
    )
    candidates = 0
    for row in rows:
        if compiler:
            candidates += verify_compiler(row)
        else:
            require(
                row.get("precision_compiler") is None, "unexpected compiler evidence"
            )
    exposed = omitted = 0
    for call, row in zip(calls, called):
        require(call["response_source"] == source, "response source mismatch")
        prompt_path = (task / call["prompt_path"]).resolve()
        require(prompt_path.is_relative_to(task.resolve()), "prompt path escapes task")
        prompt = prompt_path.read_bytes()
        require(sha256(prompt) == call["prompt_hash"], "prompt hash mismatch")
        require(
            sha256(call["response_raw"].encode()) == call["response_hash"],
            "response hash mismatch",
        )
        require(
            len(call["request_hash"]) == 64
            and all(c in "0123456789abcdef" for c in call["request_hash"]),
            "invalid request hash",
        )
        response = json.loads(call["response_raw"])
        require(
            response.get("schema_version") == "loop-head-candidate-v1"
            and isinstance(response.get("candidates"), list),
            "invalid response schema",
        )
        exposed += verify_native_context(
            row["native_predicate_context"], prompt.decode()
        )
        omitted += row["native_predicate_context"]["omitted"]
        require(
            all(
                p["classification"] == "PRECISION_ONLY"
                for p in row["validated_predicates"]
            ),
            "LLM role mismatch",
        )
    if cache is not None:
        cache_rows = []
        for path in sorted(cache.rglob("*.json")):
            entry = json.loads(path.read_text(encoding="utf-8"))
            require(
                entry["schema_version"] == 1
                and path.parent.name == entry["request_hash"],
                "cache request/schema mismatch",
            )
            require(
                path.name == f"{entry['ordinal']:06d}.json", "cache ordinal mismatch"
            )
            cache_rows.append(
                (
                    entry["request_hash"],
                    sha256(entry["content"].encode()),
                    entry["ordinal"],
                )
            )
        ordinals = {}
        expected = []
        for call in calls:
            key = call["request_hash"]
            ordinals[key] = ordinals.get(key, 0) + 1
            expected.append((key, call["response_hash"], ordinals[key]))
        require(sorted(cache_rows) == sorted(expected), "complete cache/call mismatch")
    if replay_of is not None:
        _, live_summary, live_rows, live_calls = task_data(replay_of)
        require(
            all(c["response_source"] == "live_recorded" for c in live_calls),
            "reference is not live recorded",
        )
        require(source == "replay", "replay source required")
        verify_replay(live_calls, live_rows, calls, rows)
        require(summary["verdict"] == live_summary["verdict"], "replay verdict differs")
    usage = [c.get("usage") for c in calls]
    totals = {
        key: sum(u[key] for u in usage)
        if all(
            isinstance(u, dict) and type(u.get(key)) is int and u[key] >= 0
            for u in usage
        )
        else None
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
    }
    return {
        "verdict": summary["verdict"],
        "refinements": summary.get("refinements"),
        "compiler_candidates_lowered": candidates,
        "compiler_true_candidates_not_lowered": sum(
            len(r["precision_compiler"]["candidates"]) for r in rows
        )
        - candidates
        if compiler
        else 0,
        "calls": len(calls),
        "recorded_responses": len(calls) if source == "live_recorded" else 0,
        "replayed_responses": len(calls) if source == "replay" else 0,
        "native_context_entries_exposed": exposed,
        "native_context_entries_omitted": omitted,
        "validated": sum(len(r["validated_predicates"]) for r in called),
        "injected": sum(len(r["precision_injected"]) for r in called),
        "rejections": sum(len(r["candidate_rejections"]) for r in called),
        "usage_complete": all(value is not None for value in totals.values()),
        "usage": totals,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump", required=True, type=Path)
    parser.add_argument("--compiler", action="store_true")
    parser.add_argument(
        "--source", choices=("none", "live_recorded", "replay"), default="none"
    )
    parser.add_argument("--max-calls", type=int, required=True)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--replay-of", type=Path)
    args = parser.parse_args()
    try:
        result = verify_dump(
            args.dump,
            args.compiler,
            args.source,
            args.max_calls,
            args.cache,
            args.replay_of,
        )
    except (KeyError, TypeError, AttributeError, OSError, ValueError) as error:
        parser.exit(1, f"Invalid consumer evidence ({type(error).__name__}): {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
