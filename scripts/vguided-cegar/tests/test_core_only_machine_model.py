"""Regression checks for issue #178's core-only machine-model launch mapping."""

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
    return {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "SV_BENCHMARKS": str(tmp_path),
        "VGUIDE_LLM_REPLAY_DIR": str(tmp_path / "replay"),
    }


def manifest(path: Path, data_model: str) -> Path:
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
                        "family": "issue178",
                        "task_sha256": "a" * 64,
                        "source_sha256": ["b" * 64],
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
            str(manifest(tmp_path / "manifest.json", data_model)),
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
    assert "invalid data model" in result.stderr


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
        subprocess.run([gcc, f"-m{bits}", str(fixture), "-o", str(binary)], check=True)
        assert subprocess.run([str(binary)], check=False).returncode == expected_exit
