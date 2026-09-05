from pathlib import Path


DISPUTES = Path(__file__).parents[1] / "known_verdict_disputes.txt"


def _reasons():
    return {
        line.split("\t", 1)[0]: line.split("\t", 1)[1]
        for line in DISPUTES.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    }


def test_dispute_reasons_match_source_semantics():
    reasons = _reasons()
    assert len(reasons) == 12
    assert all("arithmetic formula" in reasons[task] for task in (
        "c/array-fpi/ifcomp.yml",
        "c/array-fpi/ifeqn4.yml",
        "c/array-fpi/sqm.yml",
    ))
    assert "array permutation" in reasons["c/array-tiling/revcpyswp2.yml"]
    assert all("heap/list structural" in reasons[task] for task in reasons if task.startswith("c/forester-heap/"))
    assert "official false is corroborated" in reasons[
        "c/hardware-verification-bv/btor2c-lazyMod.circular_pointer_top_w64_d8_e0.yml"
    ]
    assert "machine-model discrepancy remains unverified" in reasons[
        "c/hardware-verification-bv/btor2c-lazyMod.circular_pointer_top_w64_d8_e0.yml"
    ]
