#!/usr/bin/env bash

# This file is part of CPAchecker,
# a tool for configurable software verification:
# https://cpachecker.sosy-lab.org
#
# SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>
#
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

PYTHON_BIN=$(realpath /usr/bin/python3)

run_python_script() {
  "$PYTHON_BIN" -I -c '
import runpy
import sys
from pathlib import Path

script = Path(sys.argv.pop(1)).resolve()
sys.argv[0] = str(script)
sys.dont_write_bytecode = True
sys.pycache_prefix = "/dev/null"
sys.path.insert(0, str(script.parent))
runpy.run_path(str(script), run_name="__main__")
' "$@"
}

require_clean_repo() {
  local repository=$1
  local label=$2
  local allow_missing_skip=${3:-false}
  local index_flags
  git -C "$repository" rev-parse --is-inside-work-tree >/dev/null
  index_flags=$(git -C "$repository" ls-files -v)
  if grep -Eq '^[a-z] ' <<<"$index_flags"; then
    echo "$label checkout has assume-unchanged index entries: $repository" >&2
    return 1
  fi
  if [[ -n $(git -C "$repository" status --porcelain=v1 --untracked-files=all) ]] ||
    ! git -C "$repository" diff --quiet HEAD --; then
    echo "$label checkout is not clean: $repository" >&2
    return 1
  fi
  "$PYTHON_BIN" -I - "$repository" "$label" "$allow_missing_skip" <<'PY'
import os
import stat
import subprocess
import sys
from pathlib import Path

root = Path(sys.argv[1])
allow_missing = sys.argv[3] == "true"
index = {}
for record in subprocess.check_output(
    ["git", "-C", str(root), "ls-files", "-s", "-z"]
).decode("utf-8", "surrogateescape").split("\0"):
  if record:
    metadata, relative = record.split("\t", 1)
    mode, oid, stage = metadata.split()
    if stage == "0":
      index[relative] = (mode, oid)
head = {}
for record in subprocess.check_output(
    ["git", "-C", str(root), "ls-tree", "-r", "-z", "HEAD"]
).decode("utf-8", "surrogateescape").split("\0"):
  if record:
    metadata, relative = record.split("\t", 1)
    mode, _, oid = metadata.split()
    head[relative] = (mode, oid)
for record in subprocess.check_output(
    ["git", "-C", str(root), "ls-files", "-v", "-z"]
).decode("utf-8", "surrogateescape").split("\0"):
  if not record or record[0] != "S":
    continue
  relative = record[2:]
  path = root / relative
  mode, oid = index[relative]
  if head.get(relative) != (mode, oid):
    raise SystemExit(f"{sys.argv[2]} skip-worktree index differs from HEAD: {relative}")
  if not os.path.lexists(path):
    if allow_missing:
      continue
    raise SystemExit(
        f"{sys.argv[2]} checkout has missing skip-worktree entry: {relative}"
    )
  actual_mode = path.lstat().st_mode
  if mode == "120000" and stat.S_ISLNK(actual_mode):
    content = os.readlink(path).encode("utf-8", "surrogateescape")
  elif mode in {"100644", "100755"} and stat.S_ISREG(actual_mode):
    if bool(actual_mode & stat.S_IXUSR) != (mode == "100755"):
      raise SystemExit(
          f"{sys.argv[2]} checkout has changed skip-worktree mode: {relative}"
      )
    content = path.read_bytes()
  else:
    raise SystemExit(
        f"{sys.argv[2]} checkout has changed skip-worktree node type: {relative}"
    )
  expected = subprocess.check_output(
      ["git", "-C", str(root), "cat-file", "blob", oid]
  )
  if content != expected:
    raise SystemExit(
        f"{sys.argv[2]} checkout has changed materialized skip-worktree file: {relative}"
    )
PY
}

validate_formal_package_topology() {
  local package=$1
  local actual
  local expected
  actual=$(find -P "$package" -mindepth 1 -printf '%y %P\n' | sort)
  expected=$(
    printf '%s\n' \
      "d corpus" \
      "d corpus/properties" \
      "f artifact-manifest.json" \
      "f candidate-manifest-valkyrie-formal.json" \
      "f corpus/properties/unreach-call.prp"
  )
  if [[ "$actual" != "$expected" ]]; then
    echo "formal package node topology is not frozen" >&2
    return 1
  fi
}

path_is_within() {
  local child
  local parent
  child=$(realpath -m "$1")
  parent=$(realpath -m "$2")
  [[ "$child" == "$parent" || "$child" == "$parent/"* ]]
}

reject_output_overlap() {
  local output
  local input
  local input_tree
  output=$(realpath -m "$1")
  shift
  for input in "$@"; do
    input=$(realpath "$input")
    if [[ -d "$input" ]]; then
      input_tree=$input
    else
      input_tree=$(dirname "$input")
    fi
    if path_is_within "$output" "$input_tree"; then
      echo "output overlaps input tree: $output within $input_tree" >&2
      return 1
    fi
    if path_is_within "$input" "$output"; then
      echo "input overlaps output tree: $input within $output" >&2
      return 1
    fi
  done
}

result_copy_name() {
  local role=$1
  local source=$2
  if [[ "$source" == *.bz2 ]]; then
    printf '%s-result.xml.bz2\n' "$role"
  else
    printf '%s-result.xml\n' "$role"
  fi
}

copy_phase_evidence() {
  local evidence_dir=$1
  local roles=(original reroute recovery)
  local property_path
  local role
  local index
  local result_name
  mkdir -p "$evidence_dir/corpus/properties"
  cp -- "$PARENT_MANIFEST" "$evidence_dir/parent-manifest.json"
  property_path=$("$PYTHON_BIN" -I - "$PARENT_MANIFEST" <<'PY'
import json
import sys

manifest = json.load(open(sys.argv[1], encoding="utf-8"))
files = manifest.get("corpus_files")
expected = None
if isinstance(files, list) and len(files) == 1:
  expected = [{
      "path": "corpus/properties/unreach-call.prp",
      "sha256": files[0]["sha256"],
  }]
if files != expected:
  raise SystemExit("parent manifest does not declare exactly the frozen corpus property")
print(files[0]["path"])
PY
)
  cp -- "$(dirname "$PARENT_MANIFEST")/$property_path" \
    "$evidence_dir/corpus/properties/unreach-call.prp"

  COPIED_PARENT="$evidence_dir/parent-manifest.json"
  COPIED_MANIFESTS=()
  COPIED_RESULTS=()
  COPIED_SURVIVORS=()
  for index in "${!roles[@]}"; do
    role=${roles[$index]}
    result_name=$(result_copy_name "$role" "${PHASE_RESULTS[$index]}")
    cp -- "${PHASE_MANIFESTS[$index]}" "$evidence_dir/$role-manifest.json"
    cp -- "${PHASE_RESULTS[$index]}" "$evidence_dir/$result_name"
    cp -- "${PHASE_SURVIVORS[$index]}" "$evidence_dir/$role-survivor.json"
    COPIED_MANIFESTS+=("$evidence_dir/$role-manifest.json")
    COPIED_RESULTS+=("$evidence_dir/$result_name")
    COPIED_SURVIVORS+=("$evidence_dir/$role-survivor.json")
  done
  (
    cd "$evidence_dir"
    find . -type f ! -name inventory.sha256 -printf '%P\n' |
      sort |
      xargs sha256sum >inventory.sha256
  )
}

