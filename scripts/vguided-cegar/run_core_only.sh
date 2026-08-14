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

# 0. Output-dir lock: refuse overlapping invocations on the same --out.
# PID-based: a lock whose holder died (SIGKILL/host crash) is reclaimed, but only
# when no worker processes of that run remain.
if ! mkdir "$OUT/.run.lock" 2>/dev/null; then
  if [[ -f "$OUT/.run.lock/pid" ]]; then
    LOCK_PID="$(cat "$OUT/.run.lock/pid")"
    if ! kill -0 "$LOCK_PID" 2>/dev/null; then
      if pgrep -f "$OUT/logs" >/dev/null 2>&1; then
        die "stale lock for dead PID $LOCK_PID but workers still run for $OUT"
      fi
      echo "reclaiming stale lock (dead PID $LOCK_PID)"
      rm -rf "$OUT/.run.lock"
      mkdir "$OUT/.run.lock" || die "cannot create $OUT/.run.lock"
    else
      die "$OUT/.run.lock held by live PID $LOCK_PID"
    fi
  else
    # lock dir without a pid file: holder was killed between mkdir and pid write.
    # Reclaim it if no workers of that run remain.
    if pgrep -f "$OUT/logs" >/dev/null 2>&1; then
      die "$OUT/.run.lock exists without a pid file but workers still run for $OUT"
    fi
    echo "reclaiming lock dir without pid (no workers remain for $OUT)"
    rm -rf "$OUT/.run.lock"
    mkdir "$OUT/.run.lock" || die "cannot create $OUT/.run.lock"
  fi
fi
echo "$$" >"$OUT/.run.lock/pid"
trap 'rm -rf "$OUT/.run.lock" 2>/dev/null || true' EXIT

# 2. Run metadata (computed before tasks.tsv so the resume provenance check can
# validate the invocation without overwriting an existing tasks.tsv).
COMMIT="$(git -C "$REPO" rev-parse HEAD)"
CONFIG_SHA="$(python3 -c "import sys; sys.path.insert(0, '$SCRIPT_DIR'); import core_only_config_diff as d; print(d.config_sha256(__import__('pathlib').Path('$REPO/$CONFIG')))")"
MANIFEST_SHA="$(sha256sum "$MANIFEST" | cut -d' ' -f1)"
SPEC_SHA="$(sha256sum "$SPEC" | cut -d' ' -f1)"
CPA_SH_SHA="$(sha256sum "$CPA_SH" | cut -d' ' -f1)"
LOAD_CHECK="$(LC_ALL=C mpstat -P 0-15 1 1 2>/dev/null | awk -F' +' '$2 ~ /^[0-9]+$/ { if (100 - $NF >= 50) b = b " " $2 } END { print (b == "") ? "idle" : "busy:" b }')"
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Effective thinking settings mirror PredicateProposalClient's normalization
# (aliases: true/on/1 -> enabled; default -> high; medium -> high; xhigh -> max).
# Portable lowercase (Bash 3.2/macOS compatible).
lc() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }
THINKING_RAW="${VGUIDE_LLM_THINKING:-disabled}"
case "$(lc "$THINKING_RAW")" in
  enabled|true|on|1) THINKING="enabled" ;;
  *) THINKING="disabled" ;;
esac
# Effective reasoning effort mirrors PredicateProposalClient.reasoningEffortFromEnv
# (default -> high; medium -> high; xhigh -> max). When thinking is disabled the
# client sets effort to null and sends no effort — record that as null too.
# EFFORT is a JSON-encoded token (null | "high" | "low" | "max").
EFFORT_RAW="${VGUIDE_LLM_REASONING_EFFORT:-}"
if [[ "$THINKING" == "disabled" ]]; then
  EFFORT="null"
else
  case "$(lc "$EFFORT_RAW")" in
    ""|default) EFFORT="\"high\"" ;;
    low) EFFORT="\"low\"" ;;
    medium|high) EFFORT="\"high\"" ;;
    max|xhigh) EFFORT="\"max\"" ;;
    *) EFFORT="\"high\"" ;;
  esac
fi

