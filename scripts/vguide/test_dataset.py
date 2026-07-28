#!/usr/bin/env python3

# This file is part of CPAchecker,
# a tool for configurable software verification:
# https://cpachecker.sosy-lab.org
#
# SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>
#
# SPDX-License-Identifier: Apache-2.0

import bz2
import collections
import copy
import csv
import hashlib
import importlib.util
import json
import os
import random
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SPEC = importlib.util.spec_from_file_location("dataset", Path(__file__).with_name("dataset.py"))
dataset = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dataset)


def write_stock_result(path, tasks, host, formal=False, omit=None, marker=""):
  limit = "900s" if formal else "120s"
  root = ET.Element(
      "result",
      {
          "benchmarkname": f"hard-case-candidates.{marker}",
          "starttime": f"2026-07-27T00:00:{marker or '00'}+08:00",
          "endtime": f"2026-07-27T00:01:{marker or '00'}+08:00",
          "tool": "CPAchecker",
          "version": dataset.FROZEN_CPACHECKER_VERSION,
          "toolmodule": dataset.FROZEN_TOOLMODULE,
          "generator": dataset.FROZEN_BENCHEXEC_GENERATOR,
          "displayName": dataset.FORMAL_DISPLAY if formal else dataset.DISCOVERY_DISPLAY,
          "memlimit": "15000000000B",
          "timelimit": limit,
          "cpuCores": "4",
          "block": "official",
          "name": "hard-case-candidates.official",
          "options": (
              f"--svcomp27 --heap 10000M --benchmark --timelimit {limit[:-1]} s"
          ),
      },
  )
  ET.SubElement(root, "systeminfo", {"hostname": host})
  for task in tasks:
    run = ET.SubElement(
        root,
        "run",
        {
            "name": str(path.parent / task["task_path"]),
            "files": (
                "["
                + ", ".join(
                    str(path.parent / source)
                    for source in task["source_paths"]
                )
                + "]"
            ),
            "properties": "unreach-call",
            "propertyFile": str(
                path.parent / "c/properties/unreach-call.prp"
            ),
            "expectedVerdict": task["expected_verdict"],
        },
    )
    for title, value in (
        ("status", "TIMEOUT"),
        ("category", "error"),
        ("cputime", limit),
        ("walltime", limit),
    ):
      if title != omit:
        ET.SubElement(run, "column", {"title": title, "value": value})
  ET.ElementTree(root).write(path, encoding="unicode")


def phase_b_fixture(root):
  corpus = root / "corpus/properties"
  corpus.mkdir(parents=True)
  prop = corpus / "unreach-call.prp"
  prop.write_text("CHECK\n", encoding="utf-8")
  official = root / "c/properties"
  official.mkdir(parents=True)
  (official / "unreach-call.prp").write_text("CHECK\n", encoding="utf-8")
  rows = []
  for index in range(6):
    task, source = root / f"t{index}.yml", root / f"s{index}.c"
    task.write_text(f"task {index}\n", encoding="utf-8")
    source.write_text(f"source {index}\n", encoding="utf-8")
    rows.append(
        {
            "task": task.name,
            "task_path": task.name,
            "task_sha256": dataset.baseline.sha256_file(task),
            "source": "sv-benchmarks",
            "source_paths": [source.name],
            "source_sha256": [dataset.baseline.sha256_file(source)],
            "family": "family",
            "seed_class": "unsolved_seed",
            "expected_verdict": "true",
            "benchmark_set": "Loops",
        }
    )
  parent = {
      "task_count": len(rows),
      "corpus_files": [
          {
              "path": "corpus/properties/unreach-call.prp",
              "sha256": dataset.baseline.sha256_file(prop),
          }
      ],
      "tasks": rows,
  }
  parent_path = root / "parent.json"
  parent_path.write_text(json.dumps(parent), encoding="utf-8")
  roles = tuple(dataset.PHASE_A_OPERATION)
  phases, results, survivors = [], [], []
  phase_hashes, result_hashes, survivor_hashes, survivor_counts = {}, {}, {}, {}
  for index, role in enumerate(roles):
    manifest = dataset.manifest_subset(
        parent,
        [row["task"] for row in rows[index * 2 : index * 2 + 2]],
        {
            "operation": dataset.PHASE_A_OPERATION[role],
            "host": "valkyrie",
            "selection_independent_of_verifier_outcomes": True,
        },
    )
    path = root / f"phase-{role}.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    digest = dataset.baseline.sha256_file(path)
    phase_hashes[role] = digest
    result = root / f"phase-{index}.xml"
    write_stock_result(result, manifest["tasks"], "valkyrie", marker=str(index))
    result_hashes[role] = dataset.baseline.sha256_file(result)
    survivor = dataset.manifest_subset(
        manifest,
        [row["task"] for row in manifest["tasks"]],
        {
            "operation": "phase_a_analysis_survivors",
            "parent_manifest_sha256": digest,
            "result_sha256": dataset.baseline.sha256_file(result),
            "allowed_results": sorted(dataset.ANALYSIS_UNSOLVED),
            "phase_a_host": "valkyrie",
            "selection_independent_of_augmented_outcomes": True,
        },
    )
    survivor_path = root / f"survivor-{index}.json"
    survivor_path.write_text(json.dumps(survivor), encoding="utf-8")
    survivor_hashes[role] = dataset.baseline.sha256_file(survivor_path)
    survivor_counts[role] = survivor["task_count"]
    phases.append(path)
    results.append(result)
    survivors.append(survivor_path)
  fixture = SimpleNamespace(
      parent_manifest=str(parent_path),
      phase_a_manifest=[str(path) for path in phases],
      phase_a_result=[str(path) for path in results],
      survivor_manifest=[str(path) for path in survivors],
      sv_benchmarks=str(root),
      parent_sha=dataset.baseline.sha256_file(parent_path),
      phase_hashes=phase_hashes,
      result_hashes=result_hashes,
      survivor_hashes=survivor_hashes,
      survivor_counts=survivor_counts,
      rows=rows,
  )
  fixture.formal_hash = fixture_formal_hash(fixture)
  return fixture


def fixture_formal_hash(fixture):
  parent = json.loads(Path(fixture.parent_manifest).read_text())
  tasks = []
  inputs = []
  for role, survivor_path in zip(
      dataset.PHASE_A_OPERATION, fixture.survivor_manifest, strict=True
  ):
    survivor = json.loads(Path(survivor_path).read_text())
    tasks.extend(row["task"] for row in survivor["tasks"])
    inputs.append(
        {
            "role": role,
            "phase_a_manifest_sha256": fixture.phase_hashes[role],
            "phase_a_result_sha256": fixture.result_hashes[role],
            "survivor_manifest_sha256": fixture.survivor_hashes[role],
            "survivor_task_count": fixture.survivor_counts[role],
        }
    )
  merged = dataset.manifest_subset(
      parent,
      tasks,
      {
          "operation": "merge_phase_a_survivors_single_host",
          "parent_manifest_sha256": fixture.parent_sha,
          "host": "valkyrie",
          "phase_a_inputs": inputs,
          "selection_independent_of_augmented_outcomes": True,
      },
  )
  content = (json.dumps(merged, indent=2) + "\n").encode()
  return hashlib.sha256(content).hexdigest()


def phase_b_pins(fixture):
  return mock.patch.multiple(
      dataset,
      FROZEN_PARENT_MANIFEST_SHA256=fixture.parent_sha,
      FROZEN_PHASE_A_MANIFEST_SHA256=fixture.phase_hashes,
      FROZEN_PHASE_A_RESULT_SHA256=fixture.result_hashes,
      FROZEN_PHASE_A_SURVIVOR_SHA256=fixture.survivor_hashes,
      FROZEN_PHASE_A_SURVIVOR_TASK_COUNT=fixture.survivor_counts,
      FROZEN_FORMAL_MANIFEST_SHA256=fixture.formal_hash,
  )


def phase_b_inputs(fixture):
  excluded = {
      "parent_sha",
      "phase_hashes",
      "result_hashes",
      "survivor_hashes",
      "survivor_counts",
      "formal_hash",
      "rows",
  }
  return {
      name: value
      for name, value in vars(fixture).items()
      if name not in excluded
  }


