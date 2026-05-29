#!/usr/bin/env python3
"""B5 Phase 2: Call DeepSeek with B5 repair prompt and analyze generated predicates.

Usage: python3 b5_repair_from_prompt.py <prompt.md> <dump_dir> [--output <out_dir>]
"""

import json
import hashlib
import os
import re
import subprocess
import sys
import time
from pathlib import Path


def call_deepseek(prompt, api_key):
    """Call DeepSeek API and return raw response text."""
    import json as j
    body = j.dumps({
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_completion_tokens": 1024
    })
    try:
        resp = subprocess.run([
            "curl", "-s", "https://api.deepseek.com/chat/completions",
            "-H", f"Authorization: Bearer {api_key}",
            "-H", "Content-Type: application/json",
            "-d", body
        ], capture_output=True, text=True, timeout=120)
        result = json.loads(resp.stdout)
        return result.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        return f"API_ERROR: {e}"


def sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def llm_cache_dir():
    d = os.environ.get("VGUIDE_LLM_CACHE_DIR", "")
    return Path(d) if d else None


def load_cached_response(prompt_hash):
    cache = llm_cache_dir()
    if not cache:
        return None
    response_file = cache / prompt_hash / "response.txt"
    if response_file.exists():
        return response_file.read_text()
    return None


def save_cached_call(prompt_hash, prompt_text, response_text, call_site, benchmark=""):
    cache = llm_cache_dir()
    if not cache:
        return
    try:
        d = cache / prompt_hash
        d.mkdir(parents=True, exist_ok=True)
        (d / "prompt.txt").write_text(prompt_text)
        (d / "response.txt").write_text(response_text)
        meta = {
            "hash": prompt_hash,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "model": "deepseek-chat",
            "call_site": call_site,
            "benchmark": benchmark,
            "prompt_chars": len(prompt_text),
            "response_chars": len(response_text),
        }
        (d / "metadata.json").write_text(json.dumps(meta, indent=2))
        print(f"  LLM record saved: {prompt_hash}")
    except Exception as e:
        print(f"  WARNING: failed to save LLM cache: {e}")


def parse_candidates(raw_output):
    """Parse JSON predicate candidates from LLM output."""
    text = raw_output.strip()
    if '```' in text:
        m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if m:
            text = m.group(1).strip()
        else:
            text = re.sub(r'```(?:json)?\s*', '', text).replace('```', '')

    # Try direct JSON parse
    for attempt in range(5):
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass
        # Try regex extraction with balanced braces
        m = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
        if m:
            text = m.group()
        else:
            break
    return {}


def load_context(dump_dir):
    """Load context from B5 dump summaries for comparison."""
    dump_path = Path(dump_dir)
    context = {
        "entailed": set(),
        "candidates": set(),
        "global_precision": set(),
    }

    for jf in sorted(dump_path.glob("refinement_*.json")):
        with open(jf) as f:
            d = json.load(f)

        fates = d.get("candidate_fates", {})
        for item in fates.get("entailed", []):
            context["entailed"].add(normalize_pred(item.get("smt", "")))
        for item in fates.get("abstraction_candidates", []):
            context["candidates"].add(normalize_pred(item.get("smt", "")))

        prec = d.get("precision", {})
        if prec:
            for p in prec.get("global_predicates", []):
                context["global_precision"].add(normalize_pred(p.get("smt", "")))

    return context


def normalize_pred(smt_text):
    """Normalize predicate SMT text for comparison."""
    if not smt_text:
        return ""
    s = smt_text.strip()
    s = re.sub(r'\s+', ' ', s)
    return s[:200]


def extract_assertion_vars(source_code):
    """Extract assertion variables from source."""
    for m in re.finditer(r'__VERIFIER_assert\s*\(', source_code):
        start = m.end()
        depth = 1
        i = start
        while i < len(source_code) and depth > 0:
            if source_code[i] == '(': depth += 1
            elif source_code[i] == ')': depth -= 1
            i += 1
        if depth != 0: continue
        expr = source_code[start:i-1]
        if re.match(r'^(int|unsigned|void|char|long|short|float|double|bool|_Bool)\s+\w+\s*$', expr):
            continue
        return list(set(re.findall(r'\b([a-zA-Z_]\w*)\b', expr)))
    return []


