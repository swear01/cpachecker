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
import csv
import glob
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


P_CORE_CPUS = (0, 2, 4, 6, 8, 10, 12, 14)
EXPECTED_TASK_COUNT = 764


def sha256_file(path):
  digest = hashlib.sha256()
  with path.open("rb") as source:
    for chunk in iter(lambda: source.read(1024 * 1024), b""):
      digest.update(chunk)
  return digest.hexdigest()


def git_output(repo, *args):
  return subprocess.check_output(
      ["git", "-C", str(repo), *args], text=True, stderr=subprocess.STDOUT
  ).strip()


def expand_set(sv_benchmarks, set_name):
  root = Path(sv_benchmarks).resolve() / "c"
  set_path = root / set_name
  tasks = []
  for raw_line in set_path.read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#"):
      continue
    tasks.extend(Path(path) for path in glob.glob(str(root / line)))
  return sorted(set(tasks))


def task_metadata(task):
  input_files = []
  current_property = None
  expected = None
  data_model = None
  in_input_list = False
  for raw_line in task.read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if line.startswith("input_files:"):
      value = line.partition(":")[2].strip().strip("'\"")
      in_input_list = not value
      if value:
        input_files.append(value)
      continue
    if in_input_list and line.startswith("-"):
      input_files.append(line[1:].strip().strip("'\""))
      continue
    if in_input_list and raw_line and not raw_line.startswith((" ", "\t")):
      in_input_list = False
    if line.startswith("- property_file:"):
      current_property = line.partition(":")[2].strip().strip("'\"")
      continue
    if current_property and current_property.endswith("/unreach-call.prp"):
      if line.startswith("expected_verdict:"):
        expected = line.partition(":")[2].strip().lower()
    if line.startswith("data_model:"):
      data_model = line.partition(":")[2].strip().strip("'\"")
  if expected not in {"true", "false"}:
    return None
  if not input_files or data_model not in {"ILP32", "LP64"}:
    raise ValueError(f"Unsupported task definition: {task}")
  return {"expected_verdict": expected, "input_files": input_files, "data_model": data_model}


def load_tasks(sv_benchmarks):
  root = Path(sv_benchmarks).resolve()
  tasks = []
  for task in expand_set(root, "Loops.set") + expand_set(root, "VerifyThis-Loops.set"):
    metadata = task_metadata(task)
    if metadata is None:
      continue
    rel_task = task.relative_to(root).as_posix()
    sources = [(task.parent / source).resolve() for source in metadata["input_files"]]
    tasks.append({"task": rel_task, "task_path": task, "sources": sources, **metadata})
  tasks.sort(key=lambda item: item["task"])
  if len(tasks) != EXPECTED_TASK_COUNT:
    raise ValueError(f"Expected {EXPECTED_TASK_COUNT} tasks, found {len(tasks)}")
  return tasks


def corpus_digest(tasks):
  digest = hashlib.sha256()
  for task in tasks:
    for path in [task["task_path"], *task["sources"]]:
      digest.update(path.name.encode("utf-8"))
      digest.update(b"\0")
      digest.update(bytes.fromhex(sha256_file(path)))
  return digest.hexdigest()


def tree_digest(paths, root):
  digest = hashlib.sha256()
  for path in sorted(set(Path(path).resolve() for path in paths)):
    digest.update(path.relative_to(root).as_posix().encode("utf-8"))
    digest.update(b"\0")
    digest.update(bytes.fromhex(sha256_file(path)))
  return digest.hexdigest()


def config_closure(cpachecker, entry):
  root = Path(cpachecker).resolve()
  pending = [root / entry]
  closure = []
  while pending:
    path = pending.pop()
    if path in closure:
      continue
    if not path.is_file():
      raise FileNotFoundError(path)
    closure.append(path)
    for raw_line in path.read_text(encoding="utf-8").splitlines():
      line = raw_line.strip()
      if line.startswith("#include "):
        included = line.removeprefix("#include ").strip()
        candidate = path.parent / included
        if not candidate.is_file():
          candidate = root / "config" / included
        pending.append(candidate.resolve())
  return sorted(closure)


