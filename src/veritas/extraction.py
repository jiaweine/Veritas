from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import ceil

from .models import SourceLocation


class ExtractionDecision(str, Enum):
    ACCEPT = "accept"
    ABSTAIN = "abstain"
    CONFLICT = "conflict"
    DOMAIN_SHIFT = "domain_shift"


@dataclass(frozen=True)
class ExtractionCandidate:
    parser_id: str
    parser_family: str
    raw: str
    normalized_value: str
    nonconformity_score: float
    source: SourceLocation

    def __post_init__(self) -> None:
        if self.nonconformity_score < 0:
            raise ValueError("nonconformity_score must be non-negative")


@dataclass(frozen=True)
class ConformalCalibration:
    nonconformity_scores: tuple[float, ...]
    alpha: float = 0.05
    shift_scores: tuple[float, ...] = ()
    shift_alpha: float = 0.01

    def __post_init__(self) -> None:
        if not self.nonconformity_scores:
            raise ValueError("at least one calibration score is required")
        if not 0.0 < self.alpha < 1.0:
            raise ValueError("alpha must be in (0, 1)")
        if not 0.0 < self.shift_alpha < 1.0:
            raise ValueError("shift_alpha must be in (0, 1)")

    @property
    def threshold(self) -> float:
        """Finite-sample split-conformal quantile with the standard (n+1) correction."""
        scores = sorted(self.nonconformity_scores)
        n = len(scores)
        rank = ceil((n + 1) * (1.0 - self.alpha))
        rank = min(max(rank, 1), n)
        return scores[rank - 1]

    def shift_p_value(self, shift_score: float) -> float | None:
        """One-sided conformal-style tail p-value for distribution-shift screening."""
        if not self.shift_scores:
            return None
        exceedances = sum(score >= shift_score for score in self.shift_scores)
        return (exceedances + 1.0) / (len(self.shift_scores) + 1.0)


@dataclass(frozen=True)
class ExtractionResolution:
    decision: ExtractionDecision
    normalized_value: str | None
    accepted_candidates: tuple[ExtractionCandidate, ...]
    calibration_threshold: float
    shift_p_value: float | None = None
    reason: str = ""


class ConformalExtractionGate:
    """Calibrated abstention gate for high-stakes statistical extraction.

    A candidate survives only if its nonconformity score is below a held-out
    split-conformal threshold. Veritas then requires agreement from independent
    parser families. Multiple surviving values are never adjudicated by an LLM;
    the field is marked unresolved.

    The optional shift gate is selective-conformal inspired: a test item whose
    shift score lies in the extreme tail of held-out calibration examples is
    abstained before value aggregation.
    """

    def __init__(self, calibration: ConformalCalibration, *, min_independent_families: int = 2) -> None:
        if min_independent_families < 1:
            raise ValueError("min_independent_families must be positive")
        self.calibration = calibration
        self.min_independent_families = min_independent_families

    def resolve(
        self,
        candidates: tuple[ExtractionCandidate, ...] | list[ExtractionCandidate],
        *,
        shift_score: float | None = None,
    ) -> ExtractionResolution:
        threshold = self.calibration.threshold
        shift_p = None
        if shift_score is not None:
            shift_p = self.calibration.shift_p_value(shift_score)
            if shift_p is not None and shift_p < self.calibration.shift_alpha:
                return ExtractionResolution(
                    decision=ExtractionDecision.DOMAIN_SHIFT,
                    normalized_value=None,
                    accepted_candidates=(),
                    calibration_threshold=threshold,
                    shift_p_value=shift_p,
                    reason="Input appears outside the calibration uncertainty distribution; extraction abstained.",
                )

        accepted = tuple(candidate for candidate in candidates if candidate.nonconformity_score <= threshold)
        if not accepted:
            return ExtractionResolution(
                decision=ExtractionDecision.ABSTAIN,
                normalized_value=None,
                accepted_candidates=(),
                calibration_threshold=threshold,
                shift_p_value=shift_p,
                reason="No extraction candidate passed the conformal calibration threshold.",
            )

        by_value: dict[str, list[ExtractionCandidate]] = {}
        for candidate in accepted:
            by_value.setdefault(candidate.normalized_value, []).append(candidate)

        if len(by_value) > 1:
            return ExtractionResolution(
                decision=ExtractionDecision.CONFLICT,
                normalized_value=None,
                accepted_candidates=accepted,
                calibration_threshold=threshold,
                shift_p_value=shift_p,
                reason="Multiple calibrated extraction values disagree; Veritas refuses to guess.",
            )

        value, supporters = next(iter(by_value.items()))
        families = {candidate.parser_family for candidate in supporters}
        if len(families) < self.min_independent_families:
            return ExtractionResolution(
                decision=ExtractionDecision.ABSTAIN,
                normalized_value=None,
                accepted_candidates=tuple(supporters),
                calibration_threshold=threshold,
                shift_p_value=shift_p,
                reason="Calibrated value lacks support from enough independent parser families.",
            )

        return ExtractionResolution(
            decision=ExtractionDecision.ACCEPT,
            normalized_value=value,
            accepted_candidates=tuple(supporters),
            calibration_threshold=threshold,
            shift_p_value=shift_p,
            reason="Calibrated candidates from independent parser families agree.",
        )
