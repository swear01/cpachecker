#!/usr/bin/env python3

# This file is part of CPAchecker,
# a tool for configurable software verification:
# https://cpachecker.sosy-lab.org
#
# SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>
#
# SPDX-License-Identifier: Apache-2.0

import argparse
import bz2
import collections
import csv
import datetime
import hashlib
import importlib.util
import json
import os
import re
import signal
import shutil
import stat
import statistics
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("baseline", Path(__file__).with_name("baseline.py"))
baseline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(baseline)

LOOP = re.compile(r"\b(?:while|for)\s*\(|\bdo\s*\{")
ERROR_CALL = re.compile(r"\b(?:reach_error|__VERIFIER_error)\s*\(")
SOURCE_REFERENCE = re.compile(r"(?<![-\w./])([\w./+-]+\.c)(?![\w./])")
SOURCE_LICENSES = {
    "cbmc": "BSD-4-Clause",
    "esbmc": "Apache-2.0 AND BSD-4-Clause",
    "seahorn": "BSD-3-Clause-CMU",
}
SOURCE_LICENSE_FILES = {
    "cbmc": "LICENSE",
    "esbmc": "COPYING",
    "seahorn": "license.txt",
}
SOURCE_URLS = {
    "cbmc": "https://github.com/diffblue/cbmc",
    "esbmc": "https://github.com/esbmc/esbmc",
    "seahorn": "https://github.com/seahorn/seahorn",
    "sv-benchmarks": "https://gitlab.com/sosy-lab/benchmarking/sv-benchmarks",
}
ANALYSIS_UNSOLVED = {"timeout", "out_of_memory", "unknown"}
DISCOVERY_HOSTS = ("athena", "cthulhu", "valkyrie")
REROUTE_HOSTS = ("athena", "valkyrie")
FROZEN_CTHULHU_MANIFEST_SHA256 = (
    "40bda9c755c88d9b617269aaa6e1c66ceea07fb818e0741f8a1f960536bd6d4b"
)
FROZEN_ATHENA_MANIFEST_SHA256 = (
    "5b0224af541b371fd8f882cf71099b774fdd33dc3187cf6dca31cc3c8ca55cef"
)
FROZEN_ATHENA_REROUTE_MANIFEST_SHA256 = (
    "477374a2bbab9fd8559e1945e6781b5484e26afec7808266332423c1db9cddd6"
)
FROZEN_ATHENA_RECOVERY_MANIFEST_SHA256 = (
    "59681ac7dbbf177ae6a4ce3cfd3bd5e5b45d57658c1d6ed467c74e1cd4f60f04"
)
FROZEN_PARENT_MANIFEST_SHA256 = (
    "6b5b997c424c8649d9492a84caae1b486b6936e2e843a1d43a22944cae39ac3c"
)
FROZEN_PHASE_A_MANIFEST_SHA256 = {
    "original_valkyrie": (
        "64f25378a401f1936fc836b5901c96d304f9c654f5c9d4cf17327e086463930d"
    ),
    "reroute_valkyrie": (
        "6c5e9d46d83f9cb644cc37d9651511102cc27ce539bed7024e8b14f1698aae29"
    ),
    "recovery_valkyrie": FROZEN_ATHENA_RECOVERY_MANIFEST_SHA256,
}
FROZEN_PHASE_A_RESULT_SHA256 = {
    "original_valkyrie": (
        "c4e8b1d3d375c35f666f8b31c34ad7381be7119016071f739a873d817bcddca1"
    ),
    "reroute_valkyrie": (
        "3b0ba3c391523935f9470e2cadad2709c9249322ed25f70669c291d77c8ba6c3"
    ),
    "recovery_valkyrie": (
        "bfb0d1182a8e0797a6507b03942eb7f4fa3508931e5be84d70ca515e09d64ab2"
    ),
}
FROZEN_PHASE_A_SURVIVOR_SHA256 = {
    "original_valkyrie": (
        "95e59919dbabe5c9a3e6de18b459214be7c849840191455b08794b91fb299b77"
    ),
    "reroute_valkyrie": (
        "21635e3fe3ad5ae80b4be4e7801cd400b88284aff1ce358ffd1a9c970e82da2b"
    ),
    "recovery_valkyrie": (
        "235a4f5c70aa9322197329a572ea21af12ec36758e3afedb69fc8931ea27a628"
    ),
}
FROZEN_PHASE_A_SURVIVOR_TASK_COUNT = {
    "original_valkyrie": 91,
    "reroute_valkyrie": 45,
    "recovery_valkyrie": 134,
}
FROZEN_FORMAL_MANIFEST_SHA256 = (
    "e8aed1d26a0920bfef4964d495d86b69bbad666efb8d72e87462f297ca243855"
)
FROZEN_CAP16_ATHENA_MANIFEST_SHA256 = (
    "16e5f9ff04ed08ef9c29d8674021c11de3eed87b9da6a8c1e2ef68c6847ec0bb"
)
FROZEN_CAP16_PARENT_MANIFEST_SHA256 = (
    "490f2337d68fba626f34eed05abb64c772c752289bab31689b354240d2146876"
)
FROZEN_CAP16_PHASE_A_TASK_COUNT = 254
FROZEN_CAP16_PHASE_A_PACKAGE_AGGREGATE_SHA256 = (
    "b0ce4f33ad505df816d559a4260d8cc75f96a9914b9396e214fe9c2e3ecf5dee"
)
FROZEN_CAP16_PHASE_A_SURVIVOR_SHA256 = (
    "7ad21cb5ca4360689f00dca6f3a5eb7ec2385b9793315cfe5828892ded0ab49f"
)
FROZEN_CAP16_FORMAL_ARTIFACT_AGGREGATE_SHA256 = (
    "PENDING_AFTER_CAP16_FORMAL_COMPLETION"
)
FROZEN_CAP8_FORMAL_ARTIFACT_AGGREGATE_SHA256 = (
    "PENDING_AFTER_CAP8_R8_FORMAL_COMPLETION"
)
FROZEN_CAP8_FORMAL_PACKAGE_MANIFEST_SHA256 = (
    "a20797345df1bef6d5be5356906ee106b75b374b0d6cd2adfbc56cc5c3e65fef"
)
FROZEN_CAP8_FORMAL_PACKAGE_AGGREGATE_SHA256 = (
    "6c4592e158e037179d431f161c87cb494c7a22b00a9774d689ebe9b94b58f14c"
)
FROZEN_CAP8_FORMAL_TASK_COUNT = 270
FROZEN_CAP8_RESEARCH_HEAD = "558e54c5da5982db46ffb8fbca4704f4b6e03f21"
FROZEN_CAP8_RESEARCH_INVENTORY_SHA256 = (
    "a183f08ff2459ffa9102f1638d31183bb5c6b7fd7e8531deaf35b33e52c8f4f9"
)
FROZEN_CAP8_RUNTIME_CLOSURE = {
    "stock_lib_java_sha256":
        "eea0df062de5c8e3febe0d96b583741c140e79d3ae41a87a56d7be365b876f9d",
    "jdk_sha256":
        "867ff62e01a0936fc0a90ceae27338be1973559767ef0717896f8d64f780ece6",
    "ant_install": "/home/swear01/.local/opt/ant/usr",
    "ant_install_sha256":
        "52772e241e78a875fa00dea891eac2023d4f2be639a5f28a17dca81580f75e5b",
    "ant_version":
        "Apache Ant(TM) version 1.10.12 compiled on January 17 1970",
    "python_real": "/usr/bin/python3.10",
    "python_sha256":
        "7d51cd6b48b521277f5caa4610a82126e315fa2be4df069823a8b1eeb5bd4a86",
    "python_version": "Python 3.10.12",
    "python_stdlib": "/usr/lib/python3.10",
    "python_stdlib_sha256":
        "eef7994f6b57cb0bbdb803ef6aadc0c1afbe61d444932eeef5dc5c114b6cf27b",
    "python_dist_packages": "/usr/lib/python3/dist-packages",
    "python_dist_packages_sha256":
        "0970024a48206a1937b5bfbf889335525b769b89a27ca7df25d793d7727b909c",
    "python_local_dist_packages":
        "/usr/local/lib/python3.10/dist-packages",
    "python_local_dist_packages_sha256":
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "python_environment":
        '{"python_executable":"/usr/bin/python3.10","sys_path":'
        '["/var/tmp/swear01-cpachecker-paper/benchexec",'
        '"/usr/lib/python310.zip","/usr/lib/python3.10",'
        '"/usr/lib/python3.10/lib-dynload",'
        '"/usr/local/lib/python3.10/dist-packages",'
        '"/usr/lib/python3/dist-packages"],'
        '"yaml_file":"/usr/lib/python3/dist-packages/yaml/__init__.py",'
        '"yaml_version":"5.4.1"}',
    "benchexec_archive_sha256":
        "75e3332253429e6f9186352a255cd96c0aff6154a95e2fdd3b737c143ba018bc",
    "benchexec_version": "benchexec 3.35-dev",
}
PHASE_A_OPERATION = {
    "original_valkyrie": "deterministic_stratified_shard",
    "reroute_valkyrie": "deterministic_stratified_reroute",
    "recovery_valkyrie": "ordered_athena_recovery_merge",
}
FROZEN_CPACHECKER_VERSION = "4.2.2-2417-g1848f9eb59"
FROZEN_BENCHEXEC_GENERATOR = "BenchExec 3.35-dev"
FROZEN_TOOLMODULE = "benchexec.tools.cpachecker"
DISCOVERY_DISPLAY = "CPAchecker frozen stock hard-case discovery screen"
FORMAL_DISPLAY = "CPAchecker frozen stock hard-case formal measurement"
PROBE_DISPLAY = "VGuide no-candidate CEGAR eligibility probe"
FORMAL_REPETITION_PLAN_SCHEMA = "hard-case-formal-repetition-plan-v1"
CAP16_FORMAL_REPETITION_PLAN_SCHEMA = (
    "hard-case-cap16-formal-repetition-plan-v1"
)
FORMAL_TAINT_SCHEMA = "hard-case-formal-taint-v1"
CAP16_PROBE_TAINT_SCHEMA = "hard-case-cap16-cegar-probe-taint-v1"
CAP16_PROBE_PLAN_SCHEMA = "hard-case-cap16-cegar-probe-plan-v1"
CAP16_PROBE_INPUT_SCHEMA = "hard-case-cap16-cegar-probe-input-v1"
CAP16_PROBE_SUMMARY_SCHEMA = "hard-case-cap16-cegar-probe-summary-v1"
CAP8_PROBE_TAINT_SCHEMA = "hard-case-cap8-cegar-probe-taint-v1"
CAP8_PROBE_PLAN_SCHEMA = "hard-case-cap8-cegar-probe-plan-v1"
CAP8_PROBE_INPUT_SCHEMA = "hard-case-cap8-cegar-probe-input-v1"
CAP8_PROBE_SUMMARY_SCHEMA = "hard-case-cap8-cegar-probe-summary-v1"
STRICT_PROBE_STRATA = (
    ("cegar-eligible.csv", "cegar_eligible"),
    ("no-event.csv", "no_event"),
    ("hook-reached-without-loop-head.csv", "hook_reached_without_loop_head"),
    ("infrastructure-failure.csv", "infrastructure_failure"),
)
CAP16_PROBE_STRATA = STRICT_PROBE_STRATA
SCREEN_REPETITION_PLAN_SCHEMA = "hard-case-screen-repetition-plan-v1"
SCREEN_TAINT_SCHEMA = "hard-case-screen-taint-v1"
FORMAL_TAINT_REASONS = {
    "foreign_p_core_contention",
    "interrupted_incomplete",
}
FORMAL_P_CORE_CPUS = tuple(range(16))
FORMAL_FOREIGN_CPU_PERCENT = 50.0
FORMAL_FOREIGN_CPU_SECONDS = 10.0
FORMAL_LOAD_SAMPLE_SECONDS = 1.0
FORMAL_LOAD_MONITOR_SCHEMA = "formal-p-core-load-monitor-v1"
FORMAL_ATTEMPT_SCHEMA = "hard-case-formal-attempt-complete-v3"
FORMAL_PROCESS_DESCRIPTOR_SCHEMA = "hard-case-formal-process-descriptor-v2"
FORMAL_P_CORE_LIST = "0,2,4,6,8,10,12,14"
FORMAL_PYYAML_FILE = "/usr/lib/python3/dist-packages/yaml/__init__.py"
PYTHON_RUNTIME_FLAGS = (
    "-I",
    "-S",
    "-B",
    "-X",
    "pycache_prefix=/dev/null",
)
BENCHEXEC_MODULE_COMMAND = (
    "import importlib.util,runpy,sys; from pathlib import Path; "
    "repository=sys.argv.pop(1); yaml_file=sys.argv.pop(1); "
    'spec=importlib.util.spec_from_file_location("yaml",yaml_file,'
    "submodule_search_locations=[str(Path(yaml_file).parent)]); "
    "assert spec is not None and spec.loader is not None; "
    "yaml=importlib.util.module_from_spec(spec); "
    'sys.modules["yaml"]=yaml; spec.loader.exec_module(yaml); '
    "sys.path.insert(0,repository); "
    'sys.argv[0]="benchexec"; '
    'runpy.run_module("benchexec.benchexec",run_name="__main__")'
)
EMPTY_PROVIDER_MODEL = "deterministic-empty-provider"
EMPTY_PROVIDER_RESPONSE_SHA256 = (
    "950ec9013b84aed3afe9761427511822630e80cd5f009e837389312830deba94"
)


def strict_probe_profile(cohort):
  profiles = {
      "cap8": {
          "host": "valkyrie",
          "manifest_name": "candidate-manifest-cap8-probe.json",
          "input_schema": CAP8_PROBE_INPUT_SCHEMA,
          "plan_schema": CAP8_PROBE_PLAN_SCHEMA,
          "taint_schema": CAP8_PROBE_TAINT_SCHEMA,
          "summary_schema": CAP8_PROBE_SUMMARY_SCHEMA,
          "row_provenance_schema":
              "hard-case-cap8-cegar-probe-row-provenance-v1",
          "accepted_labels": {"stable_hard_solved", "stable_unsolved"},
          "operation": "cap8_zero_candidate_probe_input",
      },
      "cap16": {
          "host": "athena",
          "manifest_name": "candidate-manifest-cap16-probe.json",
          "input_schema": CAP16_PROBE_INPUT_SCHEMA,
          "plan_schema": CAP16_PROBE_PLAN_SCHEMA,
          "taint_schema": CAP16_PROBE_TAINT_SCHEMA,
          "summary_schema": CAP16_PROBE_SUMMARY_SCHEMA,
          "row_provenance_schema":
              "hard-case-cap16-cegar-probe-row-provenance-v1",
          "accepted_labels": {
              "stable_hard_solved",
              "stable_analysis_unsolved",
          },
          "operation": "cap16_zero_candidate_probe_input",
      },
  }
  try:
    return profiles[cohort]
  except KeyError as error:
    raise RuntimeError(f"unknown strict probe cohort: {cohort}") from error


def is_strict_probe_mode(mode):
  return mode in {"cap8-probe", "cap16-probe"}


def sha256_text(value):
  return hashlib.sha256(value.encode("utf-8")).hexdigest()


def family_name(component):
  return re.sub(r"[-_]?\d.*$", "", component) or component


def family_cap(candidates, limit):
  groups = collections.defaultdict(list)
  for candidate in candidates:
    key = (
        candidate["family"],
        candidate["seed_class"],
        candidate["expected_verdict"],
    )
    groups[key].append(candidate)
  selected = []
  for group in groups.values():
    selected.extend(
        sorted(group, key=lambda row: sha256_text(row["task"]))[:limit]
    )
  return sorted(selected, key=lambda row: row["task"])


def classify_repetitions(rows, hard_threshold):
  if any(row["category"] == "wrong" for row in rows):
    return "wrong_quarantine"
  if any(
      row.get("classification") == "infrastructure_or_manifest_failure"
      for row in rows
  ):
    return "infrastructure_failure"
  if all(row["category"] == "correct" for row in rows):
    cpu_times = [row["cpu_time_seconds"] for row in rows]
    if any(value is None for value in cpu_times):
      return "mixed"
    return (
        "stable_hard_solved"
        if statistics.median(cpu_times) > hard_threshold
        else "stable_solved_fast"
    )
  if all(is_analysis_unsolved(row) for row in rows):
    return "stable_analysis_unsolved"
  if all(row["category"] not in {"correct", "wrong"} for row in rows):
    return "verifier_failure_quarantine"
  return "mixed"


def is_analysis_unsolved(row):
  classification = row.get("classification")
  if classification in {"timeout", "out_of_memory"}:
    return True
  return classification == "unknown" and "unknown" in {
      row.get("category", "").strip().lower(),
      row.get("status", "").strip().lower(),
  }


def desc_inventory(source, root, desc_name):
  rows = []
  excluded = collections.Counter()
  for desc in sorted(root.rglob(desc_name)):
    text = desc.read_text(encoding="utf-8", errors="ignore")
    expected = (
        "true"
        if "VERIFICATION SUCCESSFUL" in text
        else "false"
        if "VERIFICATION FAILED" in text
        else None
    )
    if expected is None:
      excluded["no_binary_ground_truth"] += 1
      continue
    if expected == "false":
      excluded["failure_not_specific_to_reachability_property"] += 1
      continue
    sources = []
    for reference in SOURCE_REFERENCE.findall(text):
      candidate = desc.parent / reference
      if candidate.is_file() and candidate not in sources:
        sources.append(candidate)
    if len(sources) != 1:
      excluded["not_exactly_one_c_source"] += 1
      continue
    source_path = sources[0]
    program = source_path.read_text(encoding="utf-8", errors="ignore")
    if not LOOP.search(program):
      excluded["no_lexical_loop"] += 1
      continue
    if not ERROR_CALL.search(program):
      excluded["no_explicit_reachability_error_call"] += 1
      continue
    relative = source_path.relative_to(root)
    rows.append(
        {
            "source": source,
            "source_path": source_path,
            "source_relative": relative.as_posix(),
            "ground_truth_path": desc,
            "expected_verdict": expected,
            "family": family_name(relative.parts[0]),
            "license": SOURCE_LICENSES[source],
            "seed_class": "external_ground_truth",
            "task": f"external/{source}/{relative.with_suffix('.yml').as_posix()}",
        }
    )
  return rows, dict(sorted(excluded.items()))


def seahorn_inventory(root):
  rows = []
  excluded = collections.Counter()
  for source_path in sorted(root.rglob("*.c")):
    program = source_path.read_text(encoding="utf-8", errors="ignore")
    expected = (
        "true"
        if re.search(r"CHECK:\s*\^?unsat", program)
        else "false"
        if re.search(r"CHECK:\s*\^?sat", program)
        else None
    )
    if expected is None:
      excluded["no_binary_ground_truth"] += 1
      continue
    if not LOOP.search(program):
      excluded["no_lexical_loop"] += 1
      continue
    if not ERROR_CALL.search(program):
      excluded["no_explicit_reachability_error_call"] += 1
      continue
    relative = source_path.relative_to(root)
    rows.append(
        {
            "source": "seahorn",
            "source_path": source_path,
            "source_relative": relative.as_posix(),
            "ground_truth_path": source_path,
            "expected_verdict": expected,
            "family": family_name(relative.parts[0]),
            "license": SOURCE_LICENSES["seahorn"],
            "seed_class": "external_ground_truth",
            "task": f"external/seahorn/{relative.with_suffix('.yml').as_posix()}",
        }
    )
  return rows, dict(sorted(excluded.items()))


def load_svcomp_data(path):
  chunks = []
  recording = False
  with Path(path).open(encoding="utf-8") as source:
    for line in source:
      if not recording and line.startswith("const data = {"):
        recording = True
        chunks.append("{")
        continue
      if recording and line == "};\n":
        chunks.append("}")
        break
      if recording:
        chunks.append(line)
  if not chunks or chunks[-1] != "}":
    raise RuntimeError("SV-COMP result table has no complete embedded data object")
  return json.loads("".join(chunks))


def official_seed_inventory(sv_benchmarks, result_table):
  root = Path(sv_benchmarks).resolve()
  data = load_svcomp_data(result_table)
  tool_index = next(
      (
          index
          for index, tool in enumerate(data["tools"])
          if tool.get("benchmarkname") == "cpachecker"
      ),
      None,
  )
  if tool_index is None:
    raise RuntimeError("SV-COMP result table has no CPAchecker result")
  rows = []
  excluded = collections.Counter()
  for result_row in data["rows"]:
    relative, expected = result_row["id"][:2]
    task_path = root / "c" / relative
    if not task_path.is_file():
      excluded["task_missing_from_frozen_revision"] += 1
      continue
    metadata = baseline.task_metadata(task_path)
    if metadata is None or metadata["expected_verdict"] != expected:
      excluded["unsupported_or_changed_task"] += 1
      continue
    sources = [(task_path.parent / item).resolve() for item in metadata["input_files"]]
    if len(sources) != 1 or not sources[0].is_file():
      excluded["not_exactly_one_c_source"] += 1
      continue
    if not LOOP.search(sources[0].read_text(encoding="utf-8", errors="ignore")):
      excluded["no_lexical_loop"] += 1
      continue
    result = result_row["results"][tool_index]
    values = result.get("values", [])
    cpu_time = (
        float(values[1]["raw"])
        if len(values) > 1 and values[1].get("raw") not in {None, ""}
        else None
    )
    category = result.get("category", "")
    seed_class = (
        "hard_solved_seed"
        if category == "correct" and cpu_time is not None and cpu_time > 200
        else "unsolved_seed"
        if category in {"error", "unknown", "empty"}
        else None
    )
    if seed_class is None:
      excluded["not_hard_or_unsolved_in_seed_result"] += 1
      continue
    task = f"c/{relative}"
    rows.append(
        {
            "task": task,
            "task_path": task_path,
            "source_paths": sources,
            "expected_verdict": expected,
            "data_model": metadata["data_model"],
            "family": relative.split("/", 1)[0],
            "benchmark_set": f"svcomp:{relative.split('/', 1)[0]}",
            "source": "sv-benchmarks",
            "license": "per-file SPDX",
            "seed_class": seed_class,
            "seed_cpu_seconds": cpu_time,
            "seed_category": category,
        }
    )
  return rows, dict(sorted(excluded.items())), data["tools"][tool_index]


def prior_candidates(path, sv_benchmarks):
  root = Path(sv_benchmarks).resolve()
  rows = []
  with Path(path).open(newline="", encoding="utf-8") as source:
    for result in csv.DictReader(source):
      if result["category"] == "wrong" or (
          result["hard"] != "True" and result["unsolved"] != "True"
      ):
        continue
      task_path = root / result["task"]
      metadata = baseline.task_metadata(task_path)
      sources = [(task_path.parent / item).resolve() for item in metadata["input_files"]]
      relative = task_path.relative_to(root / "c").as_posix()
      rows.append(
          {
              "task": result["task"],
              "task_path": task_path,
              "source_paths": sources,
              "expected_verdict": metadata["expected_verdict"],
              "data_model": metadata["data_model"],
              "family": relative.split("/", 1)[0],
              "benchmark_set": f"svcomp:{relative.split('/', 1)[0]}",
              "source": "sv-benchmarks",
              "license": "per-file SPDX",
              "seed_class": "baseline_v1_candidate",
          }
      )
  return rows


def write_external_task(output_root, candidate, property_file):
  case_id = sha256_text(
      f"{candidate['source']}:{candidate['source_relative']}"
  )[:16]
  target_source = (
      output_root / "corpus/external" / candidate["source"] / f"{case_id}.c"
  )
  target_source.parent.mkdir(parents=True, exist_ok=True)
  shutil.copyfile(candidate["source_path"], target_source)
  task_path = target_source.with_suffix(".yml")
  relative_property = os.path.relpath(property_file, task_path.parent)
  task_path.write_text(
      "format_version: '2.0'\n"
      f"input_files: '{target_source.name}'\n"
      "properties:\n"
      f"  - property_file: '{relative_property}'\n"
      f"    expected_verdict: {candidate['expected_verdict']}\n"
      "options:\n"
      "  language: C\n"
      "  data_model: LP64\n",
      encoding="utf-8",
  )
  return f"external/{candidate['source']}/{case_id}.yml", task_path, target_source


def git_head(path):
  return subprocess.check_output(
      ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
  ).strip()


def command_inventory(args):
  output = Path(args.output_dir).resolve()
  output.mkdir(parents=True)
  sv_benchmarks = Path(args.sv_benchmarks).resolve()
  official, official_excluded, seed_tool = official_seed_inventory(
      sv_benchmarks, args.svcomp_results
  )
  prior = prior_candidates(args.prior_results, sv_benchmarks)
  prior_names = {row["task"] for row in prior}
  selected_official = family_cap(
      (row for row in official if row["task"] not in prior_names), args.official_family_cap
  )

  external_root = Path(args.external_root).resolve()
  external_inventories = []
  external_report = {}
  for name, relative, desc_name in (
      ("cbmc", "cbmc/regression/cbmc", "test.desc"),
      ("esbmc", "esbmc/regression", "test.desc"),
  ):
    rows, excluded = desc_inventory(name, external_root / relative, desc_name)
    external_inventories.extend(rows)
    external_report[name] = {"eligible": len(rows), "excluded": excluded}
  rows, excluded = seahorn_inventory(external_root / "seahorn/test")
  external_inventories.extend(rows)
  external_report["seahorn"] = {"eligible": len(rows), "excluded": excluded}
  selected_external = family_cap(external_inventories, args.external_family_cap)

  property_file = output / "corpus/properties/unreach-call.prp"
  property_file.parent.mkdir(parents=True, exist_ok=True)
  shutil.copyfile(sv_benchmarks / "c/properties/unreach-call.prp", property_file)
  candidates = {row["task"]: row for row in [*prior, *selected_official]}
  for row in selected_external:
    task, task_path, source_path = write_external_task(output, row, property_file)
    candidates[task] = {
        **row,
        "task": task,
        "task_path": task_path,
        "source_paths": [source_path],
        "data_model": "LP64",
        "benchmark_set": f"external:{row['source']}:{row['family']}",
    }
  manifest_rows = []
  for row in sorted(candidates.values(), key=lambda item: item["task"]):
    is_official = row["source"] == "sv-benchmarks"
    task_path = Path(row["task_path"])
    source_paths = [Path(path) for path in row["source_paths"]]
    path_root = sv_benchmarks if is_official else output
    ground_truth = row.get("ground_truth_path")
    manifest_rows.append(
        {
            key: value
            for key, value in {
                **row,
                "task_path": task_path.relative_to(path_root).as_posix(),
                "source_paths": [
                    path.relative_to(path_root).as_posix() for path in source_paths
                ],
                "task_sha256": baseline.sha256_file(task_path),
                "source_sha256": [
                    baseline.sha256_file(path) for path in source_paths
                ],
                "ground_truth_path": (
                    Path(ground_truth)
                    .relative_to(external_root / row["source"])
                    .as_posix()
                    if ground_truth
                    else ""
                ),
            }.items()
            if key not in {"source_path"}
        }
    )
  manifest = {
      "schema_version": "hard-case-candidate-v1",
      "task_count": len(manifest_rows),
      "selection_rule": {
          "stock_only": True,
          "hard_threshold": "median CPU time > 200 seconds",
          "repetitions": 2,
          "official_family_cap": args.official_family_cap,
          "external_family_cap": args.external_family_cap,
          "wrong_policy": "quarantine",
      },
      "repositories": {
          "sv-benchmarks": git_head(sv_benchmarks),
          **{
              source: git_head(external_root / source)
              for source in SOURCE_LICENSES
          },
      },
      "seed_result": {
          "source_url": (
              "https://sv-comp.sosy-lab.org/2026/results/results-verified/"
              "META_C.ReachSafety.table.html"
          ),
          "sha256": baseline.sha256_file(Path(args.svcomp_results)),
          "tool": seed_tool,
      },
      "inventory": {
          "official_seed_eligible": len(official),
          "official_seed_excluded": official_excluded,
          "external": external_report,
          "excluded_sources": {
              "code2inv": {
                  "revision": git_head(external_root / "code2inv"),
                  "license": "none found in frozen checkout",
                  "reason": "not distributable without license permission",
              },
              "verify-c-common": {
                  "revision": git_head(external_root / "verify-c-common"),
                  "license": "none found in frozen checkout",
                  "reason": "license and external stub semantics unresolved",
              },
              "ultimate": {
                  "revision": git_head(external_root / "ultimate"),
                  "license": "mixed per-file licensing",
                  "reason": "per-file provenance and duplicate normalization unresolved",
              },
          },
      },
      "corpus_files": [
          {
              "path": property_file.relative_to(output).as_posix(),
              "sha256": baseline.sha256_file(property_file),
          }
      ],
      "tasks": manifest_rows,
  }
  manifest_path = output / "candidate-manifest.json"
  manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
  print(manifest_path)


def render_stock(args, display, limits, rows=None):
  manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
  output = Path(args.output_dir).resolve()
  output.mkdir(parents=True, exist_ok=True)
  task_sets = write_task_sets(
      manifest["tasks"] if rows is None else rows,
      Path(args.manifest),
      args.sv_benchmarks,
      output,
  )
  root = benchmark_root(display, *limits)
  ET.SubElement(root, "resultfiles").text = "**/witness.*"
  for name, value in (
      ("--svcomp27", None),
      ("--heap", "10000M"),
      ("--benchmark", None),
      ("--timelimit", limits[0]),
  ):
    option = ET.SubElement(root, "option", {"name": name})
    if value:
      option.text = value
  write_run_definition(
      root,
      "hard-case-candidates",
      task_sets,
      args.property_file,
      Path(args.manifest).resolve().parent / "corpus/properties/unreach-call.prp",
  )
  benchmark = output / "hard-case-candidates.xml"
  write_xml(root, benchmark)
  print(benchmark)
  return benchmark


def command_render(args):
  render_stock(args, DISCOVERY_DISPLAY, ("120 s", "130 s", "140 s"))


def require_absent_or_empty_output(path):
  output = Path(path).resolve()
  if output.exists() and (
      not output.is_dir() or any(output.iterdir())
  ):
    raise RuntimeError(f"output directory must be absent or empty: {output}")


