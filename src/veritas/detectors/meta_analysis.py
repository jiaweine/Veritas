from __future__ import annotations

from math import sqrt
from uuid import uuid4

from scipy.stats import chi2, norm

from ..meta_analysis import MetaAnalysisSummary
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


def _weighted_average_min(values: tuple[float, ...], weights: tuple[tuple[float, float], ...]) -> float:
    left = min(values)
    right = max(values)
    if right - left <= _TOL:
        return left

    def minimum_centered_sum(center: float) -> float:
        total = 0.0
        for value, (w_lo, w_hi) in zip(values, weights, strict=True):
            coefficient = value - center
            total += (w_hi if coefficient < 0 else w_lo) * coefficient
        return total

    for _ in range(100):
        midpoint = (left + right) / 2.0
        if minimum_centered_sum(midpoint) > 0:
            left = midpoint
        else:
            right = midpoint
    result = (left + right) / 2.0
    return result - _SAFETY_EPS * max(1.0, abs(result))


def _weighted_average_max(values: tuple[float, ...], weights: tuple[tuple[float, float], ...]) -> float:
    left = min(values)
    right = max(values)
    if right - left <= _TOL:
        return right

    def maximum_centered_sum(center: float) -> float:
        total = 0.0
        for value, (w_lo, w_hi) in zip(values, weights, strict=True):
            coefficient = value - center
            total += (w_hi if coefficient > 0 else w_lo) * coefficient
        return total

    for _ in range(100):
        midpoint = (left + right) / 2.0
        if maximum_centered_sum(midpoint) > 0:
            left = midpoint
        else:
            right = midpoint
    result = (left + right) / 2.0
    return result + _SAFETY_EPS * max(1.0, abs(result))


def _pooled_effect_bounds(
    effects: tuple[tuple[float, float], ...],
    weights: tuple[tuple[float, float], ...],
) -> tuple[float, float]:
    lower_values = tuple(interval[0] for interval in effects)
    upper_values = tuple(interval[1] for interval in effects)
    return _weighted_average_min(lower_values, weights), _weighted_average_max(upper_values, weights)


def _absolute_ratio_bounds(
    numerator: tuple[float, float],
    positive_denominator: tuple[float, float],
) -> tuple[float, float]:
    n_lo, n_hi = numerator
    d_lo, d_hi = positive_denominator
    if d_lo <= 0:
        raise ValueError("denominator lower bound must be positive")
    maximum = max(abs(n_lo), abs(n_hi)) / d_lo
    if n_lo <= 0 <= n_hi:
        minimum = 0.0
    else:
        minimum = min(abs(n_lo), abs(n_hi)) / d_hi
    return minimum, maximum


