#!/usr/bin/env python3
"""Bootstrap candidate generator — call LLM for initial precision predicates.

Usage: python3 bootstrap_generate_candidates.py <prompt.md> <output_dir>
"""

import hashlib, json, os, re, subprocess, sys, time
from pathlib import Path


def sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def call_deepseek(prompt, api_key):
    import json as j
    effort = os.environ.get("VGUIDE_LLM_REASONING_EFFORT", "default")
    body_obj = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_completion_tokens": 1024
    }
    if effort != "default":
        body_obj["reasoning"] = {"max_tokens": {"low": 0, "medium": 1024, "high": 4096}.get(effort, 0), "exclude": True}
    body = j.dumps(body_obj)
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


def parse_candidates(raw_output):
    text = raw_output.strip()
    if '```' in text:
        m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if m: text = m.group(1).strip()
        else: text = re.sub(r'```(?:json)?\s*', '', text).replace('```', '')
    for _ in range(5):
        try:
            result = json.loads(text)
            if isinstance(result, dict): return result
        except json.JSONDecodeError:
            pass
        m = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
        if m: text = m.group()
        else: break
    return {}


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 bootstrap_generate_candidates.py <prompt.md> <output_dir>")
        sys.exit(1)

    prompt_file = sys.argv[1]
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    prompt = Path(prompt_file).read_text()
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not set"); sys.exit(1)

    print(f"Bootstrap: prompt={len(prompt)} chars, ~{len(prompt)//4} tokens")

    # Record/replay
    record_mode = os.environ.get("VGUIDE_LLM_RECORD", "") == "1"
    replay_mode = os.environ.get("VGUIDE_LLM_REPLAY", "") == "1"
    cache_dir = os.environ.get("VGUIDE_LLM_CACHE_DIR", "")
    prompt_hash = sha256(prompt)

    if replay_mode and cache_dir:
        cache_response = Path(cache_dir) / prompt_hash / "response.txt"
        if cache_response.exists():
            print(f"Replay hit: {prompt_hash}")
            raw_output = cache_response.read_text()
        else:
            print(f"ERROR: replay cache miss for {prompt_hash}")
            sys.exit(1)
    else:
        print("Calling DeepSeek...")
        raw_output = call_deepseek(prompt, api_key)
        if record_mode and cache_dir:
            d = Path(cache_dir) / prompt_hash
            d.mkdir(parents=True, exist_ok=True)
            (d / "prompt.txt").write_text(prompt)
            (d / "response.txt").write_text(raw_output)
            json.dump({"hash": prompt_hash, "model": "deepseek-chat", "prompt_chars": len(prompt), "response_chars": len(raw_output)}, open(d / "metadata.json", "w"), indent=2)
            print(f"Recorded: {prompt_hash}")

    (out_dir / "bootstrap_raw_llm_output.txt").write_text(raw_output)
    print(f"Raw response: {len(raw_output)} chars")

    candidates = parse_candidates(raw_output)
    (out_dir / "bootstrap_candidates.json").write_text(json.dumps(candidates, indent=2))
    total = sum(len(v) for v in candidates.values()) if candidates else 0
    print(f"Parsed: {total} predicates from {len(candidates)} locations")

    # Validate
    from b5_validate_candidates import validate_candidates as vc_validate
    valid, rejected, report = vc_validate(candidates)
    (out_dir / "bootstrap_candidates_validated.json").write_text(json.dumps(valid, indent=2))
    (out_dir / "bootstrap_rejected_candidates.json").write_text(json.dumps(rejected, indent=2))
    v_total = sum(len(v) for v in valid.values()) if valid else 0
    r_total = len(rejected)
    print(f"Validated: {v_total} accepted, {r_total} rejected")


if __name__ == "__main__":
    main()
