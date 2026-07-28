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
PYTHON_RUNTIME_FLAGS=(-I -S -B -X pycache_prefix=/dev/null)
BENCHEXEC_MODULE_COMMAND='import importlib.util,runpy,sys; from pathlib import Path; repository=sys.argv.pop(1); yaml_file=sys.argv.pop(1); spec=importlib.util.spec_from_file_location("yaml",yaml_file,submodule_search_locations=[str(Path(yaml_file).parent)]); assert spec is not None and spec.loader is not None; yaml=importlib.util.module_from_spec(spec); sys.modules["yaml"]=yaml; spec.loader.exec_module(yaml); sys.path.insert(0,repository); sys.argv[0]="benchexec"; runpy.run_module("benchexec.benchexec",run_name="__main__")'
BENCHEXEC_CGROUP_COMMAND='import importlib.util,runpy,sys; from pathlib import Path; repository=sys.argv.pop(1); yaml_file=sys.argv.pop(1); spec=importlib.util.spec_from_file_location("yaml",yaml_file,submodule_search_locations=[str(Path(yaml_file).parent)]); assert spec is not None and spec.loader is not None; yaml=importlib.util.module_from_spec(spec); sys.modules["yaml"]=yaml; spec.loader.exec_module(yaml); sys.path.insert(0,repository); sys.argv[0]="benchexec"; runpy.run_module("benchexec.check_cgroups",run_name="__main__")'

assert_no_sourceless_python_bytecode() {
  local root
  local match
  for root in "$@"; do
    match=$(find -P "$root" -mindepth 1 \
      \( -type d -name __pycache__ -prune \) -o \
      \( -name '*.pyc' -o -name '*.pyo' \) -print -quit)
    if [[ -n "$match" ]]; then
      echo "sourceless Python bytecode could shadow pinned source: $match" >&2
      return 1
    fi
  done
}

