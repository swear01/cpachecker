#!/usr/bin/env bash
# Core-only two-arm runner for the hard-case evaluation (Issue #2).
#
# Usage:
#   export SV_BENCHMARKS=~/sv-benchmarks/c   # required
#   export MODEL_API_KEY=...                 # Meta augmented arm (or use replay)
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
#   --exploratory           record ordinary background load; no timing/PAR-2 claims
#   --cpu-list LIST         allocated physical P-cores (exploratory mode only)
#   --dry-run               print effective launch commands without running CPA
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
P_CORE_RANGE="$P_CORE_LIST"


ARM="" MANIFEST="" OUT="" PARALLEL="8" TIMELIMIT="300" HEAP="6000M" DRY=0
EVIDENCE_TIER="performance"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --arm) ARM="$2"; shift 2 ;;
    --manifest) MANIFEST="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --parallel) PARALLEL="$2"; shift 2 ;;
    --timelimit) TIMELIMIT="${2%s}"; shift 2 ;;
    --heap) HEAP="$2"; shift 2 ;;
    --exploratory) EVIDENCE_TIER="exploratory"; shift ;;
    --cpu-list) P_CORE_LIST="$2"; shift 2 ;;
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
[[ "$PARALLEL" =~ ^[1-9][0-9]*$ ]] || die "--parallel must be a positive integer"
[[ "$P_CORE_LIST" =~ ^(0|2|4|6|8|10|12|14)(,(0|2|4|6|8|10|12|14))*$ ]] \
  || die "--cpu-list must contain physical P-cores 0,2,4,6,8,10,12,14"
IFS=',' read -r -a ALLOCATED_CORES <<<"$P_CORE_LIST"
[[ "$(printf '%s\n' "${ALLOCATED_CORES[@]}" | sort -u | wc -l)" -eq "${#ALLOCATED_CORES[@]}" ]] \
  || die "--cpu-list contains duplicates"
[[ "$PARALLEL" -le "${#ALLOCATED_CORES[@]}" ]] || die "--parallel exceeds allocated CPU count"
[[ "$EVIDENCE_TIER" == "exploratory" || "$P_CORE_LIST" == "$P_CORE_RANGE" ]] \
  || die "--cpu-list requires --exploratory"
P_CORE_RANGE="$P_CORE_LIST"
SV_BENCHMARKS="$(cd "$SV_BENCHMARKS" && pwd)"

# Refuse when any selected P-core has median busy >= 50% across five one-second samples.
# Process snapshots are diagnostics only; cumulative %CPU and last-PSR placement never veto.
check_p_cores_idle() {
  local load_window incomplete busy
  load_window="$(LC_ALL=C mpstat -P "$P_CORE_RANGE" 1 5 2>/dev/null)" \
    || die "mpstat failed during the five-sample P-core load check"
  incomplete="$(printf '%s\n' "$load_window" | awk -F' +' -v order="$P_CORE_LIST" '
    BEGIN { core_count = split(order, cores, ",") }
    $1 != "Average:" && $2 ~ /^[0-9]+$/ { count[$2]++ }
    END { for (i in cores) if (count[cores[i]] != 5) print cores[i] }
  ')"
  [[ -z "$incomplete" ]] \
    || die "incomplete five-sample P-core load check for cores: $incomplete"
  busy="$(printf '%s\n' "$load_window" | awk -F' +' -v order="$P_CORE_LIST" '
    BEGIN { core_count = split(order, cores, ",") }
    $1 != "Average:" && $2 ~ /^[0-9]+$/ {
      cpu = $2
      count[cpu]++
      value[cpu SUBSEP count[cpu]] = 100 - $NF
    }
    END {
      for (k = 1; k <= core_count; k++) {
        cpu = cores[k]
        for (i = 2; i <= count[cpu]; i++) {
          current = value[cpu SUBSEP i]
          j = i - 1
          while (j >= 1 && value[cpu SUBSEP j] > current) {
            value[cpu SUBSEP (j + 1)] = value[cpu SUBSEP j]
            j--
          }
          value[cpu SUBSEP (j + 1)] = current
        }
        if (value[cpu SUBSEP 3] >= 50) print cpu
      }
    }
  ')"
  if [[ -n "$busy" && "$EVIDENCE_TIER" == "performance" ]]; then
    die "P-core contention: median busy >= 50% on cores: $busy"
  fi
  LOAD_CHECK_NOW="$(printf '%s\n' "$load_window" | awk -F' +' -v order="$P_CORE_LIST" '
    BEGIN { core_count = split(order, cores, ",") }
    $1 != "Average:" && $2 ~ /^[0-9]+$/ {
      cpu = $2
      count[cpu]++
      value[cpu SUBSEP count[cpu]] = 100 - $NF
    }
    END {
      printf "samples_busy_pct="
      for (k = 1; k <= core_count; k++) {
        cpu = cores[k]
        if (k > 1) printf "|"
        printf "%s:", cpu
        for (i = 1; i <= count[cpu]; i++) {
          if (i > 1) printf ","
          printf "%.2f", value[cpu SUBSEP i]
        }
      }
      print ""
    }
  ')"
}
LOAD_CHECK_NOW=""
check_p_cores_idle
RESOURCE_SNAPSHOT="$(python3 - <<'EOF'
import json, os, socket
from pathlib import Path

