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
source "$SCRIPT_DIR/run-stock-formal-dataset.sh"
EXPECTED_CPACHECKER=1848f9eb597ca99a170fd98af8aad716743a2bfe
EXPECTED_SV_BENCHMARKS=9cf9198156e4c8a6c517e474770158e1bb0b566d
EXPECTED_BENCHEXEC=edb95ed3a8478366b8bb89f8cdd1d9a6c5fa8c84
EXPECTED_JDK=867ff62e01a0936fc0a90ceae27338be1973559767ef0717896f8d64f780ece6
EXPECTED_STOCK_LIB_JAVA=eea0df062de5c8e3febe0d96b583741c140e79d3ae41a87a56d7be365b876f9d
EXPECTED_ANT_INSTALL=52772e241e78a875fa00dea891eac2023d4f2be639a5f28a17dca81580f75e5b
EXPECTED_ANT_VERSION="Apache Ant(TM) version 1.10.12 compiled on January 17 1970"
EXPECTED_PYTHON_REAL=/usr/bin/python3.10
EXPECTED_PYTHON_SHA256=7d51cd6b48b521277f5caa4610a82126e315fa2be4df069823a8b1eeb5bd4a86
EXPECTED_PYTHON_VERSION="Python 3.10.12"
EXPECTED_PYTHON_STDLIB=/usr/lib/python3.10
EXPECTED_PYTHON_STDLIB_DIGEST=eef7994f6b57cb0bbdb803ef6aadc0c1afbe61d444932eeef5dc5c114b6cf27b
EXPECTED_PYTHON_DIST_PACKAGES=/usr/lib/python3/dist-packages
EXPECTED_PYTHON_DIST_PACKAGES_DIGEST=0970024a48206a1937b5bfbf889335525b769b89a27ca7df25d793d7727b909c
EXPECTED_PYTHON_LOCAL_DIST_PACKAGES=/usr/local/lib/python3.10/dist-packages
EXPECTED_PYTHON_LOCAL_DIST_PACKAGES_DIGEST=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
EXPECTED_PYTHON_SYSTEM_PATH=/usr/lib/python310.zip:/usr/lib/python3.10:/usr/lib/python3.10/lib-dynload:/usr/local/lib/python3.10/dist-packages:/usr/lib/python3/dist-packages
EXPECTED_PYYAML_FILE=/usr/lib/python3/dist-packages/yaml/__init__.py
EXPECTED_PYYAML_VERSION=5.4.1
EXPECTED_BENCHEXEC_ARCHIVE=75e3332253429e6f9186352a255cd96c0aff6154a95e2fdd3b737c143ba018bc
EXPECTED_BENCHEXEC_VERSION="benchexec 3.35-dev"
EXPECTED_CPACHECKER_JAR_CONTENT=49f95adc5255b89b1bb3edea81ab5f2f660364d36ffa69c3b12508d1e1943be3
EXPECTED_MANIFEST=16e5f9ff04ed08ef9c29d8674021c11de3eed87b9da6a8c1e2ef68c6847ec0bb
P_CORES=0,2,4,6,8,10,12,14
HOST=$(hostname -s)

[[ "$HOST" == athena ]] || {
  echo "cap-16 Phase A is Athena-only; refusing host: $HOST" >&2
  exit 1
}
[[ $(sha256sum "$MANIFEST" | cut -d' ' -f1) == "$EXPECTED_MANIFEST" ]]
run_python_script "$SCRIPT_DIR/dataset.py" validate \
  --manifest "$MANIFEST" \
  --sv-benchmarks "$SV_BENCHMARKS_DIR"
if env | grep -Eq '^(VGUIDE_|DEEPSEEK_API_KEY=|OPENAI_API_KEY=)'; then
  echo "LLM/VGuide environment is forbidden for stock dataset selection" >&2
  exit 1
fi

