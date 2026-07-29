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
import py_compile
import random
import shutil
import subprocess
import sys
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


def write_stock_result(
    path, tasks, host, formal=False, omit=None, marker="", probe=False
):
  limit = "900s" if formal or probe else "120s"
  root = ET.Element(
      "result",
      {
          "benchmarkname": (
              "cegar-eligibility.probe"
              if probe
              else f"hard-case-candidates.{marker}"
          ),
          "starttime": f"2026-07-27T00:00:{marker or '00'}+08:00",
          "endtime": f"2026-07-27T00:01:{marker or '00'}+08:00",
          "tool": "CPAchecker",
          "version": dataset.FROZEN_CPACHECKER_VERSION,
          "toolmodule": dataset.FROZEN_TOOLMODULE,
          "generator": dataset.FROZEN_BENCHEXEC_GENERATOR,
          "displayName": (
              dataset.PROBE_DISPLAY
              if probe
              else dataset.FORMAL_DISPLAY
              if formal
              else dataset.DISCOVERY_DISPLAY
          ),
          "memlimit": "15000000000B",
          "timelimit": limit,
          "cpuCores": "1" if probe else "4",
          "block": "official",
          "name": (
              "cegar-eligibility.official"
              if probe
              else "hard-case-candidates.official"
          ),
          "options": (
              (
                  "--predicateAnalysis-vguide --heap 10000M "
                  "--timelimit 900 s --option vguide.enable=true "
                  "--option vguide.provider=EMPTY"
              )
              if probe
              else (
                  f"--svcomp27 --heap 10000M --benchmark "
                  f"--timelimit {limit[:-1]} s"
              )
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


def cap16_phase_a_fixture(root):
  phase_a = root / "phase-a"
  phase_a.mkdir()
  source = phase_b_fixture(phase_a)
  manifest = json.loads(Path(source.parent_manifest).read_text(encoding="utf-8"))
  parent_sha256 = "f" * 64
  manifest["derivation"] = {
      "operation": "deterministic_stratified_shard",
      "parent_manifest_sha256": parent_sha256,
      "hosts": ["athena"],
      "host": "athena",
      "selection_independent_of_verifier_outcomes": True,
  }
  input_dir = phase_a / "input"
  input_dir.mkdir()
  shutil.copytree(phase_a / "corpus", input_dir / "corpus")
  manifest_path = input_dir / "candidate-manifest-athena.json"
  manifest_path.write_text(
      json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
  )
  generated = phase_a / "generated"
  dataset.command_render(
      SimpleNamespace(
          manifest=str(manifest_path),
          sv_benchmarks=str(phase_a),
          property_file=str(phase_a / "c/properties/unreach-call.prp"),
          output_dir=str(generated),
      )
  )
  primary = phase_a / "primary.xml"
  write_stock_result(primary, manifest["tasks"], "athena")
  plan = phase_a / "screen-plan.json"
  dataset.command_screen_plan(
      SimpleNamespace(
          manifest=str(manifest_path),
          primary_result=str(primary),
          taint_manifest=None,
          replacement_result=None,
          replacement_definition=None,
          replacement_taint_manifest=None,
          output=str(plan),
          repetition=1,
      )
  )
  summary = phase_a / "summary"
  dataset.command_screen_summary_plan(
      SimpleNamespace(
          manifest=str(manifest_path),
          benchmark_definition=str(generated / "hard-case-candidates.xml"),
          screen_plan=str(plan),
          sv_benchmarks=str(phase_a),
          phase_a_host="athena",
          output_dir=str(summary),
      )
  )
  artifact = phase_a / "provenance/artifact-manifest.json"
  dataset.baseline.command_artifact_manifest(
      SimpleNamespace(root=str(phase_a), output=str(artifact))
  )
  (summary / ".complete").write_text("complete\n", encoding="utf-8")
  return SimpleNamespace(
      root=phase_a,
      manifest=manifest_path,
      manifest_sha256=dataset.baseline.sha256_file(manifest_path),
      parent_sha256=parent_sha256,
      survivor=summary / "candidate-manifest-analysis-survivors.json",
      sv_benchmarks=phase_a,
  )


def package_cap16_fixture(fixture, output):
  with mock.patch.multiple(
      dataset,
      FROZEN_CAP16_ATHENA_MANIFEST_SHA256=fixture.manifest_sha256,
      FROZEN_CAP16_PARENT_MANIFEST_SHA256=fixture.parent_sha256,
      FROZEN_CAP16_PHASE_A_TASK_COUNT=6,
  ):
    dataset.command_package_cap16_phase_a(
        SimpleNamespace(
            phase_a_output=str(fixture.root),
            sv_benchmarks=str(fixture.sv_benchmarks),
            output_dir=str(output),
        )
      )
  artifact = json.loads(
      (output / "provenance/artifact-manifest.json").read_text(
          encoding="utf-8"
      )
  )
  return SimpleNamespace(
      root=output,
      manifest=output / "input/candidate-manifest-athena.json",
      manifest_sha256=fixture.manifest_sha256,
      parent_sha256=fixture.parent_sha256,
      survivor=output / "summary/candidate-manifest-analysis-survivors.json",
      sv_benchmarks=fixture.sv_benchmarks,
      aggregate_sha256=artifact["aggregate_sha256"],
  )


class DatasetTest(unittest.TestCase):
  def test_benchexec_paths_preserve_working_directory_representation(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      sv_benchmarks = root / "sv-benchmarks-cap16-athena-r2-20260728"
      task = sv_benchmarks / "c/loops/task.yml"
      definition = root / "generated/hard-case-candidates.xml"
      result = root / "results/repetition-1/result.xml"
      task.parent.mkdir(parents=True)
      definition.parent.mkdir(parents=True)
      task.write_text("format_version: '2.0'\n", encoding="utf-8")

      representations = dataset.benchexec_path_representations(
          task, sv_benchmarks, definition, result
      )

      self.assertIn(
          "../../../../sv-benchmarks-cap16-athena-r2-20260728/"
          "c/loops/task.yml",
          representations,
      )
      self.assertIn(
          os.path.relpath(task, definition.parent).replace("\\", "/"),
          representations,
      )
      self.assertNotIn(
          "../../evil/../../../../sv-benchmarks-cap16-athena-r2-20260728/"
          "c/loops/task.yml",
          representations,
      )

  def test_result_topology_accepts_only_exact_result_relative_paths(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      sv_benchmarks = root / "sv-benchmarks-cap16-athena-r2-20260728"
      task_path = Path("c/loops/task.yml")
      source_path = Path("c/loops/task.c")
      property_path = Path("c/properties/unreach-call.prp")
      for path in (task_path, source_path, property_path):
        target = sv_benchmarks / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"{path}\n", encoding="utf-8")
      task = {
          "task": task_path.as_posix(),
          "task_path": task_path.as_posix(),
          "source": "sv-benchmarks",
          "source_paths": [source_path.as_posix()],
          "expected_verdict": "true",
      }
      result = root / "output/results/repetition-1/result.xml"
      result.parent.mkdir(parents=True)
      write_stock_result(result, [task], "athena", formal=True)
      definition = root / "output/generated/hard-case-candidates.xml"
      definition.parent.mkdir(parents=True)
      definition.write_text("<benchmark/>\n", encoding="utf-8")
      result_prefix = "../../../sv-benchmarks-cap16-athena-r2-20260728"
      xml = ET.parse(result)
      run = xml.getroot().find("run")
      run.set("name", f"{result_prefix}/{task_path.as_posix()}")
      run.set("files", f"[{result_prefix}/{source_path.as_posix()}]")
      run.set("propertyFile", f"{result_prefix}/{property_path.as_posix()}")
      xml.write(result, encoding="unicode")
      manifest = {task["task"]: task}

      dataset.validate_result_run_topology(
          result, manifest, sv_benchmarks, definition
      )

      alias = root / "sv-benchmarks-alias"
      alias.symlink_to(sv_benchmarks, target_is_directory=True)
      rejected = (
          "../sv-benchmarks-cap16-athena-r2-20260728/c/loops/task.yml",
          "../../../../../sv-benchmarks-cap16-athena-r2-20260728/"
          "c/loops/task.yml",
          "../../../sv-benchmarks-cap16-athena-r2-20260728/"
          "c/decoy/../loops/task.yml",
          "../../../sv-benchmarks-alias/c/loops/task.yml",
          "../../../wrong-corpus/c/loops/task.yml",
      )
      for value in rejected:
        run.set("name", value)
        xml.write(result, encoding="unicode")
        with self.subTest(value=value), self.assertRaisesRegex(
            RuntimeError, "result task path is not exact"
        ):
          dataset.validate_result_run_topology(
              result, manifest, sv_benchmarks, definition
          )

      run.set("name", f"{result_prefix}/{task_path.as_posix()}")
      run.set(
          "files",
          f"[{result_prefix}/c/decoy/../loops/{source_path.name}]",
      )
      xml.write(result, encoding="unicode")
      with self.assertRaisesRegex(
          RuntimeError, "source files do not match manifest"
      ):
        dataset.validate_result_run_topology(
            result, manifest, sv_benchmarks, definition
        )
      run.set("files", f"[{result_prefix}/{source_path.as_posix()}]")
      run.set(
          "propertyFile",
          "../../../sv-benchmarks-alias/c/properties/unreach-call.prp",
      )
      xml.write(result, encoding="unicode")
      with self.assertRaisesRegex(
          RuntimeError, "result property file is not exact"
      ):
        dataset.validate_result_run_topology(
            result, manifest, sv_benchmarks, definition
        )

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
    self.assertEqual(
        dataset.classify_repetitions(unsolved, 200),
        "stable_analysis_unsolved",
    )
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

      empty = root / "empty.json"
      write_manifest(empty, [])
      two_host_output = root / "two-host-derived"
      two_hosts = ["athena", "cthulhu"]
      dataset.command_difference(
          SimpleNamespace(
              manifest=str(full),
              exclude_manifest=str(empty),
              sv_benchmarks=str(root),
              output_dir=str(two_host_output),
              host=two_hosts,
          )
      )
      two_host_shards = [
          two_host_output / f"candidate-manifest-{host}.json"
          for host in two_hosts
      ]
      self.assertFalse(
          (two_host_output / "candidate-manifest-valkyrie.json").exists()
      )
      self.assertEqual(
          [
              json.loads(path.read_text(encoding="utf-8"))["task_count"]
              for path in two_host_shards
          ],
          [2, 2],
      )
      dataset.command_validate_shards(
          SimpleNamespace(
              manifest=str(two_host_output / "candidate-manifest.json"),
              shard_manifest=[str(path) for path in two_host_shards],
              sv_benchmarks=str(root),
              host=two_hosts,
          )
      )

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
        "c9af63c831839af73b709cf538807f9ea989c834d635526875a03787c29247cc",
        "9dd464e236b90eaa25fc9576bb22442b07817d16e086f9e3754d61c3328d9bbd",
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "75e3332253429e6f9186352a255cd96c0aff6154a95e2fdd3b737c143ba018bc",
        "49f95adc5255b89b1bb3edea81ab5f2f660364d36ffa69c3b12508d1e1943be3",
        dataset.FROZEN_FORMAL_MANIFEST_SHA256,
        "a20797345df1bef6d5be5356906ee106b75b374b0d6cd2adfbc56cc5c3e65fef",
    ):
      self.assertIn(value, runner)
    self.assertIn("FORMAL_HOST=valkyrie", runner)
    self.assertIn('$(hostname -s) != "$FORMAL_HOST"', runner)
    self.assertIn("LLM/VGuide environment is forbidden", runner)
    self.assertIn("output directory must be absent or empty", runner)
    self.assertIn('OUTPUT_DIR=$(realpath -m "${15}")', runner)
    self.assertNotRegex(runner, r"\$1[0-9]")
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
    for path in (
        "yaml",
        "_yaml",
        "PyYAML-5.4.1.egg-info",
        "PyYAML-6.0.1.dist-info",
    ):
      self.assertIn(path, runner)
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
    self.assertIn("RENDER_FORMAL_COMMAND=render-formal", runner)
    self.assertIn('"$DATASET_PY" "$RENDER_FORMAL_COMMAND"', runner)
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
    self.assertIn('copy_phase_evidence "$OUTPUT_DIR/input/evidence"', runner)
    self.assertIn(
        'capture_research_provenance "$OUTPUT_DIR/input/research"', runner
    )
    self.assertIn("activate_formal_research_provenance", runner)
    self.assertIn('record_process_snapshot "$OUTPUT_DIR/provenance"', runner)
    self.assertIn('start_process_monitor "$OUTPUT_DIR/provenance/$label-', runner)
    self.assertIn("wait_for_process_monitor", runner)
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
        runner.index('mkdir -p "$OUTPUT_DIR/input/evidence"'),
    )
    self.assertLess(
        runner.index('directory_digest_value "$JAVA_HOME"'),
        runner.index('mkdir -p "$OUTPUT_DIR/input/evidence"'),
    )
    self.assertIn(
        'if [[ "$FORMAL_MODE" == cap8 && "$TASK_COUNT" -ne 270 ]]',
        runner,
    )
    self.assertIn("--hard-threshold 200", runner)
    self.assertNotIn("44ec679a56d3", runner)
    first = runner.index(
        "run_formal_benchmark repetition-1"
    )
    first_result = runner.index(
        'single_formal_result "$OUTPUT_DIR/results/repetition-1"', first
    )
    first_plan = runner.index(
        'build_repetition_plan 1 "${RESULTS[0]}"', first_result
    )
    second = runner.index(
        "run_formal_benchmark repetition-2"
    )
    second_result = runner.index(
        'single_formal_result "$OUTPUT_DIR/results/repetition-2"', second
    )
    second_plan = runner.index(
        'build_repetition_plan 2 "${RESULTS[1]}"', second_result
    )
    summarize = runner.index('"$DATASET_PY" "$SUMMARIZE_COMMAND"', second)
    self.assertLess(first, first_result)
    self.assertLess(first_result, first_plan)
    self.assertLess(first_plan, second)
    self.assertLess(second, second_result)
    self.assertLess(second_result, second_plan)
    self.assertLess(second_plan, summarize)
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
          ("run-cap8-cegar-probe.sh", "#!/usr/bin/env bash\n"),
          ("run-cap16-cegar-probe.sh", "#!/usr/bin/env bash\n"),
          ("run-strict-cegar-probe.sh", "#!/usr/bin/env bash\n"),
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
FORMAL_MODE=cap8-probe
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
      self.assertTrue(
          (saved / "scripts/run-strict-cegar-probe.sh").is_file()
      )

      frozen_head = subprocess.check_output(
          ["git", "-C", research, "rev-parse", "HEAD"], text=True
      ).strip()
      (script_dir / "baseline.py").write_text(
          "#!/usr/bin/env python3\n", encoding="utf-8"
      )
      subprocess.run(["git", "-C", research, "add", "."], check=True)
      subprocess.run(
          ["git", "-C", research, "commit", "-qm", "recovery code"],
          check=True,
      )
      verify_frozen = """
source "$1"
SCRIPT_DIR=$2
RESEARCH_ROOT=$3
FORMAL_MODE=cap8-probe
verify_frozen_research_provenance "$4" "$5"
"""
      frozen_args = [
          str(runner),
          str(script_dir),
          str(research),
          str(saved),
          frozen_head,
      ]
      subprocess.run(
          ["bash", "-c", verify_frozen, "bash", *frozen_args], check=True
      )
      saved_dataset = saved / "scripts/dataset.py"
      original_saved_dataset = saved_dataset.read_bytes()
      saved_dataset.write_text("forged\n", encoding="utf-8")
      forged = subprocess.run(
          ["bash", "-c", verify_frozen, "bash", *frozen_args]
      )
      self.assertNotEqual(forged.returncode, 0)
      saved_dataset.write_bytes(original_saved_dataset)

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
      self.assertFalse(list(provenance.glob("*.stopped.tmp.*")))
      runner_text = runner.read_text(encoding="utf-8")
      self.assertIn(
          'stopped_tmp=$(mktemp "$stopped.tmp.XXXXXX")', runner_text
      )
      self.assertIn('mv -- "$stopped_tmp" "$stopped"', runner_text)
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

      for failure in ("kill", "wait"):
        poisoned = root / f"{failure}-race-monitor.jsonl"
        poisoned.write_text("header\nsample\n", encoding="utf-8")
        command = """
source "$1"
set +e
MONITOR_ACTIVE=true
MONITOR_PID=424242
MONITOR_OUTPUT=$2
if [[ $3 == kill ]]; then
  kill() {
    [[ $1 == -0 ]]
  }
else
  kill() {
    return 0
  }
  wait() {
    return 1
  }
fi
if stop_process_monitor; then
  exit 1
fi
test "$MONITOR_ACTIVE" = true
test ! -e "$MONITOR_OUTPUT.stopped"
"""
        subprocess.run(
            [
                "bash",
                "-c",
                command,
                "bash",
                str(runner),
                str(poisoned),
                failure,
            ],
            check=True,
        )

  def test_formal_runner_authenticates_cgroup_watchdog_teardown(self):
    runner = Path(__file__).with_name("run-stock-formal-dataset.sh")
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      fake_cgroup = root / "fake-cgroup"
      nested_cgroup = fake_cgroup / "nested"
      nested_cgroup.mkdir(parents=True)
      (fake_cgroup / "cgroup.procs").write_text("22\n", encoding="ascii")
      (nested_cgroup / "cgroup.procs").write_text("11\n22\n", encoding="ascii")
      enumerated = subprocess.run(
          [
              "bash",
              "-c",
              """
source "$1"
load_owned_cgroup_pids "$2"
printf '%s\\n' "${OWNED_CGROUP_PIDS[@]}"
""",
              "bash",
              str(runner),
              str(fake_cgroup),
          ],
          check=True,
          capture_output=True,
          text=True,
      )
      self.assertEqual(enumerated.stdout.splitlines(), ["11", "22"])

      unverified = subprocess.run(
          [
              "bash",
              "-c",
              """
source "$1"
sleep 0.2 &
MONITOR_PID=$!
setsid sleep 60 &
benchmark=$!
authenticate_scope_cgroup() {
  return 1
}
systemctl() {
  return 1
}
if wait_for_benchmark_with_monitor \
  missing.scope "$benchmark" /missing.scope /missing.scope; then
  exit 1
fi
! kill -0 "$benchmark" 2>/dev/null
""",
              "bash",
              str(runner),
          ],
          capture_output=True,
          text=True,
          timeout=3,
      )
      self.assertEqual(unverified.returncode, 0, unverified.stderr)
      self.assertIn("termination is unverified", unverified.stderr)

      runtime_cgroup = root / "runtime-cgroup"
      runtime_cgroup.mkdir()
      unbound_scope = subprocess.run(
          [
              "bash",
              "-c",
              """
source "$1"
runtime_cgroup=$2
stop_marker=$3
sleep 0.2 &
MONITOR_PID=$!
setsid sleep 60 &
benchmark=$!
sleep 60 &
unrelated=$!
cleanup() {
  kill "$unrelated" 2>/dev/null || :
  wait "$unrelated" 2>/dev/null || :
}
trap cleanup EXIT
load_owned_cgroup_pids() {
  OWNED_CGROUP_PIDS=("$unrelated")
}
authenticate_scope_cgroup() {
  if ! cgroup_contains_pid "$runtime_cgroup" "$benchmark"; then
    return 1
  fi
  AUTHENTICATED_CONTROL_GROUP=/test.scope
  AUTHENTICATED_CGROUP_PATH=$runtime_cgroup
}
systemctl() {
  printf 'called\\n' >"$stop_marker"
  return 1
}
if wait_for_benchmark_with_monitor \
  test.scope "$benchmark" /test.scope "$runtime_cgroup"; then
  exit 1
fi
! kill -0 "$benchmark" 2>/dev/null
kill -0 "$unrelated" 2>/dev/null
[[ ! -e "$stop_marker" ]]
""",
              "bash",
              str(runner),
              str(runtime_cgroup),
              str(root / "unexpected-systemctl-stop"),
          ],
          capture_output=True,
          text=True,
          timeout=3,
      )
      self.assertEqual(unbound_scope.returncode, 0, unbound_scope.stderr)
      self.assertIn("termination is unverified", unbound_scope.stderr)

      command = """
source "$1"
child_file=$2
runtime_cgroup=$3
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
  os.setsid()
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
sleep 60 &
unrelated=$!
cleanup() {
  kill "$unrelated" 2>/dev/null || :
  wait "$unrelated" 2>/dev/null || :
}
trap cleanup EXIT
while [[ ! -s "$child_file" ]]; do sleep 0.01; done
child=$(cat "$child_file")
authenticate_scope_cgroup() {
  [[ ${2:-/test.scope} == /test.scope ]]
  [[ ${3:-$runtime_cgroup} == "$runtime_cgroup" ]]
  [[ ${4:-$benchmark} == "$benchmark" ]]
  AUTHENTICATED_CONTROL_GROUP=/test.scope
  AUTHENTICATED_CGROUP_PATH=$runtime_cgroup
}
load_owned_cgroup_pids() {
  load_attempts=$((${load_attempts:-0} + 1))
  if [[ $load_attempts -eq 1 ]]; then
    return 3
  fi
  OWNED_CGROUP_PIDS=()
  local pid
  local state
  for pid in "$benchmark" "$child"; do
    state=$(ps -o stat= -p "$pid" 2>/dev/null || :)
    if [[ -n "$state" && "$state" != Z* ]]; then
      OWNED_CGROUP_PIDS+=("$pid")
    fi
  done
}
owned_cgroup_is_empty() {
  [[ ${#OWNED_CGROUP_PIDS[@]} -eq 0 ]]
}
systemctl() {
  return 1
}
if wait_for_benchmark_with_monitor \
  test.scope "$benchmark" /test.scope "$runtime_cgroup"; then
  exit 1
fi
! kill -0 "$benchmark" 2>/dev/null
for _ in {1..40}; do
  if ! kill -0 "$child" 2>/dev/null; then
    kill -0 "$unrelated" 2>/dev/null
    exit 0
  fi
  sleep 0.05
done
exit 2
"""
      child_file = root / "benchmark-child.pid"
      stopped = subprocess.run(
          [
              "bash",
              "-c",
              command,
              "bash",
              str(runner),
              str(child_file),
              str(runtime_cgroup),
          ],
          capture_output=True,
          text=True,
          timeout=8,
      )
      self.assertEqual(stopped.returncode, 0, stopped.stderr)
      self.assertIn("terminating authenticated cgroup", stopped.stderr)
      self.assertIn("authenticated cgroup teardown complete", stopped.stderr)
      self.assertIn("process monitor died during BenchExec", stopped.stderr)



  def test_formal_recovery_provenance_is_revision_addressed_and_immutable(self):
    runner = Path(__file__).with_name("run-stock-formal-dataset.sh")
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      research = root / "research"
      script_dir = research / "scripts/vguide"
      script_dir.mkdir(parents=True)
      for name in (
          "run-stock-formal-dataset.sh",
          "run-stock-cap16-formal-dataset.sh",
          "dataset.py",
          "baseline.py",
      ):
        shutil.copy2(Path(__file__).with_name(name), script_dir / name)
      subprocess.run(["git", "init", "-q", research], check=True)
      subprocess.run(
          ["git", "-C", research, "config", "user.email", "test@example.com"],
          check=True,
      )
      subprocess.run(
          ["git", "-C", research, "config", "user.name", "Test"], check=True
      )

      def commit(message):
        subprocess.run(["git", "-C", research, "add", "."], check=True)
        subprocess.run(
            ["git", "-C", research, "commit", "-qm", message], check=True
        )
        return subprocess.check_output(
            ["git", "-C", research, "rev-parse", "HEAD"], text=True
        ).strip()

      def invoke(output):
        return subprocess.run(
            [
                "bash",
                "-c",
                """
source "$1"
SCRIPT_DIR=$2
RESEARCH_ROOT=$3
OUTPUT_DIR=$4
RESUMING=true
FORMAL_MODE=cap16
LEGACY_FORMAL_RESEARCH_HEAD=$5
LEGACY_RECOVERY_RESEARCH_HEAD=$6
activate_formal_research_provenance
printf '%s\n' "$ACTIVE_RESEARCH_PROVENANCE"
""",
                "bash",
                str(runner),
                str(script_dir),
                str(research),
                str(output),
                original_head,
                prior_head,
            ],
            capture_output=True,
            text=True,
        )

      def capture(destination):
        subprocess.run(
            [
                "bash",
                "-c",
                """
source "$1"
SCRIPT_DIR=$2
RESEARCH_ROOT=$3
FORMAL_MODE=cap16
capture_research_provenance "$4"
""",
                "bash",
                str(runner),
                str(script_dir),
                str(research),
                str(destination),
            ],
            check=True,
        )

      def file_bytes(directory):
        return {
            path.relative_to(directory).as_posix(): path.read_bytes()
            for path in directory.rglob("*")
            if path.is_file()
        }

      original_head = commit("original")
      output = root / "output"
      original = output / "input/research"
      capture(original)

      with (script_dir / "baseline.py").open("a", encoding="utf-8") as handle:
        handle.write("\n")
      prior_head = commit("first recovery")
      prior = output / "input/recovery-research"
      capture(prior)
      prior_bytes = file_bytes(prior)

      with (script_dir / "dataset.py").open("a", encoding="utf-8") as handle:
        handle.write("\n")
      current_head = commit("second recovery")
      current = output / f"input/recovery-research-{current_head}"

      tampered_before_capture = root / "tampered-before-capture"
      shutil.copytree(output, tampered_before_capture)
      (
          tampered_before_capture / "input/recovery-research/scripts/dataset.py"
      ).write_text("tampered\n", encoding="utf-8")
      rejected_before_capture = invoke(tampered_before_capture)
      self.assertNotEqual(rejected_before_capture.returncode, 0)
      self.assertFalse(
          (
              tampered_before_capture
              / f"input/recovery-research-{current_head}"
          ).exists()
      )

      extra_before_capture = root / "extra-before-capture"
      shutil.copytree(output, extra_before_capture)
      (
          extra_before_capture / "input/recovery-research/extra-file"
      ).write_text("extra\n", encoding="utf-8")
      rejected_extra = invoke(extra_before_capture)
      self.assertNotEqual(rejected_extra.returncode, 0)
      self.assertFalse(
          (extra_before_capture / f"input/recovery-research-{current_head}")
          .exists()
      )

      missing_prior = root / "missing-prior"
      shutil.copytree(output, missing_prior)
      shutil.rmtree(missing_prior / "input/recovery-research")
      rejected_missing_prior = invoke(missing_prior)
      self.assertNotEqual(rejected_missing_prior.returncode, 0)
      self.assertFalse(
          (missing_prior / f"input/recovery-research-{current_head}").exists()
      )

      activated = invoke(output)
      self.assertEqual(activated.returncode, 0, activated.stderr)
      self.assertEqual(activated.stdout.splitlines()[-1], str(current))
      self.assertEqual(file_bytes(prior), prior_bytes)
      current_bytes = file_bytes(current)
      self.assertEqual(
          (current / "research-head.txt").read_text(encoding="utf-8").strip(),
          current_head,
      )

      repeated = invoke(output)
      self.assertEqual(repeated.returncode, 0, repeated.stderr)
      self.assertEqual(file_bytes(prior), prior_bytes)
      self.assertEqual(file_bytes(current), current_bytes)

      descriptor = dataset.formal_process_descriptor(SimpleNamespace(
          output_root=str(output),
          mode="cap16",
          label="repetition-1",
          host="athena",
          name="hard-case-dataset-v2-cap16-formal-athena-repetition-1",
          definition=str(output / "generated/hard-case-candidates.xml"),
          result_output=str(output / "results/repetition-1"),
          monitor_output=str(output / "provenance/load-monitor.jsonl"),
          monitor_exclude_root=123,
          dataset_py=str(current / "scripts/dataset.py"),
          cpachecker_dir=str(root / "cpachecker"),
          benchexec_dir=str(root / "benchexec"),
          python_bin="/usr/bin/python3.12",
          java_home=str(root / "jdk"),
          p_cores=dataset.FORMAL_P_CORE_LIST,
      ))
      self.assertEqual(
          descriptor["inputs"]["dataset_py"],
          str(current / "scripts/dataset.py"),
      )
      self.assertEqual(
          descriptor["schema_version"],
          dataset.FORMAL_PROCESS_DESCRIPTOR_SCHEMA,
      )
      self.assertEqual(
          descriptor["identities"]["load-monitor"]["argv"][1:6],
          list(dataset.PYTHON_RUNTIME_FLAGS),
      )
      benchexec_argv = descriptor["identities"][
          "benchexec-launcher"
      ]["argv"]
      python_index = benchexec_argv.index("/usr/bin/python3.12")
      self.assertEqual(
          benchexec_argv[python_index + 1:python_index + 6],
          list(dataset.PYTHON_RUNTIME_FLAGS),
      )
      self.assertEqual(
          benchexec_argv[
              benchexec_argv.index(descriptor["inputs"]["benchexec_dir"]) + 1
          ],
          dataset.FORMAL_PYYAML_FILE,
      )
      self.assertNotIn("sys.pycache_prefix", dataset.BENCHEXEC_MODULE_COMMAND)
      self.assertNotIn(
          "sys.dont_write_bytecode", dataset.BENCHEXEC_MODULE_COMMAND
      )
      (current / "research-head.txt").write_text(
          f"{'0' * 40}\n", encoding="utf-8"
      )
      with self.assertRaisesRegex(RuntimeError, "runtime is not pinned"):
        dataset.formal_process_descriptor(SimpleNamespace(
            **descriptor["inputs"],
            output_root=str(output),
            mode="cap16",
            label="repetition-1",
            host="athena",
        ))
      (current / "research-head.txt").write_bytes(
          current_bytes["research-head.txt"]
      )
      cap8_inputs = {
          **descriptor["inputs"],
          "name": "hard-case-dataset-v2-formal-valkyrie-repetition-1",
          "python_bin": "/usr/bin/python3.10",
      }
      with self.assertRaisesRegex(RuntimeError, "runtime is not pinned"):
        dataset.formal_process_descriptor(SimpleNamespace(
            **cap8_inputs,
            output_root=str(output),
            mode="cap8",
            label="repetition-1",
            host="valkyrie",
        ))

      prior_dataset = prior / "scripts/dataset.py"
      prior_dataset.write_text("tampered\n", encoding="utf-8")
      tampered = invoke(output)
      self.assertNotEqual(tampered.returncode, 0)
      prior_dataset.write_bytes(prior_bytes["scripts/dataset.py"])

      with (script_dir / "run-stock-cap16-formal-dataset.sh").open(
          "a", encoding="utf-8"
      ) as handle:
        handle.write("\n")
      next_head = commit("third recovery")
      next_recovery = output / f"input/recovery-research-{next_head}"
      advanced = invoke(output)
      self.assertEqual(advanced.returncode, 0, advanced.stderr)
      self.assertEqual(file_bytes(prior), prior_bytes)
      self.assertEqual(file_bytes(current), current_bytes)
      self.assertEqual(
          (next_recovery / "research-head.txt")
          .read_text(encoding="utf-8")
          .strip(),
          next_head,
      )
      current_dataset = current / "scripts/dataset.py"
      current_dataset.write_text("tampered\n", encoding="utf-8")
      tampered_revision = invoke(output)
      self.assertNotEqual(tampered_revision.returncode, 0)
      current_dataset.write_bytes(current_bytes["scripts/dataset.py"])

      conflicting_output = root / "conflicting-output"
      shutil.copytree(output, conflicting_output)
      conflicting_current = (
          conflicting_output / f"input/recovery-research-{next_head}"
      )
      shutil.rmtree(conflicting_current)
      conflicting_current.write_text("conflict\n", encoding="utf-8")
      conflict = invoke(conflicting_output)
      self.assertNotEqual(conflict.returncode, 0)
      self.assertEqual(
          conflicting_current.read_text(encoding="utf-8"), "conflict\n"
      )

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
      python_stdlib.mkdir()
      (python_stdlib / "runtime.py").write_bytes(b"stdlib")
      python_dist_packages.mkdir()
      (python_dist_packages / "yaml").mkdir()
      (python_dist_packages / "yaml/__init__.py").write_bytes(b"source")
      (python_dist_packages / "yaml/_yaml.so").write_bytes(b"extension")
      (python_dist_packages / "_yaml").mkdir()
      (python_dist_packages / "_yaml/__init__.py").write_bytes(b"source")
      (python_dist_packages / "PyYAML-test.dist-info").mkdir()
      (python_dist_packages / "PyYAML-test.dist-info/METADATA").write_bytes(
          b"metadata"
      )
      python_local_dist_packages.mkdir()

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
EXPECTED_PYTHON_STDLIB_DIGEST=$(python_runtime_digest_value "$PYTHON_STDLIB")
EXPECTED_PYTHON_DIST_PACKAGES=$PYTHON_DIST_PACKAGES
EXPECTED_PYYAML_PACKAGE_PATHS=(yaml _yaml PyYAML-test.dist-info)
EXPECTED_PYYAML_PACKAGE_DIGEST=$(pyyaml_package_digest_value)
EXPECTED_PYTHON_LOCAL_DIST_PACKAGES=$PYTHON_LOCAL_DIST_PACKAGES
EXPECTED_PYTHON_LOCAL_DIST_PACKAGES_DIGEST=$(python_runtime_digest_value "$PYTHON_LOCAL_DIST_PACKAGES")
EXPECTED_PYTHON_SYSTEM_PATH=$("$PYTHON_BIN" "${PYTHON_RUNTIME_FLAGS[@]}" -c 'import sys; print(":".join(sys.path))')
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

      stdlib_digest = dataset.baseline.python_runtime_digest(python_stdlib)[
          "sha256"
      ]
      (python_stdlib / "runtime.py").write_bytes(b"changed")
      rejected = subprocess.run(
          [
              "bash",
              "-c",
              setup
              + f"\nEXPECTED_PYTHON_STDLIB_DIGEST={stdlib_digest}\n"
              + "verify_runtime_closure true",
              "bash",
              *arguments,
          ],
      )
      self.assertNotEqual(rejected.returncode, 0)
      (python_stdlib / "runtime.py").write_bytes(b"stdlib")

      package_paths = ("yaml", "_yaml", "PyYAML-test.dist-info")
      package_digest = dataset.baseline.python_runtime_digest(
          python_dist_packages, package_paths
      )["sha256"]
      local_digest = dataset.baseline.python_runtime_digest(
          python_local_dist_packages
      )["sha256"]
      for relative in (
          "yaml/__init__.py",
          "yaml/_yaml.so",
          "PyYAML-test.dist-info/METADATA",
          "yaml/unknown",
      ):
        path = python_dist_packages / relative
        original = path.read_bytes() if path.exists() else None
        path.write_bytes(b"changed")
        rejected = subprocess.run(
            [
                "bash",
                "-c",
                setup
                + f"\nEXPECTED_PYYAML_PACKAGE_DIGEST={package_digest}\n"
                + "verify_runtime_closure true",
                "bash",
                *arguments,
            ],
        )
        self.assertNotEqual(rejected.returncode, 0)
        if original is None:
          path.unlink()
        else:
          path.write_bytes(original)

      for cache in (
          python_stdlib / "__pycache__/runtime.cpython-312.pyc",
          python_dist_packages / "yaml/__pycache__/loader.cpython-312.pyc",
          python_local_dist_packages / "__pycache__/shadow.cpython-312.pyc",
      ):
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(b"cache")
      subprocess.run(
          [
              "bash",
              "-c",
              setup
              + f"\nEXPECTED_PYTHON_STDLIB_DIGEST={stdlib_digest}\n"
              + f"EXPECTED_PYYAML_PACKAGE_DIGEST={package_digest}\n"
              + (
                  "EXPECTED_PYTHON_LOCAL_DIST_PACKAGES_DIGEST="
                  f"{local_digest}\n"
              )
              + "verify_runtime_closure true",
              "bash",
              *arguments,
          ],
          check=True,
      )

      sourceless = python_dist_packages / "yaml/ignored.pyc"
      sourceless.write_bytes(b"cache")
      rejected = subprocess.run(
          [
              "bash",
              "-c",
              setup
              + f"\nEXPECTED_PYYAML_PACKAGE_DIGEST={package_digest}\n"
              + "verify_runtime_closure true",
              "bash",
              *arguments,
          ],
      )
      self.assertNotEqual(rejected.returncode, 0)
      sourceless.unlink()

      shadow = python_local_dist_packages / "yaml"
      shadow.mkdir()
      (shadow / "__init__.py").write_bytes(b"shadow")
      rejected = subprocess.run(
          [
              "bash",
              "-c",
              setup
              + f"\nEXPECTED_PYTHON_LOCAL_DIST_PACKAGES_DIGEST={local_digest}\n"
              + "verify_runtime_closure true",
              "bash",
              *arguments,
          ],
      )
      self.assertNotEqual(rejected.returncode, 0)
      shutil.rmtree(shadow)

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

  def test_formal_python_bootstrap_ignores_host_caches_and_site_hooks(self):
    runner = Path(__file__).with_name("run-stock-formal-dataset.sh")
    python = Path(os.path.realpath("/usr/bin/python3"))
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      script_dir = root / "saved/scripts"
      script_dir.mkdir(parents=True)
      helper = script_dir / "helper.py"
      helper.write_text('VALUE = "cache"\n', encoding="utf-8")
      with mock.patch.object(sys, "pycache_prefix", None):
        py_compile.compile(
            str(helper),
            invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
            doraise=True,
        )
      helper.write_text('VALUE = "source"\n', encoding="utf-8")
      output = root / "runtime.json"
      script = script_dir / "probe.py"
      script.write_text(
          """
import json
import sys
from pathlib import Path
import helper

Path(sys.argv[1]).write_text(json.dumps({
    "value": helper.VALUE,
    "sys_path": sys.path,
    "site_loaded": "site" in sys.modules,
    "dont_write_bytecode": sys.dont_write_bytecode,
    "pycache_prefix": sys.pycache_prefix,
    "isolated": sys.flags.isolated,
    "no_site": sys.flags.no_site,
    "safe_path": getattr(sys.flags, "safe_path", None),
}), encoding="utf-8")
""",
          encoding="utf-8",
      )
      hook = root / "hooks"
      hook.mkdir()
      hook_marker = root / "sitecustomize-ran"
      (hook / "sitecustomize.py").write_text(
          f"open({str(hook_marker)!r}, 'w').write('ran')\n",
          encoding="utf-8",
      )
      (hook / "injected.pth").write_text(
          f"import pathlib; pathlib.Path({str(hook_marker)!r}).write_text('pth')\n",
          encoding="utf-8",
      )
      control = subprocess.run(
          [
              python,
              "-I",
              "-S",
              "-B",
              "-c",
              (
                  "import sys; sys.path.insert(0, sys.argv[1]); "
                  "import helper; print(helper.VALUE)"
              ),
              str(script_dir),
          ],
          check=True,
          capture_output=True,
          text=True,
      )
      self.assertEqual(control.stdout.strip(), "cache")
      subprocess.run(
          [
              "bash",
              "-c",
              'source "$1"; run_python_script "$2" "$3"',
              "bash",
              str(runner),
              str(script),
              str(output),
          ],
          check=True,
          env={**os.environ, "PYTHONPATH": str(hook)},
      )
      runtime = json.loads(output.read_text(encoding="utf-8"))
      expected_path = subprocess.run(
          [python, *dataset.PYTHON_RUNTIME_FLAGS, "-c",
           (
               "import json,sys; print(json.dumps({"
               "'path':sys.path,"
               "'safe_path':getattr(sys.flags,'safe_path',None)}))"
           )],
          check=True,
          capture_output=True,
          text=True,
      )
      self.assertEqual(runtime["value"], "source")
      self.assertEqual(
          runtime["sys_path"],
          [str(script_dir), *json.loads(expected_path.stdout)["path"]],
      )
      self.assertFalse(runtime["site_loaded"])
      self.assertTrue(runtime["dont_write_bytecode"])
      self.assertEqual(runtime["pycache_prefix"], "/dev/null")
      self.assertEqual(
          {
              "isolated": runtime["isolated"],
              "no_site": runtime["no_site"],
              "safe_path": runtime["safe_path"],
          },
          {
              "isolated": 1,
              "no_site": 1,
              "safe_path": json.loads(expected_path.stdout)["safe_path"],
          },
      )
      self.assertFalse(hook_marker.exists())
      sourceless_source = script_dir / "sourceless.py"
      sourceless_source.write_text('VALUE = "bytecode"\n', encoding="utf-8")
      sourceless_bytecode = script_dir / "sourceless.pyc"
      py_compile.compile(
          str(sourceless_source),
          cfile=str(sourceless_bytecode),
          doraise=True,
      )
      sourceless_source.unlink()
      control = subprocess.run(
          [
              python,
              *dataset.PYTHON_RUNTIME_FLAGS,
              "-c",
              (
                  "import sys; sys.path.insert(0, sys.argv[1]); "
                  "import sourceless; print(sourceless.VALUE)"
              ),
              str(script_dir),
          ],
          check=True,
          capture_output=True,
          text=True,
      )
      self.assertEqual(control.stdout.strip(), "bytecode")
      sourceless_output = root / "sourceless-output"
      sourceless_probe = script_dir / "sourceless-probe.py"
      sourceless_probe.write_text(
          (
              "import sourceless\n"
              "from pathlib import Path\n"
              "Path(__import__('sys').argv[1]).write_text("
              "sourceless.VALUE, encoding='utf-8')\n"
          ),
          encoding="utf-8",
      )
      rejected = subprocess.run(
          [
              "bash",
              "-c",
              'source "$1"; run_python_script "$2" "$3"',
              "bash",
              str(runner),
              str(sourceless_probe),
              str(sourceless_output),
          ],
          capture_output=True,
          text=True,
      )
      self.assertNotEqual(rejected.returncode, 0)
      self.assertIn("sourceless Python bytecode", rejected.stderr)
      self.assertFalse(sourceless_output.exists())
      with self.assertRaisesRegex(
          RuntimeError, "sourceless Python bytecode"
      ):
        dataset.run_saved_dataset(
            sourceless_probe,
            [str(sourceless_output)],
            python_bin=python,
        )

  def test_legacy_process_descriptors_require_exact_frozen_selection(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp).resolve()

      def arguments(label):
        return SimpleNamespace(
            output_root=str(root),
            mode="cap16",
            label=label,
            host="athena",
            name=(
                "hard-case-dataset-v2-cap16-formal-athena-"
                f"{label}"
            ),
            definition=str(root / "generated/hard-case-candidates.xml"),
            result_output=str(root / f"results/{label}"),
            monitor_output=str(
                root / f"provenance/{label}-load-monitor.jsonl"
            ),
            monitor_exclude_root=123,
            dataset_py=str(root / "input/research/scripts/dataset.py"),
            cpachecker_dir=str(root / "cpachecker"),
            benchexec_dir=str(root / "benchexec"),
            python_bin="/usr/bin/python3.12",
            java_home=str(root / "jdk"),
            p_cores=dataset.FORMAL_P_CORE_LIST,
        )

      replacement = copy.deepcopy(
          dataset.FROZEN_CAP16_ATHENA_V2_RECOVERY_SELECTION
      )
      replacement_path = (
          root / replacement["files"]["process_descriptor"]["path"]
      )
      replacement_path.parent.mkdir(parents=True)
      legacy = dataset.formal_process_descriptor(
          arguments(replacement["label"]), legacy=True
      )
      replacement_path.write_text(
          json.dumps(legacy, indent=2) + "\n", encoding="utf-8"
      )
      replacement["files"]["process_descriptor"]["sha256"] = (
          dataset.baseline.sha256_file(replacement_path)
      )
      with mock.patch.object(
          dataset,
          "FROZEN_CAP16_ATHENA_V2_RECOVERY_SELECTION",
          replacement,
      ):
        self.assertEqual(
            dataset.load_formal_process_descriptor(
                replacement_path,
                root,
                "cap16",
                replacement["label"],
                "athena",
            ),
            legacy,
        )
        arbitrary = root / "provenance/arbitrary-process-descriptor.json"
        arbitrary.write_bytes(replacement_path.read_bytes())
        with self.assertRaisesRegex(RuntimeError, "not selected"):
          dataset.load_formal_process_descriptor(
              arbitrary,
              root,
              "cap16",
              replacement["label"],
              "athena",
          )
        altered = copy.deepcopy(legacy)
        altered["identities"]["load-monitor"]["argv"].append("injected")
        replacement_path.write_text(
            json.dumps(altered, indent=2) + "\n", encoding="utf-8"
        )
        replacement["files"]["process_descriptor"]["sha256"] = (
            dataset.baseline.sha256_file(replacement_path)
        )
        with self.assertRaisesRegex(RuntimeError, "content is invalid"):
          dataset.load_formal_process_descriptor(
              replacement_path,
              root,
              "cap16",
              replacement["label"],
              "athena",
          )

      primary = copy.deepcopy(dataset.LEGACY_CAP16_ATHENA_REPETITION_1)
      primary_path = root / "provenance/repetition-1-process-descriptor.json"
      primary_legacy = dataset.formal_process_descriptor(
          arguments(primary["label"]), legacy=True
      )
      primary_path.write_text(
          json.dumps(primary_legacy, indent=2) + "\n", encoding="utf-8"
      )
      primary["selected_provenance"][
          "repetition-1-process-descriptor.json"
      ] = dataset.baseline.sha256_file(primary_path)
      with (
          mock.patch.object(
              dataset, "LEGACY_CAP16_ATHENA_REPETITION_1", primary
          ),
          mock.patch.object(
              dataset, "validate_recovery_selection"
          ) as validate_selection,
      ):
        dataset.load_formal_process_descriptor(
            primary_path, root, "cap16", primary["label"], "athena"
        )
        validate_selection.assert_called_once_with(root, primary)
        displaced = (
            root
            / "provenance/abandoned/repetition-1-superseded-zero-row-rerun"
            / "provenance/repetition-1-process-descriptor.json"
        )
        displaced.parent.mkdir(parents=True)
        displaced.write_bytes(primary_path.read_bytes())
        with self.assertRaisesRegex(RuntimeError, "not selected"):
          dataset.load_formal_process_descriptor(
              displaced, root, "cap16", primary["label"], "athena"
          )
        with self.assertRaisesRegex(RuntimeError, "identity is invalid"):
          dataset.load_formal_process_descriptor(
              primary_path, root, "cap16", primary["label"], "valkyrie"
          )

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
              json.dumps({
                  "timestamp": "2026-07-27T00:00:15+08:00",
                  "elapsed_seconds": 1.0,
                  "offenders": [{
                      "pid": 456,
                      "uid": 1000,
                      "comm": "foreign",
                      "cpu_percent": 75.0,
                      "duration_seconds": 10.0,
                      "since": "2026-07-27T00:00:05+08:00",
                      "contended": True,
                  }],
              }),
              json.dumps({
                  "timestamp": "2026-07-27T00:00:31+08:00",
                  "elapsed_seconds": 16.0,
                  "offenders": [],
              }),
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
          "\n".join(monitor.read_text(encoding="utf-8").splitlines()[:2])
          + "\n",
          encoding="utf-8",
      )
      with self.assertRaisesRegex(RuntimeError, "fully observed"):
        dataset.command_formal_taint(
            SimpleNamespace(
                manifest=str(manifest),
                repetition=1,
                result=str(result),
                benchexec_log=str(log),
                load_monitor=str(monitor),
                output=str(root / "unobserved-taint.json"),
            )
        )

  def test_recovered_taint_uses_xml_for_one_trailing_log_completion(self):
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
          for index in range(5)
      ]
      manifest = {task["task"]: task for task in tasks}
      manifest_path = root / "manifest.json"
      manifest_path.write_text(
          json.dumps({"task_count": len(tasks), "tasks": tasks}),
          encoding="utf-8",
      )
      result = root / "result.xml"
      write_stock_result(result, tasks, "athena", formal=True, marker="01")
      result_root = ET.parse(result).getroot()
      result_root.set("error", "incomplete")
      result_root.attrib.pop("endtime")
      for run in result_root.findall("run")[3:]:
        for column in list(run):
          run.remove(column)
      ET.ElementTree(result_root).write(result, encoding="unicode")
      monitor = root / "load.jsonl"
      monitor.write_bytes(
          (
              json.dumps({
                  "schema_version": dataset.FORMAL_LOAD_MONITOR_SCHEMA,
                  "p_core_cpus": list(dataset.FORMAL_P_CORE_CPUS),
                  "foreign_process_cpu_percent": 50.0,
                  "minimum_consecutive_seconds": 10.0,
                  "sample_interval_seconds": 1.0,
                  "excluded_process_root": 123,
              })
              + "\n"
              + json.dumps({
                  "timestamp": "2026-07-27T00:00:30+08:00",
                  "elapsed_seconds": 1.0,
                  "offenders": [],
              })
              + "\n"
          ).encode()
          + (b"\0" * 16)
      )
      log = root / "benchexec.log"

      def write_log(completed):
        lines = []
        for index, task in enumerate(tasks):
          lines.append(f"00:00:0{index + 1}   starting   {task['task']}")
        for index in completed:
          lines.append(
              f"00:00:{10 + index}              "
              f"{tasks[index]['task']}   TIMEOUT 900 1"
          )
        log.write_text("\n".join(lines) + "\n", encoding="utf-8")

      write_log([0, 1, 2, 3])
      tainted = dataset.run_taints(
          result,
          log,
          monitor,
          manifest,
          allow_trailing_nul=True,
          allow_final_log_only_completion=True,
      )
      self.assertEqual(
          tainted,
          {
              "c/t3.yml": "interrupted_incomplete",
              "c/t4.yml": "interrupted_incomplete",
          },
      )

      with self.assertRaisesRegex(RuntimeError, "log and complete"):
        dataset.run_taints(
            result,
            log,
            monitor,
            manifest,
            allow_trailing_nul=True,
        )

      unpadded_monitor = root / "unpadded-load.jsonl"
      unpadded_monitor.write_bytes(monitor.read_bytes().rstrip(b"\0"))
      with self.assertRaisesRegex(RuntimeError, "log and complete"):
        dataset.run_taints(
            result,
            log,
            unpadded_monitor,
            manifest,
            allow_trailing_nul=True,
            allow_final_log_only_completion=True,
        )
      with self.assertRaisesRegex(RuntimeError, "log and complete"):
        dataset.run_taints(
            result,
            log,
            unpadded_monitor,
            manifest,
            allow_trailing_nul=False,
        )

      write_log([0, 1, 2, 3, 4])
      with self.assertRaisesRegex(RuntimeError, "log and complete"):
        dataset.run_taints(
            result,
            log,
            monitor,
            manifest,
            allow_trailing_nul=True,
            allow_final_log_only_completion=True,
        )

      write_log([0, 1, 3, 2])
      with self.assertRaisesRegex(RuntimeError, "log and complete"):
        dataset.run_taints(
            result,
            log,
            monitor,
            manifest,
            allow_trailing_nul=True,
            allow_final_log_only_completion=True,
        )

      write_log([0, 1, 3])
      with self.assertRaisesRegex(RuntimeError, "log and complete"):
        dataset.run_taints(
            result,
            log,
            monitor,
            manifest,
            allow_trailing_nul=True,
            allow_final_log_only_completion=True,
        )

      log.write_text(
          "00:00:01   starting   c/t0.yml\n"
          "00:00:10              c/t0.yml   TIMEOUT 900 1\n"
          "00:00:11              c/t3.yml   TIMEOUT 900 1\n",
          encoding="utf-8",
      )
      with self.assertRaisesRegex(RuntimeError, "never started"):
        dataset.run_taints(
            result, log, monitor, manifest, allow_trailing_nul=True
        )

      log.write_text(
          "00:00:01   starting   c/t0.yml\n"
          "00:00:10              c/t0.yml   TIMEOUT 900 1\n"
          "00:00:11              c/t0.yml   TIMEOUT 900 1\n",
          encoding="utf-8",
      )
      with self.assertRaisesRegex(RuntimeError, "duplicate"):
        dataset.run_taints(
            result, log, monitor, manifest, allow_trailing_nul=True
        )

      log.write_text(
          "00:00:01   starting   c/unknown.yml\n",
          encoding="utf-8",
      )
      with self.assertRaisesRegex(RuntimeError, "exactly one manifest"):
        dataset.run_taints(
            result, log, monitor, manifest, allow_trailing_nul=True
        )

      log.write_bytes(
          b"00:00:01   starting   c/t0.yml\n"
          b"00:00:10              c/t0.yml   TIMEOUT 900 1\n\0"
      )
      with self.assertRaisesRegex(RuntimeError, "NUL bytes"):
        dataset.run_taints(
            result, log, monitor, manifest, allow_trailing_nul=True
        )

      log.write_text(
          "00:00:10   starting   c/t0.yml\n"
          "00:00:09              c/t0.yml   TIMEOUT 900 1\n",
          encoding="utf-8",
      )
      with self.assertRaisesRegex(RuntimeError, "before it starts"):
        dataset.run_taints(
            result, log, monitor, manifest, allow_trailing_nul=True
        )

      log.write_text(
          "00:00:01   starting   c/t0.yml\n"
          "00:00:31              c/t0.yml   TIMEOUT 900 1\n",
          encoding="utf-8",
      )
      with self.assertRaisesRegex(RuntimeError, "after load monitor ended"):
        dataset.run_taints(
            result, log, monitor, manifest, allow_trailing_nul=True
        )

      write_log([0, 1, 2, 3])
      selection_files = {}
      for name, path in {
          "result": result,
          "benchexec_log": log,
          "load_monitor": monitor,
      }.items():
        selection_files[name] = {
            "path": path.relative_to(root).as_posix(),
            "sha256": dataset.baseline.sha256_file(path),
        }
      for name in (
          "definition",
          "benchexec_process",
          "process_descriptor",
          "monitor_pid",
          "monitor_process",
          "machine_before",
      ):
        path = root / f"evidence/{name}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{name}\n", encoding="utf-8")
        selection_files[name] = {
            "path": path.relative_to(root).as_posix(),
            "sha256": dataset.baseline.sha256_file(path),
        }
      selection = {
          **dataset.FROZEN_CAP16_ATHENA_V2_RECOVERY_SELECTION,
          "files": selection_files,
      }
      record = {
          "schema_version": dataset.FORMAL_ATTEMPT_SCHEMA,
          "label": selection["label"],
          "role": selection["role"],
          "repetition": selection["repetition"],
          "benchexec_exit": 125,
          "result_incomplete": True,
          "files": selection_files,
      }
      authenticated_taint = root / "authenticated-taint.json"
      with mock.patch.object(
          dataset,
          "FROZEN_CAP16_ATHENA_V2_RECOVERY_SELECTION",
          selection,
      ), mock.patch.object(
          dataset,
          "validate_formal_attempt_marker",
          return_value=record,
      ):
        self.assertTrue(
            dataset.marker_authorizes_final_log_only_completion(record)
        )
        self.assertFalse(
            dataset.marker_authorizes_final_log_only_completion({
                **record,
                "schema_version": dataset.LEGACY_FORMAL_ATTEMPT_SCHEMA,
            })
        )
        self.assertFalse(
            dataset.marker_authorizes_final_log_only_completion({
                **record,
                "files": {
                    **selection_files,
                    "result": {
                        **selection_files["result"],
                        "sha256": "0" * 64,
                    },
                },
            })
        )
        dataset.command_formal_taint(SimpleNamespace(
            manifest=str(manifest_path),
            repetition=selection["repetition"],
            result=str(result),
            benchexec_log=str(log),
            load_monitor=str(monitor),
            output=str(authenticated_taint),
            attempt_marker=str(root / f"{selection['label']}.json"),
            output_root=str(root),
            sv_benchmarks=str(root),
            host="athena",
            mode="cap16",
        ))
      self.assertEqual(
          [
              row["task"]
              for row in json.loads(
                  authenticated_taint.read_text(encoding="utf-8")
              )["tasks"]
          ],
          ["c/t3.yml", "c/t4.yml"],
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

  def test_screen_plan_preserves_untainted_rows_and_replaces_only_tainted(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      fixture = phase_b_fixture(root)
      manifest_path = Path(fixture.parent_manifest)
      manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
      manifest["derivation"] = {"host": "athena"}
      manifest_path.write_text(
          json.dumps(manifest), encoding="utf-8"
      )
      property_file = root / "c/properties/unreach-call.prp"
      generated = root / "generated"
      dataset.command_render(
          SimpleNamespace(
              manifest=str(manifest_path),
              sv_benchmarks=str(root),
              property_file=str(property_file),
              output_dir=str(generated),
          )
      )
      primary = root / "primary.xml"
      write_stock_result(primary, manifest["tasks"], "athena")
      tainted_tasks = [row["task"] for row in manifest["tasks"][-2:]]
      taint = root / "taint.json"
      taint.write_text(json.dumps({
          "schema_version": dataset.SCREEN_TAINT_SCHEMA,
          "repetition": 1,
          "primary_result_sha256": dataset.baseline.sha256_file(primary),
          "tasks": [
              {"task": task, "reason": "foreign_p_core_contention"}
              for task in sorted(tainted_tasks)
          ],
      }), encoding="utf-8")
      replacement_generated = root / "replacement-generated"
      dataset.command_render_screen_replacement(
          SimpleNamespace(
              manifest=str(manifest_path),
              primary_result=str(primary),
              taint_manifest=str(taint),
              sv_benchmarks=str(root),
              property_file=str(property_file),
              output_dir=str(replacement_generated),
          )
      )
      replacement = root / "replacement.xml"
      write_stock_result(
          replacement,
          [
              row
              for row in manifest["tasks"]
              if row["task"] in tainted_tasks
          ],
          "athena",
          marker="1",
      )
      replacement_taint = root / "replacement-taint.json"
      replacement_taint.write_text(json.dumps({
          "schema_version": dataset.SCREEN_TAINT_SCHEMA,
          "repetition": 1,
          "primary_result_sha256": dataset.baseline.sha256_file(replacement),
          "tasks": [
              {
                  "task": tainted_tasks[-1],
                  "reason": "interrupted_incomplete",
              }
          ],
      }), encoding="utf-8")
      second_generated = root / "second-replacement-generated"
      dataset.command_render_screen_replacement(
          SimpleNamespace(
              manifest=str(manifest_path),
              primary_result=str(replacement),
              taint_manifest=str(replacement_taint),
              sv_benchmarks=str(root),
              property_file=str(property_file),
              output_dir=str(second_generated),
          )
      )
      second_replacement = root / "second-replacement.xml"
      write_stock_result(
          second_replacement,
          [
              row
              for row in manifest["tasks"]
              if row["task"] == tainted_tasks[-1]
          ],
          "athena",
          marker="2",
      )
      second_taint = root / "second-replacement-taint.json"
      second_taint.write_text(json.dumps({
          "schema_version": dataset.SCREEN_TAINT_SCHEMA,
          "repetition": 1,
          "primary_result_sha256": dataset.baseline.sha256_file(
              second_replacement
          ),
          "tasks": [],
      }), encoding="utf-8")
      plan = root / "screen-plan.json"
      dataset.command_screen_plan(
          SimpleNamespace(
              manifest=str(manifest_path),
              primary_result=str(primary),
              taint_manifest=str(taint),
              replacement_result=[
                  str(replacement),
                  str(second_replacement),
              ],
              replacement_definition=[
                  str(replacement_generated / "hard-case-candidates.xml"),
                  str(second_generated / "hard-case-candidates.xml"),
              ],
              replacement_taint_manifest=[
                  str(replacement_taint),
                  str(second_taint),
              ],
              output=str(plan),
              repetition=1,
          )
      )
      output = root / "screen-summary"
      dataset.command_screen_summary_plan(
          SimpleNamespace(
              manifest=str(manifest_path),
              benchmark_definition=str(
                  generated / "hard-case-candidates.xml"
              ),
              screen_plan=str(plan),
              sv_benchmarks=str(root),
              phase_a_host="athena",
              output_dir=str(output),
          )
      )

      provenance = json.loads(
          (output / "row-provenance.json").read_text(encoding="utf-8")
      )
      sources = {
          row["task"]: row["source"] for row in provenance["rows"]
      }
      self.assertEqual(
          {task for task, source in sources.items() if source == "replacement"},
          set(tainted_tasks),
      )
      replacement_hashes = {
          row["task"]: row["result_sha256"]
          for row in provenance["rows"]
          if row["source"] == "replacement"
      }
      self.assertNotEqual(
          replacement_hashes[tainted_tasks[0]],
          replacement_hashes[tainted_tasks[1]],
      )
      self.assertEqual(
          json.loads((output / "summary.json").read_text(encoding="utf-8"))[
              "classifications"
          ],
          {"analysis_survivor": len(manifest["tasks"])},
      )

  def test_cap16_phase_b_authenticates_completed_phase_a(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      source = cap16_phase_a_fixture(root)
      fixture = package_cap16_fixture(source, root / "package")
      with mock.patch.multiple(
          dataset,
          FROZEN_CAP16_ATHENA_MANIFEST_SHA256=fixture.manifest_sha256,
          FROZEN_CAP16_PARENT_MANIFEST_SHA256=fixture.parent_sha256,
          FROZEN_CAP16_PHASE_A_TASK_COUNT=6,
          FROZEN_CAP16_PHASE_A_PACKAGE_AGGREGATE_SHA256=(
              fixture.aggregate_sha256
          ),
      ):
        manifest, host = dataset.authenticate_cap16_phase_a_output(
            fixture.root, fixture.sv_benchmarks
        )
        self.assertEqual(host, "athena")
        self.assertEqual(manifest["task_count"], 6)
        generated = root / "formal"
        dataset.command_render_formal(
            SimpleNamespace(
                phase_a_output=str(fixture.root),
                manifest=str(
                    fixture.root
                    / "summary/candidate-manifest-analysis-survivors.json"
                ),
                sv_benchmarks=str(fixture.sv_benchmarks),
                property_file=str(
                    fixture.sv_benchmarks / "c/properties/unreach-call.prp"
                ),
                output_dir=str(generated),
            )
        )
        definition = ET.parse(
            generated / "hard-case-candidates.xml"
        ).getroot()
        self.assertEqual(definition.get("timelimit"), "900 s")
        (fixture.root / "summary/.complete").unlink()
        with self.assertRaisesRegex(RuntimeError, "not complete"):
          dataset.authenticate_cap16_phase_a_output(
              fixture.root, fixture.sv_benchmarks
          )

  def test_cap16_phase_b_rejects_tampered_phase_a_artifact(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      source = cap16_phase_a_fixture(root)
      fixture = package_cap16_fixture(source, root / "package")
      (fixture.root / "primary.xml").write_text(
          "tampered\n", encoding="utf-8"
      )
      with mock.patch.multiple(
          dataset,
          FROZEN_CAP16_ATHENA_MANIFEST_SHA256=fixture.manifest_sha256,
          FROZEN_CAP16_PARENT_MANIFEST_SHA256=fixture.parent_sha256,
          FROZEN_CAP16_PHASE_A_TASK_COUNT=6,
          FROZEN_CAP16_PHASE_A_PACKAGE_AGGREGATE_SHA256=(
              fixture.aggregate_sha256
          ),
      ):
        with self.assertRaises(RuntimeError):
          dataset.authenticate_cap16_phase_a_output(
              fixture.root, fixture.sv_benchmarks
          )

  def test_cap16_formal_gate_stays_closed_until_package_hash_is_frozen(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      source = cap16_phase_a_fixture(root)
      fixture = package_cap16_fixture(source, root / "package")
      with mock.patch.multiple(
          dataset,
          FROZEN_CAP16_ATHENA_MANIFEST_SHA256=fixture.manifest_sha256,
          FROZEN_CAP16_PARENT_MANIFEST_SHA256=fixture.parent_sha256,
          FROZEN_CAP16_PHASE_A_TASK_COUNT=6,
          FROZEN_CAP16_PHASE_A_PACKAGE_AGGREGATE_SHA256=(
              "PENDING_AFTER_ATHENA_ATTEMPT3"
          ),
      ):
        with self.assertRaisesRegex(RuntimeError, "pending"):
          dataset.authenticate_cap16_phase_a_output(
              fixture.root, fixture.sv_benchmarks
          )

  def test_cap16_phase_a_package_is_relocatable_and_frozen(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      source = cap16_phase_a_fixture(root)
      package = package_cap16_fixture(source, root / "package")
      relocated = root / "relocated"
      shutil.copytree(package.root, relocated)
      shutil.rmtree(package.root)
      pins = {
          "FROZEN_CAP16_ATHENA_MANIFEST_SHA256": package.manifest_sha256,
          "FROZEN_CAP16_PARENT_MANIFEST_SHA256": package.parent_sha256,
          "FROZEN_CAP16_PHASE_A_TASK_COUNT": 6,
          "FROZEN_CAP16_PHASE_A_PACKAGE_AGGREGATE_SHA256": (
              package.aggregate_sha256
          ),
      }
      with mock.patch.multiple(dataset, **pins):
        manifest, host = dataset.authenticate_cap16_phase_a_output(
            relocated, source.sv_benchmarks
        )
      self.assertEqual((manifest["task_count"], host), (6, "athena"))

      complete = relocated / "summary/.complete"
      artifact_path = relocated / "provenance/artifact-manifest.json"
      complete.unlink()
      artifact_path.unlink()
      primary = relocated / "primary.xml"
      result = ET.parse(primary)
      for run in result.getroot().findall("run"):
        run.find("column[@title='status']").set("value", "true")
        run.find("column[@title='category']").set("value", "correct")
      result.write(primary, encoding="unicode")
      plan_path = relocated / "screen-plan.json"
      plan = json.loads(plan_path.read_text(encoding="utf-8"))
      plan["primary"]["sha256"] = dataset.baseline.sha256_file(primary)
      plan_path.write_text(
          json.dumps(plan, indent=2) + "\n", encoding="utf-8"
      )
      shutil.rmtree(relocated / "summary")
      dataset.command_screen_summary_plan(
          SimpleNamespace(
              manifest=str(
                  relocated / "input/candidate-manifest-athena.json"
              ),
              benchmark_definition=str(
                  relocated / "generated/hard-case-candidates.xml"
              ),
              screen_plan=str(plan_path),
              sv_benchmarks=str(source.sv_benchmarks),
              phase_a_host="athena",
              output_dir=str(relocated / "summary"),
          )
      )
      dataset.baseline.write_artifact_manifest(
          relocated, artifact_path, root_label="."
      )
      complete.write_text("complete\n", encoding="utf-8")
      with mock.patch.multiple(dataset, **pins):
        dataset.validate_cap16_phase_a_structure(
            relocated, source.sv_benchmarks, portable=True
        )
        with self.assertRaisesRegex(RuntimeError, "aggregate is not frozen"):
          dataset.authenticate_cap16_phase_a_output(
              relocated, source.sv_benchmarks
          )

  def test_cap16_formal_plan_shrinks_interrupted_replacement_subset(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      fixture = phase_b_fixture(root)
      manifest_path = Path(fixture.parent_manifest)
      manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
      manifest["derivation"] = {"host": "athena"}
      manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
      primary_definition = root / "formal-primary"
      dataset.render_stock(
          SimpleNamespace(
              manifest=str(manifest_path),
              sv_benchmarks=str(root),
              property_file=str(root / "c/properties/unreach-call.prp"),
              output_dir=str(primary_definition),
          ),
          dataset.FORMAL_DISPLAY,
          ("900 s", "910 s", "920 s"),
      )
      primary = root / "primary-formal.xml"
      write_stock_result(
          primary, manifest["tasks"], "athena", formal=True, marker="10"
      )
      pending = [row["task"] for row in manifest["tasks"][-2:]]

      def write_taint(path, result, tasks):
        path.write_text(json.dumps({
            "schema_version": dataset.FORMAL_TAINT_SCHEMA,
            "repetition": 1,
            "primary_result_sha256": dataset.baseline.sha256_file(result),
            "tasks": [
                {"task": task, "reason": "interrupted_incomplete"}
                for task in sorted(tasks)
            ],
        }), encoding="utf-8")

      first_taint = root / "primary-taint.json"
      write_taint(first_taint, primary, pending)
      replacement_definition = root / "replacement-1"
      dataset.render_stock(
          SimpleNamespace(
              manifest=str(manifest_path),
              sv_benchmarks=str(root),
              property_file=str(root / "c/properties/unreach-call.prp"),
              output_dir=str(replacement_definition),
          ),
          dataset.FORMAL_DISPLAY,
          ("900 s", "910 s", "920 s"),
          rows=[
              row for row in manifest["tasks"] if row["task"] in pending
          ],
      )
      replacement = root / "replacement-1.xml"
      write_stock_result(
          replacement,
          [row for row in manifest["tasks"] if row["task"] in pending],
          "athena",
          formal=True,
          marker="11",
      )
      second_taint = root / "replacement-1-taint.json"
      write_taint(second_taint, replacement, pending[-1:])
      second_definition = root / "replacement-2"
      dataset.render_stock(
          SimpleNamespace(
              manifest=str(manifest_path),
              sv_benchmarks=str(root),
              property_file=str(root / "c/properties/unreach-call.prp"),
              output_dir=str(second_definition),
          ),
          dataset.FORMAL_DISPLAY,
          ("900 s", "910 s", "920 s"),
          rows=[
              row
              for row in manifest["tasks"]
              if row["task"] == pending[-1]
          ],
      )
      second = root / "replacement-2.xml"
      write_stock_result(
          second,
          [row for row in manifest["tasks"] if row["task"] == pending[-1]],
          "athena",
          formal=True,
          marker="12",
      )
      final_taint = root / "replacement-2-taint.json"
      write_taint(final_taint, second, [])
      plan_path = root / "cap16-plan.json"
      dataset.command_cap16_repetition_plan(
          SimpleNamespace(
              manifest=str(manifest_path),
              repetition=1,
              primary_result=str(primary),
              taint_manifest=str(first_taint),
              replacement_result=[str(replacement), str(second)],
              replacement_definition=[
                  str(replacement_definition / "hard-case-candidates.xml"),
                  str(second_definition / "hard-case-candidates.xml"),
              ],
              replacement_taint_manifest=[
                  str(second_taint),
                  str(final_taint),
              ],
              output=str(plan_path),
          )
      )
      loaded = dataset.load_screen_plan(
          plan_path,
          dataset.baseline.load_task_manifest(manifest_path),
          manifest_path,
          "athena",
          root,
          primary_definition / "hard-case-candidates.xml",
          plan_schema=dataset.CAP16_FORMAL_REPETITION_PLAN_SCHEMA,
          repetition=1,
          display=dataset.FORMAL_DISPLAY,
          time_limit="900 s",
          taint_schema=dataset.FORMAL_TAINT_SCHEMA,
          definition_validator=dataset.validate_formal_definition,
      )
      sources = {row["task"]: row for row in loaded["row_sources"]}
      self.assertNotEqual(
          sources[pending[0]]["result_sha256"],
          sources[pending[1]]["result_sha256"],
      )

  def test_cap16_rerenders_only_pending_authenticated_replacement_rows(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      property_file = root / "c/properties/unreach-call.prp"
      property_file.parent.mkdir(parents=True)
      property_file.write_text("CHECK\n", encoding="utf-8")
      tasks = []
      for index in range(224):
        task_path = f"c/tasks/task-{index:03}.yml"
        source_path = f"c/tasks/task-{index:03}.c"
        for path in (task_path, source_path):
          target = root / path
          target.parent.mkdir(parents=True, exist_ok=True)
          target.write_text(f"{path}\n", encoding="utf-8")
        tasks.append({
            "task": task_path,
            "task_path": task_path,
            "source": "sv-benchmarks",
            "source_paths": [source_path],
            "expected_verdict": "true",
            "benchmark_set": "Loops",
        })
      manifest_path = root / "manifest.json"
      manifest = {
          "task_count": len(tasks),
          "derivation": {"host": "athena"},
          "tasks": tasks,
      }
      manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
      manifest_rows = dataset.baseline.load_task_manifest(manifest_path)
      output_root = root / "formal"
      label = "repetition-1-replacement-attempt-1"
      primary = output_root / f"results/{label}/result.xml"
      primary.parent.mkdir(parents=True)
      write_stock_result(
          primary, tasks[:174], "athena", formal=True, marker="10"
      )
      primary_root = ET.parse(primary).getroot()
      primary_root.set("error", "incomplete")
      del primary_root.attrib["endtime"]
      for index, run in enumerate(primary_root.findall("run")):
        run.set("name", str(root / tasks[index]["task_path"]))
        run.set("files", f"[{root / tasks[index]['source_paths'][0]}]")
        run.set("propertyFile", str(property_file))
      for run in primary_root.findall("run")[3:]:
        for column in list(run):
          run.remove(column)
      ET.ElementTree(primary_root).write(primary, encoding="unicode")
      expected_tasks = sorted(row["task"] for row in tasks[:174])

      def marker_record(
          result,
          result_tasks=expected_tasks,
          benchexec_exit=125,
          result_incomplete=True,
          repetition=1,
      ):
        return {
            "role": "replacement",
            "repetition": repetition,
            "benchexec_exit": benchexec_exit,
            "result_incomplete": result_incomplete,
            "result_tasks": result_tasks,
            "files": {
                "result": {
                    "path": result.relative_to(output_root).as_posix(),
                }
            },
        }

      taint = root / "taint.json"
      taint.write_text(json.dumps({
          "schema_version": dataset.FORMAL_TAINT_SCHEMA,
          "repetition": 1,
          "primary_result_sha256": dataset.baseline.sha256_file(primary),
          "tasks": [
              {
                  "task": row["task"],
                  "reason": "interrupted_incomplete",
              }
              for row in tasks[3:174]
          ],
      }), encoding="utf-8")
      args = SimpleNamespace(
          phase_a_output=str(root / "phase-a"),
          manifest=str(manifest_path),
          sv_benchmarks=str(root),
          primary_result=str(primary),
          taint_manifest=str(taint),
          property_file=str(property_file),
          output_dir=str(root / "replacement-2"),
      )
      with mock.patch.object(
          dataset,
          "authenticate_formal_manifest",
          return_value=(manifest, "athena"),
      ), mock.patch.object(
          dataset,
          "validate_formal_attempt_marker",
          return_value=marker_record(primary),
      ):
        dataset.command_render_formal_replacement(args)
      task_set = root / "replacement-2/hard-case-candidates-official.set"
      self.assertEqual(len(task_set.read_text().splitlines()), 171)
      self.assertEqual(
          task_set.read_text().splitlines(),
          [str(root / row["task_path"]) for row in tasks[3:174]],
      )

      contended = primary.with_name("contended.xml")
      contended_root = ET.parse(primary).getroot()
      del contended_root.attrib["error"]
      contended_root.set("endtime", "2026-07-27T00:01:12+08:00")
      for run in contended_root.findall("run"):
        if not list(run):
          for title, value in (
              ("status", "TIMEOUT"),
              ("category", "error"),
              ("cputime", "900s"),
              ("walltime", "900s"),
          ):
            ET.SubElement(run, "column", {"title": title, "value": value})
      ET.ElementTree(contended_root).write(contended, encoding="unicode")
      contended_taint = root / "contended-taint.json"
      contended_tasks = [tasks[10]["task"], tasks[15]["task"]]
      contended_taint.write_text(json.dumps({
          "schema_version": dataset.FORMAL_TAINT_SCHEMA,
          "repetition": 1,
          "primary_result_sha256": dataset.baseline.sha256_file(contended),
          "tasks": [
              {"task": task, "reason": "foreign_p_core_contention"}
              for task in contended_tasks
          ],
      }), encoding="utf-8")
      contended_args = SimpleNamespace(
          **{
              **vars(args),
              "primary_result": str(contended),
              "taint_manifest": str(contended_taint),
              "output_dir": str(root / "contended-replacement"),
          }
      )
      with mock.patch.object(
          dataset,
          "authenticate_formal_manifest",
          return_value=(manifest, "athena"),
      ), mock.patch.object(
          dataset,
          "validate_formal_attempt_marker",
          return_value=marker_record(
              contended, benchexec_exit=0, result_incomplete=False
          ),
      ):
        dataset.command_render_formal_replacement(contended_args)
      self.assertEqual(
          (root / "contended-replacement/"
           "hard-case-candidates-official.set").read_text().splitlines(),
          [str(root / tasks[index]["task_path"]) for index in (10, 15)],
      )
      bad_repetition_args = SimpleNamespace(
          **{**vars(args), "output_dir": str(root / "bad-repetition")}
      )
      with mock.patch.object(
          dataset,
          "authenticate_formal_manifest",
          return_value=(manifest, "athena"),
      ), mock.patch.object(
          dataset,
          "validate_formal_attempt_marker",
          return_value=marker_record(primary, repetition=2),
      ), self.assertRaisesRegex(RuntimeError, "repetition does not match"):
        dataset.command_render_formal_replacement(bad_repetition_args)

      full = root / "full.xml"
      write_stock_result(full, tasks, "athena", formal=True, marker="11")
      with mock.patch.object(
          dataset,
          "validate_formal_attempt_marker",
          side_effect=AssertionError("full results must stay on the strict path"),
      ):
        self.assertEqual(
            dataset.formal_replacement_result_manifest(
                args, full, manifest_rows, "athena"
            ),
            (manifest_rows, None),
        )

      full_replacement = (
          output_root
          / "results/repetition-2-replacement-attempt-1/result.xml"
      )
      full_replacement.parent.mkdir(parents=True)
      shutil.copyfile(full, full_replacement)
      full_taint = root / "full-replacement-taint.json"
      full_taint.write_text(json.dumps({
          "schema_version": dataset.FORMAL_TAINT_SCHEMA,
          "repetition": 2,
          "primary_result_sha256": (
              dataset.baseline.sha256_file(full_replacement)
          ),
          "tasks": [{
              "task": tasks[20]["task"],
              "reason": "foreign_p_core_contention",
          }],
      }), encoding="utf-8")
      full_replacement_args = SimpleNamespace(**{
          **vars(args),
          "primary_result": str(full_replacement),
          "taint_manifest": str(full_taint),
          "output_dir": str(root / "full-replacement"),
      })
      full_record = marker_record(
          full_replacement,
          result_tasks=sorted(row["task"] for row in tasks),
          benchexec_exit=0,
          result_incomplete=False,
          repetition=2,
      )
      with mock.patch.object(
          dataset,
          "authenticate_formal_manifest",
          return_value=(manifest, "athena"),
      ), mock.patch.object(
          dataset,
          "validate_formal_attempt_marker",
          return_value=full_record,
      ) as marker:
        dataset.command_render_formal_replacement(full_replacement_args)
      marker.assert_called_once()
      self.assertEqual(
          (root / "full-replacement/"
           "hard-case-candidates-official.set").read_text().splitlines(),
          [str(root / tasks[20]["task_path"])],
      )
      with self.assertRaises(FileNotFoundError):
        dataset.formal_replacement_result_manifest(
            args, full_replacement, manifest_rows, "athena"
        )
      with mock.patch.object(
          dataset,
          "validate_formal_attempt_marker",
          side_effect=RuntimeError("invalid marker"),
      ), self.assertRaisesRegex(RuntimeError, "invalid marker"):
        dataset.formal_replacement_result_manifest(
            args, full_replacement, manifest_rows, "athena"
        )

      cap8_args = SimpleNamespace(
          manifest=str(manifest_path), sv_benchmarks=str(root)
      )
      with self.assertRaisesRegex(RuntimeError, "full manifest"):
        dataset.formal_replacement_result_manifest(
            cap8_args, primary, manifest_rows, "valkyrie"
        )

      mutations = {}
      for name in ("missing", "extra", "wrong", "duplicate"):
        path = primary.with_name(f"{name}.xml")
        tree = ET.parse(primary)
        runs = tree.getroot().findall("run")
        if name == "missing":
          tree.getroot().remove(runs[-1])
        elif name == "extra":
          extra = ET.parse(full).getroot().findall("run")[174]
          tree.getroot().append(copy.deepcopy(extra))
        elif name == "wrong":
          runs[0].set("name", str(root / "c/tasks/not-in-manifest.yml"))
        else:
          runs[1].set("name", runs[0].get("name"))
        tree.write(path, encoding="unicode")
        mutations[name] = path
      for name, path in mutations.items():
        with self.subTest(name=name), mock.patch.object(
            dataset,
            "validate_formal_attempt_marker",
            return_value=marker_record(path),
        ), self.assertRaises(RuntimeError):
          dataset.formal_replacement_result_manifest(
              args, path, manifest_rows, "athena"
          )

  def test_formal_recovery_selects_50_row_abandoned_attempt_once(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      source = (
          root / "provenance/abandoned/"
          "repetition-1-1785246981276501974"
      )
      selected_results = source / "results"
      canonical_results = root / "results/repetition-1"
      selected_provenance = source / "provenance"
      canonical_provenance = root / "provenance"
      selected_results.mkdir(parents=True)
      canonical_results.mkdir(parents=True)
      selected_provenance.mkdir()

      def write_incomplete_result(path, complete):
        result = ET.Element("result", error="incomplete")
        for index in range(224):
          run = ET.SubElement(result, "run", name=f"task-{index}.yml")
          if index < complete:
            for title in ("cputime", "memory", "status", "walltime"):
              ET.SubElement(run, "column", title=title, value="1")
        ET.ElementTree(result).write(path, encoding="unicode")

      selected_result = selected_results / "selected.xml"
      displaced_result = canonical_results / "displaced.xml"
      write_incomplete_result(selected_result, 50)
      write_incomplete_result(displaced_result, 0)
      abandoned = source / "ABANDONED"
      abandoned.write_text(
          "reason=missing-atomic-attempt-completion\n", encoding="utf-8"
      )
      selected_evidence = selected_provenance / "attempt.process.json"
      displaced_evidence = canonical_provenance / "attempt.process.json"
      selected_evidence.write_text("selected\n", encoding="utf-8")
      displaced_evidence.write_text("displaced\n", encoding="utf-8")
      spec = {
          "label": "repetition-1",
          "source": source.relative_to(root).as_posix(),
          "quarantine": (
              "provenance/abandoned/"
              "repetition-1-superseded-zero-row-rerun"
          ),
          "abandoned_sha256": dataset.baseline.sha256_file(abandoned),
          "selected_results_digest": (
              dataset.formal_result_directory_digest(selected_results)
          ),
          "displaced_results_digest": (
              dataset.formal_result_directory_digest(canonical_results)
          ),
          "selected_result_sha256": (
              dataset.baseline.sha256_file(selected_result)
          ),
          "displaced_result_sha256": (
              dataset.baseline.sha256_file(displaced_result)
          ),
          "selected_complete_rows": 50,
          "displaced_complete_rows": 0,
          "result_rows": 224,
          "selected_provenance": {
              selected_evidence.name: dataset.baseline.sha256_file(
                  selected_evidence
              )
          },
          "displaced_provenance": {
              displaced_evidence.name: dataset.baseline.sha256_file(
                  displaced_evidence
              )
          },
      }
      spec_path = root / "recovery-spec.json"
      spec_path.write_text(json.dumps(spec), encoding="utf-8")
      crashed = subprocess.run(
          [
              "/usr/bin/python3",
              "-I",
              "-c",
              (
                  "import importlib.util, json, os, sys\n"
                  "p = importlib.util.spec_from_file_location('d', sys.argv[1])\n"
                  "d = importlib.util.module_from_spec(p)\n"
                  "p.loader.exec_module(d)\n"
                  "real = d.os.replace\n"
                  "count = [0]\n"
                  "def replace(a, b):\n"
                  "  count[0] += 1\n"
                  "  real(a, b)\n"
                  "  if count[0] == 3:\n"
                  "    os._exit(91)\n"
                  "d.os.replace = replace\n"
                  "d.restore_formal_attempt(\n"
                  "    sys.argv[2], json.load(open(sys.argv[3])))\n"
              ),
              str(Path(dataset.__file__).resolve()),
              str(root),
              str(spec_path),
          ],
          check=False,
      )
      self.assertEqual(crashed.returncode, 91)
      self.assertTrue(
          root.joinpath(
              "provenance/recovery-selections/repetition-1.prepared.json"
          ).is_file()
      )
      selection = dataset.restore_formal_attempt(root, spec)
      dataset.restore_formal_attempt(root, spec)
      self.assertTrue(selection.is_file())
      self.assertEqual(
          dataset.baseline.sha256_file(
              canonical_results / selected_result.name
          ),
          spec["selected_result_sha256"],
      )
      quarantine = root / spec["quarantine"]
      self.assertEqual(
          dataset.baseline.sha256_file(
              quarantine / "results" / displaced_result.name
          ),
          spec["displaced_result_sha256"],
      )
      self.assertFalse(selected_results.exists())
      self.assertFalse(selected_evidence.exists())
      prepared = selection.with_suffix(".prepared.json")
      prepared.write_text(
          json.dumps({
              **dataset.recovery_selection_record(spec),
              "state": "prepared",
          }, indent=2, sort_keys=True) + "\n",
          encoding="utf-8",
      )
      dataset.restore_formal_attempt(root, spec)
      self.assertFalse(prepared.exists())
      forged = json.loads(selection.read_text(encoding="utf-8"))
      forged["selected_complete_rows"] = 0
      selection.write_text(json.dumps(forged), encoding="utf-8")
      with self.assertRaisesRegex(RuntimeError, "ledger differs"):
        dataset.restore_formal_attempt(root, spec)

  def test_recovered_machine_identity_ignores_memtotal_but_not_hardware(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      before = root / "before.json"
      after = root / "after.json"
      snapshot = {
          "hostname": "athena",
          "platform": "Linux-6.8.0-x86_64-with-glibc2.39",
          "kernel": "6.8.0-71-generic",
          "cpu_model": "13th Gen Intel(R) Core(TM) i9-13900K",
          "online_cpus": "0-31",
          "allowed_p_core_cpus": list(dataset.FORMAL_P_CORE_CPUS[::2]),
          "memory_bytes": 134795411456,
          "java_version": "openjdk 21.0.10 2026-01-20",
      }
      before.write_text(json.dumps(snapshot), encoding="utf-8")
      after.write_text(
          json.dumps({**snapshot, "memory_bytes": 134795423744}),
          encoding="utf-8",
      )
      binding = {"rebooted": True}
      self.assertTrue(
          dataset.recovered_machine_check_record(
              before, after, binding
          )["accepted"]
      )
      after.write_text(
          json.dumps({
              **snapshot,
              "memory_bytes": snapshot["memory_bytes"] // 2,
          }),
          encoding="utf-8",
      )
      self.assertTrue(
          dataset.recovered_machine_check_record(
              before, after, binding
          )["accepted"]
      )
      for field, changed in (
          ("hostname", "cthulhu"),
          ("platform", "changed"),
          ("kernel", "changed"),
          ("cpu_model", "changed"),
          ("online_cpus", "0-15"),
          ("allowed_p_core_cpus", [0, 2]),
          ("java_version", "changed"),
      ):
        after.write_text(
            json.dumps({
                **snapshot,
                "memory_bytes": snapshot["memory_bytes"] // 2,
                field: changed,
            }),
            encoding="utf-8",
        )
        with self.subTest(field=field), self.assertRaisesRegex(
            RuntimeError, "machine identity changed"
        ):
          dataset.recovered_machine_check_record(before, after, binding)

  def test_frozen_v2_markerless_recovery_selection_is_exact(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      paths = {}
      for name in (
          "definition",
          "benchexec_log",
          "benchexec_process",
          "process_descriptor",
          "load_monitor",
          "monitor_pid",
          "monitor_process",
          "machine_before",
      ):
        path = root / f"evidence/{name}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{name}\n", encoding="utf-8")
        paths[name] = path
      result_directory = root / "results/replacement"
      result_directory.mkdir(parents=True)
      result = result_directory / "result.xml"
      result.write_text("result\n", encoding="utf-8")
      partial = result_directory / "partial.log"
      partial.write_text("partial\n", encoding="utf-8")
      required_directory = result_directory / "result.logfiles"
      required_directory.mkdir()
      paths["result"] = result
      closure = root / "generated/tasks.set"
      closure.parent.mkdir()
      closure.write_text("task\n", encoding="utf-8")
      captured_boot = "11111111-1111-1111-1111-111111111111"
      recovery_boot = "22222222-2222-2222-2222-222222222222"
      identities = {
          role: {
              "schema_version": dataset.FORMAL_PROCESS_IDENTITY_SCHEMA,
              "boot_id": captured_boot,
          }
          for role in ("benchexec-launcher", "load-monitor")
      }
      selection = {
          "label": "repetition-1-replacement-attempt-1",
          "role": "replacement",
          "repetition": 1,
          "captured_boot_id": captured_boot,
          "result_directory": result_directory.relative_to(root).as_posix(),
          "result_directory_digest": (
              dataset.formal_result_directory_digest(result_directory)
          ),
          "result_directories": ("result.logfiles",),
          "files": {
              name: {
                  "path": path.relative_to(root).as_posix(),
                  "sha256": dataset.baseline.sha256_file(path),
              }
              for name, path in paths.items()
          },
          "closure_files": {
              closure.relative_to(root).as_posix(): (
                  dataset.baseline.sha256_file(closure)
              ),
          },
      }
      selection_patch = mock.patch.object(
          dataset,
          "FROZEN_CAP16_ATHENA_V2_RECOVERY_SELECTION",
          selection,
      )
      boot_patch = mock.patch.object(
          dataset, "read_boot_id", return_value=recovery_boot
      )
      selection_patch.start()
      boot_mock = boot_patch.start()
      self.addCleanup(selection_patch.stop)
      self.addCleanup(boot_patch.stop)

      self.assertTrue(
          dataset.validate_markerless_recovery_identity_selection(
              root,
              selection["label"],
              selection["role"],
              selection["repetition"],
              paths,
              identities,
          )
      )
      self.assertFalse(
          dataset.validate_markerless_recovery_identity_selection(
              root,
              "repetition-1",
              "primary",
              1,
              paths,
              {
                  role: {
                      "schema_version": (
                          dataset.LEGACY_FORMAL_PROCESS_IDENTITY_SCHEMA
                      )
                  }
                  for role in ("benchexec-launcher", "load-monitor")
              },
          )
      )

      extra_directory = result_directory / "extra"
      extra_directory.mkdir()
      with self.assertRaisesRegex(RuntimeError, "selection differs"):
        dataset.validate_markerless_recovery_identity_selection(
            root,
            selection["label"],
            selection["role"],
            selection["repetition"],
            paths,
            identities,
        )
      extra_directory.rmdir()

      fifo = result_directory / "extra.fifo"
      os.mkfifo(fifo)
      try:
        with self.assertRaisesRegex(RuntimeError, "selection differs"):
          dataset.validate_markerless_recovery_identity_selection(
              root,
              selection["label"],
              selection["role"],
              selection["repetition"],
              paths,
              identities,
          )
      finally:
        fifo.unlink()

      nested_directory = required_directory / "nested"
      nested_directory.mkdir()
      with self.assertRaisesRegex(RuntimeError, "selection differs"):
        dataset.validate_markerless_recovery_identity_selection(
            root,
            selection["label"],
            selection["role"],
            selection["repetition"],
            paths,
            identities,
        )
      nested_directory.rmdir()

      required_directory.rmdir()
      with self.assertRaisesRegex(RuntimeError, "selection differs"):
        dataset.validate_markerless_recovery_identity_selection(
            root,
            selection["label"],
            selection["role"],
            selection["repetition"],
            paths,
            identities,
        )
      required_directory.mkdir()

      for label, role, repetition in (
          ("repetition-1", selection["role"], selection["repetition"]),
          (selection["label"], "primary", selection["repetition"]),
          (selection["label"], selection["role"], 2),
      ):
        with self.subTest(
            label=label, role=role, repetition=repetition
        ), self.assertRaisesRegex(RuntimeError, "exact frozen v2"):
          dataset.validate_markerless_recovery_identity_selection(
              root, label, role, repetition, paths, identities
          )

      for name, path in paths.items():
        original = path.read_bytes()
        path.write_bytes(original + b"x")
        with self.subTest(file=name), self.assertRaisesRegex(
            RuntimeError, "selection differs"
        ):
          dataset.validate_markerless_recovery_identity_selection(
              root,
              selection["label"],
              selection["role"],
              selection["repetition"],
              paths,
              identities,
          )
        path.write_bytes(original)

      for relative in selection["closure_files"]:
        path = root / relative
        original = path.read_bytes()
        path.write_bytes(original + b"x")
        with self.subTest(closure=relative), self.assertRaisesRegex(
            RuntimeError, "selection differs"
        ):
          dataset.validate_markerless_recovery_identity_selection(
              root,
              selection["label"],
              selection["role"],
              selection["repetition"],
              paths,
              identities,
          )
        path.write_bytes(original)

      for path in result_directory.iterdir():
        if not path.is_file():
          continue
        original = path.read_bytes()
        path.write_bytes(original + b"x")
        with self.subTest(result_member=path.name), self.assertRaisesRegex(
            RuntimeError, "selection differs"
        ):
          dataset.validate_markerless_recovery_identity_selection(
              root,
              selection["label"],
              selection["role"],
              selection["repetition"],
              paths,
              identities,
          )
        path.write_bytes(original)

      mixed = {
          **identities,
          "load-monitor": {
              "schema_version": (
                  dataset.LEGACY_FORMAL_PROCESS_IDENTITY_SCHEMA
              ),
          },
      }
      with self.assertRaisesRegex(RuntimeError, "schemas do not match"):
        dataset.validate_markerless_recovery_identity_selection(
            root,
            selection["label"],
            selection["role"],
            selection["repetition"],
            paths,
            mixed,
        )

      boot_mismatch = {
          role: {**identity} for role, identity in identities.items()
      }
      boot_mismatch["load-monitor"]["boot_id"] = recovery_boot
      with self.assertRaisesRegex(RuntimeError, "boot identity differs"):
        dataset.validate_markerless_recovery_identity_selection(
            root,
            selection["label"],
            selection["role"],
            selection["repetition"],
            paths,
            boot_mismatch,
        )

      boot_mock.return_value = captured_boot
      with self.assertRaisesRegex(RuntimeError, "not bound across reboot"):
        dataset.validate_markerless_recovery_identity_selection(
            root,
            selection["label"],
            selection["role"],
            selection["repetition"],
            paths,
            identities,
        )
  def test_cap16_probe_plan_authenticates_one_core_primary(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      fixture = phase_b_fixture(root)
      manifest_path = Path(fixture.parent_manifest)
      manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
      definition_dir = root / "probe-definition"
      dataset.render_probe(
          manifest_path,
          manifest,
          manifest["tasks"],
          root,
          root / "c/properties/unreach-call.prp",
          definition_dir,
      )
      primary = root / "probe-primary.xml"
      write_stock_result(
          primary, manifest["tasks"], "athena", probe=True
      )
      plan_path = root / "probe-plan.json"
      dataset.command_cap16_probe_plan(
          SimpleNamespace(
              manifest=str(manifest_path),
              repetition=1,
              primary_result=str(primary),
              taint_manifest=None,
              replacement_result=None,
              replacement_definition=None,
              replacement_taint_manifest=None,
              output=str(plan_path),
          )
      )

      loaded = dataset.load_screen_plan(
          plan_path,
          dataset.baseline.load_task_manifest(manifest_path),
          manifest_path,
          "athena",
          root,
          definition_dir / "cegar-eligibility.xml",
          plan_schema=dataset.CAP16_PROBE_PLAN_SCHEMA,
          display=dataset.PROBE_DISPLAY,
          time_limit="900 s",
          taint_schema=dataset.CAP16_PROBE_TAINT_SCHEMA,
          definition_validator=dataset.validate_probe_definition,
      )

      self.assertEqual(len(loaded["rows"]), len(manifest["tasks"]))

  def test_probe_unclosed_monitor_stop_requires_authenticated_recovery(self):
    with tempfile.TemporaryDirectory() as temp:
      stopped = Path(temp) / "monitor.stopped"
      stopped.write_text(
          "pid=123\nexit=unobserved\nsamples=4\n"
          "recovery=authenticated-process-gone\n",
          encoding="utf-8",
      )

      self.assertTrue(
          dataset.validate_monitor_stop_evidence(
              stopped, 123, "cap16-probe", 125
          )
      )
      self.assertTrue(
          dataset.validate_monitor_stop_evidence(
              stopped, 123, "cap8-probe", 125
          )
      )
      stopped.write_text(
          "pid=123\nexit=0\nsamples=4\n", encoding="utf-8"
      )
      self.assertFalse(
          dataset.validate_monitor_stop_evidence(
              stopped, 123, "cap16-probe", 125
          )
      )
      with self.assertRaisesRegex(RuntimeError, "stop evidence"):
        dataset.validate_monitor_stop_evidence(
            stopped, 123, "cap16", 125
        )
      stopped.write_text(
          "pid=123\nexit=unobserved\nsamples=4\n"
          "recovery=authenticated-process-gone\n",
          encoding="utf-8",
      )
      self.assertTrue(
          dataset.validate_monitor_stop_evidence(
              stopped, 123, "cap16", 125
          )
      )
      for mode, status in (
          ("cap8", 125),
          ("cap16-probe", 130),
          ("cap8-probe", 130),
      ):
        with self.assertRaisesRegex(RuntimeError, "stop evidence"):
          dataset.validate_monitor_stop_evidence(
              stopped, 123, mode, status
          )

  def test_cap8_probe_process_descriptor_is_fixed_to_valkyrie_one_core(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      label = "repetition-1"
      descriptor = dataset.formal_process_descriptor(SimpleNamespace(
          output_root=str(root),
          mode="cap8-probe",
          label=label,
          host="valkyrie",
          name=(
              "hard-case-dataset-v2-cap8-cegar-probe-valkyrie-"
              + label
          ),
          definition=str(root / "generated/cegar-eligibility.xml"),
          result_output=str(root / "results/repetition-1"),
          monitor_output=str(root / "provenance/load.jsonl"),
          monitor_exclude_root=123,
          dataset_py=str(root / "input/research/scripts/dataset.py"),
          cpachecker_dir=str(root / "cpachecker"),
          benchexec_dir=str(root / "benchexec"),
          python_bin="/usr/bin/python3.10",
          java_home=str(root / "jdk"),
          p_cores=dataset.FORMAL_P_CORE_LIST,
      ))
      argv = descriptor["identities"]["benchexec-launcher"]["argv"]
      self.assertEqual(descriptor["host"], "valkyrie")
      self.assertEqual(argv[argv.index("-N") + 1], "8")
      self.assertEqual(argv[argv.index("-c", argv.index("-N")) + 1], "1")
      python_index = argv.index("/usr/bin/python3.10")
      self.assertEqual(
          argv[python_index + 1:python_index + 6],
          list(dataset.PYTHON_RUNTIME_FLAGS),
      )
      self.assertEqual(
          argv[argv.index(str(root / "benchexec")) + 1],
          dataset.FORMAL_PYYAML_FILE,
      )

  def test_probe_result_metadata_preserves_one_fixed_profile_host(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      tasks = phase_b_fixture(root).rows
      for host in ("valkyrie", "athena"):
        result = root / f"{host}.xml"
        write_stock_result(result, tasks, host, probe=True)
        self.assertEqual(
            dataset.probe_result_metadata(result)["host"], host
        )
      result = root / "athena.xml"
      xml = ET.parse(result)
      ET.SubElement(xml.getroot(), "systeminfo", {"hostname": "valkyrie"})
      xml.write(result, encoding="unicode")
      with self.assertRaisesRegex(RuntimeError, "exactly one"):
        dataset.probe_result_metadata(result)

  def test_formal_attempt_marker_requires_atomic_teardown_closure(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      fixture = phase_b_fixture(root)
      manifest_path = Path(fixture.parent_manifest)
      definition_dir = root / "definition"
      dataset.render_stock(
          SimpleNamespace(
              manifest=str(manifest_path),
              sv_benchmarks=str(root),
              property_file=str(root / "c/properties/unreach-call.prp"),
              output_dir=str(definition_dir),
          ),
          dataset.FORMAL_DISPLAY,
          ("900 s", "910 s", "920 s"),
      )
      result = root / "result.xml"
      write_stock_result(
          result, fixture.rows, "athena", formal=True, marker="20"
      )
      second_result = root / "result-2.xml"
      write_stock_result(
          second_result, fixture.rows, "athena", formal=True, marker="21"
      )
      log = root / "benchexec.log"
      log.write_text("complete log\n", encoding="utf-8")
      monitor = root / "monitor.jsonl"
      monitor.write_text(
          json.dumps({
              "schema_version": dataset.FORMAL_LOAD_MONITOR_SCHEMA,
              "p_core_cpus": list(dataset.FORMAL_P_CORE_CPUS),
              "foreign_process_cpu_percent": (
                  dataset.FORMAL_FOREIGN_CPU_PERCENT
              ),
              "minimum_consecutive_seconds": (
                  dataset.FORMAL_FOREIGN_CPU_SECONDS
              ),
              "sample_interval_seconds": dataset.FORMAL_LOAD_SAMPLE_SECONDS,
              "excluded_process_root": 123,
          })
          + "\n"
          + json.dumps({
              "timestamp": "2026-07-27T00:00:30+08:00",
              "elapsed_seconds": 1,
              "offenders": [],
          })
          + "\n",
          encoding="utf-8",
      )
      pid = root / "monitor.pid"
      owned = subprocess.Popen(["sleep", "0.01"])
      identity = dataset.read_process_identity(owned.pid, "load-monitor")
      owned.wait()
      pid.write_text(f"{owned.pid}\n", encoding="utf-8")
      saved_dataset = root / "input/research/scripts/dataset.py"
      saved_dataset.parent.mkdir(parents=True)
      saved_dataset.write_text("saved\n", encoding="utf-8")
      recovery_head = "b" * 40
      recovery_provenance = (
          root / f"input/recovery-research-{recovery_head}"
      )
      recovery_scripts = recovery_provenance / "scripts"
      recovery_scripts.mkdir(parents=True)
      for name in (
          "baseline.py",
          "dataset.py",
          "run-stock-cap16-formal-dataset.sh",
          "run-stock-formal-dataset.sh",
      ):
        (recovery_scripts / name).write_text(
            f"{name}\n", encoding="utf-8"
        )
      (recovery_provenance / "research-head.txt").write_text(
          f"{recovery_head}\n", encoding="utf-8"
      )
      (recovery_provenance / "research-status.porcelain").write_text(
          "", encoding="utf-8"
      )
      (recovery_provenance / "research-diff.patch").write_text(
          "", encoding="utf-8"
      )
      (recovery_provenance / "research-index-flags.txt").write_text(
          "flags\n", encoding="utf-8"
      )
      (recovery_provenance / "research-state.json").write_text(
          json.dumps(
              {
                  "head": recovery_head,
                  "clean": True,
                  "status_sha256": dataset.baseline.sha256_file(
                      recovery_provenance / "research-status.porcelain"
                  ),
                  "diff_sha256": dataset.baseline.sha256_file(
                      recovery_provenance / "research-diff.patch"
                  ),
              },
              indent=2,
          )
          + "\n",
          encoding="utf-8",
      )
      (recovery_provenance / "inventory.sha256").write_text(
          "".join(
              f"{dataset.baseline.sha256_file(path)}  "
              f"{path.relative_to(recovery_provenance).as_posix()}\n"
              for path in sorted(recovery_provenance.rglob("*"))
              if path.is_file() and path.name != "inventory.sha256"
          ),
          encoding="utf-8",
      )

      def write_process_descriptor(
          label,
          path,
          definition=None,
          result_output=None,
          monitor_output=None,
          monitor_exclude_root=123,
          mode="cap16",
      ):
        descriptor_args = SimpleNamespace(
            output_root=str(root),
            mode=mode,
            label=label,
            host="athena",
            name=(
                (
                    "hard-case-dataset-v2-cap16-cegar-probe-athena-"
                    if mode == "cap16-probe"
                    else "hard-case-dataset-v2-cap16-formal-athena-"
                )
                + label
            ),
            definition=str(
                definition
                or definition_dir / "hard-case-candidates.xml"
            ),
            result_output=str(result_output or root),
            monitor_output=str(monitor_output or monitor),
            monitor_exclude_root=monitor_exclude_root,
            dataset_py=str(saved_dataset),
            cpachecker_dir=str(root / "cpachecker"),
            benchexec_dir=str(root / "benchexec"),
            python_bin="/usr/bin/python3.12",
            java_home=str(root / "jdk"),
            p_cores=dataset.FORMAL_P_CORE_LIST,
            output=str(path),
        )
        dataset.command_write_formal_process_descriptor(descriptor_args)
        return dataset.load_formal_process_descriptor(
            path, root, mode, label, "athena"
        )

      process_descriptor = root / "repetition-1-process-descriptor.json"
      descriptor = write_process_descriptor(
          "repetition-1", process_descriptor
      )
      process_identity = root / "monitor.process.json"
      identity["argv"] = descriptor["identities"]["load-monitor"]["argv"]
      process_identity.write_text(
          json.dumps(identity), encoding="utf-8"
      )
      for field, value in (
          ("pid", -1),
          ("proc_starttime", None),
          ("uid", True),
          ("argv", ["valid", 1]),
          ("boot_id", "forged"),
      ):
        forged_identity = root / f"forged-{field}.json"
        forged_identity.write_text(
            json.dumps({**identity, field: value}), encoding="utf-8"
        )
        with self.assertRaisesRegex(RuntimeError, "identity is invalid"):
          dataset.load_owned_process_identity(forged_identity)
      benchexec_identity = root / "benchexec.process.json"
      launcher_identity = {
          **identity,
          "role": "benchexec-launcher",
          **descriptor["identities"]["benchexec-launcher"],
      }
      benchexec_identity.write_text(
          json.dumps(launcher_identity), encoding="utf-8"
      )
      systemctl = mock.patch.object(
          dataset.subprocess,
          "run",
          return_value=SimpleNamespace(
              returncode=0,
              stdout=(
                  "LoadState=not-found\n"
                  "ActiveState=inactive\n"
              ),
          ),
      )
      systemctl_mock = systemctl.start()
      self.addCleanup(systemctl.stop)
      systemctl_mock.return_value = SimpleNamespace(
          returncode=0,
          stdout="LoadState=loaded\nActiveState=failed\n",
      )
      dataset.require_process_gone(
          dataset.load_owned_process_identity(benchexec_identity),
          descriptor["systemd_unit"],
      )
      systemctl_mock.return_value = SimpleNamespace(
          returncode=0,
          stdout="LoadState=not-found\nActiveState=inactive\n",
      )
      stopped = root / "monitor.stopped"
      stopped.write_text(
          f"pid={owned.pid}\nexit=0\nsamples=1\n", encoding="utf-8"
      )
      before = root / "before.json"
      after = root / "after.json"
      counters = {
          "package_throttle_count": "1",
          "package_throttle_total_time_ms": "2",
          "pswpin_pages": "3",
          "pswpout_pages": "4",
      }
      before.write_text(json.dumps({
          "hostname": "athena", "measurement_counters": counters
      }), encoding="utf-8")
      after.write_text(json.dumps({
          "hostname": "athena", "measurement_counters": counters
      }), encoding="utf-8")
      check = root / "check.json"
      check.write_text(json.dumps({
          "hostname": "athena",
          "accepted": True,
          "stable": True,
          "counter_deltas": {
              "package_throttle_count": 0,
              "package_throttle_total_time_ms": 0,
              "pswpin_pages": 0,
              "pswpout_pages": 0,
          },
          "warnings": [],
      }), encoding="utf-8")
      marker = root / "provenance/attempts/repetition-1.json"
      args = SimpleNamespace(
          output_root=str(root),
          manifest=str(manifest_path),
          sv_benchmarks=str(root),
          host="athena",
          mode="cap16",
          label="repetition-1",
          role="primary",
          repetition=1,
          benchexec_exit=130,
          definition=str(definition_dir / "hard-case-candidates.xml"),
          result=str(result),
          benchexec_log=str(log),
          benchexec_process=str(benchexec_identity),
          process_descriptor=str(process_descriptor),
          load_monitor=str(monitor),
          monitor_pid=str(pid),
          monitor_process=str(process_identity),
          monitor_stopped=str(stopped),
          machine_before=str(before),
          machine_after=str(after),
          machine_check=str(check),
          output=str(marker),
      )
      decoy_definition = root / "decoy-definition.xml"
      decoy_definition.write_text("decoy\n", encoding="utf-8")
      decoy_process_descriptor = root / "decoy-process-descriptor.json"
      write_process_descriptor(
          "repetition-1",
          decoy_process_descriptor,
          definition=decoy_definition,
      )
      args.process_descriptor = str(decoy_process_descriptor)
      with self.assertRaisesRegex(
          RuntimeError, "descriptor does not match attempt evidence"
      ):
        dataset.command_formal_attempt_complete(args)
      args.process_descriptor = str(process_descriptor)
      stopped.rename(root / "monitor.stopped.missing")
      with self.assertRaisesRegex(RuntimeError, "monitor stopped"):
        dataset.command_formal_attempt_complete(args)
      (root / "monitor.stopped.missing").rename(stopped)
      dataset.command_formal_attempt_complete(args)
      dataset.command_formal_attempt_complete(args)
      validation = SimpleNamespace(
          output_root=str(root),
          manifest=str(manifest_path),
          sv_benchmarks=str(root),
          host="athena",
          mode="cap16",
          label="repetition-1",
          role="primary",
          repetition=1,
          definition=str(
              definition_dir / "hard-case-candidates.xml"
          ),
          result=str(result),
          marker=str(marker),
      )
      dataset.command_validate_formal_attempt(validation)
      normal_marker = marker.read_bytes()
      normal_process_identity = process_identity.read_bytes()
      normal_benchexec_identity = benchexec_identity.read_bytes()
      for name, identity_path in (
          ("monitor_process", process_identity),
          ("benchexec_process", benchexec_identity),
      ):
        legacy_identity = json.loads(identity_path.read_text(encoding="utf-8"))
        legacy_identity["schema_version"] = (
            dataset.LEGACY_FORMAL_PROCESS_IDENTITY_SCHEMA
        )
        del legacy_identity["boot_id"]
        identity_path.write_text(
            json.dumps(legacy_identity), encoding="utf-8"
        )
      legacy_marker = json.loads(normal_marker)
      legacy_marker["schema_version"] = dataset.LEGACY_FORMAL_ATTEMPT_SCHEMA
      for name, identity_path in (
          ("monitor_process", process_identity),
          ("benchexec_process", benchexec_identity),
      ):
        legacy_marker["files"][name]["sha256"] = (
            dataset.baseline.sha256_file(identity_path)
        )
      marker.write_text(
          json.dumps(legacy_marker, indent=2) + "\n", encoding="utf-8"
      )
      dataset.command_formal_attempt_complete(args)
      self.assertEqual(
          json.loads(marker.read_text(encoding="utf-8"))["schema_version"],
          dataset.LEGACY_FORMAL_ATTEMPT_SCHEMA,
      )
      self.assertEqual(
          dataset.validate_formal_attempt_marker(
              marker, root, manifest_path, root, "athena", "cap16"
          )["schema_version"],
          dataset.LEGACY_FORMAL_ATTEMPT_SCHEMA,
      )
      process_identity.write_bytes(normal_process_identity)
      benchexec_identity.write_bytes(normal_benchexec_identity)
      marker.write_bytes(normal_marker)
      with self.assertRaisesRegex(RuntimeError, "exact frozen v2"):
        dataset.command_recover_formal_attempt(args)
      normal_result = result.read_bytes()
      normal_before = before.read_bytes()
      normal_monitor = monitor.read_bytes()
      marker.unlink()
      result_root = ET.parse(result).getroot()
      result_root.set("error", "incomplete")
      result_root.attrib.pop("endtime")
      incomplete_run = result_root.findall("run")[-1]
      for column in list(incomplete_run):
        incomplete_run.remove(column)
      ET.ElementTree(result_root).write(result, encoding="unicode")
      log.write_text(
          "\n".join(
              [
                  *(
                      line
                      for row in fixture.rows[:-1]
                      for line in (
                          f"00:00:01   starting   {row['task']}",
                          f"00:00:02              {row['task']}   TIMEOUT 900 1",
                      )
                  ),
                  f"00:00:03   starting   {fixture.rows[-1]['task']}",
                  (
                      f"00:00:04              {fixture.rows[-1]['task']}   "
                      "TIMEOUT 900 1"
                  ),
              ]
          )
          + "\n",
          encoding="utf-8",
      )
      stopped.unlink()
      after.unlink()
      check.unlink()
      monitor.write_bytes(monitor.read_bytes() + (b"\0" * 16))
      for identity_path in (process_identity, benchexec_identity):
        legacy_identity = json.loads(identity_path.read_text(encoding="utf-8"))
        legacy_identity["schema_version"] = (
            dataset.LEGACY_FORMAL_PROCESS_IDENTITY_SCHEMA
        )
        legacy_identity["proc_starttime"] = 10**12
        del legacy_identity["boot_id"]
        identity_path.write_text(
            json.dumps(legacy_identity), encoding="utf-8"
        )
      legacy_trust = mock.patch.object(
          dataset,
          "trusted_legacy_process_identity",
          side_effect=lambda _root, _label, path: (
              dataset.baseline.sha256_file(path)
          ),
      )
      uptime = mock.patch.object(
          dataset, "current_uptime_ticks", side_effect=[1]
      )
      legacy_trust.start()
      uptime_mock = uptime.start()
      self.addCleanup(legacy_trust.stop)
      self.addCleanup(uptime.stop)

      def capture_recovery_machine(machine_args):
        Path(machine_args.output).write_text(
            json.dumps({
                "hostname": "athena",
                "platform": "test",
                "kernel": "test",
                "cpu_model": "test",
                "online_cpus": "0-31",
                "allowed_p_core_cpus": list(dataset.FORMAL_P_CORE_CPUS[::2]),
                "memory_bytes": 1,
                "java_version": "test",
                "measurement_counters": counters,
            }),
            encoding="utf-8",
        )

      before.write_text(
          json.dumps({
              "hostname": "athena",
              "platform": "test",
              "kernel": "test",
              "cpu_model": "test",
              "online_cpus": "0-31",
              "allowed_p_core_cpus": list(dataset.FORMAL_P_CORE_CPUS[::2]),
              "memory_bytes": 1,
              "java_version": "test",
              "measurement_counters": counters,
          }),
          encoding="utf-8",
      )
      historical_stopped = (
          root / "provenance/repetition-1-load-monitor.jsonl.stopped"
      )
      historical_after = (
          root / "provenance/machine-after-repetition-1.json"
      )
      historical_check = (
          root / "provenance/machine-check-repetition-1.json"
      )
      historical_stopped.parent.mkdir(parents=True, exist_ok=True)
      historical_stopped.write_text(
          f"pid={owned.pid}\nexit=unobserved\nsamples=1\n"
          "recovery=authenticated-process-gone\n",
          encoding="utf-8",
      )
      capture_recovery_machine(
          SimpleNamespace(output=str(historical_after))
      )
      historical_binding = dataset.recovery_process_boot_binding({
          "benchexec-launcher": json.loads(
              benchexec_identity.read_text(encoding="utf-8")
          ),
          "load-monitor": json.loads(
              process_identity.read_text(encoding="utf-8")
          ),
      })
      historical_check.write_text(
          json.dumps(
              dataset.recovered_machine_check_record(
                  before, historical_after, historical_binding
              ),
              sort_keys=True,
          )
          + "\n",
          encoding="utf-8",
      )
      args.benchexec_exit = 125
      args.monitor_stopped = str(historical_stopped)
      args.machine_after = str(historical_after)
      args.machine_check = str(historical_check)
      with self.assertRaisesRegex(RuntimeError, "log and complete"):
        dataset.command_formal_attempt_complete(args)
      log.write_text(
          "\n".join(
              [
                  *(
                      line
                      for row in fixture.rows[:-1]
                      for line in (
                          f"00:00:01   starting   {row['task']}",
                          f"00:00:02              {row['task']}   "
                          "TIMEOUT 900 1",
                      )
                  ),
                  f"00:00:03   starting   {fixture.rows[-1]['task']}",
              ]
          )
          + "\n",
          encoding="utf-8",
      )
      dataset.command_formal_attempt_complete(args)
      dataset.command_validate_formal_attempt(validation)
      marker.unlink()
      arbitrary_directory = root / "arbitrary-recovered-evidence"
      arbitrary_directory.mkdir()
      arbitrary_paths = {
          "monitor_stopped": arbitrary_directory / "monitor-stopped",
          "machine_after": arbitrary_directory / "machine-after.json",
          "machine_check": arbitrary_directory / "machine-check.json",
      }
      for name, source in (
          ("monitor_stopped", historical_stopped),
          ("machine_after", historical_after),
          ("machine_check", historical_check),
      ):
        arbitrary_paths[name].write_bytes(source.read_bytes())
        setattr(args, name, str(arbitrary_paths[name]))
      with self.assertRaisesRegex(RuntimeError, "namespace identity"):
        dataset.command_formal_attempt_complete(args)
      args.benchexec_exit = 130
      for path in (
          historical_stopped,
          historical_after,
          historical_check,
          *arbitrary_paths.values(),
      ):
        path.unlink()
      arbitrary_directory.rmdir()
      uptime_mock.reset_mock()
      uptime_mock.side_effect = [1]
      fixed_stopped = stopped
      fixed_after = after
      fixed_check = check
      recovery_directory = (
          root
          / "provenance/recoveries/repetition-1"
          / recovery_head
      )
      stopped = recovery_directory / "monitor-stopped"
      after = recovery_directory / "machine-after.json"
      check = recovery_directory / "machine-check.json"
      args.research_provenance = str(recovery_provenance)
      args.monitor_stopped = str(stopped)
      args.machine_after = str(after)
      args.machine_check = str(check)
      original_machine_after = args.machine_after
      args.machine_after = str(fixed_after)
      with self.assertRaisesRegex(RuntimeError, "versioned path"):
        dataset.command_recover_formal_attempt(args)
      args.machine_after = original_machine_after
      prepared_directory = recovery_directory.with_name(
          f".{recovery_head}.preparing"
      )
      with mock.patch.object(
          dataset.baseline,
          "command_machine",
          side_effect=RuntimeError("capture crash"),
      ), self.assertRaisesRegex(RuntimeError, "capture crash"):
        dataset.command_recover_formal_attempt(args)
      self.assertFalse(recovery_directory.exists())
      self.assertEqual(
          {path.name for path in prepared_directory.iterdir()},
          {"monitor-stopped"},
      )
      self.assertFalse(marker.exists())
      real_rename = dataset.os.rename

      def crash_before_publish(source, target):
        if Path(source) == prepared_directory:
          raise RuntimeError("publish crash")
        return real_rename(source, target)

      with mock.patch.object(
          dataset.baseline, "command_machine", side_effect=capture_recovery_machine
      ) as preparation_capture, mock.patch.object(
          dataset.os, "rename", side_effect=crash_before_publish
      ), self.assertRaisesRegex(RuntimeError, "publish crash"):
        dataset.command_recover_formal_attempt(args)
      self.assertFalse(recovery_directory.exists())
      self.assertEqual(
          {path.name for path in prepared_directory.iterdir()},
          {"monitor-stopped", "machine-after.json", "machine-check.json"},
      )
      self.assertFalse(marker.exists())
      self.assertEqual(uptime_mock.call_count, 1)
      self.assertEqual(preparation_capture.call_count, 1)
      with mock.patch.object(
          dataset.baseline, "command_machine", side_effect=capture_recovery_machine
      ) as machine_capture:
        dataset.command_recover_formal_attempt(args)
        evidence = {
            path: path.read_bytes() for path in (stopped, after, check)
        }
        dataset.command_recover_formal_attempt(args)
      self.assertEqual(uptime_mock.call_count, 1)
      self.assertEqual(machine_capture.call_count, 0)
      self.assertFalse(prepared_directory.exists())
      self.assertEqual(
          evidence,
          {path: path.read_bytes() for path in (stopped, after, check)},
      )
      recovered = json.loads(marker.read_text(encoding="utf-8"))
      self.assertEqual(recovered["benchexec_exit"], 125)
      self.assertTrue(recovered["result_incomplete"])
      self.assertEqual(
          recovered["files"]["machine_check"]["path"],
          check.relative_to(root).as_posix(),
      )
      dataset.command_validate_formal_attempt(validation)
      post_marker_extra = recovery_directory / "post-marker-extra"
      post_marker_extra.write_text("forged\n", encoding="utf-8")
      with self.assertRaisesRegex(RuntimeError, "topology"):
        dataset.command_validate_formal_attempt(validation)
      post_marker_extra.unlink()
      missing_head = "d" * 40
      missing_head_directory = recovery_directory.with_name(missing_head)
      shutil.copytree(recovery_directory, missing_head_directory)
      missing_head_paths = dataset.formal_recovery_evidence_paths(
          root, "repetition-1", missing_head
      )
      missing_head_args = SimpleNamespace(
          **{
              **vars(args),
              "benchexec_exit": 125,
              **{
                  name: str(path)
                  for name, path in missing_head_paths.items()
              },
          }
      )
      with self.assertRaisesRegex(RuntimeError, "provenance is missing"):
        dataset.formal_attempt_record(missing_head_args)
      shutil.rmtree(missing_head_directory)
      self.assertIn(
          "recovery=authenticated-process-gone",
          stopped.read_text(encoding="utf-8"),
      )
      strict_taint = root / "strict-taint.json"
      with self.assertRaisesRegex(RuntimeError, "trailing NUL"):
        dataset.command_formal_taint(SimpleNamespace(
            manifest=str(manifest_path),
            repetition=1,
            result=str(result),
            benchexec_log=str(log),
            load_monitor=str(monitor),
            output=str(strict_taint),
            attempt_marker=None,
            output_root=None,
            sv_benchmarks=None,
            host=None,
            mode=None,
        ))
      authenticated_taint = root / "authenticated-taint.json"
      dataset.command_formal_taint(SimpleNamespace(
          manifest=str(manifest_path),
          repetition=1,
          result=str(result),
          benchexec_log=str(log),
          load_monitor=str(monitor),
          output=str(authenticated_taint),
          attempt_marker=str(marker),
          output_root=str(root),
          sv_benchmarks=str(root),
          host="athena",
          mode="cap16",
      ))
      self.assertEqual(
          [
              entry["task"]
              for entry in json.loads(
                  authenticated_taint.read_text(encoding="utf-8")
              )["tasks"]
          ],
          [fixture.rows[-1]["task"]],
      )
      recovered_stop = stopped.read_bytes()
      stopped.write_text("forged\n", encoding="utf-8")
      with mock.patch.object(
          dataset.baseline, "command_machine", side_effect=capture_recovery_machine
      ), self.assertRaisesRegex(RuntimeError, "recovery evidence"):
        dataset.command_recover_formal_attempt(args)
      stopped.write_bytes(recovered_stop)
      marker.unlink()
      machine_after_bytes = after.read_bytes()
      after.unlink()
      with self.assertRaisesRegex(RuntimeError, "topology"):
        dataset.command_recover_formal_attempt(args)
      after.write_bytes(machine_after_bytes)
      extra = recovery_directory / "extra"
      extra.write_text("forged\n", encoding="utf-8")
      with self.assertRaisesRegex(RuntimeError, "topology"):
        dataset.command_recover_formal_attempt(args)
      extra.unlink()
      inventory = recovery_provenance / "inventory.sha256"
      inventory_bytes = inventory.read_bytes()
      inventory.write_text("forged\n", encoding="utf-8")
      with self.assertRaisesRegex(RuntimeError, "inventory"):
        dataset.command_recover_formal_attempt(args)
      inventory.write_bytes(inventory_bytes)
      mismatched_provenance = (
          root / f"input/recovery-research-{'d' * 40}"
      )
      shutil.copytree(recovery_provenance, mismatched_provenance)
      args.research_provenance = str(mismatched_provenance)
      with self.assertRaisesRegex(RuntimeError, "path does not match"):
        dataset.command_recover_formal_attempt(args)
      args.research_provenance = str(recovery_provenance)
      downstream = root / "repetition-1-plan.json"
      with mock.patch.object(
          dataset,
          "command_formal_attempt_complete",
          side_effect=RuntimeError("marker failure"),
      ), self.assertRaisesRegex(RuntimeError, "marker failure"):
        dataset.command_recover_formal_attempt(args)
      self.assertFalse(marker.exists())
      self.assertFalse(downstream.exists())
      other_head = "c" * 40
      other_provenance = root / f"input/recovery-research-{other_head}"
      shutil.copytree(recovery_provenance, other_provenance)
      (other_provenance / "research-head.txt").write_text(
          f"{other_head}\n", encoding="utf-8"
      )
      other_state = json.loads(
          (other_provenance / "research-state.json").read_text(
              encoding="utf-8"
          )
      )
      other_state["head"] = other_head
      (other_provenance / "research-state.json").write_text(
          json.dumps(other_state, indent=2) + "\n", encoding="utf-8"
      )
      (other_provenance / "inventory.sha256").write_text(
          "".join(
              f"{dataset.baseline.sha256_file(path)}  "
              f"{path.relative_to(other_provenance).as_posix()}\n"
              for path in sorted(other_provenance.rglob("*"))
              if path.is_file() and path.name != "inventory.sha256"
          ),
          encoding="utf-8",
      )
      other_paths = dataset.formal_recovery_evidence_paths(
          root, "repetition-1", other_head
      )
      self.assertNotEqual(
          {path.parent for path in other_paths.values()},
          {recovery_directory},
      )
      args.research_provenance = str(other_provenance)
      args.monitor_stopped = str(other_paths["monitor_stopped"])
      args.machine_after = str(other_paths["machine_after"])
      args.machine_check = str(other_paths["machine_check"])
      uptime_mock.side_effect = [2]
      with mock.patch.object(
          dataset.baseline,
          "command_machine",
          side_effect=capture_recovery_machine,
      ):
        dataset.command_recover_formal_attempt(args)
      self.assertTrue(marker.is_file())
      self.assertEqual(
          evidence,
          {path: path.read_bytes() for path in (stopped, after, check)},
      )
      self.assertTrue(all(path.is_file() for path in other_paths.values()))
      result.write_bytes(normal_result)
      before.write_bytes(normal_before)
      monitor.write_bytes(normal_monitor)
      process_identity.write_bytes(normal_process_identity)
      benchexec_identity.write_bytes(normal_benchexec_identity)
      log.write_text("complete log\n", encoding="utf-8")
      stopped = fixed_stopped
      after = fixed_after
      check = fixed_check
      args.monitor_stopped = str(stopped)
      args.machine_after = str(after)
      args.machine_check = str(check)
      stopped.write_text(
          f"pid={owned.pid}\nexit=0\nsamples=1\n", encoding="utf-8"
      )
      after.write_text(json.dumps({
          "hostname": "athena", "measurement_counters": counters
      }), encoding="utf-8")
      check.write_text(json.dumps({
          "hostname": "athena",
          "accepted": True,
          "stable": True,
          "counter_deltas": {
              "package_throttle_count": 0,
              "package_throttle_total_time_ms": 0,
              "pswpin_pages": 0,
              "pswpout_pages": 0,
          },
          "warnings": [],
      }), encoding="utf-8")
      marker.write_bytes(normal_marker)
      args.label = "repetition-2"
      args.repetition = 2
      args.result = str(second_result)
      args.output = str(
          root / "provenance/attempts/repetition-2.json"
      )
      second_process_descriptor = (
          root / "repetition-2-process-descriptor.json"
      )
      second_descriptor = write_process_descriptor(
          "repetition-2", second_process_descriptor
      )
      second_launcher = {
          **launcher_identity,
          **second_descriptor["identities"]["benchexec-launcher"],
      }
      second_benchexec_identity = root / "benchexec-2.process.json"
      second_benchexec_identity.write_text(
          json.dumps(second_launcher), encoding="utf-8"
      )
      args.benchexec_process = str(second_benchexec_identity)
      args.process_descriptor = str(second_process_descriptor)
      dataset.command_formal_attempt_complete(args)
      args.label = "repetition-1"
      args.repetition = 1
      args.result = str(result)
      args.output = str(marker)
      args.benchexec_process = str(benchexec_identity)
      args.process_descriptor = str(process_descriptor)
      probe_definition = root / "probe-definition"
      manifest_data = json.loads(
          manifest_path.read_text(encoding="utf-8")
      )
      dataset.render_probe(
          manifest_path,
          manifest_data,
          manifest_data["tasks"],
          root,
          root / "c/properties/unreach-call.prp",
          probe_definition,
      )
      probe_result = root / "probe-result.xml"
      write_stock_result(
          probe_result, fixture.rows, "athena", probe=True
      )
      probe_label = "repetition-1-replacement-attempt-1"
      probe_descriptor_path = root / "probe-process-descriptor.json"
      probe_descriptor = write_process_descriptor(
          probe_label,
          probe_descriptor_path,
          definition=probe_definition / "cegar-eligibility.xml",
          mode="cap16-probe",
      )
      probe_monitor_identity = root / "probe-monitor.process.json"
      probe_monitor_identity.write_text(json.dumps({
          **identity,
          **probe_descriptor["identities"]["load-monitor"],
      }), encoding="utf-8")
      probe_benchexec_identity = root / "probe-benchexec.process.json"
      probe_benchexec_identity.write_text(json.dumps({
          **identity,
          "role": "benchexec-launcher",
          **probe_descriptor["identities"]["benchexec-launcher"],
      }), encoding="utf-8")
      recovered_stopped = root / "probe-monitor.stopped"
      recovered_stopped.write_text(
          f"pid={owned.pid}\nexit=unobserved\nsamples=1\n"
          "recovery=authenticated-process-gone\n",
          encoding="utf-8",
      )
      recovered_args = SimpleNamespace(
          **{
              **vars(args),
              "mode": "cap16-probe",
              "label": probe_label,
              "role": "replacement",
              "benchexec_exit": 125,
              "definition": str(
                  probe_definition / "cegar-eligibility.xml"
              ),
              "result": str(probe_result),
              "benchexec_process": str(probe_benchexec_identity),
              "process_descriptor": str(probe_descriptor_path),
              "monitor_process": str(probe_monitor_identity),
              "monitor_stopped": str(recovered_stopped),
              "output": str(
                  root / f"provenance/attempts/{probe_label}.json"
              ),
          }
      )
      dataset.command_formal_attempt_complete(recovered_args)
      self.assertEqual(
          json.loads(
              Path(recovered_args.output).read_text(encoding="utf-8")
          )["benchexec_exit"],
          125,
      )
      Path(recovered_args.output).unlink()
      forged = json.loads(marker.read_text(encoding="utf-8"))
      forged["host"] = "valkyrie"
      marker.write_text(json.dumps(forged), encoding="utf-8")
      with self.assertRaisesRegex(RuntimeError, "identity"):
        dataset.validate_formal_attempt_marker(
            marker, root, manifest_path, root, "athena", "cap16"
        )
      forged["host"] = "athena"
      marker.write_text(
          json.dumps(forged, indent=2) + "\n", encoding="utf-8"
      )
      live = subprocess.Popen(["sleep", "10"])
      live_identity = root / "live-process.json"
      live_identity.write_text(
          json.dumps(dataset.read_process_identity(live.pid, "load-monitor")),
          encoding="utf-8",
      )
      try:
        with self.assertRaisesRegex(RuntimeError, "still alive"):
          dataset.require_process_gone(
              dataset.load_owned_process_identity(live_identity)
          )
      finally:
        live.terminate()
        live.wait()
      different_unit_identity = root / "different-unit.process.json"
      different_unit = (
          "vguide-cap16-repetition-1-deaddeaddead.scope"
      )
      different_unit_identity.write_text(
          json.dumps({
              **launcher_identity,
              "systemd_unit": different_unit,
          }),
          encoding="utf-8",
      )

      def systemd_state(command, **_):
        unit = command[3]
        if unit == descriptor["systemd_unit"]:
          return SimpleNamespace(
              returncode=0,
              stdout=(
                  "LoadState=loaded\n"
                  "ActiveState=active\nMainPID=999\n"
              ),
          )
        self.assertEqual(unit, different_unit)
        return SimpleNamespace(
            returncode=0,
            stdout=(
                "LoadState=not-found\n"
                "ActiveState=inactive\nMainPID=0\n"
            ),
        )

      systemctl_mock.side_effect = systemd_state
      with self.assertRaisesRegex(RuntimeError, "unit is still active"):
        dataset.command_require_formal_process_gone(
            SimpleNamespace(
                descriptor=str(process_descriptor),
                identity=str(different_unit_identity),
                output_root=str(root),
                mode="cap16",
                label="repetition-1",
                host="athena",
                role="benchexec-launcher",
            )
        )
      self.assertIn(
          descriptor["systemd_unit"],
          systemctl_mock.call_args.args[0],
      )
      systemctl_mock.side_effect = None
      systemctl_mock.return_value = SimpleNamespace(
          returncode=0,
          stdout=(
              "LoadState=not-found\nActiveState=inactive\nMainPID=0\n"
          ),
      )
      summary = root / "summary"
      summary.mkdir()
      for name in (
          "classification.csv",
          "hard-portfolio.csv",
          "mixed.csv",
          "row-provenance.json",
          "summary.json",
          "verifier-failure-quarantine.csv",
          "wrong-quarantine.csv",
      ):
        (summary / name).write_text("{}\n", encoding="utf-8")
      for relative in (
          "input/research/inventory.sha256",
          "provenance/build.log",
          "provenance/cgroup-check.log",
          "provenance/machine-preflight-start.json",
          "provenance/machine-preflight-end.json",
          "provenance/machine-preflight-check.json",
          "provenance/research-verification-final.log",
          "provenance/runtime-verification-final.log",
          "provenance/runtime-closure.txt",
      ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("evidence\n", encoding="utf-8")
      plans = []
      for repetition in (1, 2):
        plan = root / f"repetition-{repetition}-plan.json"
        plan_result = result if repetition == 1 else second_result
        plan.write_text(json.dumps({
            "schema_version": (
                dataset.CAP16_FORMAL_REPETITION_PLAN_SCHEMA
            ),
            "repetition": repetition,
            "primary": {
                "path": plan_result.relative_to(root).as_posix(),
                "sha256": dataset.baseline.sha256_file(plan_result),
            },
            "taint": None,
            "replacements": [],
        }), encoding="utf-8")
        plans.append(str(plan))
      artifact = root / "provenance/artifact-manifest.json"
      closure = SimpleNamespace(
          output_root=str(root),
          manifest=str(manifest_path),
          benchmark_definition=str(
              definition_dir / "hard-case-candidates.xml"
          ),
          sv_benchmarks=str(root),
          host="athena",
          mode="cap16",
          repetition_plan=plans,
          require_complete=False,
      )
      with self.assertRaises(FileNotFoundError):
        dataset.command_validate_formal_closure(closure)
      partial = summary / "wrong-quarantine.csv"
      partial.unlink()
      with self.assertRaisesRegex(RuntimeError, "summary topology"):
        dataset.command_validate_formal_closure(closure)
      partial.write_text("{}\n", encoding="utf-8")
      dataset.baseline.write_artifact_manifest(root, artifact)
      dataset.command_validate_formal_closure(closure)
      sentinel = summary / ".complete"
      closure.require_complete = True
      sentinel.symlink_to(summary / "summary.json")
      with self.assertRaisesRegex(RuntimeError, "sentinel"):
        dataset.command_validate_formal_closure(closure)
      sentinel.unlink()
      sentinel.write_text("comp", encoding="utf-8")
      with self.assertRaisesRegex(RuntimeError, "sentinel"):
        dataset.command_validate_formal_closure(closure)
      sentinel.unlink()
      dataset.command_write_complete_sentinel(
          SimpleNamespace(output=str(sentinel))
      )
      dataset.command_validate_formal_closure(closure)
      stopped.write_text(
          f"pid={owned.pid}\nexit=0\nsamples=0\n", encoding="utf-8"
      )
      with self.assertRaisesRegex(RuntimeError, "monitor stop"):
        dataset.command_formal_attempt_complete(args)
      stopped.write_text(
          f"pid={owned.pid}\nexit=0\nsamples=1\n", encoding="utf-8"
      )
      check.write_text("{}\n", encoding="utf-8")
      with self.assertRaisesRegex(RuntimeError, "machine check"):
        dataset.command_formal_attempt_complete(args)

  def test_cap16_formal_runner_reuses_recovery_on_athena(self):
    wrapper_path = Path(__file__).with_name(
        "run-stock-cap16-formal-dataset.sh"
    )
    wrapper = wrapper_path.read_text(encoding="utf-8")
    runner = Path(__file__).with_name(
        "run-stock-formal-dataset.sh"
    ).read_text(encoding="utf-8")

    self.assertIn('main cap16 "$@"', wrapper)
    self.assertIn('source "$SCRIPT_DIR/run-stock-formal-dataset.sh"', wrapper)
    self.assertIn("CAP16_PHASE_A_OUTPUT", runner)
    self.assertIn("FORMAL_HOST=athena", runner)
    self.assertIn("EXPECTED_PYTHON_REAL=/usr/bin/python3.12", runner)
    self.assertIn("validate-cap16-phase-a", runner)
    self.assertIn("render-cap16-formal", runner)
    self.assertIn("render-cap16-formal-replacement", runner)
    self.assertIn("summarize-cap16-formal", runner)
    self.assertIn("-N 2 -c 4", runner)
    self.assertIn("formal-taint", runner)
    self.assertIn("cap16-repetition-plan", runner)
    self.assertIn('CAP16_PHASE_A_OUTPUT="$OUTPUT_DIR/input/evidence"', runner)
    self.assertIn('if [[ -f "$plan" ]]', runner)
    self.assertIn('if [[ -f "$marker" ]]', runner)
    self.assertIn('benchexec_status" -ne 130', runner)
    self.assertIn("RESUMING=true", runner)
    self.assertIn('current_result=$replacement', runner)
    self.assertIn('current_taint=$replacement_taint', runner)
    self.assertIn("FORMAL_BENCHMARK_SCOPE=-cap16", runner)
    self.assertIn("formal-attempt-complete", runner)
    self.assertIn("validate-formal-attempt", runner)
    self.assertIn("local -a attempt_descriptor=", runner)
    self.assertEqual(runner.count("--monitor-stopped"), 2)
    self.assertIn("local -a recovery_attempt_descriptor=", runner)
    self.assertIn(
        'provenance/recoveries/$label/$recovery_research_head', runner
    )
    self.assertIn(
        '--research-provenance "$ACTIVE_RESEARCH_PROVENANCE"', runner
    )
    self.assertIn("summary.staging", runner)
    self.assertIn("validate-formal-closure", runner)
    self.assertNotIn("missing-atomic-attempt-completion", runner)
    self.assertIn("recover-formal-attempt", runner)
    self.assertIn("restore-legacy-cap16-athena-attempt", runner)
    self.assertIn("formal-owned-process-identity-v2", runner)
    self.assertIn(
        "PYTHON_RUNTIME_FLAGS=(-I -S -B -X pycache_prefix=/dev/null)",
        runner,
    )
    self.assertIn("assert_no_sourceless_python_bytecode", runner)
    self.assertNotIn('"$PYTHON_BIN" -I', runner)
    self.assertNotIn('"$PYTHON_BIN" -c', runner)
    self.assertNotIn("sys.dont_write_bytecode = True", runner)
    self.assertNotIn('sys.pycache_prefix = "/dev/null"', runner)
    shell_module_command = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; printf %s "$BENCHEXEC_MODULE_COMMAND"',
            "bash",
            str(Path(__file__).with_name("run-stock-formal-dataset.sh")),
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    self.assertEqual(shell_module_command, dataset.BENCHEXEC_MODULE_COMMAND)
    self.assertIn("input/recovery-research", runner)
    self.assertIn("verify_frozen_research_provenance", runner)
    self.assertNotIn("require-formal-process-gone", runner)
    self.assertNotIn('"$DATASET_PY" require-process-gone', runner)
    self.assertNotIn("pgrep", runner)
    self.assertIn('--unit="$unit"', runner)
    self.assertIn("invalid completion sentinel; refusing", runner)
    self.assertIn(
        '"hard-case-dataset-v2${FORMAL_BENCHMARK_SCOPE}-formal-$FORMAL_HOST-repetition-1"',
        runner,
    )
    self.assertIn(
        '"hard-case-dataset-v2${FORMAL_BENCHMARK_SCOPE}-formal-$FORMAL_HOST-repetition-2"',
        runner,
    )
    result = subprocess.run(
        [str(wrapper_path)],
        text=True,
        capture_output=True,
        check=False,
    )
    self.assertEqual(result.returncode, 2)
    self.assertIn("CAP16_PHASE_A_PACKAGE", result.stderr)

  def test_cap16_runner_is_athena_only_and_uses_case_recovery_plan(self):
    runner = Path(__file__).with_name(
        "run-stock-cap16-dataset.sh"
    ).read_text(encoding="utf-8")

    self.assertIn('[[ "$HOST" == athena ]]', runner)
    self.assertIn(
        "EXPECTED_MANIFEST="
        "16e5f9ff04ed08ef9c29d8674021c11de3eed87b9da6a8c1e2ef68c6847ec0bb",
        runner,
    )
    self.assertIn("-N 2 -c 4", runner)
    self.assertIn("screen-taint", runner)
    self.assertIn("render-screen-replacement", runner)
    self.assertIn("screen-summary-plan", runner)
    self.assertIn(
        "printf 'complete\\n' >\"$COMPLETE_CHECK/.complete\"", runner
    )
    self.assertNotIn('touch "$COMPLETE_CHECK/.complete"', runner)
    self.assertIn('source "$SCRIPT_DIR/run-stock-formal-dataset.sh"', runner)
    self.assertNotIn('"$PYTHON_BIN" -I', runner)
    self.assertNotIn('"$PYTHON_BIN" -c', runner)
    self.assertNotIn("sys.dont_write_bytecode = True", runner)
    self.assertNotIn('sys.pycache_prefix = "/dev/null"', runner)
    self.assertIn("assert_no_sourceless_python_bytecode", runner)
    package_start = runner.index("CAP16_PACKAGE_SCRIPT_FILES=(")
    package_end = runner.index("\n)", package_start)
    self.assertEqual(
        [
            line.strip()
            for line in runner[package_start:package_end].splitlines()[1:]
        ],
        [
            "baseline.py",
            "dataset.py",
            "run-stock-formal-dataset.sh",
            "run-stock-cap16-dataset.sh",
        ],
    )
    for assignment in (
        "EXPECTED_PYTHON_REAL=/usr/bin/python3.12",
        "EXPECTED_PYTHON_SHA256="
        "1643dacd9feaedc58f3cc581e4d22577dfe25c09b10282936186ccf0f2e61118",
        'EXPECTED_PYTHON_VERSION="Python 3.12.3"',
        "EXPECTED_PYTHON_STDLIB=/usr/lib/python3.12",
        "EXPECTED_PYTHON_STDLIB_DIGEST="
        "a0c9c33e4f5b6c4e8e921598ec1c7273341cf2e8f2c74d7a348d6a3584a2c325",
        "EXPECTED_PYTHON_DIST_PACKAGES=/usr/lib/python3/dist-packages",
        "EXPECTED_PYYAML_PACKAGE_DIGEST="
        "9148a8dc1759caac2f87132749a8f29de2cf8ee71b6ddead932d027613045627",
        "EXPECTED_PYTHON_LOCAL_DIST_PACKAGES="
        "/usr/local/lib/python3.12/dist-packages",
        "EXPECTED_PYTHON_LOCAL_DIST_PACKAGES_DIGEST="
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "EXPECTED_PYTHON_SYSTEM_PATH="
        "/usr/lib/python312.zip:/usr/lib/python3.12:"
        "/usr/lib/python3.12/lib-dynload",
        "EXPECTED_PYYAML_FILE=/usr/lib/python3/dist-packages/yaml/__init__.py",
        "EXPECTED_PYYAML_VERSION=6.0.1",
        "EXPECTED_ANT_INSTALL="
        "52772e241e78a875fa00dea891eac2023d4f2be639a5f28a17dca81580f75e5b",
        'EXPECTED_ANT_VERSION="Apache Ant(TM) version 1.10.12 '
        'compiled on January 17 1970"',
        "EXPECTED_CPACHECKER_JAR_CONTENT="
        "49f95adc5255b89b1bb3edea81ab5f2f660364d36ffa69c3b12508d1e1943be3",
    ):
      self.assertIn(assignment, runner)
    for path in ("yaml", "_yaml", "PyYAML-6.0.1.dist-info"):
      self.assertIn(path, runner)
    self.assertGreaterEqual(runner.count("verify_runtime_closure"), 4)
    self.assertIn("jar_content_digest_value", runner)
    self.assertIn("EXPECTED_CPACHECKER_JAR_CONTENT=", runner)
    self.assertNotIn("CURRENT_JAR_SHA256", runner)
    self.assertIn("abandoned-incomplete-metadata", runner)
    self.assertNotIn("cthulhu", runner.lower())
    self.assertNotIn("output directory must be absent or empty", runner)
    self.assertLess(
        runner.rindex("--output \"$ARTIFACT_CANDIDATE\""),
        runner.rindex('write_atomic complete "$OUTPUT_DIR/summary/.complete"'),
    )

    copy_start = runner.index("copy_manifest_package() {")
    copy_end = runner.index("\nSAVED_INPUT=", copy_start)
    copy_function = runner[copy_start:copy_end]
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      source = root / "source"
      destination = root / "destination"
      property_file = source / "corpus/properties/unreach-call.prp"
      property_file.parent.mkdir(parents=True)
      property_file.write_text("CHECK( init(main()), LTL(G ! call(__VERIFIER_error())) )\n")
      manifest = {
          "task_count": 0,
          "corpus_files": [
              {
                  "path": "corpus/properties/unreach-call.prp",
                  "sha256": hashlib.sha256(property_file.read_bytes()).hexdigest(),
              }
          ],
          "tasks": [],
      }
      manifest_path = source / "candidate-manifest-athena.json"
      manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
      destination.mkdir()
      subprocess.run(
          [
              "bash",
              "-c",
              copy_function
              + '\nsource "$4"\nSCRIPT_DIR=$1\n'
              + 'copy_manifest_package "$2" "$3"\n',
              "bash",
              str(Path(__file__).parent),
              str(manifest_path),
              str(destination),
              str(Path(__file__).with_name("run-stock-formal-dataset.sh")),
          ],
          check=True,
      )
      dataset.command_validate(
          SimpleNamespace(
              manifest=str(destination / "candidate-manifest-athena.json"),
              sv_benchmarks=str(root),
          )
      )

    start = runner.index("promote_plan() {")
    end = runner.index("\nrun_screen() {", start)
    promotion_functions = runner[start:end]
    with tempfile.TemporaryDirectory() as temp:
      subprocess.run(
          [
              "bash",
              "-c",
              promotion_functions
              + r'''
set -euo pipefail
PYTHON_BIN=python3
root=$1
printf '{' >"$root/partial-plan.json"
printf '{}\n' >"$root/candidate-plan.json"
promote_plan "$root/candidate-plan.json" "$root/partial-plan.json" \
  "$root/preserved-partial-plan.json"
test "$(cat "$root/partial-plan.json")" = '{}'
test "$(cat "$root/preserved-partial-plan.json")" = '{'
printf '{}\n' >"$root/authenticated-plan.json"
printf '{"different": true}\n' >"$root/conflicting-plan.json"
if promote_plan "$root/conflicting-plan.json" \
  "$root/authenticated-plan.json" "$root/unexpected-plan-evidence.json"; then
  exit 1
fi
test -f "$root/conflicting-plan.json"
test "$(cat "$root/authenticated-plan.json")" = '{}'
printf '{' >"$root/partial-taint.json"
printf '{}\n' >"$root/candidate-taint.json"
promote_plan "$root/candidate-taint.json" "$root/partial-taint.json" \
  "$root/preserved-partial-taint.json"
test "$(cat "$root/partial-taint.json")" = '{}'
test "$(cat "$root/preserved-partial-taint.json")" = '{'
: >"$root/partial-result.path"
printf '/tmp/result.xml\n' >"$root/candidate-result.path"
promote_path_record "$root/candidate-result.path" "$root/partial-result.path" \
  "$root/preserved-partial-result.path"
test "$(cat "$root/partial-result.path")" = '/tmp/result.xml'
test ! -s "$root/preserved-partial-result.path"
printf '/tmp/res' >"$root/truncated-result.path"
printf '/tmp/result.xml\n' >"$root/second-candidate-result.path"
promote_path_record "$root/second-candidate-result.path" \
  "$root/truncated-result.path" "$root/preserved-truncated-result.path"
test "$(cat "$root/truncated-result.path")" = '/tmp/result.xml'
test "$(cat "$root/preserved-truncated-result.path")" = '/tmp/res'
printf '/tmp/first.xml\n' >"$root/authenticated-result.path"
printf '/tmp/second.xml\n' >"$root/conflicting-result.path"
if promote_path_record "$root/conflicting-result.path" \
  "$root/authenticated-result.path" "$root/unexpected-result-evidence.path"; then
  exit 1
fi
test -f "$root/conflicting-result.path"
test "$(cat "$root/authenticated-result.path")" = '/tmp/first.xml'
mkdir "$root/partial-summary" "$root/candidate-summary"
printf old >"$root/partial-summary/old"
printf new >"$root/candidate-summary/new"
promote_summary "$root/candidate-summary" "$root/partial-summary" \
  "$root/preserved-partial-summary"
test ! -e "$root/partial-summary/.complete"
test "$(cat "$root/partial-summary/new")" = new
test "$(cat "$root/preserved-partial-summary/old")" = old
write_atomic complete "$root/partial-summary/.complete"
cp -a "$root/partial-summary" "$root/identical-summary"
promote_summary "$root/identical-summary" "$root/partial-summary" \
  "$root/unexpected-partial-summary"
test ! -e "$root/identical-summary"
test ! -e "$root/unexpected-partial-summary"
cp -a "$root/partial-summary" "$root/conflicting-summary"
printf changed >"$root/conflicting-summary/new"
if promote_summary "$root/conflicting-summary" "$root/partial-summary" \
  "$root/unexpected-conflicting-summary"; then
  exit 1
fi
test -d "$root/conflicting-summary"
test "$(cat "$root/partial-summary/new")" = new
''',
              "bash",
              temp,
          ],
          check=True,
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

  def test_probe_telemetry_requires_exact_empty_provider_events(self):
    events = [
        {
            "schema_version": "vguide-telemetry-v1",
            "refinement": 1,
            "counterexample_visits_loop_head": True,
            "provider_calls": [
                {
                    "agent_role": role,
                    "model": "deterministic-empty-provider",
                    "response_sha256":
                        "950ec9013b84aed3afe9761427511822630e80cd5f009e837389312830deba94",
                }
                for role in ("invariant", "counterexample", "refinement")
            ],
            "activated_candidates": [],
            "rejected_candidates": 0,
        }
    ]

    self.assertEqual(
        dataset.validate_probe_events(events), "cegar_eligible"
    )
    for mutate in (
        lambda event: event.update(extra=True),
        lambda event: event["provider_calls"].append(
            event["provider_calls"][0]
        ),
        lambda event: event["activated_candidates"].append(
            {"predicate": "x"}
        ),
        lambda event: event.update(rejected_candidates=1),
        lambda event: event.update(rejected_candidates=False),
        lambda event: event.update(refinement=True),
        lambda event: event.update(refinement=1.0),
        lambda event: event["provider_calls"][0].update(model="remote"),
    ):
      changed = json.loads(json.dumps(events))
      mutate(changed[0])
      with self.assertRaises(RuntimeError):
        dataset.validate_probe_events(changed)

  def test_probe_telemetry_requires_sequential_refinements(self):
    event = {
        "schema_version": "vguide-telemetry-v1",
        "refinement": 2,
        "counterexample_visits_loop_head": False,
        "provider_calls": [
            {
                "agent_role": role,
                "model": "deterministic-empty-provider",
                "response_sha256":
                    "950ec9013b84aed3afe9761427511822630e80cd5f009e837389312830deba94",
            }
            for role in ("invariant", "counterexample", "refinement")
        ],
        "activated_candidates": [],
        "rejected_candidates": 0,
    }

    with self.assertRaises(RuntimeError):
      dataset.validate_probe_events([event])

  def test_probe_telemetry_mapping_rejects_ambiguous_and_unknown_tasks(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      result = root / "run.results.cegar-eligibility.official.xml"
      xml = ET.Element("result")
      for name in ("a/same.yml", "b/same.yml"):
        ET.SubElement(xml, "run", {"name": name})
      ET.ElementTree(xml).write(result, encoding="unicode")
      manifest = {
          name: {"task_path": name}
          for name in ("a/same.yml", "b/same.yml")
      }
      with self.assertRaisesRegex(RuntimeError, "ambiguous"):
        dataset.probe_result_telemetry(result, manifest)

      xml.remove(xml.findall("run")[1])
      ET.ElementTree(xml).write(result, encoding="unicode")
      manifest = {"a/same.yml": {"task_path": "a/same.yml"}}
      misplaced = root / "vguide-telemetry.json"
      misplaced.write_text("[]\n", encoding="utf-8")
      with self.assertRaisesRegex(RuntimeError, "misplaced telemetry"):
        dataset.probe_result_telemetry(result, manifest)
      misplaced.unlink()
      self.assertEqual(
          dataset.probe_result_telemetry(result, manifest),
          {"a/same.yml": None},
      )
      files = root / "run.files/cegar-eligibility"
      unknown = files / "unknown.yml/output/vguide-telemetry.json"
      unknown.parent.mkdir(parents=True)
      unknown.write_text("[]\n", encoding="utf-8")
      with self.assertRaisesRegex(RuntimeError, "unknown telemetry"):
        dataset.probe_result_telemetry(result, manifest)

  def test_probe_summary_accepts_no_files_for_explicit_verifier_failure(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      manifest_path = root / "manifest.json"
      manifest_data = {
          "task_count": 1,
          "tasks": [{
              "task": "a.yml",
              "task_path": "a.yml",
              "expected_verdict": "true",
              "benchmark_set": "Loops",
          }],
      }
      manifest_path.write_text(
          json.dumps(manifest_data), encoding="utf-8"
      )
      result = root / "run.results.cegar-eligibility.official.xml"
      xml = ET.Element("result")
      ET.SubElement(xml, "run", {"name": "a.yml"})
      ET.ElementTree(xml).write(result, encoding="unicode")
      plan = {
          "row_sources": [{
              "task": "a.yml",
              "result_path": result.name,
              "result_sha256": dataset.baseline.sha256_file(result),
              "source": "primary",
          }],
          "rows": {
              "a.yml": {
                  "task": "a.yml",
                  "classification": "verifier_or_resource_error",
                  "status": "ERROR",
                  "category": "error",
              }
          },
      }
      with (
          mock.patch.object(
              dataset,
              "validate_cap16_probe_input",
              return_value=(
                  root,
                  manifest_path,
                  manifest_data,
                  [{"task": "a.yml"}],
                  {},
              ),
          ),
          mock.patch.object(dataset, "validate_probe_definition"),
          mock.patch.object(dataset, "load_screen_plan", return_value=plan),
          mock.patch.object(
              dataset, "declared_plan_file", return_value=result
          ),
      ):
        rows, _, _ = dataset.cap16_probe_summary_rows(
            SimpleNamespace(
                probe_input=str(root),
                sv_benchmarks=str(root),
                benchmark_definition=str(root / "probe.xml"),
                probe_plan=str(root / "plan.json"),
            )
        )

      self.assertEqual(
          rows[0]["probe_classification"], "infrastructure_failure"
      )
      telemetry = (
          root
          / "run.files/cegar-eligibility/a.yml/output/vguide-telemetry.json"
      )
      telemetry.parent.mkdir(parents=True)
      telemetry.write_text("[]\n", encoding="utf-8")
      with (
          mock.patch.object(
              dataset,
              "validate_cap16_probe_input",
              return_value=(
                  root,
                  manifest_path,
                  manifest_data,
                  [{"task": "a.yml"}],
                  {},
              ),
          ),
          mock.patch.object(dataset, "validate_probe_definition"),
          mock.patch.object(dataset, "load_screen_plan", return_value=plan),
          mock.patch.object(
              dataset, "declared_plan_file", return_value=result
          ),
      ):
        rows, _, _ = dataset.cap16_probe_summary_rows(
            SimpleNamespace(
                probe_input=str(root),
                sv_benchmarks=str(root),
                benchmark_definition=str(root / "probe.xml"),
                probe_plan=str(root / "plan.json"),
            )
        )
      self.assertEqual(
          rows[0]["probe_classification"], "infrastructure_failure"
      )
      plan["rows"]["a.yml"].update(
          classification="timeout",
          status="TIMEOUT",
          category="error",
      )
      with (
          mock.patch.object(
              dataset,
              "validate_cap16_probe_input",
              return_value=(
                  root,
                  manifest_path,
                  manifest_data,
                  [{"task": "a.yml"}],
                  {},
              ),
          ),
          mock.patch.object(dataset, "validate_probe_definition"),
          mock.patch.object(dataset, "load_screen_plan", return_value=plan),
          mock.patch.object(
              dataset, "declared_plan_file", return_value=result
          ),
      ):
        rows, _, _ = dataset.cap16_probe_summary_rows(
            SimpleNamespace(
                probe_input=str(root),
                sv_benchmarks=str(root),
                benchmark_definition=str(root / "probe.xml"),
                probe_plan=str(root / "plan.json"),
            )
        )
      self.assertEqual(rows[0]["probe_classification"], "no_event")

  def test_cap16_probe_input_authenticates_saved_formal_backlink(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      fixture = phase_b_fixture(root)
      source_manifest = json.loads(
          Path(fixture.parent_manifest).read_text(encoding="utf-8")
      )
      source_manifest.pop("corpus_files")
      formal = root / "formal"
      paths = dataset.cap16_formal_probe_paths(formal)
      paths["manifest"].parent.mkdir(parents=True)
      paths["summary"].parent.mkdir(parents=True)
      paths["artifact"].parent.mkdir(parents=True)
      paths["manifest"].write_text(
          json.dumps(source_manifest, indent=2) + "\n", encoding="utf-8"
      )
      classification = [
          {
              "task": "t0.yml",
              "classification": "stable_hard_solved",
          },
          {
              "task": "t1.yml",
              "classification": "stable_analysis_unsolved",
          },
          {"task": "t2.yml", "classification": "correct_fast"},
      ]
      for path, rows in (
          (paths["classification"], classification),
          (paths["hard"], classification[:2]),
      ):
        with path.open("w", newline="", encoding="utf-8") as target:
          writer = csv.DictWriter(
              target, fieldnames=("task", "classification")
          )
          writer.writeheader()
          writer.writerows(rows)
      paths["summary"].write_text("{}\n", encoding="utf-8")
      dataset.baseline.write_artifact_manifest(formal, paths["artifact"])

      probe = root / "probe"
      probe.mkdir()
      source_manifest_sha256 = dataset.baseline.sha256_file(
          paths["manifest"]
      )
      hard_sha256 = dataset.baseline.sha256_file(paths["hard"])
      artifact = json.loads(
          paths["artifact"].read_text(encoding="utf-8")
      )
      derived = dataset.manifest_subset(
          source_manifest,
          ["t0.yml", "t1.yml"],
          {
              "operation": "cap16_zero_candidate_probe_input",
              "source_manifest_sha256": source_manifest_sha256,
              "source_formal_manifest_sha256": source_manifest_sha256,
              "source_formal_hard_portfolio_sha256": hard_sha256,
              "source_formal_artifact_aggregate_sha256": artifact[
                  "aggregate_sha256"
              ],
              "selection_independent_of_augmented_outcomes": True,
          },
      )
      manifest_path = probe / "candidate-manifest-cap16-probe.json"
      manifest_path.write_text(
          json.dumps(derived, indent=2) + "\n", encoding="utf-8"
      )
      shutil.copyfile(paths["hard"], probe / "hard-portfolio.csv")
      for source, target in (
          (paths["manifest"], "source-formal-manifest.json"),
          (paths["classification"], "source-formal-classification.csv"),
          (paths["summary"], "source-formal-summary.json"),
          (paths["artifact"], "source-formal-artifact-manifest.json"),
      ):
        shutil.copyfile(source, probe / target)
      identity = {
          "schema_version": dataset.CAP16_PROBE_INPUT_SCHEMA,
          "host": "athena",
          "task_count": 2,
          "formal_artifact_aggregate_sha256": artifact[
              "aggregate_sha256"
          ],
          "formal_artifact_manifest_sha256": dataset.baseline.sha256_file(
              paths["artifact"]
          ),
          "formal_manifest_sha256": source_manifest_sha256,
          "formal_hard_portfolio_sha256": hard_sha256,
          "formal_classification_sha256": dataset.baseline.sha256_file(
              paths["classification"]
          ),
          "formal_summary_sha256": dataset.baseline.sha256_file(
              paths["summary"]
          ),
          "probe_manifest_sha256": dataset.baseline.sha256_file(
              manifest_path
          ),
          "selection_independent_of_augmented_outcomes": True,
      }
      identity_path = probe / "identity.json"

      def write_identity():
        identity_path.write_text(
            json.dumps(identity, indent=2) + "\n", encoding="utf-8"
        )

      write_identity()
      with mock.patch.object(
          dataset,
          "FROZEN_CAP16_PHASE_A_SURVIVOR_SHA256",
          source_manifest_sha256,
      ):
        with self.assertRaisesRegex(RuntimeError, "pin is pending"):
          dataset.validate_cap16_probe_input(probe, root)
      with mock.patch.multiple(
          dataset,
          FROZEN_CAP16_PHASE_A_SURVIVOR_SHA256=source_manifest_sha256,
          FROZEN_CAP16_FORMAL_ARTIFACT_AGGREGATE_SHA256=artifact[
              "aggregate_sha256"
          ],
      ):
        dataset.validate_cap16_probe_input(probe, root)
        identity["formal_manifest_sha256"] = "NOT-A-HASH"
        write_identity()
        with self.assertRaisesRegex(RuntimeError, "identity"):
          dataset.validate_cap16_probe_input(probe, root)

        identity["formal_manifest_sha256"] = source_manifest_sha256
        derived["derivation"]["source_formal_manifest_sha256"] = "b" * 64
        manifest_path.write_text(
            json.dumps(derived, indent=2) + "\n", encoding="utf-8"
        )
        identity["probe_manifest_sha256"] = dataset.baseline.sha256_file(
            manifest_path
        )
        write_identity()
        with self.assertRaisesRegex(RuntimeError, "hard portfolio"):
          dataset.validate_cap16_probe_input(probe, root)

        derived["derivation"][
            "source_formal_manifest_sha256"
        ] = source_manifest_sha256
        derived["tasks"][0]["family"] = "forged-family"
        manifest_path.write_text(
            json.dumps(derived, indent=2) + "\n", encoding="utf-8"
        )
        identity["probe_manifest_sha256"] = dataset.baseline.sha256_file(
            manifest_path
        )
        write_identity()
        with self.assertRaisesRegex(RuntimeError, "hard portfolio"):
          dataset.validate_cap16_probe_input(probe, root)

        forged_classification = [
            {
                "task": "t0.yml",
                "classification": "stable_hard_solved",
            },
            {"task": "t1.yml", "classification": "correct_fast"},
            {
                "task": "t2.yml",
                "classification": "stable_analysis_unsolved",
            },
        ]
        forged_hard = [
            forged_classification[0], forged_classification[2]
        ]
        copied_classification = (
            probe / "source-formal-classification.csv"
        )
        copied_hard = probe / "hard-portfolio.csv"
        for path, rows in (
            (copied_classification, forged_classification),
            (copied_hard, forged_hard),
        ):
          with path.open("w", newline="", encoding="utf-8") as target:
            writer = csv.DictWriter(
                target, fieldnames=("task", "classification")
            )
            writer.writeheader()
            writer.writerows(rows)
        forged_hard_sha256 = dataset.baseline.sha256_file(copied_hard)
        forged_classification_sha256 = dataset.baseline.sha256_file(
            copied_classification
        )
        manifest_path.write_text(
            json.dumps(derived, indent=2) + "\n", encoding="utf-8"
        )
        copied_artifact = probe / "source-formal-artifact-manifest.json"
        forged_artifact = json.loads(
            copied_artifact.read_text(encoding="utf-8")
        )
        classification_relative = paths["classification"].relative_to(
            formal
        ).as_posix()
        hard_relative = paths["hard"].relative_to(formal).as_posix()
        for entry in forged_artifact["files"]:
          if entry["path"] == classification_relative:
            entry["sha256"] = forged_classification_sha256
            entry["size_bytes"] = copied_classification.stat().st_size
          elif entry["path"] == hard_relative:
            entry["sha256"] = forged_hard_sha256
            entry["size_bytes"] = copied_hard.stat().st_size
        aggregate = hashlib.sha256()
        for entry in forged_artifact["files"]:
          aggregate.update(entry["path"].encode("utf-8"))
          aggregate.update(b"\0")
          aggregate.update(bytes.fromhex(entry["sha256"]))
        forged_artifact["aggregate_sha256"] = aggregate.hexdigest()
        copied_artifact.write_text(
            json.dumps(forged_artifact, indent=2) + "\n",
            encoding="utf-8",
        )
        identity["formal_artifact_aggregate_sha256"] = aggregate.hexdigest()
        identity[
            "formal_hard_portfolio_sha256"
        ] = forged_hard_sha256
        identity[
            "formal_classification_sha256"
        ] = forged_classification_sha256
        identity[
            "formal_artifact_manifest_sha256"
        ] = dataset.baseline.sha256_file(copied_artifact)
        forged_derived = dataset.manifest_subset(
            source_manifest,
            ["t0.yml", "t2.yml"],
            {
                "operation": "cap16_zero_candidate_probe_input",
                "source_manifest_sha256": source_manifest_sha256,
                "source_formal_manifest_sha256": source_manifest_sha256,
                "source_formal_hard_portfolio_sha256":
                    forged_hard_sha256,
                "source_formal_artifact_aggregate_sha256":
                    aggregate.hexdigest(),
                "selection_independent_of_augmented_outcomes": True,
            },
        )
        manifest_path.write_text(
            json.dumps(forged_derived, indent=2) + "\n",
            encoding="utf-8",
        )
        identity["task_count"] = 2
        identity["probe_manifest_sha256"] = dataset.baseline.sha256_file(
            manifest_path
        )
        write_identity()
        with self.assertRaisesRegex(RuntimeError, "backlink"):
          dataset.validate_cap16_probe_input(probe, root)

  def test_strict_probe_runner_has_fixed_thin_wrappers(self):
    cap8_wrapper = Path(__file__).with_name(
        "run-cap8-cegar-probe.sh"
    ).read_text(encoding="utf-8")
    cap16_wrapper = Path(__file__).with_name(
        "run-cap16-cegar-probe.sh"
    ).read_text(encoding="utf-8")
    runner = Path(__file__).with_name(
        "run-strict-cegar-probe.sh"
    ).read_text(encoding="utf-8")
    self.assertIn('run-strict-cegar-probe.sh" cap8 "$@"', cap8_wrapper)
    self.assertIn('run-strict-cegar-probe.sh" cap16 "$@"', cap16_wrapper)
    self.assertLess(len(cap8_wrapper.splitlines()), 20)
    self.assertLess(len(cap16_wrapper.splitlines()), 20)
    self.assertNotIn("HARD_PORTFOLIO_CSV", runner)
    self.assertIn('"$AUTH_FORMAL_COMMAND"', runner)
    self.assertIn(
        'diff -r -- "$EXPECTED_INPUT" "$OUTPUT_DIR/input/formal"', runner
    )
    self.assertIn("require-formal-process-gone", runner)
    self.assertIn("recovery=authenticated-process-gone", runner)
    self.assertIn('--benchexec-exit "$recovery_exit"', runner)
    self.assertIn(
        "PYTHON_RUNTIME_FLAGS=(-I -S -B -X pycache_prefix=/dev/null)",
        Path(__file__).with_name("run-stock-formal-dataset.sh")
        .read_text(encoding="utf-8"),
    )
    self.assertNotIn('"$PYTHON_BIN" -I', runner)
    self.assertNotIn("sys.dont_write_bytecode", runner)
    self.assertNotIn("sys.pycache_prefix", runner)
    self.assertIn("assert_no_sourceless_python_bytecode", runner)
    self.assertIn("authenticate_scope_cgroup", runner)
    self.assertIn("wait_for_benchmark_with_monitor", runner)
    self.assertIn("reap_benchmark_launcher", runner)
    self.assertIn("EXPECTED_PYYAML_PACKAGE_DIGEST=", runner)
    self.assertIn(
        "ProcessLookupError",
        Path(__file__).with_name("dataset.py").read_text(encoding="utf-8"),
    )
    self.assertIn("authenticate_probe_taint", runner)
    self.assertNotIn('if [[ ! -f "$primary_taint" ]]', runner)
    self.assertNotIn("ABANDONED", runner)
    self.assertEqual(runner.count("set +e"), 2)
    recovery = runner.index("local recovery_exit=125")
    recovered_marker = runner.index(
        '--benchexec-exit "$recovery_exit"', recovery
    )
    recovered_return = runner.index("\n    return\n", recovered_marker)
    new_descriptor = runner.index(
        "write-formal-process-descriptor", recovered_return
    )
    self.assertLess(recovery, recovered_marker)
    self.assertLess(recovered_marker, recovered_return)
    self.assertLess(recovered_return, new_descriptor)
    self.assertIn('-L "$OUTPUT_DIR/summary/.complete"', runner)
    self.assertIn('--mode "$FORMAL_MODE"', runner)
    self.assertIn("-N 8 -c 1", runner)
    self.assertIn("EXPECTED_PYTHON_REAL=/usr/bin/python3.10", runner)
    self.assertIn('P_CORE_LOCK="/var/tmp/vguide-$FORMAL_HOST-pcores.lock"', runner)
    auth = runner.index('"$AUTH_FORMAL_COMMAND"')
    self.assertLess(auth, runner.index("RESUMING=false"))
    self.assertLess(auth, runner.index("-Divy.disable=true clean jar"))
    self.assertIn(
        "EXPECTED_STOCK_LIB_JAVA="
        "eea0df062de5c8e3febe0d96b583741c140e79d3ae41a87a56d7be365b876f9d",
        runner,
    )
    self.assertIn(
        "EXPECTED_CPACHECKER_JAR_CONTENT="
        "34953059634f4a708ef0fc9f9bd288d6d4f0172c980b95033fd8d75229535a69",
        runner,
    )
    self.assertNotIn(
        'EXPECTED_STOCK_LIB_JAVA=$(directory_digest_value', runner
    )
    self.assertIn('after_tmp=$(mktemp "$after.tmp.XXXXXX")', runner)
    self.assertIn('mv -- "$after_tmp" "$after"', runner)
    self.assertIn('check_tmp=$(mktemp "$check.tmp.XXXXXX")', runner)
    self.assertIn('mv -- "$check_tmp" "$check"', runner)
    self.assertIn("vguide.provider=EMPTY", Path(__file__).with_name(
        "dataset.py"
    ).read_text(encoding="utf-8"))

  def test_cap8_probe_pending_pin_fails_before_output_creation(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      output = root / "probe-input"
      args = SimpleNamespace(
          formal_output=str(root / "formal"),
          sv_benchmarks=str(root / "sv-benchmarks"),
          output_dir=str(output),
      )
      with self.assertRaisesRegex(RuntimeError, "pin is pending"):
        dataset.command_package_cap8_probe_input(args)
      self.assertFalse(output.exists())

  def test_cap8_r8_summary_reproduction_uses_saved_three_phase_evidence(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      paths = dataset.cap8_formal_probe_paths(root)
      paths["evidence"].mkdir(parents=True)
      for role in ("original", "reroute", "recovery"):
        (paths["evidence"] / f"{role}-result.xml.bz2").write_bytes(b"x")
      arguments = dataset.cap8_summary_reproduction_arguments(
          paths, root / "sv-benchmarks", root / "reproduced"
      )
      self.assertEqual(arguments[0], "summarize")
      self.assertEqual(arguments.count("--phase-a-manifest"), 3)
      self.assertEqual(arguments.count("--phase-a-result"), 3)
      self.assertEqual(arguments.count("--survivor-manifest"), 3)
      self.assertIn(str(paths["manifest"]), arguments)
      self.assertIn(str(paths["plan_1"]), arguments)
      self.assertIn(str(paths["plan_2"]), arguments)
      self.assertEqual(arguments[-2:], ["--hard-threshold", "200"])

  def test_cap8_r8_adapter_authenticates_full_legacy_closure(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      fixture = phase_b_fixture(root)
      formal = root / "formal"
      paths = dataset.cap8_formal_probe_paths(formal)
      paths["manifest"].parent.mkdir(parents=True)
      manifest = json.loads(
          Path(fixture.parent_manifest).read_text(encoding="utf-8")
      )
      paths["manifest"].write_text(
          json.dumps(manifest), encoding="utf-8"
      )
      shutil.copytree(
          root / "corpus", paths["manifest"].parent / "corpus"
      )
      package = dataset.write_phase_b_artifact_manifest(
          paths["manifest"].parent
      )[0]

      paths["evidence"].mkdir(parents=True)
      shutil.copyfile(
          fixture.parent_manifest,
          paths["evidence"] / "parent-manifest.json",
      )
      (paths["evidence"] / "corpus/properties").mkdir(parents=True)
      shutil.copyfile(
          root / "corpus/properties/unreach-call.prp",
          paths["evidence"] / "corpus/properties/unreach-call.prp",
      )
      for role in ("original", "reroute", "recovery"):
        for kind in ("manifest", "survivor"):
          (paths["evidence"] / f"{role}-{kind}.json").write_text(
              "{}\n", encoding="utf-8"
          )
        (paths["evidence"] / f"{role}-result.xml.bz2").write_bytes(b"x")

      paths["research"].mkdir(parents=True)
      research_files = (
          "research-diff.patch",
          "research-head.txt",
          "research-index-flags.txt",
          "research-state.json",
          "research-status.porcelain",
          "scripts/baseline.py",
          "scripts/dataset.py",
          "scripts/run-stock-formal-dataset.sh",
      )
      for relative in research_files:
        path = paths["research"] / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            (
                dataset.FROZEN_CAP8_RESEARCH_HEAD + "\n"
                if relative == "research-head.txt"
                else f"{relative}\n"
            ),
            encoding="utf-8",
        )

      def write_inventory(directory):
        files = sorted(
            path for path in directory.rglob("*")
            if path.is_file() and path.name != "inventory.sha256"
        )
        (directory / "inventory.sha256").write_text(
            "".join(
                f"{dataset.baseline.sha256_file(path)}  "
                f"{path.relative_to(directory).as_posix()}\n"
                for path in files
            ),
            encoding="utf-8",
        )

      write_inventory(paths["evidence"])
      write_inventory(paths["research"])

      paths["definition"].parent.mkdir(parents=True)
      paths["definition"].write_text("<benchmark/>\n", encoding="utf-8")
      paths["plan_1"].write_text("{}\n", encoding="utf-8")
      paths["plan_2"].write_text('{"repetition": 2}\n', encoding="utf-8")
      paths["summary"].parent.mkdir(parents=True)
      classification = [
          {
              "task": row["task"],
              "classification": (
                  "stable_hard_solved"
                  if index == 0
                  else "stable_unsolved"
                  if index == 1
                  else "mixed"
              ),
          }
          for index, row in enumerate(manifest["tasks"])
      ]
      for path, rows in (
          (paths["classification"], classification),
          (paths["hard"], classification[:2]),
      ):
        with path.open("w", newline="", encoding="utf-8") as target:
          writer = csv.DictWriter(
              target, fieldnames=("task", "classification")
          )
          writer.writeheader()
          writer.writerows(rows)
      for name in (
          "mixed.csv",
          "row-provenance.json",
          "summary.json",
          "verifier-failure-quarantine.csv",
          "wrong-quarantine.csv",
      ):
        (paths["summary"].parent / name).write_text(
            f"{name}\n", encoding="utf-8"
        )
      for relative in (
          "provenance/build.log",
          "provenance/cgroup-check.log",
          "provenance/machine-preflight-start.json",
          "provenance/machine-preflight-end.json",
          "provenance/machine-preflight-check.json",
          "provenance/research-verification-final.log",
          "provenance/runtime-verification-final.log",
          "provenance/runtime-closure.txt",
      ):
        path = formal / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("evidence\n", encoding="utf-8")
      runtime = {"runtime": "fixture"}
      (formal / "provenance/runtime-closure.txt").write_text(
          "runtime=fixture\n", encoding="utf-8"
      )
      dataset.baseline.write_artifact_manifest(
          formal, paths["artifact"]
      )
      artifact = json.loads(paths["artifact"].read_text(encoding="utf-8"))

      def reproduce(_, arguments, python_bin=None):
        self.assertEqual(python_bin, "/usr/bin/python3.10")
        output = Path(arguments[arguments.index("--output-dir") + 1])
        for source in paths["summary"].parent.iterdir():
          shutil.copyfile(source, output / source.name)

      with (
          mock.patch.object(dataset, "run_saved_dataset", reproduce),
          mock.patch.multiple(
              dataset,
              FROZEN_CAP8_FORMAL_ARTIFACT_AGGREGATE_SHA256=artifact[
                  "aggregate_sha256"
              ],
              FROZEN_CAP8_FORMAL_PACKAGE_MANIFEST_SHA256=(
                  dataset.baseline.sha256_file(
                      paths["formal_package_artifact"]
                  )
              ),
              FROZEN_CAP8_FORMAL_PACKAGE_AGGREGATE_SHA256=package[
                  "aggregate_sha256"
              ],
              FROZEN_FORMAL_MANIFEST_SHA256=dataset.baseline.sha256_file(
                  paths["manifest"]
              ),
              FROZEN_CAP8_FORMAL_TASK_COUNT=manifest["task_count"],
              FROZEN_CAP8_RESEARCH_INVENTORY_SHA256=(
                  dataset.baseline.sha256_file(
                      paths["research_inventory"]
                  )
              ),
              FROZEN_CAP8_RUNTIME_CLOSURE=runtime,
          ),
      ):
        _, _, hard, closure = dataset.authenticate_cap8_formal_for_probe(
            formal, root
        )
      self.assertEqual(len(hard), 2)
      self.assertEqual(
          closure["artifact_aggregate_sha256"],
          artifact["aggregate_sha256"],
      )

  def test_cap16_probe_summary_writes_all_four_strata(self):
    with tempfile.TemporaryDirectory() as temp:
      self.assertEqual(
          dataset.CAP16_PROBE_STRATA,
          (
              ("cegar-eligible.csv", "cegar_eligible"),
              ("no-event.csv", "no_event"),
              (
                  "hook-reached-without-loop-head.csv",
                  "hook_reached_without_loop_head",
              ),
              ("infrastructure-failure.csv", "infrastructure_failure"),
          ),
      )
      rows = [
          {
              "task": f"task-{index}",
              "probe_classification": classification,
          }
          for index, classification in enumerate((
              "cegar_eligible",
              "no_event",
              "hook_reached_without_loop_head",
              "infrastructure_failure",
          ))
      ]
      plan = {
          "plan_sha256": "a" * 64,
          "primary_sha256": "b" * 64,
          "replacement_sha256": [],
          "row_sources": [],
      }
      identity = {
          "formal_artifact_aggregate_sha256": "c" * 64,
          "probe_manifest_sha256": "d" * 64,
      }
      with mock.patch.object(
          dataset,
          "cap16_probe_summary_rows",
          return_value=(rows, plan, identity),
      ):
        summary = dataset.write_cap16_probe_summary(
            SimpleNamespace(output_dir=temp)
        )
      self.assertEqual(
          summary["classifications"],
          {
              "cegar_eligible": 1,
              "hook_reached_without_loop_head": 1,
              "infrastructure_failure": 1,
              "no_event": 1,
          },
      )
      for filename in (
          "cegar-eligible.csv",
          "no-event.csv",
          "hook-reached-without-loop-head.csv",
          "infrastructure-failure.csv",
      ):
        with (Path(temp) / filename).open(
            newline="", encoding="utf-8"
        ) as source:
          self.assertEqual(len(list(csv.DictReader(source))), 1)
      self.assertFalse(
          (Path(temp) / "structurally-unreachable.csv").exists()
      )

  def test_probe_uses_one_core_per_single_threaded_predicate_run(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      manifest = root / "manifest.json"
      task = root / "example.yml"
      source = root / "example.c"
      task.write_text("task\n", encoding="utf-8")
      source.write_text("int main(void) {}\n", encoding="utf-8")
      property_file = root / "c/properties/unreach-call.prp"
      property_file.parent.mkdir(parents=True)
      property_file.write_text("CHECK\n", encoding="utf-8")
      manifest.write_text(
          json.dumps(
              {
                  "task_count": 1,
                  "tasks": [
                      {
                          "task": "c/example.yml",
                          "task_path": "example.yml",
                          "task_sha256": dataset.baseline.sha256_file(task),
                          "source": "sv-benchmarks",
                          "source_paths": ["example.c"],
                          "source_sha256": [
                              dataset.baseline.sha256_file(source)
                          ],
                          "expected_verdict": "true",
                          "benchmark_set": "Loops",
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
              property_file=str(property_file),
              output_dir=str(output),
          )
      )

      self.assertEqual(
          ET.parse(output / "cegar-eligibility.xml").getroot().get("cpuCores"), "1"
      )
      benchmark = output / "cegar-eligibility.xml"
      tree = ET.parse(benchmark)
      provider = next(
          option
          for option in tree.getroot().findall("option")
          if option.text == "vguide.provider=EMPTY"
      )
      provider.text = "vguide.provider=REMOTE"
      tree.write(benchmark, encoding="unicode")
      with self.assertRaisesRegex(RuntimeError, "topology is not frozen"):
        dataset.validate_probe_definition(
            benchmark,
            manifest,
            json.loads(manifest.read_text(encoding="utf-8")),
            root,
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
