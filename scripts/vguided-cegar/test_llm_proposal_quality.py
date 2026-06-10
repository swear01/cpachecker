#!/usr/bin/env python3
"""Sample DeepSeek predicate proposals; score JSON + L1 contract (aligned with Java validator).

Parallel by default (VGUIDE_LLM_QUALITY_PARALLEL or PARALLEL, default 16).
DeepSeek API rate limit ~500/min — safe to run many concurrent HTTP calls.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-v4-pro"
RUNS = int(os.environ.get("VGUIDE_LLM_QUALITY_RUNS", "5"))
PARALLEL = int(
    os.environ.get(
        "VGUIDE_LLM_QUALITY_PARALLEL",
        os.environ.get("PARALLEL", "16"),
    )
)
MAX_PREDS = 12

FORBIDDEN = [
    (re.compile(r"\|[a-z_]\w+::"), "internal_pipe"),
    (re.compile(r"\.def_\d+"), "def_term"),
    (re.compile(r"(?<!\|)\b\w+@\d+\b"), "ssa_suffix"),
    (re.compile(r"\b[A-Za-z_]\w*\s*\["), "c_array_subscript"),
    (re.compile(r"\bselect\b"), "select"),
    (re.compile(r"\bstore\b"), "store"),
    (re.compile(r"\bbvshl\b"), "bvshl"),
    (re.compile(r"\bbvlshr\b"), "bvlshr"),
    (re.compile(r"\bbvashr\b"), "bvashr"),
]

RULES = """RULES (violations are discarded automatically):
- Use ONLY source variable names from the allowed list.
- SMT-LIB2 prefix notation; each predicate must start with '('.
- Prefer bitvector ops for 32-bit ints: bvsge, bvslt, bvsle, bvsgt, bvadd, bvsub, = .
- Do NOT use: |main::...|, @suffix, .def_N, select, store, quantifiers, bvshl/lshr/ashr.
- Do NOT use C syntax: A[i], *p, struct fields.
"""

JSON_CONTRACT = (
    "Output ONLY valid JSON (no markdown, no commentary):\n"
    '{"predicates": ["(bvsge i (_ bv0 32))", "(bvslt i n)"]}\n'
    "Between 4 and 8 items. Do NOT use N* location keys; Java binds predicates to all loop heads."
)

DUAL_PROFILES = os.environ.get("VGUIDE_LLM_QUALITY_DUAL", "true").lower() in (
    "1",
    "true",
    "on",
    "yes",
)

SCALAR_DECL = re.compile(r"\bint\s+([A-Za-z_]\w*)\s*;")
ARRAY_DECL = re.compile(r"\bint\s+([A-Za-z_]\w*)\s*\[")


def contract_ok(pred: str) -> tuple[bool, str]:
    s = pred.strip()
    if not s.startswith("("):
        return False, "not_sexp"
    for pat, code in FORBIDDEN:
        if pat.search(s):
            return False, code
    return True, "ok"


def sanitize(preds: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for p in preds:
        p = p.strip()
        if not p or p in seen:
            continue
        if contract_ok(p)[0]:
            seen.add(p)
            out.append(p)
        if len(out) >= MAX_PREDS:
            break
    return out


def json_candidates(text: str) -> list[str]:
    t = text.strip()
    if "```" in t:
        t = re.sub(r"(?s)```(?:json)?\s*", " ", t).replace("```", " ").strip()
    out = [t]
    start = t.find("{")
    if start >= 0:
        depth = 0
        for i, c in enumerate(t[start:], start):
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    out.append(t[start : i + 1])
                    break
    return out


def parse_predicates(text: str) -> list[str]:
    for cand in json_candidates(text):
        try:
            root = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(root, dict) and "predicates" in root and isinstance(root["predicates"], list):
            raw = [p.strip() for p in root["predicates"] if isinstance(p, str) and p.strip()]
            if raw:
                return sanitize(raw)
        if isinstance(root, dict):
            flat: list[str] = []
            for v in root.values():
                if isinstance(v, list):
                    flat.extend(p.strip() for p in v if isinstance(p, str) and p.strip())
            if flat:
                return sanitize(flat)
    return []


def scalar_names(source: str) -> list[str]:
    scalars = {m.group(1) for m in SCALAR_DECL.finditer(source)}
    arrays = {m.group(1) for m in ARRAY_DECL.finditer(source)}
    return sorted(scalars - arrays)


def variable_hints(source: str) -> str:
    scalars = scalar_names(source)
    lines = []
    if scalars:
        lines.append(f"Allowed scalar variables (use ONLY these names): {scalars}")
    if ARRAY_DECL.search(source):
        lines.append(
            "Array program: do NOT use array identifiers (e.g. A) or C subscripts (A[i]).\n"
            "BAD (rejected): (= A[i] 0), (select A i)\n"
            "GOOD: (bvsge i (_ bv0 32)), (bvsle i (_ bv1024 32))"
        )
    return "\n".join(lines) + ("\n" if lines else "")


def task_examples(source: str, assertion: str) -> str:
    if "int k" in source and "int i" in source and "int n" in source:
        return """
