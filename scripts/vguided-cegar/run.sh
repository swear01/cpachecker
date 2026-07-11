#!/usr/bin/env bash
# VGuide experiment runner (single entry point; see docs/vguided-cegar/RUN_EXPERIMENTS.md).
#
# Usage:
#   ./run.sh bench-setup              # default: recommended (ReachSafety + P1)
#   ./run.sh bench-setup --profile=reachsafety
#   ./run.sh bench-setup --profile=p1
#   ./run.sh bench-reclassify         # rediscover + classify (official tree) + regen
#   ./run.sh bench-regen              # regen benchmark_sets/*.list only
#   ./run.sh cpa --set sample         # -> output/vguide/experiments/sample_vguide
#   ./run.sh cpa --set sample --mode stock  # -> .../sample_stock
#   ./run.sh cpa --set full_scalar --mode svcomp27-stock  # -> .../full_scalar_svcomp27_stock
#   ./run.sh cpa --set full_scalar --parallel 16 --timelimit 300
#   ./run.sh cpa --set full_scalar --ablation l3 --parallel 8 --timelimit 300
#   ./run.sh llm-quality [--tasks up,down,array_3-1]
#   ./run.sh verify-pack --task array_3-1   # CPA + artifacts (real ContextPack)
#   ./run.sh nla-oracle validate
#   ./run.sh nla-oracle run --arm both --timelimit 60
#   ./run.sh help
#
# Environment (see RUN_EXPERIMENTS.md):
#   JAVA              — Java 21+ required for CPA
#   DEEPSEEK_API_KEY  — required for vguide / llm-quality / verify-pack
#   DEEPSEEK_MODEL    — optional override (default deepseek-v4-pro)
#   VGUIDE_LLM_RECORD_DIR / VGUIDE_LLM_REPLAY_DIR — mutually exclusive paired-response modes
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
    "$HOME/.local/bin/java" \
    "$HOME/.local/jdk-21/bin/java" \
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
  if [[ -n "${VGUIDE_LLM_RECORD_DIR:-}" && -n "${VGUIDE_LLM_REPLAY_DIR:-}" ]]; then
    die "VGUIDE_LLM_RECORD_DIR and VGUIDE_LLM_REPLAY_DIR are mutually exclusive"
  fi
  [[ -n "${DEEPSEEK_API_KEY:-}" || -n "${VGUIDE_LLM_REPLAY_DIR:-}" ]] \
    || die "DEEPSEEK_API_KEY required unless VGUIDE_LLM_REPLAY_DIR is set"
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
  local set="" mode="vguide" parallel="" timelimit="" heap="" out="" dry="" ablation="" extra=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --set) set="$2"; shift 2 ;;
      --mode) mode="$2"; shift 2 ;;
      --parallel) parallel="$2"; shift 2 ;;
      --timelimit) timelimit="$2"; shift 2 ;;
      --heap) heap="$2"; shift 2 ;;
      --out) out="$2"; shift 2 ;;
      --ablation) ablation="$2"; shift 2 ;;
      --dry-run) dry=1; shift ;;
      --) shift; extra=("$@"); break ;;
      *) extra+=("$1"); shift ;;
    esac
  done
  [[ -n "$set" ]] || die "cpa requires --set <sample|full_scalar|...>"
  require_java
  case "$mode" in
    stock|svcomp26|svcomp27-stock|svcomp26-overflow|termination-stock) ;;
    vguide|usefulness-gate-off|usefulness-gate-on|svcomp26-vguide|svcomp27-vguide|svcomp|svcomp26-overflow-vguide|source-prior-loops|source-prior-overflow|source-prior-svcomp26-loops|source-prior-svcomp26-overflow|termination-vguide) require_api ;;
    *) die "unknown --mode: $mode (see run.sh usage for supported modes)" ;;
  esac
  if [[ -z "$out" ]]; then
    case "$ablation" in
      l3|with-l3|entailment) out="output/vguide/experiments/${set}_vguide_l3" ;;
      no-l3|no_l3|precision-only) out="output/vguide/experiments/${set}_vguide_noL3" ;;
      *)
        if [[ "$mode" == "stock" ]]; then
          out="output/vguide/experiments/${set}_stock"
        elif [[ "$mode" == "usefulness-gate-off" ]]; then
          out="output/vguide/experiments/${set}_usefulness_gate_off"
        elif [[ "$mode" == "usefulness-gate-on" ]]; then
          out="output/vguide/experiments/${set}_usefulness_gate_on"
        elif [[ "$mode" == "svcomp26" ]]; then
          out="output/vguide/experiments/${set}_svcomp26"
        elif [[ "$mode" == "svcomp26-vguide" ]]; then
          out="output/vguide/experiments/${set}_svcomp26_vguide"
        elif [[ "$mode" == "svcomp26-overflow" ]]; then
          out="output/vguide/experiments/${set}_svcomp26_overflow"
        elif [[ "$mode" == "svcomp26-overflow-vguide" ]]; then
          out="output/vguide/experiments/${set}_svcomp26_overflow_vguide"
        elif [[ "$mode" == "svcomp27-stock" ]]; then
          out="output/vguide/experiments/${set}_svcomp27_stock"
        elif [[ "$mode" == "svcomp27-vguide" || "$mode" == "svcomp" ]]; then
          out="output/vguide/experiments/${set}_svcomp27_vguide"
        elif [[ "$mode" == "source-prior-loops" ]]; then
          out="output/vguide/experiments/${set}_source_prior_loops"
        elif [[ "$mode" == "source-prior-overflow" ]]; then
          out="output/vguide/experiments/${set}_source_prior_overflow"
        elif [[ "$mode" == "source-prior-svcomp26-loops" ]]; then
          out="output/vguide/experiments/${set}_source_prior_svcomp26_loops"
        elif [[ "$mode" == "source-prior-svcomp26-overflow" ]]; then
          out="output/vguide/experiments/${set}_source_prior_svcomp26_overflow"
        elif [[ "$mode" == "termination-stock" ]]; then
          out="output/vguide/experiments/${set}_termination_stock"
        elif [[ "$mode" == "termination-vguide" ]]; then
          out="output/vguide/experiments/${set}_termination_vguide"
        else
          out="output/vguide/experiments/${set}_vguide"
        fi
        ;;
    esac
  fi
  local env_extra=()
  [[ -n "$parallel" ]] && env_extra+=(VGUIDE_PARALLEL="$parallel" PARALLEL="$parallel")
  [[ -n "$timelimit" ]] && env_extra+=(TIMELIMIT="$timelimit")
  [[ -n "$heap" ]] && env_extra+=(HEAP="$heap")
  env_extra+=(VGUIDE_OUT_BASE="$out")
  [[ "$dry" == "1" ]] && env_extra+=(VGUIDE_DRY_RUN=1)
  if [[ "$mode" == "stock" ]]; then
    env_extra+=(VGUIDE_USE_VOCABULARY_GUIDE=false)
  elif [[ "$mode" == "usefulness-gate-off" ]]; then
    env_extra+=(VGUIDE_CONFIG=config/vguide-experiment-usefulness-gate-off.properties)
  elif [[ "$mode" == "usefulness-gate-on" ]]; then
    env_extra+=(VGUIDE_CONFIG=config/vguide-experiment-usefulness-gate-on.properties)
  elif [[ "$mode" == "svcomp26" ]]; then
    env_extra+=(
      VGUIDE_USE_VOCABULARY_GUIDE=false
      VGUIDE_CONFIG=config/unmaintained/svcomp26.properties
      VGUIDE_SPEC=
    )
  elif [[ "$mode" == "svcomp26-vguide" ]]; then
    env_extra+=(
      VGUIDE_SVCOMP=1
      VGUIDE_CONFIG=config/unmaintained/svcomp26-vguide.properties
      VGUIDE_SPEC="$REPO/config/specification/sv-comp-reachability.spc"
    )
  elif [[ "$mode" == "svcomp26-overflow" ]]; then
    env_extra+=(
      VGUIDE_SVCOMP=1
      VGUIDE_USE_VOCABULARY_GUIDE=false
      VGUIDE_CONFIG=config/unmaintained/svcomp26--overflow.properties
      VGUIDE_SPEC="$REPO/config/specification/sv-comp-overflow.spc"
    )
  elif [[ "$mode" == "svcomp26-overflow-vguide" ]]; then
    env_extra+=(
      VGUIDE_SVCOMP=1
      VGUIDE_CONFIG=config/unmaintained/svcomp26-overflow-vguide.properties
      VGUIDE_SPEC="$REPO/config/specification/sv-comp-overflow.spc"
    )
  elif [[ "$mode" == "svcomp27-stock" ]]; then
    env_extra+=(
      VGUIDE_SVCOMP=1
      VGUIDE_USE_VOCABULARY_GUIDE=false
      VGUIDE_CONFIG=config/svcomp27.properties
      VGUIDE_SPEC="$REPO/config/specification/sv-comp-reachability.spc"
    )
  elif [[ "$mode" == "svcomp27-vguide" || "$mode" == "svcomp" ]]; then
    env_extra+=(
      VGUIDE_SVCOMP=1
      VGUIDE_CONFIG=config/svcomp27-vguide.properties
      VGUIDE_SPEC="$REPO/config/specification/sv-comp-reachability.spc"
    )
  elif [[ "$mode" == "source-prior-loops" ]]; then
    env_extra+=(
      VGUIDE_CONFIG=config/vguide-experiment-source-prior-loops.properties
      VGUIDE_SPEC="$REPO/config/specification/default.spc"
    )
  elif [[ "$mode" == "source-prior-overflow" ]]; then
    env_extra+=(
      VGUIDE_CONFIG=config/vguide-experiment-source-prior-overflow.properties
      VGUIDE_SPEC="$REPO/config/specification/sv-comp-overflow.spc"
    )
  elif [[ "$mode" == "source-prior-svcomp26-loops" ]]; then
    env_extra+=(
      VGUIDE_SVCOMP=1
      VGUIDE_CONFIG=config/vguide-experiment-source-prior-svcomp26-loops.properties
      VGUIDE_SPEC="$REPO/config/specification/sv-comp-reachability.spc"
    )
  elif [[ "$mode" == "source-prior-svcomp26-overflow" ]]; then
    env_extra+=(
      VGUIDE_SVCOMP=1
      VGUIDE_CONFIG=config/vguide-experiment-source-prior-svcomp26-overflow.properties
      VGUIDE_SPEC="$REPO/config/specification/sv-comp-overflow.spc"
    )
  elif [[ "$mode" == "termination-stock" ]]; then
    # lasso-only termination (isolates the lasso route for clean hook attribution).
    # VGUIDE_SPEC= (empty): config uses internal termination automata; passing default.spc
    # would override it and break termination detection.
    # USE_VOCABULARY_GUIDE=false: the inner safety analysis is predicate-based, so leaving it
    # on would enable the *reachability* VGuide inside termination and confound the ranking hook.
    env_extra+=(
      VGUIDE_CONFIG=config/components/termination-composition-lassoBasedAnalysis.properties
      VGUIDE_SPEC=
      VGUIDE_USE_VOCABULARY_GUIDE=false
    )
  elif [[ "$mode" == "termination-vguide" ]]; then
    # VGUIDE_TERMINATION_RANKING=on activates the LLM ranking-function fallback inside LassoAnalysis
    # (env-gated to avoid termination.config self-reference option-propagation issues).
    env_extra+=(
      VGUIDE_CONFIG=config/vguide-experiment-termination.properties
      VGUIDE_SPEC=
      VGUIDE_USE_VOCABULARY_GUIDE=false
      VGUIDE_TERMINATION_RANKING=on
    )
  fi
  # Termination-* tasks (termination-crafted/-crafted-lit/-numeric) are all LP64; the harness
  # otherwise defaults to ILP32 and wrong int widths can flip termination verdicts (0-wrong risk).
  if [[ "$mode" == termination-* ]]; then
    extra+=(--option analysis.machineModel=Linux64)
  fi
  case "$ablation" in
    ""|"no-l3"|"no_l3"|"precision-only")
      [[ -n "$ablation" ]] && extra+=(--option vguide.enableL3Entailment=false)
      ;;
    l3|with-l3|entailment)
      extra+=(--option vguide.enableL3Entailment=true)
      ;;
    *)
      die "unknown --ablation: $ablation (supported: l3, no-l3)"
      ;;
  esac
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
    --option vguide.llmCallSchedule=first_spurious \
    --option vguide.maxLlmRoundsPerAnalysis=1 \
    --timelimit "${timelimit}s" \
    --spec "$REPO/config/specification/default.spc" \
    --stats \
    --no-output-files \
    "$rel" 2>&1 | tee "$out/cpa.log"
  if grep -q "VGuide LLM round" "$out/cpa.log" 2>/dev/null; then
    echo "--- VGuide LLM (from cpa.log) ---"
    grep -E "VGuide LLM round|VGuide predicate" "$out/cpa.log" | head -15
  else
    echo "WARN: no VGuide LLM lines in $out/cpa.log (NO_SPURIOUS or timeout?)"
  fi
}

cmd_nla_oracle() {
  require_java
  exec python3 "$SCRIPT_DIR/oracle_capacity_harness.py" \
    --benchmark-root "$SV_BENCHMARKS" "$@"
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
    nla-oracle) cmd_nla_oracle "$@" ;;
    *) die "unknown command: $cmd (try: ./run.sh help)" ;;
  esac
}

main "$@"
