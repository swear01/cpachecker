#!/usr/bin/env bash
# Build the deck. Usage: build.sh [light]  (default dark). Output: ./main.pdf
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"; cd "$DIR"
MODE="${1:-dark}"
export PATH="/Library/TeX/texbin:$PATH"
JOBARG=""
[[ "$MODE" == "light" ]] && JOBARG="\\def\\slidemode{light}"
T="${TECTONIC:-$HOME/.local/bin/tectonic}"
if [[ -x "$T" ]]; then
  "$T" -X compile main.tex --outdir . --print
else
  for _ in 1 2; do
    lualatex -interaction=nonstopmode -halt-on-error "${JOBARG}\\input{main}"
  done
fi
[[ -f main.pdf ]] || { echo "ERROR: no main.pdf produced" >&2; exit 1; }
if grep -qi "overfull" main.log 2>/dev/null; then
  echo "WARN: overfull boxes — check main.log (拆頁/縮圖,勿縮字)"
fi
echo "Wrote $DIR/main.pdf (mode=$MODE)"
