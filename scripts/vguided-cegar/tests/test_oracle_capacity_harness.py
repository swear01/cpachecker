#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

import oracle_capacity_harness as harness


class OracleCapacityHarnessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        family = self.root / "nla-digbench"
        family.mkdir()
        self.source = family / "sample.c"
        self.source.write_text("int main(void) { int x = 0; return x; }\n")
        self.yml = family / "sample.yml"
        self.yml.write_text("properties:\n  - expected_verdict: true\n")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _catalog(self, *, sha: str | None = None) -> Path:
        payload = {
            "version": 1,
            "tasks": [
                {
                    "task": "sample",
                    "source": "nla-digbench/sample.c",
                    "yml": "nla-digbench/sample.yml",
                    "expected": "TRUE",
                    "source_sha256": sha
                    or hashlib.sha256(self.source.read_bytes()).hexdigest(),
                    "yml_sha256": hashlib.sha256(self.yml.read_bytes()).hexdigest(),
                    "predicates": [
                        "(= |main::x| 0)",
                        "(= (+ |main::x| |main::y|) |main::n|)",
                    ],
                }
            ],
        }
        path = self.root / "catalog.json"
        path.write_text(json.dumps(payload))
        return path

    def test_load_catalog_checks_hashes_and_expected_count(self) -> None:
        catalog = harness.load_catalog(
            self._catalog(), self.root, expected_count=1, verify_hashes=True
        )
        self.assertEqual(["sample"], [task.task for task in catalog.tasks])
        self.assertEqual("TRUE", catalog.tasks[0].expected)

    def test_load_catalog_rejects_source_hash_mismatch(self) -> None:
        with self.assertRaisesRegex(harness.CatalogError, "source SHA-256 mismatch"):
            harness.load_catalog(
                self._catalog(sha="0" * 64),
                self.root,
                expected_count=1,
                verify_hashes=True,
            )

    def test_converter_compatibility_rejects_nary_arithmetic(self) -> None:
        with self.assertRaisesRegex(harness.CatalogError, "operator \\+ requires 2 operands"):
            harness.validate_converter_compatible(
                "(= (+ |main::x| |main::y| |main::z|) |main::n|)", "sample"
            )

    def test_render_predicate_map_declares_int_symbols_once(self) -> None:
        catalog = harness.load_catalog(
            self._catalog(), self.root, expected_count=1, verify_hashes=True
        )
        rendered = harness.render_predicate_map(catalog.tasks[0])
        self.assertIn("(declare-fun |main::x| () Int)", rendered)
        self.assertIn("(declare-fun |main::y| () Int)", rendered)
        self.assertIn("(declare-fun |main::n| () Int)", rendered)
        self.assertEqual(1, rendered.count("(declare-fun |main::x| () Int)"))
        self.assertIn("\n*:\n", rendered)
        self.assertIn("(assert (= |main::x| 0))", rendered)

        conjunction = harness.render_predicate_map(catalog.tasks[0], shape="conjunction")
        self.assertEqual(1, conjunction.count("(assert "))
        self.assertIn(
            "(assert (and (= |main::x| 0) (= (+ |main::x| |main::y|) |main::n|)))",
            conjunction,
        )

        supporting = harness.render_predicate_map(
            catalog.tasks[0], shape="supporting-first"
        )
        self.assertLess(
            supporting.index("(assert (= (+ |main::x| |main::y|) |main::n|))"),
            supporting.index("(assert (= |main::x| 0))"),
        )

    def test_select_tasks_rejects_unknown_names(self) -> None:
        catalog = harness.load_catalog(
            self._catalog(), self.root, expected_count=1, verify_hashes=True
        )
        self.assertEqual((catalog.tasks[0],), harness.select_tasks(catalog, ["sample"]).tasks)
        with self.assertRaisesRegex(harness.CatalogError, "unknown requested tasks"):
            harness.select_tasks(catalog, ["missing"])

    def test_build_command_uses_existing_k_induction_import_path(self) -> None:
        task = harness.load_catalog(
            self._catalog(), self.root, expected_count=1, verify_hashes=True
        ).tasks[0]
        command = harness.build_command(
            repo=Path("/repo"),
            task=task,
            benchmark_root=self.root,
            output_dir=Path("/out"),
            timelimit=60,
            heap="4G",
            predicate_map=Path("/pred/sample.smt2"),
            encoding="bv",
        )
        joined = " ".join(str(x) for x in command)
        self.assertIn("config/components/kInduction/kInduction.properties", joined)
        self.assertIn("bmc.kinduction.predicatePrecisionFile=/pred/sample.smt2", joined)
        self.assertIn(
            "cpa.predicate.abstraction.initialPredicates.encodePredicates=INT2BV",
            joined,
        )
        self.assertIn("bmc.kinduction.reuse.pred.strategy=GLOBAL", joined)
        self.assertTrue(joined.endswith("nla-digbench/sample.c"))

    def test_build_command_supports_exact_nonlinear_integer_encoding(self) -> None:
        task = harness.load_catalog(
            self._catalog(), self.root, expected_count=1, verify_hashes=True
        ).tasks[0]
        command = harness.build_command(
            repo=Path("/repo"),
            task=task,
            benchmark_root=self.root,
            output_dir=Path("/out"),
            timelimit=60,
            heap="4G",
            predicate_map=Path("/pred/sample.smt2"),
            encoding="nia",
        )
        joined = " ".join(str(x) for x in command)
        self.assertIn("cpa.predicate.encodeBitvectorAs=INTEGER", joined)
        self.assertIn("cpa.predicate.useNonlinearArithmeticForIntAsBv=true", joined)
        self.assertIn("solver.nonLinearArithmetic=USE", joined)
        self.assertIn("solver.solver=Z3", joined)
        self.assertNotIn("encodePredicates=INT2BV", joined)

    def test_build_command_supports_conjunctive_k_induction_candidates(self) -> None:
        task = harness.load_catalog(
            self._catalog(), self.root, expected_count=1, verify_hashes=True
        ).tasks[0]
        command = harness.build_command(
            repo=Path("/repo"),
            task=task,
            benchmark_root=self.root,
            output_dir=Path("/out"),
            timelimit=60,
            heap="4G",
            predicate_map=Path("/pred/sample.smt2"),
            encoding="bv",
            consumer="kinduction",
            oracle_mode="conjunction",
        )
        joined = " ".join(str(x) for x in command)
        self.assertIn("bmc.kinduction.reuse.pred.conjunction=true", joined)

    def test_build_command_supports_direct_pdr_oracle_vocabulary(self) -> None:
        task = harness.load_catalog(
            self._catalog(), self.root, expected_count=1, verify_hashes=True
        ).tasks[0]
        command = harness.build_command(
            repo=Path("/repo"),
            task=task,
            benchmark_root=self.root,
            output_dir=Path("/out"),
            timelimit=60,
            heap="4G",
            predicate_map=Path("/pred/sample.smt2"),
            encoding="bv",
            consumer="pdr-abstraction",
            oracle_mode="abstraction",
        )
        joined = " ".join(str(x) for x in command)
        self.assertIn(
            "config/unmaintained/components/kInduction/pdr.properties", joined
        )
        self.assertIn("pdr.abstractionStrategy=ALLSAT_BASED_PREDICATE_ABSTRACTION", joined)
        self.assertIn("pdr.liftingStrategy=ABSTRACTION_BASED_LIFTING", joined)
        self.assertIn(
            "pdr.oraclePredicatePrecisionFile=/pred/sample.smt2", joined
        )
        self.assertIn("pdr.oracleMode=ABSTRACTION", joined)
        self.assertNotIn("bmc.kinduction.predicatePrecisionFile", joined)

    def test_parse_log_distinguishes_result_and_failure_stage(self) -> None:
        parsed = harness.parse_log(
            """
            Number of invariants proposed: 3
            Verification result: TRUE. No property violation found by chosen configuration.
            Total time for CPAchecker: 4.250s
            """
        )
        self.assertEqual("TRUE", parsed.result)
        self.assertEqual(4.25, parsed.wall_s)
        self.assertEqual(3, parsed.invariants_proposed)
        self.assertEqual("solved", parsed.note)

        attributed = harness.parse_log(
            """
            PDR oracle predicates seeded:        3
            PDR oracle roots confirmed:          1
            Target confirmed after oracle root:    true
            Verification result: TRUE
            """
        )
        self.assertEqual(3, attributed.oracle_predicates_seeded)
        self.assertEqual(1, attributed.oracle_roots_confirmed)
        self.assertTrue(attributed.target_after_oracle_root)

        failed = harness.parse_log(
            "Could not read precision from file named p.smt2\nVerification result: UNKNOWN"
        )
        self.assertEqual("candidate_parse", failed.note)

        assertion = harness.parse_log(
            'CPU-time limit of 10s\nException in thread "main" java.lang.AssertionError: '
            "There was a problem while parsing the formula"
        )
        self.assertEqual("candidate_parse", assertion.note)

        fast_unknown = harness.parse_log(
            "Using the following resource limits: CPU-time limit of 10s\n"
            "Verification result: UNKNOWN, incomplete analysis."
        )
        self.assertEqual("unknown", fast_unknown.note)

        invalid = harness.parse_log(
            "Error: Invalid configuration (The SMT solver Z3 is not available on this machine)"
        )
        self.assertEqual("invalid_configuration", invalid.note)

    def test_compare_arms_reports_new_lost_and_wrong(self) -> None:
        rows = harness.compare_arms(
            [
                ("new", "TRUE", "UNKNOWN", "TRUE"),
                ("lost", "TRUE", "TRUE", "UNKNOWN"),
                ("wrong", "TRUE", "UNKNOWN", "FALSE"),
                ("same", "FALSE", "FALSE", "FALSE"),
            ]
        )
        self.assertEqual(1, rows.new)
        self.assertEqual(1, rows.lost)
        self.assertEqual(1, rows.wrong)
        self.assertEqual(2, rows.stock_solved)
        self.assertEqual(3, rows.oracle_solved)

    def test_infrastructure_failures_are_not_scientific_unknowns(self) -> None:
        failures = harness.infrastructure_failures(
            {
                "stock": [{"task": "a", "note": "unknown"}],
                "oracle": [
                    {"task": "a", "note": "invalid_configuration"},
                    {"task": "b", "note": "candidate_parse"},
                ],
            }
        )
        self.assertEqual(
            ["oracle/a:invalid_configuration", "oracle/b:candidate_parse"], failures
        )


if __name__ == "__main__":
    unittest.main()
