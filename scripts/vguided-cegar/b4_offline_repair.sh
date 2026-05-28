#!/usr/bin/env bash
# B4 offline repair — call LLM with CEGAR context to generate repair predicates
# Usage: ./b4_offline_repair.sh <context_dir> <output_dir>
set -euo pipefail

CTXDIR="$1"
OUTDIR="$2"
mkdir -p "$OUTDIR"

CONTEXT="${CTXDIR}/b4_context.json"
if [ ! -f "$CONTEXT" ]; then
  echo "No b4_context.json in $CTXDIR"
  exit 1
fi

API_KEY="${DEEPSEEK_API_KEY:-}"
[ -z "$API_KEY" ] && { echo "DEEPSEEK_API_KEY not set"; exit 1; }

# Extract key info
RESULT=$(python3 -c "import json; d=json.load(open('$CONTEXT')); print(d.get('result','UNKNOWN'))" 2>/dev/null || echo "UNKNOWN")
REFS=$(python3 -c "import json; d=json.load(open('$CONTEXT')); print(d.get('refinements',0))" 2>/dev/null || echo "0")
VOCAB=$(python3 -c "import json; d=json.load(open('$CONTEXT')); entries=d.get('vocabulary_entries',[]); print('; '.join(f\"[{e['location']}] {e['predicate']}\" for e in entries))" 2>/dev/null || echo "none")

# Build repair prompt using python for safety
PROMPT=$(python3 -c "
import json
d = json.load(open('$CONTEXT'))
result = d.get('result','UNKNOWN')
refs = d.get('refinements',0)
entries = d.get('vocabulary_entries',[])
vocab = '; '.join(f'[{e[\"location\"]}] {e[\"predicate\"]}' for e in entries) or 'none'
print(f'''You are helping a CEGAR-based predicate abstraction verifier.

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
{{\"N19\": [\"pred1\", \"pred2\", ...]}}

Generate 5-10 new predicates.''')
")

echo "=== B4 repair request ==="

# Call DeepSeek API
RESP=$(curl -s https://api.deepseek.com/chat/completions \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d "$(python3 -c "
import json
print(json.dumps({
  'model': 'deepseek-chat',
  'messages': [{'role': 'user', 'content': '''$PROMPT'''}],
  'temperature': 0,
  'max_completion_tokens': 1024
}))
")" 2>/dev/null)

echo "$RESP" > "$OUTDIR/llm_raw_response.json"

CONTENT=$(python3 -c "
import json
r = json.loads(open('$OUTDIR/llm_raw_response.json').read())
print(r['choices'][0]['message']['content'])
" 2>/dev/null || echo "{}")

echo "$CONTENT" > "$OUTDIR/repair_predicates_raw.txt"

# Try to extract JSON from response
python3 -c "
import json, re, sys
text = open('$OUTDIR/repair_predicates_raw.txt').read()
# Find JSON object
m = re.search(r'\{[^{}]*\}', text, re.DOTALL)
if m:
    try:
        obj = json.loads(m.group())
        json.dump(obj, open('$OUTDIR/repair_candidates.json', 'w'), indent=2)
        print(f'Extracted {sum(len(v) for v in obj.values())} predicates')
        sys.exit(0)
    except:
        pass
# Try as raw JSON
text = text.strip()
if '```' in text:
    text = re.sub(r'\`\`\`(?:json)?\s*', '', text).replace('\`\`\`', '')
try:
    obj = json.loads(text)
    json.dump(obj, open('$OUTDIR/repair_candidates.json', 'w'), indent=2)
    print(f'Parsed {sum(len(v) for v in obj.values())} predicates')
except Exception as e:
    print(f'Parse failed: {e}')
    open('$OUTDIR/repair_candidates.json', 'w').write('{}')
" 2>/dev/null

echo "Repair candidates saved to $OUTDIR/repair_candidates.json"
