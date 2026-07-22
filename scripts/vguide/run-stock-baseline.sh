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
EXPECTED_CORPUS=9696f77dec0b5a64198240ca2f515e2e30f3bb3db4d5d68655a9521c542329a9
EXPECTED_JDK=867ff62e01a0936fc0a90ceae27338be1973559767ef0717896f8d64f780ece6
EXPECTED_CONFIG=90c8da6caef2a934cf7316fb5a591bae58b243a18e6772089453b9c755cc441b
EXPECTED_SOURCE=f00720ec4375df486eeaef41fe365d3dc021d4b63985b0c1d80a1ae05b78a25d
EXPECTED_CLASSES=614a87278ff960242c8227e01d7db609c3c8154b546348229ee57080967717f3

if [[ -d "$OUTPUT_DIR" && -n $(find "$OUTPUT_DIR" -mindepth 1 -print -quit) ]]; then
  echo "output directory must be absent or empty: $OUTPUT_DIR" >&2
  exit 1
fi

require_revision() {
  local repo=$1 expected=$2 label=$3
  local actual
  actual=$(git -C "$repo" rev-parse HEAD)
  if [[ "$actual" != "$expected" ]]; then
    echo "$label revision mismatch: expected $expected, got $actual" >&2
    exit 1
  fi
}

json_field() {
  python3 - "$1" "$2" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as source:
  value = json.load(source)
for component in sys.argv[2].split("."):
  value = value[component]
print(value)
PY
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

P_CORES=0,2,4,6,8,10,12,14
systemd-run --user --quiet --scope --slice=benchexec -p Delegate=yes \
  taskset -c "$P_CORES" env PYTHONPATH="$BENCHEXEC_DIR" \
  python3 -m benchexec.check_cgroups --no-thread

mkdir -p "$OUTPUT_DIR/generated" "$OUTPUT_DIR/results" "$OUTPUT_DIR/provenance"
finalize_artifacts() {
  local status=$?
  local artifact_status=0
  trap - EXIT
  "$SCRIPT_DIR/baseline.py" artifact-manifest \
    --root "$OUTPUT_DIR" \
    --output "$OUTPUT_DIR/provenance/artifact-manifest.json" || artifact_status=$?
  if ((status != 0)); then
    exit "$status"
  fi
  exit "$artifact_status"
}
trap finalize_artifacts EXIT

JAVA_HOME=${JAVA_HOME:?JAVA_HOME must point to JDK 21}
JAVA="$JAVA_HOME/bin/java"
if [[ ! -x "$JAVA" ]]; then
  echo "JAVA_HOME does not contain an executable bin/java: $JAVA_HOME" >&2
  exit 1
fi
java_output=$($JAVA -version 2>&1)
java_version=${java_output%%$'\n'*}
if [[ "$java_version" != *'21.0.11'* ]]; then
  echo "baseline v1 requires the pinned OpenJDK 21.0.11 runtime, got: $java_version" >&2
  exit 1
fi
jdk_digest_json=$("$SCRIPT_DIR/baseline.py" directory-digest --root "$JAVA_HOME")
jdk_digest=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["sha256"])' \
  <<<"$jdk_digest_json")
if [[ "$jdk_digest" != "$EXPECTED_JDK" ]]; then
  echo "JDK tree hash mismatch: expected $EXPECTED_JDK, got $jdk_digest" >&2
  exit 1
fi
run_ant_gate() {
  local name=$1
  shift
  (
    cd "$CPACHECKER_DIR"
    taskset -c "$P_CORES" env JAVA_HOME="$JAVA_HOME" PATH="$JAVA_HOME/bin:$PATH" \
      ant "$@"
  ) 2>&1 | tee "$OUTPUT_DIR/provenance/$name.log"
}
run_ant_gate build -Divy.disable=true clean jar
run_ant_gate unit-tests -Divy.disable=true -DskipBuild=true unit-tests
JAVA_TOOL_OPTIONS=-Xmx4g run_ant_gate configuration-checks \
  -Divy.disable=true -DskipBuild=true configuration-checks
