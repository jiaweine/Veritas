from pathlib import Path


def test_private_target_schema_doc_keeps_fail_closed_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "docs/reproduction-private-target-v1.md").read_text(encoding="utf-8")
    for phrase in (
        "orchestrator-only",
        "No undeclared keys are accepted",
        "finite JSON number",
        "row-level schema versions are forbidden",
        "booleans used as integers or numbers",
    ):
        assert phrase in text