def zero_phase_a_survivors(fixture):
  for role, result_value, survivor_value in zip(
      dataset.PHASE_A_OPERATION,
      fixture.phase_a_result,
      fixture.survivor_manifest,
      strict=True,
  ):
    result = Path(result_value)
    root = ET.parse(result).getroot()
    for run in root.findall("run"):
      run.find("column[@title='status']").set("value", "true")
      run.find("column[@title='category']").set("value", "correct")
    ET.ElementTree(root).write(result, encoding="unicode")
    survivor = json.loads(Path(survivor_value).read_text())
    survivor["derivation"]["result_sha256"] = dataset.baseline.sha256_file(
        result
    )
    survivor["task_count"] = 0
    survivor["tasks"] = []
    Path(survivor_value).write_text(json.dumps(survivor), encoding="utf-8")
    fixture.result_hashes[role] = dataset.baseline.sha256_file(result)
    fixture.survivor_hashes[role] = dataset.baseline.sha256_file(
        Path(survivor_value)
    )
    fixture.survivor_counts[role] = 0
  fixture.formal_hash = fixture_formal_hash(fixture)


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
      self.assertEqual(
          dataset.baseline.sha256_file(output / "candidate-manifest.json"),
          "62d29eee73ac252fef708af4526d651f31d0e090257ba18126adae95b1ec753d",
      )
      self.assertEqual(
          {
              host: dataset.baseline.sha256_file(
                  output / f"candidate-manifest-{host}.json"
              )
              for host in dataset.DISCOVERY_HOSTS
          },
          {
              "athena": (
                  "d5f769e729ecc43ae8511b6408117cef884deb1e82d6492db3abeaa5329712b0"
              ),
              "cthulhu": (
                  "dba6d5a33824c78cbef1098efe0b6878b741ffd09dcc74a7e4277fe1be203d7f"
              ),
              "valkyrie": (
                  "5f741982bb88353e2a92045833a57abc0a03cb5bb6b894d1fb8b7bfcf113c024"
              ),
          },
      )
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

  def test_cthulhu_reroute_is_fixed_complete_and_fail_closed(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      corpus = root / "corpus/properties"
      corpus.mkdir(parents=True)
      property_file = corpus / "unreach-call.prp"
      property_file.write_text("CHECK\n", encoding="utf-8")
      tasks = []
      for index in range(8):
        task = root / f"task-{index}.yml"
        source = root / f"source-{index}.c"
        task.write_text(f"task {index}\n", encoding="utf-8")
        source.write_text(f"source {index}\n", encoding="utf-8")
        tasks.append(
            {
                "task": task.name,
                "source": "sv-benchmarks",
                "task_path": task.name,
                "task_sha256": dataset.baseline.sha256_file(task),
                "source_paths": [source.name],
                "source_sha256": [dataset.baseline.sha256_file(source)],
                "family": f"family-{index % 3}",
                "seed_class": (
                    "hard_solved_seed" if index % 2 else "unsolved_seed"
                ),
                "expected_verdict": "true" if index % 2 else "false",
            }
        )
      parent = root / "candidate-manifest-cthulhu.json"
      parent.write_text(
          json.dumps(
              {
                  "schema_version": "hard-case-candidate-v2-derived",
                  "task_count": len(tasks),
                  "corpus_files": [
                      {
                          "path": "corpus/properties/unreach-call.prp",
                          "sha256": dataset.baseline.sha256_file(property_file),
                      }
                  ],
                  "derivation": {
                      "operation": "deterministic_stratified_shard",
                      "hosts": list(dataset.DISCOVERY_HOSTS),
                      "host": "cthulhu",
                      "selection_independent_of_verifier_outcomes": True,
                  },
                  "tasks": tasks,
              },
              indent=2,
          )
          + "\n",
          encoding="utf-8",
      )
      parent_sha256 = dataset.baseline.sha256_file(parent)
      output = root / "rerouted"
      paths = [
          output / f"candidate-manifest-{host}.json"
          for host in dataset.REROUTE_HOSTS
      ]
      args = SimpleNamespace(
          manifest=str(parent),
          reroute_manifest=[str(path) for path in paths],
          sv_benchmarks=str(root),
      )
      with mock.patch.object(
          dataset, "FROZEN_CTHULHU_MANIFEST_SHA256", parent_sha256
      ):
        dataset.command_reroute_cthulhu(
            SimpleNamespace(
                manifest=str(parent),
                sv_benchmarks=str(root),
                output_dir=str(output),
            )
        )
        dataset.command_validate_reroute(args)
        originals = {
            path: json.loads(path.read_text(encoding="utf-8"))
            for path in paths
        }

        tampered = copy.deepcopy(originals[paths[0]])
        tampered["derivation"]["operation"] = "other"
        paths[0].write_text(json.dumps(tampered), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "provenance"):
          dataset.command_validate_reroute(args)
        paths[0].write_text(json.dumps(originals[paths[0]]), encoding="utf-8")

        tampered = copy.deepcopy(originals[paths[0]])
        tampered["tasks"][0]["family"] = "changed"
        paths[0].write_text(json.dumps(tampered), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "changed provenance or rows"):
          dataset.command_validate_reroute(args)
        paths[0].write_text(json.dumps(originals[paths[0]]), encoding="utf-8")

        tampered = copy.deepcopy(originals[paths[0]])
        tampered["tasks"].pop()
        tampered["task_count"] -= 1
        paths[0].write_text(json.dumps(tampered), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "missing"):
          dataset.command_validate_reroute(args)
        paths[0].write_text(json.dumps(originals[paths[0]]), encoding="utf-8")

        parent_manifest = json.loads(parent.read_text(encoding="utf-8"))
        first = dataset.manifest_subset(
            parent_manifest,
            [
                *(row["task"] for row in originals[paths[0]]["tasks"]),
                originals[paths[1]]["tasks"][0]["task"],
            ],
            originals[paths[0]]["derivation"],
        )
        paths[0].write_text(json.dumps(first), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "overlapping"):
          dataset.command_validate_reroute(args)
        paths[0].write_text(json.dumps(originals[paths[0]]), encoding="utf-8")

        first_tasks = [row["task"] for row in originals[paths[0]]["tasks"]]
        second_tasks = [row["task"] for row in originals[paths[1]]["tasks"]]
        first_tasks[0], second_tasks[0] = second_tasks[0], first_tasks[0]
        first = dataset.manifest_subset(
            parent_manifest,
            first_tasks,
            originals[paths[0]]["derivation"],
        )
        second = dataset.manifest_subset(
            parent_manifest,
            second_tasks,
            originals[paths[1]]["derivation"],
        )
        paths[0].write_text(json.dumps(first), encoding="utf-8")
        paths[1].write_text(json.dumps(second), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "recomputed assignment"):
          dataset.command_validate_reroute(args)

  def test_athena_recovery_merge_preserves_both_frozen_parents(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      corpus = root / "corpus/properties"
      corpus.mkdir(parents=True)
      property_file = corpus / "unreach-call.prp"
      property_file.write_text("CHECK\n", encoding="utf-8")
      tasks = []
      for index in range(4):
        task = root / f"task-{index}.yml"
        source = root / f"source-{index}.c"
        task.write_text(f"task {index}\n", encoding="utf-8")
        source.write_text(f"source {index}\n", encoding="utf-8")
        tasks.append(
            {
                "task": task.name,
                "source": "sv-benchmarks",
                "task_path": task.name,
                "task_sha256": dataset.baseline.sha256_file(task),
                "source_paths": [source.name],
                "source_sha256": [dataset.baseline.sha256_file(source)],
            }
        )

      def write_parent(path, rows, derivation):
        path.write_text(
            json.dumps(
                {
                    "schema_version": "hard-case-candidate-v2-derived",
                    "task_count": len(rows),
                    "corpus_files": [
                        {
                            "path": "corpus/properties/unreach-call.prp",
                            "sha256": dataset.baseline.sha256_file(property_file),
                        }
                    ],
                    "tasks": rows,
                    "derivation": derivation,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

      original = root / "candidate-manifest-athena.json"
      reroute = root / "candidate-manifest-reroute-athena.json"
      original_derivation = {"operation": "original", "host": "athena"}
      reroute_derivation = {"operation": "reroute", "host": "athena"}
      write_parent(original, tasks[:2], original_derivation)
      write_parent(reroute, tasks[2:], reroute_derivation)
      output = root / "recovery"
      original_sha256 = dataset.baseline.sha256_file(original)
      reroute_sha256 = dataset.baseline.sha256_file(reroute)
      with (
          mock.patch.object(
              dataset, "FROZEN_ATHENA_MANIFEST_SHA256", original_sha256
          ),
          mock.patch.object(
              dataset,
              "FROZEN_ATHENA_REROUTE_MANIFEST_SHA256",
              reroute_sha256,
          ),
      ):
        expected = dataset.expected_athena_recovery_manifest(
            original, reroute, root
        )
        expected_sha256 = dataset.sha256_text(
            json.dumps(expected, indent=2) + "\n"
        )
        with mock.patch.object(
            dataset,
            "FROZEN_ATHENA_RECOVERY_MANIFEST_SHA256",
            expected_sha256,
        ):
          dataset.command_athena_recovery(
              SimpleNamespace(
                  athena_manifest=str(original),
                  athena_reroute_manifest=str(reroute),
                  sv_benchmarks=str(root),
                  output_dir=str(output),
              )
          )
          manifest_path = output / "candidate-manifest-valkyrie.json"
          dataset.command_validate_athena_recovery(
              SimpleNamespace(
                  athena_manifest=str(original),
                  athena_reroute_manifest=str(reroute),
                  manifest=str(manifest_path),
                  sv_benchmarks=str(root),
              )
          )
          merged = json.loads(manifest_path.read_text(encoding="utf-8"))
          self.assertEqual(merged["tasks"], tasks)
          self.assertEqual(merged["derivation"]["host"], "valkyrie")
          self.assertEqual(
              [
                  parent["derivation"]
                  for parent in merged["derivation"]["parents"]
              ],
              [original_derivation, reroute_derivation],
          )
          merged["tasks"].reverse()
          manifest_path.write_text(json.dumps(merged), encoding="utf-8")
          with self.assertRaisesRegex(
              RuntimeError, "hash is not frozen r5 output"
          ):
            dataset.command_validate_athena_recovery(
                SimpleNamespace(
                    athena_manifest=str(original),
                    athena_reroute_manifest=str(reroute),
                    manifest=str(manifest_path),
                    sv_benchmarks=str(root),
                )
            )

      with self.assertRaisesRegex(RuntimeError, "overlapping"):
        dataset.athena_recovery_manifest(
            json.loads(original.read_text(encoding="utf-8")),
            {
                **json.loads(reroute.read_text(encoding="utf-8")),
                "tasks": [tasks[0], tasks[2]],
            },
        )

  def test_r5_production_closure(self):
    runner = Path(__file__).with_name("run-stock-dataset.sh").read_text(
        encoding="utf-8"
    )
    self.assertEqual(
        dataset.FROZEN_ATHENA_MANIFEST_SHA256,
        "5b0224af541b371fd8f882cf71099b774fdd33dc3187cf6dca31cc3c8ca55cef",
    )
    self.assertEqual(
        dataset.FROZEN_ATHENA_REROUTE_MANIFEST_SHA256,
        "477374a2bbab9fd8559e1945e6781b5484e26afec7808266332423c1db9cddd6",
    )
    self.assertEqual(
        dataset.FROZEN_ATHENA_RECOVERY_MANIFEST_SHA256,
        "59681ac7dbbf177ae6a4ce3cfd3bd5e5b45d57658c1d6ed467c74e1cd4f60f04",
    )
    self.assertIn(
        f"EXPECTED_MANIFEST={dataset.FROZEN_ATHENA_RECOVERY_MANIFEST_SHA256}",
        runner,
    )
    names = (
        "VGUIDE_R5_ATHENA_MANIFEST",
        "VGUIDE_R5_ATHENA_REROUTE_MANIFEST",
        "VGUIDE_R5_RECOVERY_MANIFEST",
        "VGUIDE_SV_BENCHMARKS",
    )
    paths = [os.environ.get(name) for name in names]
    if not any(paths):
      self.skipTest("production manifest paths are not configured")
    self.assertTrue(all(paths), f"set all production paths: {names}")
    expected = dataset.expected_athena_recovery_manifest(
        paths[0], paths[1], paths[3]
    )
    actual = dataset.validate_manifest(paths[2], paths[3])
    self.assertEqual(actual, expected)
    self.assertEqual(
        dataset.baseline.sha256_file(Path(paths[2])),
        dataset.FROZEN_ATHENA_RECOVERY_MANIFEST_SHA256,
    )

  def test_phase_b_production_closure(self):
    names = (
        "VGUIDE_PHASE_B_PARENT_MANIFEST",
        "VGUIDE_PHASE_B_PHASE_MANIFESTS",
        "VGUIDE_PHASE_B_RESULTS",
        "VGUIDE_PHASE_B_SURVIVORS",
        "VGUIDE_PHASE_B_SV_BENCHMARKS",
    )
    values = [os.environ.get(name) for name in names]
    if not any(values):
      self.skipTest("Phase-B production evidence paths are not configured")
    self.assertTrue(all(values), f"set all production paths: {names}")
    phase_manifests = values[1].split(os.pathsep)
    results = values[2].split(os.pathsep)
    survivors = values[3].split(os.pathsep)
    self.assertEqual(
        [len(phase_manifests), len(results), len(survivors)], [3, 3, 3]
    )
    inputs = {
        "parent_manifest": values[0],
        "phase_a_manifest": phase_manifests,
        "phase_a_result": results,
        "survivor_manifest": survivors,
        "sv_benchmarks": values[4],
    }
    parent, _, merged = dataset.authenticate_phase_b_inputs(
        SimpleNamespace(**inputs)
    )
    self.assertEqual(parent["task_count"], 320)
    self.assertEqual(merged["task_count"], 270)
    self.assertEqual(
        dataset.FROZEN_FORMAL_MANIFEST_SHA256,
        "e8aed1d26a0920bfef4964d495d86b69bbad666efb8d72e87462f297ca243855",
    )
    packages = []
    with tempfile.TemporaryDirectory() as temp:
      for repetition in range(2):
        output = Path(temp) / str(repetition)
        dataset.command_merge_survivors(
            SimpleNamespace(**inputs, output_dir=str(output))
        )
        manifest_path = output / "candidate-manifest-valkyrie-formal.json"
        authenticated, host = dataset.authenticate_formal_manifest(
            SimpleNamespace(**inputs, manifest=str(manifest_path))
        )
        self.assertEqual(host, "valkyrie")
        self.assertEqual(authenticated["task_count"], 270)
        self.assertEqual(
            dataset.baseline.sha256_file(manifest_path),
            dataset.FROZEN_FORMAL_MANIFEST_SHA256,
        )
        declared = {row["path"] for row in parent.get("corpus_files", [])}
        files = {
            path.relative_to(output).as_posix(): path.read_bytes()
            for path in output.rglob("*")
            if path.is_file()
        }
        self.assertEqual(
            set(files),
            {
                "artifact-manifest.json",
                "candidate-manifest-valkyrie-formal.json",
                *declared,
            },
        )
        artifact = json.loads(files["artifact-manifest.json"])
        self.assertEqual(artifact["root"], ".")
        self.assertEqual(artifact["file_count"], len(artifact["files"]))
        self.assertEqual(
            [row["path"] for row in artifact["files"]],
            sorted(
                {
                    "candidate-manifest-valkyrie-formal.json",
                    *declared,
                }
            ),
        )
        aggregate = hashlib.sha256()
        for row in artifact["files"]:
          self.assertEqual(len(files[row["path"]]), row["size_bytes"])
          self.assertEqual(
              hashlib.sha256(files[row["path"]]).hexdigest(), row["sha256"]
          )
          aggregate.update(row["path"].encode("utf-8"))
          aggregate.update(b"\0")
          aggregate.update(bytes.fromhex(row["sha256"]))
        self.assertEqual(artifact["aggregate_sha256"], aggregate.hexdigest())
        packages.append(files)
    self.assertEqual(packages[0], packages[1])

  def test_r5_runner_accepts_only_athena_recovery_on_valkyrie(self):
    runner = Path(__file__).with_name("run-stock-dataset.sh").read_text(
        encoding="utf-8"
    )
    self.assertIn(
        dataset.FROZEN_ATHENA_RECOVERY_MANIFEST_SHA256,
        runner,
    )
    self.assertNotIn(
        dataset.FROZEN_ATHENA_MANIFEST_SHA256,
        runner,
    )
    self.assertNotIn(
        dataset.FROZEN_ATHENA_REROUTE_MANIFEST_SHA256,
        runner,
    )
    self.assertIn('if [[ $HOST != "valkyrie" ]]', runner)
    self.assertIn("r5 Athena recovery is Valkyrie-only", runner)
    self.assertIn('--phase-a-host "$HOST"', runner)
    self.assertIn(
        '--name "hard-case-dataset-v2-discovery-athena-recovery-valkyrie-screen"',
        runner,
    )

  def test_formal_runner_is_pinned_sequential_and_fail_closed(self):
    path = Path(__file__).with_name("run-stock-formal-dataset.sh")
    runner = path.read_text(encoding="utf-8")
    subprocess.run(["bash", "-n", path], check=True)
    for value in (
        "1848f9eb597ca99a170fd98af8aad716743a2bfe",
        "9cf9198156e4c8a6c517e474770158e1bb0b566d",
        "edb95ed3a8478366b8bb89f8cdd1d9a6c5fa8c84",
        "867ff62e01a0936fc0a90ceae27338be1973559767ef0717896f8d64f780ece6",
        "eea0df062de5c8e3febe0d96b583741c140e79d3ae41a87a56d7be365b876f9d",
        "52772e241e78a875fa00dea891eac2023d4f2be639a5f28a17dca81580f75e5b",
        "7d51cd6b48b521277f5caa4610a82126e315fa2be4df069823a8b1eeb5bd4a86",
        "eef7994f6b57cb0bbdb803ef6aadc0c1afbe61d444932eeef5dc5c114b6cf27b",
        "0970024a48206a1937b5bfbf889335525b769b89a27ca7df25d793d7727b909c",
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "75e3332253429e6f9186352a255cd96c0aff6154a95e2fdd3b737c143ba018bc",
        "49f95adc5255b89b1bb3edea81ab5f2f660364d36ffa69c3b12508d1e1943be3",
        dataset.FROZEN_FORMAL_MANIFEST_SHA256,
        "a20797345df1bef6d5be5356906ee106b75b374b0d6cd2adfbc56cc5c3e65fef",
    ):
      self.assertIn(value, runner)
    self.assertIn('$(hostname -s) != "valkyrie"', runner)
    self.assertIn("LLM/VGuide environment is forbidden", runner)
    self.assertIn("output directory must be absent or empty", runner)
    self.assertIn('R8_RECOVERY_ROOT=$(realpath "${15}")', runner)
    self.assertIn('OUTPUT_DIR=$(realpath -m "${16}")', runner)
    self.assertIn("flock -n 9", runner)
    self.assertNotIn("foreign-workload-gate", runner)
    self.assertIn('require_clean_repo "$RESEARCH_ROOT" "research"', runner)
    self.assertIn('require_clean_repo "$BENCHEXEC_DIR" "BenchExec"', runner)
    self.assertIn("assume-unchanged index entries", runner)
    self.assertIn("changed materialized skip-worktree file", runner)
    self.assertIn("validate_formal_package_topology", runner)
    self.assertIn("reject_output_overlap", runner)
    self.assertIn('"$JAVA_HOME" "$ANT_INSTALL" "$PYTHON_BIN" "$PYTHON_STDLIB"', runner)
    self.assertIn(
        '"$PYTHON_DIST_PACKAGES" "$PYTHON_LOCAL_DIST_PACKAGES"', runner
    )
    self.assertIn('"$ANT_BIN" -Divy.disable=true clean jar', runner)
    self.assertIn("EXPECTED_PYTHON_REAL=/usr/bin/python3.10", runner)
    self.assertIn("EXPECTED_PYYAML_VERSION=5.4.1", runner)
    self.assertIn(
        "EXPECTED_PYYAML_FILE=/usr/lib/python3/dist-packages/yaml/__init__.py",
        runner,
    )
    self.assertIn('EXPECTED_ANT_VERSION="Apache Ant(TM) version 1.10.12', runner)
    self.assertIn("jar_content_digest_value", runner)
    self.assertIn("remove_compiled_classes", runner)
    self.assertGreaterEqual(runner.count("assert_no_compiled_classes"), 3)
    build = runner.index('"$ANT_BIN" -Divy.disable=true clean jar')
    remove_classes = runner.index("remove_compiled_classes", build)
    self.assertLess(
        runner.index('"$EXPECTED_CPACHECKER_JAR_CONTENT" ]]', build),
        remove_classes,
    )
    self.assertLess(remove_classes, runner.index("machine-preflight-start.json", build))
    self.assertGreaterEqual(runner.count("verify_runtime_closure"), 5)
    self.assertIn("sleep 10", runner)
    self.assertIn('"$DATASET_PY" render-formal', runner)
    self.assertIn("--container", runner)
    self.assertIn("--read-only-dir /", runner)
    self.assertIn("--hidden-dir /home", runner)
    self.assertIn("--overlay-dir", runner)
    self.assertIn("-N 2 -c 4", runner)
    self.assertIn("machine-after-failure.json", runner)
    self.assertIn("failure-capture-status.txt", runner)
    self.assertIn("trap capture_failure EXIT", runner)
    self.assertIn('exit "$status"', runner)
    self.assertGreaterEqual(runner.count("artifact-manifest"), 3)
    self.assertIn(
        'cp -a "$FORMAL_PACKAGE/." "$OUTPUT_DIR/input/formal/"', runner
    )
    self.assertIn(
        'cp -a "$R8_RECOVERY_ROOT" "$OUTPUT_DIR/input/recovery-r8"', runner
    )
    self.assertGreaterEqual(runner.count("validate-cap8-r8-recovery"), 2)
    self.assertIn('copy_phase_evidence "$OUTPUT_DIR/input/evidence"', runner)
    self.assertIn(
        'capture_research_provenance "$OUTPUT_DIR/input/research"', runner
    )
    self.assertIn('activate_saved_scripts "$OUTPUT_DIR/input/research"', runner)
    self.assertIn('record_process_snapshot "$OUTPUT_DIR/provenance"', runner)
    self.assertIn('start_process_monitor "$OUTPUT_DIR/provenance/$label-', runner)
    self.assertIn("wait_for_process_monitor", runner)
    self.assertIn("wait_for_benchmark_with_monitor", runner)
    self.assertIn("terminate_owned_session", runner)
    self.assertIn("os.setsid()", runner)
    self.assertIn('systemctl --user stop "$scope"', runner)
    self.assertGreaterEqual(
        Path(__file__).with_name("dataset.py").read_text().count(
            "ProcessLookupError"
        ),
        2,
    )
    self.assertIn('[[ "$samples" -ge 10 ]]', runner)
    self.assertIn("stop_process_monitor_for_teardown", runner)
    self.assertIn("stop_process_monitor", runner)
    captured = runner.index(
        'capture_research_provenance "$OUTPUT_DIR/input/research"'
    )
    self.assertNotIn('"$SCRIPT_DIR/dataset.py"', runner[captured:])
    self.assertNotIn('"$SCRIPT_DIR/baseline.py"', runner[captured:])
    self.assertLess(
        runner.index('JAVA_HOME=$(realpath "${JAVA_HOME:'),
        runner.index('mkdir -p "$OUTPUT_DIR/input/formal"'),
    )
    self.assertLess(
        runner.index('directory_digest_value "$JAVA_HOME"'),
        runner.index('mkdir -p "$OUTPUT_DIR/input/formal"'),
    )
    self.assertNotIn('if [[ "$TASK_COUNT" -eq 0 ]]', runner)
    self.assertIn('if [[ "$TASK_COUNT" -ne 270 ]]', runner)
    self.assertIn("--hard-threshold 200", runner)
    self.assertNotIn("44ec679a56d3", runner)
    self.assertNotIn("run_formal_benchmark repetition-1", runner)
    self.assertNotIn("run_formal_benchmark repetition-2", runner)
    first = runner.index('RECOVERY_COPY="$OUTPUT_DIR/input/recovery-r8"')
    first_result = runner.index(
        'single_formal_result "$OUTPUT_DIR/results/repetition-1"', first
    )
    first_plan = runner.index(
        '--output "$OUTPUT_DIR/repetition-1-plan.json"', first_result
    )
    second = runner.index('build_repetition_plan 2 "${RESULTS[1]}"')
    second_result = runner.index(
        'single_formal_result "$OUTPUT_DIR/results/repetition-2"', first
    )
    summarize = runner.index('"$DATASET_PY" summarize', second)
    self.assertLess(first, first_result)
    self.assertLess(first_result, first_plan)
    self.assertLess(second_result, first_plan)
    self.assertLess(first_plan, second)
    self.assertLess(second, summarize)
    self.assertIn('--repetition-plan "${PLANS[0]}"', runner)
    self.assertIn('--repetition-plan "${PLANS[1]}"', runner)
    self.assertNotIn('--result "${RESULTS[0]}"', runner)

  def test_formal_runner_result_lookup_is_exact_and_fail_closed(self):
    runner = Path(__file__).with_name("run-stock-formal-dataset.sh")
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      expected = (
          root
          / "run.results.hard-case-candidates.official.xml.bz2"
      )
      expected.touch()
      (root / "run.results.hard-case-candidates.external.xml.bz2").touch()
      (root / f"{expected.name}.txt").touch()
      nested = root / "nested"
      nested.mkdir()
      (nested / expected.name).touch()
      command = 'source "$1"; single_formal_result "$2"'
      found = subprocess.run(
          ["bash", "-c", command, "bash", str(runner), str(root)],
          check=True,
          capture_output=True,
          text=True,
      )
      self.assertEqual(found.stdout.splitlines(), [str(expected)])

      extra = root / "other.results.hard-case-candidates.xml"
      extra.touch()
      multiple = subprocess.run(
          ["bash", "-c", command, "bash", str(runner), str(root)],
          capture_output=True,
          text=True,
      )
      self.assertNotEqual(multiple.returncode, 0)
      self.assertIn("expected exactly one formal result", multiple.stderr)

      expected.unlink()
      extra.unlink()
      missing = subprocess.run(
          ["bash", "-c", command, "bash", str(runner), str(root)],
          capture_output=True,
          text=True,
      )
      self.assertNotEqual(missing.returncode, 0)
      self.assertIn("found 0", missing.stderr)

  def test_formal_runner_rejects_dirty_benchexec_checkout(self):
    runner = Path(__file__).with_name("run-stock-formal-dataset.sh")
    with tempfile.TemporaryDirectory() as temp:
      repository = Path(temp) / "benchexec"
      repository.mkdir()
      subprocess.run(["git", "init", "-q", repository], check=True)
      subprocess.run(
          ["git", "-C", repository, "config", "user.email", "test@example.com"],
          check=True,
      )
      subprocess.run(
          ["git", "-C", repository, "config", "user.name", "Test"], check=True
      )
      tracked = repository / "tracked"
      tracked.write_text("clean\n", encoding="utf-8")
      subprocess.run(["git", "-C", repository, "add", "tracked"], check=True)
      subprocess.run(
          ["git", "-C", repository, "commit", "-qm", "fixture"], check=True
      )
      command = 'source "$1"; require_clean_repo "$2" BenchExec'
      subprocess.run(
          ["bash", "-c", command, "bash", str(runner), str(repository)],
          check=True,
      )
      tracked.write_text("dirty\n", encoding="utf-8")
      rejected = subprocess.run(
          ["bash", "-c", command, "bash", str(runner), str(repository)],
          capture_output=True,
          text=True,
      )
      self.assertNotEqual(rejected.returncode, 0)
      self.assertIn("BenchExec checkout is not clean", rejected.stderr)

  def test_formal_runner_rejects_assume_unchanged_and_changed_sparse_file(self):
    runner = Path(__file__).with_name("run-stock-formal-dataset.sh")
    with tempfile.TemporaryDirectory() as temp:
      repository = Path(temp) / "sparse"
      repository.mkdir()
      subprocess.run(["git", "init", "-q", repository], check=True)
      subprocess.run(
          ["git", "-C", repository, "config", "user.email", "test@example.com"],
          check=True,
      )
      subprocess.run(
          ["git", "-C", repository, "config", "user.name", "Test"], check=True
      )
      tracked = repository / "tracked"
      tracked.write_text("HEAD\n", encoding="utf-8")
      link = repository / "link"
      link.symlink_to("tracked")
      subprocess.run(["git", "-C", repository, "add", "tracked", "link"], check=True)
      subprocess.run(
          ["git", "-C", repository, "commit", "-qm", "fixture"], check=True
      )
      command = 'source "$1"; require_clean_repo "$2" sparse true'

      subprocess.run(
          ["git", "-C", repository, "update-index", "--assume-unchanged", "tracked"],
          check=True,
      )
      rejected = subprocess.run(
          ["bash", "-c", command, "bash", str(runner), str(repository)],
          capture_output=True,
          text=True,
      )
      self.assertNotEqual(rejected.returncode, 0)
      self.assertIn("assume-unchanged index entries", rejected.stderr)
      subprocess.run(
          ["git", "-C", repository, "update-index", "--no-assume-unchanged", "tracked"],
          check=True,
      )

      subprocess.run(
          ["git", "-C", repository, "update-index", "--skip-worktree", "tracked"],
          check=True,
      )
      subprocess.run(
          ["bash", "-c", command, "bash", str(runner), str(repository)],
          check=True,
      )
      tracked.unlink()
      subprocess.run(
          ["bash", "-c", command, "bash", str(runner), str(repository)],
          check=True,
      )
      missing_rejected = subprocess.run(
          [
              "bash",
              "-c",
              'source "$1"; require_clean_repo "$2" stock',
              "bash",
              str(runner),
              str(repository),
          ],
          capture_output=True,
          text=True,
      )
      self.assertNotEqual(missing_rejected.returncode, 0)
      self.assertIn("missing skip-worktree entry", missing_rejected.stderr)
      tracked.write_text("hidden change\n", encoding="utf-8")
      rejected = subprocess.run(
          ["bash", "-c", command, "bash", str(runner), str(repository)],
          capture_output=True,
          text=True,
      )
      self.assertNotEqual(rejected.returncode, 0)
      self.assertIn("changed materialized skip-worktree file", rejected.stderr)

      tracked.write_text("HEAD\n", encoding="utf-8")
      tracked.chmod(0o755)
      rejected = subprocess.run(
          ["bash", "-c", command, "bash", str(runner), str(repository)],
          capture_output=True,
          text=True,
      )
      self.assertNotEqual(rejected.returncode, 0)
      self.assertIn("changed skip-worktree mode", rejected.stderr)
      tracked.chmod(0o644)

      tracked.chmod(0o744)
      rejected = subprocess.run(
          ["bash", "-c", command, "bash", str(runner), str(repository)],
          capture_output=True,
          text=True,
      )
      self.assertNotEqual(rejected.returncode, 0)
      self.assertIn("changed skip-worktree mode", rejected.stderr)
      tracked.chmod(0o644)

      subprocess.run(
          ["git", "-C", repository, "update-index", "--skip-worktree", "link"],
          check=True,
      )
      subprocess.run(
          ["bash", "-c", command, "bash", str(runner), str(repository)],
          check=True,
      )
      link.unlink()
      link.write_text("tracked", encoding="utf-8")
      rejected = subprocess.run(
          ["bash", "-c", command, "bash", str(runner), str(repository)],
          capture_output=True,
          text=True,
      )
      self.assertNotEqual(rejected.returncode, 0)
      self.assertIn("changed skip-worktree node type", rejected.stderr)

  def test_formal_runner_rejects_symlinked_package_node(self):
    runner = Path(__file__).with_name("run-stock-formal-dataset.sh")
    with tempfile.TemporaryDirectory() as temp:
      package = Path(temp) / "package"
      properties = package / "corpus/properties"
      properties.mkdir(parents=True)
      (package / "artifact-manifest.json").write_text("{}\n", encoding="utf-8")
      (package / "candidate-manifest-valkyrie-formal.json").write_text(
          "{}\n", encoding="utf-8"
      )
      prop = properties / "unreach-call.prp"
      prop.write_text("CHECK\n", encoding="utf-8")
      command = 'source "$1"; validate_formal_package_topology "$2"'
      subprocess.run(
          ["bash", "-c", command, "bash", str(runner), str(package)],
          check=True,
      )
      prop.unlink()
      prop.symlink_to("/dev/null")
      rejected = subprocess.run(
          ["bash", "-c", command, "bash", str(runner), str(package)],
          capture_output=True,
          text=True,
      )
      self.assertNotEqual(rejected.returncode, 0)
      self.assertIn("node topology is not frozen", rejected.stderr)
      prop.unlink()
      prop.write_text("CHECK\n", encoding="utf-8")
      package_link = Path(temp) / "package-link"
      package_link.symlink_to(package, target_is_directory=True)
      rejected = subprocess.run(
          ["bash", "-c", command, "bash", str(runner), str(package_link)],
          capture_output=True,
          text=True,
      )
      self.assertNotEqual(rejected.returncode, 0)
      self.assertIn("node topology is not frozen", rejected.stderr)

  def test_formal_runner_rejects_output_overlap_in_both_directions(self):
    runner = Path(__file__).with_name("run-stock-formal-dataset.sh")
    command = 'source "$1"; reject_output_overlap "$2" "$3"'
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      input_tree = root / "inputs"
      input_tree.mkdir()
      source = input_tree / "manifest.json"
      source.write_text("{}\n", encoding="utf-8")
      safe_output = root / "separate/output"
      subprocess.run(
          ["bash", "-c", command, "bash", str(runner), str(safe_output), str(source)],
          check=True,
      )
      nested_output = input_tree / "results"
      rejected = subprocess.run(
          ["bash", "-c", command, "bash", str(runner), str(nested_output), str(source)],
          capture_output=True,
          text=True,
      )
      self.assertNotEqual(rejected.returncode, 0)
      self.assertIn("output overlaps input tree", rejected.stderr)

      outer_output = root / "outer"
      nested_input = outer_output / "package"
      nested_input.mkdir(parents=True)
      rejected = subprocess.run(
          ["bash", "-c", command, "bash", str(runner), str(outer_output), str(nested_input)],
          capture_output=True,
          text=True,
      )
      self.assertNotEqual(rejected.returncode, 0)
      self.assertIn("input overlaps output tree", rejected.stderr)

  def test_formal_runner_rejects_java_output_overlap_before_initialization(self):
    runner = Path(__file__).with_name("run-stock-formal-dataset.sh")
    command = 'source "$1"; reject_output_overlap "$2" "$3"'
    with tempfile.TemporaryDirectory() as temp:
      java_home = Path(temp) / "jdk"
      java_home.mkdir()
      rejected = subprocess.run(
          [
              "bash",
              "-c",
              command,
              "bash",
              str(runner),
              str(java_home / "formal-output"),
              str(java_home),
          ],
          capture_output=True,
          text=True,
      )
      self.assertNotEqual(rejected.returncode, 0)
      self.assertIn("output overlaps input tree", rejected.stderr)
      self.assertFalse((java_home / "formal-output").exists())

  def test_formal_runner_executes_saved_script_and_cleans_monitor(self):
    runner = Path(__file__).with_name("run-stock-formal-dataset.sh")
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      research = root / "research"
      script_dir = research / "scripts/vguide"
      script_dir.mkdir(parents=True)
      for name, content in (
          ("run-stock-formal-dataset.sh", "#!/usr/bin/env bash\n"),
          ("dataset.py", "#!/usr/bin/env python3\n"),
          (
              "baseline.py",
              (
                  "#!/usr/bin/env python3\n"
                  "import pathlib,sys\n"
                  'pathlib.Path(sys.argv[1]).write_text("saved\\n")\n'
              ),
          ),
      ):
        path = script_dir / name
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)
      subprocess.run(["git", "init", "-q", research], check=True)
      subprocess.run(
          ["git", "-C", research, "config", "user.email", "test@example.com"],
          check=True,
      )
      subprocess.run(
          ["git", "-C", research, "config", "user.name", "Test"], check=True
      )
      subprocess.run(["git", "-C", research, "add", "."], check=True)
      subprocess.run(
          ["git", "-C", research, "commit", "-qm", "fixture"], check=True
      )
      saved = root / "saved"
      marker = root / "marker"
      command = """
source "$1"
SCRIPT_DIR=$2
RESEARCH_ROOT=$3
capture_research_provenance "$4"
activate_saved_scripts "$4"
run_python_script "$BASELINE_PY" "$5"
verify_research_provenance "$4"
"""
      subprocess.run(
          [
              "bash",
              "-c",
              command,
              "bash",
              str(runner),
              str(script_dir),
              str(research),
              str(saved),
              str(marker),
          ],
          check=True,
      )
      self.assertEqual(marker.read_text(encoding="utf-8"), "saved\n")

      provenance = root / "monitor"
      provenance.mkdir()
      monitor = provenance / "load-monitor.jsonl"
      command = """
source "$1"
DATASET_PY=$3
P_CORES=0,2,4,6,8,10,12,14
record_process_snapshot "$2"
start_process_monitor "$4"
pid=$MONITOR_PID
taskset -pc "$pid" | grep -q '16-23'
sleep 1.25
stop_process_monitor
! kill -0 "$pid" 2>/dev/null
"""
      subprocess.run(
          [
              "bash",
              "-c",
              command,
              "bash",
              str(runner),
              str(provenance),
              str(Path(__file__).with_name("dataset.py")),
              str(monitor),
          ],
          check=True,
      )
      self.assertIn("PID", (provenance / "process-start.txt").read_text())
      self.assertIn("PSR", (provenance / "process-start.txt").read_text())
      samples = monitor.read_text(encoding="utf-8").splitlines()
      self.assertEqual(
          json.loads(samples[0])["foreign_process_cpu_percent"], 50.0
      )
      self.assertIn("timestamp", json.loads(samples[1]))
      stopped = Path(f"{monitor}.stopped").read_text()
      self.assertIn("exit=0", stopped)
      self.assertIn("samples=", stopped)
      command = """
source "$1"
MONITOR_ACTIVE=false
MONITOR_PID=
stop_process_monitor_for_teardown
"""
      subprocess.run(
          ["bash", "-c", command, "bash", str(runner), str(provenance)],
          check=True,
      )

      killed = root / "killed-monitor"
      killed.mkdir()
      killed_monitor = killed / "load-monitor.jsonl"
      command = """
source "$1"
DATASET_PY=$2
P_CORES=0,2,4,6,8,10,12,14
start_process_monitor "$3"
pid=$MONITOR_PID
sleep 0.1
kill -9 "$pid"
wait "$pid" 2>/dev/null || :
if stop_process_monitor; then
  exit 1
fi
"""
      subprocess.run(
          [
              "bash",
              "-c",
              command,
              "bash",
              str(runner),
              str(Path(__file__).with_name("dataset.py")),
              str(killed_monitor),
          ],
          check=True,
      )
      self.assertFalse(Path(f"{killed_monitor}.stopped").exists())

      command = """
source "$1"
child_file=$2
sleep 0.2 &
MONITOR_PID=$!
setsid bash -c '
  exec python3 -c '"'"'
import os
import signal
import sys
import time

child = os.fork()
if child == 0:
  os.setpgrp()
  signal.signal(signal.SIGTERM, signal.SIG_IGN)
  with open(sys.argv[1], "w") as output:
    output.write(str(os.getpid()))
  time.sleep(60)
else:
  signal.signal(signal.SIGTERM, signal.SIG_IGN)
  os.wait()
'"'"' "$1"
' bash "$child_file" &
benchmark=$!
while [[ ! -s "$child_file" ]]; do sleep 0.01; done
child=$(cat "$child_file")
systemctl() {
  return 1
}
if wait_for_benchmark_with_monitor test.scope "$benchmark"; then
  exit 1
fi
! kill -0 "$benchmark" 2>/dev/null
for _ in {1..40}; do
  if ! kill -0 "$child" 2>/dev/null; then
    exit 0
  fi
  sleep 0.05
done
exit 1
"""
      child_file = root / "benchmark-child.pid"
      stopped = subprocess.run(
          ["bash", "-c", command, "bash", str(runner), str(child_file)],
          capture_output=True,
          text=True,
          timeout=5,
      )
      self.assertEqual(stopped.returncode, 0, stopped.stderr)
      self.assertIn("terminating owned session", stopped.stderr)
      self.assertIn("process monitor died during BenchExec", stopped.stderr)

  def test_formal_runner_reverifies_runtime_closure(self):
    runner = Path(__file__).with_name("run-stock-formal-dataset.sh")
    baseline_path = Path(__file__).with_name("baseline.py")
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)

      def repository(name):
        path = root / name
        path.mkdir()
        subprocess.run(["git", "init", "-q", path], check=True)
        subprocess.run(
            ["git", "-C", path, "config", "user.email", "test@example.com"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", path, "config", "user.name", "Test"], check=True
        )
        return path

      stock, sv_benchmarks, benchexec = (
          repository("stock"),
          repository("sv-benchmarks"),
          repository("benchexec"),
      )
      (stock / "lib/java").mkdir(parents=True)
      (stock / "lib/java/runtime.jar").write_bytes(b"runtime")
      (stock / ".gitignore").write_text(
          "cpachecker.jar\nclasses/\nlib/java/*.jar\n", encoding="utf-8"
      )
      (sv_benchmarks / "task").write_text("task\n", encoding="utf-8")
      (benchexec / "module.py").write_text("VERSION = 1\n", encoding="utf-8")
      for repository_path in (stock, sv_benchmarks, benchexec):
        subprocess.run(["git", "-C", repository_path, "add", "."], check=True)
        subprocess.run(
            ["git", "-C", repository_path, "commit", "-qm", "fixture"],
            check=True,
        )
      with zipfile.ZipFile(stock / "cpachecker.jar", "w") as jar:
        jar.writestr("entry", b"first")
      java_home = root / "jdk"
      java_home.mkdir()
      (java_home / "release").write_text("JAVA_VERSION=21\n", encoding="utf-8")
      ant_install = root / "ant/usr"
      ant_home = ant_install / "share/ant"
      (ant_home / "bin").mkdir(parents=True)
      ant = ant_home / "bin/ant"
      ant.write_text('#!/bin/sh\nprintf "test-ant\\n"\n', encoding="utf-8")
      ant.chmod(0o755)
      python_stdlib = root / "python-stdlib"
      python_dist_packages = root / "python-dist-packages"
      python_local_dist_packages = root / "python-local-dist-packages"
      for path, content in (
          (python_stdlib, b"stdlib"),
          (python_dist_packages, b"dist-packages"),
          (python_local_dist_packages, b"local-dist-packages"),
      ):
        path.mkdir()
        (path / "closure").write_bytes(content)

      setup = """
source "$1"
SCRIPT_DIR=$(dirname "$2")
BASELINE_PY=$2
CPACHECKER_DIR=$3
SV_BENCHMARKS_DIR=$4
BENCHEXEC_DIR=$5
JAVA_HOME=$6
ANT_HOME=$7
ANT_INSTALL=$8
ANT_BIN=$ANT_HOME/bin/ant
PYTHON_STDLIB=$9
PYTHON_DIST_PACKAGES=${10}
PYTHON_LOCAL_DIST_PACKAGES=${11}
EXPECTED_CPACHECKER=$(git -C "$CPACHECKER_DIR" rev-parse HEAD)
EXPECTED_SV_BENCHMARKS=$(git -C "$SV_BENCHMARKS_DIR" rev-parse HEAD)
EXPECTED_BENCHEXEC=$(git -C "$BENCHEXEC_DIR" rev-parse HEAD)
EXPECTED_STOCK_LIB_JAVA=$(directory_digest_value "$CPACHECKER_DIR/lib/java")
EXPECTED_JDK=$(directory_digest_value "$JAVA_HOME")
EXPECTED_ANT_INSTALL=$(directory_digest_value "$ANT_INSTALL")
EXPECTED_ANT_VERSION=test-ant
EXPECTED_PYTHON_REAL=$PYTHON_BIN
EXPECTED_PYTHON_SHA256=$(sha256sum "$PYTHON_BIN" | cut -d' ' -f1)
EXPECTED_PYTHON_VERSION=$("$PYTHON_BIN" --version)
EXPECTED_PYTHON_STDLIB=$PYTHON_STDLIB
EXPECTED_PYTHON_STDLIB_DIGEST=$(directory_digest_value "$PYTHON_STDLIB")
EXPECTED_PYTHON_DIST_PACKAGES=$PYTHON_DIST_PACKAGES
EXPECTED_PYTHON_DIST_PACKAGES_DIGEST=$(directory_digest_value "$PYTHON_DIST_PACKAGES")
EXPECTED_PYTHON_LOCAL_DIST_PACKAGES=$PYTHON_LOCAL_DIST_PACKAGES
EXPECTED_PYTHON_LOCAL_DIST_PACKAGES_DIGEST=$(directory_digest_value "$PYTHON_LOCAL_DIST_PACKAGES")
EXPECTED_PYTHON_SYSTEM_PATH=$("$PYTHON_BIN" -I -c 'import sys; print(":".join(sys.path))')
EXPECTED_PYYAML_FILE=$("$PYTHON_BIN" -I -c 'import yaml; print(yaml.__file__)')
EXPECTED_PYYAML_VERSION=$("$PYTHON_BIN" -I -c 'import yaml; print(yaml.__version__)')
EXPECTED_BENCHEXEC_ARCHIVE=$(benchexec_archive_digest)
EXPECTED_BENCHEXEC_VERSION=test-benchexec
EXPECTED_CPACHECKER_JAR_CONTENT=$(jar_content_digest_value "$CPACHECKER_DIR/cpachecker.jar")
benchexec_version() { printf 'test-benchexec\\n'; }
"""
      arguments = [
          str(runner),
          str(baseline_path),
          str(stock),
          str(sv_benchmarks),
          str(benchexec),
          str(java_home),
          str(ant_home),
          str(ant_install),
          str(python_stdlib),
          str(python_dist_packages),
          str(python_local_dist_packages),
      ]
      subprocess.run(
          ["bash", "-c", setup + "\nverify_runtime_closure true", "bash", *arguments],
          check=True,
      )

      original_runtime = (stock / "lib/java/runtime.jar").read_bytes()
      stock_lib_digest = dataset.baseline.directory_digest(stock / "lib/java")["sha256"]
      (stock / "lib/java/runtime.jar").write_bytes(b"changed runtime")
      rejected = subprocess.run(
          [
              "bash",
              "-c",
              setup
              + f"\nEXPECTED_STOCK_LIB_JAVA={stock_lib_digest}\n"
              + "verify_runtime_closure true",
              "bash",
              *arguments,
          ],
      )
      self.assertNotEqual(rejected.returncode, 0)
      (stock / "lib/java/runtime.jar").write_bytes(original_runtime)

      for closure_dir, expected_variable, original in (
          (python_stdlib, "EXPECTED_PYTHON_STDLIB_DIGEST", b"stdlib"),
          (
              python_dist_packages,
              "EXPECTED_PYTHON_DIST_PACKAGES_DIGEST",
              b"dist-packages",
          ),
          (
              python_local_dist_packages,
              "EXPECTED_PYTHON_LOCAL_DIST_PACKAGES_DIGEST",
              b"local-dist-packages",
          ),
      ):
        original_digest = dataset.baseline.directory_digest(closure_dir)["sha256"]
        (closure_dir / "closure").write_bytes(b"changed")
        rejected = subprocess.run(
            [
                "bash",
                "-c",
                setup
                + f"\n{expected_variable}={original_digest}\n"
                + "verify_runtime_closure true",
                "bash",
                *arguments,
            ],
        )
        self.assertNotEqual(rejected.returncode, 0)
        (closure_dir / "closure").write_bytes(original)

      original_ant = ant.read_text(encoding="utf-8")
      ant_digest = dataset.baseline.directory_digest(ant_install)["sha256"]
      ant.write_text(original_ant + "# drift\n", encoding="utf-8")
      rejected = subprocess.run(
          [
              "bash",
              "-c",
              setup
              + f"\nEXPECTED_ANT_INSTALL={ant_digest}\n"
              + "verify_runtime_closure true",
              "bash",
              *arguments,
          ],
      )
      self.assertNotEqual(rejected.returncode, 0)
      ant.write_text(original_ant, encoding="utf-8")

      rejected = subprocess.run(
          [
              "bash",
              "-c",
              setup
              + "\nEXPECTED_PYTHON_SHA256=wrong\n"
              + "verify_runtime_closure true",
              "bash",
              *arguments,
          ],
      )
      self.assertNotEqual(rejected.returncode, 0)

      for variable in (
          "EXPECTED_PYTHON_SYSTEM_PATH",
          "EXPECTED_PYYAML_FILE",
          "EXPECTED_PYYAML_VERSION",
      ):
        rejected = subprocess.run(
            [
                "bash",
                "-c",
                setup
                + f"\n{variable}=wrong\n"
                + "verify_runtime_closure true",
                "bash",
                *arguments,
            ],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("unexpected", rejected.stderr)

      classes = stock / "classes"
      classes.mkdir()
      (classes / "Injected.class").write_bytes(b"injected")
      rejected = subprocess.run(
          [
              "bash",
              "-c",
              setup + "\nverify_runtime_closure true",
              "bash",
              *arguments,
          ],
          capture_output=True,
          text=True,
      )
      self.assertNotEqual(rejected.returncode, 0)
      self.assertIn("could shadow the pinned JAR", rejected.stderr)
      subprocess.run(
          [
              "bash",
              "-c",
              setup + "\nremove_compiled_classes\nassert_no_compiled_classes",
              "bash",
              *arguments,
          ],
          check=True,
      )
      self.assertFalse(classes.exists())

      with zipfile.ZipFile(stock / "cpachecker.jar", "w") as jar:
        jar.writestr("entry", b"changed")
      rejected = subprocess.run(
          [
              "bash",
              "-c",
              setup
              + "\nEXPECTED_CPACHECKER_JAR_CONTENT=wrong\n"
              + "verify_runtime_closure true",
              "bash",
              *arguments,
          ],
      )
      self.assertNotEqual(rejected.returncode, 0)

  def test_formal_runner_copies_relative_evidence_for_reauthentication(self):
    runner = Path(__file__).with_name("run-stock-formal-dataset.sh")
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      fixture = phase_b_fixture(root / "fixture")
      evidence = root / "output/evidence"
      arguments = [
          str(runner),
          str(evidence),
          fixture.parent_manifest,
          *fixture.phase_a_manifest,
          *fixture.phase_a_result,
          *fixture.survivor_manifest,
      ]
      command = """
source "$1"
PARENT_MANIFEST=$3
PHASE_MANIFESTS=("$4" "$5" "$6")
PHASE_RESULTS=("$7" "$8" "$9")
PHASE_SURVIVORS=("${10}" "${11}" "${12}")
copy_phase_evidence "$2"
"""
      subprocess.run(["bash", "-c", command, "bash", *arguments], check=True)
      expected = {
          "parent-manifest.json",
          "original-manifest.json",
          "original-result.xml",
          "original-survivor.json",
          "reroute-manifest.json",
          "reroute-result.xml",
          "reroute-survivor.json",
          "recovery-manifest.json",
          "recovery-result.xml",
          "recovery-survivor.json",
          "corpus/properties/unreach-call.prp",
          "inventory.sha256",
      }
      self.assertEqual(
          {
              path.relative_to(evidence).as_posix()
              for path in evidence.rglob("*")
              if path.is_file()
          },
          expected,
      )
      inventory = (evidence / "inventory.sha256").read_text(encoding="utf-8")
      self.assertNotIn(str(root), inventory)
      self.assertNotIn("inventory.sha256", inventory)
      copied = SimpleNamespace(
          parent_manifest=str(evidence / "parent-manifest.json"),
          phase_a_manifest=[
              str(evidence / f"{role}-manifest.json")
              for role in ("original", "reroute", "recovery")
          ],
          phase_a_result=[
              str(evidence / f"{role}-result.xml")
              for role in ("original", "reroute", "recovery")
          ],
          survivor_manifest=[
              str(evidence / f"{role}-survivor.json")
              for role in ("original", "reroute", "recovery")
          ],
          sv_benchmarks=fixture.sv_benchmarks,
      )
      with phase_b_pins(fixture):
        _, _, authenticated = dataset.authenticate_phase_b_inputs(copied)
      self.assertEqual(len(authenticated["tasks"]), 6)

  def test_dataset_runner_finds_only_exact_screen_result_forms(self):
    runner = Path(__file__).with_name("run-stock-dataset.sh").read_text(
        encoding="utf-8"
    )
    start = runner.index("single_result() {")
    end = runner.index("\n}\n\nrun_benchexec", start) + 3
    function = runner[start:end]
    expected_names = (
        "run.results.hard-case-candidates.xml",
        "run.results.hard-case-candidates.xml.bz2",
        "run.results.hard-case-candidates.official.xml",
        "run.results.hard-case-candidates.official.xml.bz2",
    )
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      for index, name in enumerate(expected_names):
        directory = root / str(index)
        directory.mkdir()
        expected = directory / name
        expected.touch()
        (directory / "run.results.hard-case-candidates.external.xml.bz2").touch()
        (directory / f"{name}.txt").touch()
        nested = directory / "nested"
        nested.mkdir()
        (nested / name).touch()
        found = subprocess.check_output(
            ["bash", "-c", f'{function}\nsingle_result "$1"', "bash", directory],
            text=True,
        ).splitlines()
        self.assertEqual(found, [str(expected)])

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

  def test_phase_b_survivors_merge_by_effective_host_and_recompute_results(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      fixture = phase_b_fixture(root)
      output = root / "merged"
      args = SimpleNamespace(
          **phase_b_inputs(fixture),
          output_dir=str(output),
      )
      with phase_b_pins(fixture):
        dataset.command_merge_survivors(args)

      manifest_path = output / "candidate-manifest-valkyrie-formal.json"
      manifest = dataset.validate_manifest(manifest_path, root)
      self.assertEqual(
          dataset.baseline.sha256_file(manifest_path), fixture.formal_hash
      )
      self.assertEqual(manifest["derivation"]["host"], "valkyrie")
      self.assertEqual(manifest["tasks"], fixture.rows)
      self.assertEqual(
          {
              path.relative_to(output).as_posix()
              for path in output.rglob("*")
              if path.is_file()
          },
          {
              "artifact-manifest.json",
              "candidate-manifest-valkyrie-formal.json",
              "corpus/properties/unreach-call.prp",
          },
      )
      artifact = json.loads((output / "artifact-manifest.json").read_text())
      self.assertEqual(artifact["root"], ".")
      self.assertEqual(artifact["file_count"], len(artifact["files"]))
      self.assertEqual(
          [row["path"] for row in artifact["files"]],
          [
              "candidate-manifest-valkyrie-formal.json",
              "corpus/properties/unreach-call.prp",
          ],
      )
      aggregate = hashlib.sha256()
      for row in artifact["files"]:
        aggregate.update(row["path"].encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(bytes.fromhex(row["sha256"]))
      self.assertEqual(artifact["aggregate_sha256"], aggregate.hexdigest())
      self.assertFalse(
          (output / "candidate-manifest-publication-union.json").exists()
      )
      with phase_b_pins(fixture), self.assertRaisesRegex(
          RuntimeError, "formal manifest hash is not the frozen"
      ):
        changed = copy.deepcopy(manifest)
        changed["derivation"]["operation"] = "changed"
        changed_path = output / "changed-formal.json"
        changed_path.write_text(json.dumps(changed), encoding="utf-8")
        dataset.command_render_formal(
            SimpleNamespace(
                **phase_b_inputs(fixture),
                manifest=str(changed_path),
                property_file=str(root / "c/properties/unreach-call.prp"),
                output_dir=str(root / "not-runnable"),
            )
        )

      args.phase_a_result = fixture.phase_a_result[:2]
      args.output_dir = str(root / "missing-result")
      with phase_b_pins(fixture), self.assertRaisesRegex(
          RuntimeError, "exactly three"
      ):
        dataset.command_merge_survivors(args)
      args.phase_a_result = fixture.phase_a_result

      phase = Path(fixture.phase_a_manifest[0])
      original_phase = phase.read_text(encoding="utf-8")
      phase.write_text(
          json.dumps(json.loads(original_phase), indent=2), encoding="utf-8"
      )
      args.output_dir = str(root / "changed-phase-manifest")
      with phase_b_pins(fixture), self.assertRaisesRegex(
          RuntimeError, "manifest hash is not a distinct frozen input"
      ):
        dataset.command_merge_survivors(args)
      phase.write_text(original_phase, encoding="utf-8")

      result = Path(fixture.phase_a_result[0])
      survivor_path = Path(fixture.survivor_manifest[0])
      role = next(iter(dataset.PHASE_A_OPERATION))
      original_result = result.read_text(encoding="utf-8")
      original_survivor = survivor_path.read_text(encoding="utf-8")
      original_result_pin = fixture.result_hashes[role]
      original_survivor_pin = fixture.survivor_hashes[role]

      result.write_text(original_result + "\n", encoding="utf-8")
      args.output_dir = str(root / "changed-result-identity")
      with phase_b_pins(fixture), self.assertRaisesRegex(
          RuntimeError, "result hash is not a distinct frozen input"
      ):
        dataset.command_merge_survivors(args)
      result.write_text(original_result, encoding="utf-8")

      survivor = json.loads(original_survivor)
      survivor_path.write_text(
          json.dumps(survivor, indent=2), encoding="utf-8"
      )
      args.output_dir = str(root / "changed-survivor-identity")
      with phase_b_pins(fixture), self.assertRaisesRegex(
          RuntimeError, "survivor manifest hash is not a distinct frozen input"
      ):
        dataset.command_merge_survivors(args)
      survivor_path.write_text(original_survivor, encoding="utf-8")

      result_root = ET.parse(result).getroot()
      result_root.set("version", "changed")
      ET.ElementTree(result_root).write(result, encoding="unicode")
      fixture.result_hashes[role] = dataset.baseline.sha256_file(result)
      args.output_dir = str(root / "wrong-version")
      with phase_b_pins(fixture), self.assertRaisesRegex(RuntimeError, "metadata"):
        dataset.command_merge_survivors(args)
      result.write_text(original_result, encoding="utf-8")
      fixture.result_hashes[role] = original_result_pin

      result_root = ET.parse(result).getroot()
      result_root.set("error", "incomplete")
      ET.ElementTree(result_root).write(result, encoding="unicode")
      fixture.result_hashes[role] = dataset.baseline.sha256_file(result)
      args.output_dir = str(root / "incomplete-result")
      with phase_b_pins(fixture), self.assertRaisesRegex(RuntimeError, "metadata"):
        dataset.command_merge_survivors(args)
      result.write_text(original_result, encoding="utf-8")
      fixture.result_hashes[role] = original_result_pin

      result_root = ET.parse(result).getroot()
      del result_root.attrib["endtime"]
      ET.ElementTree(result_root).write(result, encoding="unicode")
      fixture.result_hashes[role] = dataset.baseline.sha256_file(result)
      args.output_dir = str(root / "missing-endtime")
      with phase_b_pins(fixture), self.assertRaisesRegex(
          RuntimeError, "end time"
      ):
        dataset.command_merge_survivors(args)
      result.write_text(original_result, encoding="utf-8")
      fixture.result_hashes[role] = original_result_pin

      result_root = ET.parse(result).getroot()
      result_root.find("run").set("properties", "termination")
      ET.ElementTree(result_root).write(result, encoding="unicode")
      fixture.result_hashes[role] = dataset.baseline.sha256_file(result)
      args.output_dir = str(root / "wrong-property")
      with phase_b_pins(fixture), self.assertRaisesRegex(
          RuntimeError, "property is not unreach-call"
      ):
        dataset.command_merge_survivors(args)
      result.write_text(original_result, encoding="utf-8")
      fixture.result_hashes[role] = original_result_pin

      result_root = ET.parse(result).getroot()
      result_root.find("run").set(
          "propertyFile",
          "../../evil/../../../../sv-benchmarks/c/properties/unreach-call.prp",
      )
      ET.ElementTree(result_root).write(result, encoding="unicode")
      fixture.result_hashes[role] = dataset.baseline.sha256_file(result)
      args.output_dir = str(root / "wrong-property-file")
      with phase_b_pins(fixture), self.assertRaisesRegex(
          RuntimeError, "property file is not exact"
      ):
        dataset.command_merge_survivors(args)
      result.write_text(original_result, encoding="utf-8")
      fixture.result_hashes[role] = original_result_pin

      result_root = ET.parse(result).getroot()
      result_root.find("run").set(
          "files", "[../../evil/../../../../sv-benchmarks/s0.c]"
      )
      ET.ElementTree(result_root).write(result, encoding="unicode")
      fixture.result_hashes[role] = dataset.baseline.sha256_file(result)
      args.output_dir = str(root / "wrong-source-files")
      with phase_b_pins(fixture), self.assertRaisesRegex(
          RuntimeError, "source files do not match"
      ):
        dataset.command_merge_survivors(args)
      result.write_text(original_result, encoding="utf-8")
      fixture.result_hashes[role] = original_result_pin

      result_root = ET.parse(result).getroot()
      result_root.find("run").set(
          "name", "../../evil/../../../../sv-benchmarks/t0.yml"
      )
      ET.ElementTree(result_root).write(result, encoding="unicode")
      fixture.result_hashes[role] = dataset.baseline.sha256_file(result)
      args.output_dir = str(root / "wrong-task-path")
      with phase_b_pins(fixture), self.assertRaisesRegex(
          RuntimeError, "task path is not exact"
      ):
        dataset.command_merge_survivors(args)
      result.write_text(original_result, encoding="utf-8")
      fixture.result_hashes[role] = original_result_pin

      result_root = ET.parse(result).getroot()
      result_root.find("run").set("unexpected", "attribute")
      ET.ElementTree(result_root).write(result, encoding="unicode")
      fixture.result_hashes[role] = dataset.baseline.sha256_file(result)
      args.output_dir = str(root / "wrong-run-topology")
      with phase_b_pins(fixture), self.assertRaisesRegex(
          RuntimeError, "run topology is not exact"
      ):
        dataset.command_merge_survivors(args)
      result.write_text(original_result, encoding="utf-8")
      fixture.result_hashes[role] = original_result_pin

      result_root = ET.parse(result).getroot()
      result_root.find("systeminfo").set("hostname", "athena")
      ET.ElementTree(result_root).write(result, encoding="unicode")
      fixture.result_hashes[role] = dataset.baseline.sha256_file(result)
      args.output_dir = str(root / "wrong-host")
      with phase_b_pins(fixture), self.assertRaisesRegex(RuntimeError, "hostname"):
        dataset.command_merge_survivors(args)
      result.write_text(original_result, encoding="utf-8")
      fixture.result_hashes[role] = original_result_pin

      result_root = ET.parse(result).getroot()
      result_root.find("run/column[@title='status']").set("value", "true")
      result_root.find("run/column[@title='category']").set("value", "correct")
      ET.ElementTree(result_root).write(result, encoding="unicode")
      fixture.result_hashes[role] = dataset.baseline.sha256_file(result)
      survivor = json.loads(survivor_path.read_text())
      survivor["derivation"]["result_sha256"] = dataset.baseline.sha256_file(result)
      survivor_path.write_text(json.dumps(survivor), encoding="utf-8")
      fixture.survivor_hashes[role] = dataset.baseline.sha256_file(
          survivor_path
      )
      args.output_dir = str(root / "rejected")
      with phase_b_pins(fixture), self.assertRaisesRegex(RuntimeError, "recomputed"):
        dataset.command_merge_survivors(args)
      fixture.result_hashes[role] = original_result_pin
      fixture.survivor_hashes[role] = original_survivor_pin

  def test_phase_b_formal_summary_is_fixed_distinct_and_same_host(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      fixture = phase_b_fixture(root)
      inputs = phase_b_inputs(fixture)
      merged = root / "merged"
      with phase_b_pins(fixture):
        dataset.command_merge_survivors(
            SimpleNamespace(**inputs, output_dir=str(merged))
        )
      manifest = merged / "candidate-manifest-valkyrie-formal.json"
      generated = root / "generated"
      with phase_b_pins(fixture):
        dataset.command_render_formal(
            SimpleNamespace(
                **inputs,
                manifest=str(manifest),
                property_file=str(root / "c/properties/unreach-call.prp"),
              output_dir=str(generated),
            )
        )
      with phase_b_pins(fixture), self.assertRaisesRegex(
          RuntimeError, "output directory must be absent or empty"
      ):
        dataset.command_render_formal(
            SimpleNamespace(
                **inputs,
                manifest=str(manifest),
                property_file=str(root / "c/properties/unreach-call.prp"),
                output_dir=str(generated),
            )
        )
      definition = generated / "hard-case-candidates.xml"
      tasks = json.loads(manifest.read_text())["tasks"]
      first, second = root / "formal-1.xml", root / "formal-2.xml"
      write_stock_result(first, tasks, "valkyrie", formal=True, marker="1")
      write_stock_result(second, tasks, "valkyrie", formal=True, marker="2")
      plan_counter = 0

      def summarize(name, results, benchmark=definition):
        nonlocal plan_counter
        plan_counter += 1
        plans = []
        for repetition, result in enumerate(results, 1):
          plan = root / f"plan-{plan_counter}-{repetition}.json"
          dataset.command_repetition_plan(
              SimpleNamespace(
                  manifest=str(manifest),
                  repetition=repetition,
                  primary_result=str(result),
                  taint_manifest=None,
                  replacement_result=None,
                  replacement_definition=None,
                  output=str(plan),
              )
          )
          plans.append(plan)
        with phase_b_pins(fixture):
          dataset.command_summarize(
              SimpleNamespace(
                  **inputs,
                  manifest=str(manifest),
                  benchmark_definition=str(benchmark),
                  repetition_plan=[str(path) for path in plans],
                  output_dir=str(root / name),
                  hard_threshold=200,
              )
          )

      summarize("accepted", [first, second])
      with self.assertRaisesRegex(
          RuntimeError, "output directory must be absent or empty"
      ):
        summarize("accepted", [first, second])
      with self.assertRaisesRegex(RuntimeError, "fixed at 200"):
        with phase_b_pins(fixture):
          dataset.command_summarize(
              SimpleNamespace(
                  **inputs,
                  manifest=str(manifest),
                  benchmark_definition=str(definition),
                  repetition_plan=[
                      str(root / "plan-1-1.json"),
                      str(root / "plan-1-2.json"),
                  ],
                  output_dir=str(root / "wrong-threshold"),
                  hard_threshold=201,
              )
          )
      invalid = root / "invalid.xml"
      write_stock_result(invalid, tasks, "athena", formal=True)
      with self.assertRaisesRegex(RuntimeError, "merged manifest host"):
        summarize("cross-host", [first, invalid])
      write_stock_result(invalid, tasks, "valkyrie")
      with self.assertRaisesRegex(RuntimeError, "metadata"):
        summarize("wrong-limit", [first, invalid])
      write_stock_result(
          invalid, tasks, "valkyrie", formal=True, omit="walltime"
      )
      with self.assertRaisesRegex(RuntimeError, "incomplete primary rows"):
        summarize("missing-metric", [first, invalid])
      invalid_root = ET.parse(second).getroot()
      invalid_root.find("run").set(
          "propertyFile",
          "../../evil/../../../../sv-benchmarks/c/properties/unreach-call.prp",
      )
      ET.ElementTree(invalid_root).write(invalid, encoding="unicode")
      with self.assertRaisesRegex(RuntimeError, "property file is not exact"):
        summarize("formal-wrong-property", [first, invalid])
      invalid_root = ET.parse(second).getroot()
      invalid_root.find("run").set(
          "files", "[../../evil/../../../../sv-benchmarks/s0.c]"
      )
      ET.ElementTree(invalid_root).write(invalid, encoding="unicode")
      with self.assertRaisesRegex(RuntimeError, "source files do not match"):
        summarize("formal-wrong-source", [first, invalid])
      invalid_root = ET.parse(second).getroot()
      invalid_root.find("run").set(
          "name", "../../evil/../../../../sv-benchmarks/t0.yml"
      )
      ET.ElementTree(invalid_root).write(invalid, encoding="unicode")
      with self.assertRaisesRegex(RuntimeError, "task path is not exact"):
        summarize("formal-wrong-task-path", [first, invalid])
      with self.assertRaisesRegex(RuntimeError, "distinct"):
        summarize("duplicate", [first, first])
      invalid_root = ET.parse(second).getroot()
      invalid_root.set("starttime", ET.parse(first).getroot().get("starttime"))
      ET.ElementTree(invalid_root).write(invalid, encoding="unicode")
      with self.assertRaisesRegex(RuntimeError, "distinct starttime"):
        summarize("duplicate-starttime", [first, invalid])
      invalid_root = ET.parse(second).getroot()
      invalid_root.set(
          "benchmarkname", ET.parse(first).getroot().get("benchmarkname")
      )
      ET.ElementTree(invalid_root).write(invalid, encoding="unicode")
      with self.assertRaisesRegex(RuntimeError, "distinct benchmarkname"):
        summarize("duplicate-benchmarkname", [first, invalid])
      changed = root / "changed-definition.xml"
      definition_root = ET.parse(definition).getroot()
      definition_root.set("hardtimelimit", "120 s")
      ET.ElementTree(definition_root).write(changed, encoding="unicode")
      with self.assertRaisesRegex(RuntimeError, "900/910/920"):
        summarize("wrong-definition", [first, second], changed)
      extra = root / "extra-definition.xml"
      definition_root = ET.parse(definition).getroot()
      ET.SubElement(definition_root, "option", {"name": "--extra"})
      ET.ElementTree(definition_root).write(extra, encoding="unicode")
      with self.assertRaisesRegex(RuntimeError, "topology"):
        summarize("extra-definition", [first, second], extra)

  def test_formal_summary_replaces_only_explicitly_tainted_cases(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      fixture = phase_b_fixture(root)
      inputs = phase_b_inputs(fixture)
      merged = root / "merged"
      with phase_b_pins(fixture):
        dataset.command_merge_survivors(
            SimpleNamespace(**inputs, output_dir=str(merged))
        )
      manifest = merged / "candidate-manifest-valkyrie-formal.json"
      generated = root / "generated"
      with phase_b_pins(fixture):
        dataset.command_render_formal(
            SimpleNamespace(
                **inputs,
                manifest=str(manifest),
                property_file=str(root / "c/properties/unreach-call.prp"),
                output_dir=str(generated),
            )
        )
      definition = generated / "hard-case-candidates.xml"
      tasks = json.loads(manifest.read_text())["tasks"]
      primary, second = root / "primary.xml", root / "second.xml"
      replacement = root / "replacement.xml"
      write_stock_result(primary, tasks, "valkyrie", formal=True, marker="1")
      write_stock_result(second, tasks, "valkyrie", formal=True, marker="2")
      write_stock_result(
          replacement, tasks[:2], "valkyrie", formal=True, marker="3"
      )
      primary_root = ET.parse(primary).getroot()
      primary_root.set("error", "incomplete")
      del primary_root.attrib["endtime"]
      for column in list(primary_root.findall("run")[0]):
        primary_root.findall("run")[0].remove(column)
      ET.ElementTree(primary_root).write(primary, encoding="unicode")
      taint = root / "taint.json"
      taint.write_text(
          json.dumps(
              {
                  "schema_version": dataset.FORMAL_TAINT_SCHEMA,
                  "repetition": 1,
                  "primary_result_sha256": dataset.baseline.sha256_file(primary),
                  "tasks": [
                      {
                          "task": tasks[0]["task"],
                          "reason": "interrupted_incomplete",
                      },
                      {
                          "task": tasks[1]["task"],
                          "reason": "foreign_p_core_contention",
                      },
                  ],
              }
          ),
          encoding="utf-8",
      )
      replacement_definition = root / "replacement-definition"
      with phase_b_pins(fixture):
        dataset.command_render_formal_replacement(
            SimpleNamespace(
                **inputs,
                manifest=str(manifest),
                primary_result=str(primary),
                taint_manifest=str(taint),
                property_file=str(root / "c/properties/unreach-call.prp"),
                output_dir=str(replacement_definition),
            )
        )
      first_plan, second_plan = root / "plan-1.json", root / "plan-2.json"
      dataset.command_repetition_plan(
          SimpleNamespace(
              manifest=str(manifest),
              repetition=1,
              primary_result=str(primary),
              taint_manifest=str(taint),
              replacement_result=[str(replacement)],
              replacement_definition=[
                  str(replacement_definition / "hard-case-candidates.xml")
              ],
              output=str(first_plan),
          )
      )
      dataset.command_repetition_plan(
          SimpleNamespace(
              manifest=str(manifest),
              repetition=2,
              primary_result=str(second),
              taint_manifest=None,
              replacement_result=None,
              replacement_definition=None,
              output=str(second_plan),
          )
      )
      output = root / "summary"
      with phase_b_pins(fixture):
        dataset.command_summarize(
            SimpleNamespace(
                **inputs,
                manifest=str(manifest),
                benchmark_definition=str(definition),
                repetition_plan=[str(first_plan), str(second_plan)],
                output_dir=str(output),
                hard_threshold=200,
            )
        )
      with (output / "classification.csv").open(
          newline="", encoding="utf-8"
      ) as source:
        rows = {row["task"]: row for row in csv.DictReader(source)}
      self.assertEqual(rows[tasks[0]["task"]]["result_sources"], "replacement;primary")
      self.assertEqual(rows[tasks[1]["task"]]["result_sources"], "replacement;primary")
      self.assertEqual(rows[tasks[2]["task"]]["result_sources"], "primary;primary")
      provenance = json.loads(
          (output / "row-provenance.json").read_text(encoding="utf-8")
      )
      first_sources = {
          row["task"]: row for row in provenance["repetitions"][0]["rows"]
      }
      self.assertEqual(first_sources[tasks[0]["task"]]["source"], "replacement")
      self.assertEqual(
          first_sources[tasks[0]["task"]]["reason"], "interrupted_incomplete"
      )
      self.assertEqual(
          first_sources[tasks[1]["task"]]["reason"],
          "foreign_p_core_contention",
      )

      original_primary = primary.read_bytes()
      primary.write_bytes(original_primary + b"\n")
      with phase_b_pins(fixture), self.assertRaisesRegex(
          RuntimeError, "primary result hash"
      ):
        dataset.command_summarize(
            SimpleNamespace(
                **inputs,
                manifest=str(manifest),
                benchmark_definition=str(definition),
                repetition_plan=[str(first_plan), str(second_plan)],
                output_dir=str(root / "tampered-summary"),
                hard_threshold=200,
            )
        )
      primary.write_bytes(original_primary)

      taint_data = json.loads(taint.read_text(encoding="utf-8"))
      taint_data["tasks"] = taint_data["tasks"][1:]
      missing_taint = root / "missing-taint.json"
      missing_taint.write_text(json.dumps(taint_data), encoding="utf-8")
      invalid_plan = root / "invalid-plan.json"
      with self.assertRaisesRegex(RuntimeError, "cover exactly"):
        dataset.command_repetition_plan(
            SimpleNamespace(
                manifest=str(manifest),
                repetition=1,
                primary_result=str(primary),
                taint_manifest=str(missing_taint),
                replacement_result=[str(replacement)],
                replacement_definition=[
                    str(replacement_definition / "hard-case-candidates.xml")
                ],
                output=str(invalid_plan),
            )
        )

  def test_formal_taint_marks_only_tasks_overlapping_sustained_contention(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      tasks = [
          {
              "task": f"c/t{index}.yml",
              "task_path": f"c/t{index}.yml",
              "source_paths": [f"c/s{index}.c"],
              "expected_verdict": "true",
              "benchmark_set": "Loops",
          }
          for index in range(3)
      ]
      manifest = root / "manifest.json"
      manifest.write_text(
          json.dumps({"task_count": len(tasks), "tasks": tasks}),
          encoding="utf-8",
      )
      result = root / "result.xml"
      write_stock_result(result, tasks, "valkyrie", formal=True, marker="01")
      log = root / "benchexec.log"
      log.write_text(
          "\n".join([
              "00:00:02   starting   t0.yml",
              "00:00:02   starting   t1.yml",
              "00:00:20              t0.yml   TIMEOUT 900 18",
              "00:00:20   starting   t2.yml",
              "00:00:21              t1.yml   TIMEOUT 900 19",
              "00:00:30              t2.yml   TIMEOUT 900 10",
          ]) + "\n",
          encoding="utf-8",
      )
      monitor = root / "load.jsonl"
      monitor.write_text(
          "\n".join([
              json.dumps({
                  "schema_version": dataset.FORMAL_LOAD_MONITOR_SCHEMA,
                  "p_core_cpus": list(dataset.FORMAL_P_CORE_CPUS),
                  "foreign_process_cpu_percent": 50.0,
                  "minimum_consecutive_seconds": 10.0,
                  "sample_interval_seconds": 1.0,
                  "excluded_process_root": 123,
              }),
              *[
                json.dumps({
                  "timestamp": f"2026-07-27T00:00:{second:02d}+08:00",
                  "elapsed_seconds": 1.0,
                  "offenders": ([{
                      "pid": 456,
                      "uid": 1000,
                      "comm": "foreign",
                      "cpu_percent": 75.0,
                      "duration_seconds": 10.0,
                      "since": "2026-07-27T00:00:05+08:00",
                      "contended": True,
                  }] if second == 15 else []),
                })
                for second in range(1, 32)
              ],
          ]) + "\n",
          encoding="utf-8",
      )
      output = root / "taint.json"
      dataset.command_formal_taint(
          SimpleNamespace(
              manifest=str(manifest),
              repetition=1,
              result=str(result),
              benchexec_log=str(log),
              load_monitor=str(monitor),
              output=str(output),
          )
      )
      tainted = json.loads(output.read_text(encoding="utf-8"))["tasks"]
      self.assertEqual(
          [row["task"] for row in tainted],
          ["c/t0.yml", "c/t1.yml"],
      )

      monitor.write_text(
          "\n".join(monitor.read_text(encoding="utf-8").splitlines()[:-8])
          + "\n",
          encoding="utf-8",
      )
      tainted = dataset.formal_run_taints(result, log, monitor, {
          row["task"]: row for row in tasks
      })
      self.assertEqual(
          tainted["c/t2.yml"], "missing_load_monitor_coverage"
      )

  def test_frozen_recovery_manifest_rejects_tree_drift_and_special_nodes(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      (root / "provenance").mkdir()
      data = root / "evidence"
      data.write_text("frozen\n", encoding="utf-8")
      digest = dataset.baseline.sha256_file(data)
      aggregate = hashlib.sha256()
      aggregate.update(b"evidence\0")
      aggregate.update(bytes.fromhex(digest))
      artifact = root / "provenance/artifact-manifest.json"
      artifact.write_text(json.dumps({
          "root": "frozen-original",
          "file_count": 1,
          "aggregate_sha256": aggregate.hexdigest(),
          "files": [{
              "path": "evidence",
              "size_bytes": data.stat().st_size,
              "sha256": digest,
          }],
      }, indent=2) + "\n", encoding="utf-8")
      with mock.patch.object(
          dataset, "FROZEN_CAP8_R8_FAILURE_ROOT", "frozen-original"
      ):
        dataset.validate_frozen_artifact_manifest(
            root,
            dataset.baseline.sha256_file(artifact),
            aggregate.hexdigest(),
        )
        empty = root / "empty"
        empty.mkdir()
        with self.assertRaisesRegex(RuntimeError, "tree does not match"):
          dataset.validate_frozen_artifact_manifest(
              root,
              dataset.baseline.sha256_file(artifact),
              aggregate.hexdigest(),
          )
        empty.rmdir()
        alias = root / "directory-alias"
        alias.symlink_to(root / "provenance", target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, "unsupported"):
          dataset.validate_frozen_artifact_manifest(
              root,
              dataset.baseline.sha256_file(artifact),
              aggregate.hexdigest(),
          )
        alias.unlink()
        fifo = root / "fifo"
        os.mkfifo(fifo)
        with self.assertRaisesRegex(RuntimeError, "unsupported"):
          dataset.validate_frozen_artifact_manifest(
              root,
              dataset.baseline.sha256_file(artifact),
              aggregate.hexdigest(),
          )

  def test_phase_b_zero_survivors_are_preserved_and_skip_formal(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      fixture = phase_b_fixture(root)
      zero_phase_a_survivors(fixture)
      inputs = phase_b_inputs(fixture)
      merged = root / "merged"
      with phase_b_pins(fixture):
        dataset.command_merge_survivors(
            SimpleNamespace(**inputs, output_dir=str(merged))
        )
      manifest = merged / "candidate-manifest-valkyrie-formal.json"
      self.assertEqual(json.loads(manifest.read_text())["task_count"], 0)
      formal_args = SimpleNamespace(
          **inputs,
          manifest=str(manifest),
          property_file=str(root / "c/properties/unreach-call.prp"),
          output_dir=str(root / "formal-valkyrie"),
      )
      with phase_b_pins(fixture), self.assertRaisesRegex(
          RuntimeError, "skipped.*no tasks"
      ):
        dataset.command_render_formal(formal_args)
      with phase_b_pins(fixture), self.assertRaisesRegex(
          RuntimeError, "skipped.*no tasks"
      ):
        dataset.command_summarize(
            SimpleNamespace(
                **inputs,
                manifest=str(manifest),
                benchmark_definition=str(root / "absent.xml"),
                repetition_plan=[
                    str(root / "absent-1.json"),
                    str(root / "absent-2.json"),
                ],
                output_dir=str(root / "summary-valkyrie"),
                hard_threshold=200,
            )
          )

  def test_phase_a_host_requires_one_matching_systeminfo_and_supports_bz2(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)

      def write_result(path, hostnames):
        result = ET.Element("result")
        for hostname in hostnames:
          ET.SubElement(result, "systeminfo", {"hostname": hostname})
        content = ET.tostring(result, encoding="utf-8")
        path.write_bytes(
            bz2.compress(content) if path.suffix == ".bz2" else content
        )

      valid = root / "valid.xml.bz2"
      write_result(valid, ["athena"])
      self.assertEqual(
          dataset.validate_phase_a_host(valid, "athena", "athena"), "athena"
      )
      for name, hostnames, requested, manifest, message in (
          ("missing.xml", [], "athena", "athena", "exactly one"),
          ("empty.xml", [""], "athena", "athena", "exactly one"),
          (
              "multiple.xml",
              ["athena", "athena"],
              "athena",
              "athena",
              "exactly one",
          ),
          ("wrong.xml", ["valkyrie"], "athena", "athena", "Phase-A host"),
          ("manifest.xml", ["athena"], "athena", "valkyrie", "Phase-A host"),
      ):
        with self.subTest(name=name):
          path = root / name
          write_result(path, hostnames)
          with self.assertRaisesRegex(RuntimeError, message):
            dataset.validate_phase_a_host(path, requested, manifest)

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
                  "derivation": {"host": "athena"},
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
      ET.SubElement(result_root, "systeminfo", {"hostname": "athena"})
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
              phase_a_host="athena",
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
      self.assertEqual(summary["phase_a_host"], "athena")
      with (output / "classification.csv").open(
          newline="", encoding="utf-8"
      ) as source:
        self.assertEqual(
            {row["phase_a_host"] for row in csv.DictReader(source)}, {"athena"}
        )
      survivor = dataset.validate_manifest(
          output / "candidate-manifest-analysis-survivors.json", root
      )
      self.assertEqual(survivor["derivation"]["phase_a_host"], "athena")
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
                phase_a_host="athena",
                output_dir=str(root / "invalid-summary"),
            )
        )
      with self.assertRaisesRegex(RuntimeError, "Phase-A host"):
        dataset.command_screen_summary(
            SimpleNamespace(
                manifest=str(manifest),
                result=str(result),
                sv_benchmarks=str(root),
                phase_a_host="valkyrie",
                output_dir=str(root / "wrong-host-summary"),
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
