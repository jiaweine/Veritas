from pathlib import Path


def test_postverification_archive_receipt_docs_preserve_authority_boundary() -> None:
    text = Path("docs/EXTRACTION_POSTVERIFICATION_ARCHIVE_RECEIPT.md").read_text(
        encoding="utf-8"
    )

    for phrase in (
        "does **not** provide a command that generates that external receipt",
        "verify_extraction_postverification_external_archive_receipt.py",
        "Do not copy expected custodian/channel/record values from the receipt",
        "does not trust the handoff's stored `archive_object_set_sha256` without reconstruction",
        "independent_control_established=false",
        "historical_channel_semantics_established=false",
        "production_authorized=false",
        "does not retroactively expand the original external Ed25519 provenance signature",
        "Issue #26 remains open",
    ):
        assert phrase in text