class MetaAnalysisArithmeticDetector(Detector):
    """Audit inverse-variance meta-analysis arithmetic under rounding uncertainty.

    Fixed-effect weights are bounded exactly from each study SE interval. For random
    inverse-variance models with a reported tau^2, Veritas forms a dependency-relaxed
    weight box using the common tau^2 interval. That box is a superset of the true
    feasible weights, so a contradiction outside it remains safe while some genuine
    contradictions may be missed.
    """

    detector_id = "meta_analysis_inverse_variance_arithmetic"
    version = "0.5.0"

    def supports(self, obj: object) -> bool:
        return isinstance(obj, MetaAnalysisSummary)

    def run(self, obj: object) -> list[CheckResult]:
        assert isinstance(obj, MetaAnalysisSummary)
        applicability = self._applicability(obj)
        if applicability is not None:
            return [applicability]

        prepared = self._prepare_weight_bounds(obj)
        if isinstance(prepared, CheckResult):
            return [prepared]
        effect_intervals, weight_intervals, relaxation_note = prepared

        pooled_effect = _pooled_effect_bounds(effect_intervals, weight_intervals)
        total_weight_min = sum(bounds[0] for bounds in weight_intervals)
        total_weight_max = sum(bounds[1] for bounds in weight_intervals)
        pooled_se = (sqrt(1.0 / total_weight_max), sqrt(1.0 / total_weight_min))

        common_evidence = {
            "model": obj.model,
            "studies": len(obj.studies),
            "pooled_effect_interval": pooled_effect,
            "pooled_se_interval": pooled_se,
            "weight_bounds": weight_intervals,
            "relaxation": relaxation_note,
            "algorithm": "rounding-aware inverse-variance linear-fractional bounds",
        }

        checks: list[CheckResult] = [
            self._check_stat(
                obj,
                "pooled_effect",
                obj.reported_pooled_effect,
                pooled_effect,
                "Reported pooled meta-analysis effect",
                common_evidence,
            )
        ]

        if obj.inference_method == "normal":
            checks.append(
                self._check_stat(
                    obj,
                    "pooled_se",
                    obj.reported_pooled_se,
                    pooled_se,
                    "Reported conventional pooled standard error",
                    common_evidence,
                )
            )
            alpha = 1.0 - obj.confidence_level
            critical = float(norm.ppf(1.0 - alpha / 2.0))
            lower_ci = (
                pooled_effect[0] - critical * pooled_se[1],
                pooled_effect[1] - critical * pooled_se[0],
            )
            upper_ci = (
                pooled_effect[0] + critical * pooled_se[0],
                pooled_effect[1] + critical * pooled_se[1],
            )
            checks.extend(
                [
                    self._check_stat(
                        obj,
                        "ci_lower",
                        obj.reported_ci_lower,
                        lower_ci,
                        "Reported pooled confidence-interval lower endpoint",
                        {**common_evidence, "critical_value": critical},
                    ),
                    self._check_stat(
                        obj,
                        "ci_upper",
                        obj.reported_ci_upper,
                        upper_ci,
                        "Reported pooled confidence-interval upper endpoint",
                        {**common_evidence, "critical_value": critical},
                    ),
                ]
            )
            if obj.p_value_adjusted:
                checks.append(
                    self._unverifiable_check(
                        obj,
                        "pooled_p_value",
                        "The pooled p-value is adjusted; its adjustment rule is not reconstructed here.",
                    )
                )
            else:
                absolute_z = _absolute_ratio_bounds(pooled_effect, pooled_se)
                pooled_p = (
                    float(2.0 * norm.sf(absolute_z[1])),
                    float(2.0 * norm.sf(absolute_z[0])),
                )
                checks.append(
                    self._check_stat(
                        obj,
                        "pooled_p_value",
                        obj.reported_pooled_p_value,
                        pooled_p,
                        "Reported pooled two-sided p-value",
                        {**common_evidence, "inference_distribution": "normal"},
                    )
                )
        else:
            reason = (
                "The pooled center and inverse-variance weights can be reconstructed, but this inference path "
                f"({obj.inference_method}) is not treated as conventional normal inference."
            )
            for check_id, reported in (
                ("pooled_se", obj.reported_pooled_se),
                ("ci_lower", obj.reported_ci_lower),
                ("ci_upper", obj.reported_ci_upper),
                ("pooled_p_value", obj.reported_pooled_p_value),
            ):
                checks.append(
                    self._not_relevant_or_unverifiable(obj, check_id, reported, reason)
                )

        checks.extend(self._weight_checks(obj, weight_intervals, common_evidence))
        checks.extend(self._heterogeneity_checks(obj))
        return checks

    def _applicability(self, obj: MetaAnalysisSummary) -> CheckResult | None:
        if not obj.effects_on_common_analysis_scale_verified:
            return self._unverifiable(obj, "Study effects are not verified to share one additive analysis scale.")
        if not obj.independent_effects_verified:
            return self._unverifiable(obj, "The supplied study effects are not verified as independent inputs.")
        if not obj.inverse_variance_weighting_verified:
            return self._unverifiable(obj, "Inverse-variance weighting has not been verified.")
        if obj.model not in {"fixed_inverse_variance", "random_inverse_variance_reported_tau2"}:
            return self._unverifiable(obj, "The meta-analysis model is outside the supported inverse-variance paths.")
        for study in obj.studies:
            if study.effect.operator is not ComparisonOperator.EQ or study.se.operator is not ComparisonOperator.EQ:
                return self._unverifiable(obj, "Study effects and SEs must be equality-reported values.")
            se_lo, _ = study.se.rounding_interval()
            if se_lo <= 0:
                return self._unverifiable(obj, "A study SE rounding interval includes zero, so weights are unbounded.")
        return None

    def _prepare_weight_bounds(
        self,
        obj: MetaAnalysisSummary,
    ) -> tuple[tuple[tuple[float, float], ...], tuple[tuple[float, float], ...], str] | CheckResult:
        effects = tuple(study.effect.rounding_interval() for study in obj.studies)
        tau_lo = tau_hi = 0.0
        relaxation = "none_fixed_effect"

        if obj.model == "random_inverse_variance_reported_tau2":
            tau = obj.reported_tau_squared
            if tau is None:
                return self._unverifiable(obj, "Random-effects weight reconstruction requires reported tau^2.")
            if tau.operator is not ComparisonOperator.EQ:
                return self._unverifiable(obj, "Reported tau^2 must be an equality value for rounding reconstruction.")
            raw_lo, raw_hi = tau.rounding_interval()
            if raw_hi < 0:
                return self._hard_contradiction(
                    obj,
                    "tau_squared",
                    "The entire reported rounding interval for tau^2 is negative, but a variance cannot be negative.",
                    {"reported_tau_squared_interval": (raw_lo, raw_hi)},
                )
            tau_lo = max(0.0, raw_lo)
            tau_hi = max(0.0, raw_hi)
            relaxation = "common_tau2_dependency_relaxed_to_independent_weight_bounds"

        weights = []
        for study in obj.studies:
            se_lo, se_hi = study.se.rounding_interval()
            weight_lo = 1.0 / (se_hi**2 + tau_hi)
            weight_hi = 1.0 / (se_lo**2 + tau_lo)
            weights.append((weight_lo, weight_hi))
        return effects, tuple(weights), relaxation

    def _weight_checks(
        self,
        obj: MetaAnalysisSummary,
        weights: tuple[tuple[float, float], ...],
        common_evidence: dict[str, object],
    ) -> list[CheckResult]:
        checks = []
        for index, study in enumerate(obj.studies):
            reported = study.reported_weight_percent
            if reported is None:
                checks.append(
                    CheckResult(
                        self.detector_id,
                        f"weight_percent:{study.study_id}",
                        obj.object_id,
                        CheckStatus.NOT_RELEVANT,
                        EvidenceFamily.NUMERICAL_CONSISTENCY,
                        message=f"Meta-analysis weight for {study.study_id} was not reported.",
                    )
                )
                continue
            w_lo, w_hi = weights[index]
            others_hi = sum(bounds[1] for j, bounds in enumerate(weights) if j != index)
            others_lo = sum(bounds[0] for j, bounds in enumerate(weights) if j != index)
            expected = (
                100.0 * w_lo / (w_lo + others_hi),
                100.0 * w_hi / (w_hi + others_lo),
            )
            checks.append(
                self._check_stat(
                    obj,
                    f"weight_percent:{study.study_id}",
                    reported,
                    expected,
                    f"Reported meta-analysis weight for {study.study_id}",
                    {**common_evidence, "study_id": study.study_id},
                )
            )
        return checks

    def _heterogeneity_checks(self, obj: MetaAnalysisSummary) -> list[CheckResult]:
        reported_any = any(
            value is not None
            for value in (obj.reported_q, obj.reported_q_df, obj.reported_q_p_value, obj.reported_i_squared)
        )
        if not reported_any:
            return []
        if not obj.q_definition_verified:
            return [
                self._not_relevant_or_unverifiable(
                    obj,
                    "heterogeneity",
                    obj.reported_q or obj.reported_i_squared or obj.reported_q_p_value or obj.reported_q_df,
                    "Cochran Q/I-squared semantics have not been verified for the reported heterogeneity statistics.",
                )
            ]

        df = float(len(obj.studies) - 1)
        checks = [
            self._check_stat(
                obj,
                "q_df",
                obj.reported_q_df,
                (df, df),
                "Reported Cochran Q degrees of freedom",
                {"studies": len(obj.studies), "formula": "k - 1"},
            )
        ]
        if obj.reported_q is None:
            for check_id, reported in (
                ("q_p_value", obj.reported_q_p_value),
                ("i_squared", obj.reported_i_squared),
            ):
                checks.append(
                    self._not_relevant_or_unverifiable(
                        obj,
                        check_id,
                        reported,
                        "Cochran Q was not reported, so this heterogeneity statistic cannot be reconstructed paper-only.",
                    )
                )
            return checks

        q_lo, q_hi = obj.reported_q.rounding_interval()
        if q_hi < 0:
            checks.append(
                self._hard_contradiction(
                    obj,
                    "q_statistic",
                    "The entire reported rounding interval for Cochran Q is negative.",
                    {"reported_q_interval": (q_lo, q_hi)},
                )
            )
            return checks
        q_interval = (max(0.0, q_lo), max(0.0, q_hi))
        q_p = (
            float(chi2.sf(q_interval[1], df)),
            float(chi2.sf(q_interval[0], df)),
        )
        checks.append(
            self._check_stat(
                obj,
                "q_p_value",
                obj.reported_q_p_value,
                q_p,
                "Reported Cochran Q p-value",
                {"q_interval": q_interval, "q_df": df},
            )
        )

        def i_squared(q: float) -> float:
            if q <= df or q <= 0:
                return 0.0
            return 100.0 * (q - df) / q

        i2 = (i_squared(q_interval[0]), i_squared(q_interval[1]))
        checks.append(
            self._check_stat(
                obj,
                "i_squared",
                obj.reported_i_squared,
                i2,
                "Reported I-squared",
                {"q_interval": q_interval, "q_df": df, "formula": "max(0, (Q-df)/Q) * 100"},
            )
        )
        return checks

    def _check_stat(
        self,
        obj: MetaAnalysisSummary,
        check_id: str,
        reported: ReportedNumber | None,
        expected: tuple[float, float],
        title: str,
        evidence: dict[str, object],
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
        if _reported_compatible(reported, expected):
            return CheckResult(
                self.detector_id,
                check_id,
                obj.object_id,
                CheckStatus.PASS,
                EvidenceFamily.NUMERICAL_CONSISTENCY,
                message=f"{title} is compatible with the rounding-aware meta-analysis constraints.",
            )
        explanation = f"{title} is outside every value allowed by the verified rounding-aware reconstruction."
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

    def _hard_contradiction(
        self,
        obj: MetaAnalysisSummary,
        check_id: str,
        explanation: str,
        evidence: dict[str, object],
    ) -> CheckResult:
        finding = Finding(
            finding_id=f"F-{uuid4().hex[:10]}",
            detector_id=f"{self.detector_id}@{self.version}",
            object_id=obj.object_id,
            grade=EvidenceGrade.INTERNAL_CONTRADICTION,
            materiality=obj.materiality,
            family=EvidenceFamily.NUMERICAL_CONSISTENCY,
            title="Meta-analysis reporting contradiction",
            explanation=explanation,
            evidence=evidence,
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

    def _not_relevant_or_unverifiable(
        self,
        obj: MetaAnalysisSummary,
        check_id: str,
        reported: ReportedNumber | None,
        reason: str,
    ) -> CheckResult:
        if reported is None:
            return CheckResult(
                self.detector_id,
                check_id,
                obj.object_id,
                CheckStatus.NOT_RELEVANT,
                EvidenceFamily.NUMERICAL_CONSISTENCY,
                message="The statistic was not reported.",
            )
        return self._unverifiable_check(obj, check_id, reason)

    def _unverifiable_check(self, obj: MetaAnalysisSummary, check_id: str, message: str) -> CheckResult:
        return CheckResult(
            self.detector_id,
            check_id,
            obj.object_id,
            CheckStatus.UNVERIFIABLE,
            EvidenceFamily.NUMERICAL_CONSISTENCY,
            message=message,
        )

    def _unverifiable(self, obj: MetaAnalysisSummary, message: str) -> CheckResult:
        return self._unverifiable_check(obj, "meta_analysis_applicability", message)