Examples (scalar loop / counter):
  (bvsge i (_ bv0 32)), (bvsge k (_ bv0 32)), (bvslt i n), (= k i), (bvsle i n)
"""
    if ARRAY_DECL.search(source):
        return """
Examples (array search — index scalars ONLY):
  (bvsge i (_ bv0 32)), (bvsle i (_ bv1024 32)), (bvslt i (_ bv1024 32))
NEVER output: (= A[i] 0) or any predicate mentioning array names.
"""
    if "i" in assertion and "j" in assertion:
        return """
Examples (multi-index):
  (bvsge i (_ bv0 32)), (bvsge j (_ bv0 32)), (bvslt i (_ bv100 32))
"""
    return ""


def build_system_message() -> str:
    return (
        "You help a CEGAR-based predicate abstraction verifier.\n"
        "Propose candidate abstraction predicates in SMT-LIB2 prefix notation.\n"
        + RULES
        + "\n"
        + JSON_CONTRACT
    )


def profile_role(profile: str) -> str:
    if profile == "BUG_HUNT":
        return (
            "Goal: help the verifier reach or refine toward assertion FAILURE if reachable.\n"
            "This is the FIRST spurious counterexample in this analysis.\n"
            "Propose predicates that distinguish states that can lead to assertion failure.\n"
            "Do NOT only propose predicates that imply the assertion always holds.\n"
        )
    return (
        "Goal: split spurious counterexample paths and strengthen safe abstraction.\n"
        "This is the FIRST spurious counterexample in this analysis.\n"
        "Propose abstraction predicates that help split similar spurious paths.\n"
        "Focus on loop-carried relations, guards, bounds, and assertion variables.\n"
    )


def assertion_line(assertion: str, profile: str) -> str:
    if not assertion:
        return ""
    if profile == "BUG_HUNT":
        return f"Assertion (may FAIL on real paths): {assertion}\n"
    return f"Target assertion: {assertion}\n"


def build_user_message(source: str, assertion: str, task: str, profile: str) -> str:
    ce_summary = "(no CE relations extracted)\n"
    budget = (
        "PREDICATE BUDGET (single API response — array order = priority, best first):\n"
        "- Return between 4 and 8 predicates.\n"
    )
    if profile == "BUG_HUNT":
        budget += "- Prefer assertion-failure or violation-state discriminators.\n"
    return (
        "LOOP HEADS (inject predicates here — use source variable names only):\n"
        "  (loop heads omitted in offline sample)\n\n"
        + variable_hints(source)
        + "\nSource code:\n"
        + source
        + "\n"
        + assertion_line(assertion, profile)
        + profile_role(profile)
        + task_examples(source, assertion)
        + "\nSPURIOUS CE SUMMARY (source variable names only, read-only):\n"
        + ce_summary
        + "\n"
        + budget
        + f"Task benchmark: {task}\n"
    )


def build_repair_user(source: str, assertion: str, task: str, profile: str, bad: list[str]) -> str:
    hint = (
        "Rejected predicates may have been too aligned with proving safe; "
        "try failing-state predicates from the CE summary.\n"
        if profile == "BUG_HUNT"
        else ""
    )
    return (
        build_user_message(source, assertion, task, profile)
        + "\nYour previous reply included REJECTED predicates: "
        + json.dumps(bad)
        + "\n"
        + hint
        + "Regenerate JSON only. Remove array subscripts, internal SSA names, select/store.\n"
    )


def llm_thinking_body() -> dict:
    """Match PredicateProposalClient: V4 defaults to thinking; we opt out unless enabled."""
    mode = os.environ.get("VGUIDE_LLM_THINKING", "disabled").strip().lower()
    if mode in ("enabled", "true", "on", "1"):
        effort = os.environ.get("VGUIDE_LLM_REASONING_EFFORT", "high").strip().lower()
        if effort in ("max", "xhigh"):
            effort = "max"
        else:
            effort = "high"
        return {"thinking": {"type": "enabled"}, "reasoning_effort": effort}
    return {"thinking": {"type": "disabled"}}


def call_llm(system: str, user: str) -> str:
    key = os.environ["DEEPSEEK_API_KEY"]
    model = os.environ.get("DEEPSEEK_MODEL", DEFAULT_MODEL)
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})
    payload = {
        "model": model,
        "temperature": 0,
        "max_completion_tokens": 1024,
        "response_format": {"type": "json_object"},
        "messages": messages,
        **llm_thinking_body(),
    }
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


def read_source(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def extract_assertion(source: str) -> str:
    m = re.search(r"__VERIFIER_assert\s*\(\s*(.+?)\s*\)", source, re.DOTALL)
    return m.group(1).strip() if m else ""


def eval_one_run(
    name: str,
    source: str,
    assertion: str,
    profile: str,
    run_idx: int,
) -> dict:
    system = build_system_message()
    user = build_user_message(source, assertion, name, profile)
    t0 = time.time()
    try:
        raw = call_llm(system, user)
        latency = time.time() - t0
        preds = parse_predicates(raw)
        raw_preds: list[str] = []
        for cand in json_candidates(raw):
            try:
                root = json.loads(cand)
                if isinstance(root, dict) and isinstance(root.get("predicates"), list):
                    raw_preds = [p for p in root["predicates"] if isinstance(p, str)]
            except json.JSONDecodeError:
                continue
        rejected = [
            p.strip() for p in raw_preds if p.strip() and not contract_ok(p.strip())[0]
        ]
        repaired = False
        if (not preds or rejected) and rejected:
            t1 = time.time()
            raw2 = call_llm(
                system,
                build_repair_user(source, assertion, name, profile, rejected[:5]),
            )
            latency += time.time() - t1
            preds2 = parse_predicates(raw2)
            if preds2:
                preds = preds2
                repaired = True
        c_ok = sum(1 for p in preds if contract_ok(p)[0])
        return {
            "run": run_idx,
            "profile": profile,
            "latency_s": round(latency, 2),
            "len": len(raw),
            "predicates": preds[:8],
            "contract_ok": c_ok,
            "rejected_in_raw": rejected[:5],
            "ok_json": len(preds) > 0,
            "pred_count": len(preds),
            "repaired": repaired,
        }
    except Exception as e:
        return {
            "run": run_idx,
            "profile": profile,
            "error": str(e),
            "ok_json": False,
            "pred_count": 0,
            "contract_ok": 0,
        }


def eval_task(name: str, path: str) -> list[dict]:
    source = read_source(path)
    assertion = extract_assertion(source)
    profiles = ["SAFE", "BUG_HUNT"] if DUAL_PROFILES else ["SAFE"]
    all_stats: list[dict] = []
    for profile in profiles:
        stats = {
            "task": name,
            "path": path,
            "profile": profile,
            "dual_profiles": DUAL_PROFILES,
            "runs": RUNS,
            "parallel": PARALLEL,
            "ok_json": 0,
            "total_preds": 0,
            "contract_ok": 0,
            "repaired": 0,
            "samples": [],
        }
        jobs = [(name, source, assertion, profile, i + 1) for i in range(RUNS)]
        samples: list[dict] = []
        with ThreadPoolExecutor(max_workers=min(PARALLEL, len(jobs))) as pool:
            futures = {
                pool.submit(eval_one_run, *args): args[4] for args in jobs
            }
            for fut in as_completed(futures):
                samples.append(fut.result())
        samples.sort(key=lambda s: s.get("run", 0))
        for s in samples:
            if "error" in s and "ok_json" not in s:
                stats["samples"].append(s)
                continue
            if s.get("ok_json"):
                stats["ok_json"] += 1
            stats["total_preds"] += s.get("pred_count", 0)
            stats["contract_ok"] += s.get("contract_ok", 0)
            if s.get("repaired"):
                stats["repaired"] += 1
            stats["samples"].append(
                {
                    k: s[k]
                    for k in (
                        "run",
                        "profile",
                        "latency_s",
                        "len",
                        "predicates",
                        "contract_ok",
                        "rejected_in_raw",
                        "error",
                    )
                    if k in s
                }
            )
        all_stats.append(stats)
    return all_stats


def quality_pass(all_stats: list[dict]) -> tuple[bool, list[str]]:
    issues = []
    for st in all_stats:
        task = st["task"]
        label = f"{task}/{st.get('profile', 'SAFE')}"
        if st["ok_json"] < st["runs"]:
            issues.append(f"{label}: json_ok {st['ok_json']}/{st['runs']}")
        if st["contract_ok"] < st["total_preds"]:
            issues.append(f"{label}: contract_ok {st['contract_ok']}/{st['total_preds']}")
        for s in st["samples"]:
            if "predicates" in s:
                for p in s["predicates"]:
                    if not contract_ok(p)[0]:
                        issues.append(f"{task} run{s['run']}: bad pred {p}")
            if task == "array_3-1" and "predicates" in s:
                for p in s["predicates"]:
                    if "A" in p or "[" in p:
                        issues.append(f"{task} run{s['run']}: array syntax in {p}")
    return len(issues) == 0, issues


def main() -> int:
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("DEEPSEEK_API_KEY required", file=sys.stderr)
        return 1
    bench_root = os.environ.get(
        "VGUIDE_BENCH_ROOT",
        os.environ.get("SV_BENCHMARKS", os.path.expanduser("~/sv-benchmarks/c")),
    )
    tasks = os.environ.get(
        "VGUIDE_LLM_QUALITY_TASKS", "up,down,array_3-1,string_concat-noarr"
    ).split(",")
    paths = {
        "up": f"{bench_root}/loop-invgen/up.i",
        "down": f"{bench_root}/loop-invgen/down.i",
        "array_3-1": f"{bench_root}/loop-acceleration/array_3-1.i",
        "string_concat-noarr": f"{bench_root}/loop-invgen/string_concat-noarr.i",
    }
    work: list[tuple[str, str]] = []
    for task in tasks:
        task = task.strip()
        if task not in paths or not os.path.isfile(paths[task]):
            print(f"skip {task}: file not found", file=sys.stderr)
            continue
        work.append((task, paths[task]))

    print(
        f"Parallel={PARALLEL} runs_per_task={RUNS} dual={DUAL_PROFILES} tasks={len(work)}",
        flush=True,
    )
    all_stats: list[dict] = []
    with ThreadPoolExecutor(max_workers=min(PARALLEL, max(len(work), 1))) as pool:
        futures = {pool.submit(eval_task, t, p): t for t, p in work}
        for fut in as_completed(futures):
            task = futures[fut]
            task_stats = fut.result()
            all_stats.extend(task_stats)
            for st in task_stats:
                print(
                    f"=== {task} profile={st['profile']} "
                    f"({RUNS} runs, parallel={st.get('parallel', PARALLEL)}) ===",
                    flush=True,
                )
                print(
                    f"  json_ok={st['ok_json']}/{RUNS} "
                    f"preds={st['total_preds']} contract_ok={st['contract_ok']} "
                    f"repaired={st['repaired']}",
                    flush=True,
                )
                for s in st["samples"]:
                    if "error" in s:
                        print(f"  run {s['run']}: ERROR {s['error']}")
                    else:
                        print(
                            f"  run {s['run']}: {s['latency_s']}s len={s['len']} "
                            f"preds={s['predicates']}"
                        )
    all_stats.sort(key=lambda x: (x["task"], x.get("profile", "")))
    out = os.environ.get("VGUIDE_LLM_QUALITY_OUT", "output/vguide/llm_quality_sample.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_stats, f, indent=2)
    print(f"Wrote {out}")
    ok, issues = quality_pass(all_stats)
    if not ok:
        print("QUALITY FAIL:", file=sys.stderr)
        for i in issues:
            print(f"  - {i}", file=sys.stderr)
        return 2
    print("QUALITY PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
