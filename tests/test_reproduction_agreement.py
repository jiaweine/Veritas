from __future__ import annotations

import pytest

from veritas.models import ReportedNumber, SourceLocation
from veritas.reproduction import (
    CellComparisonStatus,
    ReproducedCell,
    ReproductionDecision,
    ReproductionTarget,
    compare_reproduced_cells,
)
from veritas.reproduction_agreement import summarize_paper_agreement
from veritas.types import Materiality


def _target(
    target_id: str,
    claim_id: str,
    metric: str,
    value: float,
    *,
    decimals: int = 2,
    materiality: Materiality = Materiality.SECONDARY_RESULT,
) -> ReproductionTarget:
    return ReproductionTarget(
        target_id=target_id,
        claim_id=claim_id,
        metric=metric,
        reported=ReportedNumber(value, decimals=decimals),
        source=SourceLocation(page=7, table="Table 2", row=claim_id, column=metric),
        materiality=materiality,
    )


def test_claim_match_requires_every_sealed_effect_cell_to_match() -> None:
    targets = (
        _target(
            "main-beta",
            "claim-main",
            "coefficient",
            0.18,
            materiality=Materiality.MAIN_EMPIRICAL_CLAIM,
        ),
        _target(
            "main-se",
            "claim-main",
            "standard_error",
            0.04,
            materiality=Materiality.MAIN_EMPIRICAL_CLAIM,
        ),
        _target(
            "main-p",
            "claim-main",
            "p_value",
            0.001,
            decimals=3,
            materiality=Materiality.MAIN_EMPIRICAL_CLAIM,
        ),
    )
    comparisons = compare_reproduced_cells(
        targets,
        (
            ReproducedCell("main-beta", 0.18, "a" * 64),
            ReproducedCell("main-se", 0.04, "a" * 64),
            ReproducedCell("main-p", 0.001, "a" * 64),
        ),
    )

    summary = summarize_paper_agreement(targets, comparisons)

    assert summary.matched_claim_ids == ("claim-main",)
    assert summary.material_incomplete_claim_ids == ()
    assert summary.claims[0].decision is ReproductionDecision.MATCH
    assert summary.claims[0].metrics == ("coefficient", "standard_error", "p_value")


def test_one_wrong_effect_cell_makes_the_claim_mismatch_without_average_score() -> None:
    targets = (
        _target(
            "main-beta",
            "claim-main",
            "coefficient",
            0.18,
            materiality=Materiality.MAIN_EMPIRICAL_CLAIM,
        ),
        _target(
            "main-se",
            "claim-main",
            "standard_error",
            0.04,
            materiality=Materiality.MAIN_EMPIRICAL_CLAIM,
        ),
    )
    comparisons = compare_reproduced_cells(
        targets,
        (
            ReproducedCell("main-beta", 0.18, "a" * 64),
            ReproducedCell("main-se", 0.40, "a" * 64),
        ),
    )

    summary = summarize_paper_agreement(targets, comparisons)

    assert summary.mismatched_claim_ids == ("claim-main",)
    assert summary.material_incomplete_claim_ids == ("claim-main",)
    assert summary.claims[0].matched_targets == 1
    assert summary.claims[0].mismatched_targets == 1


def test_all_missing_is_unverifiable_while_mixed_output_is_partial() -> None:
    targets = (
        _target("a-beta", "claim-a", "coefficient", 0.2),
        _target("a-se", "claim-a", "standard_error", 0.1),
        _target("b-beta", "claim-b", "coefficient", 0.3),
    )
    comparisons = compare_reproduced_cells(
        targets,
        (ReproducedCell("a-beta", 0.2, "a" * 64),),
    )

    assert [item.status for item in comparisons] == [
        CellComparisonStatus.MATCH,
        CellComparisonStatus.MISSING,
        CellComparisonStatus.MISSING,
    ]
    summary = summarize_paper_agreement(targets, comparisons)
    assert summary.partial_claim_ids == ("claim-a",)
    assert summary.unverifiable_claim_ids == ("claim-b",)


def test_claim_summary_refuses_comparison_sets_that_do_not_match_sealed_targets() -> None:
    targets = (_target("beta", "claim", "coefficient", 0.2),)

    with pytest.raises(ValueError, match="exactly cover"):
        summarize_paper_agreement(targets, ())