def read_resource(path):
    try:
        return Path(path).read_text()
    except OSError as error:
        return {"unavailable": str(error)}

print(json.dumps({"host": socket.gethostname(), "loadavg": os.getloadavg(),
                  "meminfo": read_resource("/proc/meminfo"),
                  "memory_pressure": read_resource("/proc/pressure/memory")}))
EOF
)"

mkdir -p "$OUT/logs"
LLM_PROVIDER="$(printf '%s' "${VGUIDE_LLM_PROVIDER:-meta}" | tr '[:upper:]' '[:lower:]')"
[[ "$LLM_PROVIDER" == "deepseek" || "$LLM_PROVIDER" == "meta" ]] \
  || die "VGUIDE_LLM_PROVIDER must be deepseek or meta, got: ${VGUIDE_LLM_PROVIDER:-}"
LLM_KEY="${MODEL_API_KEY:-}"
LLM_MODEL="${VGUIDE_LLM_MODEL:-muse-spark-1.2-contributor}"
LLM_API_FORMAT="meta-chat-completions-json-schema-v1"
LLM_MAX_COMPLETION_TOKENS="1024"
if [[ "$LLM_PROVIDER" == "deepseek" ]]; then
  LLM_MODEL="${VGUIDE_LLM_MODEL:-deepseek-v4-pro}"
  LLM_API_FORMAT="deepseek-chat-completions-v1"
  [[ -n "${VGUIDE_LLM_REPLAY_DIR:-}" ]] \
    || die "DeepSeek live requests are disabled; set VGUIDE_LLM_REPLAY_DIR for historical replay"
fi
if [[ "$ARM" == "augmented" ]]; then
  mkdir -p "$OUT/dumps"
  [[ -n "$LLM_KEY" || -n "${VGUIDE_LLM_REPLAY_DIR:-}" ]] \
    || die "augmented arm requires MODEL_API_KEY (or VGUIDE_LLM_REPLAY_DIR)"
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

machine_model_for() {
  case "$1" in
    # CPAchecker parses these enum names case-insensitively, but keep the
    # canonical command spelling used by the existing runners.
    ILP32) printf '%s\n' Linux32 ;;
    LP64) printf '%s\n' Linux64 ;;
    *) die "unsupported or missing data_model '$1' (expected ILP32 or LP64)" ;;
  esac
}

build_command() {
  local data_model="$1" source="$2" machine_model
  machine_model="$(machine_model_for "$data_model")"
  RUN_CMD=(
    taskset -c "$P_CORE_LIST"
    "$CPA_SH" --heap "$HEAP"
    --config "$REPO/$CONFIG"
    --option "analysis.machineModel=$machine_model"
    --option "cpa.predicate.refinement.useVocabularyGuide=$USE_VGUIDE"
    --timelimit "${TIMELIMIT}s"
    --spec "$SPEC"
    --stats
    --no-output-files
  )
  if [[ "$ARM" == "augmented" ]]; then
    RUN_CMD+=(--option "vguide.llmMaxCompletionTokens=$LLM_MAX_COMPLETION_TOKENS")
  fi
  RUN_CMD+=("$SV_BENCHMARKS/$source")
}

