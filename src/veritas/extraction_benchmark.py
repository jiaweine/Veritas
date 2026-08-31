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
    kind: EvidenceKind
    critical_for_hard_audit: bool
    decision: ExtractionDecision
    accepted: bool
    value_correct: bool | None
    source_correct: bool | None
    page_correct: bool | None
    display_item_correct: bool | None
    row_correct: bool | None
    column_correct: bool | None

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
    accepted_value_accuracy: float
    accepted_source_accuracy: float
    field_targets: int
    accepted_field_targets: int
    accepted_field_value_accuracy: float
    table_row_targets: int
    accepted_table_row_targets: int
    accepted_table_row_identity_accuracy: float
    semantic_gate_targets: int
    accepted_semantic_gate_targets: int
    accepted_semantic_gate_accuracy: float
    critical_article_families: int
    critical_wrong_accept_families: int
    critical_family_wrong_accept_rate: float
    critical_family_wrong_accept_upper_bound: float
    outcomes: tuple[ExtractionTargetOutcome, ...]


@dataclass(frozen=True)
class ExtractionSelectivityPoint:
    """One operating point; not a probability and not a production certification score."""

    threshold: float
    selective_coverage: float
    accepted_full_accuracy: float
    accepted_field_value_accuracy: float
    accepted_table_row_identity_accuracy: float
    accepted_semantic_gate_accuracy: float
    wrong_accept_rate: float
    critical_family_wrong_accept_upper_bound: float


@dataclass(frozen=True)
class ExtractionSelectivityCurve:
    """Ordered operating points without collapsing the trade-off to one scalar."""

    points: tuple[ExtractionSelectivityPoint, ...]

    def __post_init__(self) -> None:
        thresholds = [point.threshold for point in self.points]
        if len(set(thresholds)) != len(thresholds):
            raise ValueError("selectivity-curve thresholds must be unique")
        if thresholds != sorted(thresholds):
            raise ValueError("selectivity-curve points must be sorted by threshold")