# Resume support: an existing run_meta.json must match this invocation's
# provenance exactly (arm, commit, config, manifest, timelimit, grace, heap,
# parallel, model, thinking, response-cache mode); otherwise refuse — a
# mixed-provenance dataset is invalid. Values are passed via the environment
# (single-quoted heredoc: no shell interpolation).
OLD_LOADS_JSON="[]"
if [[ -f "$OUT/run_meta.json" ]]; then
  OLD_META="$(python3 -c "import json,sys; print(json.dumps(json.load(open(sys.argv[1]))))" "$OUT/run_meta.json" 2>/dev/null || echo '{}')"
  OLD_LOADS_JSON="$(printf '%s' "$OLD_META" | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin).get('load_checks', [])))" 2>/dev/null || echo '[]')"
  OLD_STARTED_AT="$(printf '%s' "$OLD_META" | python3 -c "import json,sys; print(json.load(sys.stdin).get('started_at',''))")"
  OLD_LOAD_CHECK="$(printf '%s' "$OLD_META" | python3 -c "import json,sys; print(json.load(sys.stdin).get('load_check',''))")"
  ARM_C="$ARM" COMMIT_C="$COMMIT" CONFIG_SHA_C="$CONFIG_SHA" MANIFEST_SHA_C="$MANIFEST_SHA" SPEC_SHA_C="$SPEC_SHA" CPA_SH_SHA_C="$CPA_SH_SHA" \
  TIMELIMIT_C="$TIMELIMIT" GRACE_C="$TIMEOUT_GRACE" HEAP_C="$HEAP" PARALLEL_C="$PARALLEL" \
  MODEL_C="${DEEPSEEK_MODEL:-deepseek-v4-pro}" THINKING_C="$THINKING" EFFORT_C="$EFFORT" \
  RECORD_C="${VGUIDE_LLM_RECORD_DIR:-}" REPLAY_C="${VGUIDE_LLM_REPLAY_DIR:-}" \
  REPLAY_FP_C="$(if [[ -n "${VGUIDE_LLM_REPLAY_DIR:-}" ]]; then find "$VGUIDE_LLM_REPLAY_DIR" -type f -exec sha256sum {} + 2>/dev/null | sort | sha256sum | cut -d' ' -f1; fi)" \
  APIURL_C="${VGUIDE_LLM_API_URL:-}" MAXTOK_C="${VGUIDE_LLM_MAX_COMPLETION_TOKENS:-}" \
  TIMEOUTSEC_C="${VGUIDE_LLM_TIMEOUT_SEC:-}" PRESERVE_C="${VGUIDE_LLM_REPLAY_PRESERVE_LATENCY:-}" \
  python3 - "$OUT/run_meta.json" <<'EOF' || die "resume refused: $OUT/run_meta.json provenance differs from this invocation (use a fresh OUT dir)"
import json, os, sys
old = json.load(open(sys.argv[1]))
want = {
    "arm": os.environ["ARM_C"],
    "commit": os.environ["COMMIT_C"],
    "config_sha256": os.environ["CONFIG_SHA_C"],
    "manifest_sha256": os.environ["MANIFEST_SHA_C"],
    "spec_sha256": os.environ["SPEC_SHA_C"],
    "timelimit_s": float(os.environ["TIMELIMIT_C"]),
    "timeout_grace": int(os.environ["GRACE_C"]),
    "heap": os.environ["HEAP_C"],
    "parallel": int(os.environ["PARALLEL_C"]),
    "model": os.environ["MODEL_C"],
    "thinking": os.environ["THINKING_C"],
    "reasoning_effort": json.loads(os.environ["EFFORT_C"]),
    "llm_record_dir": os.environ["RECORD_C"],
    "llm_replay_dir": os.environ["REPLAY_C"],
    "llm_replay_fingerprint": os.environ.get("REPLAY_FP_C", ""),
    "llm_api_url": os.environ["APIURL_C"],
    "llm_max_completion_tokens": os.environ["MAXTOK_C"],
    "llm_timeout_sec": os.environ["TIMEOUTSEC_C"],
    "llm_replay_preserve_latency": os.environ["PRESERVE_C"],
}
missing = [k for k in want if k not in old]
differing = [k for k in want if k in old and old[k] != want[k]]
if missing:
    print("run_meta.json predates the current schema; missing: " + ", ".join(missing), file=sys.stderr)
    sys.exit(1)
if differing:
    print("provenance mismatch: " + ", ".join(differing), file=sys.stderr)
    sys.exit(1)
EOF
  echo "resuming: existing run_meta.json matches this invocation"
  [[ -n "$OLD_STARTED_AT" ]] && STARTED_AT="$OLD_STARTED_AT"    # keep the original start time
  [[ -n "$OLD_LOAD_CHECK" ]] && LOAD_CHECK="$OLD_LOAD_CHECK"    # keep the original load check
fi

# Atomic, escaping-safe write of run_meta.json (values via env, json.dumps).
ARM_M="$ARM" COMMIT_M="$COMMIT" CONFIG_M="$CONFIG" CONFIG_SHA_M="$CONFIG_SHA" \
MANIFEST_M="$MANIFEST" MANIFEST_SHA_M="$MANIFEST_SHA" SPEC_SHA_M="$SPEC_SHA" CPA_SH_SHA_M="$CPA_SH_SHA" \
TIMELIMIT_M="$TIMELIMIT" GRACE_M="$TIMEOUT_GRACE" PARALLEL_M="$PARALLEL" HEAP_M="$HEAP" \
SPEC_M="$SPEC" MODEL_M="${DEEPSEEK_MODEL:-deepseek-v4-pro}" THINKING_M="$THINKING" EFFORT_M="$EFFORT" \
RECORD_M="${VGUIDE_LLM_RECORD_DIR:-}" REPLAY_M="${VGUIDE_LLM_REPLAY_DIR:-}" \
REPLAY_FP_M="$(if [[ -n "${VGUIDE_LLM_REPLAY_DIR:-}" ]]; then find "$VGUIDE_LLM_REPLAY_DIR" -type f -exec sha256sum {} + 2>/dev/null | sort | sha256sum | cut -d' ' -f1; fi)" \
  APIURL_M="${VGUIDE_LLM_API_URL:-}" MAXTOK_M="${VGUIDE_LLM_MAX_COMPLETION_TOKENS:-}" \
