from __future__ import annotations

from dataclasses import dataclass

from .reproduction import (
    CellComparison,
    CellComparisonStatus,
    ReproductionDecision,
    ReproductionTarget,
)
from .types import Materiality


@dataclass(frozen=True)
class ClaimAgreementSummary:
    """Agreement for one sealed paper claim across all of its target cells."""

    claim_id: str
    target_ids: tuple[str, ...]
    metrics: tuple[str, ...]
    matched_targets: int
    mismatched_targets: int
    missing_targets: int
    decision: ReproductionDecision
    max_materiality: Materiality


@dataclass(frozen=True)
class PaperAgreementSummary:
    """Paper-level view that preserves claim identities instead of collapsing to one score."""

    claims: tuple[ClaimAgreementSummary, ...]
    matched_claim_ids: tuple[str, ...]
    mismatched_claim_ids: tuple[str, ...]
    partial_claim_ids: tuple[str, ...]
    unverifiable_claim_ids: tuple[str, ...]
    material_incomplete_claim_ids: tuple[str, ...]


def summarize_paper_agreement(
    targets: tuple[ReproductionTarget, ...],
    comparisons: tuple[CellComparison, ...],
    *,
    material_threshold: Materiality = Materiality.MAIN_EMPIRICAL_CLAIM,
) -> PaperAgreementSummary:
    """Summarize deterministic cell comparisons at the publication-claim level.

    Every sealed target must have exactly one comparison record. A claim is MATCH only when every
    sealed target for that claim matches. All-missing claims are UNVERIFIABLE; mixed match/missing
    claims are PARTIAL; any numerical mismatch makes the claim MISMATCH. This function deliberately
    does not create an aggregate similarity score.
    """

    if not targets:
        raise ValueError("paper agreement requires at least one sealed reproduction target")

    target_ids = tuple(target.target_id for target in targets)
    if len(set(target_ids)) != len(target_ids):
        raise ValueError("reproduction target ids must be unique")

    comparison_ids = tuple(item.target_id for item in comparisons)
    if len(set(comparison_ids)) != len(comparison_ids):
        raise ValueError("cell comparison target ids must be unique")
    if set(comparison_ids) != set(target_ids):
        missing = tuple(sorted(set(target_ids) - set(comparison_ids)))
        extra = tuple(sorted(set(comparison_ids) - set(target_ids)))
        raise ValueError(
            "cell comparisons must exactly cover the sealed target set; "
            f"missing={missing!r}, extra={extra!r}"
        )

    comparison_by_id = {item.target_id: item for item in comparisons}
    claim_order: list[str] = []
    grouped: dict[str, list[ReproductionTarget]] = {}
    for target in targets:
        if target.claim_id not in grouped:
            claim_order.append(target.claim_id)
            grouped[target.claim_id] = []
        grouped[target.claim_id].append(target)

    claim_summaries: list[ClaimAgreementSummary] = []
    for claim_id in claim_order:
        claim_targets = grouped[claim_id]
        claim_comparisons = [comparison_by_id[target.target_id] for target in claim_targets]
        matched = sum(item.status is CellComparisonStatus.MATCH for item in claim_comparisons)
        mismatched = sum(item.status is CellComparisonStatus.MISMATCH for item in claim_comparisons)
        missing = sum(item.status is CellComparisonStatus.MISSING for item in claim_comparisons)
        total = len(claim_comparisons)

        if mismatched:
            decision = ReproductionDecision.MISMATCH
        elif matched == total:
            decision = ReproductionDecision.MATCH
        elif missing == total:
            decision = ReproductionDecision.UNVERIFIABLE
        else:
            decision = ReproductionDecision.PARTIAL

        claim_summaries.append(
            ClaimAgreementSummary(
                claim_id=claim_id,
                target_ids=tuple(target.target_id for target in claim_targets),
                metrics=tuple(target.metric for target in claim_targets),
                matched_targets=matched,
                mismatched_targets=mismatched,
                missing_targets=missing,
                decision=decision,
                max_materiality=max(
                    (target.materiality for target in claim_targets),
                    key=int,
                ),
            )
        )

    claims = tuple(claim_summaries)

    def _ids(decision: ReproductionDecision) -> tuple[str, ...]:
        return tuple(item.claim_id for item in claims if item.decision is decision)

    material_incomplete = tuple(
        item.claim_id
        for item in claims
        if int(item.max_materiality) >= int(material_threshold)
        and item.decision is not ReproductionDecision.MATCH
    )
    return PaperAgreementSummary(
        claims=claims,
        matched_claim_ids=_ids(ReproductionDecision.MATCH),
        mismatched_claim_ids=_ids(ReproductionDecision.MISMATCH),
        partial_claim_ids=_ids(ReproductionDecision.PARTIAL),
        unverifiable_claim_ids=_ids(ReproductionDecision.UNVERIFIABLE),
        material_incomplete_claim_ids=material_incomplete,
    )
