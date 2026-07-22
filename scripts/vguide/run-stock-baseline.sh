#!/usr/bin/env bash

# This file is part of CPAchecker,
# a tool for configurable software verification:
# https://cpachecker.sosy-lab.org
#
# SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>
#
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

if [[ $# -ne 5 ]]; then
  echo "usage: $0 CPACHECKER_DIR SV_BENCHMARKS_DIR BENCH_DEFS_DIR BENCHEXEC_DIR OUTPUT_DIR" >&2
  exit 2
fi

CPACHECKER_DIR=$(realpath "$1")
SV_BENCHMARKS_DIR=$(realpath "$2")
BENCH_DEFS_DIR=$(realpath "$3")
BENCHEXEC_DIR=$(realpath "$4")
OUTPUT_DIR=$(realpath -m "$5")
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
EXPECTED_CPACHECKER=1848f9eb597ca99a170fd98af8aad716743a2bfe
EXPECTED_SV_BENCHMARKS=9cf9198156e4c8a6c517e474770158e1bb0b566d
EXPECTED_BENCH_DEFS=22caeaa1e578d6464231e9d5ac0c8a316706452f
EXPECTED_BENCHEXEC=edb95ed3a8478366b8bb89f8cdd1d9a6c5fa8c84

require_revision() {
  local repo=$1 expected=$2 label=$3
  local actual
  actual=$(git -C "$repo" rev-parse HEAD)
  if [[ "$actual" != "$expected" ]]; then
    echo "$label revision mismatch: expected $expected, got $actual" >&2
    exit 1
  fi
}

require_revision "$CPACHECKER_DIR" "$EXPECTED_CPACHECKER" CPAchecker
require_revision "$SV_BENCHMARKS_DIR" "$EXPECTED_SV_BENCHMARKS" sv-benchmarks
require_revision "$BENCH_DEFS_DIR" "$EXPECTED_BENCH_DEFS" benchmark-definitions
require_revision "$BENCHEXEC_DIR" "$EXPECTED_BENCHEXEC" BenchExec
if [[ -n $(git -C "$CPACHECKER_DIR" status --porcelain) ]]; then
  echo "CPAchecker checkout is not clean" >&2
  exit 1
fi
if env | grep -Eq '^(VGUIDE_|DEEPSEEK_API_KEY=|OPENAI_API_KEY=)'; then
  echo "LLM/VGuide environment is forbidden for the stock baseline" >&2
  exit 1
fi

systemd-run --user --quiet --scope --slice=benchexec -p Delegate=yes \
  env PYTHONPATH="$BENCHEXEC_DIR" python3 -m benchexec.check_cgroups --no-thread

mkdir -p "$OUTPUT_DIR/generated" "$OUTPUT_DIR/results" "$OUTPUT_DIR/provenance"
JAVA_HOME=${JAVA_HOME:?JAVA_HOME must point to JDK 21}
JAVA="$JAVA_HOME/bin/java"
if [[ ! -x "$JAVA" ]]; then
  echo "JAVA_HOME does not contain an executable bin/java: $JAVA_HOME" >&2
  exit 1
fi
env JAVA_HOME="$JAVA_HOME" \
  "$SCRIPT_DIR/baseline.py" machine --output "$OUTPUT_DIR/provenance/machine.json"
"$SCRIPT_DIR/baseline.py" inventory \
  --sv-benchmarks "$SV_BENCHMARKS_DIR" \
  --output "$OUTPUT_DIR/provenance/task-manifest.json"
PYTHONPATH="$BENCHEXEC_DIR" "$SCRIPT_DIR/baseline.py" provenance \
  --cpachecker "$CPACHECKER_DIR" \
  --sv-benchmarks "$SV_BENCHMARKS_DIR" \
  --bench-defs "$BENCH_DEFS_DIR" \
  --benchexec "$BENCHEXEC_DIR" \
  --output "$OUTPUT_DIR/provenance/run.json"
"$SCRIPT_DIR/baseline.py" render \
  --sv-benchmarks "$SV_BENCHMARKS_DIR" \
  --output-dir "$OUTPUT_DIR/generated" \
  --name svcomp27-loops-stock

exec systemd-run --user --scope --slice=benchexec -p Delegate=yes \
  env JAVA="$JAVA" PYTHONPATH="$BENCHEXEC_DIR" python3 -m benchexec.benchexec \
  --tool-directory "$CPACHECKER_DIR" \
  --outputpath "$OUTPUT_DIR/results" \
  --allowedCores 0,2,4,6,8,10,12,14 \
  --no-hyperthreading \
  --container \
  --read-only-dir / \
  -N 2 -c 4 \
  "$OUTPUT_DIR/generated/svcomp27-loops-stock.xml"
