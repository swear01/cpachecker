#!/usr/bin/env python3

# This file is part of CPAchecker,
# a tool for configurable software verification:
# https://cpachecker.sosy-lab.org
#
# SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>
#
# SPDX-License-Identifier: Apache-2.0

import importlib.util
import json
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
    false_tasks = {
        "c/loop-invgen/id_trans.yml",
        "c/loops/count_up_down-2.yml",
        "c/loops/trex01-1.yml",
        "c/loops/trex03-1.yml",
        "c/nla-digbench-scaling/cohencu-ll_unwindbound10.yml",
    }
    tasks = [
        {
            "task": task,
            "expected_verdict": "false" if task in false_tasks else "true",
        }
        for task in baseline.CALIBRATION_TASKS
    ]
    tasks.append({"task": "c/distractor.yml", "expected_verdict": "true"})
    first = baseline.select_calibration(tasks, 5)
    second = baseline.select_calibration(list(reversed(tasks)), 5)
    self.assertEqual(first, second)
    self.assertEqual({task["task"] for task in first}, set(baseline.CALIBRATION_TASKS))
    self.assertEqual(sum(task["expected_verdict"] == "true" for task in first), 5)
    self.assertEqual(sum(task["expected_verdict"] == "false" for task in first), 5)

  def test_calibration_rejects_missing_pinned_task(self):
    tasks = [
        {"task": task, "expected_verdict": "true"}
        for task in baseline.CALIBRATION_TASKS[:-1]
    ]
    with self.assertRaisesRegex(ValueError, "Pinned calibration tasks are missing"):
      baseline.select_calibration(tasks, 5)

  def test_config_closure_follows_includes_referenced_configs_and_specifications(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      (root / "config/components").mkdir(parents=True)
      (root / "config/specification").mkdir()
      (root / "config/root.properties").write_text(
          """#include include.properties
restartAlgorithm.configFiles = components/first.properties, \\
  components/second.properties
specification = specification/property.spc
""",
          encoding="utf-8",
      )
      (root / "config/include.properties").write_text("value = true\n", encoding="utf-8")
      for name in ("first.properties", "second.properties"):
        (root / "config/components" / name).write_text("value = true\n", encoding="utf-8")
      (root / "config/specification/property.spc").write_text(
          "#include nested.spc\n", encoding="utf-8"
      )
      (root / "config/specification/nested.spc").write_text(
          "CONTROL AUTOMATON Test\n", encoding="utf-8"
      )

      closure = baseline.config_closure(root, "config/root.properties")

      self.assertEqual(
          {path.relative_to(root).as_posix() for path in closure},
          {
              "config/root.properties",
              "config/include.properties",
              "config/components/first.properties",
              "config/components/second.properties",
              "config/specification/property.spc",
              "config/specification/nested.spc",
          },
      )

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
      manifest = Path(temp) / "manifest.json"
      manifest.write_text(
          """{"task_count":1,"tasks":[{"task":"c/test.yml","benchmark_set":"Loops","expected_verdict":"true"}]}""",
          encoding="utf-8",
      )
      args = SimpleNamespace(
          result=str(result),
          task_manifest=str(manifest),
          output_dir=temp,
          hard_threshold=200.0,
      )

      with self.assertRaisesRegex(RuntimeError, "Expected 1 result rows, found 0"):
        baseline.command_summarize(args)

  def test_summary_verifies_manifest_and_emits_distributions(self):
    with tempfile.TemporaryDirectory() as temp:
      result = Path(temp) / "result.xml"
      result.write_text(
          """<result><run name="/bench/c/test.yml">
          <column title="status" value="true"/>
          <column title="category" value="correct"/>
          <column title="cputime" value="201.5s"/>
          <column title="walltime" value="205s"/>
          <column title="memory" value="2MB"/>
          </run></result>""",
          encoding="utf-8",
      )
      manifest = Path(temp) / "manifest.json"
      manifest.write_text(
          """{"task_count":1,"tasks":[{"task":"c/test.yml","benchmark_set":"Loops","expected_verdict":"true"}]}""",
          encoding="utf-8",
      )
      output = Path(temp) / "summary"
      args = SimpleNamespace(
          result=str(result),
          task_manifest=str(manifest),
          output_dir=str(output),
          hard_threshold=200.0,
      )

      baseline.command_summarize(args)

      summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
      self.assertEqual(summary["correct_true"], 1)
      self.assertEqual(summary["hard_over_200s"], 1)
      self.assertEqual(summary["distributions"]["memory_bytes"]["median"], 2_000_000)
      self.assertEqual(summary["by_benchmark_set"]["Loops"]["correct"], 1)

  def test_summary_quarantines_wrong_from_hard_and_unsolved_strata(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      result = root / "result.xml"
      result.write_text(
          """<result>
          <run name="c/hard.yml"><column title="status" value="true"/>
          <column title="category" value="correct"/><column title="cputime" value="201s"/></run>
          <run name="c/unknown.yml"><column title="status" value="TIMEOUT"/>
          <column title="category" value="error"/><column title="cputime" value="901s"/></run>
          <run name="c/wrong.yml"><column title="status" value="false(unreach-call)"/>
          <column title="category" value="wrong"/><column title="cputime" value="301s"/></run>
          </result>""",
          encoding="utf-8",
      )
      manifest = root / "manifest.json"
      manifest.write_text(
          """{"task_count":3,"tasks":[
          {"task":"c/hard.yml","benchmark_set":"Loops","expected_verdict":"true"},
          {"task":"c/unknown.yml","benchmark_set":"Loops","expected_verdict":"true"},
          {"task":"c/wrong.yml","benchmark_set":"Loops","expected_verdict":"true"}]}""",
          encoding="utf-8",
      )
      output = root / "summary"
      args = SimpleNamespace(
          result=str(result),
          task_manifest=str(manifest),
          output_dir=str(output),
          hard_threshold=200.0,
      )

      with self.assertRaisesRegex(RuntimeError, "Result contains 1 wrong verdict"):
        baseline.command_summarize(args)

      with (output / "hard-over-200s.csv").open() as source:
        hard = list(__import__("csv").DictReader(source))
      with (output / "unsolved.csv").open() as source:
        unsolved = list(__import__("csv").DictReader(source))
      self.assertEqual([row["task"] for row in hard], ["c/hard.yml"])
      self.assertEqual([row["task"] for row in unsolved], ["c/unknown.yml"])

  def test_summary_rejects_result_outside_manifest(self):
    with tempfile.TemporaryDirectory() as temp:
      result = Path(temp) / "result.xml"
      result.write_text('<result><run name="c/other.yml"/></result>', encoding="utf-8")
      manifest = Path(temp) / "manifest.json"
      manifest.write_text(
          """{"task_count":1,"tasks":[{"task":"c/test.yml","benchmark_set":"Loops","expected_verdict":"true"}]}""",
          encoding="utf-8",
      )
      args = SimpleNamespace(
          result=str(result),
          task_manifest=str(manifest),
          output_dir=temp,
          hard_threshold=200.0,
      )

      with self.assertRaisesRegex(RuntimeError, "does not match exactly one manifest"):
        baseline.command_summarize(args)

  def test_summary_rejects_expected_verdict_disagreement(self):
    with tempfile.TemporaryDirectory() as temp:
      result = Path(temp) / "result.xml"
      result.write_text(
          '<result><run name="c/test.yml" expectedVerdict="false"/></result>', encoding="utf-8"
      )
      manifest = Path(temp) / "manifest.json"
      manifest.write_text(
          """{"task_count":1,"tasks":[{"task":"c/test.yml","benchmark_set":"Loops","expected_verdict":"true"}]}""",
          encoding="utf-8",
      )
      args = SimpleNamespace(
          result=str(result),
          task_manifest=str(manifest),
          output_dir=temp,
          hard_threshold=200.0,
      )

      with self.assertRaisesRegex(RuntimeError, "expected verdict disagrees"):
        baseline.command_summarize(args)

  def test_artifact_manifest_hashes_files_but_not_itself(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      (root / "data").mkdir()
      (root / "data" / "result.txt").write_text("result\n", encoding="utf-8")
      output = root / "SHA256SUMS.json"
      args = SimpleNamespace(root=str(root), output=str(output))

      baseline.command_artifact_manifest(args)

      manifest = json.loads(output.read_text(encoding="utf-8"))
      self.assertEqual(manifest["file_count"], 1)
      self.assertEqual(manifest["files"][0]["path"], "data/result.txt")

  def test_directory_digest_covers_file_content_and_symlink_target(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      (root / "one").write_text("first\n", encoding="utf-8")
      (root / "link").symlink_to("one")
      first = baseline.directory_digest(root)

      (root / "one").write_text("second\n", encoding="utf-8")
      second = baseline.directory_digest(root)

      self.assertEqual(first["entry_count"], 2)
      self.assertNotEqual(first["sha256"], second["sha256"])

  def test_calibration_summary_quantifies_repeated_noise(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      manifest = root / "manifest.json"
      manifest.write_text(
          """{"task_count":1,"tasks":[{"task":"c/test.yml","benchmark_set":"Loops","expected_verdict":"true"}]}""",
          encoding="utf-8",
      )
      results = []
      for index, cpu_time in enumerate((10.0, 12.0, 11.0), start=1):
        result = root / f"result-{index}.xml"
        result.write_text(
            f"""<result><run name="c/test.yml">
            <column title="status" value="true"/><column title="category" value="correct"/>
            <column title="cputime" value="{cpu_time}s"/>
            <column title="walltime" value="{cpu_time + 1}s"/>
            <column title="memory" value="1B"/></run></result>""",
            encoding="utf-8",
        )
        results.append(str(result))
      output = root / "calibration.json"
      args = SimpleNamespace(
          result=results, task_manifest=str(manifest), output=str(output)
      )

      baseline.command_calibration_summary(args)

      summary = json.loads(output.read_text(encoding="utf-8"))
      self.assertEqual(summary["repetitions"], 3)
      self.assertAlmostEqual(summary["tasks"][0]["cpu_relative_mad"], 1 / 11)

  def test_render_validation_requires_and_hashes_each_correct_witness(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      manifest = root / "manifest.json"
      manifest.write_text(
          """{"task_count":2,"tasks":[
          {"task":"c/true.yml","benchmark_set":"Loops","expected_verdict":"true"},
          {"task":"c/false.yml","benchmark_set":"Loops","expected_verdict":"false"}]}""",
          encoding="utf-8",
      )
      result = root / "result.xml"
      result.write_text(
          """<result>
          <run name="c/true.yml"><column title="status" value="true"/>
          <column title="category" value="correct"/></run>
          <run name="c/false.yml"><column title="status" value="false(unreach-call)"/>
          <column title="category" value="correct"/></run></result>""",
          encoding="utf-8",
      )
      result_files = root / "result.files" / "stock"
      for task in ("true.yml", "false.yml"):
        witness_dir = result_files / task / "output"
        witness_dir.mkdir(parents=True)
        (witness_dir / "witness.yml").write_text("entry_type: invariant_set\n", encoding="utf-8")
      sv_benchmarks = root / "sv-benchmarks"
      (sv_benchmarks / "c/properties").mkdir(parents=True)
      (sv_benchmarks / "c/properties/unreach-call.prp").write_text(
          "CHECK( init(main()), LTL(G ! call(__VERIFIER_error())) )\n", encoding="utf-8"
      )
      for task in ("true.yml", "false.yml"):
        (sv_benchmarks / "c" / task).write_text("format_version: '2.0'\n", encoding="utf-8")
      validator_dir = root / "bench-defs/benchmark-defs"
      validator_dir.mkdir(parents=True)
      for kind in ("correctness", "violation"):
        (validator_dir / f"cpachecker-validate-{kind}-witnesses-v2.xml").write_text(
            """<benchmark tool="cpachecker" timelimit="5 min" cpuCores="2">
            <resultfiles>**/witness.*</resultfiles>
            <option name="--%s-witness-validation"/>
            <option name="--benchmark"/></benchmark>""" % kind,
            encoding="utf-8",
        )
      generated = root / "generated"
      output = root / "validation.json"
      args = SimpleNamespace(
          result=str(result),
          task_manifest=str(manifest),
          result_files=str(result_files.parent),
          sv_benchmarks=str(sv_benchmarks),
          bench_defs=str(root / "bench-defs"),
          output_dir=str(generated),
          output=str(output),
      )

      baseline.command_render_validation(args)

      validation = json.loads(output.read_text(encoding="utf-8"))
      self.assertEqual(validation["correct_result_count"], 2)
      self.assertEqual(len(validation["witnesses"]), 2)
      xml = (generated / "baseline-v1-correctness-witness-validation.xml").read_text(
          encoding="utf-8"
      )
      self.assertIn("${taskdef_name}/output/witness.yml", xml)
      self.assertIn("--correctness-witness-validation", xml)

  def test_validation_summary_requires_every_validator_result_to_be_correct(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      inputs = {}
      for kind, verdict in (("correctness", "true"), ("violation", "false")):
        manifest = root / f"{kind}.manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "task_count": 1,
                    "tasks": [
                        {
                            "task": f"c/{kind}.yml",
                            "benchmark_set": "Loops",
                            "expected_verdict": verdict,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        result = root / f"{kind}.xml"
        result.write_text(
            f"""<result><run name="c/{kind}.yml">
            <column title="status" value="{verdict}"/>
            <column title="category" value="correct"/>
            <column title="cputime" value="1s"/>
            <column title="walltime" value="2s"/>
            <column title="memory" value="3B"/></run></result>""",
            encoding="utf-8",
        )
        inputs[kind] = (result, manifest)
      output = root / "summary.json"
      args = SimpleNamespace(
          correctness_result=str(inputs["correctness"][0]),
          correctness_manifest=str(inputs["correctness"][1]),
          violation_result=str(inputs["violation"][0]),
          violation_manifest=str(inputs["violation"][1]),
          output=str(output),
      )

      baseline.command_validation_summary(args)

      summary = json.loads(output.read_text(encoding="utf-8"))
      self.assertEqual(summary["validated_total"], 2)
      self.assertEqual(summary["failed_total"], 0)


if __name__ == "__main__":
  unittest.main()