JAVA_HOME=$(realpath "${JAVA_HOME:?JAVA_HOME must point to the pinned JDK 21}")
ANT_HOME=$(realpath "${ANT_HOME:?ANT_HOME must point to the pinned Ant}")
ANT_INSTALL=$(realpath "$ANT_HOME/../..")
ANT_BIN="$ANT_HOME/bin/ant"
PYTHON_STDLIB=$(realpath "$EXPECTED_PYTHON_STDLIB")
PYTHON_DIST_PACKAGES=$(realpath "$EXPECTED_PYTHON_DIST_PACKAGES")
PYTHON_LOCAL_DIST_PACKAGES=$(realpath "$EXPECTED_PYTHON_LOCAL_DIST_PACKAGES")
remove_compiled_classes
assert_no_compiled_classes
verify_runtime_closure false
systemd-run --user --quiet --scope --slice=benchexec -p Delegate=yes \
  taskset -c "$P_CORES" "$PYTHON_BIN" -I -c \
  'import runpy,sys; sys.dont_write_bytecode=True; sys.pycache_prefix="/dev/null"; sys.path.insert(0,sys.argv.pop(1)); sys.argv[0]="benchexec"; runpy.run_module("benchexec.check_cgroups",run_name="__main__")' \
  "$BENCHEXEC_DIR" --no-thread

exec 9>/var/tmp/vguide-athena-pcores.lock
flock -n 9 || {
  echo "another VGuide run holds the Athena P-core lock" >&2
  exit 1
}

copy_manifest_package() {
  local source=$1
  local destination=$2
  local status
  "$PYTHON_BIN" -I - "$SCRIPT_DIR/dataset.py" "$source" "$destination" <<'PY'
import importlib.util
import json
import shutil
import sys
from pathlib import Path

script = Path(sys.argv[1]).resolve()
source = Path(sys.argv[2]).resolve()
destination = Path(sys.argv[3]).resolve()
spec = importlib.util.spec_from_file_location("dataset", script)
dataset = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dataset)
manifest = json.loads(source.read_text(encoding="utf-8"))
dataset.copy_declared_corpus_files(source, manifest, destination)
shutil.copyfile(source, destination / "candidate-manifest-athena.json")
PY
  status=$?
  [[ "$status" -eq 0 ]]
}

SAVED_INPUT="$OUTPUT_DIR/input"
if [[ ! -e "$OUTPUT_DIR" ]] || {
  [[ -d "$OUTPUT_DIR" ]] &&
    [[ -z $(find "$OUTPUT_DIR" -mindepth 1 -print -quit) ]]
}; then
  mkdir -p "$SAVED_INPUT/scripts" "$OUTPUT_DIR/generated" \
    "$OUTPUT_DIR/attempts" "$OUTPUT_DIR/provenance"
  copy_manifest_package "$MANIFEST" "$SAVED_INPUT" || exit
  cp "$SCRIPT_DIR/dataset.py" "$SCRIPT_DIR/baseline.py" \
    "$SCRIPT_DIR/run-stock-formal-dataset.sh" \
    "$SCRIPT_DIR/run-stock-cap16-dataset.sh" "$SAVED_INPUT/scripts/"
else
  [[ -d "$OUTPUT_DIR" ]]
  [[ $(sha256sum "$SAVED_INPUT/candidate-manifest-athena.json" |
    cut -d' ' -f1) == "$EXPECTED_MANIFEST" ]]
  cmp "$SCRIPT_DIR/dataset.py" "$SAVED_INPUT/scripts/dataset.py" || exit
  cmp "$SCRIPT_DIR/baseline.py" "$SAVED_INPUT/scripts/baseline.py" || exit
  cmp "$SCRIPT_DIR/run-stock-formal-dataset.sh" \
    "$SAVED_INPUT/scripts/run-stock-formal-dataset.sh" || exit
  cmp "$SCRIPT_DIR/run-stock-cap16-dataset.sh" \
    "$SAVED_INPUT/scripts/run-stock-cap16-dataset.sh" || exit
  [[ -d "$OUTPUT_DIR/generated" && -d "$OUTPUT_DIR/attempts" &&
    -d "$OUTPUT_DIR/provenance" ]]
fi
MANIFEST="$SAVED_INPUT/candidate-manifest-athena.json"
run_python_script "$SCRIPT_DIR/dataset.py" validate \
  --manifest "$MANIFEST" \
  --sv-benchmarks "$SV_BENCHMARKS_DIR"
