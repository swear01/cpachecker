#!/usr/bin/env bash
# Run full VGuide experiment suite (sample + full_scalar vguide/stock).
# Usage: nohup ./run_full_experiments_nohup.sh >> output/vguide/experiments/full_run.log 2>&1 &
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
RUN="$REPO/scripts/vguided-cegar/run.sh"
export JAVA="${JAVA:-$HOME/jdk-21/bin/java}"
[[ -x "$JAVA" ]] || export JAVA="$HOME/FMPA2/external/jdk-21/jdk-21.0.10+7/bin/java"
export PATH="${HOME}/.local/ant/bin:$(dirname "$JAVA"):${PATH:-}"
export SV_BENCHMARKS="${SV_BENCHMARKS:-$HOME/sv-benchmarks/c}"
export DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:?DEEPSEEK_API_KEY required for VGuide batches}"

cd "$REPO"
echo "=== full experiments start $(date -Iseconds) ==="
echo "Config: vguide.properties default (llmMinIntervalSec=15, llmEveryN=72, maxLlmRounds=5)"
echo "CSV: appended per task (tail -f OUT/*_summary.csv)"
grep -E 'llmMinIntervalSec|llmEveryN|maxLlmRounds' "$REPO/config/vguide.properties" || true
# sample smoke (default out: sample_vguide / sample_stock)
"$RUN" cpa --set sample --parallel 8 --timelimit 300
"$RUN" cpa --set sample --mode stock --parallel 8 --timelimit 300

"$RUN" cpa --set full_scalar --parallel 8 --timelimit 300 \
  --out output/vguide/experiments/full_scalar_vguide

# Same config/properties; only useVocabularyGuide=false (no LLM).
"$RUN" cpa --set full_scalar --mode stock --parallel 8 --timelimit 300 \
  --out output/vguide/experiments/full_scalar_stock

echo "=== full experiments done $(date -Iseconds) ==="
VG_LOGS=output/vguide/experiments/full_scalar_vguide/logs
ST_LOGS=output/vguide/experiments/full_scalar_stock/logs
if [[ -d "$VG_LOGS" && -d "$ST_LOGS" ]]; then
  "$REPO/scripts/vguided-cegar/post_batch_analysis.sh" \
    --vguide-out output/vguide/experiments/full_scalar_vguide \
    --stock-out output/vguide/experiments/full_scalar_stock \
    --set full_scalar \
    --timelimit 300 || true
fi
