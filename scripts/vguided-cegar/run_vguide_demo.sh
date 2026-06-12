#!/usr/bin/env bash
# Unified VGuide demo: first-spurious LLM, no startup V_0. Requires DEEPSEEK_API_KEY.
set -euo pipefail
SCRIPT="$(readlink -f "$0")"
ROOT="$(readlink -f "$(dirname "$SCRIPT")/../..")"
export JAVA="${JAVA:-$HOME/.local/bin/java}"
FILE="${1:-doc/examples/example.c}"
exec "$ROOT/scripts/cpa.sh" \
  --heap 2000M \
  --config "$ROOT/config/predicateAnalysis-vguide.properties" \
  --option cpa.predicate.refinement.useVocabularyGuide=true \
  --no-output-files \
  "$FILE"
