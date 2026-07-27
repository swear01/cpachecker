#!/usr/bin/env python3

# This file is part of CPAchecker,
# a tool for configurable software verification:
# https://cpachecker.sosy-lab.org
#
# SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>
#
# SPDX-License-Identifier: Apache-2.0

import copy
import collections
import csv
import importlib.util
import json
import random
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace


SPEC = importlib.util.spec_from_file_location("dataset", Path(__file__).with_name("dataset.py"))
dataset = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dataset)


class DatasetTest(unittest.TestCase):

  def test_family_cap_is_deterministic_and_stratified(self):
    candidates = [
        {
            "task": f"c/family/{seed}-{verdict}-{index}.yml",
            "family": "family",
            "seed_class": seed,
            "expected_verdict": verdict,
        }
        for seed in ("hard_solved_seed", "unsolved_seed")
        for verdict in ("true", "false")
        for index in range(5)
    ]

    first = dataset.family_cap(candidates, 2)
    second = dataset.family_cap(reversed(candidates), 2)

    self.assertEqual(first, second)
    self.assertEqual(len(first), 8)

  def test_repeated_classification_separates_wrong_and_mixed(self):
    hard = [
        {"category": "correct", "cpu_time_seconds": 201.0},
        {"category": "correct", "cpu_time_seconds": 205.0},
    ]
    unsolved = [
        {
            "category": "error",
            "classification": "timeout",
            "cpu_time_seconds": 900.0,
        },
        {
            "category": "unknown",
            "classification": "out_of_memory",
            "cpu_time_seconds": 900.0,
        },
    ]
    self.assertEqual(dataset.classify_repetitions(hard, 200), "stable_hard_solved")
    self.assertEqual(dataset.classify_repetitions(unsolved, 200), "stable_unsolved")
    for status in ("ERROR", "EXCEPTION", "segmentation fault"):
      with self.subTest(status=status):
        verifier_failure = [
            {
                "status": status,
                "category": "error",
                "classification": "verifier_or_resource_error",
            }
        ] * 2
        self.assertEqual(
            dataset.classify_repetitions(verifier_failure, 200),
            "verifier_failure_quarantine",
        )
    self.assertEqual(
        dataset.classify_repetitions([hard[0], unsolved[0]], 200), "mixed"
    )
    self.assertEqual(
        dataset.classify_repetitions([hard[0], {"category": "wrong"}], 200),
        "wrong_quarantine",
    )
    self.assertEqual(
        dataset.classify_repetitions(
            [
                {"category": "missing", "classification": "infrastructure_or_manifest_failure"},
                {"category": "missing", "classification": "infrastructure_or_manifest_failure"},
            ],
            200,
        ),
        "infrastructure_failure",
    )

  def test_external_inventory_requires_one_source_loop_error_call_and_ground_truth(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      case = root / "Array_UF4"
      case.mkdir()
      (case / "main.c").write_text(
          "extern void __VERIFIER_error(void);\n"
          "int main(void) { while (1) { __VERIFIER_error(); } }\n",
          encoding="utf-8",
      )
      (case / "test.desc").write_text(
          "CORE\nmain.c\n\n^VERIFICATION SUCCESSFUL$\n", encoding="utf-8"
      )

      rows, excluded = dataset.desc_inventory("cbmc", root, "test.desc")

      self.assertEqual(len(rows), 1)
      self.assertEqual(rows[0]["expected_verdict"], "true")
      self.assertEqual(rows[0]["family"], "Array_UF")
      self.assertEqual(excluded, {})

  def test_validate_rejects_changed_source(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      (root / "task.yml").write_text("task\n", encoding="utf-8")
      (root / "source.c").write_text("source\n", encoding="utf-8")
      manifest = {
          "task_count": 1,
          "tasks": [
              {
                  "task": "external/test.yml",
                  "source": "external",
                  "task_path": "task.yml",
                  "task_sha256": dataset.baseline.sha256_file(root / "task.yml"),
                  "source_paths": ["source.c"],
                  "source_sha256": [dataset.baseline.sha256_file(root / "source.c")],
              }
          ],
      }
      manifest_path = root / "manifest.json"
      import json

      manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
      (root / "source.c").write_text("changed\n", encoding="utf-8")

      with self.assertRaisesRegex(RuntimeError, "hash mismatch"):
        dataset.validate_manifest(manifest_path, root)

  def test_difference_preserves_records_and_partitions_tasks_by_host(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      corpus = root / "corpus/properties"
      corpus.mkdir(parents=True)
      property_file = corpus / "unreach-call.prp"
      property_file.write_text("CHECK\n", encoding="utf-8")
      rows = []
      for index in range(4):
        task = root / f"task-{index}.yml"
        source = root / f"source-{index}.c"
        task.write_text(f"task {index}\n", encoding="utf-8")
        source.write_text(f"source {index}\n", encoding="utf-8")
        rows.append(
            {
                "task": task.name,
                "source": "sv-benchmarks",
                "task_path": task.name,
                "task_sha256": dataset.baseline.sha256_file(task),
                "source_paths": [source.name],
                "source_sha256": [dataset.baseline.sha256_file(source)],
                "family": f"family-{index % 2}",
                "seed_class": (
                    "hard_solved_seed" if index % 2 else "unsolved_seed"
                ),
                "expected_verdict": "true" if index % 2 else "false",
                "benchmark_set": "Loops",
            }
        )

      def write_manifest(path, tasks):
        path.write_text(
            json.dumps(
                {
                    "schema_version": "hard-case-candidate-v1-license-audited",
                    "task_count": len(tasks),
                    "license_audit": {
                        "included_task_count": len(tasks),
                        "excluded_task_count": 2,
                        "selection_independent_of_verifier_outcomes": True,
                    },
                    "corpus_files": [
                        {
                            "path": "corpus/properties/unreach-call.prp",
                            "sha256": dataset.baseline.sha256_file(property_file),
                        }
                    ],
                    "tasks": tasks,
                }
            ),
            encoding="utf-8",
        )

      full = root / "full.json"
      excluded = root / "excluded.json"
      write_manifest(full, rows)
      write_manifest(excluded, rows[:1])
      output = root / "derived"

      dataset.command_difference(
          SimpleNamespace(
              manifest=str(full),
              exclude_manifest=str(excluded),
              sv_benchmarks=str(root),
              output_dir=str(output),
          )
      )

      difference = dataset.validate_manifest(
          output / "candidate-manifest.json", root
      )
      self.assertEqual(difference["tasks"], rows[1:])
      self.assertNotIn("license_audit", difference)
      self.assertEqual(
          difference["parent_license_audit"],
          {
              "manifest_sha256": dataset.baseline.sha256_file(full),
              "included_task_count": 4,
              "excluded_task_count": 2,
              "selection_independent_of_verifier_outcomes": True,
              "task_license_evidence_preserved": True,
          },
      )
      shards = [
          dataset.validate_manifest(
              output / f"candidate-manifest-{host}.json", root
          )
          for host in dataset.DISCOVERY_HOSTS
      ]
      shard_tasks = [row["task"] for shard in shards for row in shard["tasks"]]
      self.assertCountEqual(shard_tasks, [row["task"] for row in rows[1:]])
      self.assertEqual(len(shard_tasks), len(set(shard_tasks)))
      shuffled = rows[1:]
      random.Random(20260727).shuffle(shuffled)
      self.assertEqual(
          {
              host: [row["task"] for row in tasks]
              for host, tasks in dataset.stratified_shards(rows[1:]).items()
          },
          {
              host: [row["task"] for row in tasks]
              for host, tasks in dataset.stratified_shards(shuffled).items()
          },
      )

      valid = dataset.stratified_shards(rows[1:])
      overlap = copy.deepcopy(valid)
      overlap["athena"].append(overlap["cthulhu"][0])
      with self.assertRaisesRegex(RuntimeError, "overlapping"):
        dataset.validate_shard_partition(rows[1:], overlap)
      missing = copy.deepcopy(valid)
      next(tasks for tasks in missing.values() if tasks).pop()
      with self.assertRaisesRegex(RuntimeError, "missing"):
        dataset.validate_shard_partition(rows[1:], missing)
      changed = copy.deepcopy(valid)
      next(tasks for tasks in changed.values() if tasks)[0]["task_sha256"] = "changed"
      with self.assertRaisesRegex(RuntimeError, "changed"):
        dataset.validate_shard_partition(rows[1:], changed)

      for key in (
          lambda row: (row["family"], row["seed_class"], row["expected_verdict"]),
          lambda row: row["family"],
          lambda row: row["seed_class"],
          lambda row: row["expected_verdict"],
      ):
        counts = {
            host: collections.Counter(key(row) for row in tasks)
            for host, tasks in valid.items()
        }
        for value in set().union(*(set(count) for count in counts.values())):
          values = [counts[host][value] for host in dataset.DISCOVERY_HOSTS]
          self.assertLessEqual(max(values) - min(values), 1)
      self.assertLessEqual(
          max(map(len, valid.values())) - min(map(len, valid.values())), 1
      )

      shard_paths = [
          output / f"candidate-manifest-{host}.json"
          for host in dataset.DISCOVERY_HOSTS
      ]
      validation_args = SimpleNamespace(
          manifest=str(output / "candidate-manifest.json"),
          shard_manifest=[str(path) for path in shard_paths],
          sv_benchmarks=str(root),
      )
      dataset.command_validate_shards(validation_args)
      athena_path = shard_paths[0]
      original = json.loads(athena_path.read_text(encoding="utf-8"))
      for field, value, message in (
          ("operation", "other", "operation"),
          ("hosts", list(reversed(dataset.DISCOVERY_HOSTS)), "host list"),
          ("parent_manifest_sha256", "0" * 64, "parent manifest hash"),
      ):
        tampered = copy.deepcopy(original)
        tampered["derivation"][field] = value
        athena_path.write_text(json.dumps(tampered), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, message):
          dataset.command_validate_shards(validation_args)
      athena_path.write_text(json.dumps(original), encoding="utf-8")

  def test_discovery_render_uses_fixed_120_130_140_second_limits(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      manifest = root / "manifest.json"
      manifest.write_text(
          json.dumps(
              {
                  "tasks": [
                      {
                          "task": "c/example.yml",
                          "task_path": "c/example.yml",
                          "source": "sv-benchmarks",
                      }
                  ]
              }
          ),
          encoding="utf-8",
      )
      output = root / "generated"

      dataset.command_render(
          SimpleNamespace(
              manifest=str(manifest),
              sv_benchmarks=str(root),
              property_file=str(root / "unreach-call.prp"),
              output_dir=str(output),
          )
      )

      benchmark = ET.parse(output / "hard-case-candidates.xml").getroot()
      self.assertEqual(benchmark.get("timelimit"), "120 s")
      self.assertEqual(benchmark.get("hardtimelimit"), "130 s")
      self.assertEqual(benchmark.get("walltimelimit"), "140 s")
      self.assertIn(
          ("--timelimit", "120 s"),
          [
              (option.get("name"), option.text)
              for option in benchmark.findall("option")
          ],
      )

  def test_screen_summary_separates_outcomes_and_writes_survivor_manifest(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      corpus = root / "corpus/properties"
      corpus.mkdir(parents=True)
      property_file = corpus / "unreach-call.prp"
      property_file.write_text("CHECK\n", encoding="utf-8")
      outcomes = [
          ("correct.yml", "true", "correct"),
          ("timeout.yml", "TIMEOUT", "error"),
          ("unknown.yml", "unknown", "unknown"),
          ("fallback.yml", "unrecognized", ""),
          ("error.yml", "ERROR", "error"),
          ("wrong.yml", "false", "wrong"),
          ("missing.yml", "", "missing"),
      ]
      tasks = []
      for name, _, _ in outcomes:
        task = root / name
        source = root / name.replace(".yml", ".c")
        task.write_text("task\n", encoding="utf-8")
        source.write_text("source\n", encoding="utf-8")
        tasks.append(
            {
                "task": name,
                "source": "sv-benchmarks",
                "family": "family",
                "seed_class": "unsolved_seed",
                "benchmark_set": "Loops",
                "expected_verdict": "true",
                "task_path": name,
                "task_sha256": dataset.baseline.sha256_file(task),
                "source_paths": [source.name],
                "source_sha256": [dataset.baseline.sha256_file(source)],
            }
        )
      manifest = root / "manifest.json"
      manifest.write_text(
          json.dumps(
              {
                  "task_count": len(tasks),
                  "corpus_files": [
                      {
                          "path": "corpus/properties/unreach-call.prp",
                          "sha256": dataset.baseline.sha256_file(property_file),
                      }
                  ],
                  "tasks": tasks,
              }
          ),
          encoding="utf-8",
      )
      result = root / "result.xml"
      result_root = ET.Element("result")
      for name, status, category in outcomes:
        run = ET.SubElement(
            result_root, "run", {"name": name, "expectedVerdict": "true"}
        )
        for title, value in (
            ("status", status),
            ("category", category),
            ("cputime", "1s"),
            ("walltime", "1s"),
            ("memory", "1B"),
        ):
          ET.SubElement(run, "column", {"title": title, "value": value})
      ET.ElementTree(result_root).write(result, encoding="unicode")
      output = root / "summary"

      dataset.command_screen_summary(
          SimpleNamespace(
              manifest=str(manifest),
              result=str(result),
              sv_benchmarks=str(root),
              output_dir=str(output),
          )
      )

      summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
      self.assertEqual(
          summary["classifications"],
          {
              "analysis_survivor": 2,
              "correct_fast": 1,
              "infrastructure_failure": 1,
              "verifier_failure_quarantine": 2,
              "wrong_quarantine": 1,
          },
      )
      survivor = dataset.validate_manifest(
          output / "candidate-manifest-analysis-survivors.json", root
      )
      self.assertEqual(
          [row["task"] for row in survivor["tasks"]],
          ["timeout.yml", "unknown.yml"],
      )
      first_run = result_root.find("run")
      first_run.remove(
          next(
              column
              for column in first_run.findall("column")
              if column.get("title") == "walltime"
          )
      )
      ET.ElementTree(result_root).write(result, encoding="unicode")
      with self.assertRaisesRegex(RuntimeError, "CPU or wall metrics"):
        dataset.command_screen_summary(
            SimpleNamespace(
                manifest=str(manifest),
                result=str(result),
                sv_benchmarks=str(root),
                output_dir=str(root / "invalid-summary"),
            )
        )

  def test_probe_classification_requires_spurious_path_through_loop_head(self):
    self.assertEqual(dataset.classify_probe_events([]), "structurally_unreachable")
    self.assertEqual(
        dataset.classify_probe_events(
            [{"counterexample_visits_loop_head": False}]
        ),
        "hook_reached_without_loop_head",
    )
    self.assertEqual(
        dataset.classify_probe_events(
            [{"counterexample_visits_loop_head": True}]
        ),
        "cegar_eligible",
    )

  def test_probe_uses_one_core_per_single_threaded_predicate_run(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      manifest = root / "manifest.json"
      manifest.write_text(
          json.dumps(
              {
                  "tasks": [
                      {
                          "task": "c/example.yml",
                          "task_path": "c/example.yml",
                          "source": "sv-benchmarks",
                      }
                  ]
              }
          ),
          encoding="utf-8",
      )
      hard = root / "hard.csv"
      with hard.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=["task"])
        writer.writeheader()
        writer.writerow({"task": "c/example.yml"})
      output = root / "generated"

      dataset.command_render_probe(
          SimpleNamespace(
              manifest=str(manifest),
              hard_portfolio=str(hard),
              sv_benchmarks=str(root),
              property_file=str(root / "unreach-call.prp"),
              output_dir=str(output),
          )
      )

      self.assertEqual(
          ET.parse(output / "cegar-eligibility.xml").getroot().get("cpuCores"), "1"
      )

  def test_license_evidence_uses_headers_or_same_directory_license(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      subprocess.run(["git", "init", "-q", root], check=True)
      subprocess.run(["git", "-C", root, "config", "user.name", "test"], check=True)
      subprocess.run(
          ["git", "-C", root, "config", "user.email", "test@example.com"], check=True
      )
      (root / "inline.c").write_text(
          "// SPDX-License-Identifier: MIT\n", encoding="utf-8"
      )
      directory = root / "directory"
      directory.mkdir()
      (directory / "License.txt").write_text("license\n", encoding="utf-8")
      (directory / "covered.c").write_text("int main(void) {}\n", encoding="utf-8")
      (root / "missing.c").write_text("int main(void) {}\n", encoding="utf-8")
      subprocess.run(["git", "-C", root, "add", "."], check=True)
      subprocess.run(["git", "-C", root, "commit", "-qm", "fixture"], check=True)

      licenses = dataset.official_license_files(root)

      self.assertEqual(
          dataset.official_license_evidence(root, "inline.c", licenses)[0][
              "identifiers"
          ],
          ["MIT"],
      )
      self.assertEqual(
          dataset.official_license_evidence(root, "directory/covered.c", licenses)[
              0
          ]["path"],
          "directory/License.txt",
      )
      self.assertEqual(
          dataset.official_license_evidence(root, "missing.c", licenses), []
      )


if __name__ == "__main__":
  unittest.main()
