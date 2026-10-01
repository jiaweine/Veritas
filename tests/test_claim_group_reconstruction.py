from __future__ import annotations

import pytest

from veritas.claim_reconstruction import (
    ClaimObjectReconstructionError,
    reconstruct_statistical_object,
)
from veritas.claims import ArtifactRef, ExtractedField, StatisticalClaimGraph, StatisticalObjectNode
from veritas.detectors.group_stats import TwoGroupSummaryDetector
from veritas.group_stats import GroupSummary, TwoGroupComparison
from veritas.models import SourceLocation
from veritas.types import CheckStatus, ComparisonOperator


def _field(
    raw: str,
    value,
    *,
    row: str | None = None,
    precision: int | None = None,
    operator: ComparisonOperator | None = None,
) -> ExtractedField:
    return ExtractedField(
        raw=raw,
        value=value,
        source=SourceLocation(
            artifact_id="paper",
            page=6,
            table="Table 3",
            row=row,
        ),
        extraction_confidence=0.98,
        displayed_precision=precision,
        comparison_operator=operator,
        identity_confidence=0.97,
    )


def test_mean_sd_reconstructs_after_graph_json_round_trip() -> None:
    graph = StatisticalClaimGraph()
    graph.add_artifact(ArtifactRef("paper", "pdf"))
    graph.add_object(
        StatisticalObjectNode(
            object_id="mean-sd-1",
            object_type="MeanSD",
            fields={
                "label": _field("Treatment", "Treatment", row="Treatment"),
                "n": _field("50", 50, row="Treatment"),
                "mean": _field(
                    "10.00",
                    10.0,
                    row="Treatment",
                    precision=2,
                    operator=ComparisonOperator.EQ,
                ),
                "sd": _field(
                    "2.00",
                    2.0,
                    row="Treatment",
                    precision=2,
                    operator=ComparisonOperator.EQ,
                ),
                "sd_definition": _field("sample", "sample", row="Treatment"),
                "weighted": _field("no", False, row="Treatment"),
            },
            source=SourceLocation(artifact_id="paper", page=6, table="Table 3"),
        )
    )

    restored = StatisticalClaimGraph.from_json(graph.to_json())
    reconstructed = reconstruct_statistical_object(restored, "mean-sd-1")

    assert isinstance(reconstructed, GroupSummary)
    assert reconstructed.label == "Treatment"
    assert reconstructed.n == 50
    assert reconstructed.mean.value == 10.0
    assert reconstructed.mean.decimals == 2
    assert reconstructed.mean.operator is ComparisonOperator.EQ
    assert reconstructed.sd.value == 2.0
    assert reconstructed.sd_definition == "sample"
    assert reconstructed.weighted is False


def _group_comparison_graph(*, include_p: bool = False) -> StatisticalClaimGraph:
    fields = {
        "group_a:label": _field("Treatment", "Treatment", row="Treatment"),
        "group_a:n": _field("50", 50, row="Treatment"),
        "group_a:mean": _field(
            "10.00",
            10.0,
            row="Treatment",
            precision=2,
            operator=ComparisonOperator.EQ,
        ),
        "group_a:sd": _field(
            "2.00",
            2.0,
            row="Treatment",
            precision=2,
            operator=ComparisonOperator.EQ,
        ),
        "group_a:sd_definition": _field("sample", "sample", row="Treatment"),
        "group_a:weighted": _field("no", False, row="Treatment"),
        "group_b:label": _field("Control", "Control", row="Control"),
        "group_b:n": _field("50", 50, row="Control"),
        "group_b:mean": _field(
            "8.00",
            8.0,
            row="Control",
            precision=2,
            operator=ComparisonOperator.EQ,
        ),
        "group_b:sd": _field(
            "2.00",
            2.0,
            row="Control",
            precision=2,
            operator=ComparisonOperator.EQ,
        ),
        "group_b:sd_definition": _field("sample", "sample", row="Control"),
        "group_b:weighted": _field("no", False, row="Control"),
        "reported_mean_difference": _field(
            "2.00",
            2.0,
            precision=2,
            operator=ComparisonOperator.EQ,
        ),
        "reported_t": _field("5.00", 5.0, precision=2, operator=ComparisonOperator.EQ),
        "reported_df": _field("98", 98.0, precision=0, operator=ComparisonOperator.EQ),
        "test_definition": _field("student_equal_var", "student_equal_var"),
        "independent_groups_verified": _field("yes", True),
        "same_outcome_scale_verified": _field("yes", True),
        "difference_direction_verified": _field("yes", True),
        "pooled_sd_effect_size_verified": _field("no", False),
    }
    if include_p:
        fields["reported_p_value"] = _field(
            "0.000002",
            0.000002,
            precision=6,
            operator=ComparisonOperator.EQ,
        )

    graph = StatisticalClaimGraph()
    graph.add_artifact(ArtifactRef("paper", "pdf"))
    graph.add_object(
        StatisticalObjectNode(
            object_id="groups-1",
            object_type="GroupComparison",
            fields=fields,
            source=SourceLocation(artifact_id="paper", page=6, table="Table 3"),
        )
    )
    return graph