TIMEOUTSEC_M="${VGUIDE_LLM_TIMEOUT_SEC:-}" PRESERVE_M="${VGUIDE_LLM_REPLAY_PRESERVE_LATENCY:-}" \
STARTED_M="$STARTED_AT" LOAD_M="$LOAD_CHECK" LOADS_M="$OLD_LOADS_JSON" P_CORES_M="$P_CORE_LIST" \
python3 - "$OUT/run_meta.json" <<'EOF'
import json, os, sys
meta = {
    "arm": os.environ["ARM_M"],
    "commit": os.environ["COMMIT_M"],
    "config": os.environ["CONFIG_M"],
    "config_sha256": os.environ["CONFIG_SHA_M"],
    "manifest": os.environ["MANIFEST_M"],
    "manifest_sha256": os.environ["MANIFEST_SHA_M"],
    "spec_sha256": os.environ["SPEC_SHA_M"],
    "cpa_sh_sha256": os.environ["CPA_SH_SHA_M"],
    "timelimit_s": int(os.environ["TIMELIMIT_M"]),
    "timeout_grace": int(os.environ["GRACE_M"]),
    "parallel": int(os.environ["PARALLEL_M"]),
    "heap": os.environ["HEAP_M"],
    "spec": os.environ["SPEC_M"],
    "model": os.environ["MODEL_M"],
    "thinking": os.environ["THINKING_M"],
    "reasoning_effort": json.loads(os.environ["EFFORT_M"]),
    "llm_record_dir": os.environ["RECORD_M"],
    "llm_replay_dir": os.environ["REPLAY_M"],
    "llm_replay_fingerprint": os.environ.get("REPLAY_FP_M", ""),
    "llm_api_url": os.environ["APIURL_M"],
    "llm_max_completion_tokens": os.environ["MAXTOK_M"],
    "llm_timeout_sec": os.environ["TIMEOUTSEC_M"],
    "llm_replay_preserve_latency": os.environ["PRESERVE_M"],
    "started_at": os.environ["STARTED_M"],
    "cpu_isolation": "taskset " + os.environ["P_CORES_M"] + " (8 physical P-cores, no SMT sibling, no E-core)",
    "load_check": os.environ["LOAD_M"],
    "load_checks": json.loads(os.environ["LOADS_M"]) + [os.environ["LOAD_M"]],
}
tmp = sys.argv[1] + ".tmp"
with open(tmp, "w") as f:
    json.dump(meta, f, indent=2)
os.replace(tmp, sys.argv[1])
EOF

# 1. Frozen task rows (hash-verified; fails on any mismatch) — generated after the
# resume provenance check so a refused resume cannot clobber an existing tasks.tsv.
python3 "$RECORDS_PY" tasks --manifest "$MANIFEST" --sv-benchmarks "$SV_BENCHMARKS" --out "$OUT/tasks.tsv"

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
    # Records use the 'verdict' key (see core_only_records.py / REQUIRED_FIELDS).
    if python3 -c "import json, sys; d = json.load(open(sys.argv[1])); assert isinstance(d, dict) and 'task' in d and 'verdict' in d" "$OUT/logs/${task_name}.json" 2>/dev/null; then
      echo "skip $task (record exists)"
      return 0
    fi
    echo "discard corrupt record for $task; rerunning"
    rm -f "$OUT/logs/${task_name}.json"
  fi
  # A previous attempt may have left a partial dump (no record was written):
  # clear it so LLM rounds / refinements from both attempts do not mix.
  # Cleanup failures abort this task (missing record -> merge fails closed).
  if [[ "$ARM" == "augmented" ]]; then
    rm -rf "$OUT/dumps/${task_name}" || return 1
  fi
  # Record-mode LLM caches are namespaced per task with the same sanitization as
  # LlmResponseCache (chars outside [A-Za-z0-9._-] become '_'); clear a partial
  # cache. Only for the augmented arm (stock runs never touch LLM state).
  if [[ "$ARM" == "augmented" && -n "${VGUIDE_LLM_RECORD_DIR:-}" ]]; then
    SANITIZED="$(printf '%s' "$task" | tr -c 'A-Za-z0-9._-' '_')"
    rm -rf "$VGUIDE_LLM_RECORD_DIR/$SANITIZED" || return 1
  fi
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
