"""Real signal delivery must not leave the isolated verifier running."""

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
@pytest.mark.parametrize("with_descendant", [False, True])
def test_capture_interruption_reaps_verifier(tmp_path, signum, with_descendant):
    log, status, ready = (tmp_path / name for name in ("raw.log", "status.json", "pid"))
    child_code = (
        "import os,signal,time; from pathlib import Path; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "print('verifier started', flush=True); "
        f"p=Path({str(ready)!r}); "
        "p.with_suffix('.tmp').write_text(str(os.getpid())); "
        "p.with_suffix('.tmp').replace(p); time.sleep(60)"
    )
    descendant = tmp_path / "descendant"
    if with_descendant:
        descendant_code = (
            "import os,signal,time; from pathlib import Path; "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            f"p=Path({str(descendant)!r}); "
            "p.with_suffix('.tmp').write_text(str(os.getpid())); "
            "p.with_suffix('.tmp').replace(p); time.sleep(60)"
        )
        child_code = (
            "import subprocess,time; from pathlib import Path\n"
            f"subprocess.Popen([{sys.executable!r}, '-c', {descendant_code!r}])\n"
            f"while not Path({str(descendant)!r}).exists(): time.sleep(0.01)\n"
            + child_code.replace("signal.signal(signal.SIGTERM, signal.SIG_IGN); ", "")
        )
    capture = subprocess.Popen(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "core_only_records.py"),
            "capture",
            "--log",
            str(log),
            "--status",
            str(status),
            "--wall-limit",
            "60",
            "--",
            sys.executable,
            "-c",
            child_code,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    child_pid = None
    try:
        deadline = time.monotonic() + 20
        while not ready.exists() and time.monotonic() < deadline:
            assert capture.poll() is None
            time.sleep(0.05)
        assert ready.is_file(), "verifier did not become ready"
        child_pid = int(ready.read_text())
        assert os.getpgid(child_pid) == child_pid
        capture.send_signal(signum)
        time.sleep(0.1)
        if capture.poll() is None:
            capture.send_signal(signum)
        assert capture.wait(timeout=20) == -signum
        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)
        assert log.read_bytes() == b"verifier started\n"
        outcome = json.loads(status.read_text())
        assert outcome["termination_reason"] == "interrupted"
        child_signal = signal.SIGTERM if with_descendant else signal.SIGKILL
        assert outcome["exit_code"] == -child_signal
        assert outcome["signal"] == child_signal
        if with_descendant:
            proc_stat = Path(f"/proc/{int(descendant.read_text())}/stat")
            deadline = time.monotonic() + 3
            while True:
                try:
                    if proc_stat.read_text().split()[2] == "Z":
                        break
                except FileNotFoundError:
                    break
                assert time.monotonic() < deadline, "descendant still running"
                time.sleep(0.01)

        assert outcome["raw_wall_s"] > 0
        assert outcome["log_sha256"] == hashlib.sha256(log.read_bytes()).hexdigest()
    finally:
        if child_pid is not None:
            try:
                os.killpg(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if capture.poll() is None:
            capture.kill()
        capture.wait(timeout=5)
