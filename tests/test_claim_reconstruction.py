from __future__ import annotations

import pytest

from veritas.claim_reconstruction import (
    ClaimObjectReconstructionError,
    reconstruct_regression_result,
    reconstruct_statistical_object,
)
from veritas.claims import ArtifactRef, ExtractedField, StatisticalClaimGraph, StatisticalObjectNode
from veritas.detectors.regression import RegressionConsistencyDetector
from veritas.models import RegressionResult, SourceLocation
from veritas.types import CheckStatus, ComparisonOperator


def _field(
    raw: str,
    value,
    *,
    page: int = 4,
    precision: int | None = None,
    operator: ComparisonOperator | None = None,
) -> ExtractedField:
    return ExtractedField(
        raw=raw,
        value=value,
        source=SourceLocation(
            artifact_id="paper",
            page=page,
            table="Table 4",
            row="Minimum wage",
        ),
        extraction_confidence=0.98,
        displayed_precision=precision,
        comparison_operator=operator,
        identity_confidence=0.97,
    )


def _graph() -> StatisticalClaimGraph:
    graph = StatisticalClaimGraph()
    graph.add_artifact(ArtifactRef("paper", "pdf", sha256="a" * 64))
    graph.add_object(
        StatisticalObjectNode(
            object_id="reg-1",
            object_type="RegressionResult",
            fields={
                "beta": _field("-0.021", -0.021, precision=3, operator=ComparisonOperator.EQ),
                "se": _field("0.026", 0.026, precision=3, operator=ComparisonOperator.EQ),
                "t_stat": _field("-0.808", -0.808, precision=3, operator=ComparisonOperator.EQ),
                "p_value": _field("0.419", 0.419, precision=3, operator=ComparisonOperator.EQ),
                "inference_distribution": _field("normal", "normal"),
                "p_value_adjusted": _field("false", False),
            },
            source=SourceLocation(
                artifact_id="paper",
                page=4,
                table="Table 4",
                row="Minimum wage",
            ),
        )
    )
    return graph


def test_regression_reconstruction_survives_graph_json_without_parser_state() -> None:
    graph = StatisticalClaimGraph.from_json(_graph().to_json())

    reconstructed = reconstruct_statistical_object(graph, "reg-1")

    assert isinstance(reconstructed, RegressionResult)
    assert reconstructed.beta.value == -0.021
    assert reconstructed.beta.decimals == 3
    assert reconstructed.beta.operator is ComparisonOperator.EQ
    assert reconstructed.se is not None and reconstructed.se.value == 0.026
    assert reconstructed.t_stat is not None and reconstructed.t_stat.value == -0.808
    assert reconstructed.p_value is not None and reconstructed.p_value.value == 0.419
    assert reconstructed.inference_distribution == "normal"
    assert reconstructed.p_value_adjusted is False
    assert reconstructed.source.table == "Table 4"

    checks = RegressionConsistencyDetector().run(reconstructed)
    by_id = {check.check_id: check for check in checks}
    assert by_id["beta_se_t"].status is CheckStatus.PASS
    assert by_id["p_value"].status is CheckStatus.PASS
    assert by_id["confidence_interval"].status is CheckStatus.NOT_RELEVANT


def test_reconstruction_preserves_explicit_p_value_comparison_operator() -> None:
    graph = _graph()
    node = graph.objects["reg-1"]
    node.fields["p_value"] = _field(
        "p < 0.050",
        0.05,
        precision=3,
        operator=ComparisonOperator.LT,
    )

    reconstructed = reconstruct_regression_result(node)

    assert reconstructed.p_value is not None
    assert reconstructed.p_value.operator is ComparisonOperator.LT
    assert reconstructed.p_value.decimals == 3


def test_reconstruction_fails_closed_without_numeric_operator() -> None:
    graph = _graph()
    node = graph.objects["reg-1"]
    node.fields["beta"] = _field("-0.021", -0.021, precision=3)

    with pytest.raises(ClaimObjectReconstructionError, match="comparison_operator"):
        reconstruct_regression_result(node)


def test_reconstruction_fails_closed_when_reported_p_lacks_inference_metadata() -> None:
    graph = _graph()
    node = graph.objects["reg-1"]
    del node.fields["inference_distribution"]

    with pytest.raises(ClaimObjectReconstructionError, match="inference_distribution"):
        reconstruct_regression_result(node)


def test_reconstruction_fails_closed_when_p_adjustment_status_is_unknown() -> None:
    graph = _graph()
    node = graph.objects["reg-1"]
    del node.fields["p_value_adjusted"]

    with pytest.raises(ClaimObjectReconstructionError, match="p_value_adjusted"):
        reconstruct_regression_result(node)


def test_confidence_interval_requires_explicit_level() -> None:
    graph = _graph()
    node = graph.objects["reg-1"]
    node.fields["ci_lower"] = _field("-0.072", -0.072, precision=3, operator=ComparisonOperator.EQ)
    node.fields["ci_upper"] = _field("0.030", 0.030, precision=3, operator=ComparisonOperator.EQ)

    with pytest.raises(ClaimObjectReconstructionError, match="ci_level"):
        reconstruct_regression_result(node)


def test_unsupported_graph_object_type_is_not_guessed() -> None:
    graph = StatisticalClaimGraph()
    graph.add_artifact(ArtifactRef("paper", "pdf"))
    graph.add_object(
        StatisticalObjectNode(
            object_id="sample-1",
            object_type="SamplePartition",
            fields={},
            source=SourceLocation(artifact_id="paper", page=2),
        )
    )

    with pytest.raises(ClaimObjectReconstructionError, match="unsupported statistical object type"):
        reconstruct_statistical_object(graph, "sample-1")