def command_provenance(args):
  cpachecker = Path(args.cpachecker).resolve()
  sv_benchmarks = Path(args.sv_benchmarks).resolve()
  bench_defs = Path(args.bench_defs).resolve()
  benchexec = Path(args.benchexec).resolve()
  closure = config_closure(cpachecker, "config/svcomp27.properties")
  forbidden = [path for path in closure if "vguide" in path.name.lower()]
  if forbidden:
    raise RuntimeError(f"VGuide config in stock closure: {forbidden}")
  tracked_status = git_output(cpachecker, "status", "--porcelain")
  if tracked_status:
    raise RuntimeError("CPAchecker stock checkout is not clean")
  class_files = list((cpachecker / "classes").rglob("*.class"))
  if not class_files:
    raise RuntimeError("CPAchecker stock classes are missing")
  manifest = {
      "stage": "SV-COMP-2027 provisional Stage A",
      "captured_utc": subprocess.check_output(
          ["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"], text=True
      ).strip(),
      "repositories": {
          "cpachecker": git_output(cpachecker, "rev-parse", "HEAD"),
          "sv_benchmarks": git_output(sv_benchmarks, "rev-parse", "HEAD"),
          "benchmark_definitions": git_output(bench_defs, "rev-parse", "HEAD"),
          "benchexec": git_output(benchexec, "rev-parse", "HEAD"),
      },
      "cpachecker_status_porcelain": tracked_status,
      "stock_config": "config/svcomp27.properties",
      "config_closure": [
          {
              "path": path.relative_to(cpachecker).as_posix(),
              "sha256": sha256_file(path),
          }
          for path in closure
      ],
      "config_closure_sha256": tree_digest(closure, cpachecker),
      "compiled_classes_sha256": tree_digest(class_files, cpachecker),
      "benchexec_version": subprocess.check_output(
          [sys.executable, "-m", "benchexec.benchexec", "--version"],
          text=True,
          env={**os.environ, "PYTHONPATH": str(benchexec)},
      ).strip(),
  }
  Path(args.output).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def command_inventory(args):
  tasks = load_tasks(args.sv_benchmarks)
  run_order = {task["task"]: index for index, task in enumerate(sorted(tasks, key=stable_score))}
  rows = []
  for task in tasks:
    rows.append(
        {
            "task": task["task"],
            "run_order": run_order[task["task"]],
            "expected_verdict": task["expected_verdict"],
            "data_model": task["data_model"],
            "input_files": [str(path.relative_to(Path(args.sv_benchmarks).resolve())) for path in task["sources"]],
            "task_sha256": sha256_file(task["task_path"]),
            "input_sha256": [sha256_file(path) for path in task["sources"]],
        }
    )
  output = {
      "task_count": len(rows),
      "expected_true": sum(row["expected_verdict"] == "true" for row in rows),
      "expected_false": sum(row["expected_verdict"] == "false" for row in rows),
      "corpus_sha256": corpus_digest(tasks),
      "tasks": rows,
  }
  Path(args.output).write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")


def read_cpu_value(cpu, name):
  return Path(f"/sys/devices/system/cpu/cpu{cpu}/topology/{name}").read_text().strip()


def read_optional(path):
  candidate = Path(path)
  if not candidate.is_file():
    return None
  try:
    return candidate.read_text().strip()
  except OSError as error:
    return f"unavailable: errno={error.errno} {error.strerror}"


def command_machine(args):
  online = Path("/sys/devices/system/cpu/online").read_text().strip()
  cores = []
  for cpu in P_CORE_CPUS:
    core_id = int(read_cpu_value(cpu, "core_id"))
    siblings = read_cpu_value(cpu, "thread_siblings_list")
    cores.append(
        {
            "cpu": cpu,
            "core_id": core_id,
            "thread_siblings_list": siblings,
            "scaling_governor": read_optional(
                f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_governor"
            ),
            "scaling_max_frequency_khz": read_optional(
                f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_max_freq"
            ),
        }
    )
  core_ids = [core["core_id"] for core in cores]
  if len(set(core_ids)) != len(P_CORE_CPUS) or any(
      core["thread_siblings_list"] != f"{core['cpu']}-{core['cpu'] + 1}" for core in cores
  ):
    raise RuntimeError(f"P-core topology changed: {cores}")
  cpuinfo = Path("/proc/cpuinfo").read_text(encoding="utf-8")
  model_match = re.search(r"^model name\s*:\s*(.+)$", cpuinfo, re.MULTILINE)
  output = {
      "hostname": platform.node(),
      "platform": platform.platform(),
      "kernel": platform.release(),
      "cpu_model": model_match.group(1) if model_match else "unknown",
      "online_cpus": online,
      "allowed_p_core_cpus": list(P_CORE_CPUS),
      "p_cores": cores,
      "intel_pstate_no_turbo": read_optional("/sys/devices/system/cpu/intel_pstate/no_turbo"),
      "load_average": Path("/proc/loadavg").read_text().strip(),
      "thermal_millicelsius": {
          path.parent.name: read_optional(path)
          for path in sorted(Path("/sys/class/thermal").glob("thermal_zone*/temp"))
      },
      "memory_bytes": os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"),
      "java_version": subprocess.check_output(
          [str(Path(os.environ["JAVA_HOME"]) / "bin/java"), "-version"],
          text=True,
          stderr=subprocess.STDOUT,
      ).splitlines()[0],
  }
  Path(args.output).write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")