capture_research_provenance() {
  local destination=$1
  local head
  local status_hash
  local diff_hash
  mkdir -p "$destination/scripts"
  cp -- "$SCRIPT_DIR/run-stock-formal-dataset.sh" \
    "$destination/scripts/run-stock-formal-dataset.sh"
  cp -- "$SCRIPT_DIR/dataset.py" "$destination/scripts/dataset.py"
  cp -- "$SCRIPT_DIR/baseline.py" "$destination/scripts/baseline.py"
  git -C "$RESEARCH_ROOT" rev-parse HEAD >"$destination/research-head.txt"
  git -C "$RESEARCH_ROOT" status --porcelain=v1 \
    >"$destination/research-status.porcelain"
  git -C "$RESEARCH_ROOT" diff --binary HEAD >"$destination/research-diff.patch"
  git -C "$RESEARCH_ROOT" ls-files -v >"$destination/research-index-flags.txt"
  if [[ -s "$destination/research-status.porcelain" ||
    -s "$destination/research-diff.patch" ]]; then
    echo "research checkout changed while provenance was captured" >&2
    return 1
  fi
  head=$(cat "$destination/research-head.txt")
  status_hash=$(sha256sum "$destination/research-status.porcelain" | cut -d' ' -f1)
  diff_hash=$(sha256sum "$destination/research-diff.patch" | cut -d' ' -f1)
  printf '{\n  "head": "%s",\n  "clean": true,\n  "status_sha256": "%s",\n  "diff_sha256": "%s"\n}\n' \
    "$head" "$status_hash" "$diff_hash" >"$destination/research-state.json"
  (
    cd "$destination"
    find . -type f ! -name inventory.sha256 -printf '%P\n' |
      sort |
      xargs sha256sum >inventory.sha256
  )
}

activate_saved_scripts() {
  local destination=$1
  DATASET_PY="$destination/scripts/dataset.py"
  BASELINE_PY="$destination/scripts/baseline.py"
  [[ -x "$DATASET_PY" && -x "$BASELINE_PY" ]]
}

verify_research_provenance() {
  local destination=$1
  require_clean_repo "$RESEARCH_ROOT" "research"
  [[ $(git -C "$RESEARCH_ROOT" rev-parse HEAD) == \
    "$(cat "$destination/research-head.txt")" ]]
  cmp -- "$SCRIPT_DIR/run-stock-formal-dataset.sh" \
    "$destination/scripts/run-stock-formal-dataset.sh"
  cmp -- "$SCRIPT_DIR/dataset.py" "$destination/scripts/dataset.py"
  cmp -- "$SCRIPT_DIR/baseline.py" "$destination/scripts/baseline.py"
  (
    cd "$destination"
    sha256sum --check --strict inventory.sha256
  )
}

directory_digest_value() {
  run_python_script "${BASELINE_PY:-$SCRIPT_DIR/baseline.py}" \
    directory-digest --root "$1" |
    "$PYTHON_BIN" -I -c 'import json,sys; print(json.load(sys.stdin)["sha256"])'
}

jar_content_digest_value() {
  run_python_script "${BASELINE_PY:-$SCRIPT_DIR/baseline.py}" \
    jar-content-digest --jar "$1" |
    "$PYTHON_BIN" -I -c 'import json,sys; print(json.load(sys.stdin)["sha256"])'
}

remove_compiled_classes() {
  local classes="$CPACHECKER_DIR/classes"
  if [[ -e "$classes" || -L "$classes" ]]; then
    find -P "$classes" -depth -delete
  fi
}

assert_no_compiled_classes() {
  if [[ -e "$CPACHECKER_DIR/classes" || -L "$CPACHECKER_DIR/classes" ]]; then
    echo "stock classes tree exists and could shadow the pinned JAR" >&2
    return 1
  fi
}

benchexec_archive_digest() {
  git -C "$BENCHEXEC_DIR" archive --format=tar HEAD | sha256sum | cut -d' ' -f1
}

python_runtime_evidence() {
  env -i HOME=/home/benchexec LANG=C.UTF-8 LC_ALL=C.UTF-8 PATH=/usr/bin:/bin \
    JAVA="$JAVA_HOME/bin/java" "$PYTHON_BIN" -I -c '
import json
import sys

sys.path.insert(0, sys.argv[1])
import yaml

print(json.dumps({
    "python_executable": sys.executable,
    "sys_path": sys.path,
    "yaml_file": yaml.__file__,
    "yaml_version": yaml.__version__,
}, sort_keys=True, separators=(",", ":")))
' "$BENCHEXEC_DIR"
}

verify_python_runtime() {
  env -i HOME=/home/benchexec LANG=C.UTF-8 LC_ALL=C.UTF-8 PATH=/usr/bin:/bin \
    JAVA="$JAVA_HOME/bin/java" "$PYTHON_BIN" -I -c '
import sys

repository, executable, system_path, yaml_file, yaml_version = sys.argv[1:]
sys.path.insert(0, repository)
import yaml

if sys.executable != executable:
  raise SystemExit(f"unexpected Python executable: {sys.executable}")
expected_path = [repository, *system_path.split(":")]
if sys.path != expected_path:
  raise SystemExit(f"unexpected isolated sys.path: {sys.path}")
if yaml.__file__ != yaml_file:
  raise SystemExit(f"unexpected yaml module: {yaml.__file__}")
if yaml.__version__ != yaml_version:
  raise SystemExit(f"unexpected yaml version: {yaml.__version__}")
' "$BENCHEXEC_DIR" "$EXPECTED_PYTHON_REAL" "$EXPECTED_PYTHON_SYSTEM_PATH" \
    "$EXPECTED_PYYAML_FILE" "$EXPECTED_PYYAML_VERSION"
}

benchexec_version() {
  "$PYTHON_BIN" -I -c '
import runpy
import sys

sys.dont_write_bytecode = True
sys.pycache_prefix = "/dev/null"
sys.path.insert(0, sys.argv.pop(1))
sys.argv[0] = "benchexec"
runpy.run_module("benchexec.benchexec", run_name="__main__")
' "$BENCHEXEC_DIR" --version
}

