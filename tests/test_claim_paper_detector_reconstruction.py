from __future__ import annotations

import pytest

from veritas.claim_reconstruction import (
    ClaimObjectReconstructionError,
    reconstruct_statistical_object,
)
from veritas.claims import ArtifactRef, ExtractedField, StatisticalClaimGraph, StatisticalObjectNode
from veritas.detectors.algebra import LogitOddsRatioDetector, MediationProductDetector
from veritas.detectors.discrete import DiscreteSummaryFeasibilityDetector
from veritas.models import DiscreteSummary, LogitResult, MediationResult, SourceLocation
from veritas.types import CheckStatus, ComparisonOperator


def _field(
    raw: str,
    value,
    *,
    precision: int | None = None,
    operator: ComparisonOperator | None = None,
    row: str = "Result",
) -> ExtractedField:
    return ExtractedField(
        raw=raw,
        value=value,
        source=SourceLocation(
            artifact_id="paper",
            page=4,
            table="Table 2",
            row=row,
        ),
        extraction_confidence=0.98,
        displayed_precision=precision,
        comparison_operator=operator,
        identity_confidence=0.97,
    )


def _graph(node: StatisticalObjectNode) -> StatisticalClaimGraph:
    graph = StatisticalClaimGraph()
    graph.add_artifact(ArtifactRef("paper", "pdf", sha256="a" * 64))
    graph.add_object(node)
    return StatisticalClaimGraph.from_json(graph.to_json())


def test_logit_reconstruction_round_trip_runs_deterministic_detector() -> None:
    graph = _graph(
        StatisticalObjectNode(
            object_id="logit-1",
            object_type="LogitResult",
            fields={
                "beta": _field("0.693", 0.693, precision=3, operator=ComparisonOperator.EQ),
                "odds_ratio": _field("2.00", 2.0, precision=2, operator=ComparisonOperator.EQ),
                "exp_beta_relation_verified": _field("true", True),
            },
            source=SourceLocation(artifact_id="paper", page=4, table="Table 2"),
        )
    )

    reconstructed = reconstruct_statistical_object(graph, "logit-1")

    assert isinstance(reconstructed, LogitResult)
    assert reconstructed.beta.decimals == 3
    assert reconstructed.odds_ratio.decimals == 2
    assert reconstructed.exp_beta_relation_verified is True
    check = LogitOddsRatioDetector().run(reconstructed)[0]
    assert check.status is CheckStatus.PASS


def test_mediation_reconstruction_round_trip_runs_deterministic_detector() -> None:
    graph = _graph(
        StatisticalObjectNode(
            object_id="med-1",
            object_type="MediationResult",
            fields={
                "a_path": _field("0.20", 0.2, precision=2, operator=ComparisonOperator.EQ),
                "b_path": _field("0.30", 0.3, precision=2, operator=ComparisonOperator.EQ),
                "indirect_effect": _field(
                    "0.060",
                    0.06,
                    precision=3,
                    operator=ComparisonOperator.EQ,
                ),
                "product_definition_verified": _field("true", True),
                "scale_consistent_verified": _field("true", True),
            },
            source=SourceLocation(artifact_id="paper", page=5, table="Table 3"),
        )
    )

    reconstructed = reconstruct_statistical_object(graph, "med-1")

    assert isinstance(reconstructed, MediationResult)
    assert reconstructed.product_definition_verified is True
    assert reconstructed.scale_consistent_verified is True
    check = MediationProductDetector().run(reconstructed)[0]
    assert check.status is CheckStatus.PASS


