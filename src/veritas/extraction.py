from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import ceil, isfinite

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
        _require_nonempty_string(self.parser_id, label="parser_id")
        _require_nonempty_string(self.parser_family, label="parser_family")
        if not isinstance(self.raw, str):
            raise TypeError("raw extraction value must be a string")
        _require_nonempty_string(self.normalized_value, label="normalized_value")
        _require_finite_nonnegative_number(
            self.nonconformity_score,
            label="nonconformity_score",
        )
        if not isinstance(self.source, SourceLocation):
            raise TypeError("extraction candidate source must be a SourceLocation")


@dataclass(frozen=True)
class ConformalCalibration:
    nonconformity_scores: tuple[float, ...]
    alpha: float = 0.05
    shift_scores: tuple[float, ...] = ()
    shift_alpha: float = 0.01

    def __post_init__(self) -> None:
        if not self.nonconformity_scores:
            raise ValueError("at least one calibration score is required")
        for score in self.nonconformity_scores:
            _require_finite_nonnegative_number(score, label="calibration nonconformity score")
        _require_open_probability(self.alpha, label="alpha")
        for score in self.shift_scores:
            _require_finite_number(score, label="calibration shift score")
        _require_open_probability(self.shift_alpha, label="shift_alpha")

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
        _require_finite_number(shift_score, label="shift_score")
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

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ExtractionDecision):
            raise TypeError("extraction resolution decision must be an ExtractionDecision")
        if not isinstance(self.accepted_candidates, tuple):
            raise TypeError("accepted_candidates must be a tuple of ExtractionCandidate values")
        if any(not isinstance(candidate, ExtractionCandidate) for candidate in self.accepted_candidates):
            raise TypeError("accepted_candidates must contain ExtractionCandidate values")
        _require_finite_nonnegative_number(
            self.calibration_threshold,
            label="calibration_threshold",
        )
        if self.shift_p_value is not None:
            _require_closed_probability(self.shift_p_value, label="shift_p_value")
        if not isinstance(self.reason, str):
            raise TypeError("extraction resolution reason must be a string")

        if self.decision is ExtractionDecision.ACCEPT:
            _require_nonempty_string(self.normalized_value, label="accepted normalized_value")
            if not self.accepted_candidates:
                raise ValueError("ACCEPT resolution requires accepted candidates")
            if any(
                candidate.normalized_value != self.normalized_value
                for candidate in self.accepted_candidates
            ):
                raise ValueError("ACCEPT candidates must agree with normalized_value")
        else:
            if self.normalized_value is not None:
                raise ValueError("non-ACCEPT resolution must not carry normalized_value")
            if self.decision is ExtractionDecision.CONFLICT:
                values = {candidate.normalized_value for candidate in self.accepted_candidates}
                if len(values) < 2:
                    raise ValueError("CONFLICT resolution requires at least two candidate values")
            if self.decision is ExtractionDecision.DOMAIN_SHIFT and self.accepted_candidates:
                raise ValueError("DOMAIN_SHIFT resolution must not carry accepted candidates")


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
        if not isinstance(calibration, ConformalCalibration):
            raise TypeError("calibration must be a ConformalCalibration")
        if isinstance(min_independent_families, bool) or not isinstance(
            min_independent_families, int
        ):
            raise TypeError("min_independent_families must be an integer")
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
        candidates = tuple(candidates)
        if any(not isinstance(candidate, ExtractionCandidate) for candidate in candidates):
            raise TypeError("candidates must contain ExtractionCandidate values")
        threshold = self.calibration.threshold
        shift_p = None
        if shift_score is not None:
            _require_finite_number(shift_score, label="shift_score")
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


def _require_nonempty_string(value: object, *, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")


def _require_finite_number(value: object, *, label: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(float(value))
    ):
        raise ValueError(f"{label} must be a finite number")


def _require_finite_nonnegative_number(value: object, *, label: str) -> None:
    _require_finite_number(value, label=label)
    if float(value) < 0.0:
        raise ValueError(f"{label} must be non-negative")


def _require_open_probability(value: object, *, label: str) -> None:
    _require_finite_number(value, label=label)
    if not 0.0 < float(value) < 1.0:
        raise ValueError(f"{label} must be in (0, 1)")


def _require_closed_probability(value: object, *, label: str) -> None:
    _require_finite_number(value, label=label)
    if not 0.0 <= float(value) <= 1.0:
        raise ValueError(f"{label} must be in [0, 1]")