if [[ -f "$OUTPUT_DIR/summary/.complete" ]]; then
  verify_runtime_closure true
  COMPLETE_CHECK=$(mktemp -d /var/tmp/vguide-cap16-summary-check.XXXXXX)
  run_python_script "$SCRIPT_DIR/dataset.py" screen-summary-plan \
    --manifest "$MANIFEST" \
    --benchmark-definition "$OUTPUT_DIR/generated/hard-case-candidates.xml" \
    --screen-plan "$OUTPUT_DIR/screen-plan.json" \
    --sv-benchmarks "$SV_BENCHMARKS_DIR" \
    --phase-a-host "$HOST" \
    --output-dir "$COMPLETE_CHECK"
  touch "$COMPLETE_CHECK/.complete"
  diff -r "$OUTPUT_DIR/summary" "$COMPLETE_CHECK"
  rm -r "$COMPLETE_CHECK"
  echo "cap-16 Phase A output is already complete: $OUTPUT_DIR"
  exit 0
fi
INVOCATION_NUMBER=$(find "$OUTPUT_DIR/provenance" -maxdepth 1 -type d \
  -name 'invocation-*' | wc -l)
printf -v INVOCATION 'invocation-%03d' "$INVOCATION_NUMBER"
INVOCATION_DIR="$OUTPUT_DIR/provenance/$INVOCATION"
mkdir "$INVOCATION_DIR"
verify_runtime_closure false
write_runtime_provenance "$INVOCATION_DIR/runtime-closure-before.txt"
MONITOR_PID=
BUILD_COMPLETED=false
capture_failure() {
  local status=$?
  trap - EXIT
  if [[ -n "$MONITOR_PID" ]] && kill -0 "$MONITOR_PID" 2>/dev/null; then
    kill "$MONITOR_PID"
    wait "$MONITOR_PID" || true
  fi
  if ((status != 0)); then
    set +e
    verify_runtime_closure "$BUILD_COMPLETED" \
      >"$INVOCATION_DIR/runtime-verification-failure.log" 2>&1
    JAVA_HOME="$JAVA_HOME" run_python_script "$SCRIPT_DIR/baseline.py" machine \
      --output "$INVOCATION_DIR/machine-after-failure.json"
    run_python_script "$SCRIPT_DIR/baseline.py" artifact-manifest \
      --root "$OUTPUT_DIR" \
      --output "$INVOCATION_DIR/artifact-manifest-failure.json"
  fi
  exit "$status"
}
trap capture_failure EXIT

(
  cd "$CPACHECKER_DIR"
  taskset -c "$P_CORES" env JAVA_HOME="$JAVA_HOME" \
    PATH="$JAVA_HOME/bin:$ANT_HOME/bin:$PATH" \
    "$ANT_BIN" -Divy.disable=true clean jar
) 2>&1 | tee "$INVOCATION_DIR/build.log"
CURRENT_JAR_CONTENT=$(jar_content_digest_value "$CPACHECKER_DIR/cpachecker.jar")
[[ "$CURRENT_JAR_CONTENT" == "$EXPECTED_CPACHECKER_JAR_CONTENT" ]]
if [[ -f "$OUTPUT_DIR/provenance/cpachecker-jar-content.sha256" ]]; then
  [[ $(cat "$OUTPUT_DIR/provenance/cpachecker-jar-content.sha256") == \
    "$CURRENT_JAR_CONTENT" ]]
else
  printf '%s\n' "$CURRENT_JAR_CONTENT" \
    >"$OUTPUT_DIR/provenance/.cpachecker-jar-content.tmp"
  mv "$OUTPUT_DIR/provenance/.cpachecker-jar-content.tmp" \
    "$OUTPUT_DIR/provenance/cpachecker-jar-content.sha256" || exit
fi
BUILD_COMPLETED=true
remove_compiled_classes
assert_no_compiled_classes
verify_runtime_closure true
JAVA_HOME="$JAVA_HOME" run_python_script "$SCRIPT_DIR/baseline.py" machine \
  --output "$INVOCATION_DIR/machine-preflight-start.json"
sleep 10
JAVA_HOME="$JAVA_HOME" run_python_script "$SCRIPT_DIR/baseline.py" machine \
  --output "$INVOCATION_DIR/machine-before.json"
run_python_script "$SCRIPT_DIR/baseline.py" machine-check \
  --before "$INVOCATION_DIR/machine-preflight-start.json" \
  --after "$INVOCATION_DIR/machine-before.json" |
  tee "$INVOCATION_DIR/machine-preflight-check.json"