verify_runtime_closure() {
  local require_jar=${1:-false}
  [[ $(git -C "$CPACHECKER_DIR" rev-parse HEAD) == "$EXPECTED_CPACHECKER" ]]
  [[ $(git -C "$SV_BENCHMARKS_DIR" rev-parse HEAD) == "$EXPECTED_SV_BENCHMARKS" ]]
  [[ $(git -C "$BENCHEXEC_DIR" rev-parse HEAD) == "$EXPECTED_BENCHEXEC" ]]
  require_clean_repo "$CPACHECKER_DIR" "CPAchecker stock"
  require_clean_repo "$SV_BENCHMARKS_DIR" "SV-Benchmarks" true
  require_clean_repo "$BENCHEXEC_DIR" "BenchExec"
  [[ $(directory_digest_value "$CPACHECKER_DIR/lib/java") == \
    "$EXPECTED_STOCK_LIB_JAVA" ]]
  [[ $(directory_digest_value "$JAVA_HOME") == "$EXPECTED_JDK" ]]
  [[ $(directory_digest_value "$ANT_INSTALL") == "$EXPECTED_ANT_INSTALL" ]]
  [[ $("$ANT_BIN" -version) == "$EXPECTED_ANT_VERSION" ]]
  [[ "$PYTHON_BIN" == "$EXPECTED_PYTHON_REAL" ]]
  [[ $(sha256sum "$PYTHON_BIN" | cut -d' ' -f1) == "$EXPECTED_PYTHON_SHA256" ]]
  [[ $("$PYTHON_BIN" --version) == "$EXPECTED_PYTHON_VERSION" ]]
  [[ "$PYTHON_STDLIB" == "$EXPECTED_PYTHON_STDLIB" ]]
  [[ "$PYTHON_DIST_PACKAGES" == "$EXPECTED_PYTHON_DIST_PACKAGES" ]]
  [[ "$PYTHON_LOCAL_DIST_PACKAGES" == "$EXPECTED_PYTHON_LOCAL_DIST_PACKAGES" ]]
  [[ $(directory_digest_value "$PYTHON_STDLIB") == \
    "$EXPECTED_PYTHON_STDLIB_DIGEST" ]]
  [[ $(directory_digest_value "$PYTHON_DIST_PACKAGES") == \
    "$EXPECTED_PYTHON_DIST_PACKAGES_DIGEST" ]]
  [[ $(directory_digest_value "$PYTHON_LOCAL_DIST_PACKAGES") == \
    "$EXPECTED_PYTHON_LOCAL_DIST_PACKAGES_DIGEST" ]]
  verify_python_runtime
  [[ $(benchexec_archive_digest) == "$EXPECTED_BENCHEXEC_ARCHIVE" ]]
  [[ $(benchexec_version) == "$EXPECTED_BENCHEXEC_VERSION" ]]
  assert_no_compiled_classes
  if [[ "$require_jar" == true ]]; then
    [[ -f "$CPACHECKER_DIR/cpachecker.jar" ]]
    [[ $(jar_content_digest_value "$CPACHECKER_DIR/cpachecker.jar") == \
      "$EXPECTED_CPACHECKER_JAR_CONTENT" ]]
  fi
}

write_runtime_provenance() {
  local output=$1
  printf '%s\n' \
    "stock_lib_java_sha256=$(directory_digest_value "$CPACHECKER_DIR/lib/java")" \
    "jdk_sha256=$(directory_digest_value "$JAVA_HOME")" \
    "ant_install=$ANT_INSTALL" \
    "ant_install_sha256=$(directory_digest_value "$ANT_INSTALL")" \
    "ant_version=$("$ANT_BIN" -version)" \
    "python_real=$PYTHON_BIN" \
    "python_sha256=$(sha256sum "$PYTHON_BIN" | cut -d' ' -f1)" \
    "python_version=$("$PYTHON_BIN" --version)" \
    "python_stdlib=$PYTHON_STDLIB" \
    "python_stdlib_sha256=$(directory_digest_value "$PYTHON_STDLIB")" \
    "python_dist_packages=$PYTHON_DIST_PACKAGES" \
    "python_dist_packages_sha256=$(directory_digest_value "$PYTHON_DIST_PACKAGES")" \
    "python_local_dist_packages=$PYTHON_LOCAL_DIST_PACKAGES" \
    "python_local_dist_packages_sha256=$(directory_digest_value "$PYTHON_LOCAL_DIST_PACKAGES")" \
    "python_environment=$(python_runtime_evidence)" \
    "benchexec_archive_sha256=$(benchexec_archive_digest)" \
    "benchexec_version=$(benchexec_version)" \
    >"$output"
}

record_process_snapshot() {
  local destination=$1
  {
    printf 'timestamp=%s\n' "$(date --iso-8601=seconds)"
    printf 'load=%s\n' "$(cat /proc/loadavg)"
    ps -eLo pid,tid,psr,pcpu,comm --sort=-pcpu | sed -n '1,41p'
  } >"$destination/process-start.txt"
}

start_process_monitor() {
  local output=$1
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
' "$DATASET_PY" monitor-formal-load \
    --output "$output" --exclude-root "$$" &
  MONITOR_PID=$!
  MONITOR_ACTIVE=true
  MONITOR_OUTPUT=$output
  printf '%s\n' "$MONITOR_PID" >"$output.pid"
  for _ in {1..40}; do
    if [[ -s "$output" ]]; then
      return
    fi
    if ! kill -0 "$MONITOR_PID" 2>/dev/null; then
      echo "process monitor failed before measurement" >&2
      return 1
    fi
    sleep 0.05
  done
  echo "process monitor did not initialize before measurement" >&2
  return 1
}

stop_process_monitor() {
  local monitor_exit
  local samples
  if [[ -z ${MONITOR_PID:-} ]] || ! kill -0 "$MONITOR_PID" 2>/dev/null; then
    echo "process monitor is not alive at teardown" >&2
    return 1
  fi
  kill "$MONITOR_PID"
  if wait "$MONITOR_PID"; then
    monitor_exit=0
  else
    monitor_exit=$?
  fi
  [[ "$monitor_exit" -eq 0 ]]
  [[ -s "$MONITOR_OUTPUT" ]]
  samples=$(($(wc -l <"$MONITOR_OUTPUT") - 1))
  [[ "$samples" -gt 0 ]]
  printf 'pid=%s\nexit=%s\nsamples=%s\n' \
    "$MONITOR_PID" "$monitor_exit" "$samples" \
    >"$MONITOR_OUTPUT.stopped"
  MONITOR_ACTIVE=false
  MONITOR_PID=
  MONITOR_OUTPUT=
}

stop_process_monitor_for_teardown() {
  if [[ ${MONITOR_ACTIVE:-false} == true ]]; then
    stop_process_monitor
  fi
}

wait_for_process_monitor() {
  local samples
  local contended
  while true; do
    if ! kill -0 "$MONITOR_PID" 2>/dev/null; then
      echo "process monitor died during the prelaunch window" >&2
      return 1
    fi
    samples=$(($(wc -l <"$MONITOR_OUTPUT") - 1))
    if [[ "$samples" -ge 10 ]]; then
      contended=$("$PYTHON_BIN" -I -c \
        'import json,sys; print(any(row["contended"] for row in json.loads(open(sys.argv[1]).read().splitlines()[-1])["offenders"]))' \
        "$MONITOR_OUTPUT")
      if [[ "$contended" == False ]]; then
        return
      fi
    fi
    sleep 1
  done
}

authenticate_scope_cgroup() {
  local scope=$1
  local expected_control_group=${2:-}
  local expected_path=${3:-}
  local expected_pid=${4:-}
  local cgroup_root
  local control_group
  local path
  local unit
  if ! cgroup_root=$(realpath -e /sys/fs/cgroup) ||
    [[ $(stat -fc %T "$cgroup_root") != cgroup2fs ]]; then
    echo "unified cgroup root is unavailable" >&2
    return 1
  fi
  for _ in {1..40}; do
    if ! unit=$(systemctl --user show "$scope" --property=Id --value 2>/dev/null); then
      unit=
    fi
    if ! control_group=$(
      systemctl --user show "$scope" --property=ControlGroup --value 2>/dev/null
    ); then
      control_group=
    fi
    if [[ "$unit" == "$scope" && "$control_group" == /* ]] &&
      path=$(realpath -e "$cgroup_root$control_group" 2>/dev/null) &&
      [[ "$path" == "$cgroup_root$control_group" ]] &&
      [[ "$path" == "$cgroup_root/"* ]] &&
      [[ ${path##*/} == "$scope" ]] &&
      [[ ${path%/*} == */benchexec.slice ]] &&
      [[ $(stat -fc %T "$path") == cgroup2fs ]] &&
      [[ -r "$path/cgroup.procs" && -r "$path/cgroup.events" ]]; then
      if [[ -n "$expected_control_group" &&
        "$control_group" != "$expected_control_group" ]] ||
        [[ -n "$expected_path" && "$path" != "$expected_path" ]]; then
        echo "named scope changed its authenticated control group: $scope" >&2
        return 1
      fi
      if [[ -n "$expected_pid" ]] &&
        ! cgroup_contains_pid "$path" "$expected_pid"; then
        sleep 0.05
        continue
      fi
      AUTHENTICATED_CONTROL_GROUP=$control_group
      AUTHENTICATED_CGROUP_PATH=$path
      return
    fi
    sleep 0.05
  done
  echo "could not authenticate named scope control group: $scope" >&2
  return 1
}

