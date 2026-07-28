#!/usr/bin/env python3

# This file is part of CPAchecker,
# a tool for configurable software verification:
# https://cpachecker.sosy-lab.org
#
# SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>
#
# SPDX-License-Identifier: Apache-2.0

import importlib.util
import io
import json
import os
import socket
import zipfile
from contextlib import redirect_stdout
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
        baseline.classify_result("OUT OF JAVA MEMORY", "error"), "out_of_memory"
    )
    self.assertEqual(
        baseline.classify_result("", "missing"), "infrastructure_or_manifest_failure"
    )

  def test_machine_check_reports_throttling_or_swap_activity(self):
    with tempfile.TemporaryDirectory() as temp:
      before = Path(temp) / "before.json"
      after = Path(temp) / "after.json"
      counters = {
          "package_throttle_count": "10",
          "package_throttle_total_time_ms": "20",
          "pswpin_pages": "30",
          "pswpout_pages": "40",
      }
      before.write_text(
          json.dumps({"hostname": "host", "measurement_counters": counters}),
          encoding="utf-8",
      )
      after.write_text(
          json.dumps({"hostname": "host", "measurement_counters": counters}),
          encoding="utf-8",
      )
      output = io.StringIO()
      with redirect_stdout(output):
        baseline.command_machine_check(SimpleNamespace(before=before, after=after))
      self.assertTrue(json.loads(output.getvalue())["stable"])
      after.write_text(
          json.dumps(
              {
                  "hostname": "host",
                  "measurement_counters": {
                      **counters,
                      "package_throttle_count": "11",
                  },
              }
          ),
          encoding="utf-8",
      )
      output = io.StringIO()
      with redirect_stdout(output):
        baseline.command_machine_check(SimpleNamespace(before=before, after=after))
      result = json.loads(output.getvalue())
      self.assertTrue(result["accepted"])
      self.assertFalse(result["stable"])
      self.assertEqual(result["counter_deltas"]["package_throttle_count"], 1)
      self.assertTrue(result["warnings"])

      for mutation, message in (
          ({"hostname": "other"}, "different hosts"),
          (
              {
                  "measurement_counters": {
                      **counters,
                      "package_throttle_count": "9",
                  }
              },
              "counter decreased",
          ),
          (
              {
                  "measurement_counters": {
                      **counters,
                      "package_throttle_count": "unavailable",
                  }
              },
              "counter is unavailable",
          ),
      ):
        after.write_text(
            json.dumps(
                {
                    "hostname": "host",
                    "measurement_counters": counters,
                    **mutation,
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(RuntimeError, message):
          baseline.command_machine_check(SimpleNamespace(before=before, after=after))

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

  def test_artifact_manifest_rejects_nonregular_nodes(self):
    for kind in ("symlink", "directory-symlink", "fifo", "socket"):
      with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        node = root / kind
        opened_socket = None
        if kind == "symlink":
          target = root / "target"
          target.write_text("data\n", encoding="utf-8")
          node.symlink_to(target)
        elif kind == "directory-symlink":
          target = root / "target"
          target.mkdir()
          node.symlink_to(target, target_is_directory=True)
        elif kind == "fifo":
          os.mkfifo(node)
        else:
          opened_socket = socket.socket(socket.AF_UNIX)
          opened_socket.bind(str(node))
        try:
          with self.assertRaisesRegex(RuntimeError, "Unsupported artifact node"):
            baseline.command_artifact_manifest(
                SimpleNamespace(root=str(root), output=str(root / "manifest.json"))
            )
        finally:
          if opened_socket is not None:
            opened_socket.close()

  def test_jar_content_digest_ignores_zip_order_and_timestamps(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      jars = (root / "first.jar", root / "second.jar")
      entries = (("a.txt", b"a"), ("b.txt", b"b"))
      for jar, ordered, year in (
          (jars[0], entries, 2025),
          (jars[1], tuple(reversed(entries)), 2026),
      ):
        with zipfile.ZipFile(jar, "w") as output:
          for name, content in ordered:
            info = zipfile.ZipInfo(name, (year, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            output.writestr(info, content)
      self.assertNotEqual(
          baseline.sha256_file(jars[0]), baseline.sha256_file(jars[1])
      )
      digests = []
      for jar in jars:
        output = io.StringIO()
        with redirect_stdout(output):
          baseline.command_jar_content_digest(SimpleNamespace(jar=str(jar)))
        digests.append(json.loads(output.getvalue()))
      self.assertEqual(digests[0], digests[1])

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

  def test_directory_digest_rejects_missing_or_non_directory_root(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      file_path = root / "file"
      file_path.write_text("content\n", encoding="utf-8")
      for invalid in (root / "missing", file_path):
        with self.subTest(path=invalid):
          with self.assertRaisesRegex(RuntimeError, "not a directory"):
            baseline.directory_digest(invalid)

  def test_python_runtime_digest_ignores_only_bytecode_caches(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      package = root / "yaml"
      metadata = root / "PyYAML.dist-info"
      package.mkdir()
      metadata.mkdir()
      (package / "__init__.py").write_text("version = 1\n", encoding="utf-8")
      (package / "_yaml.so").write_bytes(b"extension")
      (metadata / "METADATA").write_text("Version: 1\n", encoding="utf-8")
      selected = ("yaml", "PyYAML.dist-info")
      original = baseline.python_runtime_digest(root, selected)

      cache = package / "__pycache__"
      cache.mkdir()
      (cache / "__init__.cpython-312.pyc").write_bytes(b"cache")
      (package / "ignored.pyc").write_bytes(b"cache")
      (package / "ignored.pyo").write_bytes(b"cache")
      self.assertEqual(
          original, baseline.python_runtime_digest(root, selected)
      )

      for path in (
          package / "__init__.py",
          package / "_yaml.so",
          metadata / "METADATA",
          package / "unknown",
      ):
        with self.subTest(path=path):
          previous = path.read_bytes() if path.exists() else None
          path.write_bytes(b"changed")
          self.assertNotEqual(
              original, baseline.python_runtime_digest(root, selected)
          )
          if previous is None:
            path.unlink()
          else:
            path.write_bytes(previous)

  def test_python_runtime_digest_rejects_invalid_roots_and_special_nodes(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      (root / "package").mkdir()
      for selected in (("missing",), ("../package",), ("package", "package")):
        with self.subTest(selected=selected):
          with self.assertRaises(RuntimeError):
            baseline.python_runtime_digest(root, selected)
      fifo = root / "package/fifo"
      os.mkfifo(fifo)
      with self.assertRaisesRegex(RuntimeError, "Unsupported filesystem entry"):
        baseline.python_runtime_digest(root, ("package",))

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
