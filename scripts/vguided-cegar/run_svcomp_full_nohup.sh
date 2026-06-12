#!/usr/bin/env bash
# Launch svcomp27 full_scalar stock/vguide batches with nohup-safe logging.
# Default full-set command (detached):
#   ./scripts/vguided-cegar/run_svcomp_full_nohup.sh --arm both
# Dry-run:
#   ./scripts/vguided-cegar/run_svcomp_full_nohup.sh --dry-run
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
RUN="$REPO/scripts/vguided-cegar/run.sh"
ATTR="$REPO/scripts/vguided-cegar/attribute_svcomp_verdicts.py"
SET_DIR="$REPO/docs/vguided-cegar/benchmark_sets"

ARM="${SVCOMP_FULL_ARM:-both}"
SET="${SVCOMP_FULL_SET:-full_scalar}"
PARALLEL="${SVCOMP_FULL_PARALLEL:-${PARALLEL:-6}}"
TIMELIMIT="${SVCOMP_FULL_TIMELIMIT:-900}"
HEAP="${SVCOMP_FULL_HEAP:-4000M}"
GRACE="${SVCOMP_FULL_TIMEOUT_GRACE:-180}"
OUT_ROOT="${SVCOMP_FULL_OUT_ROOT:-output/vguide/experiments}"
DUMP_ROOT="${SVCOMP_FULL_DUMP_ROOT:-output/vguide/analysis_dumps}"
STAMP="${SVCOMP_FULL_STAMP:-$(date +%Y%m%d_%H%M%S)}"
DRY_RUN=0
FOREGROUND="${SVCOMP_FULL_FOREGROUND:-0}"

usage() {
  cat <<USAGE
Usage: $0 [--arm both|stock|vguide] [--set full_scalar] [--parallel N]
          [--timelimit SEC] [--heap SIZE] [--out-root DIR] [--dump-root DIR]
          [--stamp ID] [--foreground] [--dry-run]

Defaults: --arm both --set full_scalar --parallel 6 --timelimit 900 --heap 4000M
Detached mode is the default for real runs; use --foreground for smoke tests.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --arm) ARM="$2"; shift 2 ;;
    --set) SET="$2"; shift 2 ;;
    --parallel) PARALLEL="$2"; shift 2 ;;
    --timelimit) TIMELIMIT="$2"; shift 2 ;;
    --heap) HEAP="$2"; shift 2 ;;
    --out-root) OUT_ROOT="$2"; shift 2 ;;
    --dump-root) DUMP_ROOT="$2"; shift 2 ;;
    --stamp) STAMP="$2"; shift 2 ;;
    --foreground) FOREGROUND=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 1 ;;
  esac
done

case "$ARM" in
  both|stock|vguide) ;;
  *) echo "ERROR: --arm must be both, stock, or vguide" >&2; exit 1 ;;
esac

export JAVA="${JAVA:-$HOME/.local/bin/java}"
export PATH="${HOME}/.local/ant/bin:$(dirname "$JAVA"):${PATH:-}"
export SV_BENCHMARKS="${SV_BENCHMARKS:-$HOME/sv-benchmarks/c}"

MANIFEST="$SET_DIR/${SET}.list"
[[ -f "$MANIFEST" ]] || { echo "ERROR: unknown set '$SET' (no $MANIFEST)" >&2; exit 1; }
TASKS="$(grep -Ev '^[[:space:]]*($|#)' "$MANIFEST" | wc -l | tr -d ' ')"
ARM_COUNT=1
[[ "$ARM" == "both" ]] && ARM_COUNT=2
EST_SEC=$(( (TASKS * TIMELIMIT * ARM_COUNT + PARALLEL - 1) / PARALLEL ))

stock_out="$OUT_ROOT/${SET}_svcomp27_stock_${STAMP}"
vguide_out="$OUT_ROOT/${SET}_svcomp27_vguide_${STAMP}"
vguide_dump="$DUMP_ROOT/${SET}_svcomp27_vguide_${STAMP}"
launcher_log="$OUT_ROOT/svcomp_full_logs/${SET}_${ARM}_${STAMP}.log"

quote_cmd() {
  printf '%q ' "$@"
  printf '\n'
}

print_plan() {
  echo "=== svcomp27 full launcher plan ==="
  echo "date=$(date -Iseconds)"
  echo "set=$SET tasks=$TASKS arm=$ARM arm_count=$ARM_COUNT"
  echo "timelimit=${TIMELIMIT}s grace=${GRACE}s heap=$HEAP parallel=$PARALLEL"
  echo "estimated_wall_time=$((EST_SEC / 3600))h$(((EST_SEC % 3600) / 60))m$((EST_SEC % 60))s (tasks * timelimit * arms / parallel; pessimistic)"
  echo "stock_out=$stock_out"
  echo "vguide_out=$vguide_out"
  echo "vguide_dump=$vguide_dump"
  echo "launcher_log=$launcher_log"
}

