#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

import analyze_predicate_usefulness_gate as gate


class PredicateUsefulnessAnalysisTest(unittest.TestCase):
    def test_parse_and_reject_short_multiplicative_batch(self) -> None:
        features = gate.parse_first_call(
            """
            VGuide peel: refinement #10 loopHeadVisits=8 traceLen=9
            VGuide LLM round # 1 spurious # 10
            VGuide predicate  (assert (= x (bvmul y z)))
            VGuide predicate  (assert (= a (bvmul b c)))
            VGuide precision-injected 4 local predicates
            """
        )
        self.assertIsNotNone(features)
        self.assertTrue(gate.should_reject(features))

    def test_simulation_switches_rejected_task_to_stock(self) -> None:
        stock = {
            "loss": {"result": "TRUE", "wall_s": "3"},
            "win": {"result": "UNKNOWN", "wall_s": "300"},
        }
        vguide = {
            "loss": {"result": "UNKNOWN", "wall_s": "300"},
            "win": {"result": "TRUE", "wall_s": "5"},
        }
        with tempfile.TemporaryDirectory() as directory:
            logs = Path(directory)
            (logs / "loss.log").write_text(
                "VGuide peel: refinement #10 loopHeadVisits=5 traceLen=6\n"
                "VGuide LLM round # 1 spurious # 10\n"
                "VGuide predicate  (assert (= x (bvmul y z)))\n"
                "VGuide predicate  (assert (= a (bvmul b c)))\n"
            )
            (logs / "win.log").write_text(
                "VGuide peel: refinement #10 loopHeadVisits=10 traceLen=11\n"
                "VGuide LLM round # 1 spurious # 10\n"
                "VGuide predicate  (assert (= x (bvmul y z)))\n"
                "VGuide predicate  (assert (= a (bvmul b c)))\n"
            )
            result = gate.simulate(stock, vguide, logs, 300)

        self.assertEqual(2, result.gated_solved)
        self.assertEqual(0, result.gated_lost)
        self.assertEqual(1, result.rescued)
        self.assertEqual(0, result.sacrificed_wins)


if __name__ == "__main__":
    unittest.main()
