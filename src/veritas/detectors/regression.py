from __future__ import annotations

from uuid import uuid4

from scipy.stats import norm, t as student_t

from ..models import CheckResult, Finding, RegressionResult, ReportedNumber
from ..types import CheckStatus, ComparisonOperator, EvidenceFamily, EvidenceGrade
from .base import Detector

_EPS = 1e-12


def _intersects(left: tuple[float, float], right: tuple[float, float]) -> bool:
    return max(left[0], right[0]) <= min(left[1], right[1]) + _EPS


def _ratio_interval(numerator: tuple[float, float], denominator: tuple[float, float]) -> tuple[float, float]:
    if denominator[0] <= 0 <= denominator[1]:
        raise ValueError("standard-error interval crosses zero")
    values = [a / b for a in numerator for b in denominator]
    return min(values), max(values)


def _abs_interval(interval: tuple[float, float]) -> tuple[float, float]:
    lo, hi = interval
    if lo <= 0 <= hi:
        return 0.0, max(abs(lo), abs(hi))
    return min(abs(lo), abs(hi)), max(abs(lo), abs(hi))


def _two_sided_p(abs_t: float, distribution: str, df: float | None) -> float:
    if distribution == "normal":
        return float(2.0 * norm.sf(abs_t))
    if distribution == "student_t" and df is not None and df > 0:
        return float(2.0 * student_t.sf(abs_t, df))
    raise ValueError("unsupported p-value distribution")


def _possible_p_interval(t_interval: tuple[float, float], distribution: str, df: float | None) -> tuple[float, float]:
    min_abs, max_abs = _abs_interval(t_interval)
    return _two_sided_p(max_abs, distribution, df), _two_sided_p(min_abs, distribution, df)


def _reported_p_compatible(reported: ReportedNumber, possible: tuple[float, float]) -> bool:
    lo, hi = possible
    if reported.operator is ComparisonOperator.EQ:
        return _intersects(reported.rounding_interval(), possible)
    threshold = reported.value
    if reported.operator in (ComparisonOperator.LT, ComparisonOperator.LE):
        return lo <= threshold + _EPS
    if reported.operator in (ComparisonOperator.GT, ComparisonOperator.GE):
        return hi >= threshold - _EPS
    return False


def _critical_value(level: float, distribution: str, df: float | None) -> float:
    alpha = 1.0 - level
    if not 0.0 < alpha < 1.0:
        raise ValueError("confidence level must be in (0, 1)")
    if distribution == "normal":
        return float(norm.ppf(1.0 - alpha / 2.0))
    if distribution == "student_t" and df is not None and df > 0:
        return float(student_t.ppf(1.0 - alpha / 2.0, df))
    raise ValueError("unsupported confidence-interval distribution")