def command_render_formal(args):
  require_absent_or_empty_output(args.output_dir)
  manifest, _ = authenticate_formal_manifest(args)
  if not manifest["tasks"]:
    raise RuntimeError("formal Phase B skipped: authenticated host merge has no tasks")
  property_file = (
      Path(args.sv_benchmarks).resolve() / "c/properties/unreach-call.prp"
  )
  if args.property_file != str(property_file) or not property_file.is_file():
    raise RuntimeError("formal property file must be the frozen official property")
  benchmark = render_stock(args, FORMAL_DISPLAY, ("900 s", "910 s", "920 s"))
  validate_formal_definition(
      benchmark, args.manifest, manifest, args.sv_benchmarks
  )


def command_render_formal_replacement(args):
  require_absent_or_empty_output(args.output_dir)
  manifest, host = authenticate_formal_manifest(args)
  manifest_rows = baseline.load_task_manifest(args.manifest)
  primary = Path(args.primary_result).resolve()
  primary_hash = baseline.sha256_file(primary)
  primary_metadata = result_metadata(
      primary, FORMAL_DISPLAY, "900 s", allow_incomplete=True
  )
  if primary_metadata["host"] != host:
    raise RuntimeError("formal primary result must run on the merged manifest host")
  validate_result_run_topology(
      primary,
      manifest_rows,
      args.sv_benchmarks,
  )
  taint_path = Path(args.taint_manifest).resolve()
  taint_data = json.loads(taint_path.read_text(encoding="utf-8"))
  tainted = validate_taint_manifest(
      taint_data,
      taint_data.get("repetition"),
      primary_hash,
      manifest_rows,
  )
  if not tainted:
    raise RuntimeError("formal replacement requires at least one tainted task")
  primary_rows = baseline.parse_result_rows(primary, manifest_rows, 200)
  missing = {
      row["task"] for row in primary_rows if not row_is_complete(row)
  }
  if missing - set(tainted):
    raise RuntimeError(
        f"incomplete primary rows are not tainted: {sorted(missing - set(tainted))}"
    )
  selected = sorted(
      (row for row in manifest["tasks"] if row["task"] in tainted),
      key=lambda row: row["task"],
  )
  property_file = (
      Path(args.sv_benchmarks).resolve() / "c/properties/unreach-call.prp"
  )
  if args.property_file != str(property_file) or not property_file.is_file():
    raise RuntimeError("formal property file must be the frozen official property")
  benchmark = render_stock(
      args,
      FORMAL_DISPLAY,
      ("900 s", "910 s", "920 s"),
      rows=selected,
  )
  replacement_manifest = {**manifest, "task_count": len(selected), "tasks": selected}
  validate_formal_definition(
      benchmark,
      args.manifest,
      replacement_manifest,
      args.sv_benchmarks,
  )


def command_render_screen_replacement(args):
  require_absent_or_empty_output(args.output_dir)
  manifest_path = Path(args.manifest).resolve()
  manifest = validate_manifest(manifest_path, args.sv_benchmarks)
  host = manifest.get("derivation", {}).get("host")
  if host not in DISCOVERY_HOSTS:
    raise RuntimeError("screen manifest has no known host provenance")
  rows = baseline.load_task_manifest(manifest_path)
  primary = Path(args.primary_result).resolve()
  primary_hash = baseline.sha256_file(primary)
  metadata = result_metadata(
      primary, DISCOVERY_DISPLAY, "120 s", allow_incomplete=True
  )
  if metadata["host"] != host:
    raise RuntimeError("screen primary result does not match its manifest host")
  primary_tasks = result_task_names(primary, rows)
  primary_subset = {task: rows[task] for task in primary_tasks}
  validate_result_run_topology(
      primary, primary_subset, args.sv_benchmarks
  )
  tainted = validate_taint_manifest(
      json.loads(Path(args.taint_manifest).read_text(encoding="utf-8")),
      1,
      primary_hash,
      rows,
      SCREEN_TAINT_SCHEMA,
  )
  if not tainted:
    raise RuntimeError("screen replacement requires at least one tainted task")
  if not set(tainted) <= set(primary_tasks):
    raise RuntimeError("screen taint contains tasks absent from its result")
  missing = {
      row["task"]
      for row in baseline.parse_result_rows(primary, primary_subset, 200)
      if not row_is_complete(row)
  }
  if missing - set(tainted):
    raise RuntimeError(
        f"incomplete screen rows are not tainted: {sorted(missing - set(tainted))}"
    )
  selected = sorted(
      (row for row in manifest["tasks"] if row["task"] in tainted),
      key=lambda row: row["task"],
  )
  property_file = (
      Path(args.sv_benchmarks).resolve() / "c/properties/unreach-call.prp"
  )
  if args.property_file != str(property_file) or not property_file.is_file():
    raise RuntimeError("screen property file must be the frozen official property")
  benchmark = render_stock(
      args,
      DISCOVERY_DISPLAY,
      ("120 s", "130 s", "140 s"),
      rows=selected,
  )
  replacement_manifest = {
      **manifest,
      "task_count": len(selected),
      "tasks": selected,
  }
  validate_screen_definition(
      benchmark,
      manifest_path,
      replacement_manifest,
      args.sv_benchmarks,
  )


def write_task_sets(rows, manifest_path, sv_benchmarks, output):
  task_sets = {}
  for source_group, selected in (
      ("official", [row for row in rows if row["source"] == "sv-benchmarks"]),
      ("external", [row for row in rows if row["source"] != "sv-benchmarks"]),
  ):
    if not selected:
      continue
    task_set = output / f"hard-case-candidates-{source_group}.set"
    task_set.write_text(
        "\n".join(
            str(
                (
                    Path(sv_benchmarks).resolve()
                    if row["source"] == "sv-benchmarks"
                    else Path(manifest_path).resolve().parent
                )
                / row["task_path"]
            )
            for row in selected
        )
        + "\n",
        encoding="utf-8",
    )
    task_sets[source_group] = task_set
  return task_sets


def benchmark_root(display_name, time_limit, hard_time_limit, wall_time_limit):
  return ET.Element(
      "benchmark",
      {
          "tool": "cpachecker",
          "displayName": display_name,
          "timelimit": time_limit,
          "hardtimelimit": hard_time_limit,
          "walltimelimit": wall_time_limit,
          "memlimit": "15 GB",
          "cpuCores": "4",
      },
  )


def write_run_definition(
    root, name, task_sets, official_property, external_property
):
  run = ET.SubElement(root, "rundefinition", {"name": name})
  for source_group, property_file in (
      ("official", official_property),
      ("external", str(external_property)),
  ):
    if source_group not in task_sets:
      continue
    tasks = ET.SubElement(run, "tasks", {"name": source_group})
    ET.SubElement(tasks, "includesfile").text = str(task_sets[source_group])
    ET.SubElement(tasks, "propertyfile").text = str(property_file)


def write_xml(root, path):
  baseline.indent_xml(root)
  ET.ElementTree(root).write(path, encoding="unicode", xml_declaration=True)
  with path.open("a", encoding="utf-8") as target:
    target.write("\n")


def result_metadata(path, display, time_limit, allow_incomplete=False):
  with baseline.open_result(Path(path)) as source:
    root = ET.parse(source).getroot()
  expected = {
      "tool": "CPAchecker",
      "version": FROZEN_CPACHECKER_VERSION,
      "toolmodule": FROZEN_TOOLMODULE,
      "generator": FROZEN_BENCHEXEC_GENERATOR,
      "displayName": display,
      "memlimit": "15000000000B",
      "timelimit": time_limit.replace(" ", ""),
      "cpuCores": "4",
      "block": "official",
      "name": "hard-case-candidates.official",
      "options": (
          f"--svcomp27 --heap 10000M --benchmark --timelimit {time_limit}"
      ),
  }
  error = root.get("error")
  if (
      root.tag != "result"
      or (error is not None and (not allow_incomplete or error != "incomplete"))
      or any(root.get(name) != value for name, value in expected.items())
  ):
    raise RuntimeError("result metadata does not match the frozen stock protocol")
  hosts = [node.get("hostname") for node in root.findall("systeminfo")]
  if len(hosts) != 1 or not hosts[0]:
    raise RuntimeError("result must contain exactly one systeminfo hostname")
  metadata = {
      "host": hosts[0],
      "starttime": root.get("starttime"),
      "endtime": root.get("endtime"),
      "benchmarkname": root.get("benchmarkname"),
  }
  if (
      not metadata["starttime"]
      or (not metadata["endtime"] and error != "incomplete")
      or not metadata["benchmarkname"]
  ):
    raise RuntimeError("result lacks a start time, end time, or benchmark name")
  metadata["incomplete"] = error == "incomplete"
  return metadata


def probe_result_metadata(path, allow_incomplete=False):
  with baseline.open_result(Path(path)) as source:
    root = ET.parse(source).getroot()
  expected = {
      "tool": "CPAchecker",
      "toolmodule": FROZEN_TOOLMODULE,
      "generator": FROZEN_BENCHEXEC_GENERATOR,
      "displayName": PROBE_DISPLAY,
      "memlimit": "15000000000B",
      "timelimit": "900s",
      "cpuCores": "1",
      "block": "official",
      "name": "cegar-eligibility.official",
      "options": (
          "--predicateAnalysis-vguide --heap 10000M --timelimit 900 s "
          "--option vguide.enable=true --option vguide.provider=EMPTY"
      ),
  }
  error = root.get("error")
  if (
      root.tag != "result"
      or (error is not None and (not allow_incomplete or error != "incomplete"))
      or any(root.get(name) != value for name, value in expected.items())
      or not root.get("version")
  ):
    raise RuntimeError("probe result metadata does not match the zero-candidate protocol")
  hosts = [node.get("hostname") for node in root.findall("systeminfo")]
  if len(hosts) != 1 or not hosts[0]:
    raise RuntimeError(
        "probe result must contain exactly one systeminfo hostname"
    )
  metadata = {
      "host": hosts[0],
      "starttime": root.get("starttime"),
      "endtime": root.get("endtime"),
      "benchmarkname": root.get("benchmarkname"),
      "incomplete": error == "incomplete",
  }
  if (
      not metadata["starttime"]
      or (not metadata["endtime"] and error != "incomplete")
      or not metadata["benchmarkname"]
  ):
    raise RuntimeError("probe result lacks required timestamps or benchmark name")
  return metadata


def benchexec_path_representations(
    expected_path, sv_benchmarks, benchmark_definition
):
  expected = Path(expected_path).resolve()
  sv_benchmarks = Path(sv_benchmarks).resolve()
  representations = {expected.as_posix()}
  try:
    relative = expected.relative_to(sv_benchmarks).as_posix()
    representations.add(relative)
    representations.add(f"../../../../{sv_benchmarks.name}/{relative}")
  except ValueError:
    pass
  if benchmark_definition:
    relative = os.path.relpath(
        expected, Path(benchmark_definition).resolve().parent
    ).replace("\\", "/")
    representations.add(relative)
  return representations


def validate_result_run_topology(
    path, manifest, sv_benchmarks, benchmark_definition=None
):
  with baseline.open_result(Path(path)) as source:
    root = ET.parse(source).getroot()
  expected_attributes = {
      "name",
      "files",
      "properties",
      "propertyFile",
      "expectedVerdict",
  }
  sv_benchmarks = Path(sv_benchmarks).resolve()
  official_property = sv_benchmarks / "c/properties/unreach-call.prp"
  property_representations = benchexec_path_representations(
      official_property, sv_benchmarks, benchmark_definition
  )
  for run in root.findall("run"):
    run_name = run.get("name", "").replace("\\", "/")
    matching_tasks = [
        name
        for name, candidate in manifest.items()
        if candidate["source"] == "sv-benchmarks"
        and run_name
        in benchexec_path_representations(
            sv_benchmarks / candidate["task_path"],
            sv_benchmarks,
            benchmark_definition,
        )
    ]
    if len(matching_tasks) != 1:
      raise RuntimeError(f"result task path is not exact: {run_name}")
    task_name = matching_tasks[0]
    task = manifest[task_name]
    if set(run.attrib) != expected_attributes:
      raise RuntimeError(f"result run topology is not exact: {task_name}")
    if run.get("properties") != "unreach-call":
      raise RuntimeError(f"result property is not unreach-call: {task_name}")
    property_file = run.get("propertyFile", "").replace("\\", "/")
    if (
        task["source"] != "sv-benchmarks"
        or property_file not in property_representations
    ):
      raise RuntimeError(f"result property file is not exact: {task_name}")
    if run.get("expectedVerdict", "").lower() != task["expected_verdict"]:
      raise RuntimeError(f"result expected verdict is not exact: {task_name}")
    files = run.get("files", "")
    if not files.startswith("[") or not files.endswith("]"):
      raise RuntimeError(f"result source-file topology is not exact: {task_name}")
    actual_files = [
        value.strip().replace("\\", "/")
        for value in files[1:-1].split(",")
        if value.strip()
    ]
    expected_files = [
        benchexec_path_representations(
            sv_benchmarks / source_path,
            sv_benchmarks,
            benchmark_definition,
        )
        for source_path in task["source_paths"]
    ]
    if len(actual_files) != len(expected_files) or any(
        actual not in expected
        for actual, expected in zip(actual_files, expected_files, strict=True)
    ):
      raise RuntimeError(f"result source files do not match manifest: {task_name}")


def xml_shape(node):
  return (
      node.tag,
      tuple(sorted(node.attrib.items())),
      (node.text or "").strip(),
      tuple(xml_shape(child) for child in node),
  )


def validate_stock_definition(
    path, manifest_path, manifest, sv_benchmarks, display, limits
):
  time_limit, hard_time_limit, wall_time_limit = limits
  root = ET.parse(path).getroot()
  expected_attributes = {
      "tool": "cpachecker",
      "displayName": display,
      "timelimit": time_limit,
      "hardtimelimit": hard_time_limit,
      "walltimelimit": wall_time_limit,
      "memlimit": "15 GB",
      "cpuCores": "4",
  }
  if root.tag != "benchmark" or root.attrib != expected_attributes:
    raise RuntimeError("stock benchmark metadata does not match the fixed limits")
  definition_dir = Path(path).resolve().parent
  groups = {
      "official": [
          row for row in manifest["tasks"] if row["source"] == "sv-benchmarks"
      ],
      "external": [
          row for row in manifest["tasks"] if row["source"] != "sv-benchmarks"
      ],
  }
  task_sets = {
      group: definition_dir / f"hard-case-candidates-{group}.set"
      for group, rows in groups.items()
      if rows
  }
  include_values = [
      node.text for node in root.findall(".//includesfile")
  ]
  portable = bool(include_values) and all(
      value == Path(value).name for value in include_values
  )
  definition_task_sets = {
      group: path.name if portable else path
      for group, path in task_sets.items()
  }
  expected = benchmark_root(display, *limits)
  ET.SubElement(expected, "resultfiles").text = "**/witness.*"
  for name, value in (
      ("--svcomp27", None),
      ("--heap", "10000M"),
      ("--benchmark", None),
      ("--timelimit", time_limit),
  ):
    option = ET.SubElement(expected, "option", {"name": name})
    if value:
      option.text = value
  write_run_definition(
      expected,
      "hard-case-candidates",
      definition_task_sets,
      (
          "c/properties/unreach-call.prp"
          if portable
          else Path(sv_benchmarks).resolve()
          / "c/properties/unreach-call.prp"
      ),
      Path(manifest_path).resolve().parent / "corpus/properties/unreach-call.prp",
  )
  if xml_shape(root) != xml_shape(expected):
    raise RuntimeError("stock benchmark definition topology is not frozen")
  for group, task_set in task_sets.items():
    expected_tasks = []
    for row in groups[group]:
      if portable and row["source"] == "sv-benchmarks":
        expected_tasks.append(row["task_path"])
      else:
        expected_tasks.append(str(
            (
                Path(sv_benchmarks).resolve()
                if row["source"] == "sv-benchmarks"
                else Path(manifest_path).resolve().parent
            )
            / row["task_path"]
        ))
    if task_set.read_text(encoding="utf-8").splitlines() != expected_tasks:
      raise RuntimeError("stock benchmark task set does not match the host manifest")


def validate_formal_definition(path, manifest_path, manifest, sv_benchmarks):
  root = ET.parse(path).getroot()
  if root.attrib != {
      "tool": "cpachecker",
      "displayName": FORMAL_DISPLAY,
      "timelimit": "900 s",
      "hardtimelimit": "910 s",
      "walltimelimit": "920 s",
      "memlimit": "15 GB",
      "cpuCores": "4",
  }:
    raise RuntimeError("formal benchmark metadata is not fixed at 900/910/920")
  validate_stock_definition(
      path,
      manifest_path,
      manifest,
      sv_benchmarks,
      FORMAL_DISPLAY,
      ("900 s", "910 s", "920 s"),
  )


def validate_screen_definition(path, manifest_path, manifest, sv_benchmarks):
  validate_stock_definition(
      path,
      manifest_path,
      manifest,
      sv_benchmarks,
      DISCOVERY_DISPLAY,
      ("120 s", "130 s", "140 s"),
  )


def render_probe(manifest_path, manifest, selected, sv_benchmarks, property_file, output):
  output = Path(output).resolve()
  require_absent_or_empty_output(output)
  output.mkdir(parents=True, exist_ok=True)
  task_sets = write_task_sets(
      selected, manifest_path, sv_benchmarks, output
  )
  root = benchmark_root(
      PROBE_DISPLAY, "900 s", "910 s", "920 s"
  )
  root.set("cpuCores", "1")
  ET.SubElement(root, "resultfiles").text = "**/vguide-telemetry.json"
  for name, value in (
      ("--predicateAnalysis-vguide", None),
      ("--heap", "10000M"),
      ("--timelimit", "900 s"),
      ("--option", "vguide.enable=true"),
      ("--option", "vguide.provider=EMPTY"),
  ):
    option = ET.SubElement(root, "option", {"name": name})
    if value:
      option.text = value
  write_run_definition(
      root,
      "cegar-eligibility",
      task_sets,
      property_file,
      Path(manifest_path).resolve().parent / "corpus/properties/unreach-call.prp",
  )
  benchmark = output / "cegar-eligibility.xml"
  write_xml(root, benchmark)
  subset = {
      **manifest,
      "task_count": len(selected),
      "tasks": selected,
  }
  validate_probe_definition(
      benchmark, manifest_path, subset, sv_benchmarks
  )
  print(benchmark)


def validate_probe_definition(path, manifest_path, manifest, sv_benchmarks):
  root = ET.parse(path).getroot()
  expected = benchmark_root(
      PROBE_DISPLAY, "900 s", "910 s", "920 s"
  )
  expected.set("cpuCores", "1")
  ET.SubElement(expected, "resultfiles").text = "**/vguide-telemetry.json"
  for name, value in (
      ("--predicateAnalysis-vguide", None),
      ("--heap", "10000M"),
      ("--timelimit", "900 s"),
      ("--option", "vguide.enable=true"),
      ("--option", "vguide.provider=EMPTY"),
  ):
    option = ET.SubElement(expected, "option", {"name": name})
    if value:
      option.text = value
  definition_dir = Path(path).resolve().parent
  groups = {
      "official": [
          row for row in manifest["tasks"] if row["source"] == "sv-benchmarks"
      ],
      "external": [
          row for row in manifest["tasks"] if row["source"] != "sv-benchmarks"
      ],
  }
  task_sets = {
      group: definition_dir / f"hard-case-candidates-{group}.set"
      for group, rows in groups.items()
      if rows
  }
  write_run_definition(
      expected,
      "cegar-eligibility",
      task_sets,
      Path(sv_benchmarks).resolve() / "c/properties/unreach-call.prp",
      Path(manifest_path).resolve().parent
      / "corpus/properties/unreach-call.prp",
  )
  if xml_shape(root) != xml_shape(expected):
    raise RuntimeError("probe benchmark definition topology is not frozen")
  for group, task_set in task_sets.items():
    expected_tasks = [
        str(
            (
                Path(sv_benchmarks).resolve()
                if row["source"] == "sv-benchmarks"
                else Path(manifest_path).resolve().parent
            )
            / row["task_path"]
        )
        for row in groups[group]
    ]
    if task_set.read_text(encoding="utf-8").splitlines() != expected_tasks:
      raise RuntimeError("probe task set does not match the authenticated manifest")


def command_render_probe(args):
  manifest_path = Path(args.manifest).resolve()
  manifest = validate_manifest(manifest_path, args.sv_benchmarks)
  details = {row["task"]: row for row in manifest["tasks"]}
  with Path(args.hard_portfolio).open(newline="", encoding="utf-8") as source:
    rows = list(csv.DictReader(source))
  tasks = [row["task"] for row in rows]
  if (
      len(tasks) != len(set(tasks))
      or any(task not in details for task in tasks)
      or not tasks
  ):
    raise RuntimeError("probe hard portfolio is empty, duplicated, or outside manifest")
  render_probe(
      manifest_path,
      manifest,
      [details[task] for task in tasks],
      args.sv_benchmarks,
      args.property_file,
      args.output_dir,
  )


def render_strict_probe(args, cohort):
  _, manifest_path, manifest, hard, _ = validate_strict_probe_input(
      args.probe_input, args.sv_benchmarks, cohort
  )
  details = {row["task"]: row for row in manifest["tasks"]}
  render_probe(
      manifest_path,
      manifest,
      [details[row["task"]] for row in hard],
      args.sv_benchmarks,
      args.property_file,
      args.output_dir,
  )


def command_render_cap8_probe(args):
  render_strict_probe(args, "cap8")


def command_render_cap16_probe(args):
  render_strict_probe(args, "cap16")


def render_strict_probe_replacement(args, cohort):
  profile = strict_probe_profile(cohort)
  _, manifest_path, manifest, _, _ = validate_strict_probe_input(
      args.probe_input, args.sv_benchmarks, cohort
  )
  by_name = baseline.load_task_manifest(manifest_path)
  result = Path(args.primary_result).resolve()
  tainted = validate_taint_manifest(
      json.loads(Path(args.taint_manifest).read_text(encoding="utf-8")),
      1,
      baseline.sha256_file(result),
      by_name,
      profile["taint_schema"],
  )
  if not tainted:
    raise RuntimeError("probe replacement requires at least one tainted task")
  result_tasks = set(result_task_names(result, by_name))
  if not set(tainted) <= result_tasks:
    raise RuntimeError("probe replacement taint is outside its result")
  selected = sorted(
      (
          row for row in manifest["tasks"]
          if row["task"] in tainted
      ),
      key=lambda row: row["task"],
  )
  render_probe(
      manifest_path,
      manifest,
      selected,
      args.sv_benchmarks,
      args.property_file,
      args.output_dir,
  )


def command_render_cap8_probe_replacement(args):
  render_strict_probe_replacement(args, "cap8")


def command_render_cap16_probe_replacement(args):
  render_strict_probe_replacement(args, "cap16")


def split_for_family(family):
  bucket = int(sha256_text(family)[:8], 16) % 10
  return "development" if bucket < 6 else "validation" if bucket < 8 else "heldout"


def manifest_subset(manifest, tasks, derivation):
  selected = set(tasks)
  rows = [row for row in manifest["tasks"] if row["task"] in selected]
  if len(rows) != len(selected):
    raise RuntimeError("subset contains tasks absent from the input manifest")
  result = {
      **{key: value for key, value in manifest.items() if key != "license_audit"},
      "schema_version": "hard-case-candidate-v2-derived",
      "task_count": len(rows),
      "derivation": derivation,
      "tasks": rows,
  }
  if "license_audit" in manifest:
    source_sha256 = derivation.get("source_manifest_sha256")
    if not source_sha256:
      raise RuntimeError("derived audited manifest lacks its source manifest hash")
    audit = manifest["license_audit"]
    result["parent_license_audit"] = {
        "manifest_sha256": source_sha256,
        "included_task_count": audit["included_task_count"],
        "excluded_task_count": audit["excluded_task_count"],
        "selection_independent_of_verifier_outcomes": audit[
            "selection_independent_of_verifier_outcomes"
        ],
        "task_license_evidence_preserved": True,
    }
  return result


def stratified_shards(rows, hosts=DISCOVERY_HOSTS):
  hosts = tuple(hosts)
  if not hosts or len(hosts) != len(set(hosts)):
    raise RuntimeError("shard hosts must be nonempty and unique")
  groups = collections.defaultdict(list)
  for row in rows:
    groups[
        (row["family"], row["seed_class"], row["expected_verdict"])
    ].append(row)
  counts = {host: collections.Counter() for host in hosts}
  shards = {host: [] for host in hosts}
  host_order = {host: index for index, host in enumerate(hosts)}
  for stratum, tasks in sorted(
      groups.items(), key=lambda item: (-len(item[1]), item[0])
  ):
    family, seed, verdict = stratum
    for row in sorted(
        tasks, key=lambda item: (sha256_text(item["task"]), item["task"])
    ):
      host = min(
          hosts,
          key=lambda candidate: (
              counts[candidate][("stratum", stratum)],
              counts[candidate][("family", family)],
              counts[candidate][("seed", seed)],
              counts[candidate][("verdict", verdict)],
              counts[candidate][("total",)],
              host_order[candidate],
          ),
      )
      shards[host].append(row)
      counts[host][("stratum", stratum)] += 1
      counts[host][("family", family)] += 1
      counts[host][("seed", seed)] += 1
      counts[host][("verdict", verdict)] += 1
      counts[host][("total",)] += 1
  return shards


def requested_shard_hosts(args):
  hosts = tuple(getattr(args, "host", None) or DISCOVERY_HOSTS)
  if (
      not hosts
      or len(hosts) != len(set(hosts))
      or any(host not in DISCOVERY_HOSTS for host in hosts)
  ):
    raise RuntimeError("shard hosts must be known, nonempty, and unique")
  return hosts


def validate_shard_partition(rows, shards, hosts=DISCOVERY_HOSTS):
  hosts = tuple(hosts)
  expected = stratified_shards(rows, hosts)
  input_rows = {row["task"]: row for row in rows}
  actual_tasks = [
      row["task"] for host in hosts for row in shards.get(host, [])
  ]
  if len(actual_tasks) != len(set(actual_tasks)):
    raise RuntimeError("shard partition contains overlapping tasks")
  if set(actual_tasks) != set(input_rows):
    raise RuntimeError("shard partition contains missing or unexpected tasks")
  for host in hosts:
    actual = {row["task"]: row for row in shards.get(host, [])}
    if any(input_rows[task] != row for task, row in actual.items()):
      raise RuntimeError(f"shard partition contains changed task records: {host}")
    if set(actual) != {row["task"] for row in expected[host]}:
      raise RuntimeError(f"shard partition differs from recomputed assignment: {host}")


def command_difference(args):
  hosts = requested_shard_hosts(args)
  full_path = Path(args.manifest).resolve()
  excluded_path = Path(args.exclude_manifest).resolve()
  full = validate_manifest(full_path, args.sv_benchmarks)
  excluded = validate_manifest(excluded_path, args.sv_benchmarks)
  full_rows = {row["task"]: row for row in full["tasks"]}
  for row in excluded["tasks"]:
    if full_rows.get(row["task"]) != row:
      raise RuntimeError(
          f"excluded task is absent or differs from full manifest: {row['task']}"
      )
  excluded_tasks = {row["task"] for row in excluded["tasks"]}
  tasks = sorted(set(full_rows) - excluded_tasks)
  full_sha256 = baseline.sha256_file(full_path)
  output = Path(args.output_dir).resolve()
  if output.exists() and any(output.iterdir()):
    raise RuntimeError(f"output directory must be absent or empty: {output}")
  output.mkdir(parents=True, exist_ok=True)
  shutil.copytree(full_path.parent / "corpus", output / "corpus")
  derivation = {
      "operation": "difference",
      "source_manifest_sha256": full_sha256,
      "excluded_manifest_sha256": baseline.sha256_file(excluded_path),
      "selection_independent_of_verifier_outcomes": True,
  }
  difference = manifest_subset(full, tasks, derivation)
  difference_path = output / "candidate-manifest.json"
  difference_path.write_text(
      json.dumps(difference, indent=2) + "\n", encoding="utf-8"
  )
  difference_sha256 = baseline.sha256_file(difference_path)
  assigned = stratified_shards(difference["tasks"], hosts)
  shards = {}
  shard_manifests = {}
  for host in hosts:
    host_tasks = [row["task"] for row in assigned[host]]
    shard = manifest_subset(
        full,
        host_tasks,
        {
            "operation": "deterministic_stratified_shard",
            "source_manifest_sha256": full_sha256,
            "parent_manifest_sha256": difference_sha256,
            "hosts": list(hosts),
            "host": host,
            "algorithm": (
                "strata (family,seed_class,expected_verdict) by (-size,key); "
                "tasks by SHA-256(task); lexicographic least host counts for "
                "stratum,family,seed,verdict,total,host-order"
            ),
            "selection_independent_of_verifier_outcomes": True,
        },
    )
    shard_manifests[host] = shard
    path = output / f"candidate-manifest-{host}.json"
    path.write_text(json.dumps(shard, indent=2) + "\n", encoding="utf-8")
    shards[host] = {
        "task_count": len(host_tasks),
        "sha256": baseline.sha256_file(path),
    }
  validate_shard_partition(
      difference["tasks"],
      {host: shard["tasks"] for host, shard in shard_manifests.items()},
      hosts,
  )
  print(
      json.dumps(
          {
              "task_count": len(tasks),
              "sha256": difference_sha256,
              "shards": shards,
          },
          sort_keys=True,
      )
  )


