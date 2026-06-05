#!/usr/bin/env bash
# After VGuide + stock batches: verdict compare, PAR-2, cactus plot.
#
# Usage:
#   ./post_batch_analysis.sh \
#     --vguide-out output/vguide/experiments/full_scalar_vguide_interval15 \
#     --stock-out  output/vguide/experiments/full_scalar_stock_interval15 \
#     --set full_scalar \
#     --timelimit 300
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
VG_OUT="" ST_OUT="" SET="full_scalar" TIMELIMIT="300"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --vguide-out) VG_OUT="$2"; shift 2 ;;
    --stock-out) ST_OUT="$2"; shift 2 ;;
    --set) SET="$2"; shift 2 ;;
    --timelimit) TIMELIMIT="$2"; shift 2 ;;
    -h|--help)
      sed -n '3,12p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

[[ -n "$VG_OUT" && -n "$ST_OUT" ]] || {
  echo "Requires --vguide-out and --stock-out" >&2
  exit 1
}

MANIFEST="$REPO/docs/vguided-cegar/benchmark_sets/${SET}.list"
VG_LOGS="$VG_OUT/logs"
ST_LOGS="$ST_OUT/logs"

[[ -d "$VG_LOGS" && -d "$ST_LOGS" ]] || {
  echo "Missing logs: $VG_LOGS or $ST_LOGS" >&2
  exit 1
}

echo "=== post_batch_analysis $(date -Iseconds) ==="
echo "set=$SET timelimit=${TIMELIMIT}s"

python3 "$REPO/scripts/vguided-cegar/compare_official_reference.py" \
  --baseline stock \
  --vguide-logs "$VG_LOGS" \
  --baseline-logs "$ST_LOGS" \
  --manifest "$MANIFEST" \
  | tee "$VG_OUT/vs_stock_baseline.txt"

python3 "$REPO/scripts/vguided-cegar/analyze_benchmark_comparison.py" \
  --vguide-logs "$VG_LOGS" \
  --baseline-logs "$ST_LOGS" \
  --manifest "$MANIFEST" \
  --timelimit "$TIMELIMIT" \
  --out "$VG_OUT"

echo "=== done: $VG_OUT/vs_stock_baseline.txt $VG_OUT/analysis_vs_stock.txt $VG_OUT/cactus_vs_stock.png ==="
