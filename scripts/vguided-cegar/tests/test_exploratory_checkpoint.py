"""Exploratory load policy must remain explicit and part of resume identity."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

RUNNER = Path(__file__).resolve().parents[1] / "run_core_only.sh"


def test_exploratory_load_allocation_and_resume(tmp_path):
    mpstat = tmp_path / "mpstat"
    mpstat.write_text(
        "#!/bin/bash\n"
        "for sample in {1..5}; do\n"
        "  for cpu in 0 2 4 6 8 10 12 14; do\n"
        "    echo \"01:00:00 $cpu 99 0 1\"\n"
        "  done\n"
        "done\n"
    )
    mpstat.chmod(0o755)
    taskset = tmp_path / "taskset"
    taskset.write_text("#!/bin/sh\necho 'Verification result: TRUE. No property violation found.'\n")
    taskset.chmod(0o755)
    source = tmp_path / "test.c"
    source.write_text("int main(void) { return 0; }\n")
    task = tmp_path / "test.yml"
    task.write_text("input_files: test.c\noptions:\n  data_model: ILP32\n")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"task_count": 1, "tasks": [{
        "task": "c/test.yml", "source_paths": ["c/test.c"],
        "expected_verdict": "true", "data_model": "ILP32", "family": "test",
        "task_sha256": hashlib.sha256(task.read_bytes()).hexdigest(),
        "source_sha256": [hashlib.sha256(source.read_bytes()).hexdigest()],
    }]}))
    output = tmp_path / "out"
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}",
           "SV_BENCHMARKS": str(tmp_path)}

    def run(*args):
        stdout, stderr = tmp_path / "stdout", tmp_path / "stderr"
        with stdout.open("w") as out, stderr.open("w") as err:
            result = subprocess.run(
                ["bash", str(RUNNER), "--arm", "stock", "--manifest", str(manifest),
                 "--out", str(output), "--parallel", "2", *args],
                env=env, text=True, stdout=out, stderr=err, timeout=20, check=False,
            )
        return subprocess.CompletedProcess(
            result.args, result.returncode, stdout.read_text(), stderr.read_text()
        )

    formal = run("--dry-run")
    assert formal.returncode != 0
    assert "P-core contention" in formal.stderr
    for allocation in ("8,8", "8,9", "8", "8,"):
        assert run("--exploratory", "--cpu-list", allocation).returncode != 0
    assert run("--cpu-list", "8,10").returncode != 0

    exploratory = run("--exploratory", "--cpu-list", "8,10")
    assert exploratory.returncode == 0, exploratory.stdout + exploratory.stderr
    meta = json.loads((output / "run_meta.json").read_text())
    assert meta["evidence_tier"] == "exploratory"
    assert meta["cpu_list"] == "8,10"
    assert meta["timing_claims_allowed"] is False
    assert "8:99.00" in meta["load_check"]
    assert meta["resource_snapshot"]["meminfo"]
    assert meta["resource_snapshot"]["memory_pressure"]

    changed = run("--exploratory", "--cpu-list", "12,14")
    assert changed.returncode != 0
    assert "provenance mismatch: cpu_list" in changed.stderr
    assert json.loads((output / "run_meta.json").read_text()) == meta
