from __future__ import annotations

from math import exp, log, sqrt
from uuid import uuid4

from scipy.special import gammaln
from scipy.stats import t as student_t

from ..group_stats import TwoGroupComparison
from ..models import CheckResult, Finding, ReportedNumber
from ..types import CheckStatus, ComparisonOperator, EvidenceFamily, EvidenceGrade
from .base import Detector

_TOL = 1e-10


def _sub_interval(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    return a[0] - b[1], a[1] - b[0]


def _positive_divide(numerator: tuple[float, float], denominator: tuple[float, float]) -> tuple[float, float]:
    if denominator[0] <= 0:
        raise ValueError("denominator interval is not strictly positive")
    values = (
        numerator[0] / denominator[0],
        numerator[0] / denominator[1],
        numerator[1] / denominator[0],
        numerator[1] / denominator[1],
    )
    return min(values), max(values)


def _reported_compatible(number: ReportedNumber, expected: tuple[float, float]) -> bool:
    lo, hi = expected
    if number.operator is ComparisonOperator.EQ:
        reported_lo, reported_hi = number.rounding_interval()
        return max(lo, reported_lo) <= min(hi, reported_hi) + _TOL
    if number.operator is ComparisonOperator.LT:
        return lo < number.value - _TOL
    if number.operator is ComparisonOperator.LE:
        return lo <= number.value + _TOL
    if number.operator is ComparisonOperator.GT:
        return hi > number.value + _TOL
    if number.operator is ComparisonOperator.GE:
        return hi >= number.value - _TOL
    return False


def _absolute_interval(interval: tuple[float, float]) -> tuple[float, float]:
    lo, hi = interval
    if lo <= 0 <= hi:
        return 0.0, max(abs(lo), abs(hi))
    values = (abs(lo), abs(hi))
    return min(values), max(values)


def _hedges_exact_correction(df: float) -> float:
    if df <= 1:
        raise ValueError("Hedges exact correction requires df > 1")
    return exp(gammaln(df / 2.0) - 0.5 * log(df / 2.0) - gammaln((df - 1.0) / 2.0))


def _hedges_approx_correction(df: float) -> float:
    return 1.0 - 3.0 / (4.0 * df - 1.0)


class TwoGroupSummaryDetector(Detector):
    """Reconstruct independent two-group statistics from rounded N/mean/SD summaries.

    Student equal-variance and Welch statistics are modeled separately. All expected
    values are intervals induced by the displayed rounding. A contradiction is only
    emitted when the reported statistic is incompatible with every value in the
    reconstructed interval under explicitly verified assumptions.
    """

    detector_id = "two_group_summary_reconstruction"
    version = "0.4.0"

    def supports(self, obj: object) -> bool:
        return isinstance(obj, TwoGroupComparison)

    def run(self, obj: object) -> list[CheckResult]:
        assert isinstance(obj, TwoGroupComparison)
        if not obj.independent_groups_verified:
            return [self._unverifiable(obj, "Group independence has not been verified.")]
        if not obj.same_outcome_scale_verified:
            return [self._unverifiable(obj, "The two group summaries are not verified to use the same outcome scale.")]
        if obj.group_a.sd_definition != "sample" or obj.group_b.sd_definition != "sample":
            return [self._unverifiable(obj, "Two-group reconstruction currently requires sample SDs.")]
        if obj.group_a.weighted is not False or obj.group_b.weighted is not False:
            return [self._unverifiable(obj, "Weighted or unknown-weight group summaries are not supported.")]
        summary_numbers = (
            obj.group_a.mean,
            obj.group_a.sd,
            obj.group_b.mean,
            obj.group_b.sd,
        )
        if any(number.operator is not ComparisonOperator.EQ for number in summary_numbers):
            return [
                self._unverifiable(
                    obj,
                    "Group means and SDs must be equality-reported values before rounding intervals can be reconstructed.",
                )
            ]

        mean_a = obj.group_a.mean.rounding_interval()
        mean_b = obj.group_b.mean.rounding_interval()
        sd_a = self._sd_interval(obj.group_a.sd)
        sd_b = self._sd_interval(obj.group_b.sd)
        difference = _sub_interval(mean_a, mean_b)

        checks: list[CheckResult] = []
        checks.append(
            self._check_stat(
                obj,
                "mean_difference",
                obj.reported_mean_difference,
                difference if obj.difference_direction_verified else None,
                "Reported mean difference",
                {"formula": "mean_A - mean_B"},
                unverifiable_reason="The sign/order of the reported mean difference has not been verified.",
            )
        )

        pooled_sd = self._pooled_sd_interval(obj, sd_a, sd_b)
        t_interval: tuple[float, float] | None = None
        df_interval: tuple[float, float] | None = None
        test_reason: str | None = None

        if not obj.difference_direction_verified:
            test_reason = "The sign/order of the reported test statistic has not been verified."
        elif obj.test_definition == "student_equal_var":
            if pooled_sd[0] <= 0:
                test_reason = "Rounded SD intervals permit a zero pooled SD, so t is not bounded."
            else:
                scale = sqrt(1.0 / obj.group_a.n + 1.0 / obj.group_b.n)
                t_interval = _positive_divide(difference, (pooled_sd[0] * scale, pooled_sd[1] * scale))
                df = float(obj.group_a.n + obj.group_b.n - 2)
                df_interval = (df, df)
        elif obj.test_definition == "welch":
            se = (
                sqrt(sd_a[0] ** 2 / obj.group_a.n + sd_b[0] ** 2 / obj.group_b.n),
                sqrt(sd_a[1] ** 2 / obj.group_a.n + sd_b[1] ** 2 / obj.group_b.n),
            )
            if se[0] <= 0:
                test_reason = "Rounded SD intervals permit a zero Welch standard error, so t is not bounded."
            else:
                t_interval = _positive_divide(difference, se)
                df_interval = self._welch_df_interval(obj, sd_a, sd_b)
                if df_interval is None:
                    test_reason = "Welch degrees of freedom are not bounded because an SD interval includes zero."
        else:
            test_reason = "The paper's two-group test definition is not verified as Student equal-variance or Welch."

        checks.append(
            self._check_stat(
                obj,
                "t_statistic",
                obj.reported_t,
                t_interval,
                "Reported two-group t statistic",
                {"test_definition": obj.test_definition},
                unverifiable_reason=test_reason,
            )
        )
        checks.append(
            self._check_stat(
                obj,
                "degrees_of_freedom",
                obj.reported_df,
                df_interval,
                "Reported two-group degrees of freedom",
                {"test_definition": obj.test_definition},
                unverifiable_reason=test_reason,
            )
        )

        p_interval = None
        p_reason = test_reason
        if obj.p_value_adjusted:
            p_reason = "The reported p-value is adjusted; the adjustment rule is not reconstructed here."
        elif t_interval is not None and df_interval is not None:
            p_interval = self._two_sided_p_interval(t_interval, df_interval)
        checks.append(
            self._check_stat(
                obj,
                "p_value",
                obj.reported_p_value,
                p_interval,
                "Reported two-sided p-value",
                {"test_definition": obj.test_definition, "tail": "two-sided"},
                unverifiable_reason=p_reason,
            )
        )

        effect_reason = None
        d_interval = None
        if not obj.pooled_sd_effect_size_verified:
            effect_reason = "The reported standardized effect is not verified to use the pooled-SD definition."
        elif not obj.difference_direction_verified:
            effect_reason = "The direction of the standardized effect has not been verified."
        elif pooled_sd[0] <= 0:
            effect_reason = "Rounded SD intervals permit a zero pooled SD, so standardized effects are not bounded."
        else:
            d_interval = _positive_divide(difference, pooled_sd)

        checks.append(
            self._check_stat(
                obj,
                "cohen_d",
                obj.reported_cohen_d,
                d_interval,
                "Reported Cohen's d",
                {"formula": "(mean_A - mean_B) / pooled_sample_SD"},
                unverifiable_reason=effect_reason,
            )
        )

        g_interval = None
        g_reason = effect_reason
        if d_interval is not None:
            effect_df = float(obj.group_a.n + obj.group_b.n - 2)
            if obj.hedges_correction == "exact_gamma":
                correction = _hedges_exact_correction(effect_df)
                g_interval = (d_interval[0] * correction, d_interval[1] * correction)
                g_reason = None
            elif obj.hedges_correction == "approx_4df_minus_1":
                correction = _hedges_approx_correction(effect_df)
                g_interval = (d_interval[0] * correction, d_interval[1] * correction)
                g_reason = None
            else:
                g_reason = "The Hedges small-sample correction formula has not been verified."
        checks.append(
            self._check_stat(
                obj,
                "hedges_g",
                obj.reported_hedges_g,
                g_interval,
                "Reported Hedges' g",
                {"correction": obj.hedges_correction},
                unverifiable_reason=g_reason,
            )
        )
        return checks

    def _sd_interval(self, number: ReportedNumber) -> tuple[float, float]:
        lo, hi = number.rounding_interval()
        return max(0.0, lo), max(0.0, hi)

    def _pooled_sd_interval(
        self,
        obj: TwoGroupComparison,
        sd_a: tuple[float, float],
        sd_b: tuple[float, float],
    ) -> tuple[float, float]:
        n_a, n_b = obj.group_a.n, obj.group_b.n
        denominator = n_a + n_b - 2
        low = sqrt(((n_a - 1) * sd_a[0] ** 2 + (n_b - 1) * sd_b[0] ** 2) / denominator)
        high = sqrt(((n_a - 1) * sd_a[1] ** 2 + (n_b - 1) * sd_b[1] ** 2) / denominator)
        return low, high

    def _welch_df_interval(
        self,
        obj: TwoGroupComparison,
        sd_a: tuple[float, float],
        sd_b: tuple[float, float],
    ) -> tuple[float, float] | None:
        if sd_a[0] <= 0 or sd_b[0] <= 0:
            return None
        n_a, n_b = obj.group_a.n, obj.group_b.n
        a_lo, a_hi = sd_a[0] ** 2 / n_a, sd_a[1] ** 2 / n_a
        b_lo, b_hi = sd_b[0] ** 2 / n_b, sd_b[1] ** 2 / n_b
        ratio_lo, ratio_hi = a_lo / b_hi, a_hi / b_lo
        stationary = (n_a - 1) / (n_b - 1)

        def df_for_ratio(ratio: float) -> float:
            return (ratio + 1.0) ** 2 / (ratio**2 / (n_a - 1) + 1.0 / (n_b - 1))

        candidates = [df_for_ratio(ratio_lo), df_for_ratio(ratio_hi)]
        if ratio_lo <= stationary <= ratio_hi:
            candidates.append(df_for_ratio(stationary))
        return min(candidates), max(candidates)

    def _two_sided_p_interval(
        self,
        t_interval: tuple[float, float],
        df_interval: tuple[float, float],
    ) -> tuple[float, float]:
        abs_lo, abs_hi = _absolute_interval(t_interval)
        # For fixed |t| > 0, Student-t two-sided p decreases as df increases.
        p_lo = float(2.0 * student_t.sf(abs_hi, df_interval[1]))
        p_hi = float(2.0 * student_t.sf(abs_lo, df_interval[0]))
        return max(0.0, p_lo), min(1.0, p_hi)

    def _check_stat(
        self,
        obj: TwoGroupComparison,
        check_id: str,
        reported: ReportedNumber | None,
        expected: tuple[float, float] | None,
        title: str,
        evidence: dict[str, object],
        *,
        unverifiable_reason: str | None,
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
                message=f"{title} is compatible with the rounded group summaries.",
            )

        explanation = (
            f"{title} is incompatible with every value reconstructed from the verified rounded group summaries "
            "under the stated formula and test definition."
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
                "reported_decimals": reported.decimals,
                "reported_operator": reported.operator.value,
                "group_a_n": obj.group_a.n,
                "group_b_n": obj.group_b.n,
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

    def _unverifiable(self, obj: TwoGroupComparison, message: str) -> CheckResult:
        return CheckResult(
            self.detector_id,
            "two_group_applicability",
            obj.object_id,
            CheckStatus.UNVERIFIABLE,
            EvidenceFamily.NUMERICAL_CONSISTENCY,
            message=message,
        )
