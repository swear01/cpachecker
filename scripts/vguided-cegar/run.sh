#!/usr/bin/env bash
# VGuide experiment runner (single entry point; see docs/vguided-cegar/RUN_EXPERIMENTS.md).
#
# Usage:
#   ./run.sh bench-setup              # default: recommended (ReachSafety + P1)
#   ./run.sh bench-setup --profile=reachsafety
#   ./run.sh bench-setup --profile=p1
#   ./run.sh bench-reclassify         # rediscover + classify (official tree) + regen
#   ./run.sh bench-regen              # regen benchmark_sets/*.list only
#   ./run.sh cpa --set sample         # Unified VGuide batch (default mode)
#   ./run.sh cpa --set sample --mode stock
#   ./run.sh cpa --set full_scalar --parallel 16 --timelimit 300
#   ./run.sh llm-quality [--tasks up,down,array_3-1]
#   ./run.sh verify-pack --task array_3-1   # CPA + artifacts (real ContextPack)
#   ./run.sh help
#
# Environment (see RUN_EXPERIMENTS.md):
#   JAVA              — Java 21+ required for CPA
#   DEEPSEEK_API_KEY  — required for vguide / llm-quality / verify-pack
#   SV_BENCHMARKS     — default $HOME/sv-benchmarks/c

set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export SV_BENCHMARKS="${SV_BENCHMARKS:-$HOME/sv-benchmarks/c}"
export PATH="${HOME}/.local/ant/bin:${PATH:-}"

die() { echo "ERROR: $*" >&2; exit 1; }

require_java() {
  if [[ -n "${JAVA:-}" && -x "$JAVA" ]]; then
    export PATH="$(dirname "$JAVA"):$PATH"
    return
  fi
  for cand in \
    "$HOME/jdk-21/bin/java" \
    "$HOME/.jdks/temurin-21*/bin/java" \
    /usr/lib/jvm/java-21-openjdk-amd64/bin/java \
    /usr/lib/jvm/java-21-amazon-corretto/bin/java; do
    # shellcheck disable=SC2086
    if [[ -x $cand ]]; then
      JAVA=$cand
      export JAVA PATH="$(dirname "$JAVA"):$PATH"
      return
    fi
  done
  die "JAVA not set. Install JDK 21+ to ~/jdk-21 or export JAVA=/path/to/java-21/bin/java"
}

require_api() {
  [[ -n "${DEEPSEEK_API_KEY:-}" ]] || die "DEEPSEEK_API_KEY required"
}

cmd_help() {
  sed -n '3,20p' "$0" | sed 's/^# \{0,1\}//'
  echo ""
  echo "Docs: $REPO/docs/vguided-cegar/RUN_EXPERIMENTS.md"
}

cmd_bench_setup() {
  exec "$SCRIPT_DIR/setup_benchmarks.sh" "$@"
}

cmd_bench_reclassify() {
  exec "$SCRIPT_DIR/setup_benchmarks.sh" --reclassify
}

cmd_bench_regen() {
  export SV_BENCHMARKS
  exec python3 "$SCRIPT_DIR/regenerate_benchmark_lists.py"
}

cmd_cpa() {
  local set="" mode="vguide" parallel="" timelimit="" heap="" out="" dry="" extra=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --set) set="$2"; shift 2 ;;
      --mode) mode="$2"; shift 2 ;;
      --parallel) parallel="$2"; shift 2 ;;
      --timelimit) timelimit="$2"; shift 2 ;;
      --heap) heap="$2"; shift 2 ;;
      --out) out="$2"; shift 2 ;;
      --dry-run) dry=1; shift ;;
      --) shift; extra=("$@"); break ;;
      *) extra+=("$1"); shift ;;
    esac
  done
  [[ -n "$set" ]] || die "cpa requires --set <sample|full_scalar|...>"
  require_java
  [[ "$mode" == "stock" ]] || require_api
  local env_extra=()
  [[ -n "$parallel" ]] && env_extra+=(VGUIDE_PARALLEL="$parallel" PARALLEL="$parallel")
  [[ -n "$timelimit" ]] && env_extra+=(TIMELIMIT="$timelimit")
  [[ -n "$heap" ]] && env_extra+=(HEAP="$heap")
  [[ -n "$out" ]] && env_extra+=(VGUIDE_OUT_BASE="$out")
  [[ "$dry" == "1" ]] && env_extra+=(VGUIDE_DRY_RUN=1)
  if [[ "$mode" == "stock" ]]; then
    env_extra+=(VGUIDE_USE_VOCABULARY_GUIDE=false)
  fi
  env "${env_extra[@]}" SV_BENCHMARKS="$SV_BENCHMARKS" \
    "$SCRIPT_DIR/run_benchmark_set.sh" "$set" "${extra[@]}"
}

