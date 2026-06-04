#!/usr/bin/env bash
# Install SV-COMP benchmarks under ~/sv-benchmarks-vguide (sosy-lab/sv-benchmarks).
#
# Usage:
#   ./setup_benchmarks.sh                      # default: loops-full (ReachSafety-Loops 完整)
#   ./setup_benchmarks.sh --profile reachsafety   # 全部 ReachSafety-* 子類 (~80 目錄)
#   ./setup_benchmarks.sh --profile loops-full    # loop 相關（Loops.set / ReachSafety-Loops）
#   ./setup_benchmarks.sh --full               # entire repo (very large)
#   ./setup_benchmarks.sh --regen              # only regenerate manifest lists
#   ./setup_benchmarks.sh --reclassify         # expand tree + rediscover + classify + regen
#
# After setup:
#   export SV_BENCHMARKS="$HOME/sv-benchmarks-vguide/c"
#   ./run.sh bench-regen
#   ./run.sh bench-reclassify

set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
ROOT="${SV_BENCHMARKS_ROOT:-$HOME/sv-benchmarks-vguide}"
REMOTE="${SV_BENCHMARKS_REMOTE:-https://github.com/sosy-lab/sv-benchmarks.git}"
PROFILE="${SV_BENCHMARKS_PROFILE:-loops-full}"
REGEN=0
FULL=0
RECLASSIFY=0
WANT_RECLASSIFY=0
LIST_PY="$REPO/scripts/vguided-cegar/list_svcomp_sparse_paths.py"

for arg in "$@"; do
  case "$arg" in
    --full) FULL=1 ;;
    --regen) REGEN=1 ;;
    --reclassify) RECLASSIFY=1; WANT_RECLASSIFY=1 ;;
    --profile)
      echo "ERROR: use --profile=reachsafety or --profile=loops-full" >&2
      exit 1
      ;;
    --profile=*) PROFILE="${arg#--profile=}" ;;
    -h|--help)
      sed -n '3,22p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
  esac
done

expand_sparse_profile() {
  if [[ ! -f "$LIST_PY" ]]; then
    die "missing $LIST_PY"
  fi
  local paths_file
  paths_file="$(mktemp)"
  python3 "$LIST_PY" --profile "$PROFILE" --repo "$ROOT" >"$paths_file"
  local n
  n="$(grep -c '^c/' "$paths_file" || true)"
  echo "Sparse checkout profile=$PROFILE ($n paths)"
  # shellcheck disable=SC2046
  git sparse-checkout set $(cat "$paths_file")
  rm -f "$paths_file"
}

die() { echo "ERROR: $*" >&2; exit 1; }

# Legacy: old script only checked out c/loop* by name
expand_loop_legacy() {
  local dirs
  dirs="$(git ls-tree -d HEAD c/ | awk '{print $4}' | grep -iE '^c/(loop|loops)' | tr '\n' ' ')"
  echo "Sparse checkout (legacy loop*): $dirs c/bitvector-loops"
  # shellcheck disable=SC2086
  git sparse-checkout set $dirs c/bitvector-loops c/properties c/ReachSafety-Loops.set c/Loops.set
}

if [[ "$RECLASSIFY" == "1" && -d "$ROOT/.git" ]]; then
  (cd "$ROOT" && expand_sparse_profile)
  export SV_BENCHMARKS="$ROOT/c"
  exec "$REPO/scripts/vguided-cegar/reclassify_benchmarks.sh"
fi

if [[ "$REGEN" == "1" ]]; then
  export SV_BENCHMARKS="$ROOT/c"
  exec python3 "$REPO/scripts/vguided-cegar/regenerate_benchmark_lists.py"
fi

if [[ -d "$ROOT/.git" ]]; then
  echo "Benchmark repo exists: $ROOT — refreshing sparse checkout (profile=$PROFILE)"
  (cd "$ROOT" && git pull --ff-only 2>/dev/null || true)
  if [[ "$PROFILE" == "legacy-loop-star" ]]; then
    (cd "$ROOT" && expand_loop_legacy)
  else
    (cd "$ROOT" && expand_sparse_profile)
  fi
else
  echo "Cloning $REMOTE -> $ROOT (profile=$PROFILE)"
  if [[ "$FULL" == "1" ]]; then
    git clone --depth 1 "$REMOTE" "$ROOT"
  else
    git clone --depth 1 --filter=blob:none --sparse "$REMOTE" "$ROOT"
    (cd "$ROOT" && {
      if [[ "$PROFILE" == "legacy-loop-star" ]]; then
        expand_loop_legacy
      else
        expand_sparse_profile
      fi
    })
  fi
fi

export SV_BENCHMARKS="$ROOT/c"
if [[ ! -d "$SV_BENCHMARKS" ]]; then
  die "expected $SV_BENCHMARKS"
fi

ni=$(find "$SV_BENCHMARKS" -name '*.i' 2>/dev/null | wc -l)
nc=$(find "$SV_BENCHMARKS" -name '*.c' 2>/dev/null | wc -l)
nd=$(find "$SV_BENCHMARKS" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)
du_h=$(du -sh "$ROOT" 2>/dev/null | awk '{print $1}')
echo ""
echo "Bench root:  $SV_BENCHMARKS"
echo "Install dir: $ROOT  (size $du_h)"
echo "Profile:     $PROFILE"
echo "Counts:      $nd top-level dirs under c/, $ni .i, $nc .c"
echo ""
echo "SV-COMP categories (reference):"
echo "  loops-full   = ReachSafety-Loops.set + bitvector-loops"
echo "  reachsafety  = all ReachSafety-*.set task trees"
echo ""
python3 "$LIST_PY" --profile "$PROFILE" --repo "$ROOT" --print-dirs-only 2>/dev/null | tail -5
echo ""
python3 "$REPO/scripts/vguided-cegar/regenerate_benchmark_lists.py" 2>/dev/null || true
echo ""
echo "For classifier-aligned lists: ./scripts/vguided-cegar/run.sh bench-reclassify"
echo "Export: export SV_BENCHMARKS=$SV_BENCHMARKS"

if [[ "$WANT_RECLASSIFY" == "1" ]]; then
  export SV_BENCHMARKS="$ROOT/c"
  exec "$REPO/scripts/vguided-cegar/reclassify_benchmarks.sh"
fi
