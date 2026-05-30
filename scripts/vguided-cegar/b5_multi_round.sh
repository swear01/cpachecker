#!/usr/bin/env bash
# B5-MR: Multi-Round Trace/Interpolant-Guided LLM Repair (simplified)
# Each round = full B5 workflow: dump → summarize → prompt → repair → validate → inject → rerun
# Tracks cumulative predicates to detect stagnation.
set -euo pipefail

BENCH="$1"; OUT_DIR="$2"
MAX_ROUNDS="${3:-3}"; PER_ROUND_TL="${4:-60}"
BENCH_NAME=$(basename "$BENCH" | sed 's/\.[^.]*$//')
mkdir -p "$OUT_DIR"

echo "benchmark,round,mode,result,refs,time,new_valid,new_inj,total_inj,stop_reason" > "$OUT_DIR/summary.csv"

run_cpa() {
  timeout $((PER_ROUND_TL + 30)) scripts/cpa.sh --heap 2000M --predicateAnalysis --stats --no-output-files --timelimit "${PER_ROUND_TL}s" \
    --spec config/specification/default.spc --option cpa.predicate.refinement.useVocabularyGuide=true \
    "$BENCH" < /dev/null > "$1" 2>&1
}
get_refs() { grep "Number of predicate refinements:" "$1" | grep -oP '\d+' | head -1 || echo "?"; }
get_result() { grep "Verification result:" "$1" | awk '{print $NF}' | tr -d '.' || echo "?"; }

# ---- Round 0: Initial B2 ----
R0="$OUT_DIR/round_0"; mkdir -p "$R0"
export VGUIDE_B5_DUMP_CONTEXT="$R0/b5_context"; export VGUIDE_B5_DUMP_LIMIT=3
unset VGUIDE_INJECT_REPAIR_PREDICATES_ONCE VGUIDE_REPAIR_CANDIDATES_FILE
export VGUIDE_LLM_RECORD=1; unset VGUIDE_LLM_REPLAY

run_cpa "$R0/cpa.log"
R0R=$(get_result "$R0/cpa.log"); R0F=$(get_refs "$R0/cpa.log")
echo "$BENCH_NAME,0,B2,$R0R,$R0F,,,,," >> "$OUT_DIR/summary.csv"
echo "Round 0: $R0R refs=$R0F"
[ "$R0R" = "TRUE" ] || [ "$R0R" = "FALSE" ] && { echo "Already solved."; exit 0; }

# ---- Repair rounds ----
TOTAL_INJ=0
ALL_PREDS_FILE="$OUT_DIR/all_predicates.json"; echo "[]" > "$ALL_PREDS_FILE"

for ROUND in $(seq 1 $MAX_ROUNDS); do
  RD="$OUT_DIR/round_$ROUND"; mkdir -p "$RD"
  echo ""
  echo "===== Round $ROUND ====="

  # Enable repair injection with cumulative predicates
  if [ "$TOTAL_INJ" -gt 0 ]; then
    python3 -c "
import json
preds = json.load(open('$ALL_PREDS_FILE'))
json.dump({'N0': preds}, open('$RD/cumulative.json','w'), indent=2)
" 2>/dev/null
    export VGUIDE_INJECT_REPAIR_PREDICATES_ONCE=1
    export VGUIDE_REPAIR_CANDIDATES_FILE=$(realpath "$RD/cumulative.json" 2>/dev/null || echo "")
    export VGUIDE_B4_REPAIR_TOP_K=50
  fi

  export VGUIDE_B5_DUMP_CONTEXT="$RD/b5_context"; export VGUIDE_B5_DUMP_LIMIT=3
  unset VGUIDE_PRECISION_TOP_K

  run_cpa "$RD/cpa.log"
  RR=$(get_result "$RD/cpa.log"); RF=$(get_refs "$RD/cpa.log")
  echo "  CPA: $RR refs=$RF injected=$TOTAL_INJ"

  if [ "$RR" = "TRUE" ] || [ "$RR" = "FALSE" ]; then
    echo "$BENCH_NAME,$ROUND,B5-MR,$RR,$RF,,0,0,$TOTAL_INJ,solved" >> "$OUT_DIR/summary.csv"
    echo "  SOLVED!"; break
  fi

  # Dump context + summarize + build prompt + repair
  python3 scripts/vguided-cegar/b5_context_summarizer.py "$RD/b5_context" "$BENCH" > /dev/null 2>&1
  python3 scripts/vguided-cegar/b5_build_prompt.py "$BENCH" "$RD/b5_context" --output "$RD/prompt_base.md" > /dev/null 2>&1

  # Append multi-round context to prompt
  if [ -f "$RD/prompt_base.md" ]; then
    cat "$RD/prompt_base.md" > "$RD/prompt.md"
    echo "" >> "$RD/prompt.md"
    echo "---" >> "$RD/prompt.md"
    echo "## Multi-Round Context" >> "$RD/prompt.md"
    echo "This is repair round $ROUND. $TOTAL_INJ predicates already injected." >> "$RD/prompt.md"
    if [ "$TOTAL_INJ" -gt 0 ]; then
      echo "Previously injected:" >> "$RD/prompt.md"
      python3 -c "import json; [print(f'- \`{p[:120]}\`') for p in json.load(open('$ALL_PREDS_FILE'))]" >> "$RD/prompt.md" 2>/dev/null
    fi
    echo "Generate NEW predicates not already in the injection list." >> "$RD/prompt.md"
  fi

  # LLM repair
  python3 scripts/vguided-cegar/b5_repair_from_prompt.py "$RD/prompt.md" "$RD/b5_context" > "$RD/repair.log" 2>&1
  NEW_ACC=$(grep "validated:" "$RD/repair.log" | grep -oP '\d+' | head -1 || echo "0")
  echo "  LLM: accepted=$NEW_ACC"

  # Dedup + accumulate
  VALIDATED="$RD/b5_context/repair_candidates_validated.json"
  NEW_INJ=0
  if [ -f "$VALIDATED" ] && [ "$NEW_ACC" != "0" ]; then
    NEW_INJ=$(python3 -c "
import json
validated = json.load(open('$VALIDATED'))
all_preds = json.load(open('$ALL_PREDS_FILE'))
new = 0
for loc, preds in validated.items():
    for p in preds:
        if p not in all_preds:
            all_preds.append(p); new += 1
json.dump(all_preds, open('$ALL_PREDS_FILE','w'), indent=2)
print(new)
" 2>/dev/null || echo "0")
    TOTAL_INJ=$((TOTAL_INJ + NEW_INJ))
    echo "  new injected: $NEW_INJ (total: $TOTAL_INJ)"
  fi

  echo "$BENCH_NAME,$ROUND,B5-MR,$RR,$RF,,$NEW_ACC,$NEW_INJ,$TOTAL_INJ,continued" >> "$OUT_DIR/summary.csv"

  if [ "$NEW_INJ" = "0" ]; then echo "  No new predicates. Stopping."; break; fi
  if [ "$TOTAL_INJ" -ge 30 ]; then echo "  Cap reached."; break; fi
done

echo ""; echo "===== SUMMARY ====="; cat "$OUT_DIR/summary.csv"