#!/usr/bin/env bash
# Independent cross-check of the stock-224 verdict-bearing tasks with k-induction.
# Input: TSV (task, source, expected, stock_verdict); Output: TSV + summary.
set -euo pipefail
REPO="/home/swear01/cpachecker"
SV="/var/tmp/swear01-cpachecker-paper/sv-benchmarks/c"
OUT="${1:-/tmp/kinduction-verify}"
TL="${2:-180}"
PARALLEL="${3:-4}"
INPUT="${4:-/home/swear01/cpachecker-experiments/runs/verify27-tasks.tsv}"
mkdir -p "$OUT"
rm -f "$OUT/results.tsv"
echo -e "task\texpected\tstock\tkinduction" > "$OUT/results.tsv"
run_one() {
  IFS=$'\t' read -r task source expected stock <<< "$1"
  name="${task//\//_}"
  log="$OUT/${name}.log"
  timeout "$((TL+30))s" "$REPO/scripts/cpa.sh" --config config/kInduction.properties \
    --spec "$REPO/config/specification/sv-comp-reachability.spc" --timelimit "${TL}s" \
    "$SV/$source" > "$log" 2>&1
  verdict=$(grep -m1 "Verification result" "$log" | sed -E 's/Verification result:[[:space:]]*([A-Za-z]+).*/\1/')
  echo -e "$task\t$expected\t$stock\t${verdict:-UNKNOWN}" >> "$OUT/results.tsv"
}
export -f run_one
export REPO SV OUT TL INPUT
tr '\n' '\0' < "$INPUT" | xargs -0 -n 1 -P "$PARALLEL" bash -c 'run_one "$1"' _
echo "=== summary ==="
python3 - "$OUT/results.tsv" <<'PY'
import sys
rows = [l.strip().split('\t') for l in open(sys.argv[1]) if l.strip() and not l.startswith('task')]
agree = sum(1 for _, e, s, k in rows if k in ('TRUE','FALSE') and k == s)
disagree = sum(1 for _, e, s, k in rows if k in ('TRUE','FALSE') and k != s)
unknown = sum(1 for _, e, s, k in rows if k not in ('TRUE','FALSE'))
print(f"kinduction agrees with stock: {agree}, disagrees: {disagree}, unknown: {unknown} / {len(rows)}")
for _, e, s, k in rows:
    if k in ('TRUE','FALSE') and k != s:
        print(f"  DISPUTE: {_} expected={e} stock={s} kinduction={k}")
PY
