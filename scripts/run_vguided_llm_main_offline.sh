#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
  echo "OPENROUTER_API_KEY is not set" >&2
  exit 1
fi

mkdir -p results/vguided-bench/logs results/vguided-bench/llm-main-solved

stamp="$(date +%Y%m%d_%H%M%S)"
log="results/vguided-bench/logs/llm_main_solved_${stamp}.log"
pidfile="results/vguided-bench/llm-main-solved.pid"
logpathfile="results/vguided-bench/llm-main-solved.logpath"
session="vguided_llm_main"
socket="$(pwd)/results/vguided-bench/tmux.sock"
envfile="results/vguided-bench/llm-main-solved.env"

if tmux -S "${socket}" has-session -t "${session}" 2>/dev/null; then
  echo "tmux session ${session} is already running" >&2
  echo "Log: $(cat "${logpathfile}" 2>/dev/null || true)" >&2
  exit 1
fi

cat >"${envfile}" <<EOF
export PYTHONUNBUFFERED=1
export JAVA_HOME=/home/swear01/FMPA2/external/jdk-21/jdk-21.0.10+7
export PATH=/home/swear01/FMPA2/external/jdk-21/jdk-21.0.10+7/bin:/home/swear01/.local/bin:\${PATH}
export OPENROUTER_API_KEY='${OPENROUTER_API_KEY}'
export OPENROUTER_TIMEOUT_SECONDS='${OPENROUTER_TIMEOUT_SECONDS:-300}'
export OPENROUTER_REASONING_TOKENS='${OPENROUTER_REASONING_TOKENS:-8192}'
export OPENROUTER_MAX_COMPLETION_TOKENS='${OPENROUTER_MAX_COMPLETION_TOKENS:-4096}'
EOF
chmod 600 "${envfile}"

printf '%s\n' "${log}" >"${logpathfile}"

tmux -S "${socket}" new-session -d -s "${session}" \
  "cd '$(pwd)' && . '${envfile}' && python3 scripts/vguided_bench.py \
    --phase compare \
    --selection-csv results/vguided-bench/selected_main_solved.csv \
    --timelimit 300 \
    --heap 8000M \
    --jobs '${VGUIDED_JOBS:-4}' \
    --results-dir results/vguided-bench/llm-main-solved \
    >'${log}' 2>&1"

pid="$(tmux -S "${socket}" list-panes -t "${session}" -F '#{pane_pid}')"
printf '%s\n' "${pid}" >"${pidfile}"

echo "Started V-guided LLM main-solved tmux session ${session}, pane PID ${pid}"
echo "Socket: ${socket}"
echo "Log: ${log}"
echo "CSV: results/vguided-bench/llm-main-solved/vguided.csv"
