from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Any

from .types import CheckStatus, ComparisonOperator, EvidenceFamily, EvidenceGrade, Materiality


@dataclass(frozen=True)
class SourceLocation:
    artifact_id: str = "paper"
    page: int | None = None
    section: str | None = None
    table: str | None = None
    figure: str | None = None
    row: str | None = None
    column: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    bbox: tuple[float, float, float, float] | None = None
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
class CorrelationMatrix:
    """A reported correlation matrix; cells may be omitted in one triangle."""

    object_id: str
    labels: tuple[str, ...]
    cells: tuple[tuple[ReportedNumber | None, ...], ...]
    materiality: Materiality = Materiality.SECONDARY_RESULT
    source: SourceLocation = field(default_factory=SourceLocation)

    def __post_init__(self) -> None:
        n = len(self.labels)
        if n < 2:
            raise ValueError("correlation matrix requires at least two variables")
        if len(self.cells) != n or any(len(row) != n for row in self.cells):
            raise ValueError("correlation matrix cells must be square and match labels")


@dataclass(frozen=True)
class DiscreteSummary:
    """Reported summary statistics for a variable with an explicit finite support."""

    object_id: str
    n: int
    mean: ReportedNumber
    support: tuple[float, ...]
    sd: ReportedNumber | None = None
    sd_definition: str = "unknown"  # sample | population | unknown
    support_verified: bool = False
    n_verified: bool = False
    weighted: bool | None = None
    materiality: Materiality = Materiality.SECONDARY_RESULT
    source: SourceLocation = field(default_factory=SourceLocation)

    def __post_init__(self) -> None:
        if self.n <= 0:
            raise ValueError("DiscreteSummary.n must be positive")
        if len(self.support) < 2:
            raise ValueError("DiscreteSummary.support requires at least two values")
        if len(set(self.support)) != len(self.support):
            raise ValueError("DiscreteSummary.support values must be unique")
        if any(not isfinite(value) for value in self.support):
            raise ValueError("DiscreteSummary.support values must be finite")


@dataclass(frozen=True)
class LogitResult:
    object_id: str
    beta: ReportedNumber
    odds_ratio: ReportedNumber
    exp_beta_relation_verified: bool = False
    materiality: Materiality = Materiality.SECONDARY_RESULT
    source: SourceLocation = field(default_factory=SourceLocation)


@dataclass(frozen=True)
class MediationResult:
    object_id: str
    a_path: ReportedNumber
    b_path: ReportedNumber
    indirect_effect: ReportedNumber
    product_definition_verified: bool = False
    scale_consistent_verified: bool = False
    materiality: Materiality = Materiality.SECONDARY_RESULT
    source: SourceLocation = field(default_factory=SourceLocation)


@dataclass(frozen=True)
class DIDDesign:
    object_id: str
    periods: int | None = None
    staggered_adoption: bool | None = None
    treatment_type: str = "binary"  # binary | continuous | unknown
    estimator: str | None = None
    event_study: bool | None = None
    heterogeneity_robust_estimator_reported: bool | None = None
    comparison_group: str | None = None
    materiality: Materiality = Materiality.MAIN_EMPIRICAL_CLAIM
    source: SourceLocation = field(default_factory=SourceLocation)


@dataclass(frozen=True)
class IVDesign:
    object_id: str
    single_instrument: bool | None = None
    single_endogenous_regressor: bool | None = None
    just_identified: bool | None = None
    first_stage_f: ReportedNumber | None = None
    uses_f_gt_10_rule_as_validity_claim: bool = False
    weak_robust_methods: tuple[str, ...] = ()
    materiality: Materiality = Materiality.MAIN_EMPIRICAL_CLAIM
    source: SourceLocation = field(default_factory=SourceLocation)


@dataclass(frozen=True)
class RDDDesign:
    object_id: str
    framework: str = "unknown"  # continuity | local_randomization | unknown
    design_type: str = "sharp"  # sharp | fuzzy | unknown
    estimator: str | None = None
    global_polynomial_order: int | None = None
    robust_bias_corrected_inference: bool | None = None
    alternative_modern_inference_reported: bool | None = None
    randomization_inference_reported: bool | None = None
    density_test_reported: bool | None = None
    bandwidth_selection: str | None = None
    materiality: Materiality = Materiality.MAIN_EMPIRICAL_CLAIM
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
