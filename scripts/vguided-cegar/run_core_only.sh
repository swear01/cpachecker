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

# Formal-run CPU isolation (Baseline-Protocol): the 8 physical P-cores of the
# 13900K/14900K pool, without SMT siblings and without E-cores.
P_CORE_LIST="0,2,4,6,8,10,12,14"
P_CORE_RANGE="0-15"


ARM="" MANIFEST="" OUT="" PARALLEL="8" TIMELIMIT="300" HEAP="6000M" DRY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --arm) ARM="$2"; shift 2 ;;
    --manifest) MANIFEST="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --parallel) PARALLEL="$2"; shift 2 ;;
    --timelimit) TIMELIMIT="${2%s}"; shift 2 ;;
    --heap) HEAP="$2"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    *) die "unknown argument: $1" ;;
  esac
done
[[ -n "$ARM" ]] || die "--arm stock|augmented required"
[[ "$ARM" == "stock" || "$ARM" == "augmented" ]] || die "--arm must be stock or augmented"
[[ -f "$MANIFEST" ]] || die "--manifest file required: $MANIFEST"
[[ -n "$OUT" ]] || die "--out required"
[[ "$TIMELIMIT" =~ ^[1-9][0-9]*$ ]] || die "TIMELIMIT must be a positive integer, got: $TIMELIMIT"
[[ -d "$SV_BENCHMARKS" ]] || die "SV_BENCHMARKS not found: $SV_BENCHMARKS (export SV_BENCHMARKS=~/sv-benchmarks/c)"

# Refuse to start a formal run when foreign processes occupy the P-core pool
# (Baseline-Protocol: load monitoring; foreign_p_core_contention is a failure).
# Note: mpstat lines start with a timestamp (23:21:15); the CPU id is field $2
# with -F' +' — match $2 as a pure integer to skip header/avg lines.
check_p_cores_idle() {
  local busy
  busy=$(LC_ALL=C mpstat -P "$P_CORE_RANGE" 1 1 2>/dev/null | awk -F' +' '
    $2 ~ /^[0-9]+$/ { if (100 - $NF >= 50) print $2 }')
  if [[ -n "$busy" ]]; then
    die "P-core contention: busy cores: $busy (formal runs require an idle P-core pool; use the fleet availability monitor to pick a free machine)"
  fi
  ps -eo user,pgid,psr,pcpu,comm --no-headers | awk -v list="$P_CORE_LIST" -v u="$USER" -v g="$(ps -o pgid= -p $$ | tr -d ' ')" '
    BEGIN { n = split(list, a, ","); for (i in a) allowed[a[i]] = 1 }
    $1 == u && $2 != g && $3 in allowed && ($4 + 0) > 25 { bad[$3] = 1 }
    END { for (c in bad) print c }' | while read -r c; do
      die "P-core $c has concurrent local processes; formal runs require an idle P-core pool"
  done
}
check_p_cores_idle

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
TIMEOUT_GRACE="${VGUIDE_TIMEOUT_GRACE:-10}"
TIMEOUT_GRACE="${TIMEOUT_GRACE%s}" # strip a trailing 's'
[[ "$TIMEOUT_GRACE" =~ ^[0-9]+$ ]] || die "TIMEOUT_GRACE must be a non-negative integer, got: $TIMEOUT_GRACE"

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
LOAD_CHECK="$(LC_ALL=C mpstat -P 0-15 1 1 2>/dev/null | awk -F' +' '$2 ~ /^[0-9]+$/ { if (100 - $NF >= 50) b = b " " $2 } END { print (b == "") ? "idle" : "busy:" b }')"
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Effective thinking settings mirror PredicateProposalClient's normalization
# (aliases: true/on/1 -> enabled; default -> high; medium -> high; xhigh -> max).
THINKING_RAW="${VGUIDE_LLM_THINKING:-disabled}"
case "${THINKING_RAW,,}" in
  enabled|true|on|1) THINKING="enabled" ;;
  *) THINKING="disabled" ;;
esac
# Effective reasoning effort mirrors PredicateProposalClient.reasoningEffortFromEnv
# (default -> high; medium -> high; xhigh -> max). When thinking is disabled the
# client sets effort to null and sends no effort — record that as null too.
EFFORT_RAW="${VGUIDE_LLM_REASONING_EFFORT:-}"
if [[ "$THINKING" == "disabled" ]]; then
  EFFORT="null"
else
  case "${EFFORT_RAW,,}" in
    ""|default) EFFORT="\"high\"" ;;
    low) EFFORT="\"low\"" ;;
    medium|high) EFFORT="\"high\"" ;;
    max|xhigh) EFFORT="\"max\"" ;;
    *) EFFORT="\"high\"" ;;
  esac
fi

# Resume support: an existing run_meta.json must match this invocation's
# provenance exactly (arm, commit, config, manifest, timelimit, heap,
# parallel, model, thinking); otherwise refuse — a mixed-provenance dataset
# is invalid. Values are passed via the environment (single-quoted heredoc:
# no shell interpolation).
if [[ -f "$OUT/run_meta.json" ]]; then
  ARM_C="$ARM" COMMIT_C="$COMMIT" CONFIG_SHA_C="$CONFIG_SHA" MANIFEST_SHA_C="$MANIFEST_SHA" \
  TIMELIMIT_C="$TIMELIMIT" GRACE_C="$TIMEOUT_GRACE" HEAP_C="$HEAP" PARALLEL_C="$PARALLEL" \
  MODEL_C="${DEEPSEEK_MODEL:-deepseek-v4-pro}" THINKING_C="$THINKING" EFFORT_C="$EFFORT" \
  python3 - "$OUT/run_meta.json" <<'EOF'
