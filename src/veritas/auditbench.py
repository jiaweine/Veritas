from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .types import CheckStatus, EvidenceGrade, Materiality

_ALERT_STATUSES = {CheckStatus.REVIEW, CheckStatus.FAIL}


@dataclass(frozen=True)
class AuditBenchExpectation:
    case_id: str
    paper_id: str
    detector_id: str
    check_id: str
    corruption_family: str
    affected_claim_ids: tuple[str, ...]
    materiality: Materiality
    discipline: str
    reporting_style: str
    expected_status: CheckStatus
    maximum_allowed_grade: EvidenceGrade
    extraction_error_case: bool = False
    benign_exception: bool = False


@dataclass(frozen=True)
class AuditBenchObservation:
    case_id: str
    detector_id: str
    check_id: str
    status: CheckStatus
    grade: EvidenceGrade | None


@dataclass(frozen=True)
class AuditBenchMetrics:
    cases: int
    papers: int
    expected_alerts: int
    observed_alerts: int
    true_alerts: int
    false_alerts: int
    missed_alerts: int
    alert_precision: float
    alert_recall: float
    clean_papers: int
    false_hard_alert_papers: int
    false_hard_alert_rate_per_clean_paper: float
    grade_violations: int
    grade_violation_rate: float
    extraction_error_cases: int
    extraction_error_hard_alerts: int


@dataclass(frozen=True)
class AuditBenchReport:
    overall: AuditBenchMetrics
    by_detector: dict[str, AuditBenchMetrics]
    by_materiality: dict[str, AuditBenchMetrics]
    by_discipline: dict[str, AuditBenchMetrics]
    by_reporting_style: dict[str, AuditBenchMetrics]
    passed: bool
    reasons: tuple[str, ...]


def evaluate_auditbench(
    expectations: Iterable[AuditBenchExpectation],
    observations: Iterable[AuditBenchObservation],
    *,
    min_alert_precision: float,
    min_alert_recall: float,
    max_false_hard_alert_rate_per_clean_paper: float,
    max_grade_violation_rate: float,
) -> AuditBenchReport:
    expected = tuple(expectations)
    observed = tuple(observations)
    _validate_policy(
        min_alert_precision=min_alert_precision,
        min_alert_recall=min_alert_recall,
        max_false_hard_alert_rate_per_clean_paper=max_false_hard_alert_rate_per_clean_paper,
        max_grade_violation_rate=max_grade_violation_rate,
    )
    expected_by_case = _unique_by_case(expected)
    observed_by_case = _unique_observations(observed)
    if set(expected_by_case) != set(observed_by_case):
        missing = sorted(set(expected_by_case) - set(observed_by_case))
        extra = sorted(set(observed_by_case) - set(expected_by_case))
        raise ValueError(f"AuditBench observations must exactly match cases; missing={missing!r}, extra={extra!r}")
    for case_id, expectation in expected_by_case.items():
        observation = observed_by_case[case_id]
        if observation.detector_id != expectation.detector_id or observation.check_id != expectation.check_id:
            raise ValueError(f"AuditBench observation identity mismatch for {case_id!r}")

    overall = _metrics(expected, observed_by_case)
    by_detector = _slices(expected, observed_by_case, lambda item: item.detector_id)
    by_materiality = _slices(expected, observed_by_case, lambda item: item.materiality.name)
    by_discipline = _slices(expected, observed_by_case, lambda item: item.discipline)
    by_reporting_style = _slices(expected, observed_by_case, lambda item: item.reporting_style)

    reasons: list[str] = []
    if overall.alert_precision < min_alert_precision:
        reasons.append(
            f"alert precision below policy: {overall.alert_precision:.4f} < {min_alert_precision:.4f}"
        )
    if overall.alert_recall < min_alert_recall:
        reasons.append(
            f"alert recall below policy: {overall.alert_recall:.4f} < {min_alert_recall:.4f}"
        )
    if overall.false_hard_alert_rate_per_clean_paper > max_false_hard_alert_rate_per_clean_paper:
        reasons.append(
            "false hard-alert rate per clean paper exceeds policy: "
            f"{overall.false_hard_alert_rate_per_clean_paper:.4f} > "
            f"{max_false_hard_alert_rate_per_clean_paper:.4f}"
        )
    if overall.grade_violation_rate > max_grade_violation_rate:
        reasons.append(
            f"evidence-grade violation rate exceeds policy: {overall.grade_violation_rate:.4f} > "
            f"{max_grade_violation_rate:.4f}"
        )

    return AuditBenchReport(
        overall=overall,
        by_detector=by_detector,
        by_materiality=by_materiality,
        by_discipline=by_discipline,
        by_reporting_style=by_reporting_style,
        passed=not reasons,
        reasons=tuple(reasons),
    )


