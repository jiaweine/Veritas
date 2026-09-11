from pathlib import Path


def test_execution_attestation_archive_docs_preserve_cold_verification_boundary() -> None:
    text = Path("docs/EXTRACTION_EXECUTION_ATTESTATION_ARCHIVE.md").read_text(
        encoding="utf-8"
    )

    for phrase in (
        "scripts/build_extraction_execution_attestation.py",
        "does **not** accept a caller-supplied threshold number",
        "exact canonical JSON byte contract",
        "not accepted as a trusted cold-verification input",
        "rebuilds execution evidence itself",
        "does not prove that an external runner actually enforced network isolation",
        "never grants production authority",
    ):
        assert phrase in text
