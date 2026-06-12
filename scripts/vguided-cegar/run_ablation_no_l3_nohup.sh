#!/usr/bin/env bash
# L3 ablation: vguide.enableL3Entailment=false (all predicates -> PRECISION_ONLY, no strengthen).
# Compare with full_scalar_vguide (L3 on) and stock baseline after completion.
#
# Usage:
#   nohup ./run_ablation_no_l3_nohup.sh >> output/vguide/experiments/ablation_no_l3.log 2>&1 &
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
RUN="$REPO/scripts/vguided-cegar/run.sh"
export JAVA="${JAVA:-$HOME/.local/bin/java}"
export PATH="${HOME}/.local/ant/bin:$(dirname "$JAVA"):${PATH:-}"
export SV_BENCHMARKS="${SV_BENCHMARKS:-$HOME/sv-benchmarks/c}"
export DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:?DEEPSEEK_API_KEY required}"

OUT="output/vguide/experiments/full_scalar_vguide_noL3"
cd "$REPO"

echo "=== L3 ablation start $(date -Iseconds) ==="
echo "option: vguide.enableL3Entailment=false"
echo "out: $OUT"

"$RUN" cpa --set full_scalar --ablation no-l3 --parallel 8 --timelimit 300 --out "$OUT"

echo "=== L3 ablation done $(date -Iseconds) ==="

VG_BASE="output/vguide/experiments/full_scalar_vguide"
ST_BASE="output/vguide/experiments/full_scalar_stock"
if [[ -d "$OUT/logs" && -d "$VG_BASE/logs" ]]; then
  python3 "$REPO/scripts/vguided-cegar/compare_official_reference.py" \
    --baseline stock \
    --vguide-logs "$OUT/logs" \
    --baseline-logs "$ST_BASE/logs" \
    --manifest "$REPO/docs/vguided-cegar/benchmark_sets/full_scalar.list" \
    | tee "$OUT/vs_stock_baseline.txt"
  python3 "$REPO/scripts/vguided-cegar/analyze_benchmark_comparison.py" \
    --vguide-logs "$OUT/logs" \
    --baseline-logs "$ST_BASE/logs" \
    --manifest "$REPO/docs/vguided-cegar/benchmark_sets/full_scalar.list" \
    --timelimit 300 \
    --out "$OUT"
  echo "=== vs L3-on baseline ==="
  python3 - <<'PY' "$OUT/logs" "$VG_BASE/logs" "$REPO/docs/vguided-cegar/benchmark_sets/full_scalar.list"
import re, sys
from pathlib import Path

no_l3 = Path(sys.argv[1])
l3_on = Path(sys.argv[2])
manifest = Path(sys.argv[3]).read_text().splitlines()
tasks = []
for line in manifest:
    line = line.strip()
    if line and not line.startswith("#"):
        tasks.append(Path(line).stem)

def parse(logdir, task):
    p = logdir / f"{task}.log"
    if not p.exists():
        return "MISSING", None
    t = p.read_text(errors="replace")
    m = re.search(r"Verification result:\s*(\w+)", t)
    r = m.group(1).upper() if m else "UNKNOWN"
    wm = re.search(r"Total time for CPAchecker:\s+([\d.]+)", t)
    w = float(wm.group(1)) if wm else None
    return r, w

score = {"TRUE": 3, "FALSE": 2, "UNKNOWN": 1, "ERROR": 0}
def bucket(r):
    if r in ("TRUE", "FALSE"):
        return r
    return "INCOMPLETE"

imp = deg = same = 0
for task in tasks:
    r0, _ = parse(l3_on, task)
    r1, _ = parse(no_l3, task)
    s0 = score.get(bucket(r0), 1)
    s1 = score.get(bucket(r1), 1)
    if s1 > s0:
        imp += 1
    elif s1 < s0:
        deg += 1
    else:
        same += 1
print(f"noL3 vs L3-on: improved={imp} same={same} degraded={deg} (tasks={len(tasks)})")
PY
fi
