from pathlib import Path


def test_postverification_external_handoff_preserves_authority_boundary() -> None:
    text = Path("docs/EXTRACTION_POSTVERIFICATION_EXTERNAL_HANDOFF.md").read_text(
        encoding="utf-8"
    )

    for phrase in (
        "after `verify_bound_extraction_external_provenance.py` succeeds",
        "new post-verification archive event",
        "It does not directly commit the later release sidecar files",
        "is not an external archive receipt",
        "archive_object_set_sha256",
        "independent_archive_receipt_present=false",
        "independent_control_established=false",
        "historical_channel_semantics_established=false",
        "production_authorized=false",
        "Issue #26 remains open",
    ):
        assert phrase in text
