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
import statistics
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


P_CORE_CPUS = (0, 2, 4, 6, 8, 10, 12, 14)
EXPECTED_TASK_COUNT = 764
CALIBRATION_TASKS = (
    "c/loop-industry-pattern/aiob_4.c.v+lhb-reducer.yml",
    "c/loop-invariants/bin-suffix-5.yml",
    "c/loop-invgen/id_trans.yml",
    "c/loops/count_up_down-2.yml",
    "c/loops/trex01-1.yml",
    "c/loops/trex03-1.yml",
    "c/loops/trex04.yml",
    "c/nla-digbench-scaling/cohencu-ll_unwindbound10.yml",
    "c/nla-digbench-scaling/ps3-ll_valuebound50.yml",
    "c/nla-digbench-scaling/sqrt1-ll_unwindbound5.yml",
)


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


def git_archive_sha256(repo):
  digest = hashlib.sha256()
  process = subprocess.Popen(
      ["git", "-C", str(repo), "archive", "--format=tar", "HEAD"],
      stdout=subprocess.PIPE,
  )
  if process.stdout is None:
    raise RuntimeError("git archive did not provide stdout")
  for chunk in iter(lambda: process.stdout.read(1024 * 1024), b""):
    digest.update(chunk)
  return_code = process.wait()
  if return_code:
    raise RuntimeError(f"git archive failed with exit code {return_code}: {repo}")
  return digest.hexdigest()


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
  seen = set()
  for set_name in ("Loops.set", "VerifyThis-Loops.set"):
    for task in expand_set(root, set_name):
      metadata = task_metadata(task)
      if metadata is None:
        continue
      rel_task = task.relative_to(root).as_posix()
      if rel_task in seen:
        raise ValueError(f"Task occurs in more than one benchmark set: {rel_task}")
      seen.add(rel_task)
      sources = [(task.parent / source).resolve() for source in metadata["input_files"]]
      tasks.append(
          {
              "task": rel_task,
              "task_path": task,
              "sources": sources,
              "benchmark_set": Path(set_name).stem,
              **metadata,
          }
      )
  tasks.sort(key=lambda item: item["task"])
  if len(tasks) != EXPECTED_TASK_COUNT:
    raise ValueError(f"Expected {EXPECTED_TASK_COUNT} tasks, found {len(tasks)}")
  return tasks


def corpus_digest(tasks):
  digest = hashlib.sha256()
  for task in tasks:
    digest.update(task["task"].encode("utf-8"))
    digest.update(b"\0")
    digest.update(task["benchmark_set"].encode("utf-8"))
    digest.update(b"\0")
    for index, path in enumerate([task["task_path"], *task["sources"]]):
      digest.update(str(index).encode("ascii"))
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


def directory_digest(root):
  root = Path(root).resolve()
  digest = hashlib.sha256()
  entries = sorted(root.rglob("*"), key=lambda path: path.relative_to(root).as_posix())
  for path in entries:
    digest.update(path.relative_to(root).as_posix().encode("utf-8"))
    digest.update(b"\0")
    if path.is_symlink():
      digest.update(b"link\0")
      digest.update(os.readlink(path).encode("utf-8"))
    elif path.is_file():
      digest.update(b"file\0")
      digest.update(bytes.fromhex(sha256_file(path)))
    elif path.is_dir():
      digest.update(b"directory\0")
    else:
      raise RuntimeError(f"Unsupported filesystem entry in {root}: {path}")
  return {"entry_count": len(entries), "sha256": digest.hexdigest()}


def logical_lines(path):
  pending = ""
  for raw_line in path.read_text(encoding="utf-8").splitlines():
    line = pending + raw_line.strip()
    if line.endswith("\\"):
      pending = line[:-1].rstrip() + " "
    else:
      yield line
      pending = ""
  if pending:
    raise RuntimeError(f"Unterminated continuation in configuration file: {path}")