load_api_key_if_needed() {
  if [[ "$ARM" == "stock" ]]; then
    return 0
  fi
  if [[ -z "${DEEPSEEK_API_KEY:-}" && -f "$HOME/.bashrc" ]]; then
    # Non-interactive shells do not load ~/.bashrc; load only the export line, without printing it.
    eval "$(grep '^export DEEPSEEK_API_KEY=' "$HOME/.bashrc" || true)"
    export DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-}"
  fi
  [[ -n "${DEEPSEEK_API_KEY:-}" ]] || { echo "ERROR: DEEPSEEK_API_KEY required for VGuide arm" >&2; exit 1; }
}

run_attribution() {
  local out="$1"
  if [[ -d "$out/logs" ]]; then
    echo "[post] attributing $out/logs -> $out/svcomp_attribution.csv"
    "$ATTR" "$out/logs" --out "$out/svcomp_attribution.csv" || true
  else
    echo "[post] skip attribution; missing $out/logs"
  fi
}

run_stock() {
  local cmd=(env VGUIDE_TIMEOUT_GRACE="$GRACE" "$RUN" cpa --set "$SET" --mode svcomp27-stock --parallel "$PARALLEL" --timelimit "$TIMELIMIT" --heap "$HEAP" --out "$stock_out")
  echo "=== stock arm start $(date -Iseconds) ==="
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "[dry-run] $(quote_cmd "${cmd[@]}")"
  else
    "${cmd[@]}"
    run_attribution "$stock_out"
  fi
  echo "=== stock arm done $(date -Iseconds) ==="
}

run_vguide() {
  local cmd=(env VGUIDE_TIMEOUT_GRACE="$GRACE" VGUIDE_ANALYSIS_DUMP_DIR="$vguide_dump" VGUIDE_ANALYSIS_BENCHMARK_SET="$SET" VGUIDE_ANALYSIS_TIMELIMIT_SEC="$TIMELIMIT" "$RUN" cpa --set "$SET" --mode svcomp --parallel "$PARALLEL" --timelimit "$TIMELIMIT" --heap "$HEAP" --out "$vguide_out")
  echo "=== vguide arm start $(date -Iseconds) ==="
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "[dry-run] $(quote_cmd "${cmd[@]}")"
  else
    load_api_key_if_needed
    "${cmd[@]}"
    run_attribution "$vguide_out"
  fi
  echo "=== vguide arm done $(date -Iseconds) ==="
}

print_plan

if [[ "$DRY_RUN" != "1" && "$FOREGROUND" != "1" ]]; then
  mkdir -p "$(dirname "$launcher_log")"
  echo "Launching detached nohup job..."
  cmd=(env
    SVCOMP_FULL_FOREGROUND=1
    SVCOMP_FULL_ARM="$ARM"
    SVCOMP_FULL_SET="$SET"
    SVCOMP_FULL_PARALLEL="$PARALLEL"
    SVCOMP_FULL_TIMELIMIT="$TIMELIMIT"
    SVCOMP_FULL_HEAP="$HEAP"
    SVCOMP_FULL_TIMEOUT_GRACE="$GRACE"
    SVCOMP_FULL_OUT_ROOT="$OUT_ROOT"
    SVCOMP_FULL_DUMP_ROOT="$DUMP_ROOT"
    SVCOMP_FULL_STAMP="$STAMP"
    JAVA="$JAVA"
    PATH="$PATH"
    SV_BENCHMARKS="$SV_BENCHMARKS"
    "$0" --foreground --arm "$ARM" --set "$SET" --parallel "$PARALLEL" --timelimit "$TIMELIMIT" --heap "$HEAP" --out-root "$OUT_ROOT" --dump-root "$DUMP_ROOT" --stamp "$STAMP")
  nohup "${cmd[@]}" >"$launcher_log" 2>&1 &
  pid=$!
  echo "pid=$pid"
  echo "log=$launcher_log"
  echo "tail -f $launcher_log"
  exit 0
fi

cd "$REPO"
case "$ARM" in
  both) run_stock; run_vguide ;;
  stock) run_stock ;;
  vguide) run_vguide ;;
esac

echo "=== svcomp27 full launcher done $(date -Iseconds) ==="
