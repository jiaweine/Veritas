from pathlib import Path


def test_reproduction_security_invariants_document_authority_boundaries() -> None:
    text = Path("docs/reproduction-security-invariants-v0.11.md").read_text(encoding="utf-8")

    for phrase in (
        "Duplicate object keys are rejected",
        "Booleans are never accepted as integers or numeric results",
        "internal claim IDs, task IDs, and method-spec IDs are excluded",
        "truthy strings do not grant access",
        "does not trust a caller-provided `MATCH`/`MISMATCH` status",
        "must not reuse the CodeAgent identity",
        "`production_authorized: false`",
        "`e4_authorized: false`",
        "remains experimental",
    ):
        assert phrase in text