def resolve_config_reference(root, current_path, reference):
  for candidate in (
      (current_path.parent / reference).resolve(),
      (root / "config" / reference).resolve(),
  ):
    try:
      candidate.relative_to(root)
    except ValueError as error:
      raise RuntimeError(
          f"Configuration reference escapes the CPAchecker tree: {reference!r}"
      ) from error
    if candidate.is_file():
      return candidate
  raise FileNotFoundError(f"Configuration reference {reference!r} from {current_path}")


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
    for line in logical_lines(path):
      if line.startswith("#include "):
        included = line[len("#include ") :].partition("#")[0].strip()
        pending.append(resolve_config_reference(root, path, included))
      elif line and not line.startswith(("#", "//")):
        value = line.partition("=")[2].partition("#")[0]
        for reference in re.findall(r"[A-Za-z0-9_./+~-]+\.(?:properties|spc)", value):
          pending.append(resolve_config_reference(root, path, reference))
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
  java_home = Path(os.environ["JAVA_HOME"]).resolve()
  java_version = subprocess.check_output(
      [str(java_home / "bin/java"), "-version"], text=True, stderr=subprocess.STDOUT
  ).splitlines()[0]
  manifest = {
      "stage": "SV-COMP-2027 snapshot baseline v1 (frozen 2026-07-22)",
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
      "tracked_source_archive_sha256": git_archive_sha256(cpachecker),
      "jdk": {
          "version": java_version,
          "home": str(java_home),
          **directory_digest(java_home),
      },
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
            "benchmark_set": task["benchmark_set"],
            "data_model": task["data_model"],
            "input_files": [
                str(path.relative_to(Path(args.sv_benchmarks).resolve()))
                for path in task["sources"]
            ],
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
  if per_verdict != 5:
    raise ValueError("Baseline v1 calibration is fixed at five tasks per verdict")
  tasks_by_name = {task["task"]: task for task in tasks}
  missing = [task for task in CALIBRATION_TASKS if task not in tasks_by_name]
  if missing:
    raise ValueError(f"Pinned calibration tasks are missing: {missing}")
  selected = [tasks_by_name[task] for task in CALIBRATION_TASKS]
  for verdict in ("true", "false"):
    count = sum(task["expected_verdict"] == verdict for task in selected)
    if count != per_verdict:
      raise ValueError(
          f"Pinned calibration has {count} {verdict} tasks, expected {per_verdict}"
      )
  return sorted(selected, key=lambda task: task["task"])


def write_benchmark(args, selected):
  output_dir = Path(args.output_dir).resolve()
  output_dir.mkdir(parents=True, exist_ok=True)
  task_set = output_dir / f"{args.name}.set"
  sv_root = Path(args.sv_benchmarks).resolve()
  task_set.write_text(
      "\n".join(str(sv_root / task["task"]) for task in selected) + "\n", encoding="utf-8"
  )
  selection_manifest = {
      "task_count": len(selected),
      "tasks": [
          {
              "task": task["task"],
              "benchmark_set": task["benchmark_set"],
              "expected_verdict": task["expected_verdict"],
              "data_model": task["data_model"],
              "task_sha256": sha256_file(task["task_path"]),
          }
          for task in selected
      ],
  }
  (output_dir / f"{args.name}.manifest.json").write_text(
      json.dumps(selection_manifest, indent=2) + "\n", encoding="utf-8"
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
  ET.SubElement(xml, "resultfiles").text = "**/witness.*"
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
  indent_xml(xml)
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


def parse_bytes(value):
  if not value:
    return None
  match = re.fullmatch(r"([0-9.]+)([KMGT]?B)", value)
  if not match:
    return None
  multipliers = {"B": 1, "KB": 1000, "MB": 1000**2, "GB": 1000**3, "TB": 1000**4}
  return int(float(match.group(1)) * multipliers[match.group(2)])


def distribution(values):
  ordered = sorted(value for value in values if value is not None)
  if not ordered:
    return {"count": 0, "min": None, "median": None, "p95": None, "max": None, "mean": None}
  p95_index = max(0, (95 * len(ordered) + 99) // 100 - 1)
  return {
      "count": len(ordered),
      "min": ordered[0],
      "median": statistics.median(ordered),
      "p95": ordered[p95_index],
      "max": ordered[-1],
      "mean": sum(ordered) / len(ordered),
  }


def load_task_manifest(path):
  manifest = json.loads(Path(path).read_text(encoding="utf-8"))
  tasks = manifest.get("tasks")
  if not isinstance(tasks, list) or manifest.get("task_count") != len(tasks):
    raise RuntimeError("Task manifest has an invalid task count")
  by_name = {}
  for task in tasks:
    name = task.get("task")
    if not isinstance(name, str) or name in by_name:
      raise RuntimeError("Task manifest contains a missing or duplicate task name")
    if task.get("expected_verdict") not in {"true", "false"}:
      raise RuntimeError(f"Task manifest has no binary expected verdict for {name}")
    if not isinstance(task.get("benchmark_set"), str) or not task["benchmark_set"]:
      raise RuntimeError(f"Task manifest has no benchmark-set origin for {name}")
    by_name[name] = task
  return by_name


def match_result_task(result_name, manifest):
  normalized = result_name.replace("\\", "/")
  matches = [name for name in manifest if normalized == name or normalized.endswith("/" + name)]
  if len(matches) != 1:
    raise RuntimeError(f"Result task does not match exactly one manifest entry: {result_name}")
  return matches[0]


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


def parse_result_rows(result_path, manifest, hard_threshold):
  result_path = Path(result_path)
  with open_result(result_path) as source:
    root = ET.parse(source).getroot()
  rows = []
  for run in root.findall("run"):
    task_name = match_result_task(run.attrib.get("name", ""), manifest)
    task = manifest[task_name]
    result_expected = run.attrib.get("expectedVerdict", "").partition("(")[0].lower()
    if result_expected and result_expected != task["expected_verdict"]:
      raise RuntimeError(
          f"BenchExec expected verdict disagrees with manifest for {task_name}: "
          f"{result_expected} != {task['expected_verdict']}"
      )
    property_file = run.attrib.get("propertyFile", "")
    if property_file and not property_file.replace("\\", "/").endswith("/unreach-call.prp"):
      raise RuntimeError(f"Unexpected property file for {task_name}: {property_file}")
    columns = {
        column.attrib["title"]: column.attrib.get("value", "")
        for column in run.findall("column")
    }
    status = columns.get("status", "")
    category = columns.get("category", "")
    cpu_time = parse_time(columns.get("cputime"))
    wall_time = parse_time(columns.get("walltime"))
    classification = classify_result(status, category)
    rows.append(
        {
            "task": task_name,
            "benchmark_set": task["benchmark_set"],
            "expected_verdict": task["expected_verdict"],
            "status": status,
            "category": category,
            "classification": classification,
            "cpu_time_seconds": cpu_time,
            "wall_time_seconds": wall_time,
            "memory_bytes": parse_bytes(columns.get("memory")),
            "hard": cpu_time is not None and cpu_time > hard_threshold,
            "unsolved": category not in {"correct"},
        }
    )
  if len(rows) != len(manifest):
    raise RuntimeError(
        f"Expected {len(manifest)} result rows, found {len(rows)} in {result_path}"
    )
  task_names = [row["task"] for row in rows]
  if len(set(task_names)) != len(task_names):
    raise RuntimeError("Result contains duplicate task names")
  if set(task_names) != set(manifest):
    missing = sorted(set(manifest) - set(task_names))
    unexpected = sorted(set(task_names) - set(manifest))
    raise RuntimeError(f"Result/manifest task mismatch; missing={missing}, unexpected={unexpected}")
  return rows


def command_summarize(args):
  manifest = load_task_manifest(args.task_manifest)
  result_path = Path(args.result)
  rows = parse_result_rows(result_path, manifest, args.hard_threshold)
  output_dir = Path(args.output_dir)
  output_dir.mkdir(parents=True, exist_ok=True)
  fieldnames = (
      list(rows[0])
      if rows
      else [
          "task",
          "benchmark_set",
          "expected_verdict",
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
      "distributions": {
          "cpu_time_seconds": distribution(row["cpu_time_seconds"] for row in rows),
          "wall_time_seconds": distribution(row["wall_time_seconds"] for row in rows),
          "memory_bytes": distribution(row["memory_bytes"] for row in rows),
      },
      "by_benchmark_set": {},
  }
  for benchmark_set in sorted({row["benchmark_set"] for row in rows}):
    subset = [row for row in rows if row["benchmark_set"] == benchmark_set]
    summary["by_benchmark_set"][benchmark_set] = {
        "total": len(subset),
        "correct": sum(row["category"] == "correct" for row in subset),
        "wrong": sum(row["category"] == "wrong" for row in subset),
        "unsolved": sum(row["unsolved"] for row in subset),
        "hard_over_200s": sum(row["hard"] for row in subset),
        "cpu_time_seconds": distribution(row["cpu_time_seconds"] for row in subset),
        "wall_time_seconds": distribution(row["wall_time_seconds"] for row in subset),
        "memory_bytes": distribution(row["memory_bytes"] for row in subset),
    }
  (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
  if summary["wrong"]:
    raise RuntimeError(f"Result contains {summary['wrong']} wrong verdicts")


def relative_median_absolute_deviation(values):
  median = statistics.median(values)
  absolute_deviation = statistics.median(abs(value - median) for value in values)
  return None if median == 0 else absolute_deviation / median


def command_calibration_summary(args):
  if len(args.result) < 2:
    raise RuntimeError("Calibration summary requires at least two repeated result files")
  manifest = load_task_manifest(args.task_manifest)
  parsed = []
  for result in args.result:
    rows = parse_result_rows(result, manifest, hard_threshold=200.0)
    not_correct = [row["task"] for row in rows if row["category"] != "correct"]
    if not_correct:
      raise RuntimeError(f"Calibration contains non-correct runs in {result}: {not_correct}")
    parsed.append({row["task"]: row for row in rows})
  tasks = []
  for task in sorted(manifest):
    cpu_values = [repetition[task]["cpu_time_seconds"] for repetition in parsed]
    wall_values = [repetition[task]["wall_time_seconds"] for repetition in parsed]
    if any(value is None for value in cpu_values + wall_values):
      raise RuntimeError(f"Calibration lacks CPU or wall time for {task}")
    tasks.append(
        {
            "task": task,
            "cpu_time_seconds": distribution(cpu_values),
            "cpu_relative_mad": relative_median_absolute_deviation(cpu_values),
            "wall_time_seconds": distribution(wall_values),
            "wall_relative_mad": relative_median_absolute_deviation(wall_values),
        }
    )
  output = {
      "repetitions": len(parsed),
      "task_count": len(manifest),
      "results": [
          {"path": str(Path(result).resolve()), "sha256": sha256_file(Path(result))}
          for result in args.result
      ],
      "max_cpu_relative_mad": max(
          (task["cpu_relative_mad"] for task in tasks if task["cpu_relative_mad"] is not None),
          default=None,
      ),
      "max_wall_relative_mad": max(
          (task["wall_relative_mad"] for task in tasks if task["wall_relative_mad"] is not None),
          default=None,
      ),
      "tasks": tasks,
  }
  Path(args.output).write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")


def clone_xml_element(element):
  return ET.fromstring(ET.tostring(element, encoding="unicode"))


def indent_xml(element, level=0):
  indentation = "\n" + level * "  "
  child_indentation = "\n" + (level + 1) * "  "
  if len(element):
    if not element.text or not element.text.strip():
      element.text = child_indentation
    for child in element:
      indent_xml(child, level + 1)
      if not child.tail or not child.tail.strip():
        child.tail = child_indentation
    child.tail = indentation
  elif level and (not element.tail or not element.tail.strip()):
    element.tail = indentation


def write_validation_benchmark(
    output_dir,
    name,
    tasks,
    template_path,
    sv_benchmarks,
    witness_run_directory,
):
  template = ET.parse(template_path).getroot()
  if template.tag != "benchmark" or template.attrib.get("tool") != "cpachecker":
    raise RuntimeError(f"Unexpected witness-validator definition: {template_path}")
  xml = ET.Element("benchmark", dict(template.attrib))
  for child in template:
    if child.tag in {"resultfiles", "option"}:
      xml.append(clone_xml_element(child))
  run = ET.SubElement(xml, "rundefinition", {"name": name})
  witness_pattern = str(witness_run_directory / "${taskdef_name}" / "witness.yml")
  ET.SubElement(run, "requiredfiles").text = witness_pattern
  witness_option = ET.SubElement(run, "option", {"name": "--witness"})
  witness_option.text = witness_pattern
  task_set = output_dir / f"{name}.set"
  sv_root = Path(sv_benchmarks).resolve()
  task_set.write_text(
      "\n".join(str(sv_root / task["task"]) for task in tasks) + "\n", encoding="utf-8"
  )
  task_group = ET.SubElement(run, "tasks", {"name": "C.unreach-call.Loops"})
  ET.SubElement(task_group, "includesfile").text = str(task_set)
  ET.SubElement(task_group, "propertyfile").text = str(
      sv_root / "c/properties/unreach-call.prp"
  )
  tree = ET.ElementTree(xml)
  indent_xml(xml)
  benchmark_path = output_dir / f"{name}.xml"
  tree.write(benchmark_path, encoding="unicode", xml_declaration=True)
  with benchmark_path.open("a", encoding="utf-8") as target:
    target.write("\n")
  selection_manifest = {
      "task_count": len(tasks),
      "tasks": tasks,
  }
  manifest_path = output_dir / f"{name}.manifest.json"
  manifest_path.write_text(
      json.dumps(selection_manifest, indent=2) + "\n", encoding="utf-8"
  )
  return benchmark_path, manifest_path


def command_render_validation(args):
  manifest = load_task_manifest(args.task_manifest)
  rows = parse_result_rows(Path(args.result), manifest, hard_threshold=200.0)
  correct_rows = [row for row in rows if row["category"] == "correct"]
  result_files = Path(args.result_files).resolve()
  run_directories = [path for path in result_files.iterdir() if path.is_dir()]
  if len(run_directories) != 1:
    raise RuntimeError(
        f"Expected exactly one run-definition directory in {result_files}, "
        f"found {len(run_directories)}"
    )
  witness_run_directory = run_directories[0]
  basenames = [Path(row["task"]).name for row in correct_rows]
  if len(basenames) != len(set(basenames)):
    raise RuntimeError("Correct result tasks do not have unique task-definition basenames")
  witnesses = []
  for row in correct_rows:
    witness = witness_run_directory / Path(row["task"]).name / "witness.yml"
    if not witness.is_file() or witness.stat().st_size == 0:
      raise RuntimeError(f"Missing or empty YAML witness for correct result: {row['task']}")
    witnesses.append(
        {
            "task": row["task"],
            "expected_verdict": row["expected_verdict"],
            "path": str(witness),
            "sha256": sha256_file(witness),
        }
    )
  output_dir = Path(args.output_dir).resolve()
  output_dir.mkdir(parents=True, exist_ok=True)
  validator_root = Path(args.bench_defs).resolve() / "benchmark-defs"
  generated = {}
  for expected_verdict, kind in (("true", "correctness"), ("false", "violation")):
    selected = [
        manifest[row["task"]]
        for row in correct_rows
        if row["expected_verdict"] == expected_verdict
    ]
    if not selected:
      raise RuntimeError(f"No correct {expected_verdict.upper()} results to validate")
    template_path = validator_root / f"cpachecker-validate-{kind}-witnesses-v2.xml"
    if not template_path.is_file():
      raise FileNotFoundError(template_path)
    benchmark_path, selection_manifest = write_validation_benchmark(
        output_dir,
        f"baseline-v1-{kind}-witness-validation",
        selected,
        template_path,
        args.sv_benchmarks,
        witness_run_directory,
    )
    generated[kind] = {
        "official_template": str(template_path),
        "official_template_sha256": sha256_file(template_path),
        "benchmark": str(benchmark_path),
        "benchmark_sha256": sha256_file(benchmark_path),
        "task_manifest": str(selection_manifest),
        "task_count": len(selected),
    }
  validation_manifest = {
      "source_result": str(Path(args.result).resolve()),
      "source_result_sha256": sha256_file(Path(args.result)),
      "result_files": str(result_files),
      "source_rundefinition": witness_run_directory.name,
      "correct_result_count": len(correct_rows),
      "unvalidated_unsolved_count": len(rows) - len(correct_rows),
      "generated": generated,
      "witnesses": witnesses,
  }
  Path(args.output).write_text(
      json.dumps(validation_manifest, indent=2) + "\n", encoding="utf-8"
  )


def command_validation_summary(args):
  specifications = (
      ("correctness", "true", args.correctness_result, args.correctness_manifest),
      ("violation", "false", args.violation_result, args.violation_manifest),
  )
  output = {"validators": {}, "validated_total": 0, "failed_total": 0}
  failures = []
  for kind, expected_verdict, result, manifest_path in specifications:
    manifest = load_task_manifest(manifest_path)
    wrong_partition = [
        task
        for task, metadata in manifest.items()
        if metadata["expected_verdict"] != expected_verdict
    ]
    if wrong_partition:
      raise RuntimeError(f"{kind} validation manifest has wrong-verdict tasks: {wrong_partition}")
    rows = parse_result_rows(Path(result), manifest, hard_threshold=200.0)
    failed = [row for row in rows if row["category"] != "correct"]
    failures.extend(f"{kind}:{row['task']}" for row in failed)
    output["validators"][kind] = {
        "source_result": str(Path(result).resolve()),
        "result_sha256": sha256_file(Path(result)),
        "task_count": len(rows),
        "validated": len(rows) - len(failed),
        "failed": len(failed),
        "cpu_time_seconds": distribution(row["cpu_time_seconds"] for row in rows),
        "wall_time_seconds": distribution(row["wall_time_seconds"] for row in rows),
        "memory_bytes": distribution(row["memory_bytes"] for row in rows),
    }
    output["validated_total"] += len(rows) - len(failed)
    output["failed_total"] += len(failed)
  output["failures"] = failures
  Path(args.output).write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
  if failures:
    raise RuntimeError(f"Witness validation failed for {len(failures)} tasks")


def command_artifact_manifest(args):
  root = Path(args.root).resolve()
  output = Path(args.output).resolve()
  files = [
      path
      for path in root.rglob("*")
      if path.is_file() and path.resolve() != output and ".git" not in path.parts
  ]
  entries = []
  aggregate = hashlib.sha256()
  for path in sorted(files):
    relative = path.relative_to(root).as_posix()
    digest = sha256_file(path)
    entries.append({"path": relative, "size_bytes": path.stat().st_size, "sha256": digest})
    aggregate.update(relative.encode("utf-8"))
    aggregate.update(b"\0")
    aggregate.update(bytes.fromhex(digest))
  manifest = {
      "root": str(root),
      "file_count": len(entries),
      "aggregate_sha256": aggregate.hexdigest(),
      "files": entries,
  }
  output.parent.mkdir(parents=True, exist_ok=True)
  output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def command_directory_digest(args):
  print(json.dumps(directory_digest(args.root), sort_keys=True))


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
  summarize.add_argument("--task-manifest", required=True)
  summarize.add_argument("--output-dir", required=True)
  summarize.add_argument("--hard-threshold", type=float, default=200.0)
  summarize.set_defaults(function=command_summarize)
  calibration = subparsers.add_parser("calibration-summary")
  calibration.add_argument("--result", action="append", required=True)
  calibration.add_argument("--task-manifest", required=True)
  calibration.add_argument("--output", required=True)
  calibration.set_defaults(function=command_calibration_summary)
  render_validation = subparsers.add_parser("render-validation")
  render_validation.add_argument("--result", required=True)
  render_validation.add_argument("--task-manifest", required=True)
  render_validation.add_argument("--result-files", required=True)
  render_validation.add_argument("--sv-benchmarks", required=True)
  render_validation.add_argument("--bench-defs", required=True)
  render_validation.add_argument("--output-dir", required=True)
  render_validation.add_argument("--output", required=True)
  render_validation.set_defaults(function=command_render_validation)
  validation = subparsers.add_parser("validation-summary")
  validation.add_argument("--correctness-result", required=True)
  validation.add_argument("--correctness-manifest", required=True)
  validation.add_argument("--violation-result", required=True)
  validation.add_argument("--violation-manifest", required=True)
  validation.add_argument("--output", required=True)
  validation.set_defaults(function=command_validation_summary)
  directory = subparsers.add_parser("directory-digest")
  directory.add_argument("--root", required=True)
  directory.set_defaults(function=command_directory_digest)
  artifacts = subparsers.add_parser("artifact-manifest")
  artifacts.add_argument("--root", required=True)
  artifacts.add_argument("--output", required=True)
  artifacts.set_defaults(function=command_artifact_manifest)
  args = parser.parse_args()
  args.function(args)


if __name__ == "__main__":
  main()
