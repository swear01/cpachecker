#!/usr/bin/env bash
# Batch evaluation of V-guided CEGAR on existing benchmarks.
# Usage:
#   Stage A: ./batch_eval.sh stock <candidates.txt> <outdir>
#   Stage B: ./batch_eval.sh vmodes <filtered.csv> <outdir>
#   Full:    ./batch_eval.sh all <candidates.txt> <outdir>
# No strict error checking — this is a batch script
# that handles individual failures gracefully

REPO="$(dirname "$0")/../.."
CPA_SH="$REPO/scripts/cpa.sh"
SPEC="$REPO/config/specification/default.spc"
JAVA="${JAVA:-java}"
HEAP="${HEAP:-8000M}"
TIMELIMIT="${TIMELIMIT:-300}"
LLM_TIMEOUT="${LLM_TIMEOUT:-180}"

die() { echo "ERROR: $*" >&2; exit 1; }

run_cpa() {
  local mode="$1" outlog="$2"; shift 2
  timeout "$LLM_TIMEOUT" "$CPA_SH" \
    --heap "$HEAP" --predicateAnalysis --stats --no-output-files \
    --timelimit "${TIMELIMIT}s" --spec "$SPEC" "$@" \
    > "$outlog" 2>&1 < /dev/null || true
}

extract_refs() { grep "Number of predicate refinements:" "$1" | grep -oP '\d+' | head -1; }
extract_result() { grep "Verification result:" "$1" | awk '{print $NF}' | tr -d '.'; }
extract_time() { grep "Total time for CPAchecker:" "$1" | grep -oP '[\d.]+' | head -1; }

run_stock() {
  local prog="$1" outdir="$2" name="$3"
  local log="$outdir/logs/${name}.stock.log"
  mkdir -p "$(dirname "$log")"
  run_cpa stock "$log" "$prog"
  echo "$(extract_refs "$log" || echo 0),$(extract_result "$log" || echo TIMEOUT),$(extract_time "$log" || echo 0)"
}

run_vguided() {
  local mode="$1" prog="$2" outdir="$3" name="$4" extra_opts="$5"
  local log="$outdir/logs/${name}.${mode}.log"
  mkdir -p "$(dirname "$log")"
  export VGUIDE_INJECT_TOP1_PARITY_ONCE="${VGUIDE_INJECT_TOP1_PARITY_ONCE:-}"
  export VGUIDE_FORCE_PARITY="${VGUIDE_FORCE_PARITY:-}"
  local opts="--option cpa.predicate.refinement.useVocabularyGuide=true $extra_opts"
  run_cpa "$mode" "$log" "$prog" $opts
  echo "$(extract_refs "$log" || echo 0),$(extract_result "$log" || echo TIMEOUT),$(extract_time "$log" || echo 0)"
}

count_v_fate() {
  local label="$1" log="$2"
  grep -c "V-FATE.*${label}" "$log" 2>/dev/null || echo 0
}

count_v_injected() {
  grep -c "V precision-injected\|V one-shot" "$1" 2>/dev/null || echo 0
}

# ---- Stage A: Stock pre-scan ----
stage_stock() {
  local candidates="$1" outdir="$2"
  local outcsv="$outdir/stock_scan.csv"
  mkdir -p "$outdir/logs"

  echo "benchmark,category,stock_refs,result,time_s" > "$outcsv"

  while IFS='|' read -r category name prog; do
    [ -f "$prog" ] || continue
    echo "[stock] $name ($category)" >&2
    local stock_info=$(run_stock "$prog" "$outdir" "$name")
    echo "$name,$category,$stock_info" >> "$outcsv"
  done < "$candidates"

  echo "Stage A done. Results: $outcsv"
}

# ---- Stage B: V modes (entailed + precision) ----
stage_vmodes() {
  local filtered="$1" outdir="$2"
  local outcsv="$outdir/summary.csv"
  mkdir -p "$outdir/logs"

  echo "benchmark,category,result,stock_refs,entailed_refs,precision_refs,stock_time,entailed_time,precision_time,entailed_count,abstraction_count,injected_count,notes" > "$outcsv"

  tail -n +2 "$filtered" | while IFS=',' read -r name category stock_refs result stock_time; do
    local prog=""
    # Re-find the program path
    for cat in loop-acceleration loop-invariants loop-crafted loops; do
      for f in /home/swear01/sv-benchmarks-vguided/c/$cat/"$name"; do
        [ -f "$f" ] && { prog="$f"; break 2; }
      done
    done
    [ -z "$prog" ] && { echo "[skip] $name: not found" >&2; continue; }

    # Entailed-only
    echo "[entailed] $name" >&2
    local entailed_info=$(run_vguided entailed "$prog" "$outdir" "$name" "")
    local entailed_refs=$(echo "$entailed_info" | cut -d, -f1)
    local entailed_time=$(echo "$entailed_info" | cut -d, -f3)
    local entailed_log="$outdir/logs/${name}.entailed.log"
    local entailed_count=$(count_v_fate "ENTAILED" "$entailed_log")
    local abst_count=$(count_v_fate "ABSTRACTION-CANDIDATE" "$entailed_log")

    # One-shot precision
    echo "[precision] $name" >&2
    export VGUIDE_INJECT_TOP1_PARITY_ONCE=1
    export VGUIDE_FORCE_PARITY=1
    local prec_info=$(run_vguided precision "$prog" "$outdir" "$name" "")
    unset VGUIDE_INJECT_TOP1_PARITY_ONCE
    unset VGUIDE_FORCE_PARITY
    local prec_refs=$(echo "$prec_info" | cut -d, -f1)
    local prec_time=$(echo "$prec_info" | cut -d, -f3)
    local prec_log="$outdir/logs/${name}.precision.log"
    local injected=$(count_v_injected "$prec_log")

    # Classification
    local notes=""
    local prec_num=${prec_refs:-0}; local ent_num=${entailed_refs:-0}; local stock_num=${stock_refs:-0}
    if [ "$prec_num" -lt 10 ] && [ "$ent_num" -ge 20 ]; then notes="relational-positive"
    elif [ "$ent_num" -lt "$((stock_num * 75 / 100))" ] && [ "$prec_num" -ge "$((ent_num * 90 / 100))" ]; then notes="bounds-dominated"
    elif [ "$stock_num" -lt 10 ]; then notes="too-easy"
    elif [ "$prec_num" -gt "$((ent_num * 150 / 100))" ]; then notes="regression"
    else notes="no-effect"
    fi

    echo "$name,$category,$result,$stock_refs,$entailed_refs,$prec_refs,$stock_time,$entailed_time,$prec_time,$entailed_count,$abst_count,$injected,$notes" >> "$outcsv"
  done

  echo "Stage B done. Results: $outcsv"
}

# ---- Main ----
case "${1:-}" in
  stock) stage_stock "${2:?need candidates file}" "${3:?need output dir}" ;;
  vmodes) stage_vmodes "${2:?need filtered csv}" "${3:?need output dir}" ;;
  all)
    CAND="${2:?need candidates file}"
    OUT="${3:?need output dir}"
    stage_stock "$CAND" "$OUT"
    stage_vmodes "$OUT/stock_scan.csv" "$OUT"
    ;;
  *) echo "Usage: $0 {stock|vmodes|all} <input> <outdir>" >&2; exit 1 ;;
esac
