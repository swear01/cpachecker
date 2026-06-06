#!/usr/bin/env bash
# Re-discover + classify all loop programs under SV_BENCHMARKS (official tree).
# Updates results/vguided-cegar/classifier/*.csv and regenerates benchmark_sets/*.list
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export SV_BENCHMARKS="${SV_BENCHMARKS:-$HOME/sv-benchmarks/c}"

CAND="$REPO/results/vguided-cegar/classifier/sv_benchmarks_candidates.csv"
CLASSIFIED="$REPO/results/vguided-cegar/classifier/scalar_classified.csv"
LEGACY="$REPO/results/vguided-cegar/classifier/scalar_classified_fmpa2_legacy.csv"

echo "SV_BENCHMARKS=$SV_BENCHMARKS"
if [[ -f "$CLASSIFIED" && ! -f "$LEGACY" ]]; then
  cp -a "$CLASSIFIED" "$LEGACY"
  echo "Backed up previous classifier -> $LEGACY"
fi
python3 "$SCRIPT_DIR/discover_loop_programs.py"
python3 "$SCRIPT_DIR/classify_bootstrap_targets.py" --csv "$CAND" --output "$CLASSIFIED"
python3 "$SCRIPT_DIR/regenerate_benchmark_lists.py"
echo "Done. See docs/vguided-cegar/benchmark_sets/regen_report.txt"
