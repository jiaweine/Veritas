from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .types import CheckStatus, ComparisonOperator, EvidenceFamily, EvidenceGrade, Materiality


@dataclass(frozen=True)
class SourceLocation:
    artifact_id: str = "paper"
    page: int | None = None
    table: str | None = None
    row: str | None = None
    column: str | None = None
    text_quote: str | None = None


@dataclass(frozen=True)
class ReportedNumber:
    value: float
    decimals: int | None = None
    operator: ComparisonOperator = ComparisonOperator.EQ

    def rounding_interval(self) -> tuple[float, float]:
        """Return a conservative interval compatible with the displayed rounded value."""
        if self.decimals is None or self.operator is not ComparisonOperator.EQ:
            return self.value, self.value
        half_unit = 0.5 * (10.0 ** (-self.decimals))
        return self.value - half_unit, self.value + half_unit


@dataclass(frozen=True)
class RegressionResult:
    object_id: str
    beta: ReportedNumber
    se: ReportedNumber | None = None
    t_stat: ReportedNumber | None = None
    p_value: ReportedNumber | None = None
    ci_lower: ReportedNumber | None = None
    ci_upper: ReportedNumber | None = None
    ci_level: float = 0.95
    degrees_of_freedom: float | None = None
    inference_distribution: str = "normal"  # normal | student_t | unknown
    p_value_adjusted: bool = False
    materiality: Materiality = Materiality.SECONDARY_RESULT
    source: SourceLocation = field(default_factory=SourceLocation)


@dataclass(frozen=True)
class SamplePartition:
    object_id: str
    total_n: int | None
    groups: dict[str, int]
    exhaustive: bool | None = None
    non_overlapping: bool = True
    explanation_present: bool | None = None
    materiality: Materiality = Materiality.SECONDARY_RESULT
    source: SourceLocation = field(default_factory=SourceLocation)


@dataclass(frozen=True)
class Finding:
    finding_id: str
    detector_id: str
    object_id: str
    grade: EvidenceGrade
    materiality: Materiality
    family: EvidenceFamily
    title: str
    explanation: str
    evidence: dict[str, Any] = field(default_factory=dict)
    applicability_confidence: float = 1.0
    extraction_confidence: float = 1.0
    detector_precision: float = 1.0
    source: SourceLocation = field(default_factory=SourceLocation)


@dataclass(frozen=True)
class CheckResult:
    detector_id: str
    check_id: str
    object_id: str
    status: CheckStatus
    family: EvidenceFamily
    coverage_weight: float = 1.0
    message: str = ""
    finding: Finding | None = None


@dataclass(frozen=True)
class AuditSummary:
    verification_coverage: float
    review_priority: float
    findings: tuple[Finding, ...]
    checks: tuple[CheckResult, ...]
