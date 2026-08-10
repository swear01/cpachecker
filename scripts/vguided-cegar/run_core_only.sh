#!/usr/bin/env bash
# Core-only two-arm runner for the hard-case evaluation (Issue #2).
#
# Usage:
#   export SV_BENCHMARKS=~/sv-benchmarks/c   # required
#   export DEEPSEEK_API_KEY=...              # required for --arm augmented (or use replay)
#   ./run_core_only.sh --arm stock --manifest /path/candidate-manifest.json \
#       --out output/vguide/core_only/stock_core
#   ./run_core_only.sh --arm augmented --manifest /path/candidate-manifest.json \
#       --out output/vguide/core_only/augmented_core
#
# Options:
#   --arm stock|augmented   which arm (required)
#   --manifest <json>       frozen Hard-case Dataset v2 manifest (required)
#   --out <dir>             output directory (required)
#   --parallel N            max concurrent CPA jobs (default 8)
#   --timelimit S           per-task CPU limit in seconds (default 300)
#   --heap M                JVM heap (default 6000M)
#   --dry-run               print commands only
#
# Output:
#   <out>/tasks.tsv           frozen task rows (source-hash verified)
#   <out>/records.jsonl      one JSON record per task (hashes, verdict,
#                            resources, refinements, LLM metrics, failure)
#   <out>/run_meta.json      arm, commit, config/manifest hashes, limits
#   <out>/logs/<task>.log    CPAchecker log per task
#   <out>/dumps/             VGuide analysis dump (augmented arm only)
#
# One task per record; interrupted/invalid runs are recorded as
# infrastructure failures and never silently retried.

set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CPA_SH="$REPO/scripts/cpa.sh"
SV_BENCHMARKS="${SV_BENCHMARKS:-$HOME/sv-benchmarks/c}"
RECORDS_PY="$SCRIPT_DIR/core_only_records.py"
export PATH="${HOME}/.local/ant/bin:${PATH:-}"

die() { echo "ERROR: $*" >&2; exit 1; }

ARM="" MANIFEST="" OUT="" PARALLEL="8" TIMELIMIT="300" HEAP="6000M" DRY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --arm) ARM="$2"; shift 2 ;;
    --manifest) MANIFEST="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --parallel) PARALLEL="$2"; shift 2 ;;
    --timelimit) TIMELIMIT="$2"; shift 2 ;;
    --heap) HEAP="$2"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    *) die "unknown argument: $1" ;;
  esac
done
[[ -n "$ARM" ]] || die "--arm stock|augmented required"
[[ "$ARM" == "stock" || "$ARM" == "augmented" ]] || die "--arm must be stock or augmented"
[[ -f "$MANIFEST" ]] || die "--manifest file required: $MANIFEST"
[[ -n "$OUT" ]] || die "--out required"
[[ -d "$SV_BENCHMARKS" ]] || die "SV_BENCHMARKS not found: $SV_BENCHMARKS (export SV_BENCHMARKS=~/sv-benchmarks/c)"

mkdir -p "$OUT/logs"
if [[ "$ARM" == "augmented" ]]; then
  mkdir -p "$OUT/dumps"
  [[ -n "${DEEPSEEK_API_KEY:-}" || -n "${VGUIDE_LLM_REPLAY_DIR:-}" ]] \
    || die "augmented arm requires DEEPSEEK_API_KEY (or VGUIDE_LLM_REPLAY_DIR)"
fi

if [[ "$ARM" == "stock" ]]; then
  CONFIG="config/predicateAnalysis.properties"
  USE_VGUIDE="false"
else
  CONFIG="config/predicateAnalysis-vguide.properties"
  USE_VGUIDE="true"
fi
SPEC="$REPO/config/specification/sv-comp-reachability.spc"
TIMEOUT_GRACE=30

if [[ "$DRY" == "1" ]]; then
  echo "arm=$ARM manifest=$MANIFEST out=$OUT config=$CONFIG use_vguide=$USE_VGUIDE"
  echo "tasks: $(python3 "$RECORDS_PY" tasks --manifest "$MANIFEST" --sv-benchmarks "$SV_BENCHMARKS" --no-verify --out "$OUT/tasks.tsv")"
  exit 0
fi

# 1. Frozen task rows (hash-verified; fails on any mismatch).
python3 "$RECORDS_PY" tasks --manifest "$MANIFEST" --sv-benchmarks "$SV_BENCHMARKS" --out "$OUT/tasks.tsv"

