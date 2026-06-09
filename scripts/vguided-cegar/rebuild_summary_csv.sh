#!/usr/bin/env bash
# Rebuild <set>_summary.csv from CPA logs + benchmark manifest (manifest order).
#
# Usage:
#   ./rebuild_summary_csv.sh --out output/vguide/experiments/full_scalar_vguide_noL3_budget306_20260609 --set full_scalar
#
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
SET_DIR="${VGUIDE_SET_DIR:-$REPO/docs/vguided-cegar/benchmark_sets}"
OUT_BASE=""
SET=""
TIMELIMIT="${TIMELIMIT:-300}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) OUT_BASE="$2"; shift 2 ;;
    --set) SET="$2"; shift 2 ;;
    --timelimit) TIMELIMIT="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

[[ -n "$OUT_BASE" && -n "$SET" ]] || {
  echo "Usage: $0 --out <experiment_dir> --set <manifest_name>" >&2
  exit 1
}

MANIFEST="$SET_DIR/${SET}.list"
SUMMARY="$OUT_BASE/${SET}_summary.csv"
[[ -f "$MANIFEST" ]] || { echo "Missing manifest: $MANIFEST" >&2; exit 1; }

finalize_log_verdict() {
  local log="$1"
  [[ -f "$log" ]] || return 0
  if grep -q 'Verification result:' "$log" 2>/dev/null; then
    return 0
  fi
  local reason="incomplete analysis (no CPA summary line)"
  if grep -q 'forcing immediate termination' "$log" 2>/dev/null; then
    reason="incomplete analysis (SMT hang; forced termination after shutdown grace)"
  elif grep -q 'CPU-time limit of.*has elapsed' "$log" 2>/dev/null; then
    reason="incomplete analysis (CPU time limit reached)"
  elif grep -qE 'Exception in thread "main"|java\.lang\.' "$log" 2>/dev/null; then
    reason="incomplete analysis (Java exception)"
  fi
  {
    echo ""
    echo "--- VGuide batch runner post-process $(date -Iseconds) ---"
    echo "Verification result: UNKNOWN, ${reason}."
    echo "Total time for CPAchecker: ${TIMELIMIT}.000s"
  } >>"$log"
}

extract_field() {
  local pat="$1" log="$2"
  grep "$pat" "$log" 2>/dev/null | head -1 || true
}

tmp="$(mktemp)"
echo "task,rel_path,result,refinements,wall_s,log" >"$tmp"
rows=0
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ "$line" =~ ^[[:space:]]*# ]] && continue
  line="${line%%#*}"
  line="$(echo "$line" | xargs)"
  [[ -n "$line" ]] || continue
  rel="${line##*/}"
  task="${rel%.i}"; task="${task%.c}"
  log="$OUT_BASE/logs/${task}.log"
  if [[ ! -f "$log" ]]; then
    echo "WARN: missing log for $task" >&2
    continue
  fi
  finalize_log_verdict "$log"
  result="$(extract_field 'Verification result:' "$log" | sed -n 's/.*Verification result:[[:space:]]*\([A-Za-z]*\).*/\1/p' | head -1 | tr '[:lower:]' '[:upper:]' || true)"
  refs="$(extract_field 'Number of predicate refinements:' "$log" | grep -oE '[0-9]+' | head -1 || true)"
  wall="$(extract_field 'Total time for CPAchecker:' "$log" | grep -oE '[0-9.]+' | head -1 || true)"
  [[ -n "$result" ]] || result="UNKNOWN"
  [[ -n "$refs" ]] || refs="0"
  [[ -n "$wall" ]] || wall="0"
  echo "$task,$rel,$result,$refs,$wall,$log" >>"$tmp"
  rows=$((rows + 1))
done <"$MANIFEST"

mv "$tmp" "$SUMMARY"
echo "Wrote $SUMMARY ($rows tasks)"
