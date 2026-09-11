from pathlib import Path


def test_development_freeze_docs_preserve_temporal_and_authority_boundaries() -> None:
    text = Path("docs/EXTRACTION_DEVELOPMENT_FREEZE.md").read_text(encoding="utf-8")

    for phrase in (
        "scripts/freeze_extraction_development_threshold.py",
        "scripts/build_extraction_test_evaluation_lock.py",
        "scripts/build_extraction_development_freeze_external_handoff.py",
        "scripts/verify_extraction_pretest_external_archive_receipt.py",
        "The command has no TEST-manifest, TEST-prediction, or TEST-metric argument",
        "executed_v015_development_predictions=true",
        "executed_v015_test_predictions=false",
        "Only after the second archive/receipt exists",
        "TEST must not feed back",
        "do not prove that the named channel was independently controlled",
    ):
        assert phrase in text
