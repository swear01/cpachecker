"""Exercise the real wrapper with local supervisor/notification subprocesses only."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

WRAPPER = Path(__file__).resolve().parents[1] / "notify_core_only_completion.py"


@pytest.mark.parametrize(
    ("stopped", "missing_summary", "notification_exit", "expected_exit"),
    [(False, False, 0, 0), (True, False, 0, 1), (False, True, 0, 1),
     (False, False, 1, 1)],
)
def test_terminal_notification_after_summary(
    tmp_path, stopped, missing_summary, notification_exit, expected_exit,
):
    summary = tmp_path / "checkpoint-summary.json"
    receipt = tmp_path / "receipt.json"
    delivered = tmp_path / "delivered.json"
    hapi = tmp_path / "hapi"
    hapi.write_text(
        f"#!{sys.executable}\nimport json,sys\nfrom pathlib import Path\n"
        f"Path({str(delivered)!r}).write_text(json.dumps(sys.argv[1:]))\n"
        f"sys.exit({notification_exit})\n"
    )
    hapi.chmod(0o755)
    child = "import json,sys\nfrom pathlib import Path\n"
    if stopped:
        child += f"Path({str(tmp_path / 'STOP.json')!r}).write_text('{{\"new_failures\": [\"poly1\"]}}')\n"
    if not missing_summary:
        child += (
            f"Path({str(summary)!r}).write_text(json.dumps({{'arms': {{"
            "'stock': {'records': 2, 'missing_tasks': []}, "
            "'augmented': {'records': 1, 'missing_tasks': ['poly1']}}}))\n"
        )
    child += f"sys.exit({int(stopped)})\n"
    command = [sys.executable, str(WRAPPER), "--summary", str(summary),
               "--receipt", str(receipt), "--session", "test-session", "--",
               sys.executable, "-c", child]
    env = {**os.environ, "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"]}
    result = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
    assert result.returncode == expected_exit, result.stderr
    record = json.loads(receipt.read_text())
    args = json.loads(delivered.read_text())
    assert args[:2] == ["ping-peer", "test-session"]
    sent = json.loads(args[2].split("harvest: ", 1)[1])
    assert ("summary_error" in sent) == missing_summary
    if not missing_summary:
        assert sent["arms"]["augmented"] == {"records": 1, "missing": 1}
        assert bool(sent["stop"]) == stopped
        assert len(sent["summary_sha256"]) == 64
    assert record["notification"] == ("accepted" if notification_exit == 0 else "failed")
    # Neither completed evidence nor the receipt may be reused to start another supervisor.
    again = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
    assert again.returncode != 0
