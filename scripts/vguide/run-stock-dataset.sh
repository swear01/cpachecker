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
  echo "usage: $0 CPACHECKER_DIR SV_BENCHMARKS_DIR BENCHEXEC_DIR CANDIDATE_MANIFEST OUTPUT_DIR" >&2
  exit 2
fi

CPACHECKER_DIR=$(realpath "$1")
SV_BENCHMARKS_DIR=$(realpath "$2")
BENCHEXEC_DIR=$(realpath "$3")
MANIFEST=$(realpath "$4")
OUTPUT_DIR=$(realpath -m "$5")
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
EXPECTED_CPACHECKER=1848f9eb597ca99a170fd98af8aad716743a2bfe
EXPECTED_SV_BENCHMARKS=9cf9198156e4c8a6c517e474770158e1bb0b566d
EXPECTED_BENCHEXEC=edb95ed3a8478366b8bb89f8cdd1d9a6c5fa8c84
EXPECTED_MANIFEST=c6d914c113c1e7e5f66f1b76b3f3fab4d111b936b12c24a8a1a83bdff926803b
EXPECTED_JDK=867ff62e01a0936fc0a90ceae27338be1973559767ef0717896f8d64f780ece6
P_CORES=0,2,4,6,8,10,12,14

[[ $(git -C "$CPACHECKER_DIR" rev-parse HEAD) == "$EXPECTED_CPACHECKER" ]]
[[ $(git -C "$SV_BENCHMARKS_DIR" rev-parse HEAD) == "$EXPECTED_SV_BENCHMARKS" ]]
[[ $(git -C "$BENCHEXEC_DIR" rev-parse HEAD) == "$EXPECTED_BENCHEXEC" ]]
[[ -z $(git -C "$CPACHECKER_DIR" status --porcelain) ]]
[[ $(sha256sum "$MANIFEST" | cut -d' ' -f1) == "$EXPECTED_MANIFEST" ]]
"$SCRIPT_DIR/dataset.py" validate \
  --manifest "$MANIFEST" \
  --sv-benchmarks "$SV_BENCHMARKS_DIR"
if [[ -d "$OUTPUT_DIR" && -n $(find "$OUTPUT_DIR" -mindepth 1 -print -quit) ]]; then
  echo "output directory must be absent or empty: $OUTPUT_DIR" >&2
  exit 1
fi
if env | grep -Eq '^(VGUIDE_|DEEPSEEK_API_KEY=|OPENAI_API_KEY=)'; then
  echo "LLM/VGuide environment is forbidden for stock dataset selection" >&2
  exit 1
fi

JAVA_HOME=${JAVA_HOME:?JAVA_HOME must point to the pinned JDK 21}
[[ $("$SCRIPT_DIR/baseline.py" directory-digest --root "$JAVA_HOME" |
  python3 -c 'import json,sys; print(json.load(sys.stdin)["sha256"])') == "$EXPECTED_JDK" ]]
systemd-run --user --quiet --scope --slice=benchexec -p Delegate=yes \
  taskset -c "$P_CORES" env PYTHONPATH="$BENCHEXEC_DIR" \
  python3 -m benchexec.check_cgroups --no-thread

mkdir -p "$OUTPUT_DIR/generated" "$OUTPUT_DIR/results" "$OUTPUT_DIR/provenance"
cp "$MANIFEST" "$OUTPUT_DIR/provenance/candidate-manifest.json"
(
  cd "$CPACHECKER_DIR"
  taskset -c "$P_CORES" env JAVA_HOME="$JAVA_HOME" PATH="$JAVA_HOME/bin:$PATH" \
    ant -Divy.disable=true clean jar
) 2>&1 | tee "$OUTPUT_DIR/provenance/build.log"
env JAVA_HOME="$JAVA_HOME" "$SCRIPT_DIR/baseline.py" machine \
  --output "$OUTPUT_DIR/provenance/machine-before.json"
"$SCRIPT_DIR/dataset.py" render \
  --manifest "$MANIFEST" \
  --sv-benchmarks "$SV_BENCHMARKS_DIR" \
  --property-file "$SV_BENCHMARKS_DIR/c/properties/unreach-call.prp" \
  --output-dir "$OUTPUT_DIR/generated"

run_benchexec() {
  local repetition=$1
  local output="$OUTPUT_DIR/results/repetition-$repetition"
  mkdir -p "$output"
  (
    cd "$CPACHECKER_DIR"
    systemd-run --user --quiet --scope --slice=benchexec -p Delegate=yes \
      taskset -c "$P_CORES" env -i \
      HOME=/home/benchexec LANG=C.UTF-8 LC_ALL=C.UTF-8 PATH=/usr/bin:/bin \
      JAVA="$JAVA_HOME/bin/java" PYTHONPATH="$BENCHEXEC_DIR" \
      /usr/bin/python3 -m benchexec.benchexec \
      --name "hard-case-dataset-v1-r$repetition" \
      --tool-directory "$CPACHECKER_DIR" \
      --outputpath "$output/" \
      --allowedCores "$P_CORES" \
      --no-hyperthreading \
      --container \
      --read-only-dir / \
      --hidden-dir /home \
      --overlay-dir "$CPACHECKER_DIR" \
      -N 2 -c 4 \
      "$OUTPUT_DIR/generated/hard-case-candidates.xml"
  )
}

single_result() {
  local directory=$1
  find "$directory" -maxdepth 1 -type f \
    \( -name '*.results.*.xml' -o -name '*.results.*.xml.bz2' \) -print
}

run_benchexec 1
env JAVA_HOME="$JAVA_HOME" "$SCRIPT_DIR/baseline.py" machine \
  --output "$OUTPUT_DIR/provenance/machine-after-repetition-1.json"
run_benchexec 2
env JAVA_HOME="$JAVA_HOME" "$SCRIPT_DIR/baseline.py" machine \
  --output "$OUTPUT_DIR/provenance/machine-after-repetition-2.json"

mapfile -t results < <(
  single_result "$OUTPUT_DIR/results/repetition-1"
  single_result "$OUTPUT_DIR/results/repetition-2"
)
if [[ ${#results[@]} -ne 2 ]]; then
  echo "expected two result files, found ${#results[@]}" >&2
  exit 1
fi
"$SCRIPT_DIR/dataset.py" summarize \
  --manifest "$MANIFEST" \
  --result "${results[0]}" \
  --result "${results[1]}" \
  --output-dir "$OUTPUT_DIR/summary"
"$SCRIPT_DIR/baseline.py" artifact-manifest \
  --root "$OUTPUT_DIR" \
  --output "$OUTPUT_DIR/provenance/artifact-manifest.json"
