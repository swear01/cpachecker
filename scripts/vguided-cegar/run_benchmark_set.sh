#!/usr/bin/env bash
# Run Unified VGuide CPA on a named benchmark set.
#
# Usage:
#   export DEEPSEEK_API_KEY=...
#   export SV_BENCHMARKS=/path/to/sv-benchmarks/c   # default: LOCAL_DEVELOPMENT_ENV
#   ./run_benchmark_set.sh <set> [extra cpa.sh args...]
#
# Sets (manifest under docs/vguided-cegar/benchmark_sets/<set>.list):
#   sample              — Tier S-Sample: 8 tasks (CI / LLM quality smoke)
#   rescue_core         — 6 core rescue tasks (scalar + array_3-1)
#   full_scalar         — classifier RUN_SCALAR (resolved paths; skips missing)
#   frozen_exception    — half_2, seq-3 (frozen / no-LLM path; for comparison)
#
# Environment:
#   JAVA, HEAP (default 2000M), TIMELIMIT (default 300s)
#   VGUIDE_PARALLEL or PARALLEL — max concurrent CPA jobs (default 8)
#   VGUIDE_SET_DIR — override manifest directory
#   VGUIDE_DRY_RUN=1 — print commands only
#   VGUIDE_SKIP_MISSING=1 — default; skip tasks whose .i is not found
#
# Scheduling defaults come from config/vguide.properties.
# Summary rows are appended after each task (flock); safe to tail -f while running.
# Override per run, e.g.:
#   --option vguide.llmCallSchedule=first_spurious
#
# Output (VGUIDE_OUT_BASE; run.sh default: output/vguide/experiments/<set>_vguide|_stock):
#   $OUT_BASE/logs/<task>.log
#   $OUT_BASE/<set>_summary.csv  (task,result,refs,wall_s,log)
#
# See docs/vguided-cegar/evaluation/STANDARD_BENCHMARK_SUITE.md

set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
CPA_SH="$REPO/scripts/cpa.sh"
SPEC="$REPO/config/specification/default.spc"
CONFIG="${VGUIDE_CONFIG:-config/predicateAnalysis-vguide.properties}"
SET_DIR="${VGUIDE_SET_DIR:-$REPO/docs/vguided-cegar/benchmark_sets}"
JAVA="${JAVA:-}"
HEAP="${HEAP:-2000M}"
TIMELIMIT="${TIMELIMIT:-300}"
OUT_BASE="${VGUIDE_OUT_BASE:-$REPO/output/vguide/batch}"
SV_BENCHMARKS="${SV_BENCHMARKS:-$HOME/sv-benchmarks/c}"
SKIP_MISSING="${VGUIDE_SKIP_MISSING:-1}"
DRY_RUN="${VGUIDE_DRY_RUN:-0}"
PARALLEL="${VGUIDE_PARALLEL:-${PARALLEL:-8}}"
USE_VGUIDE="${VGUIDE_USE_VOCABULARY_GUIDE:-true}"

die() { echo "ERROR: $*" >&2; exit 1; }

usage() {
  sed -n '3,38p' "$0" | sed 's/^# \{0,1\}//'
  echo ""
  echo "Available sets:"
  ls -1 "$SET_DIR"/*.list 2>/dev/null | xargs -n1 basename | sed 's/\.list$//'
  exit 1
}

[[ $# -ge 1 ]] || usage
SET="$1"
shift
MANIFEST="$SET_DIR/${SET}.list"
[[ -f "$MANIFEST" ]] || die "Unknown set '$SET' (no $MANIFEST)"

if [[ "$USE_VGUIDE" == "true" && -z "${DEEPSEEK_API_KEY:-}" ]]; then
  die "DEEPSEEK_API_KEY required for Unified VGuide"
fi

mkdir -p "$OUT_BASE/logs"
SUMMARY="$OUT_BASE/${SET}_summary.csv"
SUMMARY_LOCK="$OUT_BASE/.${SET}_summary.lock"
TMPDIR="$OUT_BASE/.tmp_${SET}_$$"
mkdir -p "$TMPDIR"
if [[ ! -f "$SUMMARY" ]]; then
  echo "task,rel_path,result,refinements,wall_s,log" > "$SUMMARY"
fi

# Append one CSV row as each task finishes (safe under parallel jobs).
append_summary_row() {
  local row="$1"
  {
    flock -x 9
    echo "$row" >>"$SUMMARY"
  } 9>"$SUMMARY_LOCK"
}

resolve_path() {
  local line="$1"
  line="${line%%#*}"
  line="$(echo "$line" | xargs)"
  [[ -n "$line" ]] || return 1
  if [[ -f "$SV_BENCHMARKS/$line" ]]; then
    echo "$SV_BENCHMARKS/$line"
    return 0
  fi
  local base="${line%.i}"; base="${base%.c}"
  local task="${base##*/}"
  local hit
  hit="$(find "$SV_BENCHMARKS" -name "${task}.i" -type f 2>/dev/null | head -1)"
  [[ -n "$hit" ]] || hit="$(find "$SV_BENCHMARKS" -name "${task}.c" -type f 2>/dev/null | head -1)"
  if [[ -n "$hit" && -f "$hit" ]]; then
    echo "$hit"
    return 0
  fi
  return 1
}

