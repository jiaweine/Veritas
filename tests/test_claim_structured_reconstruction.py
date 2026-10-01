from __future__ import annotations

import pytest

from veritas.claim_reconstruction import (
    ClaimObjectReconstructionError,
    reconstruct_statistical_object,
)
from veritas.claims import ArtifactRef, ExtractedField, StatisticalClaimGraph, StatisticalObjectNode
from veritas.detectors.correlation import CorrelationPSDDetector
from veritas.detectors.sample import SampleAccountingDetector
from veritas.models import CorrelationMatrix, SamplePartition, SourceLocation
from veritas.types import CheckStatus, ComparisonOperator


def _field(
    raw: str,
    value,
    *,
    row: str | None = None,
    column: str | None = None,
    precision: int | None = None,
    operator: ComparisonOperator | None = None,
) -> ExtractedField:
    return ExtractedField(
        raw=raw,
        value=value,
        source=SourceLocation(
            artifact_id="paper",
            page=3,
            table="Table 2",
            row=row,
            column=column,
        ),
        extraction_confidence=0.98,
        displayed_precision=precision,
        comparison_operator=operator,
        identity_confidence=0.96,
    )


def test_sample_partition_reconstructs_from_scalar_source_addressable_fields() -> None:
    graph = StatisticalClaimGraph()
    graph.add_artifact(ArtifactRef("paper", "pdf"))
    graph.add_object(
        StatisticalObjectNode(
            object_id="sample-1",
            object_type="SamplePartition",
            fields={
                "total_n": _field("100", 100, row="Total"),
                "group_count:treated": _field("50", 50, row="Treated"),
                "group_count:control": _field("50", 50, row="Control"),
                "exhaustive": _field("yes", True),
                "non_overlapping": _field("yes", True),
                "explanation_present": _field("no", False),
            },
            source=SourceLocation(artifact_id="paper", page=3, table="Table 2"),
        )
    )

    restored = StatisticalClaimGraph.from_json(graph.to_json())
    reconstructed = reconstruct_statistical_object(restored, "sample-1")

    assert isinstance(reconstructed, SamplePartition)
    assert reconstructed.total_n == 100
    assert reconstructed.groups == {"treated": 50, "control": 50}
    assert reconstructed.exhaustive is True
    assert reconstructed.non_overlapping is True
    checks = SampleAccountingDetector().run(reconstructed)
    assert checks[0].status is CheckStatus.PASS


def test_sample_partition_requires_explicit_overlap_semantics_when_groups_exist() -> None:
    graph = StatisticalClaimGraph()
    graph.add_artifact(ArtifactRef("paper", "pdf"))
    graph.add_object(
        StatisticalObjectNode(
            object_id="sample-1",
            object_type="SamplePartition",
            fields={
                "total_n": _field("100", 100),
                "group_count:treated": _field("60", 60),
                "group_count:control": _field("60", 60),
            },
            source=SourceLocation(artifact_id="paper", page=3),
        )
    )

    with pytest.raises(ClaimObjectReconstructionError, match="non_overlapping"):
        reconstruct_statistical_object(graph, "sample-1")


def test_sample_partition_rejects_negative_group_count() -> None:
    graph = StatisticalClaimGraph()
    graph.add_artifact(ArtifactRef("paper", "pdf"))
    graph.add_object(
        StatisticalObjectNode(
            object_id="sample-1",
            object_type="SamplePartition",
            fields={
                "group_count:treated": _field("-1", -1),
                "non_overlapping": _field("yes", True),
            },
            source=SourceLocation(artifact_id="paper", page=3),
        )
    )

    with pytest.raises(ClaimObjectReconstructionError, match="non-negative"):
        reconstruct_statistical_object(graph, "sample-1")


def _correlation_graph() -> StatisticalClaimGraph:
    graph = StatisticalClaimGraph()
    graph.add_artifact(ArtifactRef("paper", "pdf"))
    graph.add_object(
        StatisticalObjectNode(
            object_id="corr-1",
            object_type="CorrelationMatrix",
            fields={
                "label:0": _field("Employment", "Employment", row="Employment"),
                "label:1": _field("Wage", "Wage", row="Wage"),
                "cell:0:0": _field(
                    "1.00",
                    1.0,
                    row="Employment",
                    column="Employment",
                    precision=2,
                    operator=ComparisonOperator.EQ,
                ),
                "cell:0:1": _field(
                    "0.20",
                    0.2,
                    row="Employment",
                    column="Wage",
                    precision=2,
                    operator=ComparisonOperator.EQ,
                ),
                "cell:1:1": _field(
                    "1.00",
                    1.0,
                    row="Wage",
                    column="Wage",
                    precision=2,
                    operator=ComparisonOperator.EQ,
                ),
            },
            source=SourceLocation(artifact_id="paper", page=3, table="Table 2"),
        )
    )
    return graph


def test_correlation_matrix_reconstructs_after_json_round_trip() -> None:
    graph = StatisticalClaimGraph.from_json(_correlation_graph().to_json())

    reconstructed = reconstruct_statistical_object(graph, "corr-1")

    assert isinstance(reconstructed, CorrelationMatrix)
    assert reconstructed.labels == ("Employment", "Wage")
    assert reconstructed.cells[0][1] is not None
    assert reconstructed.cells[0][1].value == 0.2
    assert reconstructed.cells[0][1].decimals == 2
    assert reconstructed.cells[1][0] is None
    checks = CorrelationPSDDetector().run(reconstructed)
    assert checks[0].status is CheckStatus.PASS


def test_correlation_matrix_rejects_noncontiguous_label_indexes() -> None:
    graph = StatisticalClaimGraph()
    graph.add_artifact(ArtifactRef("paper", "pdf"))
    graph.add_object(
        StatisticalObjectNode(
            object_id="corr-1",
            object_type="CorrelationMatrix",
            fields={
                "label:0": _field("A", "A"),
                "label:2": _field("B", "B"),
            },
            source=SourceLocation(artifact_id="paper", page=3),
        )
    )

    with pytest.raises(ClaimObjectReconstructionError, match="contiguous"):
        reconstruct_statistical_object(graph, "corr-1")


def test_correlation_matrix_rejects_cell_outside_declared_labels() -> None:
    graph = _correlation_graph()
    node = graph.objects["corr-1"]
    node.fields["cell:0:2"] = _field(
        "0.10",
        0.1,
        precision=2,
        operator=ComparisonOperator.EQ,
    )

    with pytest.raises(ClaimObjectReconstructionError, match="outside matrix"):
        reconstruct_statistical_object(graph, "corr-1")
