from __future__ import annotations

from itertools import product
from math import inf, sqrt
from uuid import uuid4

from scipy.stats import chi2, norm
from scipy.stats import t as student_t

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
    nonnegative_denominator: tuple[float, float],
) -> tuple[float, float]:
    n_lo, n_hi = numerator
    d_lo, d_hi = nonnegative_denominator
    if d_hi <= 0:
        raise ValueError("denominator upper bound must be positive")
    maximum = inf if d_lo <= 0 else max(abs(n_lo), abs(n_hi)) / d_lo
    if n_lo <= 0 <= n_hi:
        minimum = 0.0
    else:
        minimum = min(abs(n_lo), abs(n_hi)) / d_hi
    return minimum, maximum


def _weighted_residual_ss(values: tuple[float, ...], weights: tuple[float, ...]) -> float:
    total_weight = sum(weights)
    center = sum(weight * value for weight, value in zip(weights, values, strict=True)) / total_weight
    return sum(
        weight * (value - center) ** 2 for weight, value in zip(weights, values, strict=True)
    )


def _minimum_residual_ss(
    effects: tuple[tuple[float, float], ...],
    weights: tuple[tuple[float, float], ...],
) -> float:
    """Safe global lower bound for weighted residual SSE over effect/weight intervals."""

    lower_weights = tuple(bounds[0] for bounds in weights)
    left = min(lo for lo, _ in effects)
    right = max(hi for _, hi in effects)

    def derivative(center: float) -> float:
        total = 0.0
        for weight, (lo, hi) in zip(lower_weights, effects, strict=True):
            if center < lo:
                total += 2.0 * weight * (center - lo)
            elif center > hi:
                total += 2.0 * weight * (center - hi)
        return total

    for _ in range(120):
        midpoint = (left + right) / 2.0
        if derivative(midpoint) < 0:
            left = midpoint
        else:
            right = midpoint
    center = (left + right) / 2.0

    objective = 0.0
    for weight, (lo, hi) in zip(lower_weights, effects, strict=True):
        if center < lo:
            distance = lo - center
        elif center > hi:
            distance = center - hi
        else:
            distance = 0.0
        objective += weight * distance**2
    return max(0.0, objective - _SAFETY_EPS * max(1.0, objective))


def _maximum_residual_ss(
    effects: tuple[tuple[float, float], ...],
    weights: tuple[tuple[float, float], ...],
    *,
    max_vertex_studies: int,
) -> tuple[float, str]:
    """Safe global upper bound for weighted residual SSE over effect/weight intervals."""

    upper_weights = tuple(bounds[1] for bounds in weights)
    if len(effects) <= max_vertex_studies:
        maximum = 0.0
        for choices in product((0, 1), repeat=len(effects)):
            values = tuple(effects[index][choice] for index, choice in enumerate(choices))
            maximum = max(maximum, _weighted_residual_ss(values, upper_weights))
        return maximum + _SAFETY_EPS * max(1.0, maximum), "effect_vertex_enumeration"

    global_lo = min(lo for lo, _ in effects)
    global_hi = max(hi for _, hi in effects)
    span = global_hi - global_lo
    maximum = sum(upper_weights) * span**2 / 4.0
    return maximum + _SAFETY_EPS * max(1.0, maximum), "weighted_popoviciu_range_bound"


