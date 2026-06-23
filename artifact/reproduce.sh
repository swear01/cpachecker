#!/usr/bin/env bash
# Reproduction entry point for the VGuide artifact.
# Runs natively or inside the Docker image (see Dockerfile). Tiers:
#   (no arg) : offline + build-dependent reproduction that needs NO API key
#   full     : additionally re-run the live VGuide LLM arm (needs DEEPSEEK_API_KEY)
#
# Environment: SV_BENCHMARKS must point at sv-benchmarks/c (the Docker image sets it).
set -euo pipefail

# Locate the CPAchecker tree (this script lives in <tree>/artifact/).
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CPA="$(cd "$HERE/.." && pwd)"
cd "$CPA"
: "${SV_BENCHMARKS:=$HOME/sv-benchmarks/c}"
export SV_BENCHMARKS
ANT="${ANT:-ant}"

hr() { printf '\n==================== %s ====================\n' "$1"; }

hr "0. Offline checks (recorded outputs; no build, no API key)"
python3 "$HERE/reproduce_termination.py"
python3 "$HERE/reproduce_reachsafety.py"

hr "1. Build CPAchecker + VGuide (offline; lib/ is bundled)"
if [ ! -f classes/org/sosy_lab/cpachecker/cmdline/CPAMain.class ]; then
  "$ANT" build-project
else
  echo "classes/ already present (prebuilt); skipping ant build-project"
fi

hr "2. Unit tests for the soundness core (verifier + parser; no API key)"
CP="classes"
for d in lib lib/java/runtime lib/java/test; do
  for j in "$d"/*.jar; do CP="$CP:$j"; done
done
java -cp "$CP" -Djava.awt.headless=true org.junit.runner.JUnitCore \
  org.sosy_lab.cpachecker.core.algorithm.termination.lasso_analysis.vguide.RankingFunctionVerifierTest \
  org.sosy_lab.cpachecker.core.algorithm.termination.lasso_analysis.vguide.RankingTermParserTest

hr "3. Live stock-baseline smoke (real CPAchecker run; deterministic; no API key)"
./scripts/vguided-cegar/run.sh cpa --set termination_smoke_2 --mode termination-stock \
  --timelimit 30 --parallel 2 || true

if [ "${1:-}" = "full" ]; then
  hr "4. Live VGuide LLM arm (needs DEEPSEEK_API_KEY; NON-deterministic)"
  : "${DEEPSEEK_API_KEY:?set DEEPSEEK_API_KEY to run the live VGuide arm}"
  ./scripts/vguided-cegar/run.sh cpa --set termination_scalar --mode termination-vguide \
    --timelimit 300 --parallel 6 || true
  echo "Compare the produced summary CSV against the recorded run in artifact/data/."
fi

hr "DONE"
echo "Table 3 and Table 2 summaries verified offline in step 0;"
echo "tool built and unit-tested in steps 1-2; real verification runs in step 3 (and step 4 with an API key)."
