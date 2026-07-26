#!/usr/bin/env python3

# This file is part of CPAchecker,
# a tool for configurable software verification:
# https://cpachecker.sosy-lab.org
#
# SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>
#
# SPDX-License-Identifier: Apache-2.0

import csv
import importlib.util
import json
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
        {"category": "error", "cpu_time_seconds": 900.0},
        {"category": "error", "cpu_time_seconds": 900.0},
    ]
    self.assertEqual(dataset.classify_repetitions(hard, 200), "stable_hard_solved")
    self.assertEqual(dataset.classify_repetitions(unsolved, 200), "stable_unsolved")
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
