from __future__ import annotations

import pytest

from veritas.claim_reconstruction import (
    ClaimObjectReconstructionError,
    reconstruct_statistical_object,
)
from veritas.claims import ArtifactRef, ExtractedField, StatisticalClaimGraph, StatisticalObjectNode
from veritas.detectors.standardized_regression import StandardizedRegressionReconstructionDetector
from veritas.models import SourceLocation, StandardizedRegressionReconstruction
from veritas.types import CheckStatus, ComparisonOperator


def _field(
    raw: str,
    value,
    *,
    precision: int | None = None,
    operator: ComparisonOperator | None = None,
) -> ExtractedField:
    return ExtractedField(
        raw=raw,
        value=value,
        source=SourceLocation(artifact_id="paper", page=7, table="Table 5"),
        extraction_confidence=0.98,
        displayed_precision=precision,
        comparison_operator=operator,
        identity_confidence=0.97,
    )


def _graph(*, include_same_sample: bool = True) -> StatisticalClaimGraph:
    graph = StatisticalClaimGraph()
    graph.add_artifact(ArtifactRef("paper", "pdf", sha256="a" * 64))
    graph.add_object(
        StatisticalObjectNode(
            object_id="corr-1",
            object_type="CorrelationMatrix",
            fields={
                "label:0": _field("X", "X"),
                "label:1": _field("Y", "Y"),
                "cell:0:1": _field("0.500", 0.5, precision=3, operator=ComparisonOperator.EQ),
                "cell:1:0": _field("0.500", 0.5, precision=3, operator=ComparisonOperator.EQ),
            },
            source=SourceLocation(artifact_id="paper", page=6, table="Table 4"),
        )
    )
    fields = {
        "correlation_matrix_object_id": _field("corr-1", "corr-1"),
        "outcome": _field("Y", "Y"),
        "predictor:0": _field("X", "X"),
        "standardized_beta:0": _field(
            "0.500",
            0.5,
            precision=3,
            operator=ComparisonOperator.EQ,
        ),
        "ols_identity_verified": _field("true", True),
        "same_sample_verified": _field("true", True),
        "complete_predictor_set_verified": _field("true", True),
    }
    if not include_same_sample:
        del fields["same_sample_verified"]
    graph.add_object(
        StatisticalObjectNode(
            object_id="std-1",
            object_type="StandardizedRegressionReconstruction",
            fields=fields,
            source=SourceLocation(artifact_id="paper", page=7, table="Table 5"),
        )
    )
    return StatisticalClaimGraph.from_json(graph.to_json())


def test_standardized_regression_round_trip_resolves_graph_correlation_reference() -> None:
    reconstructed = reconstruct_statistical_object(_graph(), "std-1")

    assert isinstance(reconstructed, StandardizedRegressionReconstruction)
    assert reconstructed.correlation_matrix.object_id == "corr-1"
    assert reconstructed.correlation_matrix.labels == ("X", "Y")
    assert reconstructed.outcome == "Y"
    assert reconstructed.predictors == ("X",)
    assert reconstructed.standardized_betas[0].value == 0.5
    assert reconstructed.standardized_betas[0].decimals == 3
    assert reconstructed.ols_identity_verified is True
    assert reconstructed.same_sample_verified is True
    assert reconstructed.complete_predictor_set_verified is True

    check = StandardizedRegressionReconstructionDetector().run(reconstructed)[0]
    assert check.status is CheckStatus.PASS


def test_standardized_regression_missing_applicability_gate_fails_closed() -> None:
    with pytest.raises(ClaimObjectReconstructionError, match="same_sample_verified"):
        reconstruct_statistical_object(_graph(include_same_sample=False), "std-1")


def test_standardized_regression_rejects_unknown_correlation_object_reference() -> None:
    graph = _graph()
    graph.objects["std-1"].fields["correlation_matrix_object_id"] = _field(
        "missing",
        "missing",
    )

    with pytest.raises(ClaimObjectReconstructionError, match="unknown correlation matrix"):
        reconstruct_statistical_object(graph, "std-1")


def test_standardized_regression_requires_matching_predictor_and_beta_indexes() -> None:
    graph = _graph()
    graph.objects["std-1"].fields["predictor:1"] = _field("Z", "Z")

    with pytest.raises(ClaimObjectReconstructionError, match="predictor indexes"):
        reconstruct_statistical_object(graph, "std-1")


def test_standardized_regression_beta_requires_explicit_display_operator() -> None:
    graph = _graph()
    graph.objects["std-1"].fields["standardized_beta:0"] = _field(
        "0.500",
        0.5,
        precision=3,
    )

    with pytest.raises(ClaimObjectReconstructionError, match="comparison_operator"):
        reconstruct_statistical_object(graph, "std-1")


def test_standardized_regression_reference_must_point_to_correlation_matrix() -> None:
    graph = _graph()
    graph.add_object(
        StatisticalObjectNode(
            object_id="not-corr",
            object_type="SamplePartition",
            fields={},
            source=SourceLocation(artifact_id="paper", page=3),
        )
    )
    graph.objects["std-1"].fields["correlation_matrix_object_id"] = _field(
        "not-corr",
        "not-corr",
    )

    with pytest.raises(ClaimObjectReconstructionError, match="expected CorrelationMatrix"):
        reconstruct_statistical_object(graph, "std-1")
