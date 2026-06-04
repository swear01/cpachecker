#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

mkdir -p results/vguided-bench/logs

stamp="$(date +%Y%m%d_%H%M%S)"
log="results/vguided-bench/logs/pilot_${stamp}.log"
pidfile="results/vguided-bench/pilot.pid"

setsid nohup env PYTHONUNBUFFERED=1 python3 scripts/vguided_bench.py \
    --phase pilot \
    --timelimit 300 \
    --heap 8000M \
    --jobs 8 \
    --resume \
    >"${log}" 2>&1 < /dev/null &

pid="$!"
printf '%s\n' "${pid}" >"${pidfile}"

echo "Started vguided pilot PID ${pid}"
echo "Log: ${log}"
echo "CSV: results/vguided-bench/baseline_stock.csv"