# 2. Run metadata.
COMMIT="$(git -C "$REPO" rev-parse HEAD)"
CONFIG_SHA="$(python3 -c "import sys; sys.path.insert(0, '$SCRIPT_DIR'); import core_only_config_diff as d; print(d.config_sha256(__import__('pathlib').Path('$REPO/$CONFIG')))")"
MANIFEST_SHA="$(sha256sum "$MANIFEST" | cut -d' ' -f1)"
cat >"$OUT/run_meta.json" <<EOF
{
  "arm": "$ARM",
  "commit": "$COMMIT",
  "config": "$CONFIG",
  "config_sha256": "$CONFIG_SHA",
  "manifest": "$MANIFEST",
  "manifest_sha256": "$MANIFEST_SHA",
  "timelimit_s": $TIMELIMIT,
  "parallel": $PARALLEL,
  "heap": "$HEAP",
  "spec": "$SPEC",
  "model": "${DEEPSEEK_MODEL:-deepseek-v4-pro}",
  "started_at": "$(date -Iseconds)"
}
EOF

# 3. Run each task once (parallel), then emit one record per task.
rm -f "$OUT/records.jsonl"
export -f sha256sum 2>/dev/null || true
run_one() {
  local line="$1"
  local task source expected model family tsha ssha
  IFS=$'\t' read -r task source expected model family tsha ssha <<<"$line"
  local task_name="${task//\//_}"
  local log="$OUT/logs/${task_name}.log"
  local cmd=(
    timeout "$((TIMELIMIT + TIMEOUT_GRACE))s"
    "$CPA_SH" --heap "$HEAP"
    --config "$REPO/$CONFIG"
    --option "cpa.predicate.refinement.useVocabularyGuide=$USE_VGUIDE"
    --timelimit "${TIMELIMIT}s"
    --spec "$SPEC"
    --stats
    --no-output-files
    "$SV_BENCHMARKS/$source"
  )
  if [[ "$DRY" == "1" ]]; then
    echo "${cmd[*]}"
    return 0
  fi
  set +e
  if [[ "$ARM" == "augmented" ]]; then
    VGUIDE_LLM_CACHE_NAMESPACE="$task" VGUIDE_ANALYSIS_DUMP_DIR="$OUT/dumps" \
      "${cmd[@]}" >"$log" 2>&1
  else
    "${cmd[@]}" >"$log" 2>&1
  fi
  set -e
  # One JSON record per task (also for failures — never silently dropped).
  local rowfile dump_dir=""
  rowfile="$(mktemp)"
  printf '%s\n' "$line" >"$rowfile"
  [[ "$ARM" == "augmented" ]] && dump_dir="$OUT/dumps"
  python3 "$RECORDS_PY" record \
    --task "$rowfile" \
    --log "$log" \
    --dump-dir "$dump_dir" \
    --config-sha "$CONFIG_SHA" \
    --commit "$COMMIT" \
    --arm "$ARM" \
    --timelimit "$TIMELIMIT" \
    --out "$OUT/records.jsonl"
  rm -f "$rowfile"
}
export -f run_one
export OUT ARM USE_VGUIDE REPO CPA_SH SV_BENCHMARKS RECORDS_PY CONFIG SPEC TIMELIMIT TIMEOUT_GRACE HEAP COMMIT CONFIG_SHA

# tasks.tsv has a header row; skip it.
tail -n +2 "$OUT/tasks.tsv" | xargs -P "$PARALLEL" -I{} bash -c 'run_one "$1"' _ {}

# 4. Verify completeness: one record per task.
N_TASKS="$(tail -n +2 "$OUT/tasks.tsv" | wc -l | tr -d ' ')"
N_RECORDS="$(wc -l <"$OUT/records.jsonl" | tr -d ' ')"
[[ "$N_RECORDS" == "$N_TASKS" ]] || die "record mismatch: $N_RECORDS records for $N_TASKS tasks"
echo "core-only $ARM arm complete: $N_RECORDS records"
python3 - "$OUT/records.jsonl" <<'EOF'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
from collections import Counter
print("verdicts:", dict(Counter(r["verdict"] for r in rows)))
print("failures:", dict(Counter(r["failure_category"] for r in rows)))
EOF
