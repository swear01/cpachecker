#!/usr/bin/env python3
"""Run pilot/baseline experiments for Vocabulary-Guided CEGAR.

The default workflow is:

  1. Discover reach-safety SV-COMP tasks from selected loop/array categories.
  2. Run stock CPAchecker as a baseline.
  3. Filter out trivial tasks by runtime/refinement count.
  4. Optionally run V-guided CPAchecker on the filtered tasks.

Results are written as CSV files under results/vguided-bench/.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
DEFAULT_BENCHMARK_ROOT = REPO.parent / "sv-benchmarks-vguided"
DEFAULT_RESULTS = REPO / "results" / "vguided-bench"
DEFAULT_CATEGORIES = (
    "c/loops",
    "c/loop-invariants",
    "c/array-examples",
    "c/array-industry-pattern",
    "c/array-reach",
    "c/loop-acceleration",
    "c/loop-crafted",
)

RESULT_RE = re.compile(r"Verification result:\s+([A-Z]+)")
REFINEMENTS_RE = re.compile(r"Number of predicate refinements:\s+([0-9]+)")
TIME_RE = re.compile(r"Time for refinement:\s+([0-9.]+)s")
LLM_INIT_RE = re.compile(r"LLM: V_0 initialized with\s+([0-9]+)\s+predicates")
LLM_FAIL_RE = re.compile(r"LLM V_0 initialization failed \(([^)]*)\)")
LLM_TIMEOUT_RE = re.compile(r"LLM V_0 initialization did not finish within\s+([0-9]+)\s+([A-Z]+)")
LLM_EMPTY_RE = re.compile(r"LLM V_0 initialization produced no predicates")


@dataclass(frozen=True)
class Task:
  category: str
  yml: Path
  program: Path
  expected: str


def java_env() -> dict[str, str]:
  env = os.environ.copy()
  bundled_jdk = Path("/home/swear01/FMPA2/external/jdk-21/jdk-21.0.10+7")
  if bundled_jdk.exists():
    env["JAVA_HOME"] = str(bundled_jdk)
    env["PATH"] = str(bundled_jdk / "bin") + os.pathsep + env.get("PATH", "")
  return env


def parse_scalar(line: str) -> str | None:
  _, value = line.split(":", 1)
  value = value.strip()
  if not value:
    return None
  if value[0] in "'\"" and value[-1] == value[0]:
    return value[1:-1]
  return value


def read_task_from_yml(root: Path, category_dir: Path, yml: Path) -> Task | None:
  text = yml.read_text(errors="replace").splitlines()
  has_reach = any("unreach-call.prp" in line for line in text)
  if not has_reach:
    return None

  input_file = None
  expected = ""
  for line in text:
    stripped = line.strip()
    if stripped.startswith("input_files:"):
      input_file = parse_scalar(stripped)
    elif stripped.startswith("expected_verdict:") and not expected:
      expected = parse_scalar(stripped) or ""

  if not input_file:
    return None
  program = yml.parent / input_file
  if not program.exists():
    return None
  return Task(
      category=str(category_dir.relative_to(root)),
      yml=yml,
      program=program,
      expected=expected,
  )


def discover_tasks(root: Path, categories: list[str]) -> list[Task]:
  tasks: list[Task] = []
  for category in categories:
    category_dir = root / category
    if not category_dir.exists():
      continue
    for yml in sorted(category_dir.glob("*.yml")):
      task = read_task_from_yml(root, category_dir, yml)
      if task is not None:
        tasks.append(task)
  return tasks


def parse_run_output(output: str) -> tuple[str, int, float]:
  result_match = RESULT_RE.search(output)
  result = result_match.group(1) if result_match else "UNKNOWN"

  refinements_match = REFINEMENTS_RE.search(output)
  refinements = int(refinements_match.group(1)) if refinements_match else 0

  refinement_time_match = TIME_RE.search(output)
  refinement_time = float(refinement_time_match.group(1)) if refinement_time_match else 0.0
  return result, refinements, refinement_time


def ensure_text(output: str | bytes | None) -> str:
  if output is None:
    return ""
  if isinstance(output, bytes):
    return output.decode(errors="replace")
  return output


def csv_cell(value: object) -> str:
  text = "" if value is None else str(value)
  return " ".join(text.split())


def safe_log_name(task: Task) -> str:
  name = f"{task.category}_{task.program.name}".replace("/", "_")
  return re.sub(r"[^A-Za-z0-9_.+-]", "_", name)


def parse_llm_status(output: str, mode: str) -> tuple[str, str, str]:
  if mode != "vguided":
    return "NOT_APPLICABLE", "", ""

  init_match = LLM_INIT_RE.search(output)
  if init_match:
    return "LLM_INIT_OK", init_match.group(1), ""

  fail_match = LLM_FAIL_RE.search(output)
  if fail_match:
    return "LLM_INIT_FAILED", "", fail_match.group(1)

  timeout_match = LLM_TIMEOUT_RE.search(output)
  if timeout_match:
    return "LLM_INIT_TIMEOUT", "", f"{timeout_match.group(1)} {timeout_match.group(2)}"

  if LLM_EMPTY_RE.search(output):
    return "LLM_INIT_EMPTY", "0", ""

  if "LLM: initializing V_0 from source code" in output:
    return "LLM_INIT_STARTED_NO_RESULT", "", ""

  return "LLM_NOT_OBSERVED", "", ""


def run_cpachecker(
    task: Task, mode: str, timelimit: int, heap: str, log_dir: Path
) -> dict[str, str]:
  cmd = [
      str(REPO / "scripts" / "cpa.sh"),
      "--heap",
      heap,
      "--predicateAnalysis",
      "--stats",
      "--no-output-files",
      "--timelimit",
      f"{timelimit}s",
      "--spec",
      str(REPO / "config" / "specification" / "default.spc"),
  ]
  if mode == "vguided":
    cmd.extend(["--option", "cpa.predicate.refinement.useVocabularyGuide=true"])
  cmd.append(str(task.program))

  start = time.monotonic()
  timed_out = False
  try:
    completed = subprocess.run(
        cmd,
        cwd=REPO,
        env=java_env(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timelimit + 60,
        check=False,
    )
    output = ensure_text(completed.stdout)
    returncode = completed.returncode
  except subprocess.TimeoutExpired as e:
    timed_out = True
    output = ensure_text(e.stdout)
    returncode = 124
  wall = time.monotonic() - start

  result, refinements, refinement_time = parse_run_output(output)
  if timed_out:
    result = "TIMEOUT"
  log_dir.mkdir(parents=True, exist_ok=True)
  log_file = log_dir / f"{safe_log_name(task)}.log"
  log_file.write_text(output, errors="replace")
  llm_status, llm_predicates, llm_error = parse_llm_status(output, mode)

  return {
      "mode": mode,
      "category": task.category,
      "program": str(task.program),
      "yml": str(task.yml),
      "expected": task.expected,
      "result": result,
      "returncode": str(returncode),
      "wall_s": f"{wall:.3f}",
      "predicate_refinements": str(refinements),
      "refinement_time_s": f"{refinement_time:.3f}",
      "llm_status": llm_status,
      "llm_predicates": llm_predicates,
      "llm_error": csv_cell(llm_error),
      "log_file": str(log_file),
  }


def run_tasks_parallel(
    tasks: list[Task],
    mode: str,
    timelimit: int,
    heap: str,
    jobs: int,
    output_csv: Path,
    existing_rows: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
  rows: list[dict[str, str]] = list(existing_rows or [])
  total = len(tasks)
  output_csv.parent.mkdir(parents=True, exist_ok=True)
  log_dir = output_csv.parent / f"{mode}-logs"
  with ThreadPoolExecutor(max_workers=jobs) as executor:
    future_to_task = {
        executor.submit(run_cpachecker, task, mode, timelimit, heap, log_dir): (idx, task)
        for idx, task in enumerate(tasks, start=1)
    }
    for future in as_completed(future_to_task):
      idx, task = future_to_task[future]
      try:
        row = future.result()
      except Exception as e:  # keep long benchmark runs robust
        row = {
            "mode": mode,
            "category": task.category,
            "program": str(task.program),
            "yml": str(task.yml),
            "expected": task.expected,
            "result": "HARNESS_ERROR",
            "returncode": "-1",
            "wall_s": "0.000",
            "predicate_refinements": "0",
            "refinement_time_s": "0.000",
            "llm_status": "HARNESS_ERROR",
            "llm_predicates": "",
            "llm_error": csv_cell(e),
            "log_file": "",
        }
        print(f"[{mode} {idx}/{total}] HARNESS_ERROR {task.program}: {e}", flush=True)
      rows.append(row)
      write_rows(output_csv, rows)
      print(
          f"[{mode} {idx}/{total}] {row['result']} wall={row['wall_s']}s "
          f"refs={row['predicate_refinements']} llm={row.get('llm_status', '')} {task.program}",
          flush=True,
      )
  rows.sort(key=lambda row: row["program"])
  write_rows(output_csv, rows)
  return rows


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  fields = [
      "mode",
      "category",
      "program",
      "yml",
      "expected",
      "result",
      "returncode",
      "wall_s",
      "predicate_refinements",
      "refinement_time_s",
      "llm_status",
      "llm_predicates",
      "llm_error",
      "log_file",
  ]
  with path.open("w", newline="") as out:
    writer = csv.DictWriter(out, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)


def read_baseline(path: Path) -> list[dict[str, str]]:
  with path.open(newline="") as inp:
    return list(csv.DictReader(inp))


def merge_existing_rows(
    path: Path, tasks: list[Task], resume: bool
) -> tuple[list[dict[str, str]], list[Task]]:
  if not resume or not path.exists():
    return [], tasks
  existing = read_baseline(path)
  done = {row["program"] for row in existing}
  remaining = [task for task in tasks if str(task.program) not in done]
  return existing, remaining


def filter_baseline(
    rows: list[dict[str, str]], fast_threshold: float, min_refinements: int
) -> list[dict[str, str]]:
  selected = []
  for row in rows:
    try:
      wall = float(row["wall_s"])
      refinements = int(row["predicate_refinements"])
    except ValueError:
      continue
    if row["result"] == "TIMEOUT":
      continue
    if wall >= fast_threshold and refinements >= min_refinements:
      selected.append(row)
  return selected


def task_by_program(tasks: list[Task]) -> dict[str, Task]:
  return {str(t.program): t for t in tasks}


def main() -> int:
  parser = argparse.ArgumentParser()
  parser.add_argument("--benchmark-root", type=Path, default=DEFAULT_BENCHMARK_ROOT)
  parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
  parser.add_argument("--categories", nargs="*", default=list(DEFAULT_CATEGORIES))
  parser.add_argument("--phase", choices=["list", "pilot", "compare", "both"], default="pilot")
  parser.add_argument("--timelimit", type=int, default=60)
  parser.add_argument("--heap", default="4000M")
  parser.add_argument(
      "--jobs",
      type=int,
      default=1,
      help="parallel CPAchecker runs; use 0 for os.cpu_count()",
  )
  parser.add_argument("--fast-threshold", type=float, default=3.0)
  parser.add_argument("--min-refinements", type=int, default=2)
  parser.add_argument("--limit", type=int, default=0)
  parser.add_argument("--resume", action="store_true", help="skip tasks already present in output CSV")
  parser.add_argument(
      "--selection-csv",
      type=Path,
      help="CSV file with selected baseline rows to use for compare phase",
  )
  args = parser.parse_args()

  tasks = discover_tasks(args.benchmark_root, args.categories)
  if args.limit > 0:
    tasks = tasks[: args.limit]
  jobs = os.cpu_count() if args.jobs == 0 else args.jobs
  jobs = max(1, jobs or 1)

  if args.phase == "list":
    for task in tasks:
      print(f"{task.category},{task.expected},{task.program}")
    print(f"tasks={len(tasks)}", file=sys.stderr)
    return 0

  baseline_csv = args.results_dir / "baseline_stock.csv"
  if args.phase in ("pilot", "both"):
    existing, remaining = merge_existing_rows(baseline_csv, tasks, args.resume)
    if existing:
      print(f"[stock] resume: keeping {len(existing)} completed rows, remaining {len(remaining)}")
    run_tasks_parallel(
        remaining,
        "stock",
        args.timelimit,
        args.heap,
        jobs,
        baseline_csv,
        existing_rows=existing,
    )

  if args.phase in ("compare", "both"):
    if args.selection_csv:
      selected_rows = read_baseline(args.selection_csv)
    else:
      baseline_rows = read_baseline(baseline_csv)
      selected_rows = filter_baseline(baseline_rows, args.fast_threshold, args.min_refinements)
      selected_csv = args.results_dir / "selected_from_baseline.csv"
      write_rows(selected_csv, selected_rows)

    tasks_map = task_by_program(tasks)
    selected_tasks = [tasks_map[row["program"]] for row in selected_rows if row["program"] in tasks_map]
    run_tasks_parallel(
        selected_tasks,
        "vguided",
        args.timelimit,
        args.heap,
        jobs,
        args.results_dir / "vguided.csv",
    )

  return 0


if __name__ == "__main__":
  raise SystemExit(main())
