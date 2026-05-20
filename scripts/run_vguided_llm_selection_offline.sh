#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ $# -lt 3 || $# -gt 4 ]]; then
  echo "usage: $0 <selection-csv> <results-subdir> <tmux-session> [jobs]" >&2
  exit 2
fi

selection_csv="$1"
results_subdir="$2"
session="$3"
jobs="${4:-${VGUIDED_JOBS:-4}}"

if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
  echo "OPENROUTER_API_KEY is not set" >&2
  exit 1
fi

if [[ ! -f "${selection_csv}" ]]; then
  echo "selection CSV does not exist: ${selection_csv}" >&2
  exit 1
fi

mkdir -p results/vguided-bench/logs "${results_subdir}"

stamp="$(date +%Y%m%d_%H%M%S)"
safe_session="${session//[^A-Za-z0-9_.-]/_}"
log="results/vguided-bench/logs/${safe_session}_${stamp}.log"
pidfile="${results_subdir}/run.pid"
logpathfile="${results_subdir}/run.logpath"
socket="$(pwd)/results/vguided-bench/tmux.sock"
envfile="${results_subdir}/run.env"

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
EOF
if [[ -n "${OPENROUTER_REASONING_TOKENS:-}" ]]; then
  printf "export OPENROUTER_REASONING_TOKENS='%s'\n" "${OPENROUTER_REASONING_TOKENS}" >>"${envfile}"
fi
if [[ -n "${OPENROUTER_MAX_COMPLETION_TOKENS:-}" ]]; then
  printf "export OPENROUTER_MAX_COMPLETION_TOKENS='%s'\n" "${OPENROUTER_MAX_COMPLETION_TOKENS}" >>"${envfile}"
fi
chmod 600 "${envfile}"

printf '%s\n' "${log}" >"${logpathfile}"

tmux -S "${socket}" new-session -d -s "${session}" \
  "cd '$(pwd)' && . '${envfile}' && python3 scripts/vguided_bench.py \
    --phase compare \
    --selection-csv '${selection_csv}' \
    --timelimit 300 \
    --heap 8000M \
    --jobs '${jobs}' \
    --results-dir '${results_subdir}' \
    >'${log}' 2>&1"

pid="$(tmux -S "${socket}" list-panes -t "${session}" -F '#{pane_pid}')"
printf '%s\n' "${pid}" >"${pidfile}"

echo "Started V-guided LLM run tmux session ${session}, pane PID ${pid}"
echo "Socket: ${socket}"
echo "Selection: ${selection_csv}"
echo "Log: ${log}"
echo "CSV: ${results_subdir}/vguided.csv"
