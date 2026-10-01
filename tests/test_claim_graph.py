import json

import pytest

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
from veritas.types import ComparisonOperator


def test_claim_graph_round_trip_preserves_provenance():
    graph = StatisticalClaimGraph()
    graph.add_artifact(ArtifactRef("paper", "pdf", sha256="abc"))
    graph.add_claim(
        ClaimNode(
            claim_id="claim-1",
            text="Treatment increased employment.",
            role=ClaimRole.PRIMARY,
            estimand="ATT",
            source=SourceLocation(
                artifact_id="paper",
                page=4,
                section="Results",
                text_quote="increased employment",
            ),
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
                    source=SourceLocation(
                        artifact_id="paper",
                        page=6,
                        table="4",
                        row="Treatment",
                        column="(3)",
                    ),
                    extraction_confidence=0.99,
                    displayed_precision=3,
                    comparison_operator=ComparisonOperator.EQ,
                    identity_confidence=0.93,
                )
            },
            source=SourceLocation(artifact_id="paper", page=6, table="4"),
        )
    )
    graph.add_edge(ClaimEdge("claim-1", "reg-1", RelationType.SUPPORTS, confidence=0.94))

    restored = StatisticalClaimGraph.from_json(graph.to_json())
    beta = restored.objects["reg-1"].fields["beta"]

    assert beta.raw == "0.183***"
    assert beta.source.table == "4"
    assert beta.displayed_precision == 3
    assert beta.comparison_operator is ComparisonOperator.EQ
    assert beta.identity_confidence == 0.93
    assert beta.effective_confidence == 0.93
    assert restored.claims["claim-1"].identity_confidence == 0.91
    assert restored.edges[0].relation is RelationType.SUPPORTS


def test_claim_graph_loads_legacy_extracted_fields_without_new_metadata():
    payload = {
        "artifacts": {
            "paper": {
                "artifact_id": "paper",
                "kind": "pdf",
                "sha256": None,
                "uri": None,
            }
        },
        "claims": {},
        "objects": {
            "reg-1": {
                "object_id": "reg-1",
                "object_type": "RegressionResult",
                "source": {"artifact_id": "paper"},
                "fields": {
                    "p": {
                        "raw": "p < .05",
                        "value": 0.05,
                        "source": {"artifact_id": "paper", "page": 7},
                        "extraction_confidence": 0.88,
                    }
                },
            }
        },
        "evidence_nodes": {},
        "edges": [],
    }

    graph = StatisticalClaimGraph.from_json(json.dumps(payload))
    field = graph.objects["reg-1"].fields["p"]

    assert field.displayed_precision is None
    assert field.comparison_operator is None
    assert field.identity_confidence == 1.0
    assert field.effective_confidence == 0.88


def test_extracted_field_validates_display_semantics_and_identity_confidence():
    source = SourceLocation(artifact_id="paper", page=1)

    with pytest.raises(TypeError, match="displayed_precision"):
        ExtractedField("1.0", 1.0, source, 1.0, displayed_precision=True)
    with pytest.raises(ValueError, match="displayed_precision"):
        ExtractedField("1.0", 1.0, source, 1.0, displayed_precision=-1)
    with pytest.raises(TypeError, match="comparison_operator"):
        ExtractedField("p < .05", 0.05, source, 1.0, comparison_operator="<")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="identity_confidence"):
        ExtractedField("1.0", 1.0, source, 1.0, identity_confidence=1.01)


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
