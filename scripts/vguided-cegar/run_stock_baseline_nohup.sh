#!/usr/bin/env bash
# Stock baseline for full_scalar (same config as VGuide, no LLM).
# Usage: nohup ./run_stock_baseline_nohup.sh >> output/vguide/experiments/stock_baseline_run.log 2>&1 &
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
RUN="$REPO/scripts/vguided-cegar/run.sh"
export JAVA="${JAVA:-$HOME/.local/bin/java}"
export PATH="${HOME}/.local/ant/bin:$(dirname "$JAVA"):${PATH:-}"
export SV_BENCHMARKS="${SV_BENCHMARKS:-$HOME/sv-benchmarks/c}"

cd "$REPO"
echo "=== stock baseline start $(date -Iseconds) ==="
echo "out=output/vguide/experiments/full_scalar_stock"
echo "mode=stock (useVocabularyGuide=false), config=predicateAnalysis-vguide.properties"

"$RUN" cpa --set full_scalar --mode stock --parallel 8 --timelimit 300 \
  --out output/vguide/experiments/full_scalar_stock

echo "=== stock baseline done $(date -Iseconds) ==="
VG_LOGS=output/vguide/experiments/full_scalar_vguide/logs
ST_LOGS=output/vguide/experiments/full_scalar_stock/logs
if [[ -d "$VG_LOGS" && -d "$ST_LOGS" ]]; then
  "$REPO/scripts/vguided-cegar/post_batch_analysis.sh" \
    --vguide-out output/vguide/experiments/full_scalar_vguide \
    --stock-out output/vguide/experiments/full_scalar_stock \
    --set full_scalar \
    --timelimit 300
fi
