#!/usr/bin/env bash
# Stock baseline for full_scalar (same config as VGuide, no LLM).
# Usage: nohup ./run_stock_baseline_nohup.sh >> output/vguide/experiments/stock_baseline_run.log 2>&1 &
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
RUN="$REPO/scripts/vguided-cegar/run.sh"
export JAVA="${JAVA:-$HOME/FMPA2/external/jdk-21/jdk-21.0.10+7/bin/java}"
export PATH="${HOME}/.local/ant/bin:$(dirname "$JAVA"):${PATH:-}"
export SV_BENCHMARKS="${SV_BENCHMARKS:-$HOME/sv-benchmarks-vguide/c}"

cd "$REPO"
echo "=== stock baseline start $(date -Iseconds) ==="
echo "out=output/vguide/experiments/full_scalar_stock_interval15"
echo "mode=stock (useVocabularyGuide=false), config=predicateAnalysis-vguide.properties"

"$RUN" cpa --set full_scalar --mode stock --parallel 8 --timelimit 300 \
  --out output/vguide/experiments/full_scalar_stock_interval15

echo "=== stock baseline done $(date -Iseconds) ==="
VG_LOGS=output/vguide/experiments/full_scalar_vguide_interval15/logs
ST_LOGS=output/vguide/experiments/full_scalar_stock_interval15/logs
if [[ -d "$VG_LOGS" && -d "$ST_LOGS" ]]; then
  python3 "$REPO/scripts/vguided-cegar/compare_official_reference.py" \
    --baseline stock \
    --vguide-logs "$VG_LOGS" \
    --baseline-logs "$ST_LOGS" \
    --manifest "$REPO/docs/vguided-cegar/benchmark_sets/full_scalar.list" \
    | tee output/vguide/experiments/full_scalar_vguide_interval15/vs_stock_baseline.txt
fi
