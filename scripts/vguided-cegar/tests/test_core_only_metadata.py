"""Missing or mutually corrupted provenance is never a valid pair."""

import json

import pytest
from test_core_only_integrity import fixture_pair, pair


@pytest.mark.parametrize(
    "field",
    [
        "cpu_list",
        "parallel",
        "evidence_tier",
        "model",
        "thinking",
        "reasoning_effort",
        "timeout_grace",
        "heap",
        "llm_api_url",
        "llm_max_completion_tokens",
        "timing_claims_allowed",
        "resource_snapshot",
    ],
)
def test_both_arms_missing_metadata_are_rejected(tmp_path, field):
    paths, manifest = fixture_pair(tmp_path)
    for path in paths:
        meta = path.parent / "run_meta.json"
        data = json.loads(meta.read_text())
        del data[field]
        meta.write_text(json.dumps(data))
    assert not pair.harvest(paths, manifest)["integrity_ok"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("parallel", True),
        ("parallel", 2),
        ("cpu_list", "4,4"),
        ("cpu_list", "16"),
        ("model", None),
        ("reasoning_effort", 42),
        ("llm_max_completion_tokens", ""),
        ("timing_claims_allowed", True),
        ("resource_snapshot", {}),
        ("resource_snapshot", None),
    ],
)
def test_both_arms_invalid_metadata_are_rejected(tmp_path, field, value):
    paths, manifest = fixture_pair(tmp_path)
    for path in paths:
        meta = path.parent / "run_meta.json"
        data = json.loads(meta.read_text())
        data[field] = value
        meta.write_text(json.dumps(data))
    assert not pair.harvest(paths, manifest)["integrity_ok"]


@pytest.mark.parametrize("field,value", [("cpu_list", "6"), ("heap", "2000M")])
def test_captured_resources_must_match_metadata(tmp_path, field, value):
    paths, manifest = fixture_pair(tmp_path)
    for path in paths:
        meta = path.parent / "run_meta.json"
        data = json.loads(meta.read_text())
        data[field] = value
        meta.write_text(json.dumps(data))
    report = pair.harvest(paths, manifest)
    assert not report["integrity_ok"]
    assert any("captured" in error for error in report["errors"])