def build_extraction_selectivity_curve(
    reports: tuple[tuple[float, ExtractionBenchmarkReport], ...]
    | list[tuple[float, ExtractionBenchmarkReport]],
) -> ExtractionSelectivityCurve:
    """Expose the coverage/error trade-off across frozen thresholds.

    The returned object intentionally has no AUC or aggregate score. For integrity auditing,
    a single scalar can hide the difference between abstaining aggressively and accepting a larger
    fraction of fields with more wrong accepts.
    """
    thresholds = [threshold for threshold, _ in reports]
    if len(set(thresholds)) != len(thresholds):
        raise ValueError("selectivity-curve thresholds must be unique")
    points = tuple(
        ExtractionSelectivityPoint(
            threshold=threshold,
            selective_coverage=report.selective_coverage,
            accepted_full_accuracy=report.accepted_full_accuracy,
            accepted_field_value_accuracy=report.accepted_field_value_accuracy,
            accepted_table_row_identity_accuracy=report.accepted_table_row_identity_accuracy,
            accepted_semantic_gate_accuracy=report.accepted_semantic_gate_accuracy,
            wrong_accept_rate=report.wrong_accept_rate,
            critical_family_wrong_accept_upper_bound=report.critical_family_wrong_accept_upper_bound,
        )
        for threshold, report in sorted(reports, key=lambda item: item[0])
    )
    return ExtractionSelectivityCurve(points=points)


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
                    kind=target.kind,
                    critical_for_hard_audit=target.critical_for_hard_audit,
                    decision=ExtractionDecision.ABSTAIN,
                    accepted=False,
                    value_correct=None,
                    source_correct=None,
                    page_correct=None,
                    display_item_correct=None,
                    row_correct=None,
                    column_correct=None,
                )
            )
            continue

        resolution = prediction.resolution
        accepted = resolution.decision is ExtractionDecision.ACCEPT
        value_correct = None
        source_correct = None
        page_correct = None
        display_item_correct = None
        row_correct = None
        column_correct = None
        if accepted:
            value_correct = resolution.normalized_value in set(target.accepted_normalized_values)
            candidates = resolution.accepted_candidates
            if candidates:
                source_components = [
                    _source_identity_components(candidate.source, target.source)
                    for candidate in candidates
                ]
                page_correct = all(item["page"] for item in source_components)
                display_item_correct = all(item["display_item"] for item in source_components)
                row_correct = all(item["row"] for item in source_components)
                column_correct = all(item["column"] for item in source_components)
                source_correct = all(item["source"] for item in source_components)
            else:
                page_correct = False
                display_item_correct = False
                row_correct = False
                column_correct = False
                source_correct = False

        outcomes.append(
            ExtractionTargetOutcome(
                target_id=target.target_id,
                paper_id=target.paper_id,
                article_family_id=target.article_family_id,
                kind=target.kind,
                critical_for_hard_audit=target.critical_for_hard_audit,
                decision=resolution.decision,
                accepted=accepted,
                value_correct=value_correct,
                source_correct=source_correct,
                page_correct=page_correct,
                display_item_correct=display_item_correct,
                row_correct=row_correct,
                column_correct=column_correct,
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

    field_outcomes = [outcome for outcome in outcomes if outcome.kind is EvidenceKind.FIELD]
    accepted_fields = [outcome for outcome in field_outcomes if outcome.accepted]
    semantic_outcomes = [
        outcome for outcome in outcomes if outcome.kind is EvidenceKind.SEMANTIC_GATE
    ]
    accepted_semantic = [outcome for outcome in semantic_outcomes if outcome.accepted]

    table_row_target_ids = {
        target.target_id
        for target in gold
        if target.kind is EvidenceKind.FIELD
        and (target.source.table is not None or target.source.figure is not None)
        and target.source.row is not None
    }
    table_row_outcomes = [outcome for outcome in outcomes if outcome.target_id in table_row_target_ids]
    accepted_table_rows = [outcome for outcome in table_row_outcomes if outcome.accepted]

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
        selective_coverage=_rate(accepted_count, target_count),
        accepted_full_accuracy=_rate(fully_correct, accepted_count),
        wrong_accept_rate=_rate(wrong, target_count),
        accepted_value_accuracy=_rate(
            sum(outcome.value_correct is True for outcome in accepted_outcomes),
            accepted_count,
        ),
        accepted_source_accuracy=_rate(
            sum(outcome.source_correct is True for outcome in accepted_outcomes),
            accepted_count,
        ),
        field_targets=len(field_outcomes),
        accepted_field_targets=len(accepted_fields),
        accepted_field_value_accuracy=_rate(
            sum(outcome.value_correct is True for outcome in accepted_fields),
            len(accepted_fields),
        ),
        table_row_targets=len(table_row_outcomes),
        accepted_table_row_targets=len(accepted_table_rows),
        accepted_table_row_identity_accuracy=_rate(
            sum(
                outcome.display_item_correct is True and outcome.row_correct is True
                for outcome in accepted_table_rows
            ),
            len(accepted_table_rows),
        ),
        semantic_gate_targets=len(semantic_outcomes),
        accepted_semantic_gate_targets=len(accepted_semantic),
        accepted_semantic_gate_accuracy=_rate(
            sum(outcome.fully_correct_accept for outcome in accepted_semantic),
            len(accepted_semantic),
        ),
        critical_article_families=family_count,
        critical_wrong_accept_families=family_wrong_count,
        critical_family_wrong_accept_rate=_rate(family_wrong_count, family_count),
        critical_family_wrong_accept_upper_bound=binomial_upper_bound(
            family_wrong_count,
            family_count,
            confidence=confidence,
        ),
        outcomes=tuple(outcomes),
    )


def _source_identity_components(predicted: SourceLocation, gold: SourceLocation) -> dict[str, bool]:
    artifact = predicted.artifact_id == gold.artifact_id
    page = gold.page is None or predicted.page == gold.page
    display_item = True
    for attribute in ("section", "table", "figure"):
        expected = getattr(gold, attribute)
        if expected is not None and getattr(predicted, attribute) != expected:
            display_item = False
            break
    row = gold.row is None or predicted.row == gold.row
    column = gold.column is None or predicted.column == gold.column
    return {
        "artifact": artifact,
        "page": page,
        "display_item": display_item,
        "row": row,
        "column": column,
        "source": artifact and page and display_item and row and column,
    }


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0
