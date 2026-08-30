from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable

from .models import CheckResult, Finding
from .types import CheckStatus, EvidenceGrade, Materiality

_GRADE_WEIGHT = {
    EvidenceGrade.UNVERIFIABLE: 0.0,
    EvidenceGrade.WEAK_SIGNAL: 0.10,
    EvidenceGrade.METHODOLOGICAL_RISK: 0.30,
    EvidenceGrade.INTERNAL_CONTRADICTION: 0.65,
    EvidenceGrade.REPRODUCTION_CONTRADICTION: 0.85,
    EvidenceGrade.DATA_PROVENANCE_CONCERN: 1.00,
}

_MATERIALITY_WEIGHT = {
    Materiality.FORMATTING: 0.10,
    Materiality.PERIPHERAL: 0.25,
    Materiality.SECONDARY_RESULT: 0.50,
    Materiality.MAIN_EMPIRICAL_CLAIM: 0.75,
    Materiality.CHANGES_SUBSTANTIVE_CONCLUSION: 1.00,
}


def verification_coverage(checks: Iterable[CheckResult]) -> float:
    """Share of relevant, checkable evidence that was actually assessed.

    NOT_RELEVANT checks are excluded. UNVERIFIABLE checks remain in the denominator.
    Missing artifacts therefore reduce coverage without increasing review priority.
    """
    numerator = 0.0
    denominator = 0.0
    for check in checks:
        if check.status is CheckStatus.NOT_RELEVANT:
            continue
        denominator += check.coverage_weight
        if check.status in (CheckStatus.PASS, CheckStatus.FAIL, CheckStatus.REVIEW):
            numerator += check.coverage_weight
    if denominator == 0.0:
        return 0.0
    return numerator / denominator


def finding_strength(finding: Finding) -> float:
    confidence = (
        _bounded(finding.applicability_confidence)
        * _bounded(finding.extraction_confidence)
        * _bounded(finding.detector_precision)
    )
    return _GRADE_WEIGHT[finding.grade] * _MATERIALITY_WEIGHT[finding.materiality] * confidence


def review_priority(findings: Iterable[Finding]) -> float:
    """Return 0-100 review priority, explicitly not a probability of misconduct.

    Correlated findings within the same evidence family are collapsed by max strength.
    Independent family scores are then combined with a noisy-OR style aggregation.
    """
    family_scores: dict[object, float] = defaultdict(float)
    for finding in findings:
        family_scores[finding.family] = max(family_scores[finding.family], finding_strength(finding))
    if not family_scores:
        return 0.0
    combined = 1.0 - math.prod(1.0 - score for score in family_scores.values())
    return round(100.0 * combined, 2)


def _bounded(value: float) -> float:
    return min(1.0, max(0.0, float(value)))