if [[ -f "$OUTPUT_DIR/generated/SHA256SUMS" ]]; then
  (cd "$OUTPUT_DIR/generated" && sha256sum -c SHA256SUMS)
else
  run_python_script "$SCRIPT_DIR/dataset.py" render \
    --manifest "$MANIFEST" \
    --sv-benchmarks "$SV_BENCHMARKS_DIR" \
    --property-file "$SV_BENCHMARKS_DIR/c/properties/unreach-call.prp" \
    --output-dir "$OUTPUT_DIR/generated"
  (
    cd "$OUTPUT_DIR/generated"
    find . -maxdepth 1 -type f ! -name SHA256SUMS -print0 |
      sort -z | xargs -0 sha256sum >SHA256SUMS
  )
fi

single_result() {
  local directory=$1
  local matches=()
  mapfile -t matches < <(
    find "$directory" -maxdepth 1 -type f \
      \( -name '*.results.hard-case-candidates.xml' \
      -o -name '*.results.hard-case-candidates.xml.bz2' \
      -o -name '*.results.hard-case-candidates.official.xml' \
      -o -name '*.results.hard-case-candidates.official.xml.bz2' \) -print
  )
  [[ ${#matches[@]} -eq 1 ]] || {
    echo "expected one screen result file, found ${#matches[@]}" >&2
    return 1
  }
  printf '%s\n' "${matches[0]}"
}

promote_plan() {
  local candidate=$1
  local target=$2
  local partial_evidence=$3
  if [[ -f "$target" ]]; then
    if "$PYTHON_BIN" -c \
      'import json,sys; json.load(open(sys.argv[1]))' "$target" 2>/dev/null; then
      cmp "$target" "$candidate" || return
      rm "$candidate" || return
    else
      mv "$target" "$partial_evidence" || return
      mv "$candidate" "$target" || return
    fi
  else
    mv "$candidate" "$target" || return
  fi
}

write_atomic() {
  local value=$1
  local target=$2
  local candidate="$target.tmp.$$"
  printf '%s\n' "$value" >"$candidate" || return
  mv "$candidate" "$target" || return
}

promote_path_record() {
  local candidate=$1
  local target=$2
  local partial_evidence=$3
  if [[ -f "$target" ]]; then
    if cmp --silent "$target" "$candidate"; then
      rm "$candidate" || return
    else
      local recorded
      local expected
      local line_count
      recorded=$(cat "$target") || return
      expected=$(cat "$candidate") || return
      line_count=$(wc -l <"$target") || return
      if [[ "$line_count" -ne 0 || "$expected" != "$recorded"* ]]; then
        return 1
      fi
      mv "$target" "$partial_evidence" || return
      mv "$candidate" "$target" || return
    fi
  else
    mv "$candidate" "$target" || return
  fi
}

promote_summary() {
  local candidate=$1
  local target=$2
  local partial_evidence=$3
  if [[ -d "$target" ]]; then
    if [[ -f "$target/.complete" ]]; then
      diff -r "$target" "$candidate" || return
      rm -r "$candidate" || return
    else
      mv "$target" "$partial_evidence" || return
      mv "$candidate" "$target" || return
    fi
  else
    mv "$candidate" "$target" || return
  fi
}

run_screen() {
  local attempt_dir=$1
  local definition=$2
  local label
  label=$(basename "$attempt_dir") || return
  local result_dir="$attempt_dir/results"
  local monitor="$attempt_dir/load-monitor.jsonl"
  mkdir -p "$result_dir" || return
  taskset -c 16-23 "$PYTHON_BIN" -I -u -c '
import runpy
import sys
from pathlib import Path

script = Path(sys.argv.pop(1)).resolve()
sys.argv[0] = str(script)
sys.dont_write_bytecode = True
sys.pycache_prefix = "/dev/null"
sys.path.insert(0, str(script.parent))
runpy.run_path(str(script), run_name="__main__")
' "$SCRIPT_DIR/dataset.py" monitor-formal-load \
    --output "$monitor" --exclude-root "$$" &
  MONITOR_PID=$!
  for _ in {1..40}; do
    [[ -s "$monitor" ]] && break
    kill -0 "$MONITOR_PID" 2>/dev/null || return
    sleep 0.05 || return
  done
  while [[ $(($(wc -l <"$monitor") - 1)) -lt 10 ]] ||
    "$PYTHON_BIN" -c \
      'import json,sys; raise SystemExit(not any(x["contended"] for x in json.loads(open(sys.argv[1]).read().splitlines()[-1])["offenders"]))' \
      "$monitor"; do
    kill -0 "$MONITOR_PID" 2>/dev/null || return
    sleep 1 || return
  done
  set +e
  (
    cd "$CPACHECKER_DIR"
    systemd-run --user --quiet --scope --slice=benchexec -p Delegate=yes \
      taskset -c "$P_CORES" env -i \
      HOME=/home/benchexec LANG=C.UTF-8 LC_ALL=C.UTF-8 PATH=/usr/bin:/bin \
      JAVA="$JAVA_HOME/bin/java" \
      "$PYTHON_BIN" -I -c \
      'import runpy,sys; sys.dont_write_bytecode=True; sys.pycache_prefix="/dev/null"; sys.path.insert(0,sys.argv.pop(1)); sys.argv[0]="benchexec"; runpy.run_module("benchexec.benchexec",run_name="__main__")' \
      "$BENCHEXEC_DIR" \
      --name "hard-case-dataset-cap16-athena-$label" \
      --tool-directory "$CPACHECKER_DIR" \
      --outputpath "$result_dir/" \
      --allowedCores "$P_CORES" \
      --no-hyperthreading \
      --container \
      --read-only-dir / \
      --hidden-dir /home \
      --overlay-dir "$CPACHECKER_DIR" \
      -N 2 -c 4 \
      "$definition"
  ) 2>&1 | tee "$attempt_dir/benchexec.log"
  local pipeline_status
  pipeline_status=("${PIPESTATUS[@]}")
  local run_status=${pipeline_status[0]}
  local tee_status=${pipeline_status[1]}
  set -e
  [[ "$tee_status" -eq 0 ]] || return "$tee_status"
  kill "$MONITOR_PID" || return
  wait "$MONITOR_PID" || return
  MONITOR_PID=
  [[ $run_status -eq 0 || $run_status -eq 130 ]] || return "$run_status"
}

next_attempt_dir() {
  local count
  count=$(find "$OUTPUT_DIR/attempts" -mindepth 1 -maxdepth 1 \
    -type d -name 'attempt-*' | wc -l)
  printf '%s/attempt-%03d\n' "$OUTPUT_DIR/attempts" "$count"
}

attempt_has_result_file() {
  local attempt_dir=$1
  [[ -n $(find "$attempt_dir/results" -maxdepth 1 -type f \
    \( -name '*.results.hard-case-candidates.xml' \
    -o -name '*.results.hard-case-candidates.xml.bz2' \
    -o -name '*.results.hard-case-candidates.official.xml' \
    -o -name '*.results.hard-case-candidates.official.xml.bz2' \) \
    -print -quit 2>/dev/null) ]]
}

finalize_attempt() {
  local attempt_dir=$1
  local role
  local definition
  local result
  [[ -s "$attempt_dir/role" && -s "$attempt_dir/definition.path" ]] ||
    return 21
  role=$(cat "$attempt_dir/role")
  [[ "$role" == primary || "$role" == replacement ]] || return 21
  definition=$(cat "$attempt_dir/definition.path")
  [[ "$definition" == /* && -f "$definition" ]] || return 21
  if ! result=$(single_result "$attempt_dir/results"); then
    return 20
  fi
  local taint_candidate="$attempt_dir/.taint-$INVOCATION.tmp"
  rm -f "$taint_candidate" || return 21
  if ! run_python_script "$SCRIPT_DIR/dataset.py" screen-taint \
      --manifest "$MANIFEST" \
      --result "$result" \
      --benchexec-log "$attempt_dir/benchexec.log" \
      --load-monitor "$attempt_dir/load-monitor.jsonl" \
      --output "$taint_candidate"; then
    return 21
  fi
  promote_plan "$taint_candidate" "$attempt_dir/taint.json" \
    "$INVOCATION_DIR/partial-$(basename "$attempt_dir")-taint.json" ||
    return 21
  local result_candidate="$attempt_dir/.result-path-$INVOCATION.tmp"
  printf '%s\n' "$result" >"$result_candidate" || return 21
  promote_path_record "$result_candidate" "$attempt_dir/result.path" \
    "$INVOCATION_DIR/partial-$(basename "$attempt_dir")-result.path" ||
    return 21
}

run_new_attempt() {
  local role=$1
  local definition=$2
  local attempt_dir
  attempt_dir=$(next_attempt_dir) || return
  mkdir "$attempt_dir" || return
  write_atomic "$role" "$attempt_dir/role" || return
  write_atomic "$(realpath "$definition")" "$attempt_dir/definition.path" ||
    return
  run_screen "$attempt_dir" "$definition" || return $?
  local finalize_status
  if finalize_attempt "$attempt_dir"; then
    return
  else
    finalize_status=$?
  fi
  if [[ "$finalize_status" -eq 20 ]]; then
    touch "$attempt_dir/abandoned-no-result"
    return 20
  fi
  return "$finalize_status"
}

for attempt_dir in "$OUTPUT_DIR"/attempts/attempt-*; do
  [[ -d "$attempt_dir" ]] || continue
  if [[ ! -f "$attempt_dir/abandoned-no-result" &&
    ! -f "$attempt_dir/abandoned-incomplete-metadata" ]]; then
    if finalize_attempt "$attempt_dir"; then
      :
    elif [[ $? -eq 20 ]]; then
      if [[ -e "$attempt_dir/result.path" ]]; then
        mv "$attempt_dir/result.path" \
          "$INVOCATION_DIR/partial-$(basename "$attempt_dir")-result.path" ||
          exit
      fi
      touch "$attempt_dir/abandoned-no-result"
    else
      if attempt_has_result_file "$attempt_dir"; then
        echo "preserved attempt result cannot be authenticated for recovery: $attempt_dir" >&2
        exit 1
      fi
      for metadata in role definition.path; do
        if [[ -e "$attempt_dir/$metadata" ]]; then
          mv "$attempt_dir/$metadata" \
            "$INVOCATION_DIR/partial-$(basename "$attempt_dir")-$metadata" ||
            exit
        fi
      done
      touch "$attempt_dir/abandoned-incomplete-metadata"
    fi
  fi
done

mapfile -t RECORDS < <(
  find "$OUTPUT_DIR/attempts" -mindepth 2 -maxdepth 2 \
    -type f -name result.path -printf '%h\n' | sort
)
if [[ ${#RECORDS[@]} -eq 0 ]]; then
  if run_new_attempt primary \
    "$OUTPUT_DIR/generated/hard-case-candidates.xml"; then
    :
  elif [[ $? -eq 20 ]]; then
    echo "primary attempt produced no verifiable result; resume with the same output directory" >&2
    exit 1
  else
    echo "primary attempt result cannot be authenticated for recovery" >&2
    exit 1
  fi
  mapfile -t RECORDS < <(
    find "$OUTPUT_DIR/attempts" -mindepth 2 -maxdepth 2 \
      -type f -name result.path -printf '%h\n' | sort
  )
fi
[[ $(cat "${RECORDS[0]}/role") == primary ]]
PRIMARY=$(cat "${RECORDS[0]}/result.path")
TAINT="${RECORDS[0]}/taint.json"
CURRENT_RESULT=$(cat "${RECORDS[-1]}/result.path")
CURRENT_TAINT="${RECORDS[-1]}/taint.json"
TAINT_COUNT=$("$PYTHON_BIN" -c \
  'import json,sys; print(len(json.load(open(sys.argv[1]))["tasks"]))' \
  "$CURRENT_TAINT")

while [[ "$TAINT_COUNT" -gt 0 ]]; do
  ATTEMPT_DIR=$(next_attempt_dir)
  mkdir "$ATTEMPT_DIR"
  write_atomic replacement "$ATTEMPT_DIR/role" || exit
  REPLACEMENT_DIR="$ATTEMPT_DIR/generated"
  DEFINITION="$REPLACEMENT_DIR/hard-case-candidates.xml"
  run_python_script "$SCRIPT_DIR/dataset.py" render-screen-replacement \
    --manifest "$MANIFEST" \
    --primary-result "$CURRENT_RESULT" \
    --taint-manifest "$CURRENT_TAINT" \
    --sv-benchmarks "$SV_BENCHMARKS_DIR" \
    --property-file "$SV_BENCHMARKS_DIR/c/properties/unreach-call.prp" \
    --output-dir "$REPLACEMENT_DIR"
  write_atomic "$(realpath "$DEFINITION")" "$ATTEMPT_DIR/definition.path" ||
    exit
  run_screen "$ATTEMPT_DIR" "$DEFINITION"
  if finalize_attempt "$ATTEMPT_DIR"; then
    CURRENT_RESULT=$(cat "$ATTEMPT_DIR/result.path")
    CURRENT_TAINT="$ATTEMPT_DIR/taint.json"
    TAINT_COUNT=$("$PYTHON_BIN" -c \
      'import json,sys; print(len(json.load(open(sys.argv[1]))["tasks"]))' \
      "$CURRENT_TAINT")
  elif [[ $? -eq 20 ]]; then
    touch "$ATTEMPT_DIR/abandoned-no-result"
    echo "replacement attempt produced no verifiable result; resume with the same output directory" >&2
    exit 1
  else
    echo "replacement attempt result cannot be authenticated for recovery" >&2
    exit 1
  fi
done

mapfile -t RECORDS < <(
  find "$OUTPUT_DIR/attempts" -mindepth 2 -maxdepth 2 \
    -type f -name result.path -printf '%h\n' | sort
)
REPLACEMENT_ARGS=()
for attempt_dir in "${RECORDS[@]:1}"; do
  [[ $(cat "$attempt_dir/role") == replacement ]]
  REPLACEMENT_ARGS+=(
    --replacement-result "$(cat "$attempt_dir/result.path")"
    --replacement-definition "$(cat "$attempt_dir/definition.path")"
    --replacement-taint-manifest "$attempt_dir/taint.json"
  )
done
PLAN="$OUTPUT_DIR/screen-plan.json"
PLAN_CANDIDATE="$OUTPUT_DIR/.screen-plan-$INVOCATION.tmp"
run_python_script "$SCRIPT_DIR/dataset.py" screen-plan \
  --manifest "$MANIFEST" \
  --primary-result "$PRIMARY" \
  --taint-manifest "$TAINT" \
  "${REPLACEMENT_ARGS[@]}" \
  --output "$PLAN_CANDIDATE"
promote_plan "$PLAN_CANDIDATE" "$PLAN" \
  "$INVOCATION_DIR/partial-screen-plan.json" || exit

SUMMARY_CANDIDATE="$INVOCATION_DIR/summary"
run_python_script "$SCRIPT_DIR/dataset.py" screen-summary-plan \
  --manifest "$MANIFEST" \
  --benchmark-definition "$OUTPUT_DIR/generated/hard-case-candidates.xml" \
  --screen-plan "$PLAN" \
  --sv-benchmarks "$SV_BENCHMARKS_DIR" \
  --phase-a-host "$HOST" \
  --output-dir "$SUMMARY_CANDIDATE"
promote_summary "$SUMMARY_CANDIDATE" "$OUTPUT_DIR/summary" \
  "$INVOCATION_DIR/partial-summary" || exit
JAVA_HOME="$JAVA_HOME" run_python_script "$SCRIPT_DIR/baseline.py" machine \
  --output "$INVOCATION_DIR/machine-after-screen.json"
run_python_script "$SCRIPT_DIR/baseline.py" machine-check \
  --before "$INVOCATION_DIR/machine-before.json" \
  --after "$INVOCATION_DIR/machine-after-screen.json" |
  tee "$INVOCATION_DIR/machine-screen-check.json"
verify_runtime_closure true \
  >"$INVOCATION_DIR/runtime-verification-final.log" 2>&1
ARTIFACT_MANIFEST="$OUTPUT_DIR/provenance/artifact-manifest.json"
if [[ -f "$ARTIFACT_MANIFEST" ]]; then
  mv "$ARTIFACT_MANIFEST" \
    "$INVOCATION_DIR/partial-artifact-manifest.json" || exit
fi
ARTIFACT_CANDIDATE=$(mktemp /var/tmp/vguide-cap16-artifact.XXXXXX)
run_python_script "$SCRIPT_DIR/baseline.py" artifact-manifest \
  --root "$OUTPUT_DIR" \
  --output "$ARTIFACT_CANDIDATE"
mv "$ARTIFACT_CANDIDATE" "$ARTIFACT_MANIFEST" || exit
trap - EXIT
write_atomic complete "$OUTPUT_DIR/summary/.complete" || exit
