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
        "A green CI run, a Git commit, or a structurally valid receipt alone is not that evidence",
    ):
        assert phrase in text