extract() {
  local pat="$1" log="$2"
  grep "$pat" "$log" 2>/dev/null | head -1 || true
}

# Prints one CSV summary line to stdout.
run_one() {
  local prog="$1" task="$2"
  shift 2
  local log="$OUT_BASE/logs/${task}.log"
  local cmd=(
    timeout "$((TIMELIMIT + 30))s"
    "$CPA_SH" --heap "$HEAP"
    --config "$CONFIG"
  )
  if [[ "$USE_VGUIDE" == "true" ]]; then
    cmd+=(--option cpa.predicate.refinement.useVocabularyGuide=true)
  else
    cmd+=(--option cpa.predicate.refinement.useVocabularyGuide=false)
  fi
  cmd+=(
    --timelimit "${TIMELIMIT}s"
    --spec "$SPEC"
    --stats
    --no-output-files
    "$@"
    "$prog"
  )
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "[dry-run] ${cmd[*]}"
    echo "$task,$(basename "$prog"),DRY_RUN,0,0,$log"
    return 0
  fi
  "${cmd[@]}" >"$log" 2>&1 || true
  local result refs wall
  result="$(extract 'Verification result:' "$log" | sed -n 's/.*Verification result:[[:space:]]*\([A-Za-z]*\).*/\1/p' | head -1 | tr '[:lower:]' '[:upper:]')"
  refs="$(extract 'Number of predicate refinements:' "$log" | grep -oE '[0-9]+' | head -1)"
  wall="$(extract 'Total time for CPAchecker:' "$log" | grep -oE '[0-9.]+' | head -1)"
  [[ -n "$result" ]] || result="UNKNOWN"
  [[ -n "$refs" ]] || refs="0"
  [[ -n "$wall" ]] || wall="0"
  echo "$task → $result refs=$refs wall=${wall}s" >&2
  echo "$task,$(basename "$prog"),$result,$refs,$wall,$log"
}

echo "Set=$SET manifest=$MANIFEST bench=$SV_BENCHMARKS out=$OUT_BASE parallel=$PARALLEL"
EXTRA=("$@")
ORDER_FILE="$TMPDIR/order.txt"
: >"$ORDER_FILE"
count=0
running=0

launch() {
  local prog="$1" task="$2"
  echo "$task" >>"$ORDER_FILE"
  count=$((count + 1))
  if [[ "$PARALLEL" -le 1 ]]; then
    echo "[$count] $task"
    run_one "$prog" "$task" "${EXTRA[@]}" >"$TMPDIR/${task}.row"
    append_summary_row "$(cat "$TMPDIR/${task}.row")"
    return
  fi
  while [[ "$running" -ge "$PARALLEL" ]]; do
    wait -n 2>/dev/null || wait || true
    running=$((running - 1))
  done
  echo "[$count] $task (bg)" >&2
  (
    run_one "$prog" "$task" "${EXTRA[@]}" >"$TMPDIR/${task}.row"
    append_summary_row "$(cat "$TMPDIR/${task}.row")"
  ) &
  running=$((running + 1))
}

while IFS= read -r line || [[ -n "$line" ]]; do
  [[ "$line" =~ ^[[:space:]]*# ]] && continue
  line="$(echo "$line" | xargs)"
  [[ -n "$line" ]] || continue
  prog="$(resolve_path "$line")" || {
    if [[ "$SKIP_MISSING" == "1" ]]; then
      echo "  SKIP (missing): $line"
      continue
    fi
    die "Missing benchmark: $line"
  }
  task="${prog##*/}"
  task="${task%.i}"
  task="${task%.c}"
  launch "$prog" "$task"
done <"$MANIFEST"

wait 2>/dev/null || true

# Backfill any rows missed if append failed (e.g. older runs).
while IFS= read -r task; do
  [[ -n "$task" ]] || continue
  if [[ -f "$TMPDIR/${task}.row" ]] && ! grep -q "^${task}," "$SUMMARY" 2>/dev/null; then
    append_summary_row "$(cat "$TMPDIR/${task}.row")"
  fi
done <"$ORDER_FILE"

rm -rf "$TMPDIR"
echo "Done. Summary: $SUMMARY ($count tasks, parallel=$PARALLEL)"
