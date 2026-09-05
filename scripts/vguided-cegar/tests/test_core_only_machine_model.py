"""Regression checks for issue #178's core-only machine-model launch mapping."""

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
RUNNER = ROOT / "scripts/vguided-cegar/run_core_only.sh"


def runner_env(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    mpstat = fake_bin / "mpstat"
    mpstat.write_text(
        "#!/bin/sh\n"
        "for sample in 1 2 3 4 5; do\n"
        "  for core in 0 2 4 6 8 10 12 14; do\n"
        "    echo \"12:00:$sample $core 0 0 0 0 0 100\"\n"
        "  done\n"
        "done\n"
    )
    mpstat.chmod(0o755)
    replay = tmp_path / "replay"
    replay.mkdir()
    return {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "SV_BENCHMARKS": str(tmp_path),
        "VGUIDE_LLM_REPLAY_DIR": str(replay),
    }


def manifest(path: Path, data_model: str, family: str = "issue178") -> Path:
    path.write_text(
        json.dumps(
            {
                "task_count": 1,
                "tasks": [
                    {
                        "task": f"c/issue178/{data_model}.yml",
                        "source_paths": [f"c/issue178/{data_model}.c"],
                        "expected_verdict": "true",
                        "data_model": data_model,
                        "family": family,
                        "task_sha256": "a" * 64,
                        "source_sha256": ["b" * 64],
                    }
                ],
            }
        )
    )
    return path


def verified_manifest(path: Path, benchmark_root: Path, data_model: str) -> Path:
    source = benchmark_root / "issue178" / f"{data_model}.c"
    source.parent.mkdir()
    source.write_text(
        "int main(void) { return sizeof(long) == sizeof(void*) ? 0 : 1; }\n"
    )
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    task = f"c/issue178/{data_model}.yml"
    path.write_text(
        json.dumps(
            {
                "task_count": 1,
                "tasks": [
                    {
                        "task": task,
                        "source_paths": [f"c/issue178/{data_model}.c"],
                        "expected_verdict": "true",
                        "data_model": data_model,
                        "family": "issue178",
                        "task_sha256": "a" * 64,
                        "source_sha256": [source_sha],
                    }
                ],
            }
        )
    )
    return path


@pytest.mark.parametrize(
    ("arm", "data_model", "expected"),
    [
        ("stock", "ILP32", "Linux32"),
        ("stock", "LP64", "Linux64"),
        ("augmented", "ILP32", "Linux32"),
        ("augmented", "LP64", "Linux64"),
    ],
)
def test_dry_run_captures_real_launch_for_each_arm_and_model(tmp_path, arm, data_model, expected):
    result = subprocess.run(
        [
            str(RUNNER),
            "--arm",
            arm,
            "--manifest",
            str(manifest(tmp_path / "manifest.json", data_model)),
            "--out",
            str(tmp_path / "out"),
            "--dry-run",
        ],
        env=runner_env(tmp_path),
        text=True,
        capture_output=True,
        check=True,
    )
    assert f"data_model={data_model} effective_machine_model={expected.upper()}" in result.stdout
    assert f"analysis.machineModel={expected}" in result.stdout
    assert "scripts/cpa.sh" in result.stdout


@pytest.mark.parametrize("data_model", ["", "ILP64", "LP32"])
def test_dry_run_rejects_missing_or_unsupported_model(tmp_path, data_model):
    result = subprocess.run(
        [
            str(RUNNER),
            "--arm",
            "stock",
            "--manifest",
            str(
                manifest(
                    tmp_path / "manifest.json",
                    data_model,
                    family="LP64" if data_model == "" else "issue178",
                )
            ),
            "--out",
            str(tmp_path / "out"),
            "--dry-run",
        ],
        env=runner_env(tmp_path),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "unsupported or missing data_model" in result.stderr


def test_width_sensitive_fixture_is_not_a_model_free_noop(tmp_path):
    gcc = shutil.which("gcc")
    if gcc is None:
        pytest.skip("gcc is required for the width-sensitive fixture")
    fixture = tmp_path / "width.c"
    fixture.write_text(
        "int main(void) {\n"
        "  return sizeof(long) == sizeof(void*) && sizeof(long) == 8 ? 0 : 1;\n"
        "}\n"
    )
    assert "sizeof(long)" in fixture.read_text()
    assert "sizeof(void*)" in fixture.read_text()
    for bits, expected_exit in ((32, 1), (64, 0)):
        binary = tmp_path / f"width{bits}"
        try:
            subprocess.run([gcc, f"-m{bits}", str(fixture), "-o", str(binary)], check=True)
        except subprocess.CalledProcessError as exc:
            pytest.skip(f"gcc -m{bits} multilib is unavailable: {exc}")
        assert subprocess.run([str(binary)], check=False).returncode == expected_exit


def test_real_runner_records_marker_and_requires_it_for_resume(tmp_path):
    fake_root = tmp_path / "fake-cpa"
    fake_bin = fake_root / "bin"
    fake_bin.mkdir(parents=True)
    fake_cpa = fake_bin / "cpachecker"
    fake_cpa.write_text(
        "#!/bin/sh\n"
        "echo 'Using predicate analysis with Z3 version test'\n"
        "echo 'Verification result: TRUE. No error found.'\n"
        "echo 'Total time for CPAchecker:      0.001s'\n"
        "echo 'Total CPU time for CPAchecker:  0.001s'\n"
        "echo 'Memory consumption for CPAchecker: 1.0 MB'\n"
    )
    fake_cpa.chmod(0o755)
    manifest_path = verified_manifest(tmp_path / "manifest.json", tmp_path, "LP64")
    env = runner_env(tmp_path)
    env["PATH_TO_CPACHECKER"] = str(fake_root)
    command = [
        str(RUNNER),
        "--arm",
        "stock",
        "--manifest",
        str(manifest_path),
        "--out",
        str(tmp_path / "out"),
        "--parallel",
        "1",
        "--timelimit",
        "1",
    ]
    first = subprocess.run(command, env=env, text=True, capture_output=True, check=False)
    assert first.returncode == 0, first.stdout + first.stderr
    log = next((tmp_path / "out" / "logs").glob("*.log"))
    assert "Effective machine model: LINUX64\n" in log.read_text()
    assert json.loads(next((tmp_path / "out" / "logs").glob("*.json")).read_text())["verdict"] == "TRUE"

    second = subprocess.run(command, env=env, text=True, capture_output=True, check=False)
    assert second.returncode == 0, second.stdout + second.stderr
    assert "skip c/issue178/LP64.yml (record exists)" in second.stdout
