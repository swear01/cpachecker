#!/usr/bin/env bash
# Advisor Demo Runner — minimal reproducible demos for Bootstrap+B5-MR rescue
set -euo pipefail
MODE="${1:-help}"; DRY=false; [ "${2:-}" = "--dry-run" ] && DRY=true
cd "$(dirname "$0")/../.."

export PATH="${PATH}:/home/swear01/FMPA2/external/jdk-21/jdk-21.0.10+7/bin"
export JAVA="${JAVA:-/home/swear01/FMPA2/external/jdk-21/jdk-21.0.10+7/bin/java}"
export DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-}"
export VGUIDE_LLM_REASONING_EFFORT="${VGUIDE_LLM_REASONING_EFFORT:-low}"
OUT="results/vguided-cegar/advisor_demo/${MODE}"; mkdir -p "$OUT"

run() { if $DRY; then echo "  CMD: $1"; else bash -c "$1" 2>&1 | tail -3; fi; }
get_result() { grep "Verification result:" "$1" 2>/dev/null | grep -oP 'TRUE|FALSE|UNKNOWN' | head -1 || echo "?"; }
get_refs() { grep "Number of predicate refinements:" "$1" 2>/dev/null | grep -oP '\d+' | head -1 || echo "?"; }
bootstrap() {
  local FILE="$1" TITLE="$2"
  echo "# Advisor Demo: $TITLE" | tee "$OUT/summary.md"
  echo "Source: $FILE" | tee -a "$OUT/summary.md"
  echo ""; echo "### Bootstrap" | tee -a "$OUT/summary.md"
  run "python3 scripts/vguided-cegar/bootstrap_build_prompt.py '$FILE' --output '$OUT/bootstrap_prompt.md' && python3 scripts/vguided-cegar/bootstrap_generate_candidates.py '$OUT/bootstrap_prompt.md' '$OUT'"
  if $DRY; then echo "  (dry-run complete)"; return 1; fi
  [ -f "$OUT/bootstrap_candidates_validated.json" ] || { echo "Bootstrap failed"; return 1; }
  python3 -c "import json; v=json.load(open('$OUT/bootstrap_candidates_validated.json')); f=[]; [f.extend(p) for p in v.values()]; json.dump({'N0':f}, open('$OUT/inj.json','w'), indent=2)" 2>/dev/null
  run "VGUIDE_INJECT_REPAIR_PREDICATES_ONCE=1 VGUIDE_REPAIR_CANDIDATES_FILE=$(realpath $OUT/inj.json) VGUIDE_B4_REPAIR_TOP_K=50 timeout 360 scripts/cpa.sh --heap 2000M --predicateAnalysis --stats --no-output-files --timelimit 300s --spec config/specification/default.spc --option cpa.predicate.refinement.useVocabularyGuide=true '$FILE' > '$OUT/boot.log' 2>&1"
  if [ -f "$OUT/boot.log" ]; then
    R=$(get_result "$OUT/boot.log"); F=$(get_refs "$OUT/boot.log")
    HAS_SEL=$(grep -c "select" "$OUT/bootstrap_candidates.json" 2>/dev/null || echo "0")
    echo "  Result: $R refs=$F select=$HAS_SEL" | tee -a "$OUT/summary.md"
  fi
  return 0
}

case "$MODE" in
  scalar-up)
    FILE="/home/swear01/FMPA2/part2/sv-benchmarks/c/loop-invgen/up.i"
    [ ! -f "$FILE" ] && FILE="/home/swear01/sv-benchmarks-vguided/c/loops/up.i"
    [ ! -f "$FILE" ] && { echo "up.i not found"; exit 1; }
    bootstrap "$FILE" "Scalar Rescue (up)"
    echo "Expected: TRUE (1-2 refs). Historically 3/3 reproduction." | tee -a "$OUT/summary.md"
    ;;
  array-level1)
    FILE="/home/swear01/sv-benchmarks-vguided/c/loop-acceleration/array_3-1.i"
    [ ! -f "$FILE" ] && FILE="/home/swear01/FMPA2/part2/sv-benchmarks/c/loop-acceleration/array_3-1.i"
    [ ! -f "$FILE" ] && { echo "array_3-1.i not found"; exit 1; }
    bootstrap "$FILE" "Array-Present Scalar Rescue (array_3-1)"
    echo "Expected: TRUE (1 ref), 0 select/store." | tee -a "$OUT/summary.md"
    ;;
  context-unlock)
    FILE="/home/swear01/FMPA2/part2/sv-benchmarks/c/loop-invgen/half_2.i"
    [ ! -f "$FILE" ] && FILE="/home/swear01/FMPA2/part2/sv-benchmarks/c/loop-invgen/half_2.c"
    [ ! -f "$FILE" ] && { echo "half_2 not found"; exit 1; }
    bootstrap "$FILE" "Context-Unlocked-Only (half_2)"
    echo "Expected: UNKNOWN (~67 refs). Context unlocked but not solved." | tee -a "$OUT/summary.md"
    ;;
  help|*)
    echo "Usage: bash run_advisor_demo.sh <mode> [--dry-run]"
    echo "  scalar-up       Solved-from-UNKNOWN rescue (up)"
    echo "  array-level1    Array-present scalar rescue (array_3-1)"
    echo "  context-unlock  Bootstrap unlocks but not solved (half_2)"
    ;;
esac
echo "" | tee -a "$OUT/summary.md"
echo "Complete. Output: $OUT" | tee -a "$OUT/summary.md"