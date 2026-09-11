from __future__ import annotations

from dataclasses import dataclass

from .claim_identity import EstimandIdentity


@dataclass(frozen=True)
class ClaimIdentityGold:
    claim_id: str
    estimate_object_id: str
    identity: EstimandIdentity


@dataclass(frozen=True)
class ClaimIdentityPrediction:
    claim_id: str
    estimate_object_id: str
    identity: EstimandIdentity
    accepted: bool


@dataclass(frozen=True)
class ClaimIdentityBenchmarkReport:
    true_positive_links: int
    false_positive_links: int
    false_negative_links: int
    exact_identity_matches: int
    accepted_link_count: int
    gold_link_count: int

    @property
    def precision(self) -> float:
        denominator = self.true_positive_links + self.false_positive_links
        return self.true_positive_links / denominator if denominator else 1.0

    @property
    def recall(self) -> float:
        denominator = self.true_positive_links + self.false_negative_links
        return self.true_positive_links / denominator if denominator else 1.0

    @property
    def f1(self) -> float:
        precision = self.precision
        recall = self.recall
        return 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0

    @property
    def exact_identity_accuracy(self) -> float:
        return self.exact_identity_matches / self.true_positive_links if self.true_positive_links else 1.0


def evaluate_claim_identity(
    gold: tuple[ClaimIdentityGold, ...],
    predictions: tuple[ClaimIdentityPrediction, ...],
) -> ClaimIdentityBenchmarkReport:
    """Evaluate claim/estimate identity without using detector correctness as a proxy label."""

    gold_by_link = _index_gold(gold)
    accepted = tuple(prediction for prediction in predictions if prediction.accepted)
    prediction_by_link = _index_predictions(accepted)

    gold_links = set(gold_by_link)
    predicted_links = set(prediction_by_link)
    true_positive = gold_links & predicted_links
    false_positive = predicted_links - gold_links
    false_negative = gold_links - predicted_links
    exact_identity_matches = sum(
        prediction_by_link[key].identity == gold_by_link[key].identity
        for key in true_positive
    )

    return ClaimIdentityBenchmarkReport(
        true_positive_links=len(true_positive),
        false_positive_links=len(false_positive),
        false_negative_links=len(false_negative),
        exact_identity_matches=exact_identity_matches,
        accepted_link_count=len(accepted),
        gold_link_count=len(gold),
    )


def _index_gold(
    gold: tuple[ClaimIdentityGold, ...],
) -> dict[tuple[str, str], ClaimIdentityGold]:
    indexed: dict[tuple[str, str], ClaimIdentityGold] = {}
    for item in gold:
        key = (item.claim_id, item.estimate_object_id)
        if key in indexed:
            raise ValueError(f"duplicate gold claim-identity link: {key!r}")
        indexed[key] = item
    return indexed


def _index_predictions(
    predictions: tuple[ClaimIdentityPrediction, ...],
) -> dict[tuple[str, str], ClaimIdentityPrediction]:
    indexed: dict[tuple[str, str], ClaimIdentityPrediction] = {}
    for item in predictions:
        key = (item.claim_id, item.estimate_object_id)
        if key in indexed:
            raise ValueError(f"duplicate accepted claim-identity prediction: {key!r}")
        indexed[key] = item
    return indexed