def test_group_comparison_reconstructs_and_runs_existing_detector() -> None:
    graph = StatisticalClaimGraph.from_json(_group_comparison_graph().to_json())

    reconstructed = reconstruct_statistical_object(graph, "groups-1")

    assert isinstance(reconstructed, TwoGroupComparison)
    assert reconstructed.group_a.label == "Treatment"
    assert reconstructed.group_b.label == "Control"
    assert reconstructed.test_definition == "student_equal_var"
    assert reconstructed.independent_groups_verified is True
    assert reconstructed.same_outcome_scale_verified is True
    assert reconstructed.difference_direction_verified is True

    checks = TwoGroupSummaryDetector().run(reconstructed)
    by_id = {check.check_id: check for check in checks}
    assert by_id["mean_difference"].status is CheckStatus.PASS
    assert by_id["t_statistic"].status is CheckStatus.PASS
    assert by_id["degrees_of_freedom"].status is CheckStatus.PASS


def test_group_comparison_missing_verification_semantics_downgrades_safely() -> None:
    graph = _group_comparison_graph()
    node = graph.objects["groups-1"]
    del node.fields["independent_groups_verified"]

    reconstructed = reconstruct_statistical_object(graph, "groups-1")
    assert isinstance(reconstructed, TwoGroupComparison)
    assert reconstructed.independent_groups_verified is False

    checks = TwoGroupSummaryDetector().run(reconstructed)
    assert len(checks) == 1
    assert checks[0].status is CheckStatus.UNVERIFIABLE


def test_group_comparison_reported_p_requires_explicit_adjustment_status() -> None:
    graph = _group_comparison_graph(include_p=True)

    with pytest.raises(ClaimObjectReconstructionError, match="p_value_adjusted"):
        reconstruct_statistical_object(graph, "groups-1")


def test_group_comparison_rejects_missing_numeric_operator() -> None:
    graph = _group_comparison_graph()
    node = graph.objects["groups-1"]
    node.fields["group_a:mean"] = _field("10.00", 10.0, precision=2)

    with pytest.raises(ClaimObjectReconstructionError, match="comparison_operator"):
        reconstruct_statistical_object(graph, "groups-1")


def test_mean_sd_rejects_invalid_group_constraints() -> None:
    graph = StatisticalClaimGraph()
    graph.add_artifact(ArtifactRef("paper", "pdf"))
    graph.add_object(
        StatisticalObjectNode(
            object_id="mean-sd-1",
            object_type="MeanSD",
            fields={
                "label": _field("Treatment", "Treatment"),
                "n": _field("1", 1),
                "mean": _field("10.0", 10.0, precision=1, operator=ComparisonOperator.EQ),
                "sd": _field("-1.0", -1.0, precision=1, operator=ComparisonOperator.EQ),
            },
            source=SourceLocation(artifact_id="paper", page=6),
        )
    )

    with pytest.raises(ClaimObjectReconstructionError, match="at least 2"):
        reconstruct_statistical_object(graph, "mean-sd-1")
