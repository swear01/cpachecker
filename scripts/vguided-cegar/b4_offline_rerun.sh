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
echo "B4 rerun: $RESULT, Refinements: $REFS"
echo "Summary: $OUTDIR/b4_summary.json"