run_ant_gate integration-tests -Divy.disable=true -DskipBuild=true integration-tests
if [[ -n $(git -C "$CPACHECKER_DIR" status --porcelain) ]]; then
  echo "CPAchecker checkout changed during the upstream gate" >&2
  exit 1
fi
env JAVA_HOME="$JAVA_HOME" \
  "$SCRIPT_DIR/baseline.py" machine --output "$OUTPUT_DIR/provenance/machine-before.json"
"$SCRIPT_DIR/baseline.py" inventory \
  --sv-benchmarks "$SV_BENCHMARKS_DIR" \
  --output "$OUTPUT_DIR/provenance/task-manifest.json"
actual_corpus=$(json_field "$OUTPUT_DIR/provenance/task-manifest.json" corpus_sha256)
if [[ "$actual_corpus" != "$EXPECTED_CORPUS" ]]; then
  echo "corpus hash mismatch: expected $EXPECTED_CORPUS, got $actual_corpus" >&2
  exit 1
fi
PYTHONPATH="$BENCHEXEC_DIR" "$SCRIPT_DIR/baseline.py" provenance \
  --cpachecker "$CPACHECKER_DIR" \
  --sv-benchmarks "$SV_BENCHMARKS_DIR" \
  --bench-defs "$BENCH_DEFS_DIR" \
  --benchexec "$BENCHEXEC_DIR" \
  --output "$OUTPUT_DIR/provenance/run.json"
actual_config=$(json_field "$OUTPUT_DIR/provenance/run.json" config_closure_sha256)
if [[ "$actual_config" != "$EXPECTED_CONFIG" ]]; then
  echo "stock configuration closure mismatch: expected $EXPECTED_CONFIG, got $actual_config" >&2
  exit 1
fi
actual_source=$(json_field "$OUTPUT_DIR/provenance/run.json" tracked_source_archive_sha256)
if [[ "$actual_source" != "$EXPECTED_SOURCE" ]]; then
  echo "tracked source archive mismatch: expected $EXPECTED_SOURCE, got $actual_source" >&2
  exit 1
fi
actual_classes=$(json_field "$OUTPUT_DIR/provenance/run.json" compiled_classes_sha256)
if [[ "$actual_classes" != "$EXPECTED_CLASSES" ]]; then
  echo "compiled-class hash mismatch: expected $EXPECTED_CLASSES, got $actual_classes" >&2
  exit 1
fi
"$SCRIPT_DIR/baseline.py" render \
  --sv-benchmarks "$SV_BENCHMARKS_DIR" \
  --output-dir "$OUTPUT_DIR/generated" \
  --name svcomp27-loops-stock
"$SCRIPT_DIR/baseline.py" render \
  --sv-benchmarks "$SV_BENCHMARKS_DIR" \
  --output-dir "$OUTPUT_DIR/generated" \
  --name svcomp27-loops-stock-calibration \
  --calibration-per-verdict 5

run_benchexec() {
  local name=$1 xml=$2 output=$3 threads=$4 cores_per_run=$5
  mkdir -p "$output"
  systemd-run --user --quiet --scope --slice=benchexec -p Delegate=yes \
    taskset -c "$P_CORES" env JAVA="$JAVA" PYTHONPATH="$BENCHEXEC_DIR" \
    python3 -m benchexec.benchexec \
    --name "$name" \
    --tool-directory "$CPACHECKER_DIR" \
    --outputpath "$output" \
    --allowedCores "$P_CORES" \
    --no-hyperthreading \
    --container \
    --read-only-dir / \
    --hidden-dir /home \
    -N "$threads" -c "$cores_per_run" \
    "$xml"
}

