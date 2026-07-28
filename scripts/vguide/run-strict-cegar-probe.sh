#!/usr/bin/env bash

# This file is part of CPAchecker,
# a tool for configurable software verification:
# https://cpachecker.sosy-lab.org
#
# SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>
#
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

if [[ $# -ne 6 || $1 != cap8 && $1 != cap16 ]]; then
  echo "internal usage: run through run-cap8-cegar-probe.sh or run-cap16-cegar-probe.sh" >&2
  exit 2
fi

PROBE_COHORT=$1
shift
CPACHECKER_DIR=$(realpath "$1")
SV_BENCHMARKS_DIR=$(realpath "$2")
BENCHEXEC_DIR=$(realpath "$3")
FORMAL_OUTPUT=$(realpath "$4")
OUTPUT_DIR=$(realpath -m "$5")
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$SCRIPT_DIR/run-stock-formal-dataset.sh"

FORMAL_MODE="$PROBE_COHORT-probe"
if [[ $PROBE_COHORT == cap8 ]]; then
  FORMAL_HOST=valkyrie
else
  FORMAL_HOST=athena
fi
P_CORES=0,2,4,6,8,10,12,14
RESEARCH_ROOT=$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)
EXPECTED_CPACHECKER=a80db518765174c582e2574eee1f527eff18c910
EXPECTED_SV_BENCHMARKS=9cf9198156e4c8a6c517e474770158e1bb0b566d
EXPECTED_BENCHEXEC=edb95ed3a8478366b8bb89f8cdd1d9a6c5fa8c84
EXPECTED_JDK=867ff62e01a0936fc0a90ceae27338be1973559767ef0717896f8d64f780ece6
EXPECTED_STOCK_LIB_JAVA=eea0df062de5c8e3febe0d96b583741c140e79d3ae41a87a56d7be365b876f9d
EXPECTED_CPACHECKER_JAR_CONTENT=34953059634f4a708ef0fc9f9bd288d6d4f0172c980b95033fd8d75229535a69
EXPECTED_ANT_INSTALL=52772e241e78a875fa00dea891eac2023d4f2be639a5f28a17dca81580f75e5b
EXPECTED_ANT_VERSION="Apache Ant(TM) version 1.10.12 compiled on January 17 1970"
if [[ $PROBE_COHORT == cap8 ]]; then
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
else
  EXPECTED_PYTHON_REAL=/usr/bin/python3.12
  EXPECTED_PYTHON_SHA256=1643dacd9feaedc58f3cc581e4d22577dfe25c09b10282936186ccf0f2e61118
  EXPECTED_PYTHON_VERSION="Python 3.12.3"
  EXPECTED_PYTHON_STDLIB=/usr/lib/python3.12
  EXPECTED_PYTHON_STDLIB_DIGEST=a3940bab942bcff9bf32ed7b81f7f71e0cd506166aec5c156c5058bf4f337d16
  EXPECTED_PYTHON_DIST_PACKAGES=/usr/lib/python3/dist-packages
  EXPECTED_PYTHON_DIST_PACKAGES_DIGEST=c7831aae147cc850f67958d070d122bf9e3c72c31a090fd497ff50177b84d189
  EXPECTED_PYTHON_LOCAL_DIST_PACKAGES=/usr/local/lib/python3.12/dist-packages
  EXPECTED_PYTHON_LOCAL_DIST_PACKAGES_DIGEST=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
  EXPECTED_PYTHON_SYSTEM_PATH=/usr/lib/python312.zip:/usr/lib/python3.12:/usr/lib/python3.12/lib-dynload:/usr/local/lib/python3.12/dist-packages:/usr/lib/python3/dist-packages
  EXPECTED_PYYAML_FILE=/usr/lib/python3/dist-packages/yaml/__init__.py
  EXPECTED_PYYAML_VERSION=6.0.1
fi
EXPECTED_BENCHEXEC_ARCHIVE=75e3332253429e6f9186352a255cd96c0aff6154a95e2fdd3b737c143ba018bc
EXPECTED_BENCHEXEC_VERSION="benchexec 3.35-dev"
PACKAGE_COMMAND="package-$PROBE_COHORT-probe-input"
VALIDATE_INPUT_COMMAND="validate-$PROBE_COHORT-probe-input"
RENDER_COMMAND="render-$PROBE_COHORT-probe"
RENDER_REPLACEMENT_COMMAND="render-$PROBE_COHORT-probe-replacement"
TAINT_COMMAND="$PROBE_COHORT-probe-taint"
PLAN_COMMAND="$PROBE_COHORT-probe-plan"
SUMMARY_COMMAND="$PROBE_COHORT-probe-summary"
CLOSURE_COMMAND="validate-$PROBE_COHORT-probe-closure"
AUTH_FORMAL_COMMAND="authenticate-$PROBE_COHORT-formal-for-probe"
PROBE_MANIFEST_NAME="candidate-manifest-$PROBE_COHORT-probe.json"
PROBE_RUN_PREFIX="hard-case-dataset-v2-$PROBE_COHORT-cegar-probe-$FORMAL_HOST"
P_CORE_LOCK="/var/tmp/vguide-$FORMAL_HOST-pcores.lock"

[[ $(hostname -s) == "$FORMAL_HOST" ]] || {
  echo "strict CEGAR probe host mismatch; refusing host: $(hostname -s)" >&2
  exit 1
}
if env | grep -Eq '^(VGUIDE_|DEEPSEEK_API_KEY=|OPENAI_API_KEY=)'; then
  echo "LLM credentials and VGuide environment are forbidden" >&2
  exit 1
fi

JAVA_HOME=$(realpath "${JAVA_HOME:?JAVA_HOME must point to the pinned JDK 21}")
ANT_HOME=$(realpath "${ANT_HOME:?ANT_HOME must point to the pinned Ant}")
ANT_INSTALL=$(realpath "$ANT_HOME/../..")
ANT_BIN="$ANT_HOME/bin/ant"
PYTHON_STDLIB=$(realpath "$EXPECTED_PYTHON_STDLIB")
PYTHON_DIST_PACKAGES=$(realpath "$EXPECTED_PYTHON_DIST_PACKAGES")
PYTHON_LOCAL_DIST_PACKAGES=$(realpath "$EXPECTED_PYTHON_LOCAL_DIST_PACKAGES")

require_clean_repo "$RESEARCH_ROOT" research
require_clean_repo "$CPACHECKER_DIR" "Phase-C CPAchecker runtime"
require_clean_repo "$SV_BENCHMARKS_DIR" SV-Benchmarks true
require_clean_repo "$BENCHEXEC_DIR" BenchExec
reject_output_overlap \
  "$OUTPUT_DIR" "$RESEARCH_ROOT" "$CPACHECKER_DIR" "$SV_BENCHMARKS_DIR" \
  "$BENCHEXEC_DIR" "$FORMAL_OUTPUT" "$JAVA_HOME" "$ANT_INSTALL"

run_python_script "$SCRIPT_DIR/dataset.py" "$AUTH_FORMAL_COMMAND" \
  --formal-output "$FORMAL_OUTPUT" \
  --sv-benchmarks "$SV_BENCHMARKS_DIR"

exec 9>"$P_CORE_LOCK"
flock -n 9 || {
  echo "another VGuide run holds the $FORMAL_HOST P-core lock" >&2
  exit 1
}

RESUMING=false
if [[ -e "$OUTPUT_DIR" ]] &&
  [[ -n $(find "$OUTPUT_DIR" -mindepth 1 -print -quit) ]]; then
  RESUMING=true
fi
if [[ "$RESUMING" == false ]]; then
  mkdir -p "$OUTPUT_DIR/input" "$OUTPUT_DIR/generated" \
    "$OUTPUT_DIR/results" "$OUTPUT_DIR/provenance/attempts"
  run_python_script "$SCRIPT_DIR/dataset.py" "$PACKAGE_COMMAND" \
    --formal-output "$FORMAL_OUTPUT" \
    --sv-benchmarks "$SV_BENCHMARKS_DIR" \
    --output-dir "$OUTPUT_DIR/input/formal"
  capture_research_provenance "$OUTPUT_DIR/input/research"
elif [[ ! -d "$OUTPUT_DIR/input/formal" ||
  ! -d "$OUTPUT_DIR/input/research" ]]; then
  echo "existing probe output lacks authenticated saved input" >&2
  exit 1
fi

activate_saved_scripts "$OUTPUT_DIR/input/research"
verify_research_provenance "$OUTPUT_DIR/input/research"
run_python_script "$DATASET_PY" "$VALIDATE_INPUT_COMMAND" \
  --probe-input "$OUTPUT_DIR/input/formal" \
  --sv-benchmarks "$SV_BENCHMARKS_DIR"
if [[ "$RESUMING" == true ]]; then
  EXPECTED_INPUT=$(mktemp -d /var/tmp/vguide-$PROBE_COHORT-probe-input.XXXXXX)
  trap 'rm -rf -- "$EXPECTED_INPUT"' EXIT
  run_python_script "$DATASET_PY" "$PACKAGE_COMMAND" \
    --formal-output "$FORMAL_OUTPUT" \
    --sv-benchmarks "$SV_BENCHMARKS_DIR" \
    --output-dir "$EXPECTED_INPUT"
  diff -r -- "$EXPECTED_INPUT" "$OUTPUT_DIR/input/formal"
  rm -rf -- "$EXPECTED_INPUT"
  trap - EXIT
fi
PROBE_MANIFEST="$OUTPUT_DIR/input/formal/$PROBE_MANIFEST_NAME"

if [[ -e "$OUTPUT_DIR/summary/.complete" ||
  -L "$OUTPUT_DIR/summary/.complete" ]]; then
  run_python_script "$DATASET_PY" "$CLOSURE_COMMAND" \
    --output-root "$OUTPUT_DIR" \
    --sv-benchmarks "$SV_BENCHMARKS_DIR" --require-complete
  exit 0
fi

BUILD_COMPLETED=false
MONITOR_ACTIVE=false
capture_failure() {
  local status=$?
  trap - EXIT
  if ((status != 0)); then
    set +e
    stop_process_monitor_for_teardown
    verify_research_provenance "$OUTPUT_DIR/input/research" \
      >"$OUTPUT_DIR/provenance/research-verification-failure.log" 2>&1
    if [[ "$BUILD_COMPLETED" == true ]]; then
      verify_runtime_closure true \
        >"$OUTPUT_DIR/provenance/runtime-verification-failure.log" 2>&1
    fi
    JAVA_HOME="$JAVA_HOME" run_python_script "$BASELINE_PY" machine \
      --output "$OUTPUT_DIR/provenance/machine-after-failure.json"
    run_python_script "$BASELINE_PY" artifact-manifest \
      --root "$OUTPUT_DIR" \
      --output "$OUTPUT_DIR/provenance/artifact-manifest-failure.json"
  fi
  exit "$status"
}
trap capture_failure EXIT

(
  cd "$CPACHECKER_DIR"
  taskset -c "$P_CORES" env JAVA_HOME="$JAVA_HOME" \
    PATH="$JAVA_HOME/bin:$ANT_HOME/bin:$PATH" \
    "$ANT_BIN" -Divy.disable=true clean jar
) 2>&1 | tee "$OUTPUT_DIR/provenance/build.log"
CURRENT_JAR_CONTENT=$(jar_content_digest_value "$CPACHECKER_DIR/cpachecker.jar")
[[ "$CURRENT_JAR_CONTENT" == "$EXPECTED_CPACHECKER_JAR_CONTENT" ]]
printf '%s\n' "$CURRENT_JAR_CONTENT" \
  >"$OUTPUT_DIR/provenance/cpachecker-jar-content.sha256"
BUILD_COMPLETED=true
remove_compiled_classes
assert_no_compiled_classes
verify_runtime_closure true
write_runtime_provenance "$OUTPUT_DIR/provenance/runtime-closure.txt"
record_process_snapshot "$OUTPUT_DIR/provenance"

systemd-run --user --quiet --scope --slice=benchexec -p Delegate=yes \
  taskset -c "$P_CORES" "$PYTHON_BIN" -I -c \
  'import runpy,sys; sys.dont_write_bytecode=True; sys.pycache_prefix="/dev/null"; sys.path.insert(0,sys.argv.pop(1)); sys.argv[0]="benchexec"; runpy.run_module("benchexec.check_cgroups",run_name="__main__")' \
  "$BENCHEXEC_DIR" --no-thread \
  2>&1 | tee "$OUTPUT_DIR/provenance/cgroup-check.log"
JAVA_HOME="$JAVA_HOME" run_python_script "$BASELINE_PY" machine \
  --output "$OUTPUT_DIR/provenance/machine-preflight-start.json"
sleep 10
JAVA_HOME="$JAVA_HOME" run_python_script "$BASELINE_PY" machine \
  --output "$OUTPUT_DIR/provenance/machine-preflight-end.json"
run_python_script "$BASELINE_PY" machine-check \
  --before "$OUTPUT_DIR/provenance/machine-preflight-start.json" \
  --after "$OUTPUT_DIR/provenance/machine-preflight-end.json" |
  tee "$OUTPUT_DIR/provenance/machine-preflight-check.json"

authenticate_probe_definition() {
  local allow_subdirectories=$1
  local actual=$2
  shift 2
  local expected
  local name
  local status
  local -a actual_files=()
  local -a expected_files=()
  expected=$(mktemp -d /var/tmp/vguide-$PROBE_COHORT-probe-definition.XXXXXX)
  if run_python_script "$DATASET_PY" "$@" \
    --output-dir "$expected" >/dev/null; then
    status=0
  else
    status=$?
  fi
  if ((status == 0)); then
    if [[ ! -d "$actual" || -L "$actual" ]] ||
      [[ -n $(find -P "$actual" -mindepth 1 -maxdepth 1 \
        \( -type l -o \( ! -type f ! -type d \) \) -print -quit) ]] ||
      [[ "$allow_subdirectories" == false &&
        -n $(find -P "$actual" -mindepth 1 -maxdepth 1 \
          -type d -print -quit) ]]; then
      status=1
    else
      mapfile -t expected_files < <(
        find "$expected" -maxdepth 1 -type f -printf '%f\n' | sort
      )
      mapfile -t actual_files < <(
        find "$actual" -maxdepth 1 -type f -printf '%f\n' | sort
      )
      if [[ "${expected_files[*]}" != "${actual_files[*]}" ]]; then
        status=1
      else
        for name in "${expected_files[@]}"; do
          if cmp -- "$expected/$name" "$actual/$name"; then
            :
          else
            status=$?
            break
          fi
        done
      fi
    fi
  fi
  rm -rf -- "$expected"
  return "$status"
}

if [[ ! -f "$OUTPUT_DIR/generated/cegar-eligibility.xml" ]]; then
  run_python_script "$DATASET_PY" "$RENDER_COMMAND" \
    --probe-input "$OUTPUT_DIR/input/formal" \
    --sv-benchmarks "$SV_BENCHMARKS_DIR" \
    --property-file "$SV_BENCHMARKS_DIR/c/properties/unreach-call.prp" \
    --output-dir "$OUTPUT_DIR/generated"
fi
authenticate_probe_definition true "$OUTPUT_DIR/generated" "$RENDER_COMMAND" \
  --probe-input "$OUTPUT_DIR/input/formal" \
  --sv-benchmarks "$SV_BENCHMARKS_DIR" \
  --property-file "$SV_BENCHMARKS_DIR/c/properties/unreach-call.prp"

single_probe_result() {
  local directory=$1
  local matches=()
  mapfile -t matches < <(
    find "$directory" -maxdepth 1 -type f \
      \( -name '*.results.cegar-eligibility.official.xml' \
      -o -name '*.results.cegar-eligibility.official.xml.bz2' \) -print
  )
  if [[ ${#matches[@]} -ne 1 ]]; then
    echo "expected one official probe result in $directory" >&2
    return 1
  fi
  printf '%s\n' "${matches[0]}"
}

capture_attempt_machine_evidence() {
  local before=$1
  local after=$2
  local check=$3
  local after_tmp
  local check_tmp
  for target in "$after" "$check"; do
    if [[ -L "$target" || -e "$target" && ! -f "$target" ]]; then
      echo "probe machine evidence is not regular: $target" >&2
      return 1
    fi
  done
  if [[ ! -e "$after" ]]; then
    after_tmp=$(mktemp "$after.tmp.XXXXXX")
    if ! JAVA_HOME="$JAVA_HOME" run_python_script "$BASELINE_PY" machine \
      --output "$after_tmp"; then
      rm -f -- "$after_tmp"
      return 1
    fi
    mv -- "$after_tmp" "$after"
  fi
  if [[ ! -e "$check" ]]; then
    check_tmp=$(mktemp "$check.tmp.XXXXXX")
    if ! run_python_script "$BASELINE_PY" machine-check \
      --before "$before" --after "$after" >"$check_tmp"; then
      rm -f -- "$check_tmp"
      return 1
    fi
    mv -- "$check_tmp" "$check"
    cat "$check"
  fi
}

run_probe_attempt() {
  local label=$1
  local role=$2
  local definition=$3
  local output=$4
  local name="$PROBE_RUN_PREFIX-$label"
  local marker="$OUTPUT_DIR/provenance/attempts/$label.json"
  local descriptor="$OUTPUT_DIR/provenance/$label-process-descriptor.json"
  local process="$OUTPUT_DIR/provenance/$label-benchexec.process.json"
  local monitor="$OUTPUT_DIR/provenance/$label-load-monitor.jsonl"
  local result
  local status
  local unit
  local -a evidence=(
    --output-root "$OUTPUT_DIR" --manifest "$PROBE_MANIFEST"
    --sv-benchmarks "$SV_BENCHMARKS_DIR" --host "$FORMAL_HOST"
    --mode "$FORMAL_MODE" --label "$label" --role "$role" --repetition 1
    --definition "$definition"
    --benchexec-log "$OUTPUT_DIR/provenance/$label-benchexec.log"
    --benchexec-process "$process" --process-descriptor "$descriptor"
    --load-monitor "$monitor" --monitor-pid "$monitor.pid"
    --monitor-process "$monitor.process.json"
    --monitor-stopped "$monitor.stopped"
    --machine-before "$OUTPUT_DIR/provenance/machine-before-$label.json"
    --machine-after "$OUTPUT_DIR/provenance/machine-after-$label.json"
    --machine-check "$OUTPUT_DIR/provenance/machine-check-$label.json"
    --output "$marker"
  )
  mkdir -p "$output"
  if [[ -f "$marker" ]]; then
    result=$(single_probe_result "$output")
    status=$("$PYTHON_BIN" -I -c \
      'import json,sys; print(json.load(open(sys.argv[1]))["benchexec_exit"])' \
      "$marker")
    run_python_script "$DATASET_PY" formal-attempt-complete \
      "${evidence[@]}" --benchexec-exit "$status" --result "$result" >/dev/null
    return
  fi
  if [[ -n $(find "$output" -mindepth 1 -print -quit) ||
    -e "$monitor.process.json" || -e "$process" || -e "$descriptor" ]]; then
    local before="$OUTPUT_DIR/provenance/machine-before-$label.json"
    local after="$OUTPUT_DIR/provenance/machine-after-$label.json"
    local check="$OUTPUT_DIR/provenance/machine-check-$label.json"
    local log="$OUTPUT_DIR/provenance/$label-benchexec.log"
    for required in "$descriptor" "$monitor.process.json" "$monitor.pid" \
      "$monitor" "$process" "$before" "$log"; do
      if [[ -L "$required" || ! -f "$required" ]]; then
        echo "unclosed probe attempt lacks regular evidence: $required" >&2
        return 1
      fi
    done
    result=$(single_probe_result "$output")
    run_python_script "$DATASET_PY" require-formal-process-gone \
      --descriptor "$descriptor" --identity "$monitor.process.json" \
      --output-root "$OUTPUT_DIR" --mode "$FORMAL_MODE" --label "$label" \
      --host "$FORMAL_HOST" --role load-monitor
    run_python_script "$DATASET_PY" require-formal-process-gone \
      --descriptor "$descriptor" --identity "$process" \
      --output-root "$OUTPUT_DIR" --mode "$FORMAL_MODE" --label "$label" \
      --host "$FORMAL_HOST" --role benchexec-launcher
    local recovery_exit=125
    if [[ -L "$monitor.stopped" ]]; then
      echo "unclosed probe monitor stop evidence is a symlink" >&2
      return 1
    elif [[ -e "$monitor.stopped" && ! -f "$monitor.stopped" ]]; then
      echo "unclosed probe monitor stop evidence is not regular" >&2
      return 1
    elif [[ ! -e "$monitor.stopped" ]]; then
      local samples
      local recovered_stop
      samples=$(($(wc -l <"$monitor") - 1))
      [[ "$samples" -gt 0 ]]
      recovered_stop=$(mktemp "$monitor.stopped.tmp.XXXXXX")
      if ! printf 'pid=%s\nexit=unobserved\nsamples=%s\nrecovery=authenticated-process-gone\n' \
        "$(cat "$monitor.pid")" "$samples" >"$recovered_stop"; then
        rm -f -- "$recovered_stop"
        return 1
      fi
      mv -- "$recovered_stop" "$monitor.stopped"
    fi
    capture_attempt_machine_evidence "$before" "$after" "$check"
    run_python_script "$DATASET_PY" formal-attempt-complete \
      "${evidence[@]}" --benchexec-exit "$recovery_exit" --result "$result"
    return
  fi
  run_python_script "$DATASET_PY" write-formal-process-descriptor \
    --output-root "$OUTPUT_DIR" --mode "$FORMAL_MODE" --label "$label" \
    --host "$FORMAL_HOST" --name "$name" --definition "$definition" \
    --result-output "$output" --monitor-output "$monitor" \
    --monitor-exclude-root "$$" --dataset-py "$DATASET_PY" \
    --cpachecker-dir "$CPACHECKER_DIR" --benchexec-dir "$BENCHEXEC_DIR" \
    --python-bin "$PYTHON_BIN" --java-home "$JAVA_HOME" \
    --p-cores "$P_CORES" --output "$descriptor"
  unit=$(run_python_script "$DATASET_PY" formal-systemd-unit \
    --output-root "$OUTPUT_DIR" --mode "$FORMAL_MODE" --label "$label")
  JAVA_HOME="$JAVA_HOME" run_python_script "$BASELINE_PY" machine \
    --output "$OUTPUT_DIR/provenance/machine-before-$label.json"
  start_process_monitor "$monitor"
  wait_for_process_monitor
  set +e
  (
    cd "$CPACHECKER_DIR"
    "$PYTHON_BIN" -I - "$process" "$unit" \
      systemd-run --user --quiet --scope --unit="$unit" \
      --slice=benchexec -p Delegate=yes \
      taskset -c "$P_CORES" env -i \
      HOME=/home/benchexec LANG=C.UTF-8 LC_ALL=C.UTF-8 PATH=/usr/bin:/bin \
      JAVA="$JAVA_HOME/bin/java" \
      "$PYTHON_BIN" -I -c "$BENCHEXEC_MODULE_COMMAND" "$BENCHEXEC_DIR" \
      --name "$name" --tool-directory "$CPACHECKER_DIR" \
      --outputpath "$output/" --allowedCores "$P_CORES" \
      --no-hyperthreading --container --read-only-dir / --hidden-dir /home \
      --overlay-dir "$CPACHECKER_DIR" -N 8 -c 1 "$definition" <<'PY'
import json
import os
import sys
from pathlib import Path

output, unit, *argv = sys.argv[1:]
proc = Path("/proc/self")
status = proc.joinpath("status").read_text()
uid = int(next(line for line in status.splitlines() if line.startswith("Uid:")).split()[1])
stat = proc.joinpath("stat").read_text()
identity = {
    "schema_version": "formal-owned-process-identity-v1",
    "role": "benchexec-launcher",
    "uid": uid,
    "pid": os.getpid(),
    "proc_starttime": int(stat[stat.rfind(")") + 2:].split()[19]),
    "argv": argv,
    "systemd_unit": unit,
}
Path(output).write_text(json.dumps(identity, indent=2) + "\n")
os.execvp(argv[0], argv)
PY
  ) 2>&1 | tee "$OUTPUT_DIR/provenance/$label-benchexec.log"
  status=${PIPESTATUS[0]}
  set -e
  stop_process_monitor
  capture_attempt_machine_evidence \
    "$OUTPUT_DIR/provenance/machine-before-$label.json" \
    "$OUTPUT_DIR/provenance/machine-after-$label.json" \
    "$OUTPUT_DIR/provenance/machine-check-$label.json"
  [[ "$status" -eq 0 || "$status" -eq 130 ]]
  result=$(single_probe_result "$output")
  run_python_script "$DATASET_PY" formal-attempt-complete \
    "${evidence[@]}" --benchexec-exit "$status" --result "$result"
}

authenticate_probe_taint() {
  local output=$1
  local result=$2
  local log=$3
  local monitor=$4
  local temporary
  local expected
  temporary=$(mktemp -d /var/tmp/vguide-$PROBE_COHORT-probe-taint.XXXXXX)
  expected="$temporary/taint.json"
  if ! run_python_script "$DATASET_PY" "$TAINT_COMMAND" \
    --manifest "$PROBE_MANIFEST" --result "$result" \
    --benchexec-log "$log" --load-monitor "$monitor" \
    --output "$expected"; then
    rm -rf -- "$temporary"
    return 1
  fi
  if [[ -L "$output" ]]; then
    rm -rf -- "$temporary"
    echo "probe taint evidence is a symlink: $output" >&2
    return 1
  elif [[ -e "$output" ]]; then
    if cmp -- "$expected" "$output"; then
      rm -rf -- "$temporary"
    else
      rm -rf -- "$temporary"
      return 1
    fi
  else
    mv -- "$expected" "$output"
    rmdir -- "$temporary"
  fi
}

primary_label=repetition-1
primary_output="$OUTPUT_DIR/results/$primary_label"
run_probe_attempt "$primary_label" primary \
  "$OUTPUT_DIR/generated/cegar-eligibility.xml" "$primary_output"
primary=$(single_probe_result "$primary_output")
primary_taint="$OUTPUT_DIR/$primary_label-taint.json"
authenticate_probe_taint "$primary_taint" "$primary" \
  "$OUTPUT_DIR/provenance/$primary_label-benchexec.log" \
  "$OUTPUT_DIR/provenance/$primary_label-load-monitor.jsonl"

current_result=$primary
current_taint=$primary_taint
replacement_args=()
attempt=1
while [[ $("$PYTHON_BIN" -I -c \
  'import json,sys; print(len(json.load(open(sys.argv[1]))["tasks"]))' \
  "$current_taint") -gt 0 ]]; do
  label="$primary_label-replacement-attempt-$attempt"
  definition_dir="$OUTPUT_DIR/generated/$label"
  definition="$definition_dir/cegar-eligibility.xml"
  if [[ ! -f "$definition" ]]; then
    run_python_script "$DATASET_PY" "$RENDER_REPLACEMENT_COMMAND" \
      --probe-input "$OUTPUT_DIR/input/formal" \
      --sv-benchmarks "$SV_BENCHMARKS_DIR" \
      --primary-result "$current_result" --taint-manifest "$current_taint" \
      --property-file "$SV_BENCHMARKS_DIR/c/properties/unreach-call.prp" \
      --output-dir "$definition_dir"
  fi
  authenticate_probe_definition false "$definition_dir" \
    "$RENDER_REPLACEMENT_COMMAND" \
    --probe-input "$OUTPUT_DIR/input/formal" \
    --sv-benchmarks "$SV_BENCHMARKS_DIR" \
    --primary-result "$current_result" --taint-manifest "$current_taint" \
    --property-file "$SV_BENCHMARKS_DIR/c/properties/unreach-call.prp"
  attempt_output="$OUTPUT_DIR/results/$label"
  run_probe_attempt "$label" replacement "$definition" "$attempt_output"
  replacement=$(single_probe_result "$attempt_output")
  replacement_taint="$OUTPUT_DIR/$label-taint.json"
  authenticate_probe_taint "$replacement_taint" "$replacement" \
    "$OUTPUT_DIR/provenance/$label-benchexec.log" \
    "$OUTPUT_DIR/provenance/$label-load-monitor.jsonl"
  replacement_args+=(
    --replacement-result "$replacement"
    --replacement-definition "$definition"
    --replacement-taint-manifest "$replacement_taint"
  )
  current_result=$replacement
  current_taint=$replacement_taint
  attempt=$((attempt + 1))
done

if [[ ! -f "$OUTPUT_DIR/probe-plan.json" ]]; then
  plan_args=(
    --manifest "$PROBE_MANIFEST" --primary-result "$primary"
    --output "$OUTPUT_DIR/probe-plan.json"
  )
  if [[ $("$PYTHON_BIN" -I -c \
    'import json,sys; print(len(json.load(open(sys.argv[1]))["tasks"]))' \
    "$primary_taint") -gt 0 ]]; then
    plan_args+=(--taint-manifest "$primary_taint" "${replacement_args[@]}")
  fi
  run_python_script "$DATASET_PY" "$PLAN_COMMAND" "${plan_args[@]}"
fi

SUMMARY_STAGE="$OUTPUT_DIR/summary.staging"
rm -rf -- "$SUMMARY_STAGE"
run_python_script "$DATASET_PY" "$SUMMARY_COMMAND" \
  --probe-input "$OUTPUT_DIR/input/formal" \
  --sv-benchmarks "$SV_BENCHMARKS_DIR" \
  --benchmark-definition "$OUTPUT_DIR/generated/cegar-eligibility.xml" \
  --probe-plan "$OUTPUT_DIR/probe-plan.json" --output-dir "$SUMMARY_STAGE"
rm -rf -- "$OUTPUT_DIR/summary"
mv -- "$SUMMARY_STAGE" "$OUTPUT_DIR/summary"

verify_research_provenance "$OUTPUT_DIR/input/research" \
  >"$OUTPUT_DIR/provenance/research-verification-final.log" 2>&1
verify_runtime_closure true \
  >"$OUTPUT_DIR/provenance/runtime-verification-final.log" 2>&1
run_python_script "$BASELINE_PY" artifact-manifest \
  --root "$OUTPUT_DIR" \
  --output "$OUTPUT_DIR/provenance/artifact-manifest.json"
run_python_script "$DATASET_PY" "$CLOSURE_COMMAND" \
  --output-root "$OUTPUT_DIR" --sv-benchmarks "$SV_BENCHMARKS_DIR"
run_python_script "$DATASET_PY" write-complete-sentinel \
  --output "$OUTPUT_DIR/summary/.complete"
run_python_script "$DATASET_PY" "$CLOSURE_COMMAND" \
  --output-root "$OUTPUT_DIR" \
  --sv-benchmarks "$SV_BENCHMARKS_DIR" --require-complete
trap - EXIT