def stable_score(task):
  return hashlib.sha256(task["task"].encode("utf-8")).hexdigest()


def select_calibration(tasks, per_verdict):
  selected = []
  for verdict in ("true", "false"):
    candidates = sorted(
        (task for task in tasks if task["expected_verdict"] == verdict), key=stable_score
    )
    selected.extend(candidates[:per_verdict])
  return sorted(selected, key=lambda task: task["task"])


def write_benchmark(args, selected):
  output_dir = Path(args.output_dir).resolve()
  output_dir.mkdir(parents=True, exist_ok=True)
  task_set = output_dir / f"{args.name}.set"
  sv_root = Path(args.sv_benchmarks).resolve()
  task_set.write_text(
      "\n".join(str(sv_root / task["task"]) for task in selected) + "\n", encoding="utf-8"
  )
  property_file = sv_root / "c/properties/unreach-call.prp"
  xml = ET.Element(
      "benchmark",
      {
          "tool": "cpachecker",
          "displayName": "CPAchecker stock upstream",
          "timelimit": args.time_limit,
          "hardtimelimit": args.hard_time_limit,
          "walltimelimit": args.wall_time_limit,
          "memlimit": args.memory_limit,
          "cpuCores": "4",
      },
  )
  for name, value in (
      ("--svcomp27", None),
      ("--heap", "10000M"),
      ("--benchmark", None),
      ("--timelimit", args.time_limit),
  ):
    option = ET.SubElement(xml, "option", {"name": name})
    if value:
      option.text = value
  run = ET.SubElement(xml, "rundefinition", {"name": args.name})
  tasks = ET.SubElement(run, "tasks", {"name": "C.unreach-call.Loops"})
  ET.SubElement(tasks, "includesfile").text = str(task_set)
  ET.SubElement(tasks, "propertyfile").text = str(property_file)
  tree = ET.ElementTree(xml)
  ET.indent(tree, space="  ")
  benchmark_file = output_dir / f"{args.name}.xml"
  tree.write(benchmark_file, encoding="unicode", xml_declaration=True)
  with benchmark_file.open("a", encoding="utf-8") as target:
    target.write("\n")
  print(benchmark_file)


def command_render(args):
  tasks = load_tasks(args.sv_benchmarks)
  selected = (
      sorted(tasks, key=stable_score)
      if args.calibration_per_verdict == 0
      else select_calibration(tasks, args.calibration_per_verdict)
  )
  write_benchmark(args, selected)


def parse_time(value):
  if not value:
    return None
  match = re.fullmatch(r"([0-9.]+)s", value)
  return float(match.group(1)) if match else None


def open_result(path):
  if path.suffix == ".bz2":
    return bz2.open(path, "rb")
  return path.open("rb")


def classify_result(status, category):
  normalized = status.lower()
  if category == "correct":
    return "correct_true" if normalized.startswith("true") else "correct_false"
  if category == "wrong":
    return "wrong"
  if "timeout" in normalized:
    return "timeout"
  if "out of memory" in normalized or "outofmemory" in normalized:
    return "out_of_memory"
  if category == "missing":
    return "infrastructure_or_manifest_failure"
  if category == "error":
    return "verifier_or_resource_error"
  return "unknown"