import json, os, sys
old = json.load(open(sys.argv[1]))
want = {
    "arm": os.environ["ARM_C"],
    "commit": os.environ["COMMIT_C"],
    "config_sha256": os.environ["CONFIG_SHA_C"],
    "manifest_sha256": os.environ["MANIFEST_SHA_C"],
    "timelimit_s": float(os.environ["TIMELIMIT_C"]),
    "timeout_grace": int(os.environ["GRACE_C"]),
    "heap": os.environ["HEAP_C"],
    "parallel": int(os.environ["PARALLEL_C"]),
    "model": os.environ["MODEL_C"],
    "thinking": os.environ["THINKING_C"],
    "reasoning_effort": json.loads(os.environ["EFFORT_C"]),
}
mismatch = [k for k, v in want.items() if old.get(k) != v]
if mismatch:
    print("provenance mismatch: " + ", ".join(mismatch), file=sys.stderr)
    sys.exit(1)
EOF
  if [[ $? -ne 0 ]]; then
    die "resume refused: $OUT/run_meta.json provenance differs from this invocation (use a fresh OUT dir)"
  fi
  echo "resuming: existing run_meta.json matches this invocation"
fi

cat >"$OUT/run_meta.json" <<EOF
{
  "arm": "$ARM",
  "commit": "$COMMIT",
  "config": "$CONFIG",
  "config_sha256": "$CONFIG_SHA",
  "manifest": "$MANIFEST",
  "manifest_sha256": "$MANIFEST_SHA",
  "timelimit_s": $TIMELIMIT,
  "timeout_grace": $TIMEOUT_GRACE,
  "parallel": $PARALLEL,
  "heap": "$HEAP",
  "spec": "$SPEC",
  "model": "${DEEPSEEK_MODEL:-deepseek-v4-pro}",
  "thinking": "$THINKING",
  "reasoning_effort": "$EFFORT",
  "started_at": "$STARTED_AT",
  "cpu_isolation": "taskset $P_CORE_LIST (8 physical P-cores, no SMT sibling, no E-core)",
  "load_check": "$LOAD_CHECK"
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
  # Resume support: a per-task record already written means this task finished
  # in a previous invocation — skip it instead of re-running. The record must
  # parse as JSON: a truncated/corrupt record (killed while appending) is
  # discarded and the task rerun.
  if [[ -f "$OUT/logs/${task_name}.json" ]]; then
    if python3 -c "import json, sys; json.load(open(sys.argv[1]))" "$OUT/logs/${task_name}.json" 2>/dev/null; then
      echo "skip $task (record exists)"
      return 0
    fi
    echo "discard corrupt record for $task; rerunning"
    rm -f "$OUT/logs/${task_name}.json"
  fi
  # A previous attempt may have left a partial dump (no record was written):
  # clear it so LLM rounds / refinements from both attempts do not mix.
  [[ "$ARM" == "augmented" ]] && rm -rf "$OUT/dumps/${task_name}"
  local cmd=(
    timeout "$((TIMELIMIT + TIMEOUT_GRACE))s"
    taskset -c "$P_CORE_LIST"
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
    # Per-task dump root: benchmark base names can collide across families.
    VGUIDE_LLM_CACHE_NAMESPACE="$task" VGUIDE_ANALYSIS_DUMP_DIR="$OUT/dumps/${task_name}" \
      "${cmd[@]}" >"$log" 2>&1
  else
    "${cmd[@]}" >"$log" 2>&1
  fi
  local rc=$?
  set -e
  # Complete records: append a synthetic UNKNOWN summary for logs that died without
  # a CPA summary line (native hang/crash), mirroring run_benchmark_set.sh.
  if ! grep -q 'Verification result:' "$log" 2>/dev/null; then
    {
      echo ""
      echo "--- core-only runner post-process $(date -Iseconds) ---"
      echo "Verification result: UNKNOWN, incomplete analysis (no CPA summary line)."
      echo "Total time for CPAchecker: ${TIMELIMIT}.000s"
    } >>"$log"
  fi
  # One JSON record per task (also for failures — never silently dropped).
  local dump_dir=""
  [[ "$ARM" == "augmented" ]] && dump_dir="$OUT/dumps/${task_name}"
  python3 "$RECORDS_PY" record \
    --task-row "$line" \
    --log "$log" \
    --dump-dir "$dump_dir" \
    --config-sha "$CONFIG_SHA" \
    --commit "$COMMIT" \
    --arm "$ARM" \
    --timelimit "$TIMELIMIT" \
    --exit-code "$rc" \
    --out "$OUT/logs/${task_name}.json"
}
export -f run_one
export OUT ARM USE_VGUIDE REPO CPA_SH SV_BENCHMARKS RECORDS_PY CONFIG SPEC TIMELIMIT TIMEOUT_GRACE HEAP COMMIT CONFIG_SHA P_CORE_LIST

# 4. Run each task (no header row in tasks.tsv), merge per-task records in order,
#    then verify completeness.
# Null-delimited so task names with spaces/special chars are safe
# (-n 1 keeps BSD/macOS xargs happy instead of -I).
tr '\n' '\0' <"$OUT/tasks.tsv" | xargs -0 -n 1 -P "$PARALLEL" bash -c 'run_one "$1"' _

rm -f "$OUT/records.jsonl"
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -n "$line" ]] || continue
  task="$(echo "$line" | cut -f1)"
  rec="$OUT/logs/${task//\//_}.json"
  [[ -f "$rec" ]] || die "missing record for $task"
  cat "$rec" >>"$OUT/records.jsonl"
done <"$OUT/tasks.tsv"

N_TASKS="$(wc -l <"$OUT/tasks.tsv" | tr -d ' ')"
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
