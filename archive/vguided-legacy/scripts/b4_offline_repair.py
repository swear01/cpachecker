#!/usr/bin/env python3
"""B4 offline repair — call LLM with CEGAR context to generate repair predicates."""
import json, os, re, sys

ctx_dir = sys.argv[1]
out_dir = sys.argv[2]
os.makedirs(out_dir, exist_ok=True)

ctx_file = os.path.join(ctx_dir, "b4_context.json")
if not os.path.exists(ctx_file):
    print(f"No b4_context.json in {ctx_dir}", file=sys.stderr)
    sys.exit(1)

api_key = os.environ.get("DEEPSEEK_API_KEY", "")
if not api_key:
    print("DEEPSEEK_API_KEY not set", file=sys.stderr)
    sys.exit(1)

ctx = json.load(open(ctx_file))
result = ctx.get('result', 'UNKNOWN')
refs = ctx.get('refinements', 0)
entries = ctx.get('vocabulary_entries', [])
vocab = '; '.join(f"[{e['location']}] {e['predicate']}" for e in entries) or 'none'

prompt = f"""You are helping a CEGAR-based predicate abstraction verifier.

Current state:
Result: {result}
Refinement count: {refs}
Current vocabulary:
{vocab}

The verifier is struggling. Generate additional candidate abstraction predicates
to repair the current weak abstraction.

Important:
- Predicates are Boolean features, not necessarily invariants.
- Do not repeat predicates already in the vocabulary above.
- Prefer relational predicates between variables.
- Avoid simple bounds.
- Output JSON only with SMT-LIB2 prefix notation.
- Use operators: =, !=, >=, <=, >, <, +, -, *, mod, and, or, not.

Output format:
{{"N19": ["pred1", "pred2", ...]}}

Generate 5-10 new predicates."""

print(f"=== B4 repair: result={result}, refinements={refs} ===")

import subprocess
body = json.dumps({
    "model": "deepseek-chat",
    "messages": [{"role": "user", "content": prompt}],
    "temperature": 0,
    "max_completion_tokens": 1024
})

resp = subprocess.run([
    "curl", "-s", "https://api.deepseek.com/chat/completions",
    "-H", f"Authorization: Bearer {api_key}",
    "-H", "Content-Type: application/json",
    "-d", body
], capture_output=True, text=True)

with open(os.path.join(out_dir, "llm_raw_response.json"), "w") as f:
    f.write(resp.stdout)

try:
    r = json.loads(resp.stdout)
    content = r['choices'][0]['message']['content']
except Exception as e:
    print(f"LLM response parse failed: {e}")
    content = "{}"

with open(os.path.join(out_dir, "repair_predicates_raw.txt"), "w") as f:
    f.write(content)

# Extract JSON
text = content.strip()
if '```' in text:
    text = re.sub(r'```(?:json)?\s*', '', text).replace('```', '')
m = re.search(r'\{[^{}]*\}', text, re.DOTALL)
candidates = {}
if m:
    try:
        candidates = json.loads(m.group())
    except:
        pass
if not candidates:
    try:
        candidates = json.loads(text)
    except:
        pass

total = sum(len(v) for v in candidates.values()) if isinstance(candidates, dict) else 0
print(f"Extracted {total} repair predicates")

with open(os.path.join(out_dir, "repair_candidates.json"), "w") as f:
    json.dump(candidates, f, indent=2)
