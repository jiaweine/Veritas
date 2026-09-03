from pathlib import Path


def test_claim_identity_documentation_locks_fail_closed_boundaries() -> None:
    text = Path("docs/CLAIM_GRAPH_IDENTITY.md").read_text(encoding="utf-8")

    for phrase in (
        "Claim -> Estimate -> Sample -> Data -> Code -> Assumption",
        "percent and percentage-point effects are different identities",
        "Cross-location E3 gate",
        "fails closed",
        "evaluate_claim_identity()",
        "independently from detector correctness",
        "Production hard-finding authority remains governed separately",
    ):
        assert phrase in text