load_owned_cgroup_pids() {
  local cgroup_path=$1
  local processes
  OWNED_CGROUP_PIDS=()
  if processes=$("$PYTHON_BIN" -I - "$cgroup_path" <<'PY'
import os
import stat
import sys
from pathlib import Path

root = Path(sys.argv[1])
try:
  mode = root.lstat().st_mode
  if not stat.S_ISDIR(mode) or root.is_symlink():
    raise SystemExit(f"invalid authenticated cgroup directory: {root}")
  pids = set()
  for directory, names, _ in os.walk(root, followlinks=False):
    directory = Path(directory)
    for name in names:
      child = directory / name
      child_mode = child.lstat().st_mode
      if not stat.S_ISDIR(child_mode) or child.is_symlink():
        raise SystemExit(f"invalid cgroup child directory: {child}")
    procs = directory / "cgroup.procs"
    procs_mode = procs.lstat().st_mode
    if not stat.S_ISREG(procs_mode) or procs.is_symlink():
      raise SystemExit(f"invalid cgroup.procs node: {procs}")
    for line in procs.read_text(encoding="ascii").splitlines():
      if not line.isdecimal() or int(line) <= 0:
        raise SystemExit(f"invalid PID in {procs}: {line!r}")
      pids.add(int(line))
  for pid in sorted(pids):
    print(pid)
except FileNotFoundError:
  raise SystemExit(3)
PY
  ); then
    :
  else
    local status=$?
    if [[ $status -eq 3 ]]; then
      return 3
    fi
    echo "could not enumerate authenticated cgroup: $cgroup_path" >&2
    return 1
  fi
  if [[ -n "$processes" ]]; then
    mapfile -t OWNED_CGROUP_PIDS <<<"$processes"
  fi
}

cgroup_contains_pid() {
  local cgroup_path=$1
  local expected_pid=$2
  local pid
  if [[ ! "$expected_pid" =~ ^[1-9][0-9]*$ ]] ||
    ! load_owned_cgroup_pids "$cgroup_path"; then
    return 1
  fi
  for pid in "${OWNED_CGROUP_PIDS[@]}"; do
    if [[ "$pid" == "$expected_pid" ]]; then
      return
    fi
  done
  return 1
}

owned_cgroup_is_empty() {
  local cgroup_path=$1
  local events
  local populated
  if ! events=$(cat "$cgroup_path/cgroup.events"); then
    echo "could not read authenticated cgroup events: $cgroup_path" >&2
    return 2
  fi
  populated=$(awk '$1 == "populated" { print $2 }' <<<"$events")
  if [[ "$populated" != 0 && "$populated" != 1 ]]; then
    echo "invalid populated state for authenticated cgroup: $cgroup_path" >&2
    return 2
  fi
  [[ "$populated" == 0 ]]
}