def command_validate_shards(args):
  hosts = requested_shard_hosts(args)
  manifest_path = Path(args.manifest).resolve()
  manifest = validate_manifest(manifest_path, args.sv_benchmarks)
  parent_sha256 = baseline.sha256_file(manifest_path)
  shards = {}
  for path in args.shard_manifest:
    shard = validate_manifest(path, args.sv_benchmarks)
    derivation = shard.get("derivation", {})
    host = derivation.get("host")
    if host not in hosts or host in shards:
      raise RuntimeError(f"invalid or duplicate shard host: {host}")
    if derivation.get("operation") != "deterministic_stratified_shard":
      raise RuntimeError(f"invalid shard operation: {host}")
    if derivation.get("hosts") != list(hosts):
      raise RuntimeError(f"invalid shard host list: {host}")
    if derivation.get("parent_manifest_sha256") != parent_sha256:
      raise RuntimeError(f"invalid shard parent manifest hash: {host}")
    shards[host] = shard["tasks"]
  validate_shard_partition(manifest["tasks"], shards, hosts)
  print(json.dumps({"task_count": manifest["task_count"], "valid": True}))


def validate_cthulhu_parent(manifest_path, sv_benchmarks):
  manifest_path = Path(manifest_path).resolve()
  if baseline.sha256_file(manifest_path) != FROZEN_CTHULHU_MANIFEST_SHA256:
    raise RuntimeError("Cthulhu parent manifest hash is not frozen r3 input")
  manifest = validate_manifest(manifest_path, sv_benchmarks)
  derivation = manifest.get("derivation", {})
  required = {
      "operation": "deterministic_stratified_shard",
      "hosts": list(DISCOVERY_HOSTS),
      "host": "cthulhu",
      "selection_independent_of_verifier_outcomes": True,
  }
  for field, expected in required.items():
    if derivation.get(field) != expected:
      raise RuntimeError(f"invalid Cthulhu parent provenance: {field}")
  return manifest


def reroute_derivation(parent):
  return {
      "operation": "deterministic_stratified_reroute",
      "parent_manifest_sha256": FROZEN_CTHULHU_MANIFEST_SHA256,
      "source_host": "cthulhu",
      "source_derivation": parent["derivation"],
      "hosts": list(REROUTE_HOSTS),
      "algorithm": (
          "strata (family,seed_class,expected_verdict) by (-size,key); "
          "tasks by SHA-256(task); lexicographic least host counts for "
          "stratum,family,seed,verdict,total,host-order"
      ),
      "selection_independent_of_verifier_outcomes": True,
  }


def command_reroute_cthulhu(args):
  parent_path = Path(args.manifest).resolve()
  parent = validate_cthulhu_parent(parent_path, args.sv_benchmarks)
  output = Path(args.output_dir).resolve()
  if output.exists() and any(output.iterdir()):
    raise RuntimeError(f"output directory must be absent or empty: {output}")
  output.mkdir(parents=True, exist_ok=True)
  shutil.copytree(parent_path.parent / "corpus", output / "corpus")
  assigned = stratified_shards(parent["tasks"], REROUTE_HOSTS)
  manifests = {}
  report = {}
  for host in REROUTE_HOSTS:
    derivation = {**reroute_derivation(parent), "host": host}
    manifest = manifest_subset(
        parent, [row["task"] for row in assigned[host]], derivation
    )
    path = output / f"candidate-manifest-{host}.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    manifests[host] = manifest
    report[host] = {
        "task_count": manifest["task_count"],
        "sha256": baseline.sha256_file(path),
    }
  validate_shard_partition(
      parent["tasks"],
      {host: manifest["tasks"] for host, manifest in manifests.items()},
      REROUTE_HOSTS,
  )
  print(
      json.dumps(
          {"parent_task_count": parent["task_count"], "reroutes": report},
          sort_keys=True,
      )
  )


def command_validate_reroute(args):
  parent = validate_cthulhu_parent(args.manifest, args.sv_benchmarks)
  reroutes = {}
  base_derivation = reroute_derivation(parent)
  for path in args.reroute_manifest:
    reroute = validate_manifest(path, args.sv_benchmarks)
    derivation = reroute.get("derivation", {})
    host = derivation.get("host")
    if host not in REROUTE_HOSTS or host in reroutes:
      raise RuntimeError(f"invalid or duplicate reroute host: {host}")
    expected_derivation = {**base_derivation, "host": host}
    if derivation != expected_derivation:
      raise RuntimeError(f"invalid reroute provenance: {host}")
    expected_manifest = manifest_subset(
        parent, [row["task"] for row in reroute["tasks"]], expected_derivation
    )
    if reroute != expected_manifest:
      raise RuntimeError(f"reroute contains changed provenance or rows: {host}")
    reroutes[host] = reroute["tasks"]
  if set(reroutes) != set(REROUTE_HOSTS):
    raise RuntimeError("reroute manifests do not contain both fixed hosts")
  validate_shard_partition(parent["tasks"], reroutes, REROUTE_HOSTS)
  print(json.dumps({"task_count": parent["task_count"], "valid": True}))


def athena_recovery_manifest(original, reroute):
  excluded = {"task_count", "tasks", "derivation"}
  if (
      {key: value for key, value in original.items() if key not in excluded}
      != {key: value for key, value in reroute.items() if key not in excluded}
  ):
    raise RuntimeError("Athena recovery parents have different corpus metadata")
  tasks = [*original["tasks"], *reroute["tasks"]]
  names = [row["task"] for row in tasks]
  if len(names) != len(set(names)):
    raise RuntimeError("Athena recovery parents contain overlapping tasks")
  return {
      **original,
      "task_count": len(tasks),
      "tasks": tasks,
      "derivation": {
          "operation": "ordered_athena_recovery_merge",
          "host": "valkyrie",
          "hosts": ["valkyrie"],
          "parents": [
              {
                  "manifest_sha256": FROZEN_ATHENA_MANIFEST_SHA256,
                  "task_count": original["task_count"],
                  "derivation": original["derivation"],
              },
              {
                  "manifest_sha256": FROZEN_ATHENA_REROUTE_MANIFEST_SHA256,
                  "task_count": reroute["task_count"],
                  "derivation": reroute["derivation"],
              },
          ],
          "algorithm": (
              "original Athena rows followed by r4 Athena reroute rows; "
              "each frozen parent order is preserved"
          ),
          "selection_independent_of_verifier_outcomes": True,
      },
  }


def expected_athena_recovery_manifest(
    original_path, reroute_path, sv_benchmarks
):
  inputs = (
      (
          Path(original_path).resolve(),
          FROZEN_ATHENA_MANIFEST_SHA256,
          "original Athena",
      ),
      (
          Path(reroute_path).resolve(),
          FROZEN_ATHENA_REROUTE_MANIFEST_SHA256,
          "r4 Athena reroute",
      ),
  )
  manifests = []
  for path, expected, name in inputs:
    if baseline.sha256_file(path) != expected:
      raise RuntimeError(f"{name} manifest hash is not frozen input")
    manifests.append(validate_manifest(path, sv_benchmarks))
  return athena_recovery_manifest(*manifests)


def command_athena_recovery(args):
  original_path = Path(args.athena_manifest).resolve()
  manifest = expected_athena_recovery_manifest(
      original_path, args.athena_reroute_manifest, args.sv_benchmarks
  )
  output = Path(args.output_dir).resolve()
  if output.exists() and any(output.iterdir()):
    raise RuntimeError(f"output directory must be absent or empty: {output}")
  output.mkdir(parents=True, exist_ok=True)
  for row in manifest.get("corpus_files", []):
    target = output / row["path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(original_path.parent / row["path"], target)
  manifest_path = output / "candidate-manifest-valkyrie.json"
  manifest_path.write_text(
      json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
  )
  manifest_sha256 = baseline.sha256_file(manifest_path)
  if manifest_sha256 != FROZEN_ATHENA_RECOVERY_MANIFEST_SHA256:
    raise RuntimeError("Athena recovery manifest differs from frozen r5 output")
  print(
      json.dumps(
          {
              "manifest": manifest_path.name,
              "sha256": manifest_sha256,
              "task_count": manifest["task_count"],
          },
          sort_keys=True,
      )
  )


def command_validate_athena_recovery(args):
  expected = expected_athena_recovery_manifest(
      args.athena_manifest,
      args.athena_reroute_manifest,
      args.sv_benchmarks,
  )
  manifest_path = Path(args.manifest).resolve()
  actual = validate_manifest(manifest_path, args.sv_benchmarks)
  manifest_sha256 = baseline.sha256_file(manifest_path)
  if manifest_sha256 != FROZEN_ATHENA_RECOVERY_MANIFEST_SHA256:
    raise RuntimeError("Athena recovery manifest hash is not frozen r5 output")
  if actual != expected:
    raise RuntimeError(
        "Athena recovery manifest contains changed provenance, order, or rows"
    )
  print(
      json.dumps(
          {
              "sha256": manifest_sha256,
              "task_count": actual["task_count"],
              "valid": True,
          },
          sort_keys=True,
      )
  )


def validate_phase_a_partition(parent, phases):
  parent_rows = {row["task"]: row for row in parent["tasks"]}
  tasks = [
      row
      for role in FROZEN_PHASE_A_MANIFEST_SHA256
      for row in phases[role]["manifest"]["tasks"]
  ]
  names = [row["task"] for row in tasks]
  if len(names) != len(set(names)):
    raise RuntimeError("Phase-A manifests contain overlapping tasks")
  if set(names) != set(parent_rows):
    raise RuntimeError("Phase-A manifests do not partition the frozen parent")
  if any(parent_rows[row["task"]] != row for row in tasks):
    raise RuntimeError("Phase-A manifests contain changed task records")


def authenticate_phase_b_inputs(args):
  parent_path = Path(args.parent_manifest).resolve()
  if baseline.sha256_file(parent_path) != FROZEN_PARENT_MANIFEST_SHA256:
    raise RuntimeError("parent manifest hash is not the frozen 320-task input")
  parent = validate_manifest(parent_path, args.sv_benchmarks)
  parent_sha256 = baseline.sha256_file(parent_path)
  phases = {}
  role_by_hash = {
      digest: role for role, digest in FROZEN_PHASE_A_MANIFEST_SHA256.items()
  }
  for value in args.phase_a_manifest:
    path = Path(value).resolve()
    digest = baseline.sha256_file(path)
    role = role_by_hash.get(digest)
    if role is None or role in phases:
      raise RuntimeError("Phase-A manifest hash is not a distinct frozen input")
    manifest = validate_manifest(path, args.sv_benchmarks)
    derivation = manifest.get("derivation", {})
    if (
        derivation.get("host") != "valkyrie"
        or derivation.get("operation") != PHASE_A_OPERATION[role]
    ):
      raise RuntimeError(f"invalid Phase-A operation or host: {role}")
    phases[role] = {
        "manifest": manifest,
        "path": path,
        "sha256": digest,
        "role": role,
    }
  required_roles = set(FROZEN_PHASE_A_MANIFEST_SHA256)
  if not (
      required_roles
      == set(FROZEN_PHASE_A_RESULT_SHA256)
      == set(FROZEN_PHASE_A_SURVIVOR_SHA256)
      == set(FROZEN_PHASE_A_SURVIVOR_TASK_COUNT)
  ):
    raise RuntimeError("frozen Phase-A evidence pins have inconsistent roles")
  if set(phases) != required_roles:
    raise RuntimeError("Phase-A inputs must contain exactly three frozen manifests")
  validate_phase_a_partition(parent, phases)

  if len(args.phase_a_result) != len(required_roles):
    raise RuntimeError("Phase-A inputs must contain exactly three result files")
  results = {}
  result_role_by_hash = {
      digest: role for role, digest in FROZEN_PHASE_A_RESULT_SHA256.items()
  }
  for value in args.phase_a_result:
    path = Path(value).resolve()
    digest = baseline.sha256_file(path)
    role = result_role_by_hash.get(digest)
    if role is None or role in results:
      raise RuntimeError("Phase-A result hash is not a distinct frozen input")
    metadata = result_metadata(path, DISCOVERY_DISPLAY, "120 s")
    if metadata["host"] != "valkyrie":
      raise RuntimeError("Phase-A result hostname must be valkyrie")
    task_manifest = baseline.load_task_manifest(phases[role]["path"])
    validate_result_run_topology(path, task_manifest, args.sv_benchmarks)
    results[role] = {
        "path": path,
        "sha256": digest,
        **metadata,
    }
  for field in ("starttime", "benchmarkname"):
    if len({result[field] for result in results.values()}) != len(required_roles):
      raise RuntimeError(f"Phase-A results must have distinct {field} values")
  phase_by_hash = {item["sha256"]: role for role, item in phases.items()}
  survivor_role_by_hash = {
      digest: role for role, digest in FROZEN_PHASE_A_SURVIVOR_SHA256.items()
  }
  survivors = {}
  tasks = []
  for value in args.survivor_manifest:
    path = Path(value).resolve()
    digest = baseline.sha256_file(path)
    role = survivor_role_by_hash.get(digest)
    if role is None or role in survivors:
      raise RuntimeError("survivor manifest hash is not a distinct frozen input")
    manifest = validate_manifest(path, args.sv_benchmarks)
    derivation = manifest.get("derivation", {})
    if phase_by_hash.get(derivation.get("parent_manifest_sha256")) != role:
      raise RuntimeError("survivor has invalid Phase-A parent")
    phase = phases[role]
    result_hash = derivation.get("result_sha256")
    result = results[role]
    if result_hash != result["sha256"]:
      raise RuntimeError("survivor result hash does not match Phase A")
    expected_derivation = {
        "operation": "phase_a_analysis_survivors",
        "parent_manifest_sha256": phase["sha256"],
        "result_sha256": result_hash,
        "allowed_results": sorted(ANALYSIS_UNSOLVED),
        "phase_a_host": "valkyrie",
        "selection_independent_of_augmented_outcomes": True,
    }
    if derivation != expected_derivation:
      raise RuntimeError("survivor provenance is not frozen Phase A")
    if manifest["task_count"] != FROZEN_PHASE_A_SURVIVOR_TASK_COUNT[role]:
      raise RuntimeError("survivor task count is not the frozen Phase-A count")
    runs = baseline.parse_result_rows(
        result["path"],
        baseline.load_task_manifest(phase["path"]),
        hard_threshold=200,
    )
    if any(
        row["cpu_time_seconds"] is None or row["wall_time_seconds"] is None
        for row in runs
    ):
      raise RuntimeError("Phase-A result lacks parseable CPU or wall metrics")
    selected = {
        row["task"]
        for row in runs
        if classify_screen_result(row) == "analysis_survivor"
    }
    expected = manifest_subset(phase["manifest"], selected, expected_derivation)
    if manifest != expected:
      raise RuntimeError("survivor rows do not match recomputed Phase-A results")
    survivors[role] = {
        "manifest": manifest,
        "sha256": digest,
        "result_sha256": result_hash,
    }
    tasks.extend(row["task"] for row in manifest["tasks"])
  if set(survivors) != required_roles:
    raise RuntimeError("survivors and results must cover exactly three Phase-A inputs")
  if len(tasks) != len(set(tasks)):
    raise RuntimeError("Phase-A survivor sets contain duplicate tasks")
  inputs = [
      {
          "role": role,
          "phase_a_manifest_sha256": phases[role]["sha256"],
          "phase_a_result_sha256": survivors[role]["result_sha256"],
          "survivor_manifest_sha256": survivors[role]["sha256"],
          "survivor_task_count": survivors[role]["manifest"]["task_count"],
      }
      for role in FROZEN_PHASE_A_MANIFEST_SHA256
  ]
  merged = manifest_subset(
      parent,
      tasks,
      {
          "operation": "merge_phase_a_survivors_single_host",
          "parent_manifest_sha256": parent_sha256,
          "host": "valkyrie",
          "phase_a_inputs": inputs,
          "selection_independent_of_augmented_outcomes": True,
      },
  )
  return parent, parent_sha256, merged


def authenticate_formal_manifest(args):
  if hasattr(args, "phase_a_output"):
    phase_a_manifest, host = authenticate_cap16_phase_a_output(
        args.phase_a_output, args.sv_benchmarks
    )
    manifest_path = Path(args.manifest).resolve()
    expected_path = (
        Path(args.phase_a_output).resolve()
        / "summary/candidate-manifest-analysis-survivors.json"
    )
    if manifest_path != expected_path:
      raise RuntimeError(
          "cap-16 formal manifest must be the authenticated Phase-A survivor"
      )
    manifest = validate_manifest(manifest_path, args.sv_benchmarks)
    if manifest != phase_a_manifest:
      raise RuntimeError(
          "cap-16 formal manifest differs from authenticated Phase-A survivors"
      )
    return manifest, host
  _, _, merged = authenticate_phase_b_inputs(args)
  manifest_path = Path(args.manifest).resolve()
  if baseline.sha256_file(manifest_path) != FROZEN_FORMAL_MANIFEST_SHA256:
    raise RuntimeError("formal manifest hash is not the frozen Phase-B input")
  manifest = validate_manifest(manifest_path, args.sv_benchmarks)
  if manifest != merged:
    raise RuntimeError("formal manifest does not match authenticated Valkyrie merge")
  return manifest, "valkyrie"


def validate_artifact_manifest_index(artifact):
  if (
      not isinstance(artifact, dict)
      or set(artifact)
      != {"root", "file_count", "aggregate_sha256", "files"}
      or not isinstance(artifact["root"], str)
      or not isinstance(artifact["files"], list)
  ):
    raise RuntimeError("artifact manifest topology is invalid")
  entries = []
  aggregate = hashlib.sha256()
  for entry in artifact["files"]:
    if (
        not isinstance(entry, dict)
        or set(entry) != {"path", "size_bytes", "sha256"}
        or not isinstance(entry["path"], str)
        or Path(entry["path"]).is_absolute()
        or ".." in Path(entry["path"]).parts
        or not isinstance(entry["size_bytes"], int)
        or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
    ):
      raise RuntimeError("artifact manifest entry is invalid")
    entries.append(entry["path"])
    aggregate.update(entry["path"].encode("utf-8"))
    aggregate.update(b"\0")
    aggregate.update(bytes.fromhex(entry["sha256"]))
  if entries != sorted(entries) or len(entries) != len(set(entries)):
    raise RuntimeError("artifact manifest paths are not unique and sorted")
  if (
      artifact["file_count"] != len(entries)
      or artifact["aggregate_sha256"] != aggregate.hexdigest()
  ):
    raise RuntimeError("artifact manifest aggregate is invalid")
  return {entry["path"]: entry for entry in artifact["files"]}


def validate_artifact_manifest(
    root, artifact_path, ignored, expected_root=None
):
  root = Path(root).resolve()
  artifact_path = Path(artifact_path).resolve()
  artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
  entries = validate_artifact_manifest_index(artifact)
  if artifact["root"] != (
      str(root) if expected_root is None else expected_root
  ):
    raise RuntimeError("artifact manifest root is invalid")
  for relative, entry in entries.items():
    path = root / relative
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_size != entry["size_bytes"]
        or baseline.sha256_file(path) != entry["sha256"]
    ):
      raise RuntimeError(f"artifact manifest mismatch: {relative}")
  ignored = {Path(path).as_posix() for path in ignored}
  actual = []
  for path in root.rglob("*"):
    mode = path.lstat().st_mode
    if stat.S_ISDIR(mode):
      continue
    relative = path.relative_to(root).as_posix()
    if path == artifact_path or relative in ignored:
      continue
    if not stat.S_ISREG(mode):
      raise RuntimeError(f"unsupported artifact node: {path}")
    actual.append(relative)
  if list(entries) != sorted(actual):
    raise RuntimeError("artifact manifest file set is incomplete")
  return artifact


def validate_cap16_phase_a_structure(
    phase_a_output, sv_benchmarks, portable
):
  declared = Path(phase_a_output)
  root = declared.resolve()
  if (
      declared.is_symlink()
      or Path(os.path.abspath(declared)) != root
      or not root.is_dir()
  ):
    raise RuntimeError("cap-16 Phase-A output must be a regular directory")
  complete = root / "summary/.complete"
  if (
      complete.is_symlink()
      or not complete.is_file()
      or complete.read_text(encoding="utf-8") != "complete\n"
  ):
    raise RuntimeError("cap-16 Phase-A output is not complete")
  manifest_path = root / "input/candidate-manifest-athena.json"
  if baseline.sha256_file(manifest_path) != FROZEN_CAP16_ATHENA_MANIFEST_SHA256:
    raise RuntimeError("cap-16 Phase-A manifest hash is not frozen")
  manifest = validate_manifest(manifest_path, sv_benchmarks)
  derivation = manifest.get("derivation", {})
  if (
      manifest["task_count"] != FROZEN_CAP16_PHASE_A_TASK_COUNT
      or derivation.get("operation") != "deterministic_stratified_shard"
      or derivation.get("parent_manifest_sha256")
      != FROZEN_CAP16_PARENT_MANIFEST_SHA256
      or derivation.get("hosts") != ["athena"]
      or derivation.get("host") != "athena"
      or derivation.get("selection_independent_of_verifier_outcomes") is not True
  ):
    raise RuntimeError("cap-16 Phase-A manifest provenance is invalid")
  definition = root / "generated/hard-case-candidates.xml"
  validate_screen_definition(
      definition, manifest_path, manifest, sv_benchmarks
  )
  rows = baseline.load_task_manifest(manifest_path)
  plan = load_screen_plan(
      root / "screen-plan.json",
      rows,
      manifest_path,
      "athena",
      sv_benchmarks,
      definition,
  )
  row_provenance_content = json.dumps({
      "schema_version": "hard-case-screen-row-provenance-v1",
      "screen_plan_sha256": plan["plan_sha256"],
      "primary_result_sha256": plan["primary_sha256"],
      "replacement_result_sha256": plan["replacement_sha256"],
      "rows": plan["row_sources"],
  }, indent=2) + "\n"
  row_provenance_path = root / "summary/row-provenance.json"
  if row_provenance_path.read_text(encoding="utf-8") != row_provenance_content:
    raise RuntimeError("cap-16 Phase-A row provenance is invalid")
  accepted = [plan["rows"][task] for task in rows]
  if any(
      run["cpu_time_seconds"] is None or run["wall_time_seconds"] is None
      for run in accepted
  ):
    raise RuntimeError("cap-16 Phase-A result lacks CPU or wall metrics")
  survivor_tasks = [
      run["task"]
      for run in accepted
      if classify_screen_result(run) == "analysis_survivor"
  ]
  provenance = {
      "screen_plan_sha256": plan["plan_sha256"],
      "result_sha256": [
          plan["primary_sha256"],
          *plan["replacement_sha256"],
      ],
      "row_provenance_sha256": hashlib.sha256(
          row_provenance_content.encode("utf-8")
      ).hexdigest(),
  }
  expected = manifest_subset(
      manifest,
      survivor_tasks,
      {
          "operation": "phase_a_analysis_survivors",
          "parent_manifest_sha256": FROZEN_CAP16_ATHENA_MANIFEST_SHA256,
          **provenance,
          "allowed_results": sorted(ANALYSIS_UNSOLVED),
          "phase_a_host": "athena",
          "selection_independent_of_augmented_outcomes": True,
      },
  )
  survivor_path = (
      root / "summary/candidate-manifest-analysis-survivors.json"
  )
  survivor = validate_manifest(survivor_path, sv_benchmarks)
  if survivor != expected:
    raise RuntimeError(
        "cap-16 Phase-A survivor differs from recomputed screen plan"
    )
  counts = collections.Counter(
      classify_screen_result(run) for run in accepted
  )
  expected_summary = {
      "task_count": len(accepted),
      "phase_a_host": "athena",
      "classifications": dict(sorted(counts.items())),
      **provenance,
      "survivor_manifest_sha256": baseline.sha256_file(survivor_path),
  }
  summary = json.loads(
      (root / "summary/summary.json").read_text(encoding="utf-8")
  )
  if summary != expected_summary:
    raise RuntimeError("cap-16 Phase-A summary is invalid")
  artifact = validate_artifact_manifest(
      root,
      root / "provenance/artifact-manifest.json",
      {"summary/.complete"},
      expected_root="." if portable else None,
  )
  return survivor, "athena", artifact


def authenticate_cap16_phase_a_output(phase_a_output, sv_benchmarks):
  survivor, host, artifact = validate_cap16_phase_a_structure(
      phase_a_output, sv_benchmarks, portable=True
  )
  frozen = FROZEN_CAP16_PHASE_A_PACKAGE_AGGREGATE_SHA256
  if not re.fullmatch(r"[0-9a-f]{64}", frozen):
    raise RuntimeError(
        "cap-16 Phase-A package aggregate is pending and formal execution "
        "is disabled"
    )
  if artifact["aggregate_sha256"] != frozen:
    raise RuntimeError("cap-16 Phase-A package aggregate is not frozen")
  return survivor, host


def command_package_cap16_phase_a(args):
  source = Path(args.phase_a_output)
  validate_cap16_phase_a_structure(
      source, args.sv_benchmarks, portable=False
  )
  source = source.resolve()
  output = Path(args.output_dir).resolve()
  if output == source or source in output.parents or output in source.parents:
    raise RuntimeError("cap-16 package output overlaps its Phase-A source")
  require_absent_or_empty_output(output)
  shutil.copytree(source, output, dirs_exist_ok=True)
  (output / "summary/.complete").unlink()
  (output / "provenance/artifact-manifest.json").unlink()
  manifest_path = output / "input/candidate-manifest-athena.json"
  manifest_rows = baseline.load_task_manifest(manifest_path)
  sv_benchmarks = Path(args.sv_benchmarks).resolve()
  for definition in sorted(output.glob("generated/**/hard-case-candidates.xml")):
    root = ET.parse(definition).getroot()
    for node in root.findall(".//includesfile"):
      value = Path(node.text)
      if not value.name.startswith("hard-case-candidates-"):
        raise RuntimeError("cap-16 package contains an unknown task set")
      task_set = definition.parent / value.name
      portable_tasks = []
      for task in task_set.read_text(encoding="utf-8").splitlines():
        path = Path(task).resolve()
        try:
          portable_tasks.append(path.relative_to(sv_benchmarks).as_posix())
        except ValueError as error:
          raise RuntimeError(
              "cap-16 package contains a non-SV-Benchmarks task"
          ) from error
      task_set.write_text(
          "\n".join(portable_tasks) + "\n", encoding="utf-8"
      )
      node.text = value.name
    for node in root.findall(".//propertyfile"):
      node.text = "c/properties/unreach-call.prp"
    write_xml(root, definition)

  plan_path = output / "screen-plan.json"
  plan = json.loads(plan_path.read_text(encoding="utf-8"))
  result_entries = [plan["primary"], *plan["replacements"]]
  for entry in result_entries:
    result_path = output / entry["path"]
    with baseline.open_result(result_path) as source_file:
      result = ET.parse(source_file)
    for run in result.getroot().findall("run"):
      task = baseline.match_result_task(run.get("name", ""), manifest_rows)
      row = manifest_rows[task]
      if row["source"] != "sv-benchmarks":
        raise RuntimeError(
            "cap-16 package contains a non-SV-Benchmarks result row"
        )
      run.set("name", row["task_path"])
      run.set("files", f"[{', '.join(row['source_paths'])}]")
      run.set("propertyFile", "c/properties/unreach-call.prp")
    if result_path.suffix == ".bz2":
      content = ET.tostring(result.getroot(), encoding="unicode")
      result_path.write_bytes(bz2.compress(content.encode("utf-8")))
    else:
      result.write(result_path, encoding="unicode")

  plan["primary"]["sha256"] = baseline.sha256_file(
      output / plan["primary"]["path"]
  )
  if plan["taint"] is not None:
    taint_path = output / plan["taint"]["path"]
    taint = json.loads(taint_path.read_text(encoding="utf-8"))
    taint["primary_result_sha256"] = plan["primary"]["sha256"]
    taint_path.write_text(
        json.dumps(taint, indent=2) + "\n", encoding="utf-8"
    )
    plan["taint"]["sha256"] = baseline.sha256_file(taint_path)
  for entry in plan["replacements"]:
    result_path = output / entry["path"]
    definition = plan_path.parent / entry["definition_path"]
    taint_path = output / entry["taint_path"]
    entry["sha256"] = baseline.sha256_file(result_path)
    entry["definition_sha256"] = baseline.sha256_file(definition)
    taint = json.loads(taint_path.read_text(encoding="utf-8"))
    taint["primary_result_sha256"] = entry["sha256"]
    taint_path.write_text(
        json.dumps(taint, indent=2) + "\n", encoding="utf-8"
    )
    entry["taint_sha256"] = baseline.sha256_file(taint_path)
  plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
  summary = output / "summary"
  shutil.rmtree(summary)
  command_screen_summary_plan(argparse.Namespace(
      manifest=str(output / "input/candidate-manifest-athena.json"),
      benchmark_definition=str(output / "generated/hard-case-candidates.xml"),
      screen_plan=str(plan_path),
      sv_benchmarks=args.sv_benchmarks,
      phase_a_host="athena",
      output_dir=str(summary),
  ))
  artifact = baseline.write_artifact_manifest(
      output,
      output / "provenance/artifact-manifest.json",
      root_label=".",
  )
  (summary / ".complete").write_text("complete\n", encoding="utf-8")
  validate_cap16_phase_a_structure(
      output, args.sv_benchmarks, portable=True
  )
  print(json.dumps({
      "aggregate_sha256": artifact["aggregate_sha256"],
      "output": str(output),
      "task_count": json.loads(
          (output / "input/candidate-manifest-athena.json").read_text(
              encoding="utf-8"
          )
      )["task_count"],
  }, sort_keys=True))


def command_validate_cap16_phase_a(args):
  manifest, host = authenticate_cap16_phase_a_output(
      args.phase_a_output, args.sv_benchmarks
  )
  print(json.dumps({
      "host": host,
      "manifest_sha256": baseline.sha256_file(
          Path(args.phase_a_output)
          / "summary/candidate-manifest-analysis-survivors.json"
      ),
      "task_count": manifest["task_count"],
      "valid": True,
  }, sort_keys=True))


def copy_declared_corpus_files(manifest_path, manifest, output):
  source_root = Path(manifest_path).resolve().parent
  copied = set()
  for row in manifest.get("corpus_files", []):
    relative = Path(row["path"])
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or relative.as_posix() in copied
    ):
      raise RuntimeError(f"invalid declared corpus path: {row['path']}")
    source = (source_root / relative).resolve()
    try:
      source.relative_to(source_root)
    except ValueError as error:
      raise RuntimeError(
          f"declared corpus path escapes source: {row['path']}"
      ) from error
    target = output / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    copied.add(relative.as_posix())


