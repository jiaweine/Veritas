from __future__ import annotations

from veritas.models import SourceLocation
from veritas.survey_integrity import (
    SurveyIntegrityDecision,
    SurveySignalKind,
    SurveySignalObservation,
    assess_survey_response_integrity,
)


def _signal(
    signal_id: str,
    kind: SurveySignalKind,
    *,
    applicable: bool = True,
    flagged: bool | None = True,
    confidence: float = 0.99,
) -> SurveySignalObservation:
    return SurveySignalObservation(
        signal_id,
        kind,
        applicable,
        flagged,
        confidence,
        SourceLocation(artifact_id="survey-data", row="respondent-1"),
        f"{kind.value} diagnostic",
    )


def test_two_independent_high_confidence_signals_trigger_review_only() -> None:
    assessment = assess_survey_response_integrity(
        "respondent-1",
        (
            _signal("longstring", SurveySignalKind.LONGSTRING),
            _signal("time", SurveySignalKind.RESPONSE_TIME),
        ),
    )

    assert assessment.decision is SurveyIntegrityDecision.REVIEW
    assert assessment.flagged_signal_ids == ("longstring", "time")
    assert "human review" in assessment.reasons[0]


def test_two_flags_from_same_signal_family_do_not_satisfy_independence_gate() -> None:
    assessment = assess_survey_response_integrity(
        "respondent-1",
        (
            _signal("longstring-a", SurveySignalKind.LONGSTRING),
            _signal("longstring-b", SurveySignalKind.LONGSTRING),
        ),
    )

    assert assessment.decision is SurveyIntegrityDecision.PASS


def test_no_applicable_signal_is_unverifiable_not_clean() -> None:
    assessment = assess_survey_response_integrity(
        "respondent-1",
        (
            _signal(
                "time",
                SurveySignalKind.RESPONSE_TIME,
                applicable=False,
                flagged=None,
            ),
        ),
    )

    assert assessment.decision is SurveyIntegrityDecision.UNVERIFIABLE


def test_low_confidence_flags_do_not_trigger_review() -> None:
    assessment = assess_survey_response_integrity(
        "respondent-1",
        (
            _signal("longstring", SurveySignalKind.LONGSTRING, confidence=0.40),
            _signal("time", SurveySignalKind.RESPONSE_TIME, confidence=0.40),
        ),
    )

    assert assessment.decision is SurveyIntegrityDecision.UNVERIFIABLE
    assert set(assessment.low_confidence_signal_ids) == {"longstring", "time"}
