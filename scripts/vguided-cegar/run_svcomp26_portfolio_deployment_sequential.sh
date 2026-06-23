#!/usr/bin/env bash
# Sequential svcomp26 portfolio deployment ladder (Table 2 track ii).
# Arms 0→3 run one after another; each arm may use PARALLEL concurrent tasks internally.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
RUN="$REPO/scripts/vguided-cegar/run.sh"
SET="loops_reachsafety_unreach"
PARALLEL="${VGUIDE_PARALLEL:-8}"
TIMELIMIT="${TIMELIMIT:-300}"
DATE_TAG="${SVCOMP26_DEPLOY_DATE:-$(date +%Y%m%d)}"
ROOT="$REPO/output/vguide/experiments/svcomp26_deploy_${DATE_TAG}"
MASTER_LOG="$ROOT/run.log"
STATUS="$ROOT/status.txt"

mkdir -p "$ROOT"

log() {
  local msg="[$(date -Iseconds)] $*"
  echo "$msg" | tee -a "$MASTER_LOG"
}

count_solved() {
  local summary="$1"
  [[ -f "$summary" ]] || { echo "0"; return; }
  awk -F, 'NR>1 && ($3=="TRUE" || $3=="FALSE") {c++} END {print c+0}' "$summary"
}

par2_avg() {
  local summary="$1"
  [[ -f "$summary" ]] || { echo "nan"; return; }
  python3 - "$summary" "$TIMELIMIT" <<'PY'
import csv, sys
summary, tl = sys.argv[1], float(sys.argv[2])
total, n = 0.0, 0
with open(summary, newline="") as f:
    for row in csv.DictReader(f):
        n += 1
        res = (row.get("result") or "").upper()
        wall = float(row.get("wall_s") or 0)
        total += wall if res in ("TRUE", "FALSE") else 2 * tl
print(f"{total / n:.1f}" if n else "nan")
PY
}

reuse_step0() {
  local reuse="${STEP0_REUSE:-$REPO/output/vguide/experiments/loops_reachsafety_unreach_svcomp26_20260612}"
  local link="$ROOT/step0_stock"
  [[ -d "$reuse" ]] || die "STEP0_REUSE missing: $reuse"
  if [[ -L "$link" ]]; then
    rm -f "$link"
  elif [[ -e "$link" ]]; then
    mv "$link" "${link}.aborted.$(date +%s)" 2>/dev/null || true
  fi
  ln -sfn "$reuse" "$link"
  local summary="$link/${SET}_summary.csv"
  local solved par2
  solved="$(count_solved "$summary")"
  par2="$(par2_avg "$summary")"
  log "ARM 0 REUSE $reuse solved=$solved par2_avg=$par2"
  echo "arm=0 status=reused source=$reuse solved=$solved par2_avg=$par2" >>"$STATUS"
}

die() { echo "ERROR: $*" >&2; exit 1; }

check_arm_config() {
  local out="$1"
  local expect_schedule="$2"
  local expect_peel="$3"
  local logs="$out/logs"
  [[ -d "$logs" ]] || return 0
  if rg -l "Mismatch of configuration options when loading.*'vguide\\." "$logs" 2>/dev/null | head -1 | grep -q .; then
    die "arm $out: vguide --option override lost (see logs)"
  fi
  local hit
  hit="$(rg -l "schedule= ${expect_schedule}\\b" "$logs" 2>/dev/null | head -1 || true)"
  if [[ -z "$hit" ]]; then
    die "arm $out: expected schedule ${expect_schedule} not found under $logs"
  fi
  log "ARM config OK schedule=${expect_schedule} peel=${expect_peel} sample=$hit"
}

run_arm() {
  local arm_id="$1"
  local step_dir="$2"
  shift 2
  local out="$ROOT/$step_dir"
  local summary="$out/${SET}_summary.csv"
  if [[ -e "$out" ]]; then
    mv "$out" "${out}.aborted.$(date +%s)"
    log "ARM $arm_id archived prior out=$out"
  fi
  log "ARM $arm_id START out=$out mode/opts: $*"
  echo "arm=$arm_id status=running started=$(date -Iseconds) out=$out" >>"$STATUS"
  "$RUN" cpa \
    --set "$SET" \
    --parallel "$PARALLEL" \
    --timelimit "$TIMELIMIT" \
    --out "$out" \
    "$@"
  local solved par2
  solved="$(count_solved "$summary")"
  par2="$(par2_avg "$summary")"
  log "ARM $arm_id DONE solved=$solved par2_avg=$par2 summary=$summary"
  echo "arm=$arm_id status=done finished=$(date -Iseconds) solved=$solved par2_avg=$par2 out=$out" >>"$STATUS"
}

run_arm_checked() {
  local arm_id="$1"
  local step_dir="$2"
  local expect_schedule="$3"
  local expect_peel="$4"
  shift 4
  run_arm "$arm_id" "$step_dir" "$@"
  check_arm_config "$ROOT/$step_dir" "$expect_schedule" "$expect_peel"
}

START_ARM="${START_ARM:-1}"

log "=== svcomp26 portfolio deployment batch START parallel=$PARALLEL timelimit=$TIMELIMIT start_arm=$START_ARM ==="
: >"$STATUS"

reuse_step0

if [[ "$START_ARM" -le 1 ]]; then
run_arm_checked 1 step1_fire1 EVERY_N_AND_INTERVAL 0 \
  --mode svcomp26-vguide \
  --option vguide.llmCallSchedule=every_n_and_interval \
  --option vguide.peelLoopHeadThreshold=0
fi

if [[ "$START_ARM" -le 2 ]]; then
run_arm_checked 2 step2_stockfirst EVERY_N_OR_INTERVAL 0 \
  --mode svcomp26-vguide \
  --option vguide.llmCallSchedule=every_n_or_interval \
  --option vguide.peelLoopHeadThreshold=0
fi

if [[ "$START_ARM" -le 3 ]]; then
run_arm_checked 3 step3_peel4 EVERY_N_OR_INTERVAL 4 \
  --mode svcomp26-vguide \
  --option vguide.llmCallSchedule=every_n_or_interval \
  --option vguide.peelLoopHeadThreshold=4
fi

log "=== ALL ARMS COMPLETE ==="
log "Quick summary:"
for d in step0_stock step1_fire1 step2_stockfirst step3_peel4; do
  s="$ROOT/$d/${SET}_summary.csv"
  log "  $d: solved=$(count_solved "$s") par2=$(par2_avg "$s")"
done
