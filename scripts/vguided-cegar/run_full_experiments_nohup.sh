#!/usr/bin/env bash
# Run full VGuide experiment suite (sample stock + full_scalar + full_array_scalar).
# Usage: nohup ./run_full_experiments_nohup.sh >> output/vguide/experiments/full_run.log 2>&1 &
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
RUN="$REPO/scripts/vguided-cegar/run.sh"
export JAVA="${JAVA:-$HOME/jdk-21/bin/java}"
[[ -x "$JAVA" ]] || export JAVA="$HOME/FMPA2/external/jdk-21/jdk-21.0.10+7/bin/java"
export PATH="${HOME}/.local/ant/bin:$(dirname "$JAVA"):${PATH:-}"
export SV_BENCHMARKS="${SV_BENCHMARKS:-$HOME/sv-benchmarks-vguide/c}"
export DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:?DEEPSEEK_API_KEY required for VGuide batches}"

cd "$REPO"
echo "=== full experiments start $(date -Iseconds) ==="
echo "Config: tier_s_15s (vguide.llmMinIntervalSec=15, llmEveryN=72, maxLlmRounds=5)"
echo "CSV: appended per task (tail -f OUT/*_summary.csv)"
grep -E 'llmMinIntervalSec|llmEveryN|maxLlmRounds' "$REPO/config/vguide.properties" || true
# sample (vguide + stock) is usually run interactively first; uncomment if needed:
# "$RUN" cpa --set sample --parallel 8 --out output/vguide/experiments/sample_vguide
# "$RUN" cpa --set sample --mode stock --parallel 8 --out output/vguide/experiments/sample_stock

"$RUN" cpa --set full_scalar --parallel 8 --timelimit 300 \
  --out output/vguide/experiments/full_scalar_vguide_interval15

# Same config/properties; only useVocabularyGuide=false (no LLM).
"$RUN" cpa --set full_scalar --mode stock --parallel 8 --timelimit 300 \
  --out output/vguide/experiments/full_scalar_stock_interval15

"$RUN" cpa --set full_array_scalar --parallel 8 --timelimit 300 \
  --out output/vguide/experiments/full_array_scalar_vguide

echo "=== full experiments done $(date -Iseconds) ==="
VG_LOGS=output/vguide/experiments/full_scalar_vguide_interval15/logs
ST_LOGS=output/vguide/experiments/full_scalar_stock_interval15/logs
if [[ -d "$VG_LOGS" && -d "$ST_LOGS" ]]; then
  python3 "$REPO/scripts/vguided-cegar/compare_official_reference.py" \
    --baseline stock \
    --vguide-logs "$VG_LOGS" \
    --baseline-logs "$ST_LOGS" \
    --manifest "$REPO/docs/vguided-cegar/benchmark_sets/full_scalar.list" \
    | tee output/vguide/experiments/full_scalar_vguide_interval15/vs_stock_baseline.txt || true
fi
