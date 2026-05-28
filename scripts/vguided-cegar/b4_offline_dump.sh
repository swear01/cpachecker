#!/usr/bin/env bash
# B4 offline context dump — run partial B2 and save CEGAR context
# Usage: ./b4_offline_dump.sh <benchmark_path> <output_dir>
set -euo pipefail

REPO="$(dirname "$0")/../.."
CPA_SH="$REPO/scripts/cpa.sh"
SPEC="$REPO/config/specification/default.spc"
JAVA="${JAVA:-java}"
HEAP="${HEAP:-8000M}"
TIMELIMIT="${TIMELIMIT:-60}"
LLM_TIMEOUT="${LLM_TIMEOUT:-120}"

BENCH="$1"
OUTDIR="$2"
mkdir -p "$OUTDIR"

BENCH_NAME=$(basename "$BENCH" | sed 's/\.[^.]*$//')

echo "=== B4 dump: $BENCH_NAME ==="

# Run B2 partial
export VGUIDE_B4_DUMP_CONTEXT="$OUTDIR"
export VGUIDE_FORCE_PARITY=1

timeout "$LLM_TIMEOUT" "$CPA_SH" \
  --heap "$HEAP" --predicateAnalysis --stats --no-output-files \
  --timelimit "${TIMELIMIT}s" --spec "$SPEC" \
  --option cpa.predicate.refinement.useVocabularyGuide=true \
  "$BENCH" > "$OUTDIR/b2_partial.log" 2>&1 || true

# Extract key info
RESULT=$(grep "Verification result:" "$OUTDIR/b2_partial.log" | awk '{print $NF}' | tr -d '.' || echo "TIMEOUT")
REFS=$(grep "Number of predicate refinements:" "$OUTDIR/b2_partial.log" | grep -oP '\d+' | head -1 || echo "0")

echo "Result: $RESULT, Refinements: $REFS"

# Write summary
cat > "$OUTDIR/dump_summary.json" << JSONEOF
{
  "benchmark": "$BENCH",
  "benchmark_name": "$BENCH_NAME",
  "result": "$RESULT",
  "refinements": $REFS,
  "mode": "B2_partial"
}
JSONEOF

echo "Context dumped to $OUTDIR"