if [[ "$DRY" == "1" ]]; then
  echo "arm=$ARM manifest=$MANIFEST out=$OUT config=$CONFIG use_vguide=$USE_VGUIDE evidence_tier=$EVIDENCE_TIER cpus=$P_CORE_LIST"
  python3 "$RECORDS_PY" tasks --manifest "$MANIFEST" --sv-benchmarks "$SV_BENCHMARKS" --no-verify --out "$OUT/tasks.tsv"
  while IFS=$'\t' read -r task source expected model family tsha ssha; do
    machine_model="$(machine_model_for "$model")"
    effective_machine_model="$(printf '%s' "$machine_model" | tr '[:lower:]' '[:upper:]')"
    build_command "$model" "$source"
    printf 'task=%s data_model=%s effective_machine_model=%s: ' "$task" "$model" "$effective_machine_model"
    printf '%q ' "${RUN_CMD[@]}"
    printf '\n'
  done <"$OUT/tasks.tsv"
  exit 0
fi

# 0. Output-dir lock: refuse overlapping invocations on the same --out.
# PID-based with a 10-minute mtime guard: a lock whose holder died is reclaimed
# only when (a) it is old (not a concurrent invocation still writing its pid),
# (b) no analysis workers remain on this machine, and (c) the reclaim is atomic
# (mv to a stale name — the loser retries the lock check).
HOSTNAME_L="$(hostname)"
LOCK_TRIES=0
while ! mkdir "$OUT/.run.lock" 2>/dev/null; do
  LOCK_PID=""
  [[ -f "$OUT/.run.lock/pid" ]] && LOCK_PID="$(cat "$OUT/.run.lock/pid")"
  LOCK_OWNER_HOST="${LOCK_PID%%:*}"
  LOCK_OWNER_PID="${LOCK_PID##*:}"
  [[ "$LOCK_OWNER_PID" == "$LOCK_PID" ]] && LOCK_OWNER_PID=""  # legacy pid-only format
  LOCK_AGE="$(python3 -c "import os,sys,time; print(int(time.time()-os.path.getmtime(sys.argv[1])))" "$OUT/.run.lock" 2>/dev/null || echo 0)"
  if [[ -n "$LOCK_OWNER_PID" && "$LOCK_OWNER_HOST" == "$HOSTNAME_L" ]] && kill -0 "$LOCK_OWNER_PID" 2>/dev/null; then
    die "$OUT/.run.lock held by live PID $LOCK_OWNER_PID on $LOCK_OWNER_HOST"
  fi
  if [[ "$LOCK_AGE" -lt 600 ]]; then
    # Young lock (or the holder released it between our mkdir failure and the age
    # read): retry with backoff; only refuse after several attempts. This also
    # tolerates the mkdir->pid window of a concurrent legitimate start.
    LOCK_TRIES=$((LOCK_TRIES + 1))
    if [[ $LOCK_TRIES -gt 5 ]]; then
      die "$OUT/.run.lock exists (age ${LOCK_AGE}s) with no dead-holder evidence yet; retry shortly or remove it manually"
    fi
    sleep 2
    continue
  fi
  # Workers never carry the out/log path in argv; match the benchmark root as a
  # fixed string (grep -F, not regex). A worker on another host of the NFS fleet
  # is not visible here — host-aware reclaim relies on the age guard alone then.
  # ps failure is treated as "workers present": refuse the reclaim (fail closed).
  if ! ps -eo args >/dev/null 2>&1; then
    die "cannot verify worker processes (ps failed); refusing stale-lock reclaim for $OUT"
  fi
  if ps -eo args | grep -F "$SV_BENCHMARKS" | grep -v grep >/dev/null 2>&1; then
    die "stale lock for $OUT but analysis workers still run on this machine"
  fi
  # atomic reclaim: mv the old lock away, then take the name; the loser of
  # the mv retries the whole check.
  if mv "$OUT/.run.lock" "$OUT/.run.lock.stale.$$" 2>/dev/null && mkdir "$OUT/.run.lock" 2>/dev/null; then
    rm -rf "$OUT/.run.lock.stale.$$"
    echo "reclaimed stale lock (age ${LOCK_AGE}s)"
    break
  else
    rm -rf "$OUT/.run.lock.stale.$$" 2>/dev/null
    sleep 1  # another invocation won the race; re-check
  fi
