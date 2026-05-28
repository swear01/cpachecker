#!/usr/bin/env bash
# B4 offline rerun — run CPAchecker with B2 + repair predicates
# Usage: ./b4_offline_rerun.sh <benchmark_path> <repair_dir> <output_dir>
set -euo pipefail

REPO="$(dirname "$0")/../.."
CPA_SH="$REPO/scripts/cpa.sh"
SPEC="$REPO/config/specification/default.spc"
JAVA="${JAVA:-java}"
HEAP="${HEAP:-8000M}"
TIMELIMIT="${TIMELIMIT:-120}"
LLM_TIMEOUT="${LLM_TIMEOUT:-240}"

BENCH="$1"
REPAIR_DIR="$2"
OUTDIR="$3"
mkdir -p "$OUTDIR"

BENCH_NAME=$(basename "$BENCH" | sed 's/\.[^.]*$//')

echo "=== B4 rerun: $BENCH_NAME ==="

# Collect repair predicates
REPAIR_FILE="$REPAIR_DIR/repair_candidates.json"
if [ -f "$REPAIR_FILE" ]; then
  REPAIR_COUNT=$(python3 -c "import json; d=json.load(open('$REPAIR_FILE')); print(sum(len(v) for v in d.values()))" 2>/dev/null || echo "0")
  echo "Repair predicates: $REPAIR_COUNT"

  # Build assertion predicate from first repair candidate
  FIRST_PRED=$(python3 -c "
import json
d = json.load(open('$REPAIR_FILE'))
for loc, preds in d.items():
    if preds: print(preds[0]); break
" 2>/dev/null || echo "")

  if [ -n "$FIRST_PRED" ] && [ "$FIRST_PRED" != "" ]; then
    export VGUIDE_ASSERTION_PREDICATE="$FIRST_PRED"
    echo "  top repair: $FIRST_PRED"
  fi
else
  echo "No repair candidates found"
fi

# Run with assertion oracle mode (uses repair predicate as oracle)
export VGUIDE_INJECT_ASSERTION_ORACLE_ONCE=1
export VGUIDE_FORCE_PARITY=1

timeout "$LLM_TIMEOUT" "$CPA_SH" \
  --heap "$HEAP" --predicateAnalysis --stats --no-output-files \
  --timelimit "${TIMELIMIT}s" --spec "$SPEC" \
  --option cpa.predicate.refinement.useVocabularyGuide=true \
  "$BENCH" > "$OUTDIR/b4_rerun.log" 2>&1 || true

# Extract results
RESULT=$(grep "Verification result:" "$OUTDIR/b4_rerun.log" | awk '{print $NF}' | tr -d '.' || echo "TIMEOUT")
REFS=$(grep "Number of predicate refinements:" "$OUTDIR/b4_rerun.log" | grep -oP '\d+' | head -1 || echo "0")
INJ=$(grep "V assertion oracle" "$OUTDIR/b4_rerun.log" | head -1 || echo "no injection")

cat > "$OUTDIR/b4_summary.json" << JSONEOF
{
  "benchmark": "$BENCH",
  "benchmark_name": "$BENCH_NAME",
  "result": "$RESULT",
  "refinements": $REFS,
  "injection": "$INJ",
  "mode": "B4_offline_repair"
}
JSONEOF

echo "B4 rerun: $RESULT, Refinements: $REFS"
echo "Summary: $OUTDIR/b4_summary.json"
