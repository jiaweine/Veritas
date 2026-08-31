from __future__ import annotations

from itertools import product
from uuid import uuid4

from scipy.stats import f as f_distribution

from ..group_stats import OneWayAnovaComparison
from ..models import CheckResult, Finding, ReportedNumber
from ..types import CheckStatus, ComparisonOperator, EvidenceFamily, EvidenceGrade
from .base import Detector

_TOL = 1e-10
_SAFETY_EPS = 1e-12


def _reported_compatible(number: ReportedNumber, expected: tuple[float, float]) -> bool:
    lo, hi = expected
    if number.operator is ComparisonOperator.EQ:
        r_lo, r_hi = number.rounding_interval()
        return max(lo, r_lo) <= min(hi, r_hi) + _TOL
    if number.operator is ComparisonOperator.LT:
        return lo < number.value - _TOL
    if number.operator is ComparisonOperator.LE:
        return lo <= number.value + _TOL
    if number.operator is ComparisonOperator.GT:
        return hi > number.value + _TOL
    if number.operator is ComparisonOperator.GE:
        return hi >= number.value - _TOL
    return False


def _weighted_ss(values: tuple[float, ...], weights: tuple[int, ...]) -> float:
    total_weight = float(sum(weights))
    grand = sum(weight * value for weight, value in zip(weights, values, strict=True)) / total_weight
    return sum(weight * (value - grand) ** 2 for weight, value in zip(weights, values, strict=True))


def _minimum_between_ss(
    intervals: tuple[tuple[float, float], ...],
    weights: tuple[int, ...],
) -> float:
    """Globally minimize between-group SS over mean intervals.

    min_m sum n_i (m_i - m_bar)^2 equals
    min_c sum n_i dist(c, [lo_i, hi_i])^2. The latter is a one-dimensional
    convex function with monotone derivative, so bisection finds its global minimizer.
    A tiny downward safety expansion preserves a conservative lower bound.
    """

    left = min(lo for lo, _ in intervals)
    right = max(hi for _, hi in intervals)

    def derivative(center: float) -> float:
        total = 0.0
        for weight, (lo, hi) in zip(weights, intervals, strict=True):
            if center < lo:
                total += 2.0 * weight * (center - lo)
            elif center > hi:
                total += 2.0 * weight * (center - hi)
        return total

    for _ in range(100):
        midpoint = (left + right) / 2.0
        if derivative(midpoint) < 0:
            left = midpoint
        else:
            right = midpoint
    center = (left + right) / 2.0

    objective = 0.0
    for weight, (lo, hi) in zip(weights, intervals, strict=True):
        if center < lo:
            distance = lo - center
        elif center > hi:
            distance = center - hi
        else:
            distance = 0.0
        objective += weight * distance**2

    scale = max(1.0, objective)
    return max(0.0, objective - _SAFETY_EPS * scale)


def _maximum_between_ss(
    intervals: tuple[tuple[float, float], ...],
    weights: tuple[int, ...],
    *,
    max_vertex_groups: int,
) -> tuple[float, str]:
    """Return a conservative global upper bound for between-group SS."""

    if len(intervals) <= max_vertex_groups:
        maximum = 0.0
        for choices in product((0, 1), repeat=len(intervals)):
            values = tuple(intervals[index][choice] for index, choice in enumerate(choices))
            maximum = max(maximum, _weighted_ss(values, weights))
        scale = max(1.0, maximum)
        return maximum + _SAFETY_EPS * scale, "vertex_enumeration"

    global_lo = min(lo for lo, _ in intervals)
    global_hi = max(hi for _, hi in intervals)
    total_n = sum(weights)
    coarse = total_n * (global_hi - global_lo) ** 2
    return coarse + _SAFETY_EPS * max(1.0, coarse), "coarse_range_bound"


