#!/usr/bin/env python3

# This file is part of CPAchecker,
# a tool for configurable software verification:
# https://cpachecker.sosy-lab.org
#
# SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>
#
# SPDX-License-Identifier: Apache-2.0

import importlib.util
from types import SimpleNamespace
import tempfile
import unittest
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("baseline", Path(__file__).with_name("baseline.py"))
baseline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(baseline)


class BaselineTest(unittest.TestCase):

  def test_task_metadata_extracts_unreach_call(self):
    with tempfile.TemporaryDirectory() as temp:
      task = Path(temp) / "task.yml"
      task.write_text(
          """format_version: '2.0'
input_files: 'input.c'
properties:
  - property_file: ../properties/unreach-call.prp
    expected_verdict: false
options:
  language: C
  data_model: ILP32
""",
          encoding="utf-8",
      )
      self.assertEqual(
          baseline.task_metadata(task),
          {"expected_verdict": "false", "input_files": ["input.c"], "data_model": "ILP32"},
      )

  def test_calibration_is_balanced_and_stable(self):
    tasks = [
        {"task": f"c/{verdict}-{index}.yml", "expected_verdict": verdict}
        for verdict in ("true", "false")
        for index in range(10)
    ]
    first = baseline.select_calibration(tasks, 3)
    second = baseline.select_calibration(list(reversed(tasks)), 3)
    self.assertEqual(first, second)
    self.assertEqual(sum(task["expected_verdict"] == "true" for task in first), 3)
    self.assertEqual(sum(task["expected_verdict"] == "false" for task in first), 3)

  def test_result_classification_keeps_infrastructure_separate(self):
    self.assertEqual(baseline.classify_result("true", "correct"), "correct_true")
    self.assertEqual(baseline.classify_result("TIMEOUT", "error"), "timeout")
    self.assertEqual(
        baseline.classify_result("", "missing"), "infrastructure_or_manifest_failure"
    )

  def test_summary_rejects_incomplete_result(self):
    with tempfile.TemporaryDirectory() as temp:
      result = Path(temp) / "result.xml"
      result.write_text("<result></result>", encoding="utf-8")
      args = SimpleNamespace(
          result=str(result), output_dir=temp, hard_threshold=200.0, expected_count=1
      )

      with self.assertRaisesRegex(RuntimeError, "Expected 1 result rows, found 0"):
        baseline.command_summarize(args)


if __name__ == "__main__":
  unittest.main()
