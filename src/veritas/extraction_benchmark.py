from __future__ import annotations

from dataclasses import dataclass

from .benchmark import binomial_upper_bound
from .extraction import ExtractionDecision, ExtractionResolution
from .ingestion import EvidenceKind
from .models import SourceLocation


@dataclass(frozen=True)
class ExtractionGoldTarget:
    target_id: str
    paper_id: str
    article_family_id: str
    object_type: str
    key: str
    kind: EvidenceKind
    accepted_normalized_values: tuple[str, ...]
    source: SourceLocation
    critical_for_hard_audit: bool = True
    reviewers: tuple[str, ...] = ()
    adjudicated: bool = False

    def __post_init__(self) -> None:
        if not self.target_id.strip() or not self.paper_id.strip() or not self.article_family_id.strip():
            raise ValueError("target_id, paper_id, and article_family_id are required")
        if not self.accepted_normalized_values:
            raise ValueError("at least one accepted normalized value is required")
        if len(set(self.reviewers)) < 2 or not self.adjudicated:
            raise ValueError("extraction gold targets require two independent reviewers and adjudication")


@dataclass(frozen=True)
class ExtractionPrediction:
    target_id: str
    resolution: ExtractionResolution


@dataclass(frozen=True)
class ExtractionTargetOutcome:
    target_id: str
    paper_id: str
    article_family_id: str
    critical_for_hard_audit: bool
    decision: ExtractionDecision
    accepted: bool
    value_correct: bool | None
    source_correct: bool | None

    @property
    def fully_correct_accept(self) -> bool:
        return self.accepted and self.value_correct is True and self.source_correct is True

    @property
    def wrong_accept(self) -> bool:
        return self.accepted and not self.fully_correct_accept


@dataclass(frozen=True)
class ExtractionBenchmarkReport:
    targets: int
    accepted: int
    fully_correct_accepts: int
    wrong_accepts: int
    abstentions: int
    conflicts: int
    domain_shifts: int
    selective_coverage: float
    accepted_full_accuracy: float
    wrong_accept_rate: float
    critical_article_families: int
    critical_wrong_accept_families: int
    critical_family_wrong_accept_rate: float
    critical_family_wrong_accept_upper_bound: float
    outcomes: tuple[ExtractionTargetOutcome, ...]


def evaluate_extraction_benchmark(
    gold: tuple[ExtractionGoldTarget, ...] | list[ExtractionGoldTarget],
    predictions: tuple[ExtractionPrediction, ...] | list[ExtractionPrediction],
    *,
    confidence: float = 0.95,
) -> ExtractionBenchmarkReport:
    gold_by_id = {target.target_id: target for target in gold}
    if len(gold_by_id) != len(gold):
        raise ValueError("gold target_id values must be unique")
    prediction_by_id = {prediction.target_id: prediction for prediction in predictions}
    if len(prediction_by_id) != len(predictions):
        raise ValueError("prediction target_id values must be unique")
    unknown = sorted(set(prediction_by_id) - set(gold_by_id))
    if unknown:
        raise ValueError(f"predictions reference unknown gold targets: {unknown}")

    outcomes: list[ExtractionTargetOutcome] = []
    for target in gold:
        prediction = prediction_by_id.get(target.target_id)
        if prediction is None:
            outcomes.append(
                ExtractionTargetOutcome(
                    target_id=target.target_id,
                    paper_id=target.paper_id,
                    article_family_id=target.article_family_id,
                    critical_for_hard_audit=target.critical_for_hard_audit,
                    decision=ExtractionDecision.ABSTAIN,
                    accepted=False,
                    value_correct=None,
                    source_correct=None,
                )
            )
            continue
        resolution = prediction.resolution
        accepted = resolution.decision is ExtractionDecision.ACCEPT
        value_correct = None
        source_correct = None
        if accepted:
            value_correct = resolution.normalized_value in set(target.accepted_normalized_values)
            source_correct = bool(resolution.accepted_candidates) and all(
                _source_identity_matches(candidate.source, target.source)
                for candidate in resolution.accepted_candidates
            )
        outcomes.append(
            ExtractionTargetOutcome(
                target_id=target.target_id,
                paper_id=target.paper_id,
                article_family_id=target.article_family_id,
                critical_for_hard_audit=target.critical_for_hard_audit,
                decision=resolution.decision,
                accepted=accepted,
                value_correct=value_correct,
                source_correct=source_correct,
            )
        )

    accepted_outcomes = [outcome for outcome in outcomes if outcome.accepted]
    fully_correct = sum(outcome.fully_correct_accept for outcome in accepted_outcomes)
    wrong = sum(outcome.wrong_accept for outcome in accepted_outcomes)
    critical = [outcome for outcome in outcomes if outcome.critical_for_hard_audit]
    critical_families = {outcome.article_family_id for outcome in critical}
    wrong_families = {
        outcome.article_family_id for outcome in critical if outcome.wrong_accept
    }

    accepted_count = len(accepted_outcomes)
    target_count = len(outcomes)
    family_count = len(critical_families)
    family_wrong_count = len(wrong_families)
    return ExtractionBenchmarkReport(
        targets=target_count,
        accepted=accepted_count,
        fully_correct_accepts=fully_correct,
        wrong_accepts=wrong,
        abstentions=sum(outcome.decision is ExtractionDecision.ABSTAIN for outcome in outcomes),
        conflicts=sum(outcome.decision is ExtractionDecision.CONFLICT for outcome in outcomes),
        domain_shifts=sum(outcome.decision is ExtractionDecision.DOMAIN_SHIFT for outcome in outcomes),
        selective_coverage=accepted_count / target_count if target_count else 0.0,
        accepted_full_accuracy=fully_correct / accepted_count if accepted_count else 0.0,
        wrong_accept_rate=wrong / target_count if target_count else 0.0,
        critical_article_families=family_count,
        critical_wrong_accept_families=family_wrong_count,
        critical_family_wrong_accept_rate=family_wrong_count / family_count if family_count else 0.0,
        critical_family_wrong_accept_upper_bound=binomial_upper_bound(
            family_wrong_count,
            family_count,
            confidence=confidence,
        ),
        outcomes=tuple(outcomes),
    )


def _source_identity_matches(predicted: SourceLocation, gold: SourceLocation) -> bool:
    if predicted.artifact_id != gold.artifact_id:
        return False
    if gold.page is not None and predicted.page != gold.page:
        return False
    for attribute in ("section", "table", "figure", "row", "column"):
        expected = getattr(gold, attribute)
        if expected is not None and getattr(predicted, attribute) != expected:
            return False
    return True
