from __future__ import annotations

import pytest

from veritas.auditbench import (
    AuditBenchExpectation,
    AuditBenchObservation,
    evaluate_auditbench,
)
from veritas.types import CheckStatus, EvidenceGrade, Materiality


def _expectation(
    case_id: str,
    *,
    paper_id: str | None = None,
    expected_status: CheckStatus = CheckStatus.PASS,
    maximum_allowed_grade: EvidenceGrade = EvidenceGrade.UNVERIFIABLE,
    extraction_error_case: bool = False,
) -> AuditBenchExpectation:
    return AuditBenchExpectation(
        case_id=case_id,
        paper_id=paper_id or f"paper:{case_id}",
        detector_id="detector",
        check_id="check",
        corruption_family="control",
        affected_claim_ids=(),
        materiality=Materiality.MAIN_EMPIRICAL_CLAIM,
        discipline="economics",
        reporting_style="table",
        expected_status=expected_status,
        maximum_allowed_grade=maximum_allowed_grade,
        extraction_error_case=extraction_error_case,
    )


def _observation(
    case_id: str,
    *,
    status: CheckStatus = CheckStatus.PASS,
    grade: EvidenceGrade | None = None,
) -> AuditBenchObservation:
    return AuditBenchObservation(
        case_id=case_id,
        detector_id="detector",
        check_id="check",
        status=status,
        grade=grade,
    )


def _evaluate(expectations, observations):
    return evaluate_auditbench(
        expectations,
        observations,
        min_alert_precision=0.9,
        min_alert_recall=0.9,
        max_false_hard_alert_rate_per_clean_paper=0.01,
        max_grade_violation_rate=0.0,
    )


def test_perfect_locked_semantics_pass():
    expectations = (
        _expectation("clean"),
        _expectation(
            "hard",
            expected_status=CheckStatus.FAIL,
            maximum_allowed_grade=EvidenceGrade.INTERNAL_CONTRADICTION,
        ),
        _expectation(
            "soft",
            expected_status=CheckStatus.REVIEW,
            maximum_allowed_grade=EvidenceGrade.WEAK_SIGNAL,
        ),
    )
    observations = (
        _observation("clean"),
        _observation(
            "hard",
            status=CheckStatus.FAIL,
            grade=EvidenceGrade.INTERNAL_CONTRADICTION,
        ),
        _observation("soft", status=CheckStatus.REVIEW, grade=EvidenceGrade.WEAK_SIGNAL),
    )

    report = _evaluate(expectations, observations)

    assert report.passed
    assert report.overall.status_mismatches == 0
    assert report.overall.alert_precision == 1.0
    assert report.overall.alert_recall == 1.0
    assert report.overall.false_hard_alert_rate_per_clean_paper == 0.0
    assert report.overall.grade_violations == 0


def test_exact_status_drift_fails_even_when_alert_class_is_unchanged():
    expectation = _expectation(
        "soft",
        expected_status=CheckStatus.REVIEW,
        maximum_allowed_grade=EvidenceGrade.WEAK_SIGNAL,
    )
    observation = _observation("soft", status=CheckStatus.FAIL, grade=EvidenceGrade.WEAK_SIGNAL)

    report = _evaluate((expectation,), (observation,))

    assert not report.passed
    assert report.overall.status_mismatches == 1
    assert any("exact detector status" in reason for reason in report.reasons)


def test_false_hard_alert_is_counted_at_clean_paper_level():
    expectations = (
        _expectation("a", paper_id="paper:clean"),
        _expectation("b", paper_id="paper:clean", expected_status=CheckStatus.UNVERIFIABLE),
    )
    observations = (
        _observation("a", status=CheckStatus.FAIL, grade=EvidenceGrade.INTERNAL_CONTRADICTION),
        _observation("b", status=CheckStatus.UNVERIFIABLE),
    )

    report = _evaluate(expectations, observations)

    assert not report.passed
    assert report.overall.clean_papers == 1
    assert report.overall.false_hard_alert_papers == 1
    assert report.overall.false_hard_alert_rate_per_clean_paper == 1.0


def test_evidence_grade_ceiling_is_independent_of_status():
    expectation = _expectation(
        "extract",
        expected_status=CheckStatus.UNVERIFIABLE,
        maximum_allowed_grade=EvidenceGrade.UNVERIFIABLE,
        extraction_error_case=True,
    )
    observation = _observation(
        "extract",
        status=CheckStatus.UNVERIFIABLE,
        grade=EvidenceGrade.INTERNAL_CONTRADICTION,
    )

    report = _evaluate((expectation,), (observation,))

    assert not report.passed
    assert report.overall.grade_violations == 1
    assert report.overall.extraction_error_hard_alerts == 1


def test_case_identity_set_must_match_exactly():
    with pytest.raises(ValueError, match="must exactly match cases"):
        _evaluate((_expectation("expected"),), (_observation("extra"),))


def test_duplicate_case_ids_are_rejected():
    with pytest.raises(ValueError, match="duplicate AuditBench case id"):
        _evaluate(
            (_expectation("duplicate"), _expectation("duplicate")),
            (_observation("duplicate"),),
        )