terminate_owned_cgroup() {
  local cgroup_path=$1
  local empty_status
  local load_status
  local signaled=false
  for _ in {1..20}; do
    if load_owned_cgroup_pids "$cgroup_path"; then
      :
    else
      load_status=$?
      if [[ $load_status -eq 3 && ! -e "$cgroup_path" &&
        "$signaled" == true ]]; then
        echo "authenticated cgroup was removed after termination" >&2
        return
      fi
      if [[ $load_status -eq 3 && -e "$cgroup_path" ]]; then
        sleep 0.05
        continue
      fi
      return 1
    fi
    if [[ ${#OWNED_CGROUP_PIDS[@]} -eq 0 ]]; then
      if owned_cgroup_is_empty "$cgroup_path"; then
        return
      else
        empty_status=$?
        if [[ $empty_status -eq 2 && ! -e "$cgroup_path" ]]; then
          echo "empty authenticated cgroup was removed during verification" >&2
          return
        fi
        if [[ $empty_status -eq 2 ]]; then
          return 1
        fi
      fi
    fi
    signaled=true
    if ! kill -TERM -- "${OWNED_CGROUP_PIDS[@]}" 2>/dev/null; then
      sleep 0.05
      continue
    fi
    sleep 0.05
  done
  for _ in {1..40}; do
    if load_owned_cgroup_pids "$cgroup_path"; then
      :
    else
      load_status=$?
      if [[ $load_status -eq 3 && ! -e "$cgroup_path" &&
        "$signaled" == true ]]; then
        echo "authenticated cgroup was removed after termination" >&2
        return
      fi
      if [[ $load_status -eq 3 && -e "$cgroup_path" ]]; then
        sleep 0.05
        continue
      fi
      return 1
    fi
    if [[ ${#OWNED_CGROUP_PIDS[@]} -eq 0 ]]; then
      if owned_cgroup_is_empty "$cgroup_path"; then
        return
      else
        empty_status=$?
        if [[ $empty_status -eq 2 && ! -e "$cgroup_path" ]]; then
          echo "empty authenticated cgroup was removed during verification" >&2
          return
        fi
        if [[ $empty_status -eq 2 ]]; then
          return 1
        fi
      fi
    fi
    if ! kill -KILL -- "${OWNED_CGROUP_PIDS[@]}" 2>/dev/null; then
      sleep 0.05
      continue
    fi
    sleep 0.05
  done
  if load_owned_cgroup_pids "$cgroup_path"; then
    :
  else
    load_status=$?
    if [[ $load_status -eq 3 && ! -e "$cgroup_path" &&
      "$signaled" == true ]]; then
      echo "authenticated cgroup was removed after termination" >&2
      return
    fi
    if [[ $load_status -eq 3 && -e "$cgroup_path" ]]; then
      echo "authenticated cgroup changed during final enumeration" >&2
    fi
    return 1
  fi
  if owned_cgroup_is_empty "$cgroup_path"; then
    return
  fi
  echo "authenticated cgroup survived teardown: ${OWNED_CGROUP_PIDS[*]}" >&2
  return 1
}

wait_for_owned_session_exit() {
  local leader=$1
  local processes
  for _ in {1..40}; do
    if ! processes=$(ps -e -o pid=,sid=); then
      echo "could not inspect benchmark session: $leader" >&2
      return 1
    fi
    if ! awk -v session="$leader" '$2 == session { found = 1 } END { exit !found }' \
      <<<"$processes"; then
      return
    fi
    sleep 0.05
  done
  echo "benchmark session survived authenticated cgroup teardown: $leader" >&2
  return 1
}

reap_benchmark_launcher() {
  local benchmark_pid=$1
  kill -TERM "$benchmark_pid" 2>/dev/null || :
  for _ in {1..4}; do
    if ! kill -0 "$benchmark_pid" 2>/dev/null; then
      break
    fi
    sleep 0.05
  done
  kill -KILL "$benchmark_pid" 2>/dev/null || :
  wait "$benchmark_pid" 2>/dev/null || :
}

wait_for_benchmark_with_monitor() {
  local scope=$1
  local benchmark_pid=$2
  local control_group=$3
  local cgroup_path=$4
  local benchmark_exit
  local benchmark_session
  for _ in {1..20}; do
    if ! benchmark_session=$(ps -o sid= -p "$benchmark_pid" | tr -d ' '); then
      benchmark_session=
    fi
    if [[ -z "$benchmark_session" || "$benchmark_session" == "$benchmark_pid" ]]; then
      break
    fi
    sleep 0.05
  done
  if [[ -n "$benchmark_session" && "$benchmark_session" != "$benchmark_pid" ]]; then
    echo "benchmark launcher failed to establish an owned session" >&2
    kill "$benchmark_pid"
    wait "$benchmark_pid" 2>/dev/null || :
    return 1
  fi
  while kill -0 "$benchmark_pid" 2>/dev/null; do
    if ! kill -0 "$MONITOR_PID" 2>/dev/null; then
      if ! authenticate_scope_cgroup \
        "$scope" "$control_group" "$cgroup_path" "$benchmark_pid"; then
        echo "monitor failed without an authenticated control group; termination is unverified" >&2
        reap_benchmark_launcher "$benchmark_pid"
        return 1
      fi
      if ! systemctl --user stop "$scope"; then
        echo "could not stop $scope through systemd; terminating authenticated cgroup" >&2
        if ! terminate_owned_cgroup "$cgroup_path"; then
          echo "authenticated cgroup termination could not be proven" >&2
          reap_benchmark_launcher "$benchmark_pid"
          return 1
        fi
      elif [[ -e "$cgroup_path" ]] &&
        ! terminate_owned_cgroup "$cgroup_path"; then
        echo "stopped scope retained an unreadable or populated cgroup" >&2
        reap_benchmark_launcher "$benchmark_pid"
        return 1
      fi
      wait "$benchmark_pid" 2>/dev/null || :
      if [[ -e "$cgroup_path" ]]; then
        if ! load_owned_cgroup_pids "$cgroup_path"; then
          echo "could not verify authenticated cgroup after launcher reap" >&2
          return 1
        fi
        if [[ ${#OWNED_CGROUP_PIDS[@]} -ne 0 ]] ||
          ! owned_cgroup_is_empty "$cgroup_path"; then
          echo "authenticated cgroup repopulated after launcher reap" >&2
          return 1
        fi
      fi
      if ! wait_for_owned_session_exit "$benchmark_pid"; then
        return 1
      fi
      echo "process monitor died during BenchExec; authenticated cgroup teardown complete" >&2
      return 1
    fi
    sleep 0.2
  done
  if wait "$benchmark_pid"; then
    benchmark_exit=0
  else
    benchmark_exit=$?
  fi
  if ! kill -0 "$MONITOR_PID" 2>/dev/null; then
    echo "process monitor died before BenchExec teardown" >&2
    return 1
  fi
  return "$benchmark_exit"
}

single_formal_result() {
  local directory=$1
  local matches=()
  mapfile -t matches < <(
    find "$directory" -maxdepth 1 -type f \
      \( -name '*.results.hard-case-candidates.xml' \
      -o -name '*.results.hard-case-candidates.xml.bz2' \
      -o -name '*.results.hard-case-candidates.official.xml' \
      -o -name '*.results.hard-case-candidates.official.xml.bz2' \) \
      -print
  )
  if [[ ${#matches[@]} -ne 1 ]]; then
    echo "expected exactly one formal result in $directory, found ${#matches[@]}" >&2
    return 1
  fi
  printf '%s\n' "${matches[0]}"
}

main() {
  if [[ $# -ne 16 ]]; then
    echo "usage: $0 CPACHECKER_DIR SV_BENCHMARKS_DIR BENCHEXEC_DIR FORMAL_PACKAGE PARENT_MANIFEST ORIGINAL_MANIFEST ORIGINAL_RESULT ORIGINAL_SURVIVOR REROUTE_MANIFEST REROUTE_RESULT REROUTE_SURVIVOR RECOVERY_MANIFEST RECOVERY_RESULT RECOVERY_SURVIVOR R8_RECOVERY_ROOT OUTPUT_DIR" >&2
    exit 2
  fi

  CPACHECKER_DIR=$(realpath "$1")
  SV_BENCHMARKS_DIR=$(realpath "$2")
  BENCHEXEC_DIR=$(realpath "$3")
  if [[ -L $4 ]]; then
    echo "formal package root must not be a symlink: $4" >&2
    exit 1
  fi
  FORMAL_PACKAGE=$(realpath "$4")
  PARENT_MANIFEST=$(realpath "$5")
  PHASE_MANIFESTS=(
    "$(realpath "$6")"
    "$(realpath "$9")"
    "$(realpath "${12}")"
  )
  PHASE_RESULTS=(
    "$(realpath "$7")"
    "$(realpath "${10}")"
    "$(realpath "${13}")"
  )
  PHASE_SURVIVORS=(
    "$(realpath "$8")"
    "$(realpath "${11}")"
    "$(realpath "${14}")"
  )
  if [[ -L ${15} ]]; then
    echo "r8 recovery root must not be a symlink: ${15}" >&2
    exit 1
  fi
  R8_RECOVERY_ROOT=$(realpath "${15}")
  OUTPUT_DIR=$(realpath -m "${16}")
  SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
  RESEARCH_ROOT=$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)

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
  EXPECTED_MANIFEST=e8aed1d26a0920bfef4964d495d86b69bbad666efb8d72e87462f297ca243855
  EXPECTED_PACKAGE_MANIFEST=a20797345df1bef6d5be5356906ee106b75b374b0d6cd2adfbc56cc5c3e65fef
  P_CORES=0,2,4,6,8,10,12,14

  if [[ $(hostname -s) != "valkyrie" ]]; then
    echo "formal Phase B is Valkyrie-only; refusing host: $(hostname -s)" >&2
    exit 1
  fi
  JAVA_HOME=$(realpath "${JAVA_HOME:?JAVA_HOME must point to the pinned JDK 21}")
  ANT_HOME=$(realpath "${ANT_HOME:?ANT_HOME must point to the pinned Ant}")
  ANT_INSTALL=$(realpath "$ANT_HOME/../..")
  ANT_BIN="$ANT_HOME/bin/ant"
  PYTHON_STDLIB=$(realpath "$EXPECTED_PYTHON_STDLIB")
  PYTHON_DIST_PACKAGES=$(realpath "$EXPECTED_PYTHON_DIST_PACKAGES")
  PYTHON_LOCAL_DIST_PACKAGES=$(realpath "$EXPECTED_PYTHON_LOCAL_DIST_PACKAGES")
  [[ "$PYTHON_BIN" == "$EXPECTED_PYTHON_REAL" ]]
  [[ $(sha256sum "$PYTHON_BIN" | cut -d' ' -f1) == "$EXPECTED_PYTHON_SHA256" ]]
  [[ $("$PYTHON_BIN" --version) == "$EXPECTED_PYTHON_VERSION" ]]
  require_clean_repo "$RESEARCH_ROOT" "research"
  [[ $(git -C "$CPACHECKER_DIR" rev-parse HEAD) == "$EXPECTED_CPACHECKER" ]]
  require_clean_repo "$CPACHECKER_DIR" "CPAchecker stock"
  remove_compiled_classes
  assert_no_compiled_classes
  verify_runtime_closure false
  if env | grep -Eq '^(VGUIDE_|DEEPSEEK_API_KEY=|OPENAI_API_KEY=)'; then
    echo "LLM/VGuide environment is forbidden for formal stock measurement" >&2
    exit 1
  fi
  reject_output_overlap "$OUTPUT_DIR" \
    "$RESEARCH_ROOT" "$CPACHECKER_DIR" "$SV_BENCHMARKS_DIR" "$BENCHEXEC_DIR" \
    "$JAVA_HOME" "$ANT_INSTALL" "$PYTHON_BIN" "$PYTHON_STDLIB" \
    "$PYTHON_DIST_PACKAGES" "$PYTHON_LOCAL_DIST_PACKAGES" \
    "$FORMAL_PACKAGE" "$PARENT_MANIFEST" \
    "$R8_RECOVERY_ROOT" "${PHASE_MANIFESTS[@]}" \
    "${PHASE_RESULTS[@]}" "${PHASE_SURVIVORS[@]}"
  if [[ -e "$OUTPUT_DIR" ]] && {
    [[ ! -d "$OUTPUT_DIR" ]] ||
      [[ -n $(find "$OUTPUT_DIR" -mindepth 1 -print -quit) ]]
  }; then
    echo "output directory must be absent or empty: $OUTPUT_DIR" >&2
    exit 1
  fi

  validate_formal_package_topology "$FORMAL_PACKAGE"
  FORMAL_MANIFEST="$FORMAL_PACKAGE/candidate-manifest-valkyrie-formal.json"
  PACKAGE_MANIFEST="$FORMAL_PACKAGE/artifact-manifest.json"
  [[ $(sha256sum "$FORMAL_MANIFEST" | cut -d' ' -f1) == "$EXPECTED_MANIFEST" ]]
  [[ $(sha256sum "$PACKAGE_MANIFEST" | cut -d' ' -f1) == "$EXPECTED_PACKAGE_MANIFEST" ]]
  run_python_script "$SCRIPT_DIR/dataset.py" validate \
    --manifest "$FORMAL_MANIFEST" \
    --sv-benchmarks "$SV_BENCHMARKS_DIR"
  run_python_script "$SCRIPT_DIR/dataset.py" validate-cap8-r8-recovery \
    --root "$R8_RECOVERY_ROOT" \
    --sv-benchmarks "$SV_BENCHMARKS_DIR"

  exec 9>/var/tmp/vguide-valkyrie-pcores.lock
  if ! flock -n 9; then
    echo "another VGuide run holds the Valkyrie P-core lock" >&2
    exit 1
  fi

  mkdir -p "$OUTPUT_DIR/input/formal" "$OUTPUT_DIR/input/evidence" \
    "$OUTPUT_DIR/input/research" "$OUTPUT_DIR/generated" \
    "$OUTPUT_DIR/results" "$OUTPUT_DIR/provenance"
  cp -a "$FORMAL_PACKAGE/." "$OUTPUT_DIR/input/formal/"
  cp -a "$R8_RECOVERY_ROOT" "$OUTPUT_DIR/input/recovery-r8"
  FORMAL_MANIFEST="$OUTPUT_DIR/input/formal/candidate-manifest-valkyrie-formal.json"
  capture_research_provenance "$OUTPUT_DIR/input/research"
  activate_saved_scripts "$OUTPUT_DIR/input/research"
  verify_research_provenance "$OUTPUT_DIR/input/research"
  run_python_script "$DATASET_PY" validate-cap8-r8-recovery \
    --root "$OUTPUT_DIR/input/recovery-r8" \
    --sv-benchmarks "$SV_BENCHMARKS_DIR" \
    >"$OUTPUT_DIR/provenance/r8-recovery-validation.json"
  verify_runtime_closure false
  write_runtime_provenance "$OUTPUT_DIR/provenance/runtime-closure.txt"
  BUILD_COMPLETED=false

  capture_failure() {
    local status=$?
    local monitor_status
    local research_status
    local runtime_status
    local machine_status=125
    local artifact_status=125
    local final_research_status
    local final_runtime_status
    trap - EXIT
    if ((status != 0)); then
      set +e
      stop_process_monitor_for_teardown
      monitor_status=$?
      verify_research_provenance "$OUTPUT_DIR/input/research" \
        >"$OUTPUT_DIR/provenance/research-verification-failure.log" 2>&1
      research_status=$?
      runtime_status=125
      if ((research_status == 0)); then
        verify_runtime_closure "$BUILD_COMPLETED" \
          >"$OUTPUT_DIR/provenance/runtime-verification-failure.log" 2>&1
        runtime_status=$?
      fi
      if ((research_status == 0 && runtime_status == 0)); then
        JAVA_HOME="$JAVA_HOME" run_python_script "$BASELINE_PY" machine \
          --output "$OUTPUT_DIR/provenance/machine-after-failure.json"
        machine_status=$?
      fi
      printf 'original_exit=%d\nmonitor_exit=%d\nresearch_verification_exit=%d\nruntime_verification_exit=%d\nmachine_capture_exit=%d\n' \
        "$status" "$monitor_status" "$research_status" "$runtime_status" \
        "$machine_status" \
        >"$OUTPUT_DIR/provenance/failure-capture-status.txt"
      if ((research_status == 0 && runtime_status == 0)); then
        run_python_script "$BASELINE_PY" artifact-manifest \
          --root "$OUTPUT_DIR" \
          --output "$OUTPUT_DIR/provenance/artifact-manifest.json"
        artifact_status=$?
      fi
      verify_research_provenance "$OUTPUT_DIR/input/research" >/dev/null 2>&1
      final_research_status=$?
      final_runtime_status=125
      if ((final_research_status == 0)); then
        verify_runtime_closure "$BUILD_COMPLETED" >/dev/null 2>&1
        final_runtime_status=$?
      fi
      if ((monitor_status != 0 || research_status != 0 ||
        final_research_status != 0 || runtime_status != 0 ||
        final_runtime_status != 0 ||
        machine_status != 0 || artifact_status != 0)); then
        echo "failure capture incomplete: monitor=$monitor_status research=$research_status/$final_research_status runtime=$runtime_status/$final_runtime_status machine=$machine_status artifact=$artifact_status" >&2
      fi
    fi
    exit "$status"
  }
  trap capture_failure EXIT
  record_process_snapshot "$OUTPUT_DIR/provenance"

  systemd-run --user --quiet --scope --slice=benchexec -p Delegate=yes \
    taskset -c "$P_CORES" \
    "$PYTHON_BIN" -I -c \
    'import runpy,sys; sys.dont_write_bytecode=True; sys.pycache_prefix="/dev/null"; sys.path.insert(0,sys.argv.pop(1)); sys.argv[0]="benchexec"; runpy.run_module("benchexec.check_cgroups",run_name="__main__")' \
    "$BENCHEXEC_DIR" --no-thread \
    2>&1 | tee "$OUTPUT_DIR/provenance/cgroup-check.log"

  copy_phase_evidence "$OUTPUT_DIR/input/evidence"
  PARENT_MANIFEST=$COPIED_PARENT
  PHASE_MANIFESTS=("${COPIED_MANIFESTS[@]}")
  PHASE_RESULTS=("${COPIED_RESULTS[@]}")
  PHASE_SURVIVORS=("${COPIED_SURVIVORS[@]}")
  run_python_script "$DATASET_PY" validate \
    --manifest "$FORMAL_MANIFEST" \
    --sv-benchmarks "$SV_BENCHMARKS_DIR"

  TASK_COUNT=$("$PYTHON_BIN" -I -c \
    'import json,sys; print(json.load(open(sys.argv[1]))["task_count"])' \
    "$FORMAL_MANIFEST")
  if [[ "$TASK_COUNT" -ne 270 ]]; then
    echo "formal manifest task count is not frozen at 270: $TASK_COUNT" >&2
    exit 1
  fi

  PHASE_ARGS=(--parent-manifest "$PARENT_MANIFEST")
  for manifest in "${PHASE_MANIFESTS[@]}"; do
    PHASE_ARGS+=(--phase-a-manifest "$manifest")
  done
  for result in "${PHASE_RESULTS[@]}"; do
    PHASE_ARGS+=(--phase-a-result "$result")
  done
  for survivor in "${PHASE_SURVIVORS[@]}"; do
    PHASE_ARGS+=(--survivor-manifest "$survivor")
  done
  PHASE_ARGS+=(--sv-benchmarks "$SV_BENCHMARKS_DIR")

  (
    cd "$CPACHECKER_DIR"
    taskset -c "$P_CORES" env JAVA_HOME="$JAVA_HOME" PATH="$JAVA_HOME/bin:$PATH" \
      "$ANT_BIN" -Divy.disable=true clean jar
  ) 2>&1 | tee "$OUTPUT_DIR/provenance/build.log"
  sha256sum "$CPACHECKER_DIR/cpachecker.jar" \
    >"$OUTPUT_DIR/provenance/cpachecker-jar-raw.sha256"
  run_python_script "$BASELINE_PY" jar-content-digest \
    --jar "$CPACHECKER_DIR/cpachecker.jar" \
    >"$OUTPUT_DIR/provenance/cpachecker-jar-content.json"
  [[ $("$PYTHON_BIN" -I -c \
    'import json,sys; print(json.load(open(sys.argv[1]))["sha256"])' \
    "$OUTPUT_DIR/provenance/cpachecker-jar-content.json") == \
      "$EXPECTED_CPACHECKER_JAR_CONTENT" ]]
  BUILD_COMPLETED=true
  remove_compiled_classes
  assert_no_compiled_classes

  JAVA_HOME="$JAVA_HOME" run_python_script "$BASELINE_PY" machine \
    --output "$OUTPUT_DIR/provenance/machine-preflight-start.json"
  sleep 10
  JAVA_HOME="$JAVA_HOME" run_python_script "$BASELINE_PY" machine \
    --output "$OUTPUT_DIR/provenance/machine-preflight-end.json"
  run_python_script "$BASELINE_PY" machine-check \
    --before "$OUTPUT_DIR/provenance/machine-preflight-start.json" \
    --after "$OUTPUT_DIR/provenance/machine-preflight-end.json" |
    tee "$OUTPUT_DIR/provenance/machine-preflight-check.json"

  run_python_script "$DATASET_PY" render-formal \
    "${PHASE_ARGS[@]}" \
    --manifest "$FORMAL_MANIFEST" \
    --property-file "$SV_BENCHMARKS_DIR/c/properties/unreach-call.prp" \
    --output-dir "$OUTPUT_DIR/generated" |
    tee "$OUTPUT_DIR/provenance/render-formal.log"

  run_formal_benchmark() {
    local label=$1
    local name=$2
    local definition=$3
    local output=$4
    local scope="vguide-$label.scope"
    local benchmark_pid
    local benchmark_control_group
    local benchmark_cgroup_path
    mkdir -p "$output"
    JAVA_HOME="$JAVA_HOME" run_python_script "$BASELINE_PY" machine \
      --output "$OUTPUT_DIR/provenance/machine-before-$label.json"
    start_process_monitor "$OUTPUT_DIR/provenance/$label-load-monitor.jsonl"
    wait_for_process_monitor
    "$PYTHON_BIN" -I -c \
      'import os,sys; os.setsid(); os.chdir(sys.argv.pop(1)); os.execvp(sys.argv[1],sys.argv[1:])' \
      "$CPACHECKER_DIR" \
      systemd-run --user --quiet --scope --collect \
        --unit="${scope%.scope}" --slice=benchexec -p Delegate=yes \
        taskset -c "$P_CORES" env -i \
        HOME=/home/benchexec LANG=C.UTF-8 LC_ALL=C.UTF-8 PATH=/usr/bin:/bin \
        JAVA="$JAVA_HOME/bin/java" \
        "$PYTHON_BIN" -I -c \
        'import runpy,sys; sys.dont_write_bytecode=True; sys.pycache_prefix="/dev/null"; sys.path.insert(0,sys.argv.pop(1)); sys.argv[0]="benchexec"; runpy.run_module("benchexec.benchexec",run_name="__main__")' \
        "$BENCHEXEC_DIR" \
        --name "$name" \
        --tool-directory "$CPACHECKER_DIR" \
        --outputpath "$output/" \
        --allowedCores "$P_CORES" \
        --no-hyperthreading \
        --container \
        --read-only-dir / \
        --hidden-dir /home \
        --overlay-dir "$CPACHECKER_DIR" \
        -N 2 -c 4 \
        "$definition" \
      >"$OUTPUT_DIR/provenance/$label-benchexec.log" 2>&1 &
    benchmark_pid=$!
    if ! authenticate_scope_cgroup "$scope" "" "" "$benchmark_pid"; then
      echo "could not authenticate BenchExec scope immediately after launch" >&2
      reap_benchmark_launcher "$benchmark_pid"
      return 1
    fi
    benchmark_control_group=$AUTHENTICATED_CONTROL_GROUP
    benchmark_cgroup_path=$AUTHENTICATED_CGROUP_PATH
    wait_for_benchmark_with_monitor \
      "$scope" "$benchmark_pid" \
      "$benchmark_control_group" "$benchmark_cgroup_path"
    stop_process_monitor
    JAVA_HOME="$JAVA_HOME" run_python_script "$BASELINE_PY" machine \
      --output "$OUTPUT_DIR/provenance/machine-after-$label.json"
    run_python_script "$BASELINE_PY" machine-check \
      --before "$OUTPUT_DIR/provenance/machine-before-$label.json" \
      --after "$OUTPUT_DIR/provenance/machine-after-$label.json" |
      tee "$OUTPUT_DIR/provenance/machine-check-$label.json"
  }

  build_repetition_plan() {
    local repetition=$1
    local primary=$2
    local label="repetition-$repetition"
    local taint="$OUTPUT_DIR/$label-taint.json"
    local plan="$OUTPUT_DIR/$label-plan.json"
    local taint_count
    run_python_script "$DATASET_PY" formal-taint \
      --manifest "$FORMAL_MANIFEST" \
      --repetition "$repetition" \
      --result "$primary" \
      --benchexec-log "$OUTPUT_DIR/provenance/$label-benchexec.log" \
      --load-monitor "$OUTPUT_DIR/provenance/$label-load-monitor.jsonl" \
      --output "$taint"
    taint_count=$("$PYTHON_BIN" -I -c \
      'import json,sys; print(len(json.load(open(sys.argv[1]))["tasks"]))' "$taint")
    if [[ "$taint_count" -eq 0 ]]; then
      run_python_script "$DATASET_PY" repetition-plan \
        --manifest "$FORMAL_MANIFEST" \
        --repetition "$repetition" \
        --primary-result "$primary" \
        --output "$plan"
      BUILT_PLAN=$plan
      return
    fi

    local definition_dir="$OUTPUT_DIR/generated/$label-replacement"
    local definition="$definition_dir/hard-case-candidates.xml"
    local attempt=1
    local replacement
    local replacement_taint
    local replacement_taint_count
    run_python_script "$DATASET_PY" render-formal-replacement \
      "${PHASE_ARGS[@]}" \
      --manifest "$FORMAL_MANIFEST" \
      --primary-result "$primary" \
      --taint-manifest "$taint" \
      --property-file "$SV_BENCHMARKS_DIR/c/properties/unreach-call.prp" \
      --output-dir "$definition_dir"
    while true; do
      local attempt_label="$label-replacement-attempt-$attempt"
      local attempt_output="$OUTPUT_DIR/results/$attempt_label"
      run_formal_benchmark "$attempt_label" \
        "hard-case-dataset-v2-formal-valkyrie-$attempt_label" \
        "$definition" "$attempt_output"
      replacement=$(single_formal_result "$attempt_output")
      replacement_taint="$OUTPUT_DIR/$attempt_label-taint.json"
      run_python_script "$DATASET_PY" formal-taint \
        --manifest "$FORMAL_MANIFEST" \
        --repetition "$repetition" \
        --result "$replacement" \
        --benchexec-log "$OUTPUT_DIR/provenance/$attempt_label-benchexec.log" \
        --load-monitor "$OUTPUT_DIR/provenance/$attempt_label-load-monitor.jsonl" \
        --output "$replacement_taint"
      replacement_taint_count=$("$PYTHON_BIN" -I -c \
        'import json,sys; print(len(json.load(open(sys.argv[1]))["tasks"]))' \
        "$replacement_taint")
      if [[ "$replacement_taint_count" -eq 0 ]]; then
        break
      fi
      attempt=$((attempt + 1))
      sleep 10
    done
    run_python_script "$DATASET_PY" repetition-plan \
      --manifest "$FORMAL_MANIFEST" \
      --repetition "$repetition" \
      --primary-result "$primary" \
      --taint-manifest "$taint" \
      --replacement-result "$replacement" \
      --replacement-definition "$definition" \
      --output "$plan"
    BUILT_PLAN=$plan
  }

  RECOVERY_COPY="$OUTPUT_DIR/input/recovery-r8"
  mkdir -p \
    "$OUTPUT_DIR/results/repetition-1" \
    "$OUTPUT_DIR/results/repetition-1-replacement-attempt-1" \
    "$OUTPUT_DIR/results/repetition-2"
  cp "$RECOVERY_COPY/results/repetition-1/"*.official.xml.bz2 \
    "$OUTPUT_DIR/results/repetition-1/"
  cp \
    "$RECOVERY_COPY/results/repetition-1-replacement-attempt-1/"*.official.xml.bz2 \
    "$OUTPUT_DIR/results/repetition-1-replacement-attempt-1/"
  cp "$RECOVERY_COPY/results/repetition-2/"*.official.xml \
    "$OUTPUT_DIR/results/repetition-2/"
  cp "$RECOVERY_COPY/repetition-1-taint.json" \
    "$OUTPUT_DIR/repetition-1-taint.json"
  cp "$RECOVERY_COPY/provenance/repetition-2-benchexec.log" \
    "$OUTPUT_DIR/provenance/repetition-2-benchexec.log"
  cp "$RECOVERY_COPY/provenance/repetition-2-load-monitor.jsonl" \
    "$OUTPUT_DIR/provenance/repetition-2-load-monitor.jsonl"

  RESULTS=(
    "$(single_formal_result "$OUTPUT_DIR/results/repetition-1")"
    "$(single_formal_result "$OUTPUT_DIR/results/repetition-2")"
  )
  run_python_script "$DATASET_PY" render-formal-replacement \
    "${PHASE_ARGS[@]}" \
    --manifest "$FORMAL_MANIFEST" \
    --primary-result "${RESULTS[0]}" \
    --taint-manifest "$OUTPUT_DIR/repetition-1-taint.json" \
    --property-file "$SV_BENCHMARKS_DIR/c/properties/unreach-call.prp" \
    --output-dir "$OUTPUT_DIR/generated/repetition-1-replacement"
  run_python_script "$DATASET_PY" repetition-plan \
    --manifest "$FORMAL_MANIFEST" \
    --repetition 1 \
    --primary-result "${RESULTS[0]}" \
    --taint-manifest "$OUTPUT_DIR/repetition-1-taint.json" \
    --replacement-result \
      "$(single_formal_result \
        "$OUTPUT_DIR/results/repetition-1-replacement-attempt-1")" \
    --replacement-definition \
      "$OUTPUT_DIR/generated/repetition-1-replacement/hard-case-candidates.xml" \
    --output "$OUTPUT_DIR/repetition-1-plan.json"
  PLANS=("$OUTPUT_DIR/repetition-1-plan.json")
  build_repetition_plan 2 "${RESULTS[1]}"
  PLANS+=("$BUILT_PLAN")

  run_python_script "$DATASET_PY" summarize \
    "${PHASE_ARGS[@]}" \
    --manifest "$FORMAL_MANIFEST" \
    --benchmark-definition "$OUTPUT_DIR/generated/hard-case-candidates.xml" \
    --repetition-plan "${PLANS[0]}" \
    --repetition-plan "${PLANS[1]}" \
    --output-dir "$OUTPUT_DIR/summary" \
    --hard-threshold 200 \
    2>&1 | tee "$OUTPUT_DIR/provenance/summarize.log"

  verify_research_provenance "$OUTPUT_DIR/input/research" \
    >"$OUTPUT_DIR/provenance/research-verification-final.log" 2>&1
  run_python_script "$DATASET_PY" validate-cap8-r8-recovery \
    --root "$OUTPUT_DIR/input/recovery-r8" \
    --sv-benchmarks "$SV_BENCHMARKS_DIR" \
    >"$OUTPUT_DIR/provenance/r8-recovery-verification-final.json"
  verify_runtime_closure true \
    >"$OUTPUT_DIR/provenance/runtime-verification-final.log" 2>&1
  run_python_script "$BASELINE_PY" artifact-manifest \
    --root "$OUTPUT_DIR" \
    --output "$OUTPUT_DIR/provenance/artifact-manifest.json"
  verify_research_provenance "$OUTPUT_DIR/input/research" >/dev/null
  run_python_script "$DATASET_PY" validate-cap8-r8-recovery \
    --root "$OUTPUT_DIR/input/recovery-r8" \
    --sv-benchmarks "$SV_BENCHMARKS_DIR" >/dev/null
  verify_runtime_closure true >/dev/null
  trap - EXIT
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
