from pathlib import Path


def test_extraction_evidence_runbook_preserves_external_authority_boundaries() -> None:
    text = Path("docs/EXTRACTION_EVIDENCE_RUNBOOK.md").read_text(encoding="utf-8")

    for phrase in (
        "scripts/build_extraction_split_manifests.py",
        "Do not replace the frozen execution source commit with current",
        "not proof of human independence",
        "selected expected run context, not from the signed envelope",
        "`production_authorized` remains false",
        "TEST must not feed back",
        "independent historical channel before TEST",
        "scripts/verify_extraction_release_calibration_binding.py",
        "release-calibration-binding.json",
        "There are no release-stage `--min-selective-coverage`",
        "A green CI run, a Git commit, or a structurally valid receipt alone is not that evidence",
    ):
        assert phrase in text

    release_section = text.split(
        "## 7. Build a release bundle mechanically bound to the frozen calibration chain",
        maxsplit=1,
    )[1].split("## 8.", maxsplit=1)[0]
    assert "--development-run nc-005 '<execution-id>'" in release_section
    assert "--test-run nc-005 '<execution-id>'" in release_section
    assert "--development-run nc-005 0.005" not in release_section
    assert "--test-run nc-005 0.005" not in release_section
