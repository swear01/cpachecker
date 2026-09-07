from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import analyze_predicate_study as study


HOOK_LOG = "Unified VGuide CEGAR enabled\nVerification result: UNKNOWN.\n"


def write_summary(task_dir: Path, *, refinements: int = 0, llm_rounds: int = 0) -> None:
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task_summary.json").write_text(
        json.dumps(
            {
                "task": task_dir.name,
                "verdict": "UNKNOWN",
                "refinements": refinements,
                "llm_rounds": llm_rounds,
                "llm_api_calls": llm_rounds,
                "precision_final": {"local": {}, "global": []},
            }
        )
    )


def write_refinement(task_dir: Path, **row: object) -> None:
    (task_dir / "refinements.jsonl").write_text(json.dumps(row) + "\n")


class PredicateStudyCoverageTest(unittest.TestCase):
    def test_classifies_proven_no_hook_without_failing_missing_task_dump(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = root / "tasks" / "no_hook"
            logs = root / "logs"
            logs.mkdir()
            (logs / "no_hook.log").write_text("Verification result: UNKNOWN, incomplete analysis.\n")

            coverage = study.classify_coverage(task, (logs / "no_hook.log").read_text())
            self.assertEqual(coverage.status, "vguide_not_reached")
            self.assertEqual(coverage.dump_status, "not_applicable")

            task.parent.mkdir()
            (root / "run_manifest.json").write_text(json.dumps({"dump_prompts": False}))
            manifest = root / "manifest.list"
            manifest.write_text("no_hook.yml\n")
            report = study.validate_dump(root, manifest, logs, expected_count=1)
            self.assertTrue(report.ok, report.failures)

    def test_distinguishes_no_spurious_ce_and_scheduled_skip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            no_ce = root / "tasks" / "no_ce"
            write_summary(no_ce)
            self.assertEqual(study.classify_coverage(no_ce, HOOK_LOG).status, "no_spurious_ce")

            scheduled = root / "tasks" / "scheduled"
            write_summary(scheduled, refinements=1)
            write_refinement(scheduled, llm_called=False, llm_skip_reason="schedule")
            self.assertEqual(
                study.classify_coverage(scheduled, HOOK_LOG).status,
                "llm_not_scheduled",
            )

    def test_preserves_provider_failure_and_crash_as_non_verdict_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = root / "tasks" / "provider"
            write_summary(provider, refinements=1)
            write_refinement(provider, llm_called=False, llm_skip_reason="llm_failed")
            coverage = study.classify_coverage(provider, "VGuide LLM call failed: 429\n")
            self.assertEqual(coverage.status, "provider_failure")
            self.assertEqual(coverage.reason, "llm_failed")

            crashed = root / "tasks" / "crashed"
            crashed.mkdir(parents=True)
            coverage = study.classify_coverage(crashed, HOOK_LOG + "# SIGSEGV (0xb)\n")
            self.assertEqual(coverage.status, "analysis_crash")

    def test_missing_or_malformed_dump_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing = root / "tasks" / "missing"
            coverage = study.classify_coverage(missing, HOOK_LOG)
            self.assertEqual(coverage.status, "dump_incomplete")
            self.assertEqual(coverage.reason, "missing_task_directory")

            malformed = root / "tasks" / "malformed"
            write_summary(malformed)
            (malformed / "refinements.jsonl").write_text("not json\n")
            coverage = study.classify_coverage(malformed, HOOK_LOG)
            self.assertEqual(coverage.status, "dump_incomplete")
            self.assertEqual(coverage.dump_status, "malformed")

            missing_rows = root / "tasks" / "missing_rows"
            write_summary(missing_rows, refinements=1)
            coverage = study.classify_coverage(missing_rows, HOOK_LOG)
            self.assertEqual(coverage.reason, "missing_refinements_jsonl")

    def test_dump_is_sufficient_reach_evidence_when_hook_log_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            task_dir = Path(directory) / "task"
            write_summary(task_dir)
            coverage = study.classify_coverage(task_dir, "Verification result: UNKNOWN.\n")
            self.assertEqual(coverage.status, "no_spurious_ce")

    def test_missing_log_metrics_are_not_zero(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "task.log"
            log.write_text("Verification result: UNKNOWN.\n")
            parsed = study.load_log_verdict(log)
            self.assertIsNone(parsed["wall_s"])
            self.assertIsNone(parsed["refinements"])

    def test_analysis_report_retains_coverage_counts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tasks").mkdir()
            (root / "run_manifest.json").write_text(json.dumps({"dump_prompts": False}))
            manifest = root / "manifest.list"
            manifest.write_text("missing.yml\n")
            logs = root / "logs"
            logs.mkdir()
            (logs / "missing.log").write_text(HOOK_LOG)
            out = root / "analysis"

            study.run_analysis(root, manifest, logs, None, out)

            report = (out / "analysis_report.md").read_text()
            self.assertIn("'dump_incomplete': 1", report)
            row = (out / "overlap_summary.csv").read_text()
            self.assertIn(",dump_incomplete,missing_task_directory,", row)


if __name__ == "__main__":
    unittest.main()