run_python_script() {
  assert_no_sourceless_python_bytecode "$(dirname "$(realpath "$1")")"
  "$PYTHON_BIN" "${PYTHON_RUNTIME_FLAGS[@]}" -c '
import runpy
import sys
from pathlib import Path

script = Path(sys.argv.pop(1)).resolve()
sys.argv[0] = str(script)
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
  "$PYTHON_BIN" "${PYTHON_RUNTIME_FLAGS[@]}" - \
    "$repository" "$label" "$allow_missing_skip" <<'PY'
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

validate_recovery_protocol_topology() {
  local package=$1
  local actual
  local expected
  actual=$(find -P "$package" -mindepth 1 -printf '%y %P\n' | sort)
  expected=$(
    printf '%s\n' \
      "f candidate-manifest.json" \
      "f protocol.json" \
      "f seed-ledger.json" \
      "f unreach-call.prp"
  )
  if [[ "$actual" != "$expected" ]]; then
    echo "formal recovery protocol package topology is not exact" >&2
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
  property_path=$("$PYTHON_BIN" "${PYTHON_RUNTIME_FLAGS[@]}" - \
    "$PARENT_MANIFEST" <<'PY'
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

copy_cap16_phase_evidence() {
  local evidence_dir=$1
  mkdir -p "$evidence_dir"
  cp -a "$CAP16_PHASE_A_OUTPUT/." "$evidence_dir/"
}

verify_cap16_phase_evidence() {
  run_python_script "$DATASET_PY" validate-cap16-phase-a \
    --phase-a-output "$CAP16_PHASE_A_OUTPUT" \
    --sv-benchmarks "$SV_BENCHMARKS_DIR"
}

capture_research_provenance() {
  local destination=$1
  local head
  local status_hash
  local diff_hash
  mkdir -p "$destination/scripts"
  cp -- "$SCRIPT_DIR/run-stock-formal-dataset.sh" \
    "$destination/scripts/run-stock-formal-dataset.sh"
  if [[ ${FORMAL_MODE:-cap8} == cap16 ]]; then
    cp -- "$SCRIPT_DIR/run-stock-cap16-formal-dataset.sh" \
      "$destination/scripts/run-stock-cap16-formal-dataset.sh"
  elif [[ ${FORMAL_MODE:-cap8} == cap16-probe ]]; then
    cp -- "$SCRIPT_DIR/run-cap16-cegar-probe.sh" \
      "$destination/scripts/run-cap16-cegar-probe.sh"
  fi
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
  verify_frozen_research_provenance \
    "$destination" "$(git -C "$RESEARCH_ROOT" rev-parse HEAD)"
}

verify_frozen_research_provenance() {
  local destination=$1
  local expected_head=$2
  local actual_topology
  local empty_hash=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
  local expected_topology
  local path
  require_clean_repo "$RESEARCH_ROOT" "research"
  git -C "$RESEARCH_ROOT" merge-base --is-ancestor \
    "$expected_head" "$(git -C "$RESEARCH_ROOT" rev-parse HEAD)"
  [[ $(cat "$destination/research-head.txt") == "$expected_head" ]]
  [[ ! -s "$destination/research-status.porcelain" ]]
  [[ ! -s "$destination/research-diff.patch" ]]
  [[ $(cat "$destination/research-state.json") == "$(
    printf '{\n  "head": "%s",\n  "clean": true,\n  "status_sha256": "%s",\n  "diff_sha256": "%s"\n}' \
      "$expected_head" "$empty_hash" "$empty_hash"
  )" ]]
  for path in run-stock-formal-dataset.sh dataset.py baseline.py; do
    cmp -- "$destination/scripts/$path" \
      <(git -C "$RESEARCH_ROOT" show "$expected_head:scripts/vguide/$path")
  done
  if [[ ${FORMAL_MODE:-cap8} == cap16 ]]; then
    path=run-stock-cap16-formal-dataset.sh
    cmp -- "$destination/scripts/$path" \
      <(git -C "$RESEARCH_ROOT" show "$expected_head:scripts/vguide/$path")
  elif [[ ${FORMAL_MODE:-cap8} == cap16-probe ]]; then
    path=run-cap16-cegar-probe.sh
    cmp -- "$destination/scripts/$path" \
      <(git -C "$RESEARCH_ROOT" show "$expected_head:scripts/vguide/$path")
  fi
  actual_topology=$(find -P "$destination" -mindepth 1 -printf '%y %P\n' | sort)
  expected_topology=$(
    {
      printf '%s\n' \
        "d scripts" \
        "f inventory.sha256" \
        "f research-diff.patch" \
        "f research-head.txt" \
        "f research-index-flags.txt" \
        "f research-state.json" \
        "f research-status.porcelain" \
        "f scripts/baseline.py" \
        "f scripts/dataset.py" \
        "f scripts/run-stock-formal-dataset.sh"
      if [[ ${FORMAL_MODE:-cap8} == cap16 ]]; then
        printf '%s\n' "f scripts/run-stock-cap16-formal-dataset.sh"
      elif [[ ${FORMAL_MODE:-cap8} == cap16-probe ]]; then
        printf '%s\n' "f scripts/run-cap16-cegar-probe.sh"
      fi
    } | sort
  )
  if [[ "$actual_topology" != "$expected_topology" ]]; then
    echo "research provenance node topology differs" >&2
    return 1
  fi
  (
    cd "$destination"
    cmp -- inventory.sha256 <(
      find -P . -type f ! -name inventory.sha256 -printf '%P\n' |
        sort |
        xargs sha256sum
    )
  )
}

activate_formal_research_provenance() {
  local original="$OUTPUT_DIR/input/research"
  local original_head
  local current_head
  original_head=$(cat "$original/research-head.txt")
  current_head=$(git -C "$RESEARCH_ROOT" rev-parse HEAD)
  ORIGINAL_RESEARCH_PROVENANCE=$original
  if [[ "$original_head" == "$current_head" ]]; then
    ACTIVE_RESEARCH_PROVENANCE=$original
  elif [[ "$RESUMING" == true ]] &&
    git -C "$RESEARCH_ROOT" merge-base --is-ancestor \
      "$original_head" "$current_head"; then
    ACTIVE_RESEARCH_PROVENANCE=$(
      printf '%s/input/recovery-research-%s' "$OUTPUT_DIR" "$current_head"
    )
    verify_all_research_provenance
    if [[ -L "$ACTIVE_RESEARCH_PROVENANCE" ]]; then
      echo "recovery research provenance is not a directory" >&2
      return 1
    elif [[ ! -e "$ACTIVE_RESEARCH_PROVENANCE" ]]; then
      capture_research_provenance "$ACTIVE_RESEARCH_PROVENANCE"
    elif [[ ! -d "$ACTIVE_RESEARCH_PROVENANCE" ]]; then
      echo "recovery research provenance is not a directory" >&2
      return 1
    fi
  else
    echo "saved formal research head is not an authenticated recovery parent" >&2
    return 1
  fi
  activate_saved_scripts "$ACTIVE_RESEARCH_PROVENANCE"
  verify_all_research_provenance
}

verify_all_research_provenance() {
  local destination
  local original_head
  local recovery_head
  local recovery_name
  original_head=$(cat "$ORIGINAL_RESEARCH_PROVENANCE/research-head.txt")
  verify_frozen_research_provenance \
    "$ORIGINAL_RESEARCH_PROVENANCE" "$original_head"

  destination="$OUTPUT_DIR/input/recovery-research"
  if [[ -e "$destination" || -L "$destination" ]]; then
    if [[ ! -d "$destination" || -L "$destination" ]]; then
      echo "legacy recovery research provenance is not a directory" >&2
      return 1
    fi
    verify_frozen_research_provenance \
      "$destination" "$LEGACY_RECOVERY_RESEARCH_HEAD"
  fi

  for destination in "$OUTPUT_DIR"/input/recovery-research-*; do
    if [[ ! -e "$destination" && ! -L "$destination" ]]; then
      continue
    fi
    if [[ ! -d "$destination" || -L "$destination" ]]; then
      echo "revision recovery research provenance is not a directory" >&2
      return 1
    fi
    recovery_name=${destination##*/}
    recovery_head=${recovery_name#recovery-research-}
    if [[ ! "$recovery_head" =~ ^[0-9a-f]{40}$ ]] ||
      [[ $(cat "$destination/research-head.txt") != "$recovery_head" ]]; then
      echo "revision recovery research provenance does not match its path" >&2
      return 1
    fi
    verify_frozen_research_provenance "$destination" "$recovery_head"
  done
}

directory_digest_value() {
  run_python_script "${BASELINE_PY:-$SCRIPT_DIR/baseline.py}" \
    directory-digest --root "$1" |
    "$PYTHON_BIN" "${PYTHON_RUNTIME_FLAGS[@]}" -c \
    'import json,sys; print(json.load(sys.stdin)["sha256"])'
}

python_runtime_digest_value() {
  local root=$1
  shift
  local arguments=()
  local path
  for path in "$@"; do
    arguments+=(--path "$path")
  done
  run_python_script "${BASELINE_PY:-$SCRIPT_DIR/baseline.py}" \
    python-runtime-digest --root "$root" "${arguments[@]}" |
    "$PYTHON_BIN" "${PYTHON_RUNTIME_FLAGS[@]}" -c \
    'import json,sys; print(json.load(sys.stdin)["sha256"])'
}

pyyaml_package_digest_value() {
  python_runtime_digest_value \
    "$PYTHON_DIST_PACKAGES" "${EXPECTED_PYYAML_PACKAGE_PATHS[@]}"
}

jar_content_digest_value() {
  run_python_script "${BASELINE_PY:-$SCRIPT_DIR/baseline.py}" \
    jar-content-digest --jar "$1" |
    "$PYTHON_BIN" "${PYTHON_RUNTIME_FLAGS[@]}" -c \
    'import json,sys; print(json.load(sys.stdin)["sha256"])'
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
  assert_no_sourceless_python_bytecode "$BENCHEXEC_DIR"
  env -i HOME=/home/benchexec LANG=C.UTF-8 LC_ALL=C.UTF-8 PATH=/usr/bin:/bin \
    JAVA="$JAVA_HOME/bin/java" \
    "$PYTHON_BIN" "${PYTHON_RUNTIME_FLAGS[@]}" -c '
import importlib.util
import json
import sys
from pathlib import Path

repository = sys.argv[1]
yaml_file = sys.argv[2]
spec = importlib.util.spec_from_file_location(
    "yaml",
    yaml_file,
    submodule_search_locations=[str(Path(yaml_file).parent)],
)
if spec is None or spec.loader is None:
  raise SystemExit(f"unexpected yaml module: {yaml_file}")
yaml = importlib.util.module_from_spec(spec)
sys.modules["yaml"] = yaml
spec.loader.exec_module(yaml)
sys.path.insert(0, repository)

print(json.dumps({
    "python_executable": sys.executable,
    "sys_path": sys.path,
    "dont_write_bytecode": sys.dont_write_bytecode,
    "isolated": sys.flags.isolated,
    "no_site": sys.flags.no_site,
    "pycache_prefix": sys.pycache_prefix,
    "safe_path": getattr(sys.flags, "safe_path", None),
    "site_loaded": "site" in sys.modules,
    "yaml_file": yaml.__file__,
    "yaml_version": yaml.__version__,
}, sort_keys=True, separators=(",", ":")))
' "$BENCHEXEC_DIR" "$EXPECTED_PYYAML_FILE"
}

verify_python_runtime() {
  assert_no_sourceless_python_bytecode "$BENCHEXEC_DIR"
  env -i HOME=/home/benchexec LANG=C.UTF-8 LC_ALL=C.UTF-8 PATH=/usr/bin:/bin \
    JAVA="$JAVA_HOME/bin/java" \
    "$PYTHON_BIN" "${PYTHON_RUNTIME_FLAGS[@]}" -c '
import importlib.util
import sys
from pathlib import Path

repository, executable, system_path, yaml_file, yaml_version = sys.argv[1:]
spec = importlib.util.spec_from_file_location(
    "yaml",
    yaml_file,
    submodule_search_locations=[str(Path(yaml_file).parent)],
)
if spec is None or spec.loader is None:
  raise SystemExit(f"unexpected yaml module: {yaml_file}")
yaml = importlib.util.module_from_spec(spec)
sys.modules["yaml"] = yaml
spec.loader.exec_module(yaml)
sys.path.insert(0, repository)

if sys.executable != executable:
  raise SystemExit(f"unexpected Python executable: {sys.executable}")
expected_path = [repository, *system_path.split(":")]
if sys.path != expected_path:
  raise SystemExit(f"unexpected isolated sys.path: {sys.path}")
if yaml.__file__ != yaml_file:
  raise SystemExit(f"unexpected yaml module: {yaml.__file__}")
if yaml.__version__ != yaml_version:
  raise SystemExit(f"unexpected yaml version: {yaml.__version__}")
if (
    not sys.dont_write_bytecode
    or sys.pycache_prefix != "/dev/null"
    or not sys.flags.isolated
    or not sys.flags.no_site
    or (
        hasattr(sys.flags, "safe_path")
        and not sys.flags.safe_path
    )
    or "site" in sys.modules
):
  raise SystemExit("Python startup isolation is not active")
' "$BENCHEXEC_DIR" "$EXPECTED_PYTHON_REAL" "$EXPECTED_PYTHON_SYSTEM_PATH" \
    "$EXPECTED_PYYAML_FILE" "$EXPECTED_PYYAML_VERSION"
}

benchexec_version() {
  assert_no_sourceless_python_bytecode "$BENCHEXEC_DIR"
  "$PYTHON_BIN" "${PYTHON_RUNTIME_FLAGS[@]}" -c \
    "$BENCHEXEC_MODULE_COMMAND" \
    "$BENCHEXEC_DIR" "$EXPECTED_PYYAML_FILE" --version
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
  [[ $(python_runtime_digest_value "$PYTHON_STDLIB") == \
    "$EXPECTED_PYTHON_STDLIB_DIGEST" ]]
  [[ $(pyyaml_package_digest_value) == "$EXPECTED_PYYAML_PACKAGE_DIGEST" ]]
  [[ $(python_runtime_digest_value "$PYTHON_LOCAL_DIST_PACKAGES") == \
    "$EXPECTED_PYTHON_LOCAL_DIST_PACKAGES_DIGEST" ]]
  assert_no_sourceless_python_bytecode \
    "$BENCHEXEC_DIR" \
    "$(dirname "${DATASET_PY:-$SCRIPT_DIR/dataset.py}")"
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
    "python_stdlib_non_cache_sha256=$(python_runtime_digest_value "$PYTHON_STDLIB")" \
    "python_dist_packages=$PYTHON_DIST_PACKAGES" \
    "pyyaml_package_paths=${EXPECTED_PYYAML_PACKAGE_PATHS[*]}" \
    "pyyaml_package_non_cache_sha256=$(pyyaml_package_digest_value)" \
    "python_local_dist_packages=$PYTHON_LOCAL_DIST_PACKAGES" \
    "python_local_dist_packages_non_cache_sha256=$(python_runtime_digest_value "$PYTHON_LOCAL_DIST_PACKAGES")" \
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
  taskset -c 16-23 "$PYTHON_BIN" "${PYTHON_RUNTIME_FLAGS[@]}" \
    "$DATASET_PY" monitor-formal-load \
    --output "$output" --exclude-root "$$" &
  MONITOR_PID=$!
  MONITOR_ACTIVE=true
  MONITOR_OUTPUT=$output
  printf '%s\n' "$MONITOR_PID" >"$output.pid"
  run_python_script "$DATASET_PY" capture-process-identity \
    --pid "$MONITOR_PID" --role load-monitor \
    --output "$output.process.json"
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
  local stopped
  local stopped_tmp
  if [[ -z ${MONITOR_PID:-} ]] || ! kill -0 "$MONITOR_PID" 2>/dev/null; then
    echo "process monitor is not alive at teardown" >&2
    return 1
  fi
  if ! kill "$MONITOR_PID"; then
    echo "process monitor could not be stopped" >&2
    return 1
  fi
  if wait "$MONITOR_PID"; then
    monitor_exit=0
  else
    monitor_exit=$?
  fi
  if [[ "$monitor_exit" -ne 0 ]]; then
    echo "process monitor exited unsuccessfully" >&2
    return 1
  fi
  if [[ ! -s "$MONITOR_OUTPUT" ]]; then
    echo "process monitor output is empty" >&2
    return 1
  fi
  samples=$(($(wc -l <"$MONITOR_OUTPUT") - 1))
  if [[ "$samples" -le 0 ]]; then
    echo "process monitor has no samples" >&2
    return 1
  fi
  stopped="$MONITOR_OUTPUT.stopped"
  if [[ -e "$stopped" || -L "$stopped" ]]; then
    echo "process monitor stop evidence already exists" >&2
    return 1
  fi
  if ! stopped_tmp=$(mktemp "$stopped.tmp.XXXXXX"); then
    return 1
  fi
  if ! printf 'pid=%s\nexit=%s\nsamples=%s\n' \
    "$MONITOR_PID" "$monitor_exit" "$samples" \
    >"$stopped_tmp"; then
    rm -f -- "$stopped_tmp"
    return 1
  fi
  if ! mv -- "$stopped_tmp" "$stopped"; then
    rm -f -- "$stopped_tmp"
    return 1
  fi
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
      contended=$("$PYTHON_BIN" "${PYTHON_RUNTIME_FLAGS[@]}" -c \
        'import json,sys; print(any(row["contended"] for row in json.loads(open(sys.argv[1]).read().splitlines()[-1])["offenders"]))' \
        "$MONITOR_OUTPUT")
      if [[ "$contended" == False ]]; then
        return
      fi
    fi
    sleep 1
  done
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

formal_benchexec_workers() {
  case "$1" in
    cap8)
      printf '2\n'
      ;;
    cap16)
      printf '1\n'
      ;;
    *)
      return 1
      ;;
  esac
}

main() {
  FORMAL_MODE=$1
  shift
  if [[ "$FORMAL_MODE" == cap16 && $# -ne 6 ]]; then
    echo "usage: $0 CPACHECKER_DIR SV_BENCHMARKS_DIR BENCHEXEC_DIR CAP16_PHASE_A_PACKAGE OUTPUT_DIR RECOVERY_PROTOCOL_PACKAGE" >&2
    exit 2
  elif [[ "$FORMAL_MODE" == cap8 && $# -ne 16 ]]; then
    echo "usage: $0 CPACHECKER_DIR SV_BENCHMARKS_DIR BENCHEXEC_DIR FORMAL_PACKAGE PARENT_MANIFEST ORIGINAL_MANIFEST ORIGINAL_RESULT ORIGINAL_SURVIVOR REROUTE_MANIFEST REROUTE_RESULT REROUTE_SURVIVOR RECOVERY_MANIFEST RECOVERY_RESULT RECOVERY_SURVIVOR OUTPUT_DIR RECOVERY_PROTOCOL_PACKAGE" >&2
    exit 2
  elif [[ "$FORMAL_MODE" != cap8 && "$FORMAL_MODE" != cap16 ]]; then
    echo "unknown formal mode: $FORMAL_MODE" >&2
    exit 2
  fi
  CPACHECKER_DIR=$(realpath "$1")
  SV_BENCHMARKS_DIR=$(realpath "$2")
  BENCHEXEC_DIR=$(realpath "$3")
  if [[ "$FORMAL_MODE" == cap16 ]]; then
    if [[ -L $4 ]]; then
      echo "cap-16 Phase-A output must not be a symlink: $4" >&2
      exit 1
    fi
    CAP16_PHASE_A_OUTPUT=$(realpath -m "$4")
    FORMAL_MANIFEST="$CAP16_PHASE_A_OUTPUT/summary/candidate-manifest-analysis-survivors.json"
    OUTPUT_DIR=$(realpath -m "$5")
    RECOVERY_PROTOCOL_PACKAGE=$(realpath "$6")
  elif [[ "$FORMAL_MODE" == cap8 ]]; then
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
    OUTPUT_DIR=$(realpath -m "${15}")
    RECOVERY_PROTOCOL_PACKAGE=$(realpath "${16}")
  fi
  validate_recovery_protocol_topology "$RECOVERY_PROTOCOL_PACKAGE"
  SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
  RESEARCH_ROOT=$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)

  EXPECTED_CPACHECKER=1848f9eb597ca99a170fd98af8aad716743a2bfe
  EXPECTED_SV_BENCHMARKS=9cf9198156e4c8a6c517e474770158e1bb0b566d
  EXPECTED_BENCHEXEC=edb95ed3a8478366b8bb89f8cdd1d9a6c5fa8c84
  EXPECTED_JDK=867ff62e01a0936fc0a90ceae27338be1973559767ef0717896f8d64f780ece6
  EXPECTED_STOCK_LIB_JAVA=eea0df062de5c8e3febe0d96b583741c140e79d3ae41a87a56d7be365b876f9d
  EXPECTED_ANT_INSTALL=52772e241e78a875fa00dea891eac2023d4f2be639a5f28a17dca81580f75e5b
  EXPECTED_ANT_VERSION="Apache Ant(TM) version 1.10.12 compiled on January 17 1970"
  EXPECTED_PYTHON_DIST_PACKAGES=/usr/lib/python3/dist-packages
  EXPECTED_PYTHON_LOCAL_DIST_PACKAGES_DIGEST=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
  EXPECTED_PYYAML_FILE=/usr/lib/python3/dist-packages/yaml/__init__.py
  if [[ "$FORMAL_MODE" == cap16 ]]; then
    EXPECTED_PYTHON_REAL=/usr/bin/python3.12
    EXPECTED_PYTHON_SHA256=1643dacd9feaedc58f3cc581e4d22577dfe25c09b10282936186ccf0f2e61118
    EXPECTED_PYTHON_VERSION="Python 3.12.3"
    EXPECTED_PYTHON_STDLIB=/usr/lib/python3.12
    EXPECTED_PYTHON_STDLIB_DIGEST=a0c9c33e4f5b6c4e8e921598ec1c7273341cf2e8f2c74d7a348d6a3584a2c325
    EXPECTED_PYTHON_LOCAL_DIST_PACKAGES=/usr/local/lib/python3.12/dist-packages
    EXPECTED_PYTHON_SYSTEM_PATH=/usr/lib/python312.zip:/usr/lib/python3.12:/usr/lib/python3.12/lib-dynload
    EXPECTED_PYYAML_VERSION=6.0.1
    EXPECTED_PYYAML_PACKAGE_PATHS=(
      yaml
      _yaml
      PyYAML-6.0.1.dist-info
    )
    EXPECTED_PYYAML_PACKAGE_DIGEST=9148a8dc1759caac2f87132749a8f29de2cf8ee71b6ddead932d027613045627
    FORMAL_HOST=athena
    FORMAL_BENCHMARK_SCOPE=-cap16
  else
    EXPECTED_PYTHON_REAL=/usr/bin/python3.10
    EXPECTED_PYTHON_SHA256=7d51cd6b48b521277f5caa4610a82126e315fa2be4df069823a8b1eeb5bd4a86
    EXPECTED_PYTHON_VERSION="Python 3.10.12"
    EXPECTED_PYTHON_STDLIB=/usr/lib/python3.10
    EXPECTED_PYTHON_STDLIB_DIGEST=c9af63c831839af73b709cf538807f9ea989c834d635526875a03787c29247cc
    EXPECTED_PYTHON_LOCAL_DIST_PACKAGES=/usr/local/lib/python3.10/dist-packages
    EXPECTED_PYTHON_SYSTEM_PATH=/usr/lib/python310.zip:/usr/lib/python3.10:/usr/lib/python3.10/lib-dynload
    EXPECTED_PYYAML_VERSION=5.4.1
    EXPECTED_PYYAML_PACKAGE_PATHS=(
      yaml
      _yaml
      PyYAML-5.4.1.egg-info
    )
    EXPECTED_PYYAML_PACKAGE_DIGEST=9dd464e236b90eaa25fc9576bb22442b07817d16e086f9e3754d61c3328d9bbd
    FORMAL_HOST=valkyrie
    FORMAL_BENCHMARK_SCOPE=
  fi
  EXPECTED_BENCHEXEC_ARCHIVE=75e3332253429e6f9186352a255cd96c0aff6154a95e2fdd3b737c143ba018bc
  EXPECTED_BENCHEXEC_VERSION="benchexec 3.35-dev"
  EXPECTED_CPACHECKER_JAR_CONTENT=49f95adc5255b89b1bb3edea81ab5f2f660364d36ffa69c3b12508d1e1943be3
  LEGACY_FORMAL_RESEARCH_HEAD=2e2f8e7694d5d827756c322f788f59ac3c07a39d
  LEGACY_RECOVERY_RESEARCH_HEAD=6b78ae338c687c32d905679243fb1d3a3f916733
  EXPECTED_MANIFEST=e8aed1d26a0920bfef4964d495d86b69bbad666efb8d72e87462f297ca243855
  EXPECTED_PACKAGE_MANIFEST=a20797345df1bef6d5be5356906ee106b75b374b0d6cd2adfbc56cc5c3e65fef
  P_CORES=0,2,4,6,8,10,12,14

  if [[ $(hostname -s) != "$FORMAL_HOST" ]]; then
    echo "formal Phase B is $FORMAL_HOST-only; refusing host: $(hostname -s)" >&2
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
  RESUMING=false
  if [[ -e "$OUTPUT_DIR" ]] && {
    [[ ! -d "$OUTPUT_DIR" ]] ||
      [[ -n $(find "$OUTPUT_DIR" -mindepth 1 -print -quit) ]]
  }; then
    if [[ -d "$OUTPUT_DIR/input/evidence" &&
      -d "$OUTPUT_DIR/input/research" ]]; then
      RESUMING=true
      if [[ "$FORMAL_MODE" == cap16 ]]; then
        CAP16_PHASE_A_OUTPUT="$OUTPUT_DIR/input/evidence"
        FORMAL_MANIFEST="$CAP16_PHASE_A_OUTPUT/summary/candidate-manifest-analysis-survivors.json"
      else
        FORMAL_MANIFEST="$OUTPUT_DIR/input/formal/candidate-manifest-valkyrie-formal.json"
      fi
    else
      echo "output directory must be absent or empty: $OUTPUT_DIR" >&2
      exit 1
    fi
  fi
  INPUT_PATHS=(
    "$RESEARCH_ROOT" "$CPACHECKER_DIR" "$SV_BENCHMARKS_DIR" "$BENCHEXEC_DIR"
    "$JAVA_HOME" "$ANT_INSTALL" "$PYTHON_BIN" "$PYTHON_STDLIB"
    "$PYTHON_DIST_PACKAGES" "$PYTHON_LOCAL_DIST_PACKAGES"
    "$RECOVERY_PROTOCOL_PACKAGE"
  )
  if [[ "$FORMAL_MODE" == cap16 && "$RESUMING" == false ]]; then
    INPUT_PATHS+=("$CAP16_PHASE_A_OUTPUT")
  elif [[ "$FORMAL_MODE" == cap8 ]]; then
    INPUT_PATHS+=(
      "$FORMAL_PACKAGE" "$PARENT_MANIFEST"
      "${PHASE_MANIFESTS[@]}" "${PHASE_RESULTS[@]}" "${PHASE_SURVIVORS[@]}"
    )
  fi
  reject_output_overlap "$OUTPUT_DIR" "${INPUT_PATHS[@]}"

  if [[ "$FORMAL_MODE" == cap16 ]]; then
    run_python_script "$SCRIPT_DIR/dataset.py" validate-cap16-phase-a \
      --phase-a-output "$CAP16_PHASE_A_OUTPUT" \
      --sv-benchmarks "$SV_BENCHMARKS_DIR"
  else
    validate_formal_package_topology "$FORMAL_PACKAGE"
    FORMAL_MANIFEST="$FORMAL_PACKAGE/candidate-manifest-valkyrie-formal.json"
    PACKAGE_MANIFEST="$FORMAL_PACKAGE/artifact-manifest.json"
    [[ $(sha256sum "$FORMAL_MANIFEST" | cut -d' ' -f1) == "$EXPECTED_MANIFEST" ]]
    [[ $(sha256sum "$PACKAGE_MANIFEST" | cut -d' ' -f1) == "$EXPECTED_PACKAGE_MANIFEST" ]]
    run_python_script "$SCRIPT_DIR/dataset.py" validate \
      --manifest "$FORMAL_MANIFEST" \
      --sv-benchmarks "$SV_BENCHMARKS_DIR"
  fi

  exec 9>"/var/tmp/vguide-$FORMAL_HOST-pcores.lock"
  if ! flock -n 9; then
    echo "another VGuide run holds the $FORMAL_HOST P-core lock" >&2
    exit 1
  fi

  if [[ "$RESUMING" == false ]]; then
    mkdir -p "$OUTPUT_DIR/input/evidence" "$OUTPUT_DIR/input/research" \
      "$OUTPUT_DIR/generated" "$OUTPUT_DIR/results" "$OUTPUT_DIR/provenance"
    if [[ "$FORMAL_MODE" == cap16 ]]; then
      copy_cap16_phase_evidence "$OUTPUT_DIR/input/evidence"
      CAP16_PHASE_A_OUTPUT="$OUTPUT_DIR/input/evidence"
      FORMAL_MANIFEST="$CAP16_PHASE_A_OUTPUT/summary/candidate-manifest-analysis-survivors.json"
    else
      mkdir "$OUTPUT_DIR/input/formal"
      cp -a "$FORMAL_PACKAGE/." "$OUTPUT_DIR/input/formal/"
      FORMAL_MANIFEST="$OUTPUT_DIR/input/formal/candidate-manifest-valkyrie-formal.json"
    fi
    capture_research_provenance "$OUTPUT_DIR/input/research"
  else
    if [[ "$FORMAL_MODE" == cap16 ]]; then
      CAP16_PHASE_A_OUTPUT="$OUTPUT_DIR/input/evidence"
      FORMAL_MANIFEST="$CAP16_PHASE_A_OUTPUT/summary/candidate-manifest-analysis-survivors.json"
    else
      FORMAL_MANIFEST="$OUTPUT_DIR/input/formal/candidate-manifest-valkyrie-formal.json"
    fi
  fi
  if [[ -e "$OUTPUT_DIR/input/recovery-protocol" ]]; then
    diff -r -- "$RECOVERY_PROTOCOL_PACKAGE" \
      "$OUTPUT_DIR/input/recovery-protocol"
  else
    cp -a -- "$RECOVERY_PROTOCOL_PACKAGE" \
      "$OUTPUT_DIR/input/recovery-protocol"
  fi
  PROTOCOL_ROOT="$OUTPUT_DIR/input/recovery-protocol"
  PROTOCOL_COPY="$PROTOCOL_ROOT/protocol.json"
  SEED_LEDGER_COPY="$PROTOCOL_ROOT/seed-ledger.json"
  PROTOCOL_MANIFEST_COPY="$PROTOCOL_ROOT/candidate-manifest.json"
  PROTOCOL_PROPERTY_COPY="$PROTOCOL_ROOT/unreach-call.prp"
  cmp -- "$FORMAL_MANIFEST" "$PROTOCOL_MANIFEST_COPY"
  cmp -- "$SV_BENCHMARKS_DIR/c/properties/unreach-call.prp" \
    "$PROTOCOL_PROPERTY_COPY"
  activate_formal_research_provenance
  [[ $("$PYTHON_BIN" "${PYTHON_RUNTIME_FLAGS[@]}" -c \
    'import json,sys; print(json.load(open(sys.argv[1]))["source_commit"])' \
    "$PROTOCOL_COPY") == \
    "$(cat "$ACTIVE_RESEARCH_PROVENANCE/research-head.txt")" ]]
  verify_runtime_closure false
  COMPLETE_SENTINEL="$OUTPUT_DIR/summary/.complete"
  if [[ -e "$COMPLETE_SENTINEL" || -L "$COMPLETE_SENTINEL" ]]; then
    if [[ -L "$COMPLETE_SENTINEL" || ! -f "$COMPLETE_SENTINEL" ]] ||
      ! cmp -s -- "$COMPLETE_SENTINEL" <(printf 'complete\n'); then
      echo "invalid completion sentinel; refusing to modify it" >&2
      return 1
    fi
  fi
  if [[ "$RESUMING" == true &&
    -f "$COMPLETE_SENTINEL" && ! -L "$COMPLETE_SENTINEL" ]]; then
    run_python_script "$DATASET_PY" validate-formal-closure \
      --output-root "$OUTPUT_DIR" \
      --manifest "$FORMAL_MANIFEST" --sv-benchmarks "$SV_BENCHMARKS_DIR" \
      --benchmark-definition "$OUTPUT_DIR/generated/hard-case-candidates.xml" \
      --host "$FORMAL_HOST" --mode "$FORMAL_MODE" \
      --repetition-plan \
      "$OUTPUT_DIR/formal-recovery-repetition-1-plan.json" \
      --repetition-plan \
      "$OUTPUT_DIR/formal-recovery-repetition-2-plan.json" \
      --require-complete
    if [[ "$FORMAL_MODE" == cap16 ]]; then
      verify_cap16_phase_evidence
    fi
    verify_all_research_provenance >/dev/null
    verify_runtime_closure true >/dev/null
    return
  fi
  if [[ "$RESUMING" == true ]]; then
    INVOCATION_ARCHIVE="$OUTPUT_DIR/provenance/invocations/$(date +%s%N)"
    mkdir -p "$INVOCATION_ARCHIVE"
    for candidate in \
      "$OUTPUT_DIR/provenance/runtime-closure.txt" \
      "$OUTPUT_DIR/provenance/process-start.txt" \
      "$OUTPUT_DIR/provenance/build.log" \
      "$OUTPUT_DIR/provenance/cgroup-check.log" \
      "$OUTPUT_DIR/provenance/cpachecker-jar-"* \
      "$OUTPUT_DIR/provenance/machine-preflight-"* \
      "$OUTPUT_DIR/provenance/machine-after-failure.json" \
      "$OUTPUT_DIR/provenance/failure-capture-status.txt" \
      "$OUTPUT_DIR/provenance/research-verification-failure.log" \
      "$OUTPUT_DIR/provenance/runtime-verification-failure.log" \
      "$OUTPUT_DIR/provenance/research-verification-final.log" \
      "$OUTPUT_DIR/provenance/runtime-verification-final.log" \
      "$OUTPUT_DIR/provenance/recovery-state-before.json" \
      "$OUTPUT_DIR/provenance/render-formal.log" \
      "$OUTPUT_DIR/provenance/summarize.log" \
      "$OUTPUT_DIR/provenance/artifact-manifest.json"; do
      [[ -e "$candidate" ]] || continue
      mv -- "$candidate" "$INVOCATION_ARCHIVE/"
    done
  fi
  write_runtime_provenance "$OUTPUT_DIR/provenance/runtime-closure.txt"
  "$PYTHON_BIN" "${PYTHON_RUNTIME_FLAGS[@]}" - \
    "$PROTOCOL_COPY" \
    "$OUTPUT_DIR/provenance/runtime-closure.txt" \
    "$EXPECTED_CPACHECKER" "$EXPECTED_SV_BENCHMARKS" \
    "$EXPECTED_BENCHEXEC" "$EXPECTED_JDK" \
    "$(formal_benchexec_workers "$FORMAL_MODE")" <<'PY'
import hashlib
import json
import sys

protocol = json.load(open(sys.argv[1], encoding="utf-8"))
runtime = protocol["runtime"]
expected = {
    "cpachecker_commit": sys.argv[3],
    "sv_benchmarks_commit": sys.argv[4],
    "benchexec_commit": sys.argv[5],
    "jdk_sha256": sys.argv[6],
    "configuration_closure_sha256": hashlib.sha256(
        open(sys.argv[2], "rb").read()
    ).hexdigest(),
    "workers": int(sys.argv[7]),
    "cores_per_worker": 4,
    "p_cores": "0,2,4,6,8,10,12,14",
}
if any(runtime.get(name) != value for name, value in expected.items()):
  raise SystemExit("formal recovery runtime closure differs")
PY
  run_python_script "$DATASET_PY" formal-recovery-state \
    --output-root "$OUTPUT_DIR" \
    --protocol "$PROTOCOL_COPY" \
    --seed-ledger "$SEED_LEDGER_COPY" \
    --manifest "$PROTOCOL_MANIFEST_COPY" \
    --property-file "$PROTOCOL_PROPERTY_COPY" \
    --sv-benchmarks "$SV_BENCHMARKS_DIR" \
    >"$OUTPUT_DIR/provenance/recovery-state-before.json"
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
      verify_all_research_provenance \
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
      verify_all_research_provenance >/dev/null 2>&1
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

  assert_no_sourceless_python_bytecode "$BENCHEXEC_DIR"
  systemd-run --user --quiet --scope --slice=benchexec -p Delegate=yes \
    taskset -c "$P_CORES" \
    "$PYTHON_BIN" "${PYTHON_RUNTIME_FLAGS[@]}" -c \
    "$BENCHEXEC_CGROUP_COMMAND" \
    "$BENCHEXEC_DIR" "$EXPECTED_PYYAML_FILE" --no-thread \
    2>&1 | tee "$OUTPUT_DIR/provenance/cgroup-check.log"

  if [[ "$FORMAL_MODE" == cap8 ]]; then
    copy_phase_evidence "$OUTPUT_DIR/input/evidence"
    PARENT_MANIFEST=$COPIED_PARENT
    PHASE_MANIFESTS=("${COPIED_MANIFESTS[@]}")
    PHASE_RESULTS=("${COPIED_RESULTS[@]}")
    PHASE_SURVIVORS=("${COPIED_SURVIVORS[@]}")
  else
    verify_cap16_phase_evidence
  fi
  run_python_script "$DATASET_PY" validate \
    --manifest "$FORMAL_MANIFEST" \
    --sv-benchmarks "$SV_BENCHMARKS_DIR"

  TASK_COUNT=$("$PYTHON_BIN" "${PYTHON_RUNTIME_FLAGS[@]}" -c \
    'import json,sys; print(json.load(open(sys.argv[1]))["task_count"])' \
    "$FORMAL_MANIFEST")
  if [[ "$FORMAL_MODE" == cap8 && "$TASK_COUNT" -ne 270 ]]; then
    echo "formal manifest task count is not frozen at 270: $TASK_COUNT" >&2
    exit 1
  fi
  if [[ "$TASK_COUNT" -eq 0 ]]; then
    echo "formal Phase B has no authenticated cap-16 survivors" >&2
    exit 1
  fi

  if [[ "$FORMAL_MODE" == cap16 ]]; then
    PHASE_ARGS=(
      --phase-a-output "$CAP16_PHASE_A_OUTPUT"
      --sv-benchmarks "$SV_BENCHMARKS_DIR"
    )
    RENDER_FORMAL_COMMAND=render-cap16-formal
    RENDER_REPLACEMENT_COMMAND=render-cap16-formal-replacement
    SUMMARIZE_COMMAND=summarize-cap16-formal
  else
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
    RENDER_FORMAL_COMMAND=render-formal
    RENDER_REPLACEMENT_COMMAND=render-formal-replacement
    SUMMARIZE_COMMAND=summarize
  fi

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
  [[ $("$PYTHON_BIN" "${PYTHON_RUNTIME_FLAGS[@]}" -c \
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

  if [[ ! -f "$OUTPUT_DIR/generated/hard-case-candidates.xml" ]]; then
    run_python_script "$DATASET_PY" "$RENDER_FORMAL_COMMAND" \
      "${PHASE_ARGS[@]}" \
      --manifest "$FORMAL_MANIFEST" \
      --property-file "$SV_BENCHMARKS_DIR/c/properties/unreach-call.prp" \
      --output-dir "$OUTPUT_DIR/generated" |
      tee "$OUTPUT_DIR/provenance/render-formal.log"
  fi

  if [[
    "$FORMAL_MODE" == cap16 &&
    "$FORMAL_HOST" == athena &&
    -d "$OUTPUT_DIR/provenance/abandoned/repetition-1-1785246981276501974"
  ]]; then
    run_python_script "$DATASET_PY" \
      restore-legacy-cap16-athena-attempt --output-root "$OUTPUT_DIR"
  fi

  run_formal_benchmark() {
    local label=$1
    local name=$2
    local definition=$3
    local output=$4
    local repetition=$5
    local role=primary
    [[ "$label" == *-replacement-* ]] && role=replacement
    local benchexec_status
    local result
    local marker="$OUTPUT_DIR/provenance/attempts/$label.json"
    local authorization="$OUTPUT_DIR/provenance/authorizations/$label.json"
    local benchexec_process="$OUTPUT_DIR/provenance/$label-benchexec.process.json"
    local process_descriptor="$OUTPUT_DIR/provenance/$label-process-descriptor.json"
    local recovery_research_head
    recovery_research_head=$(cat \
      "$ACTIVE_RESEARCH_PROVENANCE/research-head.txt")
    [[ "$recovery_research_head" =~ ^[0-9a-f]{40}$ ]]
    local recovery_directory="$OUTPUT_DIR/provenance/recoveries/$label/$recovery_research_head"
    local unit
    ATTEMPT_ABANDONED=false
    local -a attempt_common=(
      --output-root "$OUTPUT_DIR"
      --manifest "$FORMAL_MANIFEST"
      --sv-benchmarks "$SV_BENCHMARKS_DIR"
      --host "$FORMAL_HOST"
      --mode "$FORMAL_MODE"
      --label "$label"
      --role "$role"
      --repetition "$repetition"
      --definition "$definition"
      --benchexec-log "$OUTPUT_DIR/provenance/$label-benchexec.log"
      --benchexec-process "$benchexec_process"
      --process-descriptor "$process_descriptor"
      --load-monitor "$OUTPUT_DIR/provenance/$label-load-monitor.jsonl"
      --monitor-pid "$OUTPUT_DIR/provenance/$label-load-monitor.jsonl.pid"
      --monitor-process "$OUTPUT_DIR/provenance/$label-load-monitor.jsonl.process.json"
      --machine-before "$OUTPUT_DIR/provenance/machine-before-$label.json"
    )
    local -a attempt_descriptor=(
      "${attempt_common[@]}"
      --monitor-stopped "$OUTPUT_DIR/provenance/$label-load-monitor.jsonl.stopped"
      --machine-after "$OUTPUT_DIR/provenance/machine-after-$label.json"
      --machine-check "$OUTPUT_DIR/provenance/machine-check-$label.json"
      --output "$marker"
    )
    local -a recovery_attempt_descriptor=(
      "${attempt_common[@]}"
      --monitor-stopped "$recovery_directory/monitor-stopped"
      --machine-after "$recovery_directory/machine-after.json"
      --machine-check "$recovery_directory/machine-check.json"
      --output "$marker"
    )
    abandon_current_pretask() {
      local exit_value=$1
      shift
      local name
      local path
      local -a evidence_args=()
      local -a exit_args=()
      if [[ "$exit_value" != unobserved ]]; then
        exit_args=(--benchexec-exit "$exit_value")
      fi
      while (($#)); do
        name=$1
        path=$2
        shift 2
        if [[ -e "$path" || -L "$path" ]]; then
          if [[ ! -f "$path" || -L "$path" ]]; then
            echo "pre-task evidence is not a regular file: $path" >&2
            return 1
          fi
          evidence_args+=("--${name//_/-}" "$path")
        fi
      done
      run_python_script "$DATASET_PY" \
        abandon-formal-recovery-pretask \
        --output-root "$OUTPUT_DIR" \
        --protocol "$PROTOCOL_COPY" \
        --seed-ledger "$SEED_LEDGER_COPY" \
        --manifest "$PROTOCOL_MANIFEST_COPY" \
        --property-file "$PROTOCOL_PROPERTY_COPY" \
        --sv-benchmarks "$SV_BENCHMARKS_DIR" \
        --label "$label" "${exit_args[@]}" \
        --process-descriptor "$process_descriptor" \
        "${evidence_args[@]}" >/dev/null
      ATTEMPT_ABANDONED=true
    }
    authenticate_formal_attempt() {
      local status=$1
      local result_path=$2
      if [[ "$status" -eq 125 ]]; then
        run_python_script "$DATASET_PY" formal-attempt-complete \
          "${recovery_attempt_descriptor[@]}" \
          --benchexec-exit "$status" \
          --result "$result_path"
      else
        run_python_script "$DATASET_PY" formal-attempt-complete \
          "${attempt_descriptor[@]}" \
          --benchexec-exit "$status" \
          --result "$result_path"
      fi
    }
    mkdir -p "$output"
    if [[ -f "$marker" ]]; then
      result=$(single_formal_result "$output")
      run_python_script "$DATASET_PY" validate-formal-attempt \
        --output-root "$OUTPUT_DIR" --manifest "$FORMAL_MANIFEST" \
        --sv-benchmarks "$SV_BENCHMARKS_DIR" --host "$FORMAL_HOST" \
        --mode "$FORMAL_MODE" --label "$label" --role "$role" \
        --repetition "$repetition" --definition "$definition" \
        --result "$result" --marker "$marker" >/dev/null
      return
    fi
    if [[ -e "$authorization" || -L "$authorization" ]]; then
      if [[ ! -f "$authorization" || -L "$authorization" ]]; then
        echo "formal recovery authorization is not a regular file" >&2
        return 1
      fi
      if [[ -z $(find "$output" -mindepth 1 -print -quit) ]]; then
        local authorization_boot
        local current_boot
        local lifecycle_present=false
        authorization_boot=$("$PYTHON_BIN" "${PYTHON_RUNTIME_FLAGS[@]}" -c \
          'import json,sys; print(json.load(open(sys.argv[1]))["boot_id"])' \
          "$authorization")
        current_boot=$(< /proc/sys/kernel/random/boot_id)
        for candidate in \
          "$OUTPUT_DIR/provenance/$label-benchexec.log" \
          "$benchexec_process" \
          "$OUTPUT_DIR/provenance/$label-load-monitor.jsonl" \
          "$OUTPUT_DIR/provenance/$label-load-monitor.jsonl.pid" \
          "$OUTPUT_DIR/provenance/$label-load-monitor.jsonl.process.json" \
          "$OUTPUT_DIR/provenance/$label-load-monitor.jsonl.stopped" \
          "$OUTPUT_DIR/provenance/machine-before-$label.json" \
          "$OUTPUT_DIR/provenance/machine-after-$label.json" \
          "$OUTPUT_DIR/provenance/machine-check-$label.json"; do
          if [[ -e "$candidate" || -L "$candidate" ]]; then
            lifecycle_present=true
            break
          fi
        done
        if [[ "$authorization_boot" != "$current_boot" ||
          "$lifecycle_present" == true ]]; then
          abandon_current_pretask unobserved \
            benchexec_log \
            "$OUTPUT_DIR/provenance/$label-benchexec.log" \
            benchexec_process "$benchexec_process" \
            load_monitor \
            "$OUTPUT_DIR/provenance/$label-load-monitor.jsonl" \
            monitor_pid \
            "$OUTPUT_DIR/provenance/$label-load-monitor.jsonl.pid" \
            monitor_process \
            "$OUTPUT_DIR/provenance/$label-load-monitor.jsonl.process.json" \
            monitor_stopped \
            "$OUTPUT_DIR/provenance/$label-load-monitor.jsonl.stopped" \
            machine_before \
            "$OUTPUT_DIR/provenance/machine-before-$label.json" \
            machine_after \
            "$OUTPUT_DIR/provenance/machine-after-$label.json" \
            machine_check \
            "$OUTPUT_DIR/provenance/machine-check-$label.json"
          return
        fi
      fi
    fi
    if [[ -n $(find "$output" -mindepth 1 -print -quit) ||
      -e "$OUTPUT_DIR/provenance/$label-load-monitor.jsonl.process.json" ||
      -e "$benchexec_process" ]]; then
      local process_identity="$OUTPUT_DIR/provenance/$label-load-monitor.jsonl.process.json"
      result=$(single_formal_result "$output")
      for candidate in \
        "$process_descriptor" \
        "$process_identity" \
        "$OUTPUT_DIR/provenance/$label-load-monitor.jsonl.pid" \
        "$OUTPUT_DIR/provenance/$label-load-monitor.jsonl" \
        "$benchexec_process" \
        "$OUTPUT_DIR/provenance/machine-before-$label.json" \
        "$OUTPUT_DIR/provenance/$label-benchexec.log" \
        "$result"; do
        if [[ -L "$candidate" || ! -f "$candidate" ]]; then
          echo "unclosed attempt lacks regular recovery evidence: $candidate" >&2
          return 1
        fi
      done
      JAVA_HOME="$JAVA_HOME" run_python_script "$DATASET_PY" \
        recover-formal-attempt "${recovery_attempt_descriptor[@]}" \
        --research-provenance "$ACTIVE_RESEARCH_PROVENANCE" \
        --result "$result"
      return
    fi
    if [[ ! -f "$process_descriptor" || -L "$process_descriptor" ]]; then
      run_python_script "$DATASET_PY" write-formal-process-descriptor \
        --output-root "$OUTPUT_DIR" --mode "$FORMAL_MODE" \
        --label "$label" --host "$FORMAL_HOST" --name "$name" \
        --definition "$definition" --result-output "$output" \
        --monitor-output "$OUTPUT_DIR/provenance/$label-load-monitor.jsonl" \
        --monitor-exclude-root "$$" --dataset-py "$DATASET_PY" \
        --cpachecker-dir "$CPACHECKER_DIR" \
        --benchexec-dir "$BENCHEXEC_DIR" --python-bin "$PYTHON_BIN" \
        --java-home "$JAVA_HOME" --p-cores "$P_CORES" \
        --output "$process_descriptor"
    fi
    run_python_script "$DATASET_PY" authorize-formal-recovery-attempt \
      --output-root "$OUTPUT_DIR" \
      --protocol "$PROTOCOL_COPY" \
      --seed-ledger "$SEED_LEDGER_COPY" \
      --manifest "$PROTOCOL_MANIFEST_COPY" \
      --property-file "$PROTOCOL_PROPERTY_COPY" \
      --sv-benchmarks "$SV_BENCHMARKS_DIR" \
      --process-descriptor "$process_descriptor" \
      --label "$label" --repetition "$repetition" >/dev/null
    unit=$(run_python_script "$DATASET_PY" formal-systemd-unit \
      --output-root "$OUTPUT_DIR" --mode "$FORMAL_MODE" --label "$label")
    JAVA_HOME="$JAVA_HOME" run_python_script "$BASELINE_PY" machine \
      --output "$OUTPUT_DIR/provenance/machine-before-$label.json"
    start_process_monitor "$OUTPUT_DIR/provenance/$label-load-monitor.jsonl"
    wait_for_process_monitor
    assert_no_sourceless_python_bytecode "$BENCHEXEC_DIR"
    set +e
    (
      cd "$CPACHECKER_DIR"
      "$PYTHON_BIN" "${PYTHON_RUNTIME_FLAGS[@]}" - \
        "$benchexec_process" "$unit" \
        systemd-run --user --quiet --scope --unit="$unit" \
        --slice=benchexec -p Delegate=yes \
        taskset -c "$P_CORES" env -i \
        HOME=/home/benchexec LANG=C.UTF-8 LC_ALL=C.UTF-8 PATH=/usr/bin:/bin \
        JAVA="$JAVA_HOME/bin/java" \
        "$PYTHON_BIN" "${PYTHON_RUNTIME_FLAGS[@]}" -c \
        "$BENCHEXEC_MODULE_COMMAND" \
        "$BENCHEXEC_DIR" "$EXPECTED_PYYAML_FILE" \
        --name "$name" \
        --tool-directory "$CPACHECKER_DIR" \
        --outputpath "$output/" \
        --allowedCores "$P_CORES" \
        --no-hyperthreading \
        --container \
        --read-only-dir / \
        --hidden-dir /home \
        --overlay-dir "$CPACHECKER_DIR" \
        -N "$(formal_benchexec_workers "$FORMAL_MODE")" -c 4 \
        "$definition" <<'PY'
import json
import os
import sys
from pathlib import Path

output, unit, *argv = sys.argv[1:]
proc = Path("/proc/self")
status = proc.joinpath("status").read_text()
uid = int(next(line for line in status.splitlines() if line.startswith("Uid:")).split()[1])
stat = proc.joinpath("stat").read_text()
starttime = int(stat[stat.rfind(")") + 2:].split()[19])
identity = {
    "schema_version": "formal-owned-process-identity-v2",
    "role": "benchexec-launcher",
    "uid": uid,
    "pid": os.getpid(),
    "proc_starttime": starttime,
    "argv": argv,
    "systemd_unit": unit,
    "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
}
Path(output).write_text(json.dumps(identity, indent=2) + "\n")
os.execvp(argv[0], argv)
PY
    ) 2>&1 | tee "$OUTPUT_DIR/provenance/$label-benchexec.log"
    benchexec_status=${PIPESTATUS[0]}
    set -e
    stop_process_monitor
    JAVA_HOME="$JAVA_HOME" run_python_script "$BASELINE_PY" machine \
      --output "$OUTPUT_DIR/provenance/machine-after-$label.json"
    run_python_script "$BASELINE_PY" machine-check \
      --before "$OUTPUT_DIR/provenance/machine-before-$label.json" \
      --after "$OUTPUT_DIR/provenance/machine-after-$label.json" |
      tee "$OUTPUT_DIR/provenance/machine-check-$label.json"
    if [[ "$benchexec_status" -ne 0 && "$benchexec_status" -ne 130 ]]; then
      if [[ -z $(find "$output" -mindepth 1 -print -quit) ]]; then
        abandon_current_pretask "$benchexec_status" \
          benchexec_log \
          "$OUTPUT_DIR/provenance/$label-benchexec.log" \
          benchexec_process "$benchexec_process" \
          load_monitor \
          "$OUTPUT_DIR/provenance/$label-load-monitor.jsonl" \
          monitor_pid \
          "$OUTPUT_DIR/provenance/$label-load-monitor.jsonl.pid" \
          monitor_process \
          "$OUTPUT_DIR/provenance/$label-load-monitor.jsonl.process.json" \
          monitor_stopped \
          "$OUTPUT_DIR/provenance/$label-load-monitor.jsonl.stopped" \
          machine_before \
          "$OUTPUT_DIR/provenance/machine-before-$label.json" \
          machine_after \
          "$OUTPUT_DIR/provenance/machine-after-$label.json" \
          machine_check \
          "$OUTPUT_DIR/provenance/machine-check-$label.json"
        return
      fi
      return "$benchexec_status"
    fi
    result=$(single_formal_result "$output")
    authenticate_formal_attempt "$benchexec_status" "$result"
  }

  recovery_pending_count() {
    local repetition=$1
    run_python_script "$DATASET_PY" formal-recovery-state \
      --output-root "$OUTPUT_DIR" \
      --protocol "$PROTOCOL_COPY" \
      --seed-ledger "$SEED_LEDGER_COPY" \
      --manifest "$PROTOCOL_MANIFEST_COPY" \
      --property-file "$PROTOCOL_PROPERTY_COPY" \
      --sv-benchmarks "$SV_BENCHMARKS_DIR" |
      "$PYTHON_BIN" "${PYTHON_RUNTIME_FLAGS[@]}" -c \
        'import json,sys; print(json.load(sys.stdin)["pending"][sys.argv[1]])' \
        "$repetition"
  }

  run_recovery_repetition() {
    local repetition=$1
    local plan="$OUTPUT_DIR/formal-recovery-repetition-$repetition-plan.json"
    local prepared
    local complete
    local label
    local definition
    local result
    local taint
    local before
    local after
    while true; do
      prepared=$(run_python_script "$DATASET_PY" \
        prepare-formal-recovery-shard \
        --output-root "$OUTPUT_DIR" \
        --protocol "$PROTOCOL_COPY" \
        --seed-ledger "$SEED_LEDGER_COPY" \
        --manifest "$PROTOCOL_MANIFEST_COPY" \
        --property-file "$PROTOCOL_PROPERTY_COPY" \
        --sv-benchmarks "$SV_BENCHMARKS_DIR" \
        --repetition "$repetition" | tail -n 1)
      complete=$("$PYTHON_BIN" "${PYTHON_RUNTIME_FLAGS[@]}" -c \
        'import json,sys; print(str(json.loads(sys.argv[1])["complete"]).lower())' \
        "$prepared")
      if [[ "$complete" == true ]]; then
        break
      fi
      label=$("$PYTHON_BIN" "${PYTHON_RUNTIME_FLAGS[@]}" -c \
        'import json,sys; print(json.loads(sys.argv[1])["label"])' \
        "$prepared")
      definition="$OUTPUT_DIR/generated/$label/hard-case-candidates.xml"
      before=$(recovery_pending_count "$repetition")
      run_formal_benchmark "$label" \
        "hard-case-dataset-v2${FORMAL_BENCHMARK_SCOPE}-formal-$FORMAL_HOST-$label" \
        "$definition" "$OUTPUT_DIR/results/$label" "$repetition"
      if [[ "$ATTEMPT_ABANDONED" == true ]]; then
        continue
      fi
      result=$(single_formal_result "$OUTPUT_DIR/results/$label")
      taint="$OUTPUT_DIR/$label-taint.json"
      if [[ ! -f "$taint" ]]; then
        run_python_script "$DATASET_PY" formal-taint \
          --manifest "$PROTOCOL_MANIFEST_COPY" \
          --repetition "$repetition" \
          --result "$result" \
          --benchexec-log "$OUTPUT_DIR/provenance/$label-benchexec.log" \
          --load-monitor "$OUTPUT_DIR/provenance/$label-load-monitor.jsonl" \
          --attempt-marker "$OUTPUT_DIR/provenance/attempts/$label.json" \
          --output-root "$OUTPUT_DIR" \
          --sv-benchmarks "$SV_BENCHMARKS_DIR" \
          --host "$FORMAL_HOST" --mode "$FORMAL_MODE" \
          --output "$taint"
      fi
      run_python_script "$DATASET_PY" accept-formal-recovery-attempt \
        --output-root "$OUTPUT_DIR" \
        --protocol "$PROTOCOL_COPY" \
        --seed-ledger "$SEED_LEDGER_COPY" \
        --manifest "$PROTOCOL_MANIFEST_COPY" \
        --property-file "$PROTOCOL_PROPERTY_COPY" \
        --sv-benchmarks "$SV_BENCHMARKS_DIR" \
        --label "$label" --taint-manifest "$taint" >/dev/null
      after=$(recovery_pending_count "$repetition")
      if ((after >= before)); then
        echo "formal recovery shard made no accepted progress; evidence preserved" >&2
        return 75
      fi
    done
    if [[ ! -f "$plan" ]]; then
      run_python_script "$DATASET_PY" export-formal-recovery-plan \
        --output-root "$OUTPUT_DIR" \
        --protocol "$PROTOCOL_COPY" \
        --seed-ledger "$SEED_LEDGER_COPY" \
        --manifest "$PROTOCOL_MANIFEST_COPY" \
        --property-file "$PROTOCOL_PROPERTY_COPY" \
        --sv-benchmarks "$SV_BENCHMARKS_DIR" \
        --repetition "$repetition" --output "$plan" >/dev/null
    fi
    PLANS+=("$plan")
  }

  PLANS=()
  run_recovery_repetition 1
  run_recovery_repetition 2

  SUMMARY_STAGE="$OUTPUT_DIR/summary.staging"
  if [[ -e "$SUMMARY_STAGE" ]]; then
    mkdir -p "$OUTPUT_DIR/provenance/abandoned"
    mv -- "$SUMMARY_STAGE" \
      "$OUTPUT_DIR/provenance/abandoned/summary-staging-$(date +%s%N)"
  fi
  run_python_script "$DATASET_PY" "$SUMMARIZE_COMMAND" \
    "${PHASE_ARGS[@]}" \
    --manifest "$FORMAL_MANIFEST" \
    --benchmark-definition "$OUTPUT_DIR/generated/hard-case-candidates.xml" \
    --repetition-plan "${PLANS[0]}" \
    --repetition-plan "${PLANS[1]}" \
    --output-dir "$SUMMARY_STAGE" \
    --hard-threshold 200 \
    2>&1 | tee "$OUTPUT_DIR/provenance/summarize.log"
  if [[ -d "$OUTPUT_DIR/summary" ]]; then
    if diff -r -- "$OUTPUT_DIR/summary" "$SUMMARY_STAGE"; then
      rm -rf -- "$SUMMARY_STAGE"
    else
      mkdir -p "$OUTPUT_DIR/provenance/abandoned"
      mv -- "$OUTPUT_DIR/summary" \
        "$OUTPUT_DIR/provenance/abandoned/summary-$(date +%s%N)"
      mv -- "$SUMMARY_STAGE" "$OUTPUT_DIR/summary"
    fi
  else
    mv -- "$SUMMARY_STAGE" "$OUTPUT_DIR/summary"
  fi

  verify_all_research_provenance \
    >"$OUTPUT_DIR/provenance/research-verification-final.log" 2>&1
  verify_runtime_closure true \
    >"$OUTPUT_DIR/provenance/runtime-verification-final.log" 2>&1
  run_python_script "$BASELINE_PY" artifact-manifest \
    --root "$OUTPUT_DIR" \
    --output "$OUTPUT_DIR/provenance/artifact-manifest.json"
  if [[ "$FORMAL_MODE" == cap16 ]]; then
    verify_cap16_phase_evidence
  fi
  verify_all_research_provenance >/dev/null
  verify_runtime_closure true >/dev/null
  run_python_script "$DATASET_PY" validate-formal-closure \
    --output-root "$OUTPUT_DIR" \
    --manifest "$FORMAL_MANIFEST" --sv-benchmarks "$SV_BENCHMARKS_DIR" \
    --benchmark-definition "$OUTPUT_DIR/generated/hard-case-candidates.xml" \
    --host "$FORMAL_HOST" --mode "$FORMAL_MODE" \
    --repetition-plan "${PLANS[0]}" \
    --repetition-plan "${PLANS[1]}"
  run_python_script "$DATASET_PY" write-complete-sentinel \
    --output "$COMPLETE_SENTINEL"
  run_python_script "$DATASET_PY" validate-formal-closure \
    --output-root "$OUTPUT_DIR" \
    --manifest "$FORMAL_MANIFEST" --sv-benchmarks "$SV_BENCHMARKS_DIR" \
    --benchmark-definition "$OUTPUT_DIR/generated/hard-case-candidates.xml" \
    --host "$FORMAL_HOST" --mode "$FORMAL_MODE" \
    --repetition-plan "${PLANS[0]}" \
    --repetition-plan "${PLANS[1]}" \
    --require-complete
  trap - EXIT
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main cap8 "$@"
fi