done
echo "$HOSTNAME_L:$$" >"$OUT/.run.lock/pid"
# Heartbeat: keep the lock mtime fresh so runs longer than the 600s stale
# threshold are never reclaimed by another host of the NFS fleet. The loop
# stops as soon as the harness PID dies, so a SIGKILLed run cannot keep the
# lock fresh forever.
MAINPID=$$
( while :; do sleep 60; kill -0 "$MAINPID" 2>/dev/null || break; touch "$OUT/.run.lock" 2>/dev/null || break; done ) &
LOCK_HEARTBEAT=$!
trap 'kill "$LOCK_HEARTBEAT" 2>/dev/null || true; rm -rf "$OUT/.run.lock" 2>/dev/null || true' EXIT

# 2. Run metadata (computed before tasks.tsv so the resume provenance check can
# validate the invocation without overwriting an existing tasks.tsv).
COMMIT="$(git -C "$REPO" rev-parse HEAD)"
RUNTIME_FILE="$OUT/runtime-current.$$.json"
python3 "$RECORDS_PY" runtime --repo "$REPO" >"$RUNTIME_FILE"
CONFIG_SHA="$(python3 -c "import sys; sys.path.insert(0, '$SCRIPT_DIR'); import core_only_config_diff as d; print(d.config_sha256(__import__('pathlib').Path('$REPO/$CONFIG')))")"
MANIFEST_SHA="$(sha256sum "$MANIFEST" | cut -d' ' -f1)"
SPEC_SHA="$(sha256sum "$SPEC" | cut -d' ' -f1)"
CPA_SH_SHA="$(sha256sum "$CPA_SH" | cut -d' ' -f1)"
LOAD_CHECK="$LOAD_CHECK_NOW"
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Effective thinking settings mirror PredicateProposalClient's normalization
# (aliases: true/on/1 -> enabled; effort default -> high; low/medium/high/max passthrough).
# Portable lowercase (Bash 3.2/macOS compatible).
lc() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }
THINKING_RAW="${VGUIDE_LLM_THINKING:-disabled}"
case "$(lc "$THINKING_RAW")" in
  enabled|true|on|1) THINKING="enabled" ;;
  *) THINKING="disabled" ;;
esac
# Effective reasoning effort mirrors PredicateProposalClient.reasoningEffortFromEnv
# (default -> high; all of low/medium/high/max pass through — the official API
# supports them natively). Meta maps disabled thinking to minimal effort;
# DeepSeek sends no reasoning effort when thinking is disabled.
# EFFORT is a JSON-encoded token (null | "low" | "medium" | "high" | "max").
EFFORT_RAW="${VGUIDE_LLM_REASONING_EFFORT:-}"
if [[ "$LLM_PROVIDER" == "meta" && "$THINKING" == "disabled" ]]; then
  EFFORT="\"minimal\""
elif [[ "$THINKING" == "disabled" ]]; then
  EFFORT="null"
else
  case "$(lc "$EFFORT_RAW")" in
    ""|default) EFFORT="\"high\"" ;;
    low) EFFORT="\"low\"" ;;
    medium) EFFORT="\"medium\"" ;;
    high) EFFORT="\"high\"" ;;
    max|xhigh) EFFORT="\"max\"" ;;
    *) EFFORT="\"high\"" ;;
  esac
fi

REPLAY_FP="$(if [[ -n "${VGUIDE_LLM_REPLAY_DIR:-}" ]]; then find "$VGUIDE_LLM_REPLAY_DIR" -type f -exec sha256sum {} + 2>/dev/null | sort | sha256sum | cut -d' ' -f1; fi)"