def _metrics(
    expectations: tuple[AuditBenchExpectation, ...],
    observed_by_case: dict[str, AuditBenchObservation],
) -> AuditBenchMetrics:
    expected_alerts = sum(item.expected_status in _ALERT_STATUSES for item in expectations)
    observed_alerts = sum(observed_by_case[item.case_id].status in _ALERT_STATUSES for item in expectations)
    true_alerts = sum(
        item.expected_status in _ALERT_STATUSES
        and observed_by_case[item.case_id].status in _ALERT_STATUSES
        for item in expectations
    )
    false_alerts = sum(
        item.expected_status not in _ALERT_STATUSES
        and observed_by_case[item.case_id].status in _ALERT_STATUSES
        for item in expectations
    )
    missed_alerts = expected_alerts - true_alerts
    precision = true_alerts / observed_alerts if observed_alerts else (1.0 if not expected_alerts else 0.0)
    recall = true_alerts / expected_alerts if expected_alerts else 1.0

    expected_hard_by_paper: dict[str, bool] = {}
    observed_hard_by_paper: dict[str, bool] = {}
    for item in expectations:
        expected_hard_by_paper[item.paper_id] = expected_hard_by_paper.get(item.paper_id, False) or (
            item.expected_status is CheckStatus.FAIL
        )
        observation = observed_by_case[item.case_id]
        observed_hard_by_paper[item.paper_id] = observed_hard_by_paper.get(item.paper_id, False) or _is_hard(
            observation
        )
    clean_papers = [paper_id for paper_id, expected_hard in expected_hard_by_paper.items() if not expected_hard]
    false_hard_papers = sum(observed_hard_by_paper.get(paper_id, False) for paper_id in clean_papers)
    false_hard_rate = false_hard_papers / len(clean_papers) if clean_papers else 0.0

    grade_violations = 0
    extraction_error_cases = 0
    extraction_error_hard_alerts = 0
    for item in expectations:
        observation = observed_by_case[item.case_id]
        observed_grade = observation.grade or EvidenceGrade.UNVERIFIABLE
        if observed_grade > item.maximum_allowed_grade:
            grade_violations += 1
        if item.extraction_error_case:
            extraction_error_cases += 1
            if _is_hard(observation):
                extraction_error_hard_alerts += 1

    return AuditBenchMetrics(
        cases=len(expectations),
        papers=len({item.paper_id for item in expectations}),
        expected_alerts=expected_alerts,
        observed_alerts=observed_alerts,
        true_alerts=true_alerts,
        false_alerts=false_alerts,
        missed_alerts=missed_alerts,
        alert_precision=precision,
        alert_recall=recall,
        clean_papers=len(clean_papers),
        false_hard_alert_papers=false_hard_papers,
        false_hard_alert_rate_per_clean_paper=false_hard_rate,
        grade_violations=grade_violations,
        grade_violation_rate=grade_violations / len(expectations) if expectations else 0.0,
        extraction_error_cases=extraction_error_cases,
        extraction_error_hard_alerts=extraction_error_hard_alerts,
    )


def _slices(
    expectations: tuple[AuditBenchExpectation, ...],
    observed_by_case: dict[str, AuditBenchObservation],
    key,
) -> dict[str, AuditBenchMetrics]:
    grouped: dict[str, list[AuditBenchExpectation]] = {}
    for item in expectations:
        grouped.setdefault(str(key(item)), []).append(item)
    return {
        name: _metrics(tuple(items), observed_by_case)
        for name, items in sorted(grouped.items())
    }


def _is_hard(observation: AuditBenchObservation) -> bool:
    return observation.status is CheckStatus.FAIL or (
        observation.grade is not None and observation.grade >= EvidenceGrade.INTERNAL_CONTRADICTION
    )


def _unique_by_case(
    expectations: tuple[AuditBenchExpectation, ...],
) -> dict[str, AuditBenchExpectation]:
    result: dict[str, AuditBenchExpectation] = {}
    for item in expectations:
        if item.case_id in result:
            raise ValueError(f"duplicate AuditBench case id: {item.case_id!r}")
        result[item.case_id] = item
    return result


def _unique_observations(
    observations: tuple[AuditBenchObservation, ...],
) -> dict[str, AuditBenchObservation]:
    result: dict[str, AuditBenchObservation] = {}
    for item in observations:
        if item.case_id in result:
            raise ValueError(f"duplicate AuditBench observation case id: {item.case_id!r}")
        result[item.case_id] = item
    return result


def _validate_policy(**values: float) -> None:
    for name, value in values.items():
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be in [0, 1]")