class RegressionConsistencyDetector(Detector):
    detector_id = "regression_consistency"
    version = "0.1.0"

    def supports(self, obj: object) -> bool:
        return isinstance(obj, RegressionResult)

    def run(self, obj: object) -> list[CheckResult]:
        assert isinstance(obj, RegressionResult)
        checks: list[CheckResult] = []
        if obj.se is None:
            return [self._unverifiable(obj, "beta_se_t", "Standard error is not reported.")]

        se_interval = obj.se.rounding_interval()
        if se_interval[0] <= 0:
            checks.append(self._hard_failure(obj, "se_positive", "Reported standard error is non-positive.", {
                "reported_se": obj.se.value,
            }))
            return checks

        beta_interval = obj.beta.rounding_interval()
        implied_t = _ratio_interval(beta_interval, se_interval)

        if obj.t_stat is None:
            checks.append(self._not_relevant(obj, "beta_se_t", "No t/z statistic is reported, so there is no t/z claim to cross-check."))
        elif _intersects(implied_t, obj.t_stat.rounding_interval()):
            checks.append(self._pass(obj, "beta_se_t", "Reported coefficient, standard error, and t/z statistic are compatible."))
        else:
            checks.append(self._hard_failure(obj, "beta_se_t", "Reported t/z statistic is incompatible with beta / SE after accounting for rounding.", {
                "possible_implied_t": implied_t,
                "reported_t_interval": obj.t_stat.rounding_interval(),
            }))

        checks.extend(self._check_p_value(obj, implied_t))
        checks.extend(self._check_confidence_interval(obj))
        return checks

    def _check_p_value(self, obj: RegressionResult, implied_t: tuple[float, float]) -> list[CheckResult]:
        if obj.p_value is None:
            return [self._not_relevant(obj, "p_value", "No p-value is reported.")]
        if obj.p_value_adjusted:
            return [self._unverifiable(obj, "p_value", "Adjusted p-value is not algebraically comparable to the raw beta/SE statistic.")]
        if obj.inference_distribution == "unknown":
            return [self._unverifiable(obj, "p_value", "Inference distribution is unknown.")]
        if obj.inference_distribution == "student_t" and obj.degrees_of_freedom is None:
            return [self._unverifiable(obj, "p_value", "Student-t inference requires reported degrees of freedom.")]

        try:
            possible_p = _possible_p_interval(implied_t, obj.inference_distribution, obj.degrees_of_freedom)
        except ValueError as exc:
            return [self._unverifiable(obj, "p_value", str(exc))]

        if _reported_p_compatible(obj.p_value, possible_p):
            return [self._pass(obj, "p_value", "Reported p-value is compatible with beta/SE and the stated inference distribution.")]
        return [self._hard_failure(obj, "p_value", "Reported p-value is incompatible with beta/SE under the stated inference procedure.", {
            "possible_p_interval": possible_p,
            "reported_p": obj.p_value.value,
            "operator": obj.p_value.operator.value,
            "distribution": obj.inference_distribution,
            "df": obj.degrees_of_freedom,
        })]

    def _check_confidence_interval(self, obj: RegressionResult) -> list[CheckResult]:
        if obj.ci_lower is None and obj.ci_upper is None:
            return [self._not_relevant(obj, "confidence_interval", "No confidence interval is reported.")]
        if obj.ci_lower is None or obj.ci_upper is None or obj.se is None:
            return [self._unverifiable(obj, "confidence_interval", "Both confidence-interval bounds and SE are required.")]
        if obj.inference_distribution == "unknown":
            return [self._unverifiable(obj, "confidence_interval", "Inference distribution is unknown.")]
        if obj.inference_distribution == "student_t" and obj.degrees_of_freedom is None:
            return [self._unverifiable(obj, "confidence_interval", "Student-t interval requires reported degrees of freedom.")]

        critical = _critical_value(obj.ci_level, obj.inference_distribution, obj.degrees_of_freedom)
        beta_lo, beta_hi = obj.beta.rounding_interval()
        se_lo, se_hi = obj.se.rounding_interval()
        possible_lower = (beta_lo - critical * se_hi, beta_hi - critical * se_lo)
        possible_upper = (beta_lo + critical * se_lo, beta_hi + critical * se_hi)
        lower_ok = _intersects(possible_lower, obj.ci_lower.rounding_interval())
        upper_ok = _intersects(possible_upper, obj.ci_upper.rounding_interval())
        if lower_ok and upper_ok:
            return [self._pass(obj, "confidence_interval", "Reported confidence interval is compatible with beta and SE.")]
        return [self._hard_failure(obj, "confidence_interval", "Reported confidence interval is incompatible with beta and SE after accounting for rounding.", {
            "possible_lower_interval": possible_lower,
            "possible_upper_interval": possible_upper,
            "reported_lower_interval": obj.ci_lower.rounding_interval(),
            "reported_upper_interval": obj.ci_upper.rounding_interval(),
            "level": obj.ci_level,
        })]

    def _pass(self, obj: RegressionResult, check_id: str, message: str) -> CheckResult:
        return CheckResult(self.detector_id, check_id, obj.object_id, CheckStatus.PASS, EvidenceFamily.NUMERICAL_CONSISTENCY, message=message)

    def _not_relevant(self, obj: RegressionResult, check_id: str, message: str) -> CheckResult:
        return CheckResult(self.detector_id, check_id, obj.object_id, CheckStatus.NOT_RELEVANT, EvidenceFamily.NUMERICAL_CONSISTENCY, message=message)

    def _unverifiable(self, obj: RegressionResult, check_id: str, message: str) -> CheckResult:
        return CheckResult(self.detector_id, check_id, obj.object_id, CheckStatus.UNVERIFIABLE, EvidenceFamily.NUMERICAL_CONSISTENCY, message=message)

    def _hard_failure(self, obj: RegressionResult, check_id: str, explanation: str, evidence: dict[str, object]) -> CheckResult:
        finding = Finding(
            finding_id=f"F-{uuid4().hex[:10]}",
            detector_id=f"{self.detector_id}@{self.version}",
            object_id=obj.object_id,
            grade=EvidenceGrade.INTERNAL_CONTRADICTION,
            materiality=obj.materiality,
            family=EvidenceFamily.NUMERICAL_CONSISTENCY,
            title="Regression reporting contradiction",
            explanation=explanation,
            evidence=evidence,
            source=obj.source,
        )
        return CheckResult(self.detector_id, check_id, obj.object_id, CheckStatus.FAIL, EvidenceFamily.NUMERICAL_CONSISTENCY, message=explanation, finding=finding)