cmd_llm_quality() {
  local tasks="" runs="" parallel=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --tasks) tasks="$2"; shift 2 ;;
      --runs) runs="$2"; shift 2 ;;
      --parallel) parallel="$2"; shift 2 ;;
      *) die "unknown llm-quality arg: $1" ;;
    esac
  done
  require_api
  local env_extra=()
  [[ -n "$tasks" ]] && env_extra+=(VGUIDE_LLM_QUALITY_TASKS="$tasks")
  [[ -n "$runs" ]] && env_extra+=(VGUIDE_LLM_QUALITY_RUNS="$runs")
  [[ -n "$parallel" ]] && env_extra+=(VGUIDE_LLM_QUALITY_PARALLEL="$parallel" PARALLEL="$parallel")
  env "${env_extra[@]}" VGUIDE_BENCH_ROOT="$SV_BENCHMARKS" \
    python3 "$SCRIPT_DIR/test_llm_proposal_quality.py"
}

cmd_verify_pack() {
  local task="array_3-1" timelimit=120
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --task) task="$2"; shift 2 ;;
      --timelimit) timelimit="$2"; shift 2 ;;
      *) die "unknown verify-pack arg: $1" ;;
    esac
  done
  require_java
  require_api
  local rel
  rel="$(find "$SV_BENCHMARKS" -name "${task}.i" -type f 2>/dev/null | head -1)"
  [[ -n "$rel" ]] || rel="$(find "$SV_BENCHMARKS" -name "${task}.c" -type f 2>/dev/null | head -1)"
  [[ -n "$rel" && -f "$rel" ]] || die "task not found: $task under $SV_BENCHMARKS"
  local out="$REPO/output/vguide/verify_pack_${task}"
  mkdir -p "$out"
  echo "ContextPack verify: $rel -> $out"
  require_java
  export JAVA
  "$REPO/scripts/cpa.sh" \
    --heap 2000M \
    --config config/predicateAnalysis-vguide.properties \
    --option cpa.predicate.refinement.useVocabularyGuide=true \
    --option vguide.writeArtifacts=true \
    --option vguide.llmCallSchedule=first_spurious \
    --option vguide.maxLlmRoundsPerAnalysis=1 \
    --timelimit "${timelimit}s" \
    --spec "$REPO/config/specification/default.spc" \
    --stats \
    --no-output-files \
    "$rel" 2>&1 | tee "$out/cpa.log"
  local round
  round="$(find "$REPO/output/vguide" -maxdepth 1 -type d -name 'round_*' 2>/dev/null | sort | tail -1)"
  if [[ -n "$round" ]]; then
    echo "Artifacts: $round"
    ls -la "$round" 2>/dev/null || true
    for f in prompt.txt response.txt; do
      [[ -f "$round/$f" ]] && echo "--- $f (head) ---" && head -20 "$round/$f"
    done
  else
    echo "WARN: no output/vguide/round_* — check $out/cpa.log"
  fi
}

main() {
  local cmd="${1:-help}"
  shift || true
  case "$cmd" in
    help|-h|--help) cmd_help ;;
    bench-setup) cmd_bench_setup "$@" ;;
    bench-reclassify) cmd_bench_reclassify ;;
    bench-regen) cmd_bench_regen ;;
    cpa) cmd_cpa "$@" ;;
    llm-quality) cmd_llm_quality "$@" ;;
    verify-pack) cmd_verify_pack "$@" ;;
    *) die "unknown command: $cmd (try: ./run.sh help)" ;;
  esac
}

main "$@"
