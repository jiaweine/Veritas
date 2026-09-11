from __future__ import annotations

import pytest

from veritas.claim_identity import normalize_estimand_identity
from veritas.claim_identity_benchmark import (
    ClaimIdentityGold,
    ClaimIdentityPrediction,
    evaluate_claim_identity,
)


def _identity(outcome: str):
    return normalize_estimand_identity(
        outcome=outcome,
        treatment="program",
        transformation="level",
    )


def test_claim_identity_metrics_do_not_use_detector_correctness() -> None:
    gold = (
        ClaimIdentityGold("claim-1", "estimate-1", _identity("employment")),
        ClaimIdentityGold("claim-2", "estimate-2", _identity("earnings")),
    )
    predictions = (
        ClaimIdentityPrediction("claim-1", "estimate-1", _identity("employment"), True),
        ClaimIdentityPrediction("claim-2", "estimate-2", _identity("hours"), True),
        ClaimIdentityPrediction("claim-x", "estimate-x", _identity("employment"), True),
    )

    report = evaluate_claim_identity(gold, predictions)

    assert report.true_positive_links == 2
    assert report.false_positive_links == 1
    assert report.false_negative_links == 0
    assert report.exact_identity_matches == 1
    assert report.precision == pytest.approx(2 / 3)
    assert report.recall == 1.0
    assert report.exact_identity_accuracy == 0.5


def test_rejected_candidates_do_not_count_as_false_positive_links() -> None:
    gold = (ClaimIdentityGold("claim-1", "estimate-1", _identity("employment")),)
    predictions = (
        ClaimIdentityPrediction("claim-x", "estimate-x", _identity("employment"), False),
    )

    report = evaluate_claim_identity(gold, predictions)

    assert report.true_positive_links == 0
    assert report.false_positive_links == 0
    assert report.false_negative_links == 1
    assert report.accepted_link_count == 0


def test_duplicate_accepted_predictions_fail_closed() -> None:
    identity = _identity("employment")
    predictions = (
        ClaimIdentityPrediction("claim-1", "estimate-1", identity, True),
        ClaimIdentityPrediction("claim-1", "estimate-1", identity, True),
    )

    with pytest.raises(ValueError, match="duplicate accepted"):
        evaluate_claim_identity((), predictions)
