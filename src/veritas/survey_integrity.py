from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from .models import SourceLocation


class SurveySignalKind(str, Enum):
    LONGSTRING = "longstring"
    PERSON_TOTAL = "person_total"
    RESPONSE_TIME = "response_time"
    INVARIANT_PATTERN = "invariant_pattern"
    ATTENTION_CHECK = "attention_check"


class SurveyIntegrityDecision(str, Enum):
    PASS = "pass"
    REVIEW = "review"
    UNVERIFIABLE = "unverifiable"


@dataclass(frozen=True)
class SurveySignalObservation:
    signal_id: str
    kind: SurveySignalKind
    applicable: bool
    flagged: bool | None
    extraction_confidence: float
    source: SourceLocation
    explanation: str

    def __post_init__(self) -> None:
        if not isinstance(self.signal_id, str) or not self.signal_id.strip():
            raise ValueError("survey signal_id is required")
        if not isinstance(self.kind, SurveySignalKind):
            raise TypeError("survey signal kind must be a SurveySignalKind")
        if type(self.applicable) is not bool:
            raise TypeError("survey signal applicable must be a boolean")
        if self.flagged is not None and type(self.flagged) is not bool:
            raise TypeError("survey signal flagged must be boolean or null")
        if isinstance(self.extraction_confidence, bool) or not isinstance(
            self.extraction_confidence, (int, float)
        ):
            raise TypeError("survey signal extraction_confidence must be numeric")
        if not math.isfinite(float(self.extraction_confidence)) or not 0.0 <= float(
            self.extraction_confidence
        ) <= 1.0:
            raise ValueError("survey signal extraction_confidence must be finite and in [0, 1]")
        if not isinstance(self.explanation, str) or not self.explanation.strip():
            raise ValueError("survey signal explanation is required")


@dataclass(frozen=True)
class SurveyIntegrityAssessment:
    respondent_id: str
    decision: SurveyIntegrityDecision
    applicable_signal_ids: tuple[str, ...]
    flagged_signal_ids: tuple[str, ...]
    low_confidence_signal_ids: tuple[str, ...]
    reasons: tuple[str, ...]


def assess_survey_response_integrity(
    respondent_id: str,
    signals: tuple[SurveySignalObservation, ...],
    *,
    minimum_signal_confidence: float = 0.90,
    minimum_independent_flags: int = 2,
) -> SurveyIntegrityAssessment:
    """Escalate only when multiple applicable, high-confidence signal families agree.

    This is a review gate, not a data-fabrication detector and never emits E5 by itself.
    """

    if not isinstance(respondent_id, str) or not respondent_id.strip():
        raise ValueError("respondent_id is required")
    if not 0.0 <= minimum_signal_confidence <= 1.0:
        raise ValueError("minimum_signal_confidence must be in [0, 1]")
    if isinstance(minimum_independent_flags, bool) or not isinstance(minimum_independent_flags, int):
        raise TypeError("minimum_independent_flags must be an integer")
    if minimum_independent_flags < 2:
        raise ValueError("survey integrity escalation requires at least two independent flags")
    ids = tuple(item.signal_id for item in signals)
    if len(ids) != len(set(ids)):
        raise ValueError("survey signal ids must be unique")

    applicable = tuple(item for item in signals if item.applicable)
    if not applicable:
        return SurveyIntegrityAssessment(
            respondent_id,
            SurveyIntegrityDecision.UNVERIFIABLE,
            (),
            (),
            (),
            ("no survey response-integrity signal is applicable to this record",),
        )

    low_confidence = tuple(
        item.signal_id
        for item in applicable
        if item.extraction_confidence < minimum_signal_confidence or item.flagged is None
    )
    usable = tuple(
        item
        for item in applicable
        if item.extraction_confidence >= minimum_signal_confidence and item.flagged is not None
    )
    flagged = tuple(item for item in usable if item.flagged)
    flagged_kinds = {item.kind for item in flagged}

    if len(flagged_kinds) >= minimum_independent_flags:
        decision = SurveyIntegrityDecision.REVIEW
        reasons = (
            "multiple independent applicable response-integrity signals require human review",
        )
    elif not usable:
        decision = SurveyIntegrityDecision.UNVERIFIABLE
        reasons = ("applicable survey signals are missing or below the confidence gate",)
    else:
        decision = SurveyIntegrityDecision.PASS
        reasons = (
            "fewer than the required number of independent high-confidence signals were flagged",
        )

    return SurveyIntegrityAssessment(
        respondent_id,
        decision,
        tuple(item.signal_id for item in applicable),
        tuple(item.signal_id for item in flagged),
        low_confidence,
        reasons,
    )
