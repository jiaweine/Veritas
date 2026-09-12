from pathlib import Path


def test_bound_external_provenance_docs_lock_authoritative_entrypoint() -> None:
    text = Path("docs/BOUND_EXTRACTION_EXTERNAL_PROVENANCE.md").read_text(encoding="utf-8")

    for phrase in (
        "scripts/verify_bound_extraction_external_provenance.py",
        "compatibility verifier for older unbound archives",
        "time-of-check/time-of-use gap",
        "reconstruct and compare the release calibration binding",
        "reconstruct and compare the release execution binding",
        "independently selected expectations",
        "must not be copied from the signed envelope",
        "does **not** prove",
        "`production_authorized` remains false",
    ):
        assert phrase in text