def write_phase_b_artifact_manifest(output):
  path = output / "artifact-manifest.json"
  artifact = baseline.write_artifact_manifest(output, path, root_label=".")
  return artifact, baseline.sha256_file(path)


def command_merge_survivors(args):
  _, _, merged = authenticate_phase_b_inputs(args)
  output = Path(args.output_dir).resolve()
  require_absent_or_empty_output(output)
  output.mkdir(parents=True, exist_ok=True)
  path = output / "candidate-manifest-valkyrie-formal.json"
  path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
  manifest_sha256 = baseline.sha256_file(path)
  if manifest_sha256 != FROZEN_FORMAL_MANIFEST_SHA256:
    raise RuntimeError("merged formal manifest differs from frozen Phase-B output")
  copy_declared_corpus_files(args.parent_manifest, merged, output)
  validate_manifest(path, args.sv_benchmarks)
  artifact, artifact_sha256 = write_phase_b_artifact_manifest(output)
  print(
      json.dumps(
          {
              "aggregate_sha256": artifact["aggregate_sha256"],
              "artifact_manifest_sha256": artifact_sha256,
              "host": "valkyrie",
              "manifest_sha256": manifest_sha256,
              "task_count": merged["task_count"],
          },
          sort_keys=True,
      )
  )


def validate_manifest(manifest_path, sv_benchmarks):
  manifest_path = Path(manifest_path).resolve()
  manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
  if manifest.get("task_count") != len(manifest.get("tasks", [])):
    raise RuntimeError("candidate manifest task count is invalid")
  tasks = [row["task"] for row in manifest["tasks"]]
  if len(tasks) != len(set(tasks)):
    raise RuntimeError("candidate manifest contains duplicate tasks")
  for row in manifest.get("corpus_files", []):
    path = manifest_path.parent / row["path"]
    if not path.is_file() or baseline.sha256_file(path) != row["sha256"]:
      raise RuntimeError(f"candidate hash mismatch: {path}")
  for row in manifest["tasks"]:
    root = (
        Path(sv_benchmarks).resolve()
        if row["source"] == "sv-benchmarks"
        else manifest_path.parent
    )
    paths = [root / row["task_path"], *(root / path for path in row["source_paths"])]
    hashes = [row["task_sha256"], *row["source_sha256"]]
    for path, expected in zip(paths, hashes, strict=True):
      if not path.is_file() or baseline.sha256_file(path) != expected:
        raise RuntimeError(f"candidate hash mismatch: {path}")
  return manifest


def command_validate(args):
  manifest = validate_manifest(args.manifest, args.sv_benchmarks)
  print(json.dumps({"task_count": manifest["task_count"], "valid": True}))


def git_blob(repo, path):
  return subprocess.check_output(
      ["git", "-C", str(repo), "show", f"HEAD:{path}"]
  )


def official_license_files(repo):
  paths = subprocess.check_output(
      ["git", "-C", str(repo), "ls-tree", "-r", "--name-only", "HEAD"],
      text=True,
  ).splitlines()
  result = collections.defaultdict(list)
  for path in paths:
    if Path(path).name.lower().startswith(("license", "copying", "copyright")):
      result[Path(path).parent.as_posix()].append(path)
  return result


def official_license_evidence(repo, source_path, license_files):
  content = git_blob(repo, source_path)
  text = content.decode("utf-8", errors="replace")
  identifiers = []
  statements = []
  for line in text.splitlines():
    if "SPDX-License-Identifier:" in line:
      identifiers.append(
          line.partition("SPDX-License-Identifier:")[2].strip().rstrip("*/").strip()
      )
    match = re.search(r"Licensed under the ([^*]+)", line, re.IGNORECASE)
    if match:
      statements.append(match.group(1).strip())
  if identifiers or statements:
    return [
        {
            "kind": "source_header",
            "path": source_path,
            "sha256": hashlib.sha256(content).hexdigest(),
            "identifiers": sorted(set(identifiers)),
            "statements": sorted(set(statements)),
        }
    ]
  evidence = []
  for path in license_files.get(Path(source_path).parent.as_posix(), []):
    blob = git_blob(repo, path)
    evidence.append(
        {
            "kind": "directory_license_file",
            "path": path,
            "sha256": hashlib.sha256(blob).hexdigest(),
        }
    )
  return evidence


def command_license_audit(args):
  manifest_path = Path(args.manifest).resolve()
  validate_manifest(manifest_path, args.sv_benchmarks)
  full_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
  sv_benchmarks = Path(args.sv_benchmarks).resolve()
  external_root = Path(args.external_root).resolve()
  if git_head(sv_benchmarks) != full_manifest["repositories"]["sv-benchmarks"]:
    raise RuntimeError("sv-benchmarks revision does not match candidate manifest")
  for source in SOURCE_LICENSE_FILES:
    if git_head(external_root / source) != full_manifest["repositories"][source]:
      raise RuntimeError(f"{source} revision does not match candidate manifest")

  official_files = official_license_files(sv_benchmarks)
  included = []
  audit_rows = []
  for task in full_manifest["tasks"]:
    evidence = []
    if task["source"] == "sv-benchmarks":
      missing = []
      for source_path in task["source_paths"]:
        source_evidence = official_license_evidence(
            sv_benchmarks, source_path, official_files
        )
        if source_evidence:
          evidence.extend(source_evidence)
        else:
          missing.append(source_path)
    else:
      license_path = SOURCE_LICENSE_FILES[task["source"]]
      license_content = git_blob(external_root / task["source"], license_path)
      evidence = [
          {
              "kind": "repository_license_file",
              "repository": SOURCE_URLS[task["source"]],
              "revision": full_manifest["repositories"][task["source"]],
              "path": license_path,
              "sha256": hashlib.sha256(license_content).hexdigest(),
          }
      ]
      missing = []
    status = "included" if not missing else "license_unresolved"
    audit_rows.append(
        {
            "task": task["task"],
            "source": task["source"],
            "expected_verdict": task["expected_verdict"],
            "status": status,
            "missing_source_paths": ";".join(missing),
            "license_evidence": json.dumps(evidence, sort_keys=True),
        }
    )
    if status == "included":
      included.append(
          {
              **task,
              "license": (
                  task["license"]
                  if task["source"] != "sv-benchmarks"
                  else "see license_evidence"
              ),
              "license_evidence": evidence,
          }
      )

  output = Path(args.output_dir).resolve()
  output.mkdir(parents=True, exist_ok=True)
  if output != manifest_path.parent:
    shutil.copytree(manifest_path.parent / "corpus", output / "corpus")
    shutil.copy2(manifest_path, output / "candidate-manifest.json")
  excluded = [row for row in audit_rows if row["status"] != "included"]
  audited_manifest = {
      **full_manifest,
      "schema_version": "hard-case-candidate-v1-license-audited",
      "task_count": len(included),
      "license_audit": {
          "input_manifest_sha256": baseline.sha256_file(manifest_path),
          "selection_independent_of_verifier_outcomes": True,
          "included_task_count": len(included),
          "excluded_task_count": len(excluded),
          "excluded_tasks": [row["task"] for row in excluded],
          "repositories": {
              "sv-benchmarks": {
                  "url": SOURCE_URLS["sv-benchmarks"],
                  "revision": full_manifest["repositories"]["sv-benchmarks"],
              },
              **{
                  source: {
                      "url": SOURCE_URLS[source],
                      "revision": full_manifest["repositories"][source],
                      "license_file": SOURCE_LICENSE_FILES[source],
                  }
                  for source in SOURCE_LICENSE_FILES
              },
          },
      },
      "tasks": included,
  }
  (output / "candidate-manifest-license-audited.json").write_text(
      json.dumps(audited_manifest, indent=2) + "\n", encoding="utf-8"
  )
  fieldnames = list(audit_rows[0])
  for filename, rows in (
      ("license-audit.csv", audit_rows),
      ("license-quarantine.csv", excluded),
  ):
    with (output / filename).open("w", newline="", encoding="utf-8") as target:
      writer = csv.DictWriter(target, fieldnames=fieldnames)
      writer.writeheader()
      writer.writerows(rows)
  print(
      json.dumps(
          {
              "included": len(included),
              "license_unresolved": len(excluded),
              "manifest": str(output / "candidate-manifest-license-audited.json"),
          }
      )
  )


def classify_probe_events(events):
  if any(event.get("counterexample_visits_loop_head") is True for event in events):
    return "cegar_eligible"
  return "hook_reached_without_loop_head" if events else "structurally_unreachable"


def validate_probe_events(events):
  if not isinstance(events, list):
    raise RuntimeError("probe telemetry is not an event list")
  expected_roles = ("invariant", "counterexample", "refinement")
  for refinement, event in enumerate(events, start=1):
    if (
        not isinstance(event, dict)
        or set(event)
        != {
            "schema_version",
            "refinement",
            "counterexample_visits_loop_head",
            "provider_calls",
            "activated_candidates",
            "rejected_candidates",
        }
        or event["schema_version"] != "vguide-telemetry-v1"
        or type(event["refinement"]) is not int
        or event["refinement"] != refinement
        or not isinstance(event["counterexample_visits_loop_head"], bool)
        or event["activated_candidates"] != []
        or type(event["rejected_candidates"]) is not int
        or event["rejected_candidates"] != 0
        or not isinstance(event["provider_calls"], list)
        or len(event["provider_calls"]) != len(expected_roles)
    ):
      raise RuntimeError("probe telemetry event topology is invalid")
    for role, call in zip(
        expected_roles, event["provider_calls"], strict=True
    ):
      if (
          not isinstance(call, dict)
          or set(call) != {"agent_role", "model", "response_sha256"}
          or call["agent_role"] != role
          or call["model"] != EMPTY_PROVIDER_MODEL
          or call["response_sha256"] != EMPTY_PROVIDER_RESPONSE_SHA256
      ):
        raise RuntimeError("probe telemetry provider call is not deterministic EMPTY")
  return classify_probe_events(events)


def command_probe_summary(args):
  manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
  details = {row["task"]: row for row in manifest["tasks"]}
  with Path(args.hard_portfolio).open(newline="", encoding="utf-8") as source:
    hard_rows = list(csv.DictReader(source))
  result_files = Path(args.result_files)
  telemetry_files = list(result_files.rglob("vguide-telemetry.json"))
  rows = []
  for hard in hard_rows:
    detail = details[hard["task"]]
    task_basename = Path(detail["task_path"]).name
    matches = [
        path for path in telemetry_files if path.parent.parent.name == task_basename
    ]
    if len(matches) > 1:
      raise RuntimeError(f"multiple telemetry files for {hard['task']}")
    if not matches:
      classification = "infrastructure_failure"
      rounds = None
      telemetry_sha256 = ""
    else:
      events = json.loads(matches[0].read_text(encoding="utf-8"))
      classification = validate_probe_events(events)
      rounds = len(events)
      telemetry_sha256 = baseline.sha256_file(matches[0])
    rows.append(
        {
            **hard,
            "probe_classification": classification,
            "augmented_refinement_rounds": rounds,
            "telemetry_sha256": telemetry_sha256,
        }
    )
  output = Path(args.output_dir)
  output.mkdir(parents=True, exist_ok=True)
  fieldnames = list(rows[0]) if rows else []
  for filename, subset in (
      ("cegar-eligibility.csv", rows),
      (
          "cegar-eligible.csv",
          [row for row in rows if row["probe_classification"] == "cegar_eligible"],
      ),
      (
          "structurally-unreachable.csv",
          [
              row
              for row in rows
              if row["probe_classification"] == "structurally_unreachable"
          ],
      ),
  ):
    with (output / filename).open("w", newline="", encoding="utf-8") as target:
      writer = csv.DictWriter(target, fieldnames=fieldnames)
      writer.writeheader()
      writer.writerows(subset)
  counts = collections.Counter(row["probe_classification"] for row in rows)
  (output / "cegar-eligibility-summary.json").write_text(
      json.dumps(
          {
              "task_count": len(rows),
              "classifications": dict(sorted(counts.items())),
          },
          indent=2,
      )
      + "\n",
      encoding="utf-8",
  )


def probe_result_telemetry(result_path, manifest):
  result_path = Path(result_path).resolve()
  result_tasks = result_task_names(result_path, manifest)
  basenames = {
      task: Path(manifest[task]["task_path"]).name for task in result_tasks
  }
  if len(set(basenames.values())) != len(basenames):
    raise RuntimeError("probe result tasks have ambiguous task basenames")
  files_dirs = [
      path for path in result_path.parent.iterdir()
      if path.name.endswith(".files")
  ]
  actual = set(result_path.parent.rglob("vguide-telemetry.json"))
  if len(files_dirs) > 1:
    raise RuntimeError("probe result has multiple retrieved-result directories")
  if not files_dirs:
    if actual:
      raise RuntimeError(
          f"probe result contains misplaced telemetry: {sorted(map(str, actual))}"
      )
    return dict.fromkeys(result_tasks)
  if files_dirs[0].is_symlink() or not files_dirs[0].is_dir():
    raise RuntimeError("probe retrieved-result directory is not regular")
  expected = {
      task: (
          files_dirs[0]
          / "cegar-eligibility"
          / basename
          / "output/vguide-telemetry.json"
      )
      for task, basename in basenames.items()
  }
  unknown = actual - set(expected.values())
  if unknown:
    raise RuntimeError(
        f"probe result contains unknown telemetry: {sorted(map(str, unknown))}"
    )
  return expected


def strict_probe_summary_rows(args, cohort):
  profile = strict_probe_profile(cohort)
  validate_input = (
      validate_cap8_probe_input
      if cohort == "cap8"
      else validate_cap16_probe_input
  )
  _, manifest_path, manifest_data, hard_rows, identity = (
      validate_input(args.probe_input, args.sv_benchmarks)
  )
  manifest = baseline.load_task_manifest(manifest_path)
  validate_probe_definition(
      args.benchmark_definition,
      manifest_path,
      manifest_data,
      args.sv_benchmarks,
  )
  plan_path = Path(args.probe_plan).resolve()
  plan = load_screen_plan(
      plan_path,
      manifest,
      manifest_path,
      profile["host"],
      args.sv_benchmarks,
      args.benchmark_definition,
      plan_schema=profile["plan_schema"],
      repetition=1,
      display=PROBE_DISPLAY,
      time_limit="900 s",
      taint_schema=profile["taint_schema"],
      definition_validator=validate_probe_definition,
      hard_threshold=200,
  )
  source_by_task = {row["task"]: row for row in plan["row_sources"]}
  row_by_task = {row["task"]: row for row in plan["rows"].values()}
  telemetry_by_result = {}
  rows = []
  for hard in hard_rows:
    task = hard["task"]
    source = source_by_task[task]
    result = declared_plan_file(
        plan_path.parent,
        {
            "path": source["result_path"],
            "sha256": source["result_sha256"],
        },
        f"probe result for {task}",
    )
    if result not in telemetry_by_result:
      telemetry_by_result[result] = probe_result_telemetry(result, manifest)
    telemetry = telemetry_by_result[result][task]
    result_row = row_by_task[task]
    explicit_failure = result_row["classification"] in {
        "out_of_memory",
        "verifier_or_resource_error",
        "infrastructure_or_manifest_failure",
    }
    if telemetry is not None and telemetry.is_symlink():
      raise RuntimeError(f"probe telemetry is a symlink for {task}")
    if telemetry is not None and telemetry.exists() and not telemetry.is_file():
      raise RuntimeError(f"probe telemetry is not a regular file for {task}")
    if telemetry is not None and telemetry.is_file():
      events = json.loads(telemetry.read_text(encoding="utf-8"))
      event_classification = validate_probe_events(events)
      rounds = len(events)
      telemetry_sha256 = baseline.sha256_file(telemetry)
      if explicit_failure:
        classification = "infrastructure_failure"
        infrastructure_reason = (
            f"result failure; status={result_row['status']}; "
            f"category={result_row['category']}"
        )
      else:
        classification = (
            "no_event"
            if event_classification == "structurally_unreachable"
            else event_classification
        )
        infrastructure_reason = ""
    else:
      if not explicit_failure:
        raise RuntimeError(f"probe telemetry is unexpectedly missing for {task}")
      classification = "infrastructure_failure"
      rounds = ""
      telemetry_sha256 = ""
      infrastructure_reason = (
          f"missing telemetry; status={result_row['status']}; "
          f"category={result_row['category']}"
      )
    rows.append({
        **hard,
        "probe_classification": classification,
        "probe_refinement_rounds": rounds,
        "telemetry_sha256": telemetry_sha256,
        "probe_result_sha256": source["result_sha256"],
        "probe_result_source": source["source"],
        "infrastructure_reason": infrastructure_reason,
    })
  if {row["task"] for row in rows} != set(manifest):
    raise RuntimeError("probe summary does not cover exactly the authenticated manifest")
  return rows, plan, identity


def cap16_probe_summary_rows(args):
  return strict_probe_summary_rows(args, "cap16")


def cap8_probe_summary_rows(args):
  return strict_probe_summary_rows(args, "cap8")


def write_strict_probe_summary(args, cohort, rows_provider=None):
  profile = strict_probe_profile(cohort)
  require_absent_or_empty_output(args.output_dir)
  if rows_provider is None:
    rows_provider = lambda value: strict_probe_summary_rows(value, cohort)
  rows, plan, identity = rows_provider(args)
  output = Path(args.output_dir).resolve()
  output.mkdir(parents=True, exist_ok=True)
  fieldnames = list(rows[0])
  for filename, classification in (
      ("cegar-eligibility.csv", None),
      *STRICT_PROBE_STRATA,
  ):
    with (output / filename).open(
        "w", newline="", encoding="utf-8"
    ) as target:
      writer = csv.DictWriter(target, fieldnames=fieldnames)
      writer.writeheader()
      writer.writerows(
          rows
          if classification is None
          else (
              row for row in rows
              if row["probe_classification"] == classification
          )
      )
  row_provenance = {
      "schema_version": profile["row_provenance_schema"],
      "probe_plan_sha256": plan["plan_sha256"],
      "primary_result_sha256": plan["primary_sha256"],
      "replacement_result_sha256": plan["replacement_sha256"],
      "rows": plan["row_sources"],
  }
  provenance_path = output / "row-provenance.json"
  provenance_path.write_text(
      json.dumps(row_provenance, indent=2) + "\n", encoding="utf-8"
  )
  counts = collections.Counter(row["probe_classification"] for row in rows)
  summary = {
      "schema_version": profile["summary_schema"],
      "task_count": len(rows),
      "classifications": dict(sorted(counts.items())),
      "host": profile["host"],
      "provider": "EMPTY",
      "activated_candidate_count": 0,
      "formal_artifact_aggregate_sha256": identity[
          "formal_artifact_aggregate_sha256"
      ],
      "probe_input_manifest_sha256": identity["probe_manifest_sha256"],
      "probe_plan_sha256": plan["plan_sha256"],
      "row_provenance_sha256": baseline.sha256_file(provenance_path),
  }
  (output / "summary.json").write_text(
      json.dumps(summary, indent=2) + "\n", encoding="utf-8"
  )
  return summary


def write_cap8_probe_summary(args):
  return write_strict_probe_summary(args, "cap8", cap8_probe_summary_rows)


def write_cap16_probe_summary(args):
  return write_strict_probe_summary(
      args, "cap16", cap16_probe_summary_rows
  )


def command_cap8_probe_summary(args):
  print(json.dumps(write_cap8_probe_summary(args), sort_keys=True))


def command_cap16_probe_summary(args):
  print(json.dumps(write_cap16_probe_summary(args), sort_keys=True))


def classify_screen_result(row):
  if row["category"] == "wrong":
    return "wrong_quarantine"
  if (
      row["classification"] == "infrastructure_or_manifest_failure"
      or (
          row["category"] == "correct"
          and row["cpu_time_seconds"] is None
      )
  ):
    return "infrastructure_failure"
  if row["category"] == "correct":
    return "correct_fast"
  if is_analysis_unsolved(row):
    return "analysis_survivor"
  return "verifier_failure_quarantine"


def validate_phase_a_host(result_path, requested_host, manifest_host):
  with baseline.open_result(Path(result_path)) as source:
    root = ET.parse(source).getroot()
  systeminfo = root.findall("systeminfo")
  if len(systeminfo) != 1 or not systeminfo[0].get("hostname"):
    raise RuntimeError("screen result must contain exactly one systeminfo hostname")
  result_host = systeminfo[0].get("hostname")
  if (
      requested_host not in DISCOVERY_HOSTS
      or manifest_host != requested_host
      or result_host != requested_host
  ):
    raise RuntimeError("Phase-A host does not match result and manifest provenance")
  return requested_host


def command_screen_summary(args):
  manifest_path = Path(args.manifest).resolve()
  manifest = validate_manifest(manifest_path, args.sv_benchmarks)
  phase_a_host = validate_phase_a_host(
      args.result,
      args.phase_a_host,
      manifest.get("derivation", {}).get("host"),
  )
  parsed_manifest = baseline.load_task_manifest(manifest_path)
  runs = baseline.parse_result_rows(args.result, parsed_manifest, hard_threshold=200)
  write_screen_summary(
      args,
      manifest_path,
      manifest,
      phase_a_host,
      runs,
      {
          "result_sha256": baseline.sha256_file(Path(args.result)),
      },
  )