class MetaAnalysisArithmeticDetector(Detector):
    """Audit inverse-variance meta-analysis arithmetic under rounding uncertainty."""

    detector_id = "meta_analysis_inverse_variance_arithmetic"
    version = "0.6.0"

    def __init__(self, *, max_hksj_vertex_studies: int = 14) -> None:
        if max_hksj_vertex_studies < 2:
            raise ValueError("max_hksj_vertex_studies must be at least 2")
        self.max_hksj_vertex_studies = max_hksj_vertex_studies

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
        effect_intervals, weight_intervals, tau_interval, relaxation_note = prepared

        pooled_effect = _pooled_effect_bounds(effect_intervals, weight_intervals)
        total_weight_min = sum(bounds[0] for bounds in weight_intervals)
        total_weight_max = sum(bounds[1] for bounds in weight_intervals)
        pooled_se = (sqrt(1.0 / total_weight_max), sqrt(1.0 / total_weight_min))

        common_evidence = {
            "model": obj.model,
            "studies": len(obj.studies),
            "pooled_effect_interval": pooled_effect,
            "pooled_se_interval": pooled_se,
            "tau_squared_interval": tau_interval,
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
            checks.extend(self._normal_inference_checks(obj, pooled_effect, pooled_se, common_evidence))
        elif obj.inference_method in {"hksj", "hksj_modified"}:
            checks.extend(
                self._hksj_inference_checks(
                    obj,
                    effect_intervals,
                    weight_intervals,
                    pooled_effect,
                    common_evidence,
                )
            )
        else:
            reason = (
                "The pooled center and inverse-variance weights can be reconstructed, but this inference path "
                f"({obj.inference_method}) is not implemented."
            )
            for check_id, reported in (
                ("pooled_se", obj.reported_pooled_se),
                ("ci_lower", obj.reported_ci_lower),
                ("ci_upper", obj.reported_ci_upper),
                ("pooled_p_value", obj.reported_pooled_p_value),
                ("hksj_q", obj.reported_hksj_q),
            ):
                checks.append(self._not_relevant_or_unverifiable(obj, check_id, reported, reason))

        checks.extend(self._prediction_interval_checks(obj, pooled_effect, pooled_se, tau_interval, common_evidence))
        checks.extend(self._weight_checks(obj, weight_intervals, common_evidence))
        checks.extend(self._heterogeneity_checks(obj))
        return checks

    def _normal_inference_checks(
        self,
        obj: MetaAnalysisSummary,
        pooled_effect: tuple[float, float],
        pooled_se: tuple[float, float],
        common_evidence: dict[str, object],
    ) -> list[CheckResult]:
        checks = [
            self._check_stat(
                obj,
                "pooled_se",
                obj.reported_pooled_se,
                pooled_se,
                "Reported conventional pooled standard error",
                common_evidence,
            )
        ]
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
        checks.append(
            self._not_relevant_or_unverifiable(
                obj,
                "hksj_q",
                obj.reported_hksj_q,
                "HKSJ q is not part of conventional normal inference.",
            )
        )
        return checks

    def _hksj_inference_checks(
        self,
        obj: MetaAnalysisSummary,
        effects: tuple[tuple[float, float], ...],
        weights: tuple[tuple[float, float], ...],
        pooled_effect: tuple[float, float],
        common_evidence: dict[str, object],
    ) -> list[CheckResult]:
        if not obj.hksj_definition_verified:
            reason = "The exact HKSJ/modified-HKSJ variance definition has not been verified from the paper."
            return [
                self._not_relevant_or_unverifiable(obj, check_id, reported, reason)
                for check_id, reported in (
                    ("hksj_q", obj.reported_hksj_q),
                    ("pooled_se", obj.reported_pooled_se),
                    ("ci_lower", obj.reported_ci_lower),
                    ("ci_upper", obj.reported_ci_upper),
                    ("pooled_p_value", obj.reported_pooled_p_value),
                )
            ]

        k = len(obj.studies)
        residual_min = _minimum_residual_ss(effects, weights)
        residual_max, upper_method = _maximum_residual_ss(
            effects,
            weights,
            max_vertex_studies=self.max_hksj_vertex_studies,
        )
        q_interval = (residual_min / (k - 1), residual_max / (k - 1))
        q_for_variance = q_interval
        if obj.inference_method == "hksj_modified":
            q_for_variance = (max(1.0, q_interval[0]), max(1.0, q_interval[1]))

        total_weight_min = sum(bounds[0] for bounds in weights)
        total_weight_max = sum(bounds[1] for bounds in weights)
        hk_se = (
            sqrt(q_for_variance[0] / total_weight_max),
            sqrt(q_for_variance[1] / total_weight_min),
        )
        df = float(k - 1)
        alpha = 1.0 - obj.confidence_level
        critical = float(student_t.ppf(1.0 - alpha / 2.0, df))
        lower_ci = (
            pooled_effect[0] - critical * hk_se[1],
            pooled_effect[1] - critical * hk_se[0],
        )
        upper_ci = (
            pooled_effect[0] + critical * hk_se[0],
            pooled_effect[1] + critical * hk_se[1],
        )
        hksj_evidence = {
            **common_evidence,
            "residual_ss_interval": (residual_min, residual_max),
            "residual_ss_upper_method": upper_method,
            "hksj_q_interval": q_interval,
            "variance_q_interval": q_for_variance,
            "hksj_df": df,
            "critical_value": critical,
            "inference_method": obj.inference_method,
        }
        checks = [
            self._check_stat(
                obj,
                "hksj_q",
                obj.reported_hksj_q,
                q_interval,
                "Reported HKSJ q scale factor",
                hksj_evidence,
            ),
            self._check_stat(
                obj,
                "pooled_se",
                obj.reported_pooled_se,
                hk_se,
                "Reported HKSJ pooled standard error",
                hksj_evidence,
            ),
            self._check_stat(
                obj,
                "ci_lower",
                obj.reported_ci_lower,
                lower_ci,
                "Reported HKSJ confidence-interval lower endpoint",
                hksj_evidence,
            ),
            self._check_stat(
                obj,
                "ci_upper",
                obj.reported_ci_upper,
                upper_ci,
                "Reported HKSJ confidence-interval upper endpoint",
                hksj_evidence,
            ),
        ]
        if obj.p_value_adjusted:
            checks.append(
                self._unverifiable_check(
                    obj,
                    "pooled_p_value",
                    "The pooled p-value is adjusted; its adjustment rule is not reconstructed here.",
                )
            )
        else:
            absolute_t = _absolute_ratio_bounds(pooled_effect, hk_se)
            pooled_p = (
                float(2.0 * student_t.sf(absolute_t[1], df)),
                float(2.0 * student_t.sf(absolute_t[0], df)),
            )
            checks.append(
                self._check_stat(
                    obj,
                    "pooled_p_value",
                    obj.reported_pooled_p_value,
                    pooled_p,
                    "Reported HKSJ two-sided p-value",
                    hksj_evidence,
                )
            )
        return checks

    def _prediction_interval_checks(
        self,
        obj: MetaAnalysisSummary,
        pooled_effect: tuple[float, float],
        conventional_pooled_se: tuple[float, float],
        tau_interval: tuple[float, float],
        common_evidence: dict[str, object],
    ) -> list[CheckResult]:
        reported = (obj.reported_prediction_lower, obj.reported_prediction_upper)
        if all(value is None for value in reported):
            return []
        if not obj.prediction_method_verified:
            reason = "The exact prediction-interval construction has not been verified from the paper."
            return [
                self._not_relevant_or_unverifiable(obj, check_id, value, reason)
                for check_id, value in zip(("prediction_lower", "prediction_upper"), reported, strict=True)
            ]
        if obj.prediction_method != "hts_t_k_minus_2_conventional":
            reason = f"Prediction method {obj.prediction_method!r} is not implemented."
            return [
                self._not_relevant_or_unverifiable(obj, check_id, value, reason)
                for check_id, value in zip(("prediction_lower", "prediction_upper"), reported, strict=True)
            ]
        if obj.model != "random_inverse_variance_reported_tau2":
            reason = "HTS prediction-interval reconstruction requires a random-effects model with reported tau^2."
            return [
                self._not_relevant_or_unverifiable(obj, check_id, value, reason)
                for check_id, value in zip(("prediction_lower", "prediction_upper"), reported, strict=True)
            ]
        k = len(obj.studies)
        if k < 3:
            reason = "The HTS t_(k-2) prediction interval requires at least three studies."
            return [
                self._not_relevant_or_unverifiable(obj, check_id, value, reason)
                for check_id, value in zip(("prediction_lower", "prediction_upper"), reported, strict=True)
            ]

        df = float(k - 2)
        alpha = 1.0 - obj.prediction_level
        critical = float(student_t.ppf(1.0 - alpha / 2.0, df))
        predictive_sd = (
            sqrt(tau_interval[0] + conventional_pooled_se[0] ** 2),
            sqrt(tau_interval[1] + conventional_pooled_se[1] ** 2),
        )
        half_width = (critical * predictive_sd[0], critical * predictive_sd[1])
        lower = (
            pooled_effect[0] - half_width[1],
            pooled_effect[1] - half_width[0],
        )
        upper = (
            pooled_effect[0] + half_width[0],
            pooled_effect[1] + half_width[1],
        )
        evidence = {
            **common_evidence,
            "prediction_method": obj.prediction_method,
            "prediction_df": df,
            "prediction_critical_value": critical,
            "predictive_sd_interval": predictive_sd,
            "prediction_half_width_interval": half_width,
        }
        return [
            self._check_stat(
                obj,
                "prediction_lower",
                obj.reported_prediction_lower,
                lower,
                "Reported prediction-interval lower endpoint",
                evidence,
            ),
            self._check_stat(
                obj,
                "prediction_upper",
                obj.reported_prediction_upper,
                upper,
                "Reported prediction-interval upper endpoint",
                evidence,
            ),
        ]

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
    ) -> (
        tuple[
            tuple[tuple[float, float], ...],
            tuple[tuple[float, float], ...],
            tuple[float, float],
            str,
        ]
        | CheckResult
    ):
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
        return effects, tuple(weights), (tau_lo, tau_hi), relaxation

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
