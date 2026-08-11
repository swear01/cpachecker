#!/usr/bin/env bash
# Background driver for the core-only evaluation (Issue #2 / #39).
#
# Sequence (CORE_ONLY_EVALUATION_PLAN §4-§5):
#   1. §4 development smoke: 12 tasks, both arms; gate: 0 wrong, complete records.
#   2. §5 held-out: Stock-Core 224 once, then Augmented-Core 224 once.
#
# Harvest:
#   <out>/smoke_{stock,augmented}/records.jsonl + run_meta.json + logs/
#   <out>/{stock,augmented}_core/records.jsonl + run_meta.json + logs/ + dumps/
# After each stage the check script gates the next one; all stages are
# logged to <out>/driver.log.

set -euo pipefail

REPO="/home/swear01/cpachecker"
RUNNER="$REPO/scripts/vguided-cegar/run_core_only.sh"
CHECK="$REPO/scripts/vguided-cegar/check_core_only_smoke.py"
MANIFEST="${CORE_MANIFEST:-/tmp/dataset-v2-final/hard-case-dataset-v2-final-20260809.pnUVmB/cap16-run/candidate-manifest.json}"
SMOKE_MANIFEST="${CORE_SMOKE_MANIFEST:-/tmp/smoke-manifest.json}"
SV_BENCHMARKS="${SV_BENCHMARKS:-/var/tmp/swear01-cpachecker-paper/sv-benchmarks/c}"
OUT="${CORE_OUT:-$REPO/output/vguide/core_only}"
PARALLEL="${CORE_PARALLEL:-8}"
TIMELIMIT="${CORE_TIMELIMIT:-300}"
export SV_BENCHMARKS DEEPSEEK_API_KEY

mkdir -p "$OUT"
log() { echo "[$(date -Iseconds)] $*" | tee -a "$OUT/driver.log"; }

log "driver start: manifest=$MANIFEST smoke=$SMOKE_MANIFEST sv=$SV_BENCHMARKS parallel=$PARALLEL tl=$TIMELIMIT"

# 1. Smoke (both arms)
log "smoke stock start"
"$RUNNER" --arm stock --manifest "$SMOKE_MANIFEST" --out "$OUT/smoke_stock" --parallel "$PARALLEL" --timelimit "$TIMELIMIT"
log "smoke stock done"
log "smoke augmented start"
"$RUNNER" --arm augmented --manifest "$SMOKE_MANIFEST" --out "$OUT/smoke_augmented" --parallel "$PARALLEL" --timelimit "$TIMELIMIT"
log "smoke augmented done"

# 2. Smoke gate
log "smoke gate check"
"$CHECK" "$OUT/smoke_stock/records.jsonl" "$OUT/smoke_augmented/records.jsonl" --expect-count 12
log "smoke gate passed -> proceed to held-out"

# 3. Held-out: Stock-Core 224 once
log "held-out stock start"
"$RUNNER" --arm stock --manifest "$MANIFEST" --out "$OUT/stock_core" --parallel "$PARALLEL" --timelimit "$TIMELIMIT"
log "held-out stock done"

# 4. Held-out: Augmented-Core 224 once
log "held-out augmented start"
"$RUNNER" --arm augmented --manifest "$MANIFEST" --out "$OUT/augmented_core" --parallel "$PARALLEL" --timelimit "$TIMELIMIT"
log "held-out augmented done"

# 5. Final gate + summary
"$CHECK" "$OUT/stock_core/records.jsonl" "$OUT/augmented_core/records.jsonl" --expect-count 224
log "driver complete: all stages passed"