def test_discrete_summary_round_trip_runs_finite_support_detector() -> None:
    graph = _graph(
        StatisticalObjectNode(
            object_id="disc-1",
            object_type="DiscreteSummary",
            fields={
                "n": _field("4", 4),
                "mean": _field("1.50", 1.5, precision=2, operator=ComparisonOperator.EQ),
                "support:0": _field("1", 1.0),
                "support:1": _field("2", 2.0),
                "support_verified": _field("true", True),
                "n_verified": _field("true", True),
                "weighted": _field("false", False),
            },
            source=SourceLocation(artifact_id="paper", page=6, table="Table 4"),
        )
    )

    reconstructed = reconstruct_statistical_object(graph, "disc-1")

    assert isinstance(reconstructed, DiscreteSummary)
    assert reconstructed.n == 4
    assert reconstructed.support == (1.0, 2.0)
    assert reconstructed.mean.decimals == 2
    assert reconstructed.support_verified is True
    assert reconstructed.n_verified is True
    assert reconstructed.weighted is False
    check = DiscreteSummaryFeasibilityDetector().run(reconstructed)[0]
    assert check.status is CheckStatus.PASS


@pytest.mark.parametrize(
    ("object_type", "missing_field"),
    [
        ("LogitResult", "exp_beta_relation_verified"),
        ("MediationResult", "scale_consistent_verified"),
        ("DiscreteSummary", "support_verified"),
        ("DiscreteSummary", "n_verified"),
        ("DiscreteSummary", "weighted"),
    ],
)
def test_reconstruction_fails_closed_when_detector_gate_is_missing(
    object_type: str,
    missing_field: str,
) -> None:
    if object_type == "LogitResult":
        fields = {
            "beta": _field("0.693", 0.693, precision=3, operator=ComparisonOperator.EQ),
            "odds_ratio": _field("2.00", 2.0, precision=2, operator=ComparisonOperator.EQ),
            "exp_beta_relation_verified": _field("true", True),
        }
    elif object_type == "MediationResult":
        fields = {
            "a_path": _field("0.20", 0.2, precision=2, operator=ComparisonOperator.EQ),
            "b_path": _field("0.30", 0.3, precision=2, operator=ComparisonOperator.EQ),
            "indirect_effect": _field("0.060", 0.06, precision=3, operator=ComparisonOperator.EQ),
            "product_definition_verified": _field("true", True),
            "scale_consistent_verified": _field("true", True),
        }
    else:
        fields = {
            "n": _field("4", 4),
            "mean": _field("1.50", 1.5, precision=2, operator=ComparisonOperator.EQ),
            "support:0": _field("1", 1.0),
            "support:1": _field("2", 2.0),
            "support_verified": _field("true", True),
            "n_verified": _field("true", True),
            "weighted": _field("false", False),
        }
    del fields[missing_field]
    graph = _graph(
        StatisticalObjectNode(
            object_id="obj-1",
            object_type=object_type,
            fields=fields,
            source=SourceLocation(artifact_id="paper", page=4),
        )
    )

    with pytest.raises(ClaimObjectReconstructionError, match=missing_field):
        reconstruct_statistical_object(graph, "obj-1")


def test_discrete_summary_rejects_noncontiguous_support_indexes() -> None:
    graph = _graph(
        StatisticalObjectNode(
            object_id="disc-gap",
            object_type="DiscreteSummary",
            fields={
                "n": _field("4", 4),
                "mean": _field("1.50", 1.5, precision=2, operator=ComparisonOperator.EQ),
                "support:0": _field("1", 1.0),
                "support:2": _field("2", 2.0),
                "support_verified": _field("true", True),
                "n_verified": _field("true", True),
                "weighted": _field("false", False),
            },
            source=SourceLocation(artifact_id="paper", page=6),
        )
    )

    with pytest.raises(ClaimObjectReconstructionError, match="support indexes"):
        reconstruct_statistical_object(graph, "disc-gap")


def test_logit_reported_numbers_still_require_explicit_display_operator() -> None:
    graph = _graph(
        StatisticalObjectNode(
            object_id="logit-no-operator",
            object_type="LogitResult",
            fields={
                "beta": _field("0.693", 0.693, precision=3),
                "odds_ratio": _field("2.00", 2.0, precision=2, operator=ComparisonOperator.EQ),
                "exp_beta_relation_verified": _field("true", True),
            },
            source=SourceLocation(artifact_id="paper", page=4),
        )
    )

    with pytest.raises(ClaimObjectReconstructionError, match="comparison_operator"):
        reconstruct_statistical_object(graph, "logit-no-operator")