def classify_predicate(pred_text, assertion_vars, existing_context):
    """Classify a generated predicate."""
    result = {
        "predicate": pred_text,
        "parse_status": "OK",
        "new_or_duplicate": "NEW",
        "relation_type": "unknown",
        "likely_useful": "maybe",
        "reason": ""
    }
    reasons = []

    norm = normalize_pred(pred_text)
    if not norm or len(norm) < 3:
        result["parse_status"] = "EMPTY"
        return result

    # Check duplicates
    if norm in existing_context["entailed"]:
        result["new_or_duplicate"] = "DUPLICATE"
        result["likely_useful"] = "no"
        reasons.append("duplicate of entailed predicate")
    elif norm in existing_context["candidates"]:
        result["new_or_duplicate"] = "DUPLICATE"
        result["likely_useful"] = "no"
        reasons.append("duplicate of existing abstraction candidate")
    elif norm in existing_context["global_precision"]:
        result["new_or_duplicate"] = "DUPLICATE"
        result["likely_useful"] = "no"
        reasons.append("already in precision")

    # Classification
    vars_in_pred = set(re.findall(r'\b([a-zA-Z_]\w*)\b', pred_text))
    _bv_vars = set(re.findall(r'_ bv(\d+)', pred_text))

    if 'bvurem' in pred_text or 'mod' in pred_text.lower():
        result["relation_type"] = "modulo"
        reasons.append("modulo predicate")
    elif 'bvmul' in pred_text or '*' in pred_text:
        result["relation_type"] = "accumulator"
        reasons.append("accumulator relation")
    elif 'bvslt' in pred_text or 'bvsgt' in pred_text or 'bvsle' in pred_text or 'bvsge' in pred_text:
        if len(vars_in_pred) >= 2:
            result["relation_type"] = "relational_comparison"
            reasons.append("relational comparison (2+ vars)")
        else:
            result["relation_type"] = "scalar_bound"
            reasons.append("scalar bound")
    elif '=' in pred_text:
        if len(vars_in_pred) >= 2:
            result["relation_type"] = "relational_equality"
            reasons.append("relational equality (2+ vars)")
        else:
            result["relation_type"] = "value_constraint"
            reasons.append("value constraint")
    elif len(vars_in_pred) >= 2:
        result["relation_type"] = "relational"
    elif len(vars_in_pred) == 1:
        result["relation_type"] = "unary"

    # Assertion variable overlap
    assertion_overlap = vars_in_pred & set(assertion_vars)
    if assertion_overlap:
        reasons.append(f"mentions assertion vars: {', '.join(sorted(assertion_overlap))}")
        if len(vars_in_pred) >= 2:
            result["likely_useful"] = "yes"
            reasons.append("relational + assertion-var overlap")

    # New non-trivial predicates
    if result["new_or_duplicate"] == "NEW":
        if len(vars_in_pred) >= 2:
            result["likely_useful"] = "yes"
        elif len(vars_in_pred) == 1 and result["relation_type"] in ("scalar_bound", "value_constraint"):
            result["likely_useful"] = "probably"
            reasons.append("single-var bound may be useful")

    result["reason"] = "; ".join(reasons) if reasons else "no special classification"
    return result


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 b5_repair_from_prompt.py <prompt.md> <dump_dir> [--output <out_dir>]")
        sys.exit(1)

    prompt_file = sys.argv[1]
    dump_dir = sys.argv[2]
    out_dir = dump_dir

    if len(sys.argv) > 3 and sys.argv[3] == "--output":
        out_dir = sys.argv[4]

    prompt = Path(prompt_file).read_text()
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not set")
        sys.exit(1)

    print(f"=== B5 repair: {os.path.basename(prompt_file)} ===")
    print(f"  prompt size: {len(prompt)} chars, ~{len(prompt)//4} tokens")

    # Find source file from prompt
    source_code = ""
    m = re.search(r'## Source Code\n```c?\n(.*?)\n```', prompt, re.DOTALL)
    if m:
        source_code = m.group(1)

    assertion_vars = extract_assertion_vars(source_code)
    print(f"  assertion vars: {assertion_vars}")

    existing = load_context(dump_dir)
    print(f"  existing: entailed={len(existing['entailed'])} candidates={len(existing['candidates'])} precision={len(existing['global_precision'])}")

    # Call DeepSeek (with record/replay support)
    prompt_hash = sha256(prompt)
    print(f"  prompt hash: {prompt_hash}")
    record_mode = os.environ.get("VGUIDE_LLM_RECORD", "") == "1"
    replay_mode = os.environ.get("VGUIDE_LLM_REPLAY", "") == "1"

    if replay_mode:
        cached = load_cached_response(prompt_hash)
        if cached is None:
            print(f"  ERROR: replay cache miss for hash {prompt_hash}")
            sys.exit(1)
        print("  LLM replay hit")
        raw_output = cached
    else:
        print("  calling DeepSeek...")
        raw_output = call_deepseek(prompt, api_key)
        if record_mode:
            bench_name = os.path.splitext(os.path.basename(prompt_file))[0]
            save_cached_call(prompt_hash, prompt, raw_output, "B5_PYTHON", bench_name)
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    raw_file = Path(out_dir) / "b5_llm_raw_response.txt"
    raw_file.write_text(raw_output)
    print(f"  raw response: {len(raw_output)} chars")

    # Parse candidates
    candidates = parse_candidates(raw_output)
    candidate_file = Path(out_dir) / "b5_repair_candidates.json"
    candidate_file.write_text(json.dumps(candidates, indent=2))
    total = sum(len(v) for v in candidates.values()) if candidates else 0
    print(f"  parsed: {total} predicates from {len(candidates)} locations")

    # Validate candidates against output contract
    from b5_validate_candidates import validate_candidates as vc_validate
    valid_candidates, rejected_list, validation_report = vc_validate(candidates)
    validated_file = Path(out_dir) / "repair_candidates_validated.json"
    rejected_file = Path(out_dir) / "rejected_candidates.json"
    validated_file.write_text(json.dumps(valid_candidates, indent=2))
    rejected_file.write_text(json.dumps(rejected_list, indent=2))
    valid_total = sum(len(v) for v in valid_candidates.values()) if valid_candidates else 0
    rejected_total = sum(len(v) for v in rejected_list) if rejected_list else 0
    print(f"  validated: {valid_total} accepted, {rejected_total} rejected")
    if rejected_total > 0:
        print("  rejected reasons:")
        for r in rejected_list[:5]:
            print(f"    [{r['reason']}] {r.get('location','?')}: {r['predicate'][:80]}")

    # Analyze predicates
    print()
    print("=== Diagnosis Table ===")
    rows = []
    for loc, preds in sorted(candidates.items()):
        for pred in preds:
            classification = classify_predicate(pred, assertion_vars, existing)
            rows.append([loc, pred, classification])
            print(f"  [{classification['parse_status']}] [{classification['new_or_duplicate']}] [{classification['relation_type']}] [{classification['likely_useful']}]")
            print(f"    location: {loc}")
            print(f"    predicate: {pred}")
            print(f"    reason: {classification['reason']}")
            print()

    # Summary
    new_count = sum(1 for r in rows if r[2]['new_or_duplicate'] == 'NEW')
    dup_count = sum(1 for r in rows if r[2]['new_or_duplicate'] == 'DUPLICATE')
    useful_count = sum(1 for r in rows if r[2]['likely_useful'] == 'yes')
    print(f"=== Summary ===")
    print(f"  total: {len(rows)}, new: {new_count}, duplicate: {dup_count}, likely-useful: {useful_count}")

    # Write CSV
    csv_file = Path(out_dir) / "b5_diagnosis.csv"
    with open(csv_file, "w") as f:
        f.write("location,predicate,parse_status,new_or_duplicate,relation_type,likely_useful,reason\n")
        for row in rows:
            loc, pred, cls = row
            pred_escaped = pred.replace('"', '""')
            f.write(f'{loc},"{pred_escaped}",{cls["parse_status"]},{cls["new_or_duplicate"]},'
                    f'{cls["relation_type"]},{cls["likely_useful"]},"{cls["reason"]}"\n')
    print(f"  diagnosis written to {csv_file}")


if __name__ == "__main__":
    main()
