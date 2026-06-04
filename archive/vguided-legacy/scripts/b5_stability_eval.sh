#!/usr/bin/env bash
# B5 Stability Evaluation — K repeated B2 and B5 runs per benchmark
# Usage: bash scripts/vguided-cegar/b5_stability_eval.sh [K=5] [--quick K=3]

set -euo pipefail

K=${K:-5}
if [ "$K" -eq "$K" ] 2>/dev/null; then :; else K=5; fi

BASE="results/vguided-cegar/stability_eval"
CACHE="$BASE/cache"
mkdir -p "$BASE" "$CACHE"

export JAVA="${JAVA:-/home/swear01/FMPA2/external/jdk-21/jdk-21.0.10+7/bin/java}"
export DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-}"
export VGUIDE_LLM_CACHE_DIR="$CACHE"

echo "benchmark,mode,run_id,result,refs,time,llm_cache_status,notes" > "$BASE/summary.csv"

run_b2() {
  local NAME="$1" FILE="$2" RUN_ID="$3"
  local WORK="$BASE/$NAME/b2"
  mkdir -p "$WORK"
  local LOG="$WORK/run_${RUN_ID}.log"

  # Replay if cached, else record
  if [ -d "$CACHE" ] && [ "$(find "$CACHE" -name "response.txt" 2>/dev/null | wc -l)" -gt 0 ]; then
    unset VGUIDE_LLM_RECORD
    export VGUIDE_LLM_REPLAY=1
    local CACHE_STATUS="replay"
  else
    export VGUIDE_LLM_RECORD=1
    unset VGUIDE_LLM_REPLAY
    local CACHE_STATUS="record"
  fi

  timeout 60 scripts/cpa.sh --heap 2000M --predicateAnalysis --stats --no-output-files --timelimit 30s \
    --spec config/specification/default.spc --option cpa.predicate.refinement.useVocabularyGuide=true \
    "$FILE" < /dev/null > "$LOG" 2>&1

  local REFS=$(grep "Number of predicate refinements:" "$LOG" | grep -oP '\d+' | head -1 || echo "?")
  local RESULT=$(grep "Verification result:" "$LOG" | awk '{print $NF}' | tr -d '.' || echo "?")
  local TIME=$(grep "Time for analysis:" "$LOG" | grep -oP '[\d.]+' | head -1 || echo "?")
  echo "$NAME,B2,$RUN_ID,$RESULT,$REFS,$TIME,$CACHE_STATUS," >> "$BASE/summary.csv"
  echo "$REFS $RESULT"
}

run_b5() {
  local NAME="$1" FILE="$2" RUN_ID="$3" B2_LOG="$4"
  local WORK="$BASE/$NAME/b5/run_${RUN_ID}"
  mkdir -p "$WORK"

  # B5: step 1 = dump context
  export VGUIDE_B5_DUMP_CONTEXT="$WORK/b5_context"
  export VGUIDE_B5_DUMP_LIMIT=3
  export VGUIDE_PRECISION_TOP_K=5
  export VGUIDE_LLM_RECORD=1
  unset VGUIDE_LLM_REPLAY VGUIDE_INJECT_REPAIR_PREDICATES_ONCE

  timeout 60 scripts/cpa.sh --heap 2000M --predicateAnalysis --stats --no-output-files --timelimit 30s \
    --spec config/specification/default.spc --option cpa.predicate.refinement.useVocabularyGuide=true \
    "$FILE" < /dev/null > "$WORK/b2.log" 2>&1

  # Steps 2-5: Summarize + prompt + repair
  python3 scripts/vguided-cegar/b5_context_summarizer.py "$WORK/b5_context" "$FILE" > /dev/null 2>&1
  python3 scripts/vguided-cegar/b5_build_prompt.py "$FILE" "$WORK/b5_context" --output "$WORK/prompt.md" > /dev/null 2>&1
  if [ ! -f "$WORK/prompt.md" ]; then echo "? prompt_fail"; return; fi

  python3 scripts/vguided-cegar/b5_repair_from_prompt.py "$WORK/prompt.md" "$WORK/b5_context" > "$WORK/repair.log" 2>&1
  local ACC=$(grep "validated:" "$WORK/repair.log" | grep -oP '\d+' | head -1 || echo "0")

  cp "$WORK/b5_context/repair_candidates_validated.json" "$WORK/validated.json" 2>/dev/null
  if [ ! -f "$WORK/validated.json" ] || [ "$ACC" = "0" ]; then echo "? no_preds"; return; fi

  # Step 6: Inject + rerun
  export VGUIDE_INJECT_REPAIR_PREDICATES_ONCE=1
  export VGUIDE_REPAIR_CANDIDATES_FILE=$(realpath "$WORK/validated.json")
  export VGUIDE_B4_REPAIR_TOP_K=10
  unset VGUIDE_B5_DUMP_CONTEXT VGUIDE_B5_DUMP_LIMIT VGUIDE_PRECISION_TOP_K

  timeout 60 scripts/cpa.sh --heap 2000M --predicateAnalysis --stats --no-output-files --timelimit 30s \
    --spec config/specification/default.spc --option cpa.predicate.refinement.useVocabularyGuide=true \
    "$FILE" < /dev/null > "$WORK/rerun.log" 2>&1

  local REFS=$(grep "Number of predicate refinements:" "$WORK/rerun.log" | grep -oP '\d+' | head -1 || echo "?")
  local RESULT=$(grep "Verification result:" "$WORK/rerun.log" | awk '{print $NF}' | tr -d '.' || echo "?")
  local INJ=$(grep "V B4 repair injected" "$WORK/rerun.log" | grep -oP '\d+' | head -1 || echo "0")
  echo "$NAME,B5,$RUN_ID,$RESULT,$REFS,,record,$INJ injected" >> "$BASE/summary.csv"
  echo "$REFS $RESULT"
}

# --- Main ---
echo "=== B5 Stability Evaluation (K=$K) ==="
echo "Started: $(date)"
echo ""

for TRIO in \
  "sum04-2:/home/swear01/sv-benchmarks-vguided/c/loops/sum04-2.i" \
  "const_1-2:/home/swear01/sv-benchmarks-vguided/c/loop-acceleration/const_1-2.c" \
  "functions_1-2:/home/swear01/sv-benchmarks-vguided/c/loop-acceleration/functions_1-2.c" \
  "nested_1-2:/home/swear01/sv-benchmarks-vguided/c/loop-acceleration/nested_1-2.c"; do
  IFS=: read NAME FILE <<< "$TRIO"

  echo "===== $NAME ====="

  for ((i=1; i<=K; i++)); do
    echo -n "  B2 run $i/$K: "
    B2_OUT=$(run_b2 "$NAME" "$FILE" "$i")
    echo "$B2_OUT"
  done

  for ((i=1; i<=K; i++)); do
    echo -n "  B5 run $i/$K: "
    B5_OUT=$(run_b5 "$NAME" "$FILE" "$i" "")
    echo "$B5_OUT"
  done
  echo ""
done

echo "===== SUMMARY ====="
echo "Finished: $(date)"
cat "$BASE/summary.csv"