single_result() {
  local directory=$1
  local -a results
  mapfile -t results < <(find "$directory" -maxdepth 1 -type f \
    \( -name '*.results.*.xml' -o -name '*.results.*.xml.bz2' \) -print)
  if [[ ${#results[@]} -ne 1 ]]; then
    echo "expected exactly one BenchExec result in $directory, found ${#results[@]}" >&2
    return 1
  fi
  printf '%s\n' "${results[0]}"
}

declare -a CALIBRATION_RESULTS=()
for repetition in 1 2 3; do
  calibration_output="$OUTPUT_DIR/results/calibration-$repetition"
  run_benchexec \
    "baseline-v1-calibration-$repetition" \
    "$OUTPUT_DIR/generated/svcomp27-loops-stock-calibration.xml" \
    "$calibration_output" \
    2 4
  CALIBRATION_RESULTS+=("$(single_result "$calibration_output")")
done

calibration_args=()
for result in "${CALIBRATION_RESULTS[@]}"; do
  calibration_args+=(--result "$result")
done
"$SCRIPT_DIR/baseline.py" calibration-summary \
  "${calibration_args[@]}" \
  --task-manifest "$OUTPUT_DIR/generated/svcomp27-loops-stock-calibration.manifest.json" \
  --output "$OUTPUT_DIR/provenance/calibration-summary.json"
env JAVA_HOME="$JAVA_HOME" \
  "$SCRIPT_DIR/baseline.py" machine \
  --output "$OUTPUT_DIR/provenance/machine-after-calibration.json"

full_output="$OUTPUT_DIR/results/full"
run_benchexec \
  baseline-v1-full \
  "$OUTPUT_DIR/generated/svcomp27-loops-stock.xml" \
  "$full_output" \
  2 4
full_result=$(single_result "$full_output")
"$SCRIPT_DIR/baseline.py" summarize \
  --result "$full_result" \
  --task-manifest "$OUTPUT_DIR/provenance/task-manifest.json" \
  --output-dir "$OUTPUT_DIR/summary"
env JAVA_HOME="$JAVA_HOME" \
  "$SCRIPT_DIR/baseline.py" machine --output "$OUTPUT_DIR/provenance/machine-after-full.json"

mapfile -t full_result_directories < <(find "$full_output" -maxdepth 1 -type d \
  -name '*.files' -print)
if [[ ${#full_result_directories[@]} -ne 1 ]]; then
  echo "expected exactly one BenchExec result-files directory in $full_output;" \
    "found ${#full_result_directories[@]}" >&2
  exit 1
fi
validation_generated="$OUTPUT_DIR/generated/witness-validation"
"$SCRIPT_DIR/baseline.py" render-validation \
  --result "$full_result" \
  --task-manifest "$OUTPUT_DIR/provenance/task-manifest.json" \
  --result-files "${full_result_directories[0]}" \
  --sv-benchmarks "$SV_BENCHMARKS_DIR" \
  --bench-defs "$BENCH_DEFS_DIR" \
  --output-dir "$validation_generated" \
  --output "$OUTPUT_DIR/provenance/witness-validation-manifest.json"

correctness_output="$OUTPUT_DIR/results/witness-validation-correctness"
violation_output="$OUTPUT_DIR/results/witness-validation-violation"
run_benchexec \
  baseline-v1-correctness-witness-validation \
  "$validation_generated/baseline-v1-correctness-witness-validation.xml" \
  "$correctness_output" \
  4 2
run_benchexec \
  baseline-v1-violation-witness-validation \
  "$validation_generated/baseline-v1-violation-witness-validation.xml" \
  "$violation_output" \
  4 2
correctness_result=$(single_result "$correctness_output")
violation_result=$(single_result "$violation_output")
correctness_manifest="$validation_generated/"
correctness_manifest+=baseline-v1-correctness-witness-validation.manifest.json
violation_manifest="$validation_generated/"
violation_manifest+=baseline-v1-violation-witness-validation.manifest.json
"$SCRIPT_DIR/baseline.py" validation-summary \
  --correctness-result "$correctness_result" \
  --correctness-manifest "$correctness_manifest" \
  --violation-result "$violation_result" \
  --violation-manifest "$violation_manifest" \
  --output "$OUTPUT_DIR/summary/witness-validation.json"
env JAVA_HOME="$JAVA_HOME" \
  "$SCRIPT_DIR/baseline.py" machine \
  --output "$OUTPUT_DIR/provenance/machine-after-validation.json"
