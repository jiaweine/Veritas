from __future__ import annotations

import pytest

from veritas.claim_identity import (
    ScaleTransformation,
    add_claim_estimate_candidate,
    build_claim_estimate_alignment,
    compare_estimand_identity,
    link_empirical_evidence_chain,
    normalize_estimand_identity,
    normalize_scale_transformation,
    require_cross_location_e3_identity,
)
from veritas.claims import (
    ArtifactRef,
    ClaimNode,
    ClaimRole,
    EvidenceNode,
    EvidenceNodeKind,
    ExtractedField,
    RelationType,
    StatisticalClaimGraph,
    StatisticalObjectNode,
)
from veritas.models import SourceLocation


def _graph(*, estimate_confidence: float = 0.98) -> StatisticalClaimGraph:
    graph = StatisticalClaimGraph()
    graph.add_artifact(ArtifactRef("paper", "pdf", sha256="a" * 64))
    graph.add_artifact(ArtifactRef("data-artifact", "csv", sha256="b" * 64))
    graph.add_artifact(ArtifactRef("code-artifact", "python", sha256="c" * 64))
    graph.add_claim(
        ClaimNode(
            "claim-main",
            "Treatment increased employment by 4 percentage points.",
            ClaimRole.PRIMARY,
            SourceLocation(
                artifact_id="paper",
                page=2,
                section="Abstract",
                char_start=120,
                char_end=176,
                text_quote="increased employment by 4 percentage points",
            ),
            extraction_confidence=0.98,
            identity_confidence=0.97,
        )
    )
    graph.add_object(
        StatisticalObjectNode(
            object_id="estimate-main",
            object_type="RegressionResult",
            fields={
                "beta": ExtractedField(
                    raw="0.040",
                    value=0.04,
                    source=SourceLocation(
                        artifact_id="paper",
                        page=8,
                        table="Table 3",
                        row="Treatment",
                        column="Employment",
                    ),
                    extraction_confidence=estimate_confidence,
                )
            },
            source=SourceLocation(artifact_id="paper", page=8, table="Table 3"),
        )
    )
    graph.add_evidence_node(
        EvidenceNode(
            "sample-main",
            EvidenceNodeKind.SAMPLE,
            "analysis sample",
            SourceLocation(artifact_id="paper", page=5, section="Data"),
            {"n": 1200},
            extraction_confidence=0.97,
        )
    )
    graph.add_evidence_node(
        EvidenceNode(
            "data-main",
            EvidenceNodeKind.DATA,
            "analysis dataset",
            SourceLocation(artifact_id="data-artifact"),
            {"dataset": "analysis.csv"},
            extraction_confidence=1.0,
        )
    )
    graph.add_evidence_node(
        EvidenceNode(
            "code-main",
            EvidenceNodeKind.CODE,
            "estimation script",
            SourceLocation(artifact_id="code-artifact"),
            {"entrypoint": "analysis.py"},
            extraction_confidence=1.0,
        )
    )
    graph.add_evidence_node(
        EvidenceNode(
            "assumption-parallel",
            EvidenceNodeKind.ASSUMPTION,
            "parallel trends",
            SourceLocation(artifact_id="paper", page=4, section="Identification"),
            extraction_confidence=0.95,
        )
    )
    return graph


def test_scale_normalization_distinguishes_percent_and_percentage_points() -> None:
    assert normalize_scale_transformation("percentage points") is ScaleTransformation.PERCENTAGE_POINT
    assert normalize_scale_transformation("%") is ScaleTransformation.PERCENT


def test_core_estimand_identity_is_high_confidence_without_optional_metadata() -> None:
    claim = normalize_estimand_identity(
        outcome="Employment",
        treatment="Program assignment",
        transformation="percentage points",
    )
    estimate = normalize_estimand_identity(
        outcome="employment",
        treatment="program assignment",
        transformation="pp",
    )

    match = compare_estimand_identity(claim, estimate)

    assert match.exact_core_identity is True
    assert match.confidence == 0.90
    assert match.conflicting_dimensions == ()
    assert set(match.unresolved_dimensions) == {"population", "time_horizon"}


def test_scale_mismatch_blocks_cross_location_e3() -> None:
    graph = _graph()
    alignment = build_claim_estimate_alignment(
        graph,
        claim_id="claim-main",
        estimate_object_id="estimate-main",
        claim_identity=normalize_estimand_identity(
            outcome="employment",
            treatment="program assignment",
            transformation="percentage points",
        ),
        estimate_identity=normalize_estimand_identity(
            outcome="employment",
            treatment="program assignment",
            transformation="percent",
        ),
    )

    assert "transformation" in alignment.identity_match.conflicting_dimensions
    with pytest.raises(ValueError, match="high-confidence claim/estimand identity"):
        require_cross_location_e3_identity(alignment)


def test_low_extraction_confidence_blocks_cross_location_e3() -> None:
    graph = _graph(estimate_confidence=0.72)
    identity = normalize_estimand_identity(
        outcome="employment",
        treatment="program assignment",
        transformation="percentage points",
    )
    alignment = build_claim_estimate_alignment(
        graph,
        claim_id="claim-main",
        estimate_object_id="estimate-main",
        claim_identity=identity,
        estimate_identity=identity,
    )

    assert alignment.identity_match.confidence == 1.0 - 0.10
    assert alignment.effective_confidence == 0.72
    with pytest.raises(ValueError, match="high-confidence claim/estimand identity"):
        require_cross_location_e3_identity(alignment)


def test_claim_candidate_edge_propagates_sources_and_uncertainty() -> None:
    graph = _graph()
    identity = normalize_estimand_identity(
        outcome="employment",
        treatment="program assignment",
        transformation="percentage points",
    )
    alignment = build_claim_estimate_alignment(
        graph,
        claim_id="claim-main",
        estimate_object_id="estimate-main",
        claim_identity=identity,
        estimate_identity=identity,
        matcher_confidence=0.96,
    )

    require_cross_location_e3_identity(alignment)
    edge = add_claim_estimate_candidate(graph, alignment)

    assert edge.relation is RelationType.REPORTS
    assert edge.effective_confidence == 0.90
    assert [source.page for source in edge.sources] == [2, 8]


def test_empirical_evidence_chain_round_trip_preserves_provenance() -> None:
    graph = _graph()
    links = link_empirical_evidence_chain(
        graph,
        estimate_object_id="estimate-main",
        sample_id="sample-main",
        data_id="data-main",
        code_id="code-main",
        assumption_ids=("assumption-parallel",),
    )

    assert [edge.relation for edge in links] == [
        RelationType.USES_SAMPLE,
        RelationType.DERIVED_FROM,
        RelationType.GENERATED_BY,
        RelationType.REQUIRES_ASSUMPTION,
    ]
    restored = StatisticalClaimGraph.from_json(graph.to_json())
    assert restored.evidence_nodes["sample-main"].attributes["n"] == 1200
    assert restored.edges[-1].sources[-1].section == "Identification"


def test_evidence_chain_rejects_wrong_node_kind() -> None:
    graph = _graph()
    with pytest.raises(ValueError, match="must have kind 'sample'"):
        link_empirical_evidence_chain(
            graph,
            estimate_object_id="estimate-main",
            sample_id="data-main",
            data_id="sample-main",
            code_id="code-main",
        )
