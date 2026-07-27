#!/usr/bin/env python3

# This file is part of CPAchecker,
# a tool for configurable software verification:
# https://cpachecker.sosy-lab.org
#
# SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>
#
# SPDX-License-Identifier: Apache-2.0

import argparse
import collections
import csv
import hashlib
import importlib.util
import json
import os
import re
import shutil
import statistics
import subprocess
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
    return "stable_unsolved"
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


def render_stock(args, display, limits):
  manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
  output = Path(args.output_dir).resolve()
  output.mkdir(parents=True, exist_ok=True)
  task_sets = write_task_sets(
      manifest["tasks"], Path(args.manifest), args.sv_benchmarks, output
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


def result_metadata(path, display, time_limit):
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
  if (
      root.tag != "result"
      or "error" in root.attrib
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
      or not metadata["endtime"]
      or not metadata["benchmarkname"]
  ):
    raise RuntimeError("result lacks a start time, end time, or benchmark name")
  return metadata


def benchexec_path_representations(
    expected_path, sv_benchmarks, benchmark_definition
):
  expected = Path(expected_path).resolve()
  sv_benchmarks = Path(sv_benchmarks).resolve()
  representations = {expected.as_posix()}
  if benchmark_definition:
    relative = os.path.relpath(
        expected, Path(benchmark_definition).resolve().parent
    ).replace("\\", "/")
    representations.add(relative)
  else:
    relative = expected.relative_to(sv_benchmarks).as_posix()
    representations.add(
        f"../../../../{sv_benchmarks.name}/{relative}"
    )
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


def validate_formal_definition(path, manifest_path, manifest, sv_benchmarks):
  root = ET.parse(path).getroot()
  expected_attributes = {
      "tool": "cpachecker",
      "displayName": FORMAL_DISPLAY,
      "timelimit": "900 s",
      "hardtimelimit": "910 s",
      "walltimelimit": "920 s",
      "memlimit": "15 GB",
      "cpuCores": "4",
  }
  if root.tag != "benchmark" or root.attrib != expected_attributes:
    raise RuntimeError("formal benchmark metadata is not fixed at 900/910/920")
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
  expected = benchmark_root(FORMAL_DISPLAY, "900 s", "910 s", "920 s")
  ET.SubElement(expected, "resultfiles").text = "**/witness.*"
  for name, value in (
      ("--svcomp27", None),
      ("--heap", "10000M"),
      ("--benchmark", None),
      ("--timelimit", "900 s"),
  ):
    option = ET.SubElement(expected, "option", {"name": name})
    if value:
      option.text = value
  write_run_definition(
      expected,
      "hard-case-candidates",
      task_sets,
      Path(sv_benchmarks).resolve() / "c/properties/unreach-call.prp",
      Path(manifest_path).resolve().parent / "corpus/properties/unreach-call.prp",
  )
  if xml_shape(root) != xml_shape(expected):
    raise RuntimeError("formal benchmark definition topology is not frozen")
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
      raise RuntimeError("formal benchmark task set does not match the host manifest")


def command_render_probe(args):
  manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
  details = {row["task"]: row for row in manifest["tasks"]}
  with Path(args.hard_portfolio).open(newline="", encoding="utf-8") as source:
    tasks = [row["task"] for row in csv.DictReader(source)]
  selected = [details[task] for task in tasks]
  output = Path(args.output_dir).resolve()
  output.mkdir(parents=True, exist_ok=True)
  task_sets = write_task_sets(
      selected, Path(args.manifest), args.sv_benchmarks, output
  )
  root = benchmark_root(
      "VGuide no-candidate CEGAR eligibility probe", "900 s", "910 s", "920 s"
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
      args.property_file,
      Path(args.manifest).resolve().parent / "corpus/properties/unreach-call.prp",
  )
  benchmark = output / "cegar-eligibility.xml"
  write_xml(root, benchmark)
  print(benchmark)


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
  assigned = stratified_shards(difference["tasks"])
  shards = {}
  shard_manifests = {}
  for host in DISCOVERY_HOSTS:
    host_tasks = [row["task"] for row in assigned[host]]
    shard = manifest_subset(
        full,
        host_tasks,
        {
            "operation": "deterministic_stratified_shard",
            "source_manifest_sha256": full_sha256,
            "parent_manifest_sha256": difference_sha256,
            "hosts": list(DISCOVERY_HOSTS),
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
  manifest_path = Path(args.manifest).resolve()
  manifest = validate_manifest(manifest_path, args.sv_benchmarks)
  parent_sha256 = baseline.sha256_file(manifest_path)
  shards = {}
  for path in args.shard_manifest:
    shard = validate_manifest(path, args.sv_benchmarks)
    derivation = shard.get("derivation", {})
    host = derivation.get("host")
    if host not in DISCOVERY_HOSTS or host in shards:
      raise RuntimeError(f"invalid or duplicate shard host: {host}")
    if derivation.get("operation") != "deterministic_stratified_shard":
      raise RuntimeError(f"invalid shard operation: {host}")
    if derivation.get("hosts") != list(DISCOVERY_HOSTS):
      raise RuntimeError(f"invalid shard host list: {host}")
    if derivation.get("parent_manifest_sha256") != parent_sha256:
      raise RuntimeError(f"invalid shard parent manifest hash: {host}")
    shards[host] = shard["tasks"]
  validate_shard_partition(manifest["tasks"], shards)
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
  _, _, merged = authenticate_phase_b_inputs(args)
  manifest_path = Path(args.manifest).resolve()
  if baseline.sha256_file(manifest_path) != FROZEN_FORMAL_MANIFEST_SHA256:
    raise RuntimeError("formal manifest hash is not the frozen Phase-B input")
  manifest = validate_manifest(manifest_path, args.sv_benchmarks)
  if manifest != merged:
    raise RuntimeError("formal manifest does not match authenticated Valkyrie merge")
  return manifest, "valkyrie"


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
  files = [
      candidate
      for candidate in output.rglob("*")
      if candidate.is_file() and candidate != path
  ]
  entries = []
  aggregate = hashlib.sha256()
  for candidate in sorted(files, key=lambda item: item.relative_to(output).as_posix()):
    relative = candidate.relative_to(output).as_posix()
    digest = baseline.sha256_file(candidate)
    entries.append(
        {
            "path": relative,
            "size_bytes": candidate.stat().st_size,
            "sha256": digest,
        }
    )
    aggregate.update(relative.encode("utf-8"))
    aggregate.update(b"\0")
    aggregate.update(bytes.fromhex(digest))
  artifact = {
      "root": ".",
      "file_count": len(entries),
      "aggregate_sha256": aggregate.hexdigest(),
      "files": entries,
  }
  path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
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
      if not isinstance(events, list):
        raise RuntimeError(f"telemetry is not an event list: {matches[0]}")
      classification = classify_probe_events(events)
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
          "result_sha256": baseline.sha256_file(Path(args.result)),
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
      "result_sha256": baseline.sha256_file(Path(args.result)),
      "survivor_manifest_sha256": baseline.sha256_file(survivor_path),
  }
  (output / "summary.json").write_text(
      json.dumps(summary, indent=2) + "\n", encoding="utf-8"
  )
  print(json.dumps(summary, sort_keys=True))


def command_summarize(args):
  require_absent_or_empty_output(args.output_dir)
  if len(args.result) != 2:
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
  result_hashes = [baseline.sha256_file(Path(result)) for result in args.result]
  if len(set(result_hashes)) != 2:
    raise RuntimeError("formal repetitions must have distinct result hashes")
  manifest = baseline.load_task_manifest(manifest_path)
  repetitions = []
  metadata = []
  for result in args.result:
    result_info = result_metadata(result, FORMAL_DISPLAY, "900 s")
    if result_info["host"] != host:
      raise RuntimeError("formal repetitions must run on the merged manifest host")
    validate_result_run_topology(
        result,
        manifest,
        args.sv_benchmarks,
        args.benchmark_definition,
    )
    metadata.append(result_info)
    repetitions.append(
        {
            row["task"]: row
            for row in baseline.parse_result_rows(
                result, manifest, args.hard_threshold
            )
        }
    )
  for field in ("starttime", "benchmarkname"):
    if len({result[field] for result in metadata}) != 2:
      raise RuntimeError(f"formal repetitions must have distinct {field} values")
  if any(
      row["cpu_time_seconds"] is None or row["wall_time_seconds"] is None
      for repetition in repetitions
      for row in repetition.values()
  ):
    raise RuntimeError("formal result lacks parseable CPU or wall metrics")
  output = Path(args.output_dir)
  output.mkdir(parents=True, exist_ok=True)
  details = {row["task"]: row for row in full_manifest["tasks"]}
  rows = []
  for task in sorted(manifest):
    runs = [repetition[task] for repetition in repetitions]
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
      ]
  )
  for filename, subset in (
      ("classification.csv", rows),
      (
          "hard-portfolio.csv",
          [
              row
              for row in rows
              if row["classification"] in {"stable_hard_solved", "stable_unsolved"}
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
          row["classification"] in {"stable_hard_solved", "stable_unsolved"}
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
      "result_sha256": result_hashes,
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
  difference.set_defaults(function=command_difference)
  validate_shards = commands.add_parser("validate-shards")
  validate_shards.add_argument("--manifest", required=True)
  validate_shards.add_argument("--shard-manifest", action="append", required=True)
  validate_shards.add_argument("--sv-benchmarks", required=True)
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
  probe = commands.add_parser("render-probe")
  probe.add_argument("--manifest", required=True)
  probe.add_argument("--hard-portfolio", required=True)
  probe.add_argument("--sv-benchmarks", required=True)
  probe.add_argument("--property-file", required=True)
  probe.add_argument("--output-dir", required=True)
  probe.set_defaults(function=command_render_probe)
  validate = commands.add_parser("validate")
  validate.add_argument("--manifest", required=True)
  validate.add_argument("--sv-benchmarks", required=True)
  validate.set_defaults(function=command_validate)
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
  summarize = commands.add_parser("summarize")
  add_phase_b_inputs(summarize)
  summarize.add_argument("--manifest", required=True)
  summarize.add_argument("--benchmark-definition", required=True)
  summarize.add_argument("--result", action="append", required=True)
  summarize.add_argument("--output-dir", required=True)
  summarize.add_argument("--hard-threshold", type=float, default=200)
  summarize.set_defaults(function=command_summarize)
  screen_summary = commands.add_parser("screen-summary")
  screen_summary.add_argument("--manifest", required=True)
  screen_summary.add_argument("--result", required=True)
  screen_summary.add_argument("--sv-benchmarks", required=True)
  screen_summary.add_argument("--phase-a-host", required=True)
  screen_summary.add_argument("--output-dir", required=True)
  screen_summary.set_defaults(function=command_screen_summary)
  args = parser.parse_args()
  args.function(args)


if __name__ == "__main__":
  main()