class OneWayAnovaSummaryDetector(Detector):
    """Reconstruct classical one-way ANOVA from rounded group N/mean/SD summaries."""

    detector_id = "one_way_anova_summary_reconstruction"
    version = "0.4.0"

    def __init__(self, *, max_vertex_groups: int = 12) -> None:
        if max_vertex_groups < 2:
            raise ValueError("max_vertex_groups must be at least 2")
        self.max_vertex_groups = max_vertex_groups

    def supports(self, obj: object) -> bool:
        return isinstance(obj, OneWayAnovaComparison)

    def run(self, obj: object) -> list[CheckResult]:
        assert isinstance(obj, OneWayAnovaComparison)
        applicability = self._applicability(obj)
        if applicability is not None:
            return [applicability]

        weights = tuple(group.n for group in obj.groups)
        mean_intervals = tuple(group.mean.rounding_interval() for group in obj.groups)
        sd_intervals = tuple(self._sd_interval(group.sd) for group in obj.groups)
        total_n = sum(weights)
        df_between = float(len(obj.groups) - 1)
        df_within = float(total_n - len(obj.groups))

        ss_between_min = _minimum_between_ss(mean_intervals, weights)
        ss_between_max, max_method = _maximum_between_ss(
            mean_intervals,
            weights,
            max_vertex_groups=self.max_vertex_groups,
        )
        ss_within_min = sum((group.n - 1) * sd[0] ** 2 for group, sd in zip(obj.groups, sd_intervals, strict=True))
        ss_within_max = sum((group.n - 1) * sd[1] ** 2 for group, sd in zip(obj.groups, sd_intervals, strict=True))

        common_evidence = {
            "groups": len(obj.groups),
            "total_n": total_n,
            "ss_between_interval": (ss_between_min, ss_between_max),
            "ss_within_interval": (ss_within_min, ss_within_max),
            "between_ss_upper_method": max_method,
            "algorithm": "rounding-aware global SS bounds for classical one-way ANOVA",
        }

        checks = [
            self._check_stat(
                obj,
                "df_between",
                obj.reported_df_between,
                (df_between, df_between),
                "Reported ANOVA numerator degrees of freedom",
                common_evidence,
            ),
            self._check_stat(
                obj,
                "df_within",
                obj.reported_df_within,
                (df_within, df_within),
                "Reported ANOVA denominator degrees of freedom",
                common_evidence,
            ),
        ]

        f_interval = None
        f_reason = None
        if ss_within_min <= 0:
            f_reason = "Rounded SD intervals permit zero within-group variance, so a finite F upper bound is unavailable."
        else:
            f_min = (ss_between_min / df_between) / (ss_within_max / df_within)
            f_max = (ss_between_max / df_between) / (ss_within_min / df_within)
            f_interval = (max(0.0, f_min), max(0.0, f_max))

        checks.append(
            self._check_stat(
                obj,
                "f_statistic",
                obj.reported_f,
                f_interval,
                "Reported one-way ANOVA F statistic",
                common_evidence,
                unverifiable_reason=f_reason,
            )
        )

        p_interval = None
        p_reason = f_reason
        if obj.p_value_adjusted:
            p_reason = "The reported ANOVA p-value is adjusted; the adjustment rule is not reconstructed here."
        elif f_interval is not None:
            p_interval = (
                float(f_distribution.sf(f_interval[1], df_between, df_within)),
                float(f_distribution.sf(f_interval[0], df_between, df_within)),
            )
        checks.append(
            self._check_stat(
                obj,
                "p_value",
                obj.reported_p_value,
                p_interval,
                "Reported one-way ANOVA p-value",
                common_evidence,
                unverifiable_reason=p_reason,
            )
        )

        eta_interval = None
        eta_reason = None
        if not obj.eta_squared_definition_verified:
            eta_reason = "The reported effect size is not verified to be eta-squared for this one-way ANOVA."
        else:
            low_denominator = ss_between_min + ss_within_max
            high_denominator = ss_between_max + ss_within_min
            eta_low = 0.0 if low_denominator <= 0 else ss_between_min / low_denominator
            eta_high = 1.0 if high_denominator <= 0 else ss_between_max / high_denominator
            eta_interval = (max(0.0, eta_low), min(1.0, eta_high))
        checks.append(
            self._check_stat(
                obj,
                "eta_squared",
                obj.reported_eta_squared,
                eta_interval,
                "Reported eta-squared",
                common_evidence,
                unverifiable_reason=eta_reason,
            )
        )
        return checks

    def _applicability(self, obj: OneWayAnovaComparison) -> CheckResult | None:
        if obj.test_definition != "classic_one_way":
            return self._unverifiable(obj, "The analysis is not verified as a classical independent-groups one-way ANOVA.")
        if not obj.independent_groups_verified:
            return self._unverifiable(obj, "ANOVA group independence has not been verified.")
        if not obj.same_outcome_scale_verified:
            return self._unverifiable(obj, "ANOVA groups are not verified to use the same outcome scale.")
        if any(group.sd_definition != "sample" for group in obj.groups):
            return self._unverifiable(obj, "ANOVA reconstruction currently requires sample SDs.")
        if any(group.weighted is not False for group in obj.groups):
            return self._unverifiable(obj, "Weighted or unknown-weight ANOVA group summaries are not supported.")
        summary_numbers = tuple(number for group in obj.groups for number in (group.mean, group.sd))
        if any(number.operator is not ComparisonOperator.EQ for number in summary_numbers):
            return self._unverifiable(obj, "ANOVA group means and SDs must be equality-reported values.")
        return None

    def _sd_interval(self, number: ReportedNumber) -> tuple[float, float]:
        lo, hi = number.rounding_interval()
        return max(0.0, lo), max(0.0, hi)

    def _check_stat(
        self,
        obj: OneWayAnovaComparison,
        check_id: str,
        reported: ReportedNumber | None,
        expected: tuple[float, float] | None,
        title: str,
        evidence: dict[str, object],
        *,
        unverifiable_reason: str | None = None,
    ) -> CheckResult:
        if reported is None:
            return CheckResult(
                self.detector_id,
                check_id,
                obj.object_id,
                CheckStatus.NOT_RELEVANT,
                EvidenceFamily.NUMERICAL_CONSISTENCY,
                message=f"{title} was not reported.",
            )
        if expected is None:
            return CheckResult(
                self.detector_id,
                check_id,
                obj.object_id,
                CheckStatus.UNVERIFIABLE,
                EvidenceFamily.NUMERICAL_CONSISTENCY,
                message=unverifiable_reason or f"{title} could not be reconstructed.",
            )
        if _reported_compatible(reported, expected):
            return CheckResult(
                self.detector_id,
                check_id,
                obj.object_id,
                CheckStatus.PASS,
                EvidenceFamily.NUMERICAL_CONSISTENCY,
                message=f"{title} is compatible with all rounding-aware ANOVA constraints.",
            )

        explanation = (
            f"{title} is incompatible with every value allowed by the verified rounded group summaries "
            "under the classical one-way ANOVA definition."
        )
        finding = Finding(
            finding_id=f"F-{uuid4().hex[:10]}",
            detector_id=f"{self.detector_id}@{self.version}",
            object_id=obj.object_id,
            grade=EvidenceGrade.INTERNAL_CONTRADICTION,
            materiality=obj.materiality,
            family=EvidenceFamily.NUMERICAL_CONSISTENCY,
            title=f"{title} contradiction",
            explanation=explanation,
            evidence={
                **evidence,
                "expected_interval": expected,
                "reported_value": reported.value,
                "reported_operator": reported.operator.value,
                "reported_decimals": reported.decimals,
            },
            source=obj.source,
        )
        return CheckResult(
            self.detector_id,
            check_id,
            obj.object_id,
            CheckStatus.FAIL,
            EvidenceFamily.NUMERICAL_CONSISTENCY,
            message=explanation,
            finding=finding,
        )

    def _unverifiable(self, obj: OneWayAnovaComparison, message: str) -> CheckResult:
        return CheckResult(
            self.detector_id,
            "anova_applicability",
            obj.object_id,
            CheckStatus.UNVERIFIABLE,
            EvidenceFamily.NUMERICAL_CONSISTENCY,
            message=message,
        )