# Resume support: an existing run_meta.json must match this invocation's
# provenance exactly (arm, commit, config, manifest, timelimit, grace, heap,
# parallel, model, thinking, response-cache mode); otherwise refuse — a
# mixed-provenance dataset is invalid. Values are passed via the environment
# (single-quoted heredoc: no shell interpolation).
if [[ ! -f "$OUT/run_meta.json" ]] && ls "$OUT"/logs/*.json >/dev/null 2>&1; then
  die "per-task records exist under $OUT/logs but run_meta.json is missing (orphaned records); move them away or restore run_meta.json before resuming"
fi
OLD_LOADS_JSON="[]"
if [[ -f "$OUT/run_meta.json" ]]; then
  if ! OLD_META="$(python3 -c "import json,sys; print(json.dumps(json.load(open(sys.argv[1], encoding='utf-8'))))" "$OUT/run_meta.json" 2>/dev/null)"; then
    die "$OUT/run_meta.json exists but is not valid JSON (corrupt metadata file); fix or remove it manually"
  fi
  OLD_LOADS_JSON="$(printf '%s' "$OLD_META" | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin).get('load_checks', [])))" 2>/dev/null || echo '[]')"
  OLD_STARTED_AT="$(printf '%s' "$OLD_META" | python3 -c "import json,sys; print(json.load(sys.stdin).get('started_at',''))")"
  OLD_LOAD_CHECK="$(printf '%s' "$OLD_META" | python3 -c "import json,sys; print(json.load(sys.stdin).get('load_check',''))")"
  RUNTIME_C="$RUNTIME_FILE" ARM_C="$ARM" COMMIT_C="$COMMIT" CONFIG_SHA_C="$CONFIG_SHA" MANIFEST_SHA_C="$MANIFEST_SHA" SPEC_SHA_C="$SPEC_SHA" CPA_SH_SHA_C="$CPA_SH_SHA" \
  TIMELIMIT_C="$TIMELIMIT" GRACE_C="$TIMEOUT_GRACE" HEAP_C="$HEAP" PARALLEL_C="$PARALLEL" TIER_C="$EVIDENCE_TIER" CPUS_C="$P_CORE_LIST" \
  PROVIDER_C="$LLM_PROVIDER" MODEL_C="$LLM_MODEL" THINKING_C="$THINKING" EFFORT_C="$EFFORT" FORMAT_C="$LLM_API_FORMAT" \
  RECORD_C="${VGUIDE_LLM_RECORD_DIR:-}" REPLAY_C="${VGUIDE_LLM_REPLAY_DIR:-}" \
  REPLAY_FP_C="$REPLAY_FP" \
  APIURL_C="${VGUIDE_LLM_API_URL:-}" MAXTOK_C="$LLM_MAX_COMPLETION_TOKENS" \
  PRESERVE_C="${VGUIDE_LLM_REPLAY_PRESERVE_LATENCY:-}" \
  python3 - "$OUT/run_meta.json" <<'EOF' || die "resume refused: $OUT/run_meta.json provenance differs from this invocation (use a fresh OUT dir)"
import json, os, sys
old = json.load(open(sys.argv[1], encoding="utf-8"))
want = {
    **json.load(open(os.environ["RUNTIME_C"], encoding="utf-8")),
    "arm": os.environ["ARM_C"],
    "commit": os.environ["COMMIT_C"],
    "config_sha256": os.environ["CONFIG_SHA_C"],
    "manifest_sha256": os.environ["MANIFEST_SHA_C"],
    "spec_sha256": os.environ["SPEC_SHA_C"],
    "cpa_sh_sha256": os.environ["CPA_SH_SHA_C"],
    "timelimit_s": float(os.environ["TIMELIMIT_C"]),
    "timeout_grace": int(os.environ["GRACE_C"]),
    "heap": os.environ["HEAP_C"],
    "parallel": int(os.environ["PARALLEL_C"]),
    "evidence_tier": os.environ["TIER_C"],
    "cpu_list": os.environ["CPUS_C"],
    "llm_provider": os.environ["PROVIDER_C"],
    "model": os.environ["MODEL_C"],
    "thinking": os.environ["THINKING_C"],
    "reasoning_effort": json.loads(os.environ["EFFORT_C"]),
    "llm_api_format": os.environ["FORMAT_C"],
    "llm_record_dir": os.environ["RECORD_C"],
    "llm_replay_dir": os.environ["REPLAY_C"],
    "llm_replay_fingerprint": os.environ.get("REPLAY_FP_C", ""),
    "llm_api_url": os.environ["APIURL_C"],
    "llm_max_completion_tokens": os.environ["MAXTOK_C"],
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
  if [[ -n "$OLD_LOAD_CHECK" ]]; then
    LOAD_CHECK="$OLD_LOAD_CHECK"   # keep the first session's load check
    CURRENT_LOAD="$LOAD_CHECK_NOW"
  else
    CURRENT_LOAD="$LOAD_CHECK"
  fi
else
  CURRENT_LOAD="$LOAD_CHECK"
fi

# Atomic, escaping-safe write of run_meta.json (values via env, json.dumps).
SV_BENCHMARKS_M="$SV_BENCHMARKS" RUNTIME_M="$RUNTIME_FILE" ARM_M="$ARM" COMMIT_M="$COMMIT" CONFIG_M="$REPO/$CONFIG" CONFIG_SHA_M="$CONFIG_SHA" \
MANIFEST_M="$MANIFEST" MANIFEST_SHA_M="$MANIFEST_SHA" SPEC_SHA_M="$SPEC_SHA" CPA_SH_SHA_M="$CPA_SH_SHA" \
TIMELIMIT_M="$TIMELIMIT" GRACE_M="$TIMEOUT_GRACE" PARALLEL_M="$PARALLEL" HEAP_M="$HEAP" \
SPEC_M="$SPEC" PROVIDER_M="$LLM_PROVIDER" MODEL_M="$LLM_MODEL" THINKING_M="$THINKING" EFFORT_M="$EFFORT" FORMAT_M="$LLM_API_FORMAT" \
RECORD_M="${VGUIDE_LLM_RECORD_DIR:-}" REPLAY_M="${VGUIDE_LLM_REPLAY_DIR:-}" \
REPLAY_FP_M="$REPLAY_FP" \
  APIURL_M="${VGUIDE_LLM_API_URL:-}" MAXTOK_M="$LLM_MAX_COMPLETION_TOKENS" \
PRESERVE_M="${VGUIDE_LLM_REPLAY_PRESERVE_LATENCY:-}" \
STARTED_M="$STARTED_AT" LOAD_M="$LOAD_CHECK" LOADS_M="$OLD_LOADS_JSON" CURRLOAD_M="$CURRENT_LOAD" P_CORES_M="$P_CORE_LIST" TIER_M="$EVIDENCE_TIER" RESOURCES_M="$RESOURCE_SNAPSHOT" \
python3 - "$OUT/run_meta.json" <<'EOF'
import json, os, sys
meta = {
    **json.load(open(os.environ["RUNTIME_M"], encoding="utf-8")),
    "arm": os.environ["ARM_M"],
    "commit": os.environ["COMMIT_M"],
    "config": os.path.abspath(os.environ["CONFIG_M"]),
    "sv_benchmarks": os.path.abspath(os.environ["SV_BENCHMARKS_M"]),
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
    "llm_provider": os.environ["PROVIDER_M"],
    "model": os.environ["MODEL_M"],
    "thinking": os.environ["THINKING_M"],
    "reasoning_effort": json.loads(os.environ["EFFORT_M"]),
    "llm_api_format": os.environ["FORMAT_M"],
    "llm_record_dir": os.environ["RECORD_M"],
    "llm_replay_dir": os.environ["REPLAY_M"],
    "llm_replay_fingerprint": os.environ.get("REPLAY_FP_M", ""),
    "llm_api_url": os.environ["APIURL_M"],
    "llm_max_completion_tokens": os.environ["MAXTOK_M"],
    "llm_replay_preserve_latency": os.environ["PRESERVE_M"],
    "started_at": os.environ["STARTED_M"],
    "cpu_isolation": "taskset " + os.environ["P_CORES_M"] + " (physical P-cores, no SMT sibling, no E-core)",
    "cpu_list": os.environ["P_CORES_M"],
    "evidence_tier": os.environ["TIER_M"],
    "timing_claims_allowed": os.environ["TIER_M"] == "performance",
    "resource_snapshot": json.loads(os.environ["RESOURCES_M"]),
    "load_check": os.environ["LOAD_M"],
    "load_checks": json.loads(os.environ["LOADS_M"]) + [os.environ["CURRLOAD_M"]],
}
tmp = sys.argv[1] + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(meta, f, indent=2)
os.replace(tmp, sys.argv[1])
EOF

rm -f "$RUNTIME_FILE"

# 1. Frozen task rows (hash-verified; fails on any mismatch) — generated after the
# resume provenance check so a refused resume cannot clobber an existing tasks.tsv.
python3 "$RECORDS_PY" tasks --manifest "$MANIFEST" --sv-benchmarks "$SV_BENCHMARKS" --out "$OUT/tasks.tsv"

# Validate every frozen row before starting workers. A malformed model must
# fail the run, not become a default LINUX32 execution.
while IFS=$'\t' read -r task source expected model family tsha ssha; do
  machine_model_for "$model" >/dev/null
done <"$OUT/tasks.tsv"

# 3. Run each task once (parallel), then emit one record per task.
rm -f "$OUT/records.jsonl"
# Hash-suffixed task name: '/'-replaced names can collide (a/b vs a_b); the
# suffix keeps logs/dumps/records unique while staying readable.
task_name_of() {
  printf '%s' "${1//\//_}~$(printf '%s' "$1" | sha256sum | cut -c1-6)"
}
export -f sha256sum 2>/dev/null || true
export -f task_name_of
run_one() {
  local line="$1"
  local task source expected model family tsha ssha
  IFS=$'\t' read -r task source expected model family tsha ssha <<<"$line"
  # Reject malformed identities before deriving evidence paths.
  [[ -n "$task" ]] || { echo "empty task row; aborting task"; return 1; }
  if [[ "$task" =~ (^|/)\.\.?(/|$) ]]; then
    echo "unsafe task path '$task'; aborting task"
    return 1
  fi
  local task_name="$(task_name_of "$task")"
  local log="$OUT/logs/${task_name}.log"
  build_command "$model" "$source"
  # A completed failure is evidence too. Never overwrite an interrupted attempt.
  if [[ -f "$OUT/logs/${task_name}.json" ]]; then
    python3 -c 'import json,sys; d=json.load(open(sys.argv[1], encoding="utf-8")); assert isinstance(d,dict) and d.get("task")==sys.argv[2] and d.get("execution",{}).get("command")==sys.argv[3:]' "$OUT/logs/${task_name}.json" "$task" "${RUN_CMD[@]}" \
      || { echo "invalid existing record for $task; use fresh OUT" >&2; return 1; }
    echo "skip $task (record exists)"
    return 0
  fi
  if [[ -e "$log" || -e "$OUT/logs/${task_name}.execution.json" || -e "$OUT/dumps/${task_name}" ]]; then
    echo "unfinished evidence exists for $task; preserve it and use fresh OUT" >&2
    return 1
  fi
  build_command "$model" "$source"
  if [[ "$DRY" == "1" ]]; then
    echo "${RUN_CMD[*]}"
    return 0
  fi
  local execution="$OUT/logs/${task_name}.execution.json"
  local capture=(python3 "$RECORDS_PY" capture --log "$log" --status "$execution"
    --wall-limit "$((TIMELIMIT + TIMEOUT_GRACE))" -- "${RUN_CMD[@]}")
  if [[ "$ARM" == "augmented" ]]; then
    VGUIDE_LLM_CACHE_NAMESPACE="$(basename "$OUT")/$task" VGUIDE_ANALYSIS_DUMP_DIR="$OUT/dumps/${task_name}" \
      "${capture[@]}" || return 1
  else
    "${capture[@]}" || return 1
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
    --execution "$execution" \
    --run-meta "$OUT/run_meta.json" \
    --out "$OUT/logs/${task_name}.json"
}
export -f run_one machine_model_for build_command die
export OUT ARM USE_VGUIDE REPO CPA_SH SV_BENCHMARKS RECORDS_PY CONFIG SPEC TIMELIMIT TIMEOUT_GRACE HEAP COMMIT CONFIG_SHA P_CORE_LIST LLM_MAX_COMPLETION_TOKENS

# 4. Run each task (no header row in tasks.tsv), merge per-task records in order,
#    then verify completeness.
# Null-delimited so task names with spaces/special chars are safe
# (-n 1 keeps BSD/macOS xargs happy instead of -I).
tr '\n' '\0' <"$OUT/tasks.tsv" | xargs -0 -n 1 -P "$PARALLEL" bash -c 'run_one "$1"' _

rm -f "$OUT/records.jsonl"
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -n "$line" ]] || continue
  task="$(echo "$line" | cut -f1)"
  rec="$OUT/logs/$(task_name_of "$task").json"
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