def write_screen_summary(
    args,
    manifest_path,
    manifest,
    phase_a_host,
    runs,
    provenance,
):
  missing_metrics = [
      run["task"]
      for run in runs
      if run["cpu_time_seconds"] is None or run["wall_time_seconds"] is None
  ]
  if missing_metrics:
    raise RuntimeError(
        f"screen result lacks parseable CPU or wall metrics: {missing_metrics}"
    )
  details = {row["task"]: row for row in manifest["tasks"]}
  rows = [
      {
          "task": run["task"],
          "phase_a_host": phase_a_host,
          "source": details[run["task"]]["source"],
          "family": details[run["task"]]["family"],
          "expected_verdict": run["expected_verdict"],
          "classification": classify_screen_result(run),
          "cpu_seconds": run["cpu_time_seconds"],
          "wall_seconds": run["wall_time_seconds"],
          "status": run["status"],
      }
      for run in runs
  ]
  output = Path(args.output_dir).resolve()
  if output.exists() and any(output.iterdir()):
    raise RuntimeError(f"output directory must be absent or empty: {output}")
  output.mkdir(parents=True, exist_ok=True)
  shutil.copytree(manifest_path.parent / "corpus", output / "corpus")
  fieldnames = list(rows[0])
  filenames = {
      "correct_fast": "correct-fast.csv",
      "analysis_survivor": "analysis-survivors.csv",
      "wrong_quarantine": "wrong-quarantine.csv",
      "verifier_failure_quarantine": "verifier-failure-quarantine.csv",
      "infrastructure_failure": "infrastructure-failure.csv",
  }
  for classification, filename in filenames.items():
    with (output / filename).open("w", newline="", encoding="utf-8") as target:
      writer = csv.DictWriter(target, fieldnames=fieldnames)
      writer.writeheader()
      writer.writerows(
          row for row in rows if row["classification"] == classification
      )
  with (output / "classification.csv").open(
      "w", newline="", encoding="utf-8"
  ) as target:
    writer = csv.DictWriter(target, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
  survivor_tasks = [
      row["task"] for row in rows if row["classification"] == "analysis_survivor"
  ]
  survivor_manifest = manifest_subset(
      manifest,
      survivor_tasks,
      {
          "operation": "phase_a_analysis_survivors",
          "parent_manifest_sha256": baseline.sha256_file(manifest_path),
          **provenance,
          "allowed_results": sorted(ANALYSIS_UNSOLVED),
          "phase_a_host": phase_a_host,
          "selection_independent_of_augmented_outcomes": True,
      },
  )
  survivor_path = output / "candidate-manifest-analysis-survivors.json"
  survivor_path.write_text(
      json.dumps(survivor_manifest, indent=2) + "\n", encoding="utf-8"
  )
  validate_manifest(survivor_path, args.sv_benchmarks)
  counts = collections.Counter(row["classification"] for row in rows)
  summary = {
      "task_count": len(rows),
      "phase_a_host": phase_a_host,
      "classifications": dict(sorted(counts.items())),
      **provenance,
      "survivor_manifest_sha256": baseline.sha256_file(survivor_path),
  }
  (output / "summary.json").write_text(
      json.dumps(summary, indent=2) + "\n", encoding="utf-8"
  )
  print(json.dumps(summary, sort_keys=True))


def command_screen_summary_plan(args):
  manifest_path = Path(args.manifest).resolve()
  manifest = validate_manifest(manifest_path, args.sv_benchmarks)
  host = manifest.get("derivation", {}).get("host")
  if args.phase_a_host != host or host not in DISCOVERY_HOSTS:
    raise RuntimeError("Phase-A host does not match manifest provenance")
  validate_screen_definition(
      args.benchmark_definition,
      manifest_path,
      manifest,
      args.sv_benchmarks,
  )
  rows = baseline.load_task_manifest(manifest_path)
  plan = load_screen_plan(
      args.screen_plan,
      rows,
      manifest_path,
      host,
      args.sv_benchmarks,
      args.benchmark_definition,
  )
  output = Path(args.output_dir).resolve()
  row_provenance_content = json.dumps({
      "schema_version": "hard-case-screen-row-provenance-v1",
      "screen_plan_sha256": plan["plan_sha256"],
      "primary_result_sha256": plan["primary_sha256"],
      "replacement_result_sha256": plan["replacement_sha256"],
      "rows": plan["row_sources"],
  }, indent=2) + "\n"
  write_screen_summary(
      args,
      manifest_path,
      manifest,
      host,
      [plan["rows"][task] for task in rows],
      {
          "screen_plan_sha256": plan["plan_sha256"],
          "result_sha256": [
              plan["primary_sha256"],
              *plan["replacement_sha256"],
          ],
          "row_provenance_sha256": hashlib.sha256(
              row_provenance_content.encode("utf-8")
          ).hexdigest(),
      },
  )
  (output / "row-provenance.json").write_text(
      row_provenance_content, encoding="utf-8"
  )


def declared_plan_file(root, entry, label):
  if (
      not isinstance(entry, dict)
      or set(entry) != {"path", "sha256"}
      or not isinstance(entry["path"], str)
      or not isinstance(entry["sha256"], str)
      or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
  ):
    raise RuntimeError(f"{label} must declare only path and sha256")
  relative = Path(entry["path"])
  if relative.is_absolute() or ".." in relative.parts:
    raise RuntimeError(f"{label} path must stay inside the repetition-plan directory")
  path = root / relative
  absolute = Path(os.path.abspath(path))
  if path.is_symlink() or not path.is_file() or path.resolve() != absolute:
    raise RuntimeError(f"{label} must be a regular non-symlink file")
  if baseline.sha256_file(path) != entry["sha256"]:
    raise RuntimeError(f"{label} hash does not match")
  return absolute


def plan_file_entry(path, root):
  declared = Path(path)
  path = declared.resolve()
  try:
    relative = path.relative_to(root)
  except ValueError as error:
    raise RuntimeError("repetition-plan inputs must stay inside its directory") from error
  if (
      declared.is_symlink()
      or Path(os.path.abspath(declared)) != path
      or not path.is_file()
  ):
    raise RuntimeError(f"repetition-plan input must be a regular file: {path}")
  return {
      "path": relative.as_posix(),
      "sha256": baseline.sha256_file(path),
  }


def result_task_names(path, manifest):
  with baseline.open_result(Path(path)) as source:
    root = ET.parse(source).getroot()
  tasks = [
      baseline.match_result_task(run.get("name", ""), manifest)
      for run in root.findall("run")
  ]
  if len(tasks) != len(set(tasks)):
    raise RuntimeError("result contains duplicate task names")
  return tasks


def validate_taint_manifest(
    data,
    repetition,
    primary_hash,
    manifest,
    schema=FORMAL_TAINT_SCHEMA,
):
  if not isinstance(data, dict) or set(data) != {
      "schema_version",
      "repetition",
      "primary_result_sha256",
      "tasks",
  }:
    raise RuntimeError("formal taint manifest topology is not exact")
  if (
      data["schema_version"] != schema
      or not isinstance(data["repetition"], int)
      or data["repetition"] not in {1, 2}
      or data["repetition"] != repetition
      or data["primary_result_sha256"] != primary_hash
      or not isinstance(data["tasks"], list)
  ):
    raise RuntimeError("formal taint manifest identity does not match")
  tasks = {}
  for row in data["tasks"]:
    if (
        not isinstance(row, dict)
        or set(row) != {"task", "reason"}
        or not isinstance(row["task"], str)
        or not isinstance(row["reason"], str)
        or row["task"] not in manifest
        or row["reason"] not in FORMAL_TAINT_REASONS
        or row["task"] in tasks
    ):
      raise RuntimeError("formal taint task is invalid or duplicated")
    tasks[row["task"]] = row["reason"]
  if list(tasks) != sorted(tasks):
    raise RuntimeError("formal taint tasks must be sorted")
  return tasks


def read_proc_thread_stat(path):
  text = path.read_text(encoding="utf-8")
  fields = text[text.rfind(")") + 2 :].split()
  return (
      int(fields[11]) + int(fields[12]),
      int(fields[19]),
      int(fields[36]),
  )


def formal_systemd_unit(output_root, mode, label):
  root = Path(output_root).resolve()
  digest = sha256_text(f"{root}\0{mode}\0{label}")[:12]
  return f"vguide-{mode}-{label}-{digest}.scope"


def formal_process_descriptor(args):
  root = Path(args.output_root).resolve()
  definition = Path(args.definition).resolve()
  result_output = Path(args.result_output).resolve()
  monitor_output = Path(args.monitor_output).resolve()
  dataset_py = Path(args.dataset_py).resolve()
  cpachecker_dir = Path(args.cpachecker_dir).resolve()
  benchexec_dir = Path(args.benchexec_dir).resolve()
  python_bin = Path(args.python_bin).resolve()
  java_home = Path(args.java_home).resolve()
  for path, name in (
      (definition, "definition"),
      (result_output, "result output"),
      (monitor_output, "monitor output"),
      (dataset_py, "dataset script"),
  ):
    try:
      path.relative_to(root)
    except ValueError as error:
      raise RuntimeError(
          f"formal process {name} escapes output root"
      ) from error
  if (
      args.mode not in {"cap8", "cap16", "cap8-probe", "cap16-probe"}
      or args.p_cores != FORMAL_P_CORE_LIST
      or not isinstance(args.monitor_exclude_root, int)
      or args.monitor_exclude_root <= 0
  ):
    raise RuntimeError("formal process descriptor inputs are invalid")
  expected_host = (
      "athena" if args.mode in {"cap16", "cap16-probe"} else "valkyrie"
  )
  expected_python = (
      Path("/usr/bin/python3.12")
      if args.mode in {"cap16", "cap16-probe"}
      else Path("/usr/bin/python3.10")
  )
  if (
      args.host != expected_host
      or python_bin != expected_python
      or dataset_py != root / "input/research/scripts/dataset.py"
  ):
    raise RuntimeError("formal process descriptor runtime is not pinned")
  expected_name = (
      f"hard-case-dataset-v2-{args.mode.removesuffix('-probe')}"
      f"-cegar-probe-{args.host}-{args.label}"
      if is_strict_probe_mode(args.mode)
      else (
          f"hard-case-dataset-v2"
          f"{'-cap16' if args.mode == 'cap16' else ''}"
          f"-formal-{args.host}-{args.label}"
      )
  )
  if args.name != expected_name:
    raise RuntimeError("formal BenchExec run name is not canonical")
  unit = formal_systemd_unit(root, args.mode, args.label)
  monitor_argv = [
      str(python_bin),
      *PYTHON_RUNTIME_FLAGS,
      str(dataset_py),
      "monitor-formal-load",
      "--output",
      str(monitor_output),
      "--exclude-root",
      str(args.monitor_exclude_root),
  ]
  benchexec_argv = [
      "systemd-run",
      "--user",
      "--quiet",
      "--scope",
      f"--unit={unit}",
      "--slice=benchexec",
      "-p",
      "Delegate=yes",
      "taskset",
      "-c",
      args.p_cores,
      "env",
      "-i",
      "HOME=/home/benchexec",
      "LANG=C.UTF-8",
      "LC_ALL=C.UTF-8",
      "PATH=/usr/bin:/bin",
      f"JAVA={java_home}/bin/java",
      str(python_bin),
      *PYTHON_RUNTIME_FLAGS,
      "-c",
      BENCHEXEC_MODULE_COMMAND,
      str(benchexec_dir),
      FORMAL_PYYAML_FILE,
      "--name",
      args.name,
      "--tool-directory",
      str(cpachecker_dir),
      "--outputpath",
      f"{result_output}/",
      "--allowedCores",
      args.p_cores,
      "--no-hyperthreading",
      "--container",
      "--read-only-dir",
      "/",
      "--hidden-dir",
      "/home",
      "--overlay-dir",
      str(cpachecker_dir),
      "-N",
      "8" if is_strict_probe_mode(args.mode) else "2",
      "-c",
      "1" if is_strict_probe_mode(args.mode) else "4",
      str(definition),
  ]
  return {
      "schema_version": FORMAL_PROCESS_DESCRIPTOR_SCHEMA,
      "output_root": str(root),
      "mode": args.mode,
      "label": args.label,
      "host": args.host,
      "inputs": {
          "name": args.name,
          "definition": str(definition),
          "result_output": str(result_output),
          "monitor_output": str(monitor_output),
          "monitor_exclude_root": args.monitor_exclude_root,
          "dataset_py": str(dataset_py),
          "cpachecker_dir": str(cpachecker_dir),
          "benchexec_dir": str(benchexec_dir),
          "python_bin": str(python_bin),
          "java_home": str(java_home),
          "p_cores": args.p_cores,
      },
      "systemd_unit": unit,
      "identities": {
          "benchexec-launcher": {
              "argv": benchexec_argv,
              "systemd_unit": unit,
          },
          "load-monitor": {
              "argv": monitor_argv,
              "systemd_unit": None,
          },
      },
  }


def load_formal_process_descriptor(path, output_root, mode, label, host):
  declared = Path(path)
  resolved = declared.resolve()
  if (
      declared.is_symlink()
      or Path(os.path.abspath(declared)) != resolved
      or not resolved.is_file()
  ):
    raise RuntimeError("formal process descriptor is not a regular file")
  descriptor = json.loads(resolved.read_text(encoding="utf-8"))
  if (
      not isinstance(descriptor, dict)
      or set(descriptor) != {
          "schema_version",
          "output_root",
          "mode",
          "label",
          "host",
          "inputs",
          "systemd_unit",
          "identities",
      }
      or descriptor["schema_version"] != FORMAL_PROCESS_DESCRIPTOR_SCHEMA
      or descriptor["output_root"] != str(Path(output_root).resolve())
      or descriptor["mode"] != mode
      or descriptor["label"] != label
      or descriptor["host"] != host
      or not isinstance(descriptor["inputs"], dict)
  ):
    raise RuntimeError("formal process descriptor identity is invalid")
  expected = formal_process_descriptor(argparse.Namespace(
      output_root=descriptor["output_root"],
      mode=descriptor["mode"],
      label=descriptor["label"],
      host=descriptor["host"],
      **descriptor["inputs"],
  ))
  if descriptor != expected:
    raise RuntimeError("formal process descriptor content is invalid")
  return descriptor


def command_write_formal_process_descriptor(args):
  declared = Path(args.output)
  if declared.is_symlink():
    raise RuntimeError("formal process descriptor output is a symlink")
  output = declared.resolve()
  record = formal_process_descriptor(args)
  content = json.dumps(record, indent=2) + "\n"
  if output.exists():
    if output.read_text(encoding="utf-8") != content:
      raise RuntimeError("formal process descriptor already differs")
    return
  output.parent.mkdir(parents=True, exist_ok=True)
  temporary = output.with_name(f".{output.name}.tmp-{os.getpid()}")
  temporary.write_text(content, encoding="utf-8")
  os.replace(temporary, output)


def command_formal_systemd_unit(args):
  print(formal_systemd_unit(args.output_root, args.mode, args.label))


def read_process_identity(pid, role):
  proc = Path("/proc") / str(pid)
  status = proc.joinpath("status").read_text(encoding="utf-8")
  uid = int(re.search(r"^Uid:\s+(\d+)", status, re.MULTILINE).group(1))
  stat_fields = proc.joinpath("stat").read_text(encoding="utf-8")
  starttime = int(stat_fields[stat_fields.rfind(")") + 2 :].split()[19])
  argv = [
      value.decode("utf-8", "surrogateescape")
      for value in proc.joinpath("cmdline").read_bytes().split(b"\0")
      if value
  ]
  return {
      "schema_version": "formal-owned-process-identity-v1",
      "role": role,
      "uid": uid,
      "pid": pid,
      "proc_starttime": starttime,
      "argv": argv,
      "systemd_unit": None,
  }


def command_capture_process_identity(args):
  identity = read_process_identity(args.pid, args.role)
  output = Path(args.output)
  output.write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")


def load_owned_process_identity(path):
  identity = json.loads(Path(path).read_text(encoding="utf-8"))
  if (
      not isinstance(identity, dict)
      or set(identity) != {
          "schema_version",
          "role",
          "uid",
          "pid",
          "proc_starttime",
          "argv",
          "systemd_unit",
      }
      or identity["schema_version"] != "formal-owned-process-identity-v1"
  ):
    raise RuntimeError("owned process identity is invalid")
  return identity


def require_process_gone(identity, systemd_unit=None):
  try:
    current = read_process_identity(identity["pid"], identity["role"])
  except (FileNotFoundError, ProcessLookupError):
    current = None
  if current is not None:
    current["systemd_unit"] = identity["systemd_unit"]
  if current == identity:
    raise RuntimeError("owned formal process is still alive; refusing resume")
  unit = identity["systemd_unit"] if systemd_unit is None else systemd_unit
  if unit is not None:
    result = subprocess.run(
        [
            "systemctl",
            "--user",
            "show",
            unit,
            "--property=LoadState",
            "--property=ActiveState",
            "--property=MainPID",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
      raise RuntimeError("cannot prove transient BenchExec unit is gone")
    state = dict(
        line.split("=", 1)
        for line in result.stdout.splitlines()
        if "=" in line
    )
    if (
        state.get("LoadState") != "not-found"
        and (
            state.get("ActiveState") not in {"inactive", "failed"}
            or state.get("MainPID") not in {"0", ""}
        )
    ):
      raise RuntimeError("transient BenchExec unit is still active")


def validate_formal_process_identity(identity, expected, require_unit=True):
  if (
      identity["role"] != expected["role"]
      or identity["uid"] != os.getuid()
      or identity["argv"] != expected["argv"]
      or (
          require_unit
          and identity["systemd_unit"] != expected["systemd_unit"]
      )
  ):
    raise RuntimeError("owned process identity does not match its descriptor")


def command_require_formal_process_gone(args):
  descriptor = load_formal_process_descriptor(
      args.descriptor, args.output_root, args.mode, args.label, args.host
  )
  identity = load_owned_process_identity(args.identity)
  expected = {
      "role": args.role,
      **descriptor["identities"][args.role],
  }
  validate_formal_process_identity(identity, expected, require_unit=False)
  require_process_gone(identity, descriptor["systemd_unit"] if (
      args.role == "benchexec-launcher"
  ) else None)
  validate_formal_process_identity(identity, expected)


def command_monitor_formal_load(args):
  output = Path(args.output).resolve()
  if output.exists():
    raise RuntimeError(f"load-monitor output already exists: {output}")
  output.parent.mkdir(parents=True, exist_ok=True)
  clock_ticks = os.sysconf("SC_CLK_TCK")
  running = True

  def stop(*_):
    nonlocal running
    running = False

  signal.signal(signal.SIGTERM, stop)
  signal.signal(signal.SIGINT, stop)
  previous = {}
  previous_monotonic = time.monotonic()
  streaks = {}
  with output.open("x", encoding="utf-8", buffering=1) as target:
    target.write(json.dumps({
        "schema_version": FORMAL_LOAD_MONITOR_SCHEMA,
        "p_core_cpus": list(FORMAL_P_CORE_CPUS),
        "foreign_process_cpu_percent": FORMAL_FOREIGN_CPU_PERCENT,
        "minimum_consecutive_seconds": FORMAL_FOREIGN_CPU_SECONDS,
        "sample_interval_seconds": FORMAL_LOAD_SAMPLE_SECONDS,
        "excluded_process_root": args.exclude_root,
    }, sort_keys=True) + "\n")
    while running:
      time.sleep(FORMAL_LOAD_SAMPLE_SECONDS)
      now_monotonic = time.monotonic()
      elapsed = now_monotonic - previous_monotonic
      now = datetime.datetime.now().astimezone()
      processes = {}
      parents = {}
      for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
          continue
        try:
          status = (proc / "status").read_text(encoding="utf-8")
          parent = int(re.search(r"^PPid:\s+(\d+)$", status, re.MULTILINE).group(1))
          parents[int(proc.name)] = parent
        except (
            FileNotFoundError,
            PermissionError,
            ProcessLookupError,
            AttributeError,
            ValueError,
        ):
          continue
      excluded = {args.exclude_root}
      changed = True
      while changed:
        before = len(excluded)
        excluded.update(pid for pid, parent in parents.items() if parent in excluded)
        changed = len(excluded) != before
      current = {}
      for pid in parents:
        if pid in excluded:
          continue
        proc = Path("/proc") / str(pid)
        try:
          comm = (proc / "comm").read_text(encoding="utf-8").strip()
          uid = proc.stat().st_uid
          _, process_started, _ = read_proc_thread_stat(proc / "stat")
          for thread in (proc / "task").iterdir():
            ticks, thread_started, processor = read_proc_thread_stat(
                thread / "stat"
            )
            key = (pid, int(thread.name), thread_started)
            current[key] = ticks
            if key in previous and processor in FORMAL_P_CORE_CPUS:
              delta = ticks - previous[key]
              if delta >= 0:
                processes.setdefault(
                    pid, [0, uid, comm, process_started]
                )[0] += delta
        except (FileNotFoundError, PermissionError, ProcessLookupError, ValueError):
          continue
      qualifying = {}
      for pid, (ticks, uid, comm, started) in processes.items():
        percent = ticks / clock_ticks / elapsed * 100
        if percent >= FORMAL_FOREIGN_CPU_PERCENT:
          qualifying[(pid, started)] = (percent, uid, comm)
      for key in set(streaks) - set(qualifying):
        del streaks[key]
      offenders = []
      for key, (percent, uid, comm) in sorted(qualifying.items()):
        if key not in streaks:
          streaks[key] = (
              previous_monotonic,
              now - datetime.timedelta(seconds=elapsed),
          )
        since_monotonic, since = streaks[key]
        duration = now_monotonic - since_monotonic
        offenders.append({
            "pid": key[0],
            "uid": uid,
            "comm": comm,
            "cpu_percent": round(percent, 3),
            "duration_seconds": round(duration, 3),
            "since": since.isoformat(),
            "contended": duration >= FORMAL_FOREIGN_CPU_SECONDS,
        })
      target.write(json.dumps({
          "timestamp": now.isoformat(),
          "elapsed_seconds": round(elapsed, 6),
          "offenders": offenders,
      }, sort_keys=True) + "\n")
      previous = current
      previous_monotonic = now_monotonic


def formal_attempt_path(root, value, label):
  declared = Path(value)
  path = declared.resolve()
  try:
    relative = path.relative_to(root)
  except ValueError as error:
    raise RuntimeError(f"{label} escapes formal output") from error
  if (
      declared.is_symlink()
      or Path(os.path.abspath(declared)) != path
      or not path.is_file()
  ):
    raise RuntimeError(f"{label} is not a regular file")
  return path, relative.as_posix()


def machine_check_record(before, after):
  before_data = json.loads(before.read_text(encoding="utf-8"))
  after_data = json.loads(after.read_text(encoding="utf-8"))
  if before_data.get("hostname") != after_data.get("hostname"):
    raise RuntimeError("attempt machine snapshots have different hosts")
  deltas = {}
  for name in (
      "package_throttle_count",
      "package_throttle_total_time_ms",
      "pswpin_pages",
      "pswpout_pages",
  ):
    start = int(before_data["measurement_counters"][name])
    end = int(after_data["measurement_counters"][name])
    if end < start:
      raise RuntimeError(f"attempt machine counter decreased: {name}")
    deltas[name] = end - start
  changed = any(deltas.values())
  return {
      "hostname": before_data["hostname"],
      "accepted": True,
      "stable": not changed,
      "counter_deltas": deltas,
      "warnings": (
          ["thermal throttling or swap activity observed"] if changed else []
      ),
  }


def validate_monitor_stop_evidence(path, pid, mode, benchexec_exit):
  stopped = {}
  for line in Path(path).read_text(encoding="utf-8").splitlines():
    key, value = line.split("=", 1)
    stopped[key] = value
  normal_stop = stopped == {
      "pid": str(pid),
      "exit": "0",
      "samples": stopped.get("samples"),
  }
  recovered_stop = stopped == {
      "pid": str(pid),
      "exit": "unobserved",
      "samples": stopped.get("samples"),
      "recovery": "authenticated-process-gone",
  }
  if (
      (not normal_stop and not recovered_stop)
      or not stopped["samples"].isdigit()
      or int(stopped["samples"]) <= 0
      or (
          normal_stop
          and benchexec_exit not in {0, 130}
          and (not is_strict_probe_mode(mode) or benchexec_exit != 125)
      )
      or (
          recovered_stop
          and (not is_strict_probe_mode(mode) or benchexec_exit != 125)
      )
  ):
    raise RuntimeError("formal attempt monitor stop evidence is invalid")
  return recovered_stop


def formal_attempt_record(args):
  root = Path(args.output_root).resolve()
  manifest_path = Path(args.manifest).resolve()
  manifest = baseline.load_task_manifest(manifest_path)
  paths = {}
  for name in (
      "definition",
      "result",
      "benchexec_log",
      "benchexec_process",
      "process_descriptor",
      "load_monitor",
      "monitor_pid",
      "monitor_process",
      "monitor_stopped",
      "machine_before",
      "machine_after",
      "machine_check",
  ):
    path, relative = formal_attempt_path(
        root, getattr(args, name), name.replace("_", " ")
    )
    paths[name] = (path, relative)
  result_tasks = result_task_names(paths["result"][0], manifest)
  subset = {task: manifest[task] for task in result_tasks}
  subset_manifest = {
      "task_count": len(result_tasks),
      "tasks": [manifest[task] for task in result_tasks],
  }
  if is_strict_probe_mode(args.mode):
    validate_probe_definition(
        paths["definition"][0],
        manifest_path,
        subset_manifest,
        args.sv_benchmarks,
    )
    metadata = probe_result_metadata(
        paths["result"][0], allow_incomplete=True
    )
  else:
    validate_formal_definition(
        paths["definition"][0],
        manifest_path,
        subset_manifest,
        args.sv_benchmarks,
    )
    metadata = result_metadata(
        paths["result"][0], FORMAL_DISPLAY, "900 s", allow_incomplete=True
    )
  if metadata["host"] != args.host:
    raise RuntimeError("formal attempt host is invalid")
  validate_result_run_topology(
      paths["result"][0],
      subset,
      args.sv_benchmarks,
      paths["definition"][0],
  )
  if not paths["benchexec_log"][0].read_text(
      encoding="utf-8", errors="replace"
  ):
    raise RuntimeError("formal attempt BenchExec log is empty")
  benchexec_identity = load_owned_process_identity(
      paths["benchexec_process"][0]
  )
  process_descriptor = load_formal_process_descriptor(
      paths["process_descriptor"][0],
      root,
      args.mode,
      args.label,
      args.host,
  )
  load_formal_contention_intervals(paths["load_monitor"][0])
  monitor_header = json.loads(
      paths["load_monitor"][0].read_text(encoding="utf-8").splitlines()[0]
  )
  descriptor_inputs = process_descriptor["inputs"]
  if (
      descriptor_inputs["definition"] != str(paths["definition"][0])
      or descriptor_inputs["result_output"] != str(paths["result"][0].parent)
      or descriptor_inputs["monitor_output"] != str(paths["load_monitor"][0])
      or descriptor_inputs["monitor_exclude_root"]
      != monitor_header["excluded_process_root"]
  ):
    raise RuntimeError(
        "formal process descriptor does not match attempt evidence"
    )
  if (
      benchexec_identity.get("role") != "benchexec-launcher"
      or benchexec_identity.get("uid") != os.getuid()
  ):
    raise RuntimeError("formal BenchExec process identity is invalid")
  validate_formal_process_identity(benchexec_identity, {
      "role": "benchexec-launcher",
      **process_descriptor["identities"]["benchexec-launcher"],
  })
  require_process_gone(
      benchexec_identity, process_descriptor["systemd_unit"]
  )
  pid = int(paths["monitor_pid"][0].read_text(encoding="utf-8"))
  process_identity = load_owned_process_identity(
      paths["monitor_process"][0]
  )
  if (
      process_identity.get("pid") != pid
      or process_identity.get("uid") != os.getuid()
      or process_identity.get("role") != "load-monitor"
  ):
    raise RuntimeError("formal attempt monitor process identity is invalid")
  validate_formal_process_identity(process_identity, {
      "role": "load-monitor",
      **process_descriptor["identities"]["load-monitor"],
  })
  require_process_gone(process_identity)
  validate_monitor_stop_evidence(
      paths["monitor_stopped"][0],
      pid,
      args.mode,
      args.benchexec_exit,
  )
  expected_check = machine_check_record(
      paths["machine_before"][0], paths["machine_after"][0]
  )
  if expected_check["hostname"] != args.host:
    raise RuntimeError("formal attempt machine host is invalid")
  actual_check = json.loads(
      paths["machine_check"][0].read_text(encoding="utf-8")
  )
  if actual_check != expected_check:
    raise RuntimeError("formal attempt machine check is invalid")
  return {
      "schema_version": FORMAL_ATTEMPT_SCHEMA,
      "mode": args.mode,
      "host": args.host,
      "manifest_sha256": baseline.sha256_file(manifest_path),
      "label": args.label,
      "role": args.role,
      "repetition": args.repetition,
      "benchexec_exit": args.benchexec_exit,
      "result_tasks": sorted(result_tasks),
      "result_incomplete": metadata["incomplete"],
      "files": {
          name: {
              "path": relative,
              "sha256": baseline.sha256_file(path),
          }
          for name, (path, relative) in sorted(paths.items())
      },
  }


def validate_formal_attempt_marker(
    marker_path, root, manifest_path, sv_benchmarks, host, mode
):
  marker = Path(marker_path).resolve()
  record = json.loads(marker.read_text(encoding="utf-8"))
  if (
      not isinstance(record, dict)
      or set(record) != {
          "schema_version",
          "mode",
          "host",
          "manifest_sha256",
          "label",
          "role",
          "repetition",
          "benchexec_exit",
          "result_tasks",
          "result_incomplete",
          "files",
      }
      or record["schema_version"] != FORMAL_ATTEMPT_SCHEMA
      or record["mode"] != mode
      or record["host"] != host
      or record["manifest_sha256"] != baseline.sha256_file(manifest_path)
      or record["role"] not in {"primary", "replacement"}
      or marker.stem != record["label"]
      or not isinstance(record["files"], dict)
      or set(record["files"]) != {
          "definition",
          "result",
          "benchexec_log",
          "benchexec_process",
          "process_descriptor",
          "load_monitor",
          "monitor_pid",
          "monitor_process",
          "monitor_stopped",
          "machine_before",
          "machine_after",
          "machine_check",
      }
  ):
    raise RuntimeError("formal attempt marker schema or identity is invalid")
  canonical_label = (
      f"repetition-{record['repetition']}"
      if record["role"] == "primary"
      else rf"repetition-{record['repetition']}-replacement-attempt-[1-9]\d*"
  )
  if (
      record["label"] != canonical_label
      if record["role"] == "primary"
      else re.fullmatch(canonical_label, record["label"]) is None
  ):
    raise RuntimeError("formal attempt marker label is not canonical")
  args = argparse.Namespace(
      output_root=str(root),
      manifest=str(manifest_path),
      sv_benchmarks=str(sv_benchmarks),
      host=host,
      mode=mode,
      label=record["label"],
      role=record["role"],
      repetition=record["repetition"],
      benchexec_exit=record["benchexec_exit"],
      **{
          name: str(Path(root) / entry["path"])
          for name, entry in record["files"].items()
      },
  )
  expected = formal_attempt_record(args)
  if expected != record:
    raise RuntimeError("formal attempt marker content is invalid")
  return record


def command_formal_attempt_complete(args):
  output = Path(args.output).resolve()
  record = formal_attempt_record(args)
  content = json.dumps(record, indent=2) + "\n"
  if output.exists():
    if output.read_text(encoding="utf-8") != content:
      raise RuntimeError("formal attempt completion marker is invalid")
  else:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp-{os.getpid()}")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, output)
  validate_formal_attempt_marker(
      output,
      Path(args.output_root).resolve(),
      Path(args.manifest).resolve(),
      args.sv_benchmarks,
      args.host,
      args.mode,
  )
  print(output)


def validate_formal_closure(args):
  root = Path(args.output_root).resolve()
  manifest_path = Path(args.manifest).resolve()
  validate_manifest(manifest_path, args.sv_benchmarks)
  manifest = baseline.load_task_manifest(manifest_path)
  if len(args.repetition_plan) != 2:
    raise RuntimeError("formal closure requires exactly two repetition plans")
  complete = root / "summary/.complete"
  if args.require_complete:
    if (
        complete.is_symlink()
        or not complete.is_file()
        or complete.read_text(encoding="utf-8") != "complete\n"
    ):
      raise RuntimeError("formal output completion sentinel is invalid")
  elif complete.exists():
    raise RuntimeError("formal output completed before closure validation")
  expected_summary = {
      "classification.csv",
      "hard-portfolio.csv",
      "mixed.csv",
      "row-provenance.json",
      "summary.json",
      "verifier-failure-quarantine.csv",
      "wrong-quarantine.csv",
  }
  actual_summary = {
      path.name
      for path in (root / "summary").iterdir()
      if path.name != ".complete"
  }
  if actual_summary != expected_summary:
    raise RuntimeError("formal summary topology is incomplete")
  artifact = root / "provenance/artifact-manifest.json"
  validate_artifact_manifest(
      root, artifact, {"summary/.complete"}
  )
  mandatory = [
      "input/research/inventory.sha256",
      "provenance/build.log",
      "provenance/cgroup-check.log",
      "provenance/machine-preflight-start.json",
      "provenance/machine-preflight-end.json",
      "provenance/machine-preflight-check.json",
      "provenance/research-verification-final.log",
      "provenance/runtime-verification-final.log",
      "provenance/runtime-closure.txt",
  ]
  for relative in mandatory:
    if not (root / relative).is_file():
      raise RuntimeError(f"formal closure lacks mandatory file: {relative}")
  marker_records = {}
  marker_dir = root / "provenance/attempts"
  markers = sorted(marker_dir.glob("*.json"))
  if not markers:
    raise RuntimeError("formal closure has no attempt markers")
  for marker in markers:
    record = validate_formal_attempt_marker(
        marker,
        root,
        Path(args.manifest).resolve(),
        args.sv_benchmarks,
        args.host,
        args.mode,
    )
    marker_records[record["label"]] = record
  expected_attempts = {}
  repetitions = []
  authenticated_plans = []
  for repetition, plan_value in enumerate(args.repetition_plan, start=1):
    plan_path = Path(plan_value).resolve()
    try:
      plan_path.relative_to(root)
    except ValueError as error:
      raise RuntimeError("formal closure repetition plan escapes output") from error
    if not plan_path.is_file() or plan_path.is_symlink():
      raise RuntimeError("formal closure repetition plan is not regular")
    if args.mode == "cap16":
      authenticated = load_screen_plan(
          plan_path,
          manifest,
          manifest_path,
          args.host,
          args.sv_benchmarks,
          args.benchmark_definition,
          plan_schema=CAP16_FORMAL_REPETITION_PLAN_SCHEMA,
          repetition=repetition,
          display=FORMAL_DISPLAY,
          time_limit="900 s",
          taint_schema=FORMAL_TAINT_SCHEMA,
          definition_validator=validate_formal_definition,
          hard_threshold=200,
      )
    else:
      authenticated = load_repetition_plan(
          plan_path,
          manifest,
          manifest_path,
          args.host,
          args.sv_benchmarks,
          args.benchmark_definition,
          200,
      )
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    authenticated_plans.append(authenticated)
    repetitions.append(plan["repetition"])
    primary_label = f"repetition-{plan['repetition']}"
    expected_attempts[primary_label] = {
        "repetition": plan["repetition"],
        "role": "primary",
        "result_sha256": plan["primary"]["sha256"],
        "definition_sha256": baseline.sha256_file(
            Path(args.benchmark_definition)
        ),
        "tasks": sorted(manifest),
    }
    for entry in plan["replacements"]:
      label = Path(entry["path"]).parent.name
      expected_attempts[label] = {
          "repetition": plan["repetition"],
          "role": "replacement",
          "result_sha256": entry["sha256"],
          "definition_sha256": entry["definition_sha256"],
          "tasks": entry.get("result_tasks", entry.get("tasks")),
      }
  if repetitions != [1, 2]:
    raise RuntimeError("formal closure plans must be ordered 1 then 2")
  if len({plan["plan_sha256"] for plan in authenticated_plans}) != 2:
    raise RuntimeError("formal closure repetition plans are not distinct")
  authenticated_results = [
      digest
      for plan in authenticated_plans
      for digest in [
          plan["primary_sha256"],
          *plan["replacement_sha256"],
      ]
  ]
  if len(authenticated_results) != len(set(authenticated_results)):
    raise RuntimeError("formal closure result artifacts are reused")
  if {marker.stem for marker in markers} != set(expected_attempts):
    raise RuntimeError(
        "formal attempt markers do not match exactly the planned attempts"
    )
  for label, expected in expected_attempts.items():
    record = marker_records[label]
    actual = {
        "repetition": record["repetition"],
        "role": record["role"],
        "result_sha256": record["files"]["result"]["sha256"],
        "definition_sha256": record["files"]["definition"]["sha256"],
        "tasks": record["result_tasks"],
    }
    if actual != expected:
      raise RuntimeError(
          f"formal attempt marker does not match its planned attempt: {label}"
      )
  return {
      "artifact_aggregate_sha256": json.loads(
          artifact.read_text(encoding="utf-8")
      )["aggregate_sha256"],
      "attempt_count": len(markers),
      "complete": args.require_complete,
      "valid": True,
  }


def command_validate_formal_closure(args):
  print(json.dumps(validate_formal_closure(args), sort_keys=True))


def validate_sha256_inventory(root, inventory_path, expected_paths=None):
  root = Path(root).resolve()
  inventory_path = Path(inventory_path).resolve()
  if (
      inventory_path.is_symlink()
      or not inventory_path.is_file()
      or inventory_path.parent != root
  ):
    raise RuntimeError("SHA-256 inventory is not a regular root file")
  entries = {}
  for line in inventory_path.read_text(encoding="utf-8").splitlines():
    match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
    if match is None:
      raise RuntimeError("SHA-256 inventory line is invalid")
    digest, relative_text = match.groups()
    relative = Path(relative_text)
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or relative.as_posix() in entries
    ):
      raise RuntimeError("SHA-256 inventory path is invalid")
    path = root / relative
    current = root
    symlink_ancestor = False
    for component in relative.parts[:-1]:
      current /= component
      if current.is_symlink():
        symlink_ancestor = True
        break
    if (
        symlink_ancestor
        or path.is_symlink()
        or not path.is_file()
        or baseline.sha256_file(path) != digest
    ):
      raise RuntimeError(f"SHA-256 inventory mismatch: {relative}")
    entries[relative.as_posix()] = digest
  if list(entries) != sorted(entries):
    raise RuntimeError("SHA-256 inventory paths are not sorted")
  if expected_paths is not None and set(entries) != set(expected_paths):
    raise RuntimeError("SHA-256 inventory topology is not exact")
  return entries


def cap8_formal_probe_paths(formal_output):
  root = Path(formal_output).resolve()
  evidence = root / "input/evidence"
  research = root / "input/research"
  return {
      "root": root,
      "manifest": (
          root / "input/formal/candidate-manifest-valkyrie-formal.json"
      ),
      "formal_package_artifact": root / "input/formal/artifact-manifest.json",
      "definition": root / "generated/hard-case-candidates.xml",
      "plan_1": root / "repetition-1-plan.json",
      "plan_2": root / "repetition-2-plan.json",
      "hard": root / "summary/hard-portfolio.csv",
      "classification": root / "summary/classification.csv",
      "summary": root / "summary/summary.json",
      "artifact": root / "provenance/artifact-manifest.json",
      "evidence": evidence,
      "research": research,
      "saved_dataset": research / "scripts/dataset.py",
      "research_head": research / "research-head.txt",
      "research_inventory": research / "inventory.sha256",
  }


def frozen_cap8_formal_artifact_aggregate():
  frozen = FROZEN_CAP8_FORMAL_ARTIFACT_AGGREGATE_SHA256
  if re.fullmatch(r"[0-9a-f]{64}", frozen) is None:
    raise RuntimeError("cap-8 r8 formal artifact aggregate pin is pending")
  return frozen


def cap8_phase_result(evidence, role):
  matches = [
      path for path in (
          evidence / f"{role}-result.xml",
          evidence / f"{role}-result.xml.bz2",
      )
      if path.is_file() and not path.is_symlink()
  ]
  if len(matches) != 1:
    raise RuntimeError(f"cap-8 r8 {role} Phase-A result is not unique")
  return matches[0]


def cap8_summary_reproduction_arguments(paths, sv_benchmarks, output_dir):
  evidence = paths["evidence"]
  arguments = [
      "summarize",
      "--parent-manifest", str(evidence / "parent-manifest.json"),
  ]
  for role in ("original", "reroute", "recovery"):
    arguments.extend([
        "--phase-a-manifest", str(evidence / f"{role}-manifest.json"),
    ])
  for role in ("original", "reroute", "recovery"):
    arguments.extend([
        "--phase-a-result", str(cap8_phase_result(evidence, role)),
    ])
  for role in ("original", "reroute", "recovery"):
    arguments.extend([
        "--survivor-manifest", str(evidence / f"{role}-survivor.json"),
    ])
  arguments.extend([
      "--sv-benchmarks", str(Path(sv_benchmarks).resolve()),
      "--manifest", str(paths["manifest"]),
      "--benchmark-definition", str(paths["definition"]),
      "--repetition-plan", str(paths["plan_1"]),
      "--repetition-plan", str(paths["plan_2"]),
      "--output-dir", str(Path(output_dir).resolve()),
      "--hard-threshold", "200",
  ])
  return arguments


def run_saved_dataset(script, arguments, python_bin=None):
  if python_bin is None:
    python_bin = sys.executable
  script = Path(script).resolve()
  for path in script.parent.rglob("*"):
    if (
        path.is_file()
        and path.suffix in {".pyc", ".pyo"}
        and "__pycache__" not in path.relative_to(script.parent).parts
    ):
      raise RuntimeError(
          f"sourceless Python bytecode could shadow pinned source: {path}"
      )
  command = [
      str(python_bin),
      *PYTHON_RUNTIME_FLAGS,
      "-c",
      (
          "import runpy,sys;"
          "from pathlib import Path;"
          "script=Path(sys.argv.pop(1)).resolve();"
          "sys.argv[0]=str(script);"
          "sys.path.insert(0,str(script.parent));"
          "runpy.run_path(str(script),run_name='__main__')"
      ),
      str(script),
      *arguments,
  ]
  subprocess.run(command, check=True)


def authenticate_cap8_formal_for_probe(formal_output, sv_benchmarks):
  frozen_aggregate = frozen_cap8_formal_artifact_aggregate()
  paths = cap8_formal_probe_paths(formal_output)
  declared = Path(formal_output)
  if (
      declared.is_symlink()
      or Path(os.path.abspath(declared)) != paths["root"]
      or not paths["root"].is_dir()
  ):
    raise RuntimeError("cap-8 r8 formal output must be a regular directory")
  package_artifact = validate_artifact_manifest(
      paths["manifest"].parent,
      paths["formal_package_artifact"],
      set(),
      expected_root=".",
  )
  if (
      baseline.sha256_file(paths["formal_package_artifact"])
      != FROZEN_CAP8_FORMAL_PACKAGE_MANIFEST_SHA256
      or package_artifact["aggregate_sha256"]
      != FROZEN_CAP8_FORMAL_PACKAGE_AGGREGATE_SHA256
      or baseline.sha256_file(paths["manifest"])
      != FROZEN_FORMAL_MANIFEST_SHA256
  ):
    raise RuntimeError("cap-8 r8 frozen formal input package is invalid")
  manifest = validate_manifest(paths["manifest"], sv_benchmarks)
  if (
      manifest["task_count"] != FROZEN_CAP8_FORMAL_TASK_COUNT
      or any(row["source"] != "sv-benchmarks" for row in manifest["tasks"])
  ):
    raise RuntimeError("cap-8 r8 formal manifest identity is invalid")

  evidence_paths = {
      "corpus/properties/unreach-call.prp",
      "parent-manifest.json",
      *(
          f"{role}-{kind}.{suffix}"
          for role in ("original", "reroute", "recovery")
          for kind, suffix in (
              ("manifest", "json"),
              ("survivor", "json"),
          )
      ),
  }
  for role in ("original", "reroute", "recovery"):
    evidence_paths.add(
        cap8_phase_result(paths["evidence"], role)
        .relative_to(paths["evidence"]).as_posix()
    )
  validate_sha256_inventory(
      paths["evidence"],
      paths["evidence"] / "inventory.sha256",
      evidence_paths,
  )

  research_paths = {
      "research-diff.patch",
      "research-head.txt",
      "research-index-flags.txt",
      "research-state.json",
      "research-status.porcelain",
      "scripts/baseline.py",
      "scripts/dataset.py",
      "scripts/run-stock-formal-dataset.sh",
  }
  if (
      paths["research_head"].read_text(encoding="utf-8")
      != f"{FROZEN_CAP8_RESEARCH_HEAD}\n"
      or baseline.sha256_file(paths["research_inventory"])
      != FROZEN_CAP8_RESEARCH_INVENTORY_SHA256
  ):
    raise RuntimeError("cap-8 r8 saved research identity is invalid")
  validate_sha256_inventory(
      paths["research"], paths["research_inventory"], research_paths
  )

  mandatory = (
      "provenance/build.log",
      "provenance/cgroup-check.log",
      "provenance/machine-preflight-start.json",
      "provenance/machine-preflight-end.json",
      "provenance/machine-preflight-check.json",
      "provenance/research-verification-final.log",
      "provenance/runtime-verification-final.log",
      "provenance/runtime-closure.txt",
  )
  for relative in mandatory:
    path = paths["root"] / relative
    if path.is_symlink() or not path.is_file():
      raise RuntimeError(
          f"cap-8 r8 formal closure lacks evidence: {relative}"
      )
  failure_evidence = [
      path for path in (paths["root"] / "provenance").iterdir()
      if "failure" in path.name
  ]
  if failure_evidence:
    raise RuntimeError("cap-8 r8 formal launcher did not close successfully")
  runtime_closure = {}
  for line in (
      paths["root"] / "provenance/runtime-closure.txt"
  ).read_text(encoding="utf-8").splitlines():
    if "=" not in line:
      raise RuntimeError("cap-8 r8 runtime closure line is invalid")
    key, value = line.split("=", 1)
    if key in runtime_closure:
      raise RuntimeError("cap-8 r8 runtime closure key is duplicated")
    runtime_closure[key] = value
  if runtime_closure != FROZEN_CAP8_RUNTIME_CLOSURE:
    raise RuntimeError("cap-8 r8 runtime closure is not the frozen runtime")
  expected_summary = {
      "classification.csv",
      "hard-portfolio.csv",
      "mixed.csv",
      "row-provenance.json",
      "summary.json",
      "verifier-failure-quarantine.csv",
      "wrong-quarantine.csv",
  }
  if (
      {
          path.name for path in (paths["root"] / "summary").iterdir()
      }
      != expected_summary
  ):
    raise RuntimeError("cap-8 r8 summary topology is not exact")
  for plan in (paths["plan_1"], paths["plan_2"]):
    if plan.is_symlink() or not plan.is_file():
      raise RuntimeError("cap-8 r8 repetition plan is not regular")

  with tempfile.TemporaryDirectory(
      prefix="vguide-cap8-r8-summary-check."
  ) as temporary:
    run_saved_dataset(
        paths["saved_dataset"],
        cap8_summary_reproduction_arguments(
            paths, sv_benchmarks, temporary
        ),
        python_bin="/usr/bin/python3.10",
    )
    reproduced = Path(temporary)
    if {path.name for path in reproduced.iterdir()} != expected_summary:
      raise RuntimeError("cap-8 r8 reproduced summary topology is not exact")
    for name in expected_summary:
      if (
          (reproduced / name).read_bytes()
          != (paths["root"] / "summary" / name).read_bytes()
      ):
        raise RuntimeError("cap-8 r8 summary does not reproduce byte-identically")

  artifact = validate_artifact_manifest(
      paths["root"], paths["artifact"], set()
  )
  if artifact["aggregate_sha256"] != frozen_aggregate:
    raise RuntimeError("cap-8 r8 formal artifact aggregate is not frozen")
  with paths["classification"].open(newline="", encoding="utf-8") as source:
    classification = list(csv.DictReader(source))
  with paths["hard"].open(newline="", encoding="utf-8") as source:
    hard = list(csv.DictReader(source))
  expected = [
      row for row in classification
      if row.get("classification")
      in {"stable_hard_solved", "stable_unsolved"}
  ]
  tasks = [row.get("task") for row in hard]
  details = {row["task"]: row for row in manifest["tasks"]}
  if (
      hard != expected
      or not hard
      or tasks != sorted(tasks)
      or len(tasks) != len(set(tasks))
      or any(task not in details for task in tasks)
  ):
    raise RuntimeError(
        "cap-8 r8 hard portfolio is not the exact authenticated stable-hard set"
    )
  return paths, manifest, hard, {
      "artifact_aggregate_sha256": artifact["aggregate_sha256"],
      "valid": True,
  }


def command_authenticate_cap8_formal_for_probe(args):
  _, manifest, hard, closure = authenticate_cap8_formal_for_probe(
      args.formal_output, args.sv_benchmarks
  )
  print(json.dumps({
      "artifact_aggregate_sha256": closure[
          "artifact_aggregate_sha256"
      ],
      "hard_task_count": len(hard),
      "manifest_task_count": manifest["task_count"],
      "valid": True,
  }, sort_keys=True))


def cap16_formal_probe_paths(formal_output):
  root = Path(formal_output).resolve()
  phase_a = root / "input/evidence"
  return {
      "root": root,
      "phase_a": phase_a,
      "saved_dataset": root / "input/research/scripts/dataset.py",
      "manifest": (
          root
          / "input/evidence/summary/candidate-manifest-analysis-survivors.json"
      ),
      "definition": root / "generated/hard-case-candidates.xml",
      "plan_1": root / "repetition-1-plan.json",
      "plan_2": root / "repetition-2-plan.json",
      "hard": root / "summary/hard-portfolio.csv",
      "classification": root / "summary/classification.csv",
      "summary": root / "summary/summary.json",
      "artifact": root / "provenance/artifact-manifest.json",
  }


def frozen_cap16_formal_artifact_aggregate():
  frozen = FROZEN_CAP16_FORMAL_ARTIFACT_AGGREGATE_SHA256
  if re.fullmatch(r"[0-9a-f]{64}", frozen) is None:
    raise RuntimeError(
        "cap-16 formal artifact aggregate pin is pending"
    )
  return frozen


def authenticate_cap16_formal_for_probe(formal_output, sv_benchmarks):
  frozen_aggregate = frozen_cap16_formal_artifact_aggregate()
  paths = cap16_formal_probe_paths(formal_output)
  declared = Path(formal_output)
  if (
      declared.is_symlink()
      or Path(os.path.abspath(declared)) != paths["root"]
      or not paths["root"].is_dir()
  ):
    raise RuntimeError("cap-16 formal output must be a regular directory")
  artifact = validate_artifact_manifest(
      paths["root"], paths["artifact"], {"summary/.complete"}
  )
  if artifact["aggregate_sha256"] != frozen_aggregate:
    raise RuntimeError("cap-16 formal artifact aggregate is not frozen")
  with tempfile.TemporaryDirectory(
      prefix="vguide-cap16-formal-summary-check."
  ) as temporary:
    run_saved_dataset(paths["saved_dataset"], [
        "summarize-cap16-formal",
        "--phase-a-output", str(paths["phase_a"]),
        "--sv-benchmarks", str(Path(sv_benchmarks).resolve()),
        "--manifest", str(paths["manifest"]),
        "--benchmark-definition", str(paths["definition"]),
        "--repetition-plan", str(paths["plan_1"]),
        "--repetition-plan", str(paths["plan_2"]),
        "--output-dir", str(Path(temporary).resolve()),
        "--hard-threshold", "200",
    ], python_bin="/usr/bin/python3.12")
    reproduced = Path(temporary)
    actual_summary = {
        path.name for path in (paths["root"] / "summary").iterdir()
        if path.name != ".complete"
    }
    if {path.name for path in reproduced.iterdir()} != actual_summary:
      raise RuntimeError("cap-16 formal summary topology does not reproduce")
    for candidate in reproduced.iterdir():
      if (
          candidate.read_bytes()
          != (paths["root"] / "summary" / candidate.name).read_bytes()
      ):
        raise RuntimeError("cap-16 formal summary does not reproduce exactly")
  closure = validate_formal_closure(
      argparse.Namespace(
          output_root=str(paths["root"]),
          manifest=str(paths["manifest"]),
          benchmark_definition=str(paths["definition"]),
          sv_benchmarks=str(Path(sv_benchmarks).resolve()),
          host="athena",
          mode="cap16",
          repetition_plan=[str(paths["plan_1"]), str(paths["plan_2"])],
          require_complete=True,
      )
  )
  if (
      closure["artifact_aggregate_sha256"]
      != frozen_aggregate
  ):
    raise RuntimeError("cap-16 formal artifact aggregate is not frozen")
  manifest = validate_manifest(paths["manifest"], sv_benchmarks)
  with paths["classification"].open(newline="", encoding="utf-8") as source:
    classification = list(csv.DictReader(source))
  with paths["hard"].open(newline="", encoding="utf-8") as source:
    hard = list(csv.DictReader(source))
  expected = [
      row
      for row in classification
      if row.get("classification")
      in {"stable_hard_solved", "stable_analysis_unsolved"}
  ]
  tasks = [row.get("task") for row in hard]
  details = {row["task"]: row for row in manifest["tasks"]}
  if (
      hard != expected
      or not hard
      or tasks != sorted(tasks)
      or len(tasks) != len(set(tasks))
      or any(task not in details for task in tasks)
      or any(details[task]["source"] != "sv-benchmarks" for task in tasks)
  ):
    raise RuntimeError(
        "cap-16 formal hard portfolio is not the exact authenticated stable-hard set"
    )
  return paths, manifest, hard, closure


def command_authenticate_cap16_formal_for_probe(args):
  _, manifest, hard, closure = authenticate_cap16_formal_for_probe(
      args.formal_output, args.sv_benchmarks
  )
  print(json.dumps({
      "artifact_aggregate_sha256": closure[
          "artifact_aggregate_sha256"
      ],
      "hard_task_count": len(hard),
      "manifest_task_count": manifest["task_count"],
      "valid": True,
  }, sort_keys=True))


def package_strict_probe_input(args, cohort):
  profile = strict_probe_profile(cohort)
  authenticate = (
      authenticate_cap8_formal_for_probe
      if cohort == "cap8"
      else authenticate_cap16_formal_for_probe
  )
  paths, manifest, hard, closure = authenticate(
      args.formal_output, args.sv_benchmarks
  )
  output = Path(args.output_dir).resolve()
  require_absent_or_empty_output(output)
  output.mkdir(parents=True, exist_ok=True)
  tasks = [row["task"] for row in hard]
  source_manifest_sha256 = baseline.sha256_file(paths["manifest"])
  hard_sha256 = baseline.sha256_file(paths["hard"])
  derived = manifest_subset(
      manifest,
      tasks,
      {
          "operation": profile["operation"],
          "source_manifest_sha256": source_manifest_sha256,
          "source_formal_manifest_sha256": source_manifest_sha256,
          "source_formal_hard_portfolio_sha256": hard_sha256,
          "source_formal_artifact_aggregate_sha256": closure[
              "artifact_aggregate_sha256"
          ],
          "selection_independent_of_augmented_outcomes": True,
      },
  )
  if (paths["manifest"].parent / "corpus").is_dir():
    shutil.copytree(paths["manifest"].parent / "corpus", output / "corpus")
  manifest_path = output / profile["manifest_name"]
  manifest_path.write_text(
      json.dumps(derived, indent=2) + "\n", encoding="utf-8"
  )
  shutil.copyfile(paths["hard"], output / "hard-portfolio.csv")
  for source, target in (
      (paths["manifest"], "source-formal-manifest.json"),
      (paths["classification"], "source-formal-classification.csv"),
      (paths["summary"], "source-formal-summary.json"),
      (paths["artifact"], "source-formal-artifact-manifest.json"),
  ):
    shutil.copyfile(source, output / target)
  identity = {
      "schema_version": profile["input_schema"],
      "host": profile["host"],
      "task_count": len(tasks),
      "formal_artifact_aggregate_sha256": closure[
          "artifact_aggregate_sha256"
      ],
      "formal_artifact_manifest_sha256": baseline.sha256_file(
          paths["artifact"]
      ),
      "formal_manifest_sha256": source_manifest_sha256,
      "formal_hard_portfolio_sha256": hard_sha256,
      "formal_classification_sha256": baseline.sha256_file(
          paths["classification"]
      ),
      "formal_summary_sha256": baseline.sha256_file(paths["summary"]),
      "probe_manifest_sha256": baseline.sha256_file(manifest_path),
      "selection_independent_of_augmented_outcomes": True,
  }
  (output / "identity.json").write_text(
      json.dumps(identity, indent=2) + "\n", encoding="utf-8"
  )
  validate_strict_probe_input(output, args.sv_benchmarks, cohort)
  print(json.dumps(identity, sort_keys=True))


def command_package_cap8_probe_input(args):
  package_strict_probe_input(args, "cap8")


def command_package_cap16_probe_input(args):
  package_strict_probe_input(args, "cap16")


def validate_strict_probe_input(probe_input, sv_benchmarks, cohort):
  profile = strict_probe_profile(cohort)
  root = Path(probe_input).resolve()
  identity_path = root / "identity.json"
  manifest_path = root / profile["manifest_name"]
  hard_path = root / "hard-portfolio.csv"
  identity = json.loads(identity_path.read_text(encoding="utf-8"))
  if (
      not isinstance(identity, dict)
      or set(identity)
      != {
          "schema_version",
          "host",
          "task_count",
          "formal_artifact_aggregate_sha256",
          "formal_artifact_manifest_sha256",
          "formal_manifest_sha256",
          "formal_hard_portfolio_sha256",
          "formal_classification_sha256",
          "formal_summary_sha256",
          "probe_manifest_sha256",
          "selection_independent_of_augmented_outcomes",
      }
      or identity["schema_version"] != profile["input_schema"]
      or identity["host"] != profile["host"]
      or identity["selection_independent_of_augmented_outcomes"] is not True
      or any(
          re.fullmatch(r"[0-9a-f]{64}", identity[name]) is None
          for name in identity
          if name.startswith("formal_") or name == "probe_manifest_sha256"
      )
      or identity["probe_manifest_sha256"]
      != baseline.sha256_file(manifest_path)
  ):
    raise RuntimeError(f"{cohort} probe input identity is invalid")
  manifest = validate_manifest(manifest_path, sv_benchmarks)
  source_manifest_path = root / "source-formal-manifest.json"
  source_classification_path = root / "source-formal-classification.csv"
  source_summary_path = root / "source-formal-summary.json"
  source_artifact_path = root / "source-formal-artifact-manifest.json"
  source_manifest = validate_manifest(
      source_manifest_path, sv_benchmarks
  )
  artifact = json.loads(
      source_artifact_path.read_text(encoding="utf-8")
  )
  artifact_index = validate_artifact_manifest_index(artifact)
  if not Path(artifact["root"]).is_absolute():
    raise RuntimeError(f"{cohort} probe formal artifact root is not absolute")
  formal_paths = (
      cap8_formal_probe_paths(Path(artifact["root"]))
      if cohort == "cap8"
      else cap16_formal_probe_paths(Path(artifact["root"]))
  )
  expected_artifacts = {
      formal_paths["manifest"].relative_to(formal_paths["root"]).as_posix():
          identity["formal_manifest_sha256"],
      formal_paths["classification"].relative_to(
          formal_paths["root"]
      ).as_posix(): identity["formal_classification_sha256"],
      formal_paths["hard"].relative_to(formal_paths["root"]).as_posix():
          identity["formal_hard_portfolio_sha256"],
      formal_paths["summary"].relative_to(formal_paths["root"]).as_posix():
          identity["formal_summary_sha256"],
  }
  if (
      identity["formal_artifact_manifest_sha256"]
      != baseline.sha256_file(source_artifact_path)
      or identity["formal_manifest_sha256"]
      != (
          FROZEN_FORMAL_MANIFEST_SHA256
          if cohort == "cap8"
          else FROZEN_CAP16_PHASE_A_SURVIVOR_SHA256
      )
      or identity["formal_artifact_aggregate_sha256"]
      != artifact["aggregate_sha256"]
      or identity["formal_artifact_aggregate_sha256"]
      != (
          frozen_cap8_formal_artifact_aggregate()
          if cohort == "cap8"
          else frozen_cap16_formal_artifact_aggregate()
      )
      or any(
          relative not in artifact_index
          or artifact_index[relative]["sha256"] != digest
          for relative, digest in expected_artifacts.items()
      )
      or identity["formal_manifest_sha256"]
      != baseline.sha256_file(source_manifest_path)
      or identity["formal_classification_sha256"]
      != baseline.sha256_file(source_classification_path)
      or identity["formal_summary_sha256"]
      != baseline.sha256_file(source_summary_path)
  ):
    raise RuntimeError(f"{cohort} probe formal-closure backlink is invalid")
  with hard_path.open(newline="", encoding="utf-8") as source:
    hard = list(csv.DictReader(source))
  with source_classification_path.open(
      newline="", encoding="utf-8"
  ) as source:
    classification = list(csv.DictReader(source))
  tasks = [row.get("task") for row in hard]
  task_basenames = [
      Path(row["task_path"]).name for row in manifest["tasks"]
  ]
  source_by_task = {
      row["task"]: row for row in source_manifest["tasks"]
  }
  if (
      not hard
      or tasks != sorted(tasks)
      or len(tasks) != len(set(tasks))
      or tasks != sorted(row["task"] for row in manifest["tasks"])
      or len(task_basenames) != len(set(task_basenames))
      or identity["task_count"] != len(tasks)
      or identity["formal_hard_portfolio_sha256"]
      != baseline.sha256_file(hard_path)
      or hard
      != [
          row for row in classification
          if row.get("classification")
          in profile["accepted_labels"]
      ]
      or manifest["derivation"] != {
          "operation": profile["operation"],
          "source_manifest_sha256": identity["formal_manifest_sha256"],
          "source_formal_manifest_sha256":
              identity["formal_manifest_sha256"],
          "source_formal_hard_portfolio_sha256":
              identity["formal_hard_portfolio_sha256"],
          "source_formal_artifact_aggregate_sha256":
              identity["formal_artifact_aggregate_sha256"],
          "selection_independent_of_augmented_outcomes": True,
      }
      or any(
          source_by_task.get(row["task"]) != row
          for row in manifest["tasks"]
      )
  ):
    raise RuntimeError(f"{cohort} probe input hard portfolio is invalid")
  return root, manifest_path, manifest, hard, identity


def validate_cap8_probe_input(probe_input, sv_benchmarks):
  return validate_strict_probe_input(probe_input, sv_benchmarks, "cap8")


def validate_cap16_probe_input(probe_input, sv_benchmarks):
  return validate_strict_probe_input(probe_input, sv_benchmarks, "cap16")


def command_validate_cap8_probe_input(args):
  _, _, manifest, _, identity = validate_cap8_probe_input(
      args.probe_input, args.sv_benchmarks
  )
  print(json.dumps({
      "task_count": manifest["task_count"],
      "formal_artifact_aggregate_sha256": identity[
          "formal_artifact_aggregate_sha256"
      ],
      "valid": True,
  }, sort_keys=True))


def command_validate_cap16_probe_input(args):
  _, _, manifest, _, identity = validate_cap16_probe_input(
      args.probe_input, args.sv_benchmarks
  )
  print(json.dumps({
      "task_count": manifest["task_count"],
      "formal_artifact_aggregate_sha256": identity[
          "formal_artifact_aggregate_sha256"
      ],
      "valid": True,
  }, sort_keys=True))


def validate_strict_probe_closure(args, cohort):
  profile = strict_probe_profile(cohort)
  root = Path(args.output_root).resolve()
  probe_input = root / "input/formal"
  _, manifest_path, _, _, _ = validate_strict_probe_input(
      probe_input, args.sv_benchmarks, cohort
  )
  complete = root / "summary/.complete"
  if args.require_complete:
    if (
        complete.is_symlink()
        or not complete.is_file()
        or complete.read_text(encoding="utf-8") != "complete\n"
    ):
      raise RuntimeError("probe completion sentinel is invalid")
  elif complete.exists() or complete.is_symlink():
    raise RuntimeError("probe output completed before closure validation")
  expected_summary = {
      "cegar-eligibility.csv",
      "row-provenance.json",
      "summary.json",
      *(filename for filename, _ in STRICT_PROBE_STRATA),
  }
  actual_summary = {
      path.name
      for path in (root / "summary").iterdir()
      if path.name != ".complete"
  }
  if actual_summary != expected_summary:
    raise RuntimeError("probe summary topology is incomplete")
  summary_args = argparse.Namespace(
      probe_input=str(probe_input),
      sv_benchmarks=args.sv_benchmarks,
      benchmark_definition=str(root / "generated/cegar-eligibility.xml"),
      probe_plan=str(root / "probe-plan.json"),
      output_dir=None,
  )
  with tempfile.TemporaryDirectory(
      prefix=f"vguide-{cohort}-probe-summary-check."
  ) as temp:
    summary_args.output_dir = temp
    write_strict_probe_summary(summary_args, cohort)
    for candidate in Path(temp).iterdir():
      expected = root / "summary" / candidate.name
      if (
          not expected.is_file()
          or expected.is_symlink()
          or candidate.read_bytes() != expected.read_bytes()
      ):
        raise RuntimeError("probe summary does not reproduce exactly")
  artifact = root / "provenance/artifact-manifest.json"
  validate_artifact_manifest(root, artifact, {"summary/.complete"})
  mandatory = (
      "input/research/inventory.sha256",
      "provenance/build.log",
      "provenance/cgroup-check.log",
      "provenance/machine-preflight-start.json",
      "provenance/machine-preflight-end.json",
      "provenance/machine-preflight-check.json",
      "provenance/research-verification-final.log",
      "provenance/runtime-verification-final.log",
      "provenance/runtime-closure.txt",
  )
  for relative in mandatory:
    path = root / relative
    if not path.is_file() or path.is_symlink():
      raise RuntimeError(f"probe closure lacks mandatory evidence: {relative}")
  manifest = baseline.load_task_manifest(manifest_path)
  plan_path = root / "probe-plan.json"
  plan = json.loads(plan_path.read_text(encoding="utf-8"))
  authenticated = load_screen_plan(
      plan_path,
      manifest,
      manifest_path,
      profile["host"],
      args.sv_benchmarks,
      root / "generated/cegar-eligibility.xml",
      plan_schema=profile["plan_schema"],
      repetition=1,
      display=PROBE_DISPLAY,
      time_limit="900 s",
      taint_schema=profile["taint_schema"],
      definition_validator=validate_probe_definition,
      hard_threshold=200,
  )
  markers = sorted((root / "provenance/attempts").glob("*.json"))
  records = {
      marker.stem: validate_formal_attempt_marker(
          marker,
          root,
          manifest_path,
          args.sv_benchmarks,
          profile["host"],
          f"{cohort}-probe",
      )
      for marker in markers
  }
  expected_attempts = {
      "repetition-1": {
          "role": "primary",
          "result_sha256": plan["primary"]["sha256"],
          "definition_sha256": baseline.sha256_file(
              root / "generated/cegar-eligibility.xml"
          ),
          "tasks": sorted(manifest),
      }
  }
  for entry in plan["replacements"]:
    expected_attempts[Path(entry["path"]).parent.name] = {
        "role": "replacement",
        "result_sha256": entry["sha256"],
        "definition_sha256": entry["definition_sha256"],
        "tasks": entry["result_tasks"],
    }
  if set(records) != set(expected_attempts):
    raise RuntimeError("probe attempt markers do not exactly match the plan")
  for label, expected in expected_attempts.items():
    record = records[label]
    actual = {
        "role": record["role"],
        "result_sha256": record["files"]["result"]["sha256"],
        "definition_sha256": record["files"]["definition"]["sha256"],
        "tasks": record["result_tasks"],
    }
    if actual != expected or record["repetition"] != 1:
      raise RuntimeError(f"probe attempt marker does not match plan: {label}")
  return {
      "artifact_aggregate_sha256": json.loads(
          artifact.read_text(encoding="utf-8")
      )["aggregate_sha256"],
      "attempt_count": len(records),
      "result_count": 1 + len(authenticated["replacement_sha256"]),
      "complete": args.require_complete,
      "valid": True,
  }


def validate_cap8_probe_closure(args):
  return validate_strict_probe_closure(args, "cap8")


def validate_cap16_probe_closure(args):
  return validate_strict_probe_closure(args, "cap16")


def command_validate_cap8_probe_closure(args):
  print(json.dumps(validate_cap8_probe_closure(args), sort_keys=True))


def command_validate_cap16_probe_closure(args):
  print(json.dumps(validate_cap16_probe_closure(args), sort_keys=True))


def command_write_complete_sentinel(args):
  output = Path(args.output)
  if output.exists() or output.is_symlink():
    raise RuntimeError("formal completion sentinel already exists")
  output.parent.mkdir(parents=True, exist_ok=True)
  temporary = output.with_name(f".{output.name}.tmp-{os.getpid()}")
  descriptor = os.open(
      temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644
  )
  try:
    os.write(descriptor, b"complete\n")
    os.fsync(descriptor)
  finally:
    os.close(descriptor)
  os.replace(temporary, output)
  directory = os.open(output.parent, os.O_RDONLY)
  try:
    os.fsync(directory)
  finally:
    os.close(directory)


def load_formal_contention_intervals(path):
  lines = Path(path).read_text(encoding="utf-8").splitlines()
  if len(lines) < 2:
    raise RuntimeError("formal load monitor has no samples")
  header = json.loads(lines[0])
  if not isinstance(header, dict) or header != {
      "schema_version": FORMAL_LOAD_MONITOR_SCHEMA,
      "p_core_cpus": list(FORMAL_P_CORE_CPUS),
      "foreign_process_cpu_percent": FORMAL_FOREIGN_CPU_PERCENT,
      "minimum_consecutive_seconds": FORMAL_FOREIGN_CPU_SECONDS,
      "sample_interval_seconds": FORMAL_LOAD_SAMPLE_SECONDS,
      "excluded_process_root": (
          header.get("excluded_process_root")
          if isinstance(header, dict)
          else None
      ),
  } or not isinstance(header.get("excluded_process_root"), int):
    raise RuntimeError("formal load-monitor policy does not match")
  intervals = []
  previous = None
  for line in lines[1:]:
    sample = json.loads(line)
    if (
        not isinstance(sample, dict)
        or set(sample) != {"timestamp", "elapsed_seconds", "offenders"}
        or not isinstance(sample["elapsed_seconds"], (int, float))
        or sample["elapsed_seconds"] <= 0
    ):
      raise RuntimeError("formal load-monitor sample topology is not exact")
    timestamp = datetime.datetime.fromisoformat(sample["timestamp"])
    if timestamp.tzinfo is None or (previous is not None and timestamp <= previous):
      raise RuntimeError("formal load-monitor timestamps are invalid")
    previous = timestamp
    if not isinstance(sample["offenders"], list):
      raise RuntimeError("formal load-monitor offenders are invalid")
    for offender in sample["offenders"]:
      if (
          set(offender) != {
              "pid",
              "uid",
              "comm",
              "cpu_percent",
              "duration_seconds",
              "since",
              "contended",
          }
          or not isinstance(offender["pid"], int)
          or not isinstance(offender["uid"], int)
          or not isinstance(offender["comm"], str)
          or not isinstance(offender["cpu_percent"], (int, float))
          or not isinstance(offender["duration_seconds"], (int, float))
          or not isinstance(offender["contended"], bool)
      ):
        raise RuntimeError("formal load-monitor offender topology is not exact")
      since = datetime.datetime.fromisoformat(offender["since"])
      expected = offender["duration_seconds"] >= FORMAL_FOREIGN_CPU_SECONDS
      if (
          since.tzinfo is None
          or since > timestamp
          or offender["cpu_percent"] < FORMAL_FOREIGN_CPU_PERCENT
          or offender["contended"] != expected
      ):
        raise RuntimeError("formal load-monitor offender is inconsistent")
      if offender["contended"]:
        intervals.append((since, timestamp))
  return intervals, previous


def match_benchexec_log_task(name, manifest):
  try:
    return baseline.match_result_task(name, manifest)
  except RuntimeError:
    return baseline.match_result_task(f"c/{name}", manifest)


def run_taints(
    result,
    log,
    load_monitor,
    manifest,
    display=FORMAL_DISPLAY,
    time_limit="900 s",
):
  result = Path(result).resolve()
  metadata = (
      probe_result_metadata(result, allow_incomplete=True)
      if display == PROBE_DISPLAY
      else result_metadata(
          result, display, time_limit, allow_incomplete=True
      )
  )
  result_tasks = result_task_names(result, manifest)
  subset = {task: manifest[task] for task in result_tasks}
  rows = {
      row["task"]: row
      for row in baseline.parse_result_rows(result, subset, 200)
  }
  intervals, monitor_end = load_formal_contention_intervals(load_monitor)
  start_date = datetime.datetime.fromisoformat(metadata["starttime"])
  day = start_date.date()
  previous_clock = start_date.timetz().replace(tzinfo=None)
  starts = {}
  ends = {}
  pattern = re.compile(
      r"^(\d{2}:\d{2}:\d{2})\s+(?:(starting)\s+)?(\S+\.yml)(?:\s+.*)?$"
  )
  for line in Path(log).read_text(encoding="utf-8").splitlines():
    match = pattern.match(line)
    if not match:
      continue
    clock = datetime.time.fromisoformat(match.group(1))
    if (
        clock < previous_clock
        and (
            datetime.datetime.combine(day, previous_clock)
            - datetime.datetime.combine(day, clock)
        ).total_seconds()
        > 12 * 60 * 60
    ):
      day += datetime.timedelta(days=1)
    previous_clock = clock
    timestamp = datetime.datetime.combine(day, clock, start_date.tzinfo)
    task = match_benchexec_log_task(match.group(3), subset)
    target = starts if match.group(2) else ends
    if task in target:
      raise RuntimeError(f"duplicate BenchExec log event for {task}")
    target[task] = timestamp
  if set(ends) - set(starts):
    raise RuntimeError("BenchExec log completes a task that it never started")
  if monitor_end is None or any(
      ended > monitor_end for ended in ends.values()
  ):
    raise RuntimeError(
        "load monitor ended before a completed task was fully observed"
    )
  complete = {task for task, row in rows.items() if row_is_complete(row)}
  if complete != set(ends):
    raise RuntimeError("BenchExec log and complete result rows do not match")
  tainted = {
      task: "interrupted_incomplete"
      for task, row in rows.items()
      if not row_is_complete(row)
  }
  for task, started in starts.items():
    ended = ends.get(task, monitor_end)
    if ended is None:
      raise RuntimeError("load monitor ended before an active task could be bounded")
    ended += datetime.timedelta(seconds=1)
    if any(started <= stop and ended >= begin for begin, stop in intervals):
      tainted.setdefault(task, "foreign_p_core_contention")
  return tainted


def command_formal_taint(args):
  output = Path(args.output).resolve()
  if output.exists():
    raise RuntimeError(f"formal taint output already exists: {output}")
  manifest = baseline.load_task_manifest(args.manifest)
  primary_hash = baseline.sha256_file(Path(args.result))
  tainted = run_taints(
      args.result,
      args.benchexec_log,
      args.load_monitor,
      manifest,
  )
  output.parent.mkdir(parents=True, exist_ok=True)
  output.write_text(json.dumps({
      "schema_version": FORMAL_TAINT_SCHEMA,
      "repetition": args.repetition,
      "primary_result_sha256": primary_hash,
      "tasks": [
          {"task": task, "reason": tainted[task]}
          for task in sorted(tainted)
      ],
  }, indent=2) + "\n", encoding="utf-8")
  print(output)


def command_screen_taint(args):
  output = Path(args.output).resolve()
  if output.exists():
    raise RuntimeError(f"screen taint output already exists: {output}")
  manifest = baseline.load_task_manifest(args.manifest)
  primary_hash = baseline.sha256_file(Path(args.result))
  tainted = run_taints(
      args.result,
      args.benchexec_log,
      args.load_monitor,
      manifest,
      DISCOVERY_DISPLAY,
      "120 s",
  )
  output.parent.mkdir(parents=True, exist_ok=True)
  output.write_text(json.dumps({
      "schema_version": SCREEN_TAINT_SCHEMA,
      "repetition": 1,
      "primary_result_sha256": primary_hash,
      "tasks": [
          {"task": task, "reason": tainted[task]}
          for task in sorted(tainted)
      ],
  }, indent=2) + "\n", encoding="utf-8")
  print(output)


def write_probe_taint(args, cohort):
  profile = strict_probe_profile(cohort)
  output = Path(args.output).resolve()
  if output.exists():
    raise RuntimeError(f"probe taint output already exists: {output}")
  manifest = baseline.load_task_manifest(args.manifest)
  primary_hash = baseline.sha256_file(Path(args.result))
  tainted = run_taints(
      args.result,
      args.benchexec_log,
      args.load_monitor,
      manifest,
      PROBE_DISPLAY,
      "900 s",
  )
  output.parent.mkdir(parents=True, exist_ok=True)
  output.write_text(json.dumps({
      "schema_version": profile["taint_schema"],
      "repetition": 1,
      "primary_result_sha256": primary_hash,
      "tasks": [
          {"task": task, "reason": tainted[task]}
          for task in sorted(tainted)
      ],
  }, indent=2) + "\n", encoding="utf-8")
  print(output)


def command_cap8_probe_taint(args):
  write_probe_taint(args, "cap8")


def command_probe_taint(args):
  write_probe_taint(args, "cap16")


def row_is_complete(row):
  return (
      bool(row["status"])
      and bool(row["category"])
      and row["cpu_time_seconds"] is not None
      and row["wall_time_seconds"] is not None
  )


def load_repetition_plan(
    path,
    manifest,
    manifest_path,
    host,
    sv_benchmarks,
    benchmark_definition,
    hard_threshold,
    plan_schema=FORMAL_REPETITION_PLAN_SCHEMA,
    taint_schema=FORMAL_TAINT_SCHEMA,
    display=FORMAL_DISPLAY,
    time_limit="900 s",
    definition_validator=validate_formal_definition,
):
  declared_path = Path(path)
  path = declared_path.resolve()
  if (
      declared_path.is_symlink()
      or Path(os.path.abspath(declared_path)) != path
      or not path.is_file()
  ):
    raise RuntimeError("repetition plan must be a regular non-symlink file")
  plan = json.loads(path.read_text(encoding="utf-8"))
  if not isinstance(plan, dict) or set(plan) != {
      "schema_version",
      "repetition",
      "primary",
      "taint",
      "replacements",
  }:
    raise RuntimeError("formal repetition-plan topology is not exact")
  if (
      plan["schema_version"] != plan_schema
      or not isinstance(plan["repetition"], int)
      or plan["repetition"] not in {1, 2}
      or not isinstance(plan["replacements"], list)
  ):
    raise RuntimeError("formal repetition-plan identity is invalid")
  root = path.parent
  primary = declared_plan_file(root, plan["primary"], "primary result")
  primary_hash = plan["primary"]["sha256"]
  primary_metadata = (
      probe_result_metadata(primary, allow_incomplete=True)
      if display == PROBE_DISPLAY
      else result_metadata(
          primary, display, time_limit, allow_incomplete=True
      )
  )
  if primary_metadata["host"] != host:
    raise RuntimeError("formal primary result must run on the merged manifest host")
  validate_result_run_topology(
      primary,
      manifest,
      sv_benchmarks,
      benchmark_definition,
  )
  primary_rows = {
      row["task"]: row
      for row in baseline.parse_result_rows(
          primary, manifest, hard_threshold
      )
  }

  taint_entry = plan["taint"]
  if taint_entry is None:
    tainted = {}
    taint_hash = None
  else:
    taint_path = declared_plan_file(root, taint_entry, "taint manifest")
    taint_hash = taint_entry["sha256"]
    tainted = validate_taint_manifest(
        json.loads(taint_path.read_text(encoding="utf-8")),
        plan["repetition"],
        primary_hash,
        manifest,
        taint_schema,
    )
  missing = {
      task for task, row in primary_rows.items() if not row_is_complete(row)
  }
  if missing - set(tainted):
    raise RuntimeError(
        f"incomplete primary rows are not tainted: {sorted(missing - set(tainted))}"
    )

  accepted = dict(primary_rows)
  row_sources = {
      task: {
          "task": task,
          "source": "primary",
          "result_path": plan["primary"]["path"],
          "result_sha256": primary_hash,
      }
      for task in manifest
  }
  replacement_tasks = set()
  replacement_hashes = []
  replacement_metadata = []
  previous_path = ""
  for entry in plan["replacements"]:
    if (
        not isinstance(entry, dict)
        or set(entry) != {
            "path",
            "sha256",
            "definition_path",
            "definition_sha256",
            "tasks",
        }
        or not isinstance(entry["path"], str)
        or not isinstance(entry["sha256"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
        or not isinstance(entry["definition_path"], str)
        or not isinstance(entry["definition_sha256"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", entry["definition_sha256"])
        or not isinstance(entry["tasks"], list)
        or not entry["tasks"]
        or any(not isinstance(task, str) for task in entry["tasks"])
        or entry["tasks"] != sorted(entry["tasks"])
        or len(entry["tasks"]) != len(set(entry["tasks"]))
        or entry["path"] <= previous_path
    ):
      raise RuntimeError("formal replacement entry is invalid or not sorted")
    previous_path = entry["path"]
    tasks = set(entry["tasks"])
    if not tasks <= set(tainted) or tasks & replacement_tasks:
      raise RuntimeError("formal replacement tasks are untainted or duplicated")
    replacement = declared_plan_file(root, {
        "path": entry["path"],
        "sha256": entry["sha256"],
    }, "replacement result")
    if sorted(result_task_names(replacement, manifest)) != entry["tasks"]:
      raise RuntimeError("replacement result tasks do not match its plan entry")
    subset = {task: manifest[task] for task in entry["tasks"]}
    definition = declared_plan_file(
        root,
        {
            "path": entry["definition_path"],
            "sha256": entry["definition_sha256"],
        },
        "replacement definition",
    )
    full_manifest = {
        "task_count": len(entry["tasks"]),
        "tasks": [manifest[task] for task in entry["tasks"]],
    }
    definition_validator(
        definition,
        manifest_path,
        full_manifest,
        sv_benchmarks,
    )
    metadata = result_metadata(replacement, display, time_limit)
    if metadata["host"] != host:
      raise RuntimeError("formal replacement must run on the merged manifest host")
    validate_result_run_topology(
        replacement,
        subset,
        sv_benchmarks,
        definition,
    )
    rows = baseline.parse_result_rows(replacement, subset, hard_threshold)
    if any(not row_is_complete(row) for row in rows):
      raise RuntimeError("formal replacement result has incomplete rows")
    for row in rows:
      accepted[row["task"]] = row
      row_sources[row["task"]] = {
          "task": row["task"],
          "source": "replacement",
          "result_path": entry["path"],
          "result_sha256": entry["sha256"],
          "definition_path": entry["definition_path"],
          "definition_sha256": entry["definition_sha256"],
          "reason": tainted[row["task"]],
      }
    replacement_tasks.update(tasks)
    replacement_hashes.append(entry["sha256"])
    replacement_metadata.append(metadata)
  if replacement_tasks != set(tainted):
    raise RuntimeError(
        "formal replacements do not cover exactly the tainted task set"
    )
  if any(
      not row_is_complete(row)
      for task, row in accepted.items()
      if task not in replacement_tasks
  ):
    raise RuntimeError("accepted primary rows are incomplete")
  result_hashes = [primary_hash, *replacement_hashes]
  if len(result_hashes) != len(set(result_hashes)):
    raise RuntimeError("formal primary and replacement result hashes must be distinct")
  all_metadata = [primary_metadata, *replacement_metadata]
  for field in ("starttime", "benchmarkname"):
    if len({result[field] for result in all_metadata}) != len(all_metadata):
      raise RuntimeError(
          f"formal primary and replacements must have distinct {field} values"
      )
  return {
      "repetition": plan["repetition"],
      "plan_sha256": baseline.sha256_file(path),
      "primary_sha256": primary_hash,
      "taint_sha256": taint_hash,
      "replacement_sha256": replacement_hashes,
      "metadata": primary_metadata,
      "replacement_metadata": replacement_metadata,
      "rows": accepted,
      "row_sources": [row_sources[task] for task in sorted(row_sources)],
  }


def write_repetition_plan(
    args,
    plan_schema=FORMAL_REPETITION_PLAN_SCHEMA,
    taint_schema=FORMAL_TAINT_SCHEMA,
):
  output = Path(args.output).resolve()
  if output.exists():
    raise RuntimeError(f"repetition plan output already exists: {output}")
  output.parent.mkdir(parents=True, exist_ok=True)
  manifest = baseline.load_task_manifest(args.manifest)
  primary = plan_file_entry(args.primary_result, output.parent)
  if args.taint_manifest:
    taint = plan_file_entry(args.taint_manifest, output.parent)
    tainted = validate_taint_manifest(
        json.loads(
            (output.parent / taint["path"]).read_text(encoding="utf-8")
        ),
        args.repetition,
        primary["sha256"],
        manifest,
        taint_schema,
    )
  else:
    taint = None
    tainted = {}
  replacements = []
  covered = set()
  replacement_results = args.replacement_result or []
  replacement_definitions = args.replacement_definition or []
  if len(replacement_results) != len(replacement_definitions):
    raise RuntimeError(
        "replacement results and definitions must have the same count"
    )
  for replacement_path, definition_path in zip(
      replacement_results, replacement_definitions, strict=True
  ):
    entry = plan_file_entry(replacement_path, output.parent)
    definition = plan_file_entry(definition_path, output.parent)
    tasks = sorted(result_task_names(replacement_path, manifest))
    if not tasks or set(tasks) & covered:
      raise RuntimeError("replacement result tasks must be nonempty and disjoint")
    covered.update(tasks)
    replacements.append(
        {
            **entry,
            "definition_path": definition["path"],
            "definition_sha256": definition["sha256"],
            "tasks": tasks,
        }
    )
  replacements.sort(key=lambda entry: entry["path"])
  if covered != set(tainted):
    raise RuntimeError("replacement results do not cover exactly the taint manifest")
  plan = {
      "schema_version": plan_schema,
      "repetition": args.repetition,
      "primary": primary,
      "taint": taint,
      "replacements": replacements,
  }
  output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
  print(output)


def command_repetition_plan(args):
  write_repetition_plan(args)


def write_iterative_repetition_plan(args, plan_schema, taint_schema):
  output = Path(args.output).resolve()
  if output.exists():
    raise RuntimeError(f"screen plan output already exists: {output}")
  output.parent.mkdir(parents=True, exist_ok=True)
  manifest = baseline.load_task_manifest(args.manifest)
  primary = plan_file_entry(args.primary_result, output.parent)
  if args.taint_manifest:
    taint = plan_file_entry(args.taint_manifest, output.parent)
    remaining = validate_taint_manifest(
        json.loads(
            (output.parent / taint["path"]).read_text(encoding="utf-8")
        ),
        args.repetition,
        primary["sha256"],
        manifest,
        taint_schema,
    )
  else:
    taint = None
    remaining = {}
  results = args.replacement_result or []
  definitions = args.replacement_definition or []
  taints = args.replacement_taint_manifest or []
  if len({len(results), len(definitions), len(taints)}) != 1:
    raise RuntimeError(
        "screen replacement results, definitions, and taints must align"
    )
  replacements = []
  for result_path, definition_path, taint_path in zip(
      results, definitions, taints, strict=True
  ):
    result = plan_file_entry(result_path, output.parent)
    definition = plan_file_entry(definition_path, output.parent)
    replacement_taint = plan_file_entry(taint_path, output.parent)
    result_tasks = sorted(result_task_names(result_path, manifest))
    if set(result_tasks) != set(remaining):
      raise RuntimeError(
          "screen replacement must contain exactly the preceding tainted tasks"
      )
    next_remaining = validate_taint_manifest(
        json.loads(
            (output.parent / replacement_taint["path"]).read_text(
                encoding="utf-8"
            )
        ),
        args.repetition,
        result["sha256"],
        manifest,
        taint_schema,
    )
    if not set(next_remaining) <= set(remaining):
      raise RuntimeError("screen replacement taint expands the pending task set")
    accepted = sorted(set(remaining) - set(next_remaining))
    replacements.append({
        **result,
        "definition_path": definition["path"],
        "definition_sha256": definition["sha256"],
        "taint_path": replacement_taint["path"],
        "taint_sha256": replacement_taint["sha256"],
        "result_tasks": result_tasks,
        "accepted_tasks": accepted,
    })
    remaining = next_remaining
  if remaining:
    raise RuntimeError("screen replacements do not resolve every tainted task")
  plan = {
      "schema_version": plan_schema,
      "repetition": args.repetition,
      "primary": primary,
      "taint": taint,
      "replacements": replacements,
  }
  output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
  print(output)


def command_screen_plan(args):
  write_iterative_repetition_plan(
      args, SCREEN_REPETITION_PLAN_SCHEMA, SCREEN_TAINT_SCHEMA
  )


def command_cap16_repetition_plan(args):
  write_iterative_repetition_plan(
      args, CAP16_FORMAL_REPETITION_PLAN_SCHEMA, FORMAL_TAINT_SCHEMA
  )


def command_cap16_probe_plan(args):
  write_iterative_repetition_plan(
      args, CAP16_PROBE_PLAN_SCHEMA, CAP16_PROBE_TAINT_SCHEMA
  )


def command_cap8_probe_plan(args):
  write_iterative_repetition_plan(
      args, CAP8_PROBE_PLAN_SCHEMA, CAP8_PROBE_TAINT_SCHEMA
  )


def load_screen_plan(
    path,
    manifest,
    manifest_path,
    host,
    sv_benchmarks,
    benchmark_definition,
    plan_schema=SCREEN_REPETITION_PLAN_SCHEMA,
    repetition=1,
    display=DISCOVERY_DISPLAY,
    time_limit="120 s",
    taint_schema=SCREEN_TAINT_SCHEMA,
    definition_validator=validate_screen_definition,
    hard_threshold=200,
):
  declared_path = Path(path)
  path = declared_path.resolve()
  if (
      declared_path.is_symlink()
      or Path(os.path.abspath(declared_path)) != path
      or not path.is_file()
  ):
    raise RuntimeError("screen plan must be a regular non-symlink file")
  plan = json.loads(path.read_text(encoding="utf-8"))
  if not isinstance(plan, dict) or set(plan) != {
      "schema_version",
      "repetition",
      "primary",
      "taint",
      "replacements",
  } or (
      plan["schema_version"] != plan_schema
      or plan["repetition"] != repetition
      or not isinstance(plan["replacements"], list)
  ):
    raise RuntimeError("screen plan topology or identity is invalid")
  root = path.parent
  primary = declared_plan_file(root, plan["primary"], "screen primary result")
  primary_hash = plan["primary"]["sha256"]
  primary_metadata = (
      probe_result_metadata(primary, allow_incomplete=True)
      if display == PROBE_DISPLAY
      else result_metadata(
          primary, display, time_limit, allow_incomplete=True
      )
  )
  if primary_metadata["host"] != host:
    raise RuntimeError("screen primary result does not match its manifest host")
  validate_result_run_topology(
      primary, manifest, sv_benchmarks, benchmark_definition
  )
  primary_rows = {
      row["task"]: row
      for row in baseline.parse_result_rows(
          primary, manifest, hard_threshold
      )
  }
  if plan["taint"] is None:
    tainted = {}
    taint_hash = None
  else:
    taint_path = declared_plan_file(
        root, plan["taint"], "screen primary taint"
    )
    taint_hash = plan["taint"]["sha256"]
    tainted = validate_taint_manifest(
        json.loads(taint_path.read_text(encoding="utf-8")),
        repetition,
        primary_hash,
        manifest,
        taint_schema,
    )
  missing = {
      task for task, row in primary_rows.items() if not row_is_complete(row)
  }
  if missing - set(tainted):
    raise RuntimeError(
        f"incomplete screen primary rows are not tainted: "
        f"{sorted(missing - set(tainted))}"
    )
  accepted = {
      task: row
      for task, row in primary_rows.items()
      if task not in tainted
  }
  row_sources = {
      task: {
          "task": task,
          "source": "primary",
          "result_path": plan["primary"]["path"],
          "result_sha256": primary_hash,
      }
      for task in accepted
  }
  remaining = set(tainted)
  pending_reasons = dict(tainted)
  result_hashes = [primary_hash]
  metadata = [primary_metadata]
  for entry in plan["replacements"]:
    if (
        not isinstance(entry, dict)
        or set(entry) != {
            "path",
            "sha256",
            "definition_path",
            "definition_sha256",
            "taint_path",
            "taint_sha256",
            "result_tasks",
            "accepted_tasks",
        }
        or not isinstance(entry["path"], str)
        or not isinstance(entry["result_tasks"], list)
        or not isinstance(entry["accepted_tasks"], list)
        or entry["result_tasks"] != sorted(entry["result_tasks"])
        or entry["accepted_tasks"] != sorted(entry["accepted_tasks"])
    ):
      raise RuntimeError("screen replacement entry is invalid")
    replacement = declared_plan_file(
        root,
        {"path": entry["path"], "sha256": entry["sha256"]},
        "screen replacement result",
    )
    definition = declared_plan_file(
        root,
        {
            "path": entry["definition_path"],
            "sha256": entry["definition_sha256"],
        },
        "screen replacement definition",
    )
    replacement_taint = declared_plan_file(
        root,
        {"path": entry["taint_path"], "sha256": entry["taint_sha256"]},
        "screen replacement taint",
    )
    if (
        set(entry["result_tasks"]) != remaining
        or sorted(result_task_names(replacement, manifest))
        != entry["result_tasks"]
    ):
      raise RuntimeError(
          "screen replacement tasks do not equal the pending task set"
      )
    subset = {task: manifest[task] for task in entry["result_tasks"]}
    replacement_manifest = {
        "task_count": len(entry["result_tasks"]),
        "tasks": [manifest[task] for task in entry["result_tasks"]],
    }
    definition_validator(
        definition,
        manifest_path,
        replacement_manifest,
        sv_benchmarks,
    )
    replacement_metadata = (
        probe_result_metadata(replacement, allow_incomplete=True)
        if display == PROBE_DISPLAY
        else result_metadata(
            replacement, display, time_limit, allow_incomplete=True
        )
    )
    if replacement_metadata["host"] != host:
      raise RuntimeError("screen replacement does not match its manifest host")
    validate_result_run_topology(
        replacement, subset, sv_benchmarks, definition
    )
    rows = {
        row["task"]: row
        for row in baseline.parse_result_rows(
            replacement, subset, hard_threshold
        )
    }
    next_tainted = validate_taint_manifest(
        json.loads(replacement_taint.read_text(encoding="utf-8")),
        repetition,
        entry["sha256"],
        manifest,
        taint_schema,
    )
    if not set(next_tainted) <= remaining:
      raise RuntimeError("screen replacement taint expands the pending task set")
    expected_accepted = sorted(remaining - set(next_tainted))
    if entry["accepted_tasks"] != expected_accepted:
      raise RuntimeError("screen replacement accepted-task set is invalid")
    if any(not row_is_complete(rows[task]) for task in expected_accepted):
      raise RuntimeError("accepted screen replacement row is incomplete")
    for task in expected_accepted:
      accepted[task] = rows[task]
      row_sources[task] = {
          "task": task,
          "source": "replacement",
          "result_path": entry["path"],
          "result_sha256": entry["sha256"],
          "definition_path": entry["definition_path"],
          "definition_sha256": entry["definition_sha256"],
          "taint_path": entry["taint_path"],
          "taint_sha256": entry["taint_sha256"],
          "reason": pending_reasons[task],
      }
    remaining = set(next_tainted)
    pending_reasons = dict(next_tainted)
    result_hashes.append(entry["sha256"])
    metadata.append(replacement_metadata)
  if remaining or set(accepted) != set(manifest):
    raise RuntimeError("screen plan does not resolve exactly the full manifest")
  if len(result_hashes) != len(set(result_hashes)):
    raise RuntimeError("screen result artifacts must be distinct")
  for field in ("starttime", "benchmarkname"):
    if len({item[field] for item in metadata}) != len(metadata):
      raise RuntimeError(f"screen attempts must have distinct {field} values")
  return {
      "repetition": repetition,
      "plan_sha256": baseline.sha256_file(path),
      "primary_sha256": primary_hash,
      "taint_sha256": taint_hash,
      "replacement_sha256": result_hashes[1:],
      "metadata": primary_metadata,
      "replacement_metadata": metadata[1:],
      "rows": accepted,
      "row_sources": [row_sources[task] for task in sorted(row_sources)],
  }


def command_summarize(args):
  require_absent_or_empty_output(args.output_dir)
  if len(args.repetition_plan) != 2:
    raise RuntimeError("Dataset classification requires exactly two frozen repetitions")
  if args.hard_threshold != 200:
    raise RuntimeError("formal hard threshold is fixed at 200 CPU seconds")
  manifest_path = Path(args.manifest).resolve()
  full_manifest, host = authenticate_formal_manifest(args)
  if not full_manifest["tasks"]:
    raise RuntimeError("formal Phase B skipped: authenticated host merge has no tasks")
  validate_formal_definition(
      args.benchmark_definition,
      manifest_path,
      full_manifest,
      args.sv_benchmarks,
  )
  manifest = baseline.load_task_manifest(manifest_path)
  if hasattr(args, "phase_a_output"):
    plans = [
        load_screen_plan(
            plan,
            manifest,
            manifest_path,
            host,
            args.sv_benchmarks,
            args.benchmark_definition,
            plan_schema=CAP16_FORMAL_REPETITION_PLAN_SCHEMA,
            repetition=index,
            display=FORMAL_DISPLAY,
            time_limit="900 s",
            taint_schema=FORMAL_TAINT_SCHEMA,
            definition_validator=validate_formal_definition,
            hard_threshold=args.hard_threshold,
        )
        for index, plan in enumerate(args.repetition_plan, start=1)
    ]
  else:
    plans = [
        load_repetition_plan(
          plan,
          manifest,
          manifest_path,
          host,
          args.sv_benchmarks,
          args.benchmark_definition,
          args.hard_threshold,
        )
        for plan in args.repetition_plan
    ]
  if [plan["repetition"] for plan in plans] != [1, 2]:
    raise RuntimeError("formal repetition plans must be ordered 1 then 2")
  if len({plan["plan_sha256"] for plan in plans}) != 2:
    raise RuntimeError("formal repetition plans must have distinct hashes")
  if len({plan["primary_sha256"] for plan in plans}) != 2:
    raise RuntimeError("formal repetitions must have distinct primary results")
  all_result_hashes = [
      digest
      for plan in plans
      for digest in [plan["primary_sha256"], *plan["replacement_sha256"]]
  ]
  if len(all_result_hashes) != len(set(all_result_hashes)):
    raise RuntimeError("formal result artifacts cannot be reused across repetitions")
  metadata = [plan["metadata"] for plan in plans]
  for field in ("starttime", "benchmarkname"):
    if len({result[field] for result in metadata}) != 2:
      raise RuntimeError(f"formal repetitions must have distinct {field} values")
  output = Path(args.output_dir)
  output.mkdir(parents=True, exist_ok=True)
  provenance = {
      "schema_version": "hard-case-formal-row-provenance-v1",
      "repetitions": [
          {
              "repetition": plan["repetition"],
              "plan_sha256": plan["plan_sha256"],
              "primary_result_sha256": plan["primary_sha256"],
              "taint_manifest_sha256": plan["taint_sha256"],
              "replacement_result_sha256": plan["replacement_sha256"],
              "rows": plan["row_sources"],
          }
          for plan in plans
      ],
  }
  provenance_path = output / "row-provenance.json"
  provenance_path.write_text(
      json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
  )
  details = {row["task"]: row for row in full_manifest["tasks"]}
  rows = []
  for task in sorted(manifest):
    runs = [plan["rows"][task] for plan in plans]
    classification = classify_repetitions(runs, args.hard_threshold)
    family = details[task]["family"]
    rows.append(
        {
            "task": task,
            "source": details[task]["source"],
            "family": family,
            "expected_verdict": manifest[task]["expected_verdict"],
            "classification": classification,
            "split": split_for_family(f"{details[task]['source']}:{family}"),
            "cpu_seconds": ";".join(str(run["cpu_time_seconds"]) for run in runs),
            "statuses": ";".join(run["status"] for run in runs),
            "result_sources": ";".join(
                next(
                    row["source"]
                    for row in plan["row_sources"]
                    if row["task"] == task
                )
                for plan in plans
            ),
        }
    )
  fieldnames = (
      list(rows[0])
      if rows
      else [
          "task",
          "source",
          "family",
          "expected_verdict",
          "classification",
          "split",
          "cpu_seconds",
          "statuses",
          "result_sources",
      ]
  )
  for filename, subset in (
      ("classification.csv", rows),
      (
          "hard-portfolio.csv",
          [
              row
              for row in rows
              if row["classification"]
              in {"stable_hard_solved", "stable_analysis_unsolved"}
          ],
      ),
      (
          "wrong-quarantine.csv",
          [row for row in rows if row["classification"] == "wrong_quarantine"],
      ),
      (
          "verifier-failure-quarantine.csv",
          [
              row
              for row in rows
              if row["classification"] == "verifier_failure_quarantine"
          ],
      ),
      ("mixed.csv", [row for row in rows if row["classification"] == "mixed"]),
  ):
    with (output / filename).open("w", newline="", encoding="utf-8") as target:
      writer = csv.DictWriter(target, fieldnames=fieldnames)
      writer.writeheader()
      writer.writerows(subset)
  counts = collections.Counter(row["classification"] for row in rows)
  summary = {
      "task_count": len(rows),
      "repetitions": 2,
      "hard_threshold_cpu_seconds": args.hard_threshold,
      "classifications": dict(sorted(counts.items())),
      "hard_portfolio": sum(
          row["classification"]
          in {"stable_hard_solved", "stable_analysis_unsolved"}
          for row in rows
      ),
      "by_source": {
          source: dict(
              sorted(
                  collections.Counter(
                      row["classification"] for row in rows if row["source"] == source
                  ).items()
              )
          )
          for source in sorted({row["source"] for row in rows})
      },
      "repetition_plan_sha256": [plan["plan_sha256"] for plan in plans],
      "primary_result_sha256": [plan["primary_sha256"] for plan in plans],
      "replacement_result_sha256": [
          plan["replacement_sha256"] for plan in plans
      ],
      "row_provenance_sha256": baseline.sha256_file(provenance_path),
      "host": host,
      "manifest_sha256": baseline.sha256_file(manifest_path),
      "benchmark_definition_sha256": baseline.sha256_file(
          Path(args.benchmark_definition)
      ),
  }
  (output / "summary.json").write_text(
      json.dumps(summary, indent=2) + "\n", encoding="utf-8"
  )


def add_phase_b_inputs(parser):
  parser.add_argument("--parent-manifest", required=True)
  parser.add_argument("--phase-a-manifest", action="append", required=True)
  parser.add_argument("--survivor-manifest", action="append", required=True)
  parser.add_argument("--phase-a-result", action="append", required=True)
  parser.add_argument("--sv-benchmarks", required=True)


def add_cap16_phase_b_input(parser):
  parser.add_argument("--phase-a-output", required=True)
  parser.add_argument("--sv-benchmarks", required=True)


def main():
  parser = argparse.ArgumentParser()
  commands = parser.add_subparsers(required=True)
  inventory = commands.add_parser("inventory")
  inventory.add_argument("--sv-benchmarks", required=True)
  inventory.add_argument("--svcomp-results", required=True)
  inventory.add_argument("--prior-results", required=True)
  inventory.add_argument("--external-root", required=True)
  inventory.add_argument("--output-dir", required=True)
  inventory.add_argument("--official-family-cap", type=int, default=1)
  inventory.add_argument("--external-family-cap", type=int, default=2)
  inventory.set_defaults(function=command_inventory)
  difference = commands.add_parser("difference")
  difference.add_argument("--manifest", required=True)
  difference.add_argument("--exclude-manifest", required=True)
  difference.add_argument("--sv-benchmarks", required=True)
  difference.add_argument("--output-dir", required=True)
  difference.add_argument(
      "--host", action="append", choices=DISCOVERY_HOSTS
  )
  difference.set_defaults(function=command_difference)
  validate_shards = commands.add_parser("validate-shards")
  validate_shards.add_argument("--manifest", required=True)
  validate_shards.add_argument("--shard-manifest", action="append", required=True)
  validate_shards.add_argument("--sv-benchmarks", required=True)
  validate_shards.add_argument(
      "--host", action="append", choices=DISCOVERY_HOSTS
  )
  validate_shards.set_defaults(function=command_validate_shards)
  reroute = commands.add_parser("reroute-cthulhu")
  reroute.add_argument("--manifest", required=True)
  reroute.add_argument("--sv-benchmarks", required=True)
  reroute.add_argument("--output-dir", required=True)
  reroute.set_defaults(function=command_reroute_cthulhu)
  validate_reroute = commands.add_parser("validate-reroute")
  validate_reroute.add_argument("--manifest", required=True)
  validate_reroute.add_argument(
      "--reroute-manifest", action="append", required=True
  )
  validate_reroute.add_argument("--sv-benchmarks", required=True)
  validate_reroute.set_defaults(function=command_validate_reroute)
  athena_recovery = commands.add_parser("athena-recovery")
  athena_recovery.add_argument("--athena-manifest", required=True)
  athena_recovery.add_argument("--athena-reroute-manifest", required=True)
  athena_recovery.add_argument("--sv-benchmarks", required=True)
  athena_recovery.add_argument("--output-dir", required=True)
  athena_recovery.set_defaults(function=command_athena_recovery)
  validate_athena_recovery = commands.add_parser(
      "validate-athena-recovery"
  )
  validate_athena_recovery.add_argument("--athena-manifest", required=True)
  validate_athena_recovery.add_argument(
      "--athena-reroute-manifest", required=True
  )
  validate_athena_recovery.add_argument("--manifest", required=True)
  validate_athena_recovery.add_argument("--sv-benchmarks", required=True)
  validate_athena_recovery.set_defaults(
      function=command_validate_athena_recovery
  )
  merge_survivors = commands.add_parser("merge-survivors")
  add_phase_b_inputs(merge_survivors)
  merge_survivors.add_argument("--output-dir", required=True)
  merge_survivors.set_defaults(function=command_merge_survivors)
  render = commands.add_parser("render")
  render.add_argument("--manifest", required=True)
  render.add_argument("--sv-benchmarks", required=True)
  render.add_argument("--property-file", required=True)
  render.add_argument("--output-dir", required=True)
  render.set_defaults(function=command_render)
  render_formal = commands.add_parser("render-formal")
  add_phase_b_inputs(render_formal)
  render_formal.add_argument("--manifest", required=True)
  render_formal.add_argument("--property-file", required=True)
  render_formal.add_argument("--output-dir", required=True)
  render_formal.set_defaults(function=command_render_formal)
  render_cap16_formal = commands.add_parser("render-cap16-formal")
  add_cap16_phase_b_input(render_cap16_formal)
  render_cap16_formal.add_argument("--manifest", required=True)
  render_cap16_formal.add_argument("--property-file", required=True)
  render_cap16_formal.add_argument("--output-dir", required=True)
  render_cap16_formal.set_defaults(function=command_render_formal)
  render_replacement = commands.add_parser("render-formal-replacement")
  add_phase_b_inputs(render_replacement)
  render_replacement.add_argument("--manifest", required=True)
  render_replacement.add_argument("--primary-result", required=True)
  render_replacement.add_argument("--taint-manifest", required=True)
  render_replacement.add_argument("--property-file", required=True)
  render_replacement.add_argument("--output-dir", required=True)
  render_replacement.set_defaults(function=command_render_formal_replacement)
  render_cap16_replacement = commands.add_parser(
      "render-cap16-formal-replacement"
  )
  add_cap16_phase_b_input(render_cap16_replacement)
  render_cap16_replacement.add_argument("--manifest", required=True)
  render_cap16_replacement.add_argument("--primary-result", required=True)
  render_cap16_replacement.add_argument("--taint-manifest", required=True)
  render_cap16_replacement.add_argument("--property-file", required=True)
  render_cap16_replacement.add_argument("--output-dir", required=True)
  render_cap16_replacement.set_defaults(
      function=command_render_formal_replacement
  )
  render_screen_replacement = commands.add_parser(
      "render-screen-replacement"
  )
  render_screen_replacement.add_argument("--manifest", required=True)
  render_screen_replacement.add_argument("--primary-result", required=True)
  render_screen_replacement.add_argument("--taint-manifest", required=True)
  render_screen_replacement.add_argument("--sv-benchmarks", required=True)
  render_screen_replacement.add_argument("--property-file", required=True)
  render_screen_replacement.add_argument("--output-dir", required=True)
  render_screen_replacement.set_defaults(
      function=command_render_screen_replacement
  )
  probe = commands.add_parser("render-probe")
  probe.add_argument("--manifest", required=True)
  probe.add_argument("--hard-portfolio", required=True)
  probe.add_argument("--sv-benchmarks", required=True)
  probe.add_argument("--property-file", required=True)
  probe.add_argument("--output-dir", required=True)
  probe.set_defaults(function=command_render_probe)
  authenticate_cap8_probe = commands.add_parser(
      "authenticate-cap8-formal-for-probe"
  )
  authenticate_cap8_probe.add_argument("--formal-output", required=True)
  authenticate_cap8_probe.add_argument("--sv-benchmarks", required=True)
  authenticate_cap8_probe.set_defaults(
      function=command_authenticate_cap8_formal_for_probe
  )
  authenticate_cap16_probe = commands.add_parser(
      "authenticate-cap16-formal-for-probe"
  )
  authenticate_cap16_probe.add_argument("--formal-output", required=True)
  authenticate_cap16_probe.add_argument("--sv-benchmarks", required=True)
  authenticate_cap16_probe.set_defaults(
      function=command_authenticate_cap16_formal_for_probe
  )
  package_cap8_probe = commands.add_parser("package-cap8-probe-input")
  package_cap8_probe.add_argument("--formal-output", required=True)
  package_cap8_probe.add_argument("--sv-benchmarks", required=True)
  package_cap8_probe.add_argument("--output-dir", required=True)
  package_cap8_probe.set_defaults(
      function=command_package_cap8_probe_input
  )
  package_cap16_probe = commands.add_parser("package-cap16-probe-input")
  package_cap16_probe.add_argument("--formal-output", required=True)
  package_cap16_probe.add_argument("--sv-benchmarks", required=True)
  package_cap16_probe.add_argument("--output-dir", required=True)
  package_cap16_probe.set_defaults(
      function=command_package_cap16_probe_input
  )
  validate_cap16_probe = commands.add_parser("validate-cap16-probe-input")
  validate_cap16_probe.add_argument("--probe-input", required=True)
  validate_cap16_probe.add_argument("--sv-benchmarks", required=True)
  validate_cap16_probe.set_defaults(
      function=command_validate_cap16_probe_input
  )
  validate_cap8_probe = commands.add_parser("validate-cap8-probe-input")
  validate_cap8_probe.add_argument("--probe-input", required=True)
  validate_cap8_probe.add_argument("--sv-benchmarks", required=True)
  validate_cap8_probe.set_defaults(
      function=command_validate_cap8_probe_input
  )
  render_cap8_probe = commands.add_parser("render-cap8-probe")
  render_cap8_probe.add_argument("--probe-input", required=True)
  render_cap8_probe.add_argument("--sv-benchmarks", required=True)
  render_cap8_probe.add_argument("--property-file", required=True)
  render_cap8_probe.add_argument("--output-dir", required=True)
  render_cap8_probe.set_defaults(function=command_render_cap8_probe)
  render_cap16_probe = commands.add_parser("render-cap16-probe")
  render_cap16_probe.add_argument("--probe-input", required=True)
  render_cap16_probe.add_argument("--sv-benchmarks", required=True)
  render_cap16_probe.add_argument("--property-file", required=True)
  render_cap16_probe.add_argument("--output-dir", required=True)
  render_cap16_probe.set_defaults(function=command_render_cap16_probe)
  render_cap16_probe_replacement = commands.add_parser(
      "render-cap16-probe-replacement"
  )
  render_cap16_probe_replacement.add_argument(
      "--probe-input", required=True
  )
  render_cap16_probe_replacement.add_argument(
      "--sv-benchmarks", required=True
  )
  render_cap16_probe_replacement.add_argument(
      "--primary-result", required=True
  )
  render_cap16_probe_replacement.add_argument(
      "--taint-manifest", required=True
  )
  render_cap16_probe_replacement.add_argument(
      "--property-file", required=True
  )
  render_cap16_probe_replacement.add_argument(
      "--output-dir", required=True
  )
  render_cap16_probe_replacement.set_defaults(
      function=command_render_cap16_probe_replacement
  )
  render_cap8_probe_replacement = commands.add_parser(
      "render-cap8-probe-replacement"
  )
  render_cap8_probe_replacement.add_argument(
      "--probe-input", required=True
  )
  render_cap8_probe_replacement.add_argument(
      "--sv-benchmarks", required=True
  )
  render_cap8_probe_replacement.add_argument(
      "--primary-result", required=True
  )
  render_cap8_probe_replacement.add_argument(
      "--taint-manifest", required=True
  )
  render_cap8_probe_replacement.add_argument(
      "--property-file", required=True
  )
  render_cap8_probe_replacement.add_argument(
      "--output-dir", required=True
  )
  render_cap8_probe_replacement.set_defaults(
      function=command_render_cap8_probe_replacement
  )
  validate = commands.add_parser("validate")
  validate.add_argument("--manifest", required=True)
  validate.add_argument("--sv-benchmarks", required=True)
  validate.set_defaults(function=command_validate)
  validate_cap16 = commands.add_parser("validate-cap16-phase-a")
  add_cap16_phase_b_input(validate_cap16)
  validate_cap16.set_defaults(function=command_validate_cap16_phase_a)
  package_cap16 = commands.add_parser("package-cap16-phase-a")
  add_cap16_phase_b_input(package_cap16)
  package_cap16.add_argument("--output-dir", required=True)
  package_cap16.set_defaults(function=command_package_cap16_phase_a)
  license_audit = commands.add_parser("license-audit")
  license_audit.add_argument("--manifest", required=True)
  license_audit.add_argument("--sv-benchmarks", required=True)
  license_audit.add_argument("--external-root", required=True)
  license_audit.add_argument("--output-dir", required=True)
  license_audit.set_defaults(function=command_license_audit)
  probe_summary = commands.add_parser("probe-summary")
  probe_summary.add_argument("--manifest", required=True)
  probe_summary.add_argument("--hard-portfolio", required=True)
  probe_summary.add_argument("--result-files", required=True)
  probe_summary.add_argument("--output-dir", required=True)
  probe_summary.set_defaults(function=command_probe_summary)
  cap16_probe_summary = commands.add_parser("cap16-probe-summary")
  cap16_probe_summary.add_argument("--probe-input", required=True)
  cap16_probe_summary.add_argument("--sv-benchmarks", required=True)
  cap16_probe_summary.add_argument(
      "--benchmark-definition", required=True
  )
  cap16_probe_summary.add_argument("--probe-plan", required=True)
  cap16_probe_summary.add_argument("--output-dir", required=True)
  cap16_probe_summary.set_defaults(function=command_cap16_probe_summary)
  cap8_probe_summary = commands.add_parser("cap8-probe-summary")
  cap8_probe_summary.add_argument("--probe-input", required=True)
  cap8_probe_summary.add_argument("--sv-benchmarks", required=True)
  cap8_probe_summary.add_argument(
      "--benchmark-definition", required=True
  )
  cap8_probe_summary.add_argument("--probe-plan", required=True)
  cap8_probe_summary.add_argument("--output-dir", required=True)
  cap8_probe_summary.set_defaults(function=command_cap8_probe_summary)
  repetition_plan = commands.add_parser("repetition-plan")
  repetition_plan.add_argument("--manifest", required=True)
  repetition_plan.add_argument("--repetition", type=int, choices=(1, 2), required=True)
  repetition_plan.add_argument("--primary-result", required=True)
  repetition_plan.add_argument("--taint-manifest")
  repetition_plan.add_argument("--replacement-result", action="append")
  repetition_plan.add_argument("--replacement-definition", action="append")
  repetition_plan.add_argument("--output", required=True)
  repetition_plan.set_defaults(function=command_repetition_plan)
  cap16_repetition_plan = commands.add_parser("cap16-repetition-plan")
  cap16_repetition_plan.add_argument("--manifest", required=True)
  cap16_repetition_plan.add_argument(
      "--repetition", type=int, choices=(1, 2), required=True
  )
  cap16_repetition_plan.add_argument("--primary-result", required=True)
  cap16_repetition_plan.add_argument("--taint-manifest")
  cap16_repetition_plan.add_argument(
      "--replacement-result", action="append"
  )
  cap16_repetition_plan.add_argument(
      "--replacement-definition", action="append"
  )
  cap16_repetition_plan.add_argument(
      "--replacement-taint-manifest", action="append"
  )
  cap16_repetition_plan.add_argument("--output", required=True)
  cap16_repetition_plan.set_defaults(
      function=command_cap16_repetition_plan
  )
  cap16_probe_plan = commands.add_parser("cap16-probe-plan")
  cap16_probe_plan.add_argument("--manifest", required=True)
  cap16_probe_plan.add_argument("--primary-result", required=True)
  cap16_probe_plan.add_argument("--taint-manifest")
  cap16_probe_plan.add_argument("--replacement-result", action="append")
  cap16_probe_plan.add_argument(
      "--replacement-definition", action="append"
  )
  cap16_probe_plan.add_argument(
      "--replacement-taint-manifest", action="append"
  )
  cap16_probe_plan.add_argument("--output", required=True)
  cap16_probe_plan.set_defaults(
      function=command_cap16_probe_plan, repetition=1
  )
  cap8_probe_plan = commands.add_parser("cap8-probe-plan")
  cap8_probe_plan.add_argument("--manifest", required=True)
  cap8_probe_plan.add_argument("--primary-result", required=True)
  cap8_probe_plan.add_argument("--taint-manifest")
  cap8_probe_plan.add_argument("--replacement-result", action="append")
  cap8_probe_plan.add_argument(
      "--replacement-definition", action="append"
  )
  cap8_probe_plan.add_argument(
      "--replacement-taint-manifest", action="append"
  )
  cap8_probe_plan.add_argument("--output", required=True)
  cap8_probe_plan.set_defaults(
      function=command_cap8_probe_plan, repetition=1
  )
  screen_plan = commands.add_parser("screen-plan")
  screen_plan.add_argument("--manifest", required=True)
  screen_plan.add_argument("--primary-result", required=True)
  screen_plan.add_argument("--taint-manifest")
  screen_plan.add_argument("--replacement-result", action="append")
  screen_plan.add_argument("--replacement-definition", action="append")
  screen_plan.add_argument("--replacement-taint-manifest", action="append")
  screen_plan.add_argument("--output", required=True)
  screen_plan.set_defaults(function=command_screen_plan, repetition=1)
  monitor_formal_load = commands.add_parser("monitor-formal-load")
  monitor_formal_load.add_argument("--output", required=True)
  monitor_formal_load.add_argument("--exclude-root", type=int, required=True)
  monitor_formal_load.set_defaults(function=command_monitor_formal_load)
  capture_process = commands.add_parser("capture-process-identity")
  capture_process.add_argument("--pid", type=int, required=True)
  capture_process.add_argument("--role", required=True)
  capture_process.add_argument("--output", required=True)
  capture_process.set_defaults(function=command_capture_process_identity)
  process_unit = commands.add_parser("formal-systemd-unit")
  process_unit.add_argument("--output-root", required=True)
  process_unit.add_argument(
      "--mode",
      choices=("cap8", "cap16", "cap8-probe", "cap16-probe"),
      required=True,
  )
  process_unit.add_argument("--label", required=True)
  process_unit.set_defaults(function=command_formal_systemd_unit)
  process_descriptor = commands.add_parser(
      "write-formal-process-descriptor"
  )
  for name in (
      "output-root",
      "mode",
      "label",
      "host",
      "name",
      "definition",
      "result-output",
      "monitor-output",
      "dataset-py",
      "cpachecker-dir",
      "benchexec-dir",
      "python-bin",
      "java-home",
      "p-cores",
      "output",
  ):
    process_descriptor.add_argument(f"--{name}", required=True)
  process_descriptor.add_argument(
      "--monitor-exclude-root", type=int, required=True
  )
  process_descriptor.set_defaults(
      function=command_write_formal_process_descriptor
  )
  require_formal_gone = commands.add_parser(
      "require-formal-process-gone"
  )
  require_formal_gone.add_argument("--descriptor", required=True)
  require_formal_gone.add_argument("--identity", required=True)
  require_formal_gone.add_argument("--output-root", required=True)
  require_formal_gone.add_argument(
      "--mode",
      choices=("cap8", "cap16", "cap8-probe", "cap16-probe"),
      required=True,
  )
  require_formal_gone.add_argument("--label", required=True)
  require_formal_gone.add_argument("--host", required=True)
  require_formal_gone.add_argument(
      "--role",
      choices=("benchexec-launcher", "load-monitor"),
      required=True,
  )
  require_formal_gone.set_defaults(
      function=command_require_formal_process_gone
  )
  attempt_complete = commands.add_parser("formal-attempt-complete")
  attempt_complete.add_argument("--output-root", required=True)
  attempt_complete.add_argument("--manifest", required=True)
  attempt_complete.add_argument("--sv-benchmarks", required=True)
  attempt_complete.add_argument("--host", required=True)
  attempt_complete.add_argument(
      "--mode",
      choices=("cap8", "cap16", "cap8-probe", "cap16-probe"),
      required=True,
  )
  attempt_complete.add_argument("--label", required=True)
  attempt_complete.add_argument(
      "--role", choices=("primary", "replacement"), required=True
  )
  attempt_complete.add_argument(
      "--repetition", type=int, choices=(1, 2), required=True
  )
  attempt_complete.add_argument(
      "--benchexec-exit", type=int, required=True
  )
  for name in (
      "definition",
      "result",
      "benchexec-log",
      "benchexec-process",
      "process-descriptor",
      "load-monitor",
      "monitor-pid",
      "monitor-process",
      "monitor-stopped",
      "machine-before",
      "machine-after",
      "machine-check",
  ):
    attempt_complete.add_argument(f"--{name}", required=True)
  attempt_complete.add_argument("--output", required=True)
  attempt_complete.set_defaults(function=command_formal_attempt_complete)
  formal_closure = commands.add_parser("validate-formal-closure")
  formal_closure.add_argument("--output-root", required=True)
  formal_closure.add_argument("--manifest", required=True)
  formal_closure.add_argument("--benchmark-definition", required=True)
  formal_closure.add_argument("--sv-benchmarks", required=True)
  formal_closure.add_argument("--host", required=True)
  formal_closure.add_argument("--mode", choices=("cap8", "cap16"), required=True)
  formal_closure.add_argument(
      "--repetition-plan", action="append", required=True
  )
  formal_closure.add_argument("--require-complete", action="store_true")
  formal_closure.set_defaults(function=command_validate_formal_closure)
  probe_closure = commands.add_parser("validate-cap16-probe-closure")
  probe_closure.add_argument("--output-root", required=True)
  probe_closure.add_argument("--sv-benchmarks", required=True)
  probe_closure.add_argument("--require-complete", action="store_true")
  probe_closure.set_defaults(
      function=command_validate_cap16_probe_closure
  )
  cap8_probe_closure = commands.add_parser(
      "validate-cap8-probe-closure"
  )
  cap8_probe_closure.add_argument("--output-root", required=True)
  cap8_probe_closure.add_argument("--sv-benchmarks", required=True)
  cap8_probe_closure.add_argument(
      "--require-complete", action="store_true"
  )
  cap8_probe_closure.set_defaults(
      function=command_validate_cap8_probe_closure
  )
  complete_sentinel = commands.add_parser("write-complete-sentinel")
  complete_sentinel.add_argument("--output", required=True)
  complete_sentinel.set_defaults(function=command_write_complete_sentinel)
  formal_taint = commands.add_parser("formal-taint")
  formal_taint.add_argument("--manifest", required=True)
  formal_taint.add_argument("--repetition", type=int, choices=(1, 2), required=True)
  formal_taint.add_argument("--result", required=True)
  formal_taint.add_argument("--benchexec-log", required=True)
  formal_taint.add_argument("--load-monitor", required=True)
  formal_taint.add_argument("--output", required=True)
  formal_taint.set_defaults(function=command_formal_taint)
  probe_taint = commands.add_parser("probe-taint")
  probe_taint.add_argument("--manifest", required=True)
  probe_taint.add_argument("--result", required=True)
  probe_taint.add_argument("--benchexec-log", required=True)
  probe_taint.add_argument("--load-monitor", required=True)
  probe_taint.add_argument("--output", required=True)
  probe_taint.set_defaults(function=command_probe_taint)
  cap16_probe_taint = commands.add_parser("cap16-probe-taint")
  cap16_probe_taint.add_argument("--manifest", required=True)
  cap16_probe_taint.add_argument("--result", required=True)
  cap16_probe_taint.add_argument("--benchexec-log", required=True)
  cap16_probe_taint.add_argument("--load-monitor", required=True)
  cap16_probe_taint.add_argument("--output", required=True)
  cap16_probe_taint.set_defaults(function=command_probe_taint)
  cap8_probe_taint = commands.add_parser("cap8-probe-taint")
  cap8_probe_taint.add_argument("--manifest", required=True)
  cap8_probe_taint.add_argument("--result", required=True)
  cap8_probe_taint.add_argument("--benchexec-log", required=True)
  cap8_probe_taint.add_argument("--load-monitor", required=True)
  cap8_probe_taint.add_argument("--output", required=True)
  cap8_probe_taint.set_defaults(function=command_cap8_probe_taint)
  screen_taint = commands.add_parser("screen-taint")
  screen_taint.add_argument("--manifest", required=True)
  screen_taint.add_argument("--result", required=True)
  screen_taint.add_argument("--benchexec-log", required=True)
  screen_taint.add_argument("--load-monitor", required=True)
  screen_taint.add_argument("--output", required=True)
  screen_taint.set_defaults(function=command_screen_taint)
  summarize = commands.add_parser("summarize")
  add_phase_b_inputs(summarize)
  summarize.add_argument("--manifest", required=True)
  summarize.add_argument("--benchmark-definition", required=True)
  summarize.add_argument("--repetition-plan", action="append", required=True)
  summarize.add_argument("--output-dir", required=True)
  summarize.add_argument("--hard-threshold", type=float, default=200)
  summarize.set_defaults(function=command_summarize)
  summarize_cap16 = commands.add_parser("summarize-cap16-formal")
  add_cap16_phase_b_input(summarize_cap16)
  summarize_cap16.add_argument("--manifest", required=True)
  summarize_cap16.add_argument("--benchmark-definition", required=True)
  summarize_cap16.add_argument(
      "--repetition-plan", action="append", required=True
  )
  summarize_cap16.add_argument("--output-dir", required=True)
  summarize_cap16.add_argument("--hard-threshold", type=float, default=200)
  summarize_cap16.set_defaults(function=command_summarize)
  screen_summary = commands.add_parser("screen-summary")
  screen_summary.add_argument("--manifest", required=True)
  screen_summary.add_argument("--result", required=True)
  screen_summary.add_argument("--sv-benchmarks", required=True)
  screen_summary.add_argument("--phase-a-host", required=True)
  screen_summary.add_argument("--output-dir", required=True)
  screen_summary.set_defaults(function=command_screen_summary)
  screen_summary_plan = commands.add_parser("screen-summary-plan")
  screen_summary_plan.add_argument("--manifest", required=True)
  screen_summary_plan.add_argument("--benchmark-definition", required=True)
  screen_summary_plan.add_argument("--screen-plan", required=True)
  screen_summary_plan.add_argument("--sv-benchmarks", required=True)
  screen_summary_plan.add_argument("--phase-a-host", required=True)
  screen_summary_plan.add_argument("--output-dir", required=True)
  screen_summary_plan.set_defaults(function=command_screen_summary_plan)
  args = parser.parse_args()
  args.function(args)


if __name__ == "__main__":
  main()
