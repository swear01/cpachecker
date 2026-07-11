#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

import verify_llm_response_pair as pair


class VerifyLlmResponsePairTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write_calls(self, arm, task, rows):
        path = self.root / arm / task / "llm_rounds.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))

    def test_accepts_exact_replay_prefix(self):
        self.write_calls(
            "record",
            "task",
            [
                {"request_hash": "q1", "response_hash": "r1", "response_source": "live_recorded"},
                {"request_hash": "q2", "response_hash": "r2", "response_source": "live_recorded"},
            ],
        )
        self.write_calls(
            "replay",
            "task",
            [{"request_hash": "q1", "response_hash": "r1", "response_source": "replay"}],
        )

        result = pair.verify_pair(self.root / "record", self.root / "replay")

        self.assertEqual(result.tasks, 1)
        self.assertEqual(result.replayed_calls, 1)

    def test_rejects_response_mismatch(self):
        self.write_calls(
            "record",
            "task",
            [{"request_hash": "q", "response_hash": "recorded", "response_source": "live_recorded"}],
        )
        self.write_calls(
            "replay",
            "task",
            [{"request_hash": "q", "response_hash": "different", "response_source": "replay"}],
        )

        with self.assertRaisesRegex(ValueError, "not an exact prefix"):
            pair.verify_pair(self.root / "record", self.root / "replay")


if __name__ == "__main__":
    unittest.main()
