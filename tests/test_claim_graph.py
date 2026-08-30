from veritas.claims import (
    ArtifactRef,
    ClaimEdge,
    ClaimNode,
    ClaimRole,
    ExtractedField,
    RelationType,
    StatisticalClaimGraph,
    StatisticalObjectNode,
)
from veritas.models import SourceLocation


def test_claim_graph_round_trip_preserves_provenance():
    graph = StatisticalClaimGraph()
    graph.add_artifact(ArtifactRef("paper", "pdf", sha256="abc"))
    graph.add_claim(
        ClaimNode(
            claim_id="claim-1",
            text="Treatment increased employment.",
            role=ClaimRole.PRIMARY,
            estimand="ATT",
            source=SourceLocation(artifact_id="paper", page=4, section="Results", text_quote="increased employment"),
            extraction_confidence=0.97,
            identity_confidence=0.91,
        )
    )
    graph.add_object(
        StatisticalObjectNode(
            object_id="reg-1",
            object_type="RegressionResult",
            fields={
                "beta": ExtractedField(
                    raw="0.183***",
                    value=0.183,
                    source=SourceLocation(artifact_id="paper", page=6, table="4", row="Treatment", column="(3)"),
                    extraction_confidence=0.99,
                )
            },
            source=SourceLocation(artifact_id="paper", page=6, table="4"),
        )
    )
    graph.add_edge(ClaimEdge("claim-1", "reg-1", RelationType.SUPPORTS, confidence=0.94))

    restored = StatisticalClaimGraph.from_json(graph.to_json())

    assert restored.objects["reg-1"].fields["beta"].raw == "0.183***"
    assert restored.objects["reg-1"].fields["beta"].source.table == "4"
    assert restored.claims["claim-1"].identity_confidence == 0.91
    assert restored.edges[0].relation is RelationType.SUPPORTS


def test_claim_graph_rejects_dangling_edge():
    graph = StatisticalClaimGraph()
    graph.add_artifact(ArtifactRef("paper", "pdf"))
    graph.add_claim(ClaimNode("claim-1", "x", ClaimRole.PRIMARY, SourceLocation()))

    try:
        graph.add_edge(ClaimEdge("claim-1", "missing", RelationType.SUPPORTS))
    except ValueError as exc:
        assert "endpoints" in str(exc)
    else:
        raise AssertionError("expected dangling edge to be rejected")