def command_summarize(args):
  result_path = Path(args.result)
  with open_result(result_path) as source:
    root = ET.parse(source).getroot()
  rows = []
  for run in root.findall("run"):
    columns = {column.attrib["title"]: column.attrib.get("value", "") for column in run.findall("column")}
    status = columns.get("status", "")
    category = columns.get("category", "")
    cpu_time = parse_time(columns.get("cputime"))
    wall_time = parse_time(columns.get("walltime"))
    classification = classify_result(status, category)
    rows.append(
        {
            "task": run.attrib.get("name", ""),
            "status": status,
            "category": category,
            "classification": classification,
            "cpu_time_seconds": cpu_time,
            "wall_time_seconds": wall_time,
            "memory_bytes": columns.get("memory", ""),
            "hard": cpu_time is not None and cpu_time > args.hard_threshold,
            "unsolved": category not in {"correct"},
        }
    )
  if len(rows) != args.expected_count:
    raise RuntimeError(
        f"Expected {args.expected_count} result rows, found {len(rows)} in {result_path}"
    )
  task_names = [row["task"] for row in rows]
  if len(set(task_names)) != len(task_names):
    raise RuntimeError("Result contains duplicate task names")
  output_dir = Path(args.output_dir)
  output_dir.mkdir(parents=True, exist_ok=True)
  fieldnames = (
      list(rows[0])
      if rows
      else [
          "task",
          "status",
          "category",
          "classification",
          "cpu_time_seconds",
          "wall_time_seconds",
          "memory_bytes",
          "hard",
          "unsolved",
      ]
  )
  for filename, subset in (
      ("results.csv", rows),
      ("hard-over-200s.csv", [row for row in rows if row["hard"]]),
      ("unsolved.csv", [row for row in rows if row["unsolved"]]),
  ):
    with (output_dir / filename).open("w", newline="", encoding="utf-8") as target:
      writer = csv.DictWriter(target, fieldnames=fieldnames)
      writer.writeheader()
      writer.writerows(subset)
  summary = {
      "source_result": str(result_path.resolve()),
      "result_sha256": sha256_file(result_path),
      "total": len(rows),
      "correct": sum(row["category"] == "correct" for row in rows),
      "correct_true": sum(row["classification"] == "correct_true" for row in rows),
      "correct_false": sum(row["classification"] == "correct_false" for row in rows),
      "wrong": sum(row["category"] == "wrong" for row in rows),
      "unknown_or_error": sum(row["category"] not in {"correct", "wrong"} for row in rows),
      "timeouts": sum(row["classification"] == "timeout" for row in rows),
      "out_of_memory": sum(row["classification"] == "out_of_memory" for row in rows),
      "verifier_or_resource_error": sum(
          row["classification"] == "verifier_or_resource_error" for row in rows
      ),
      "infrastructure_or_manifest_failure": sum(
          row["classification"] == "infrastructure_or_manifest_failure" for row in rows
      ),
      "hard_over_200s": sum(row["hard"] for row in rows),
  }
  (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
  if summary["wrong"]:
    raise RuntimeError(f"Result contains {summary['wrong']} wrong verdicts")


def add_render_arguments(parser):
  parser.add_argument("--sv-benchmarks", required=True)
  parser.add_argument("--output-dir", required=True)
  parser.add_argument("--name", required=True)
  parser.add_argument("--calibration-per-verdict", type=int, default=0)
  parser.add_argument("--time-limit", default="900 s")
  parser.add_argument("--hard-time-limit", default="960 s")
  parser.add_argument("--wall-time-limit", default="1000 s")
  parser.add_argument("--memory-limit", default="15 GB")


def main():
  parser = argparse.ArgumentParser()
  subparsers = parser.add_subparsers(dest="command", required=True)
  inventory = subparsers.add_parser("inventory")
  inventory.add_argument("--sv-benchmarks", required=True)
  inventory.add_argument("--output", required=True)
  inventory.set_defaults(function=command_inventory)
  machine = subparsers.add_parser("machine")
  machine.add_argument("--output", required=True)
  machine.set_defaults(function=command_machine)
  provenance = subparsers.add_parser("provenance")
  provenance.add_argument("--cpachecker", required=True)
  provenance.add_argument("--sv-benchmarks", required=True)
  provenance.add_argument("--bench-defs", required=True)
  provenance.add_argument("--benchexec", required=True)
  provenance.add_argument("--output", required=True)
  provenance.set_defaults(function=command_provenance)
  render = subparsers.add_parser("render")
  add_render_arguments(render)
  render.set_defaults(function=command_render)
  summarize = subparsers.add_parser("summarize")
  summarize.add_argument("--result", required=True)
  summarize.add_argument("--output-dir", required=True)
  summarize.add_argument("--hard-threshold", type=float, default=200.0)
  summarize.add_argument("--expected-count", type=int, default=EXPECTED_TASK_COUNT)
  summarize.set_defaults(function=command_summarize)
  args = parser.parse_args()
  args.function(args)


if __name__ == "__main__":
  main()
