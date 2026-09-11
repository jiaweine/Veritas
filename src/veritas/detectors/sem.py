from __future__ import annotations

from math import log, sqrt
from uuid import uuid4

from scipy.stats import chi2

from ..models import CheckResult, Finding, ReportedNumber
from ..sem import SEMFitSummary, SEMNestedComparison
from ..types import CheckStatus, ComparisonOperator, EvidenceFamily, EvidenceGrade
from .base import Detector

_TOL = 1e-10


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


def _sub_interval(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    return a[0] - b[1], a[1] - b[0]


class SEMFitArithmeticDetector(Detector):
    """Audit conventional unscaled SEM/CFA fit statistics under rounding uncertainty."""

    detector_id = "sem_fit_arithmetic"
    version = "0.7.0"

    def supports(self, obj: object) -> bool:
        return isinstance(obj, SEMFitSummary)

    def run(self, obj: object) -> list[CheckResult]:
        assert isinstance(obj, SEMFitSummary)
        if obj.chi_square.operator is not ComparisonOperator.EQ:
            return [self._unverifiable(obj, "SEM model chi-square must be equality-reported for reconstruction.")]

        raw_chi = obj.chi_square.rounding_interval()
        if raw_chi[1] < 0:
            return [
                self._hard_contradiction(
                    obj,
                    "chi_square",
                    "The entire reported rounding interval for the SEM chi-square is negative.",
                    {"reported_chi_square_interval": raw_chi},
                )
            ]
        chi_interval = (max(0.0, raw_chi[0]), max(0.0, raw_chi[1]))
        common = {
            "estimator_path": obj.estimator_path,
            "chi_square_interval": chi_interval,
            "degrees_of_freedom": obj.degrees_of_freedom,
        }
        checks: list[CheckResult] = []

        if obj.unscaled_fit_statistics_verified and obj.estimator_path == "ml_unscaled":
            checks.append(self._chi_square_p_check(obj, chi_interval, common))
            checks.append(self._rmsea_check(obj, chi_interval, common))
            checks.extend(self._incremental_fit_checks(obj, chi_interval, common))
        else:
            reason = (
                "Conventional unscaled ML fit-statistic semantics have not been verified. Robust/scaled/WLSMV "
                "fit indices require estimator-specific formulas."
            )
            for check_id, reported in (
                ("model_p_value", obj.reported_p_value),
                ("rmsea", obj.reported_rmsea),
                ("cfi", obj.reported_cfi),
                ("tli", obj.reported_tli),
            ):
                checks.append(self._not_relevant_or_unverifiable(obj, check_id, reported, reason))

        checks.extend(self._information_criteria_checks(obj, common))
        return checks

    def _chi_square_p_check(
        self,
        obj: SEMFitSummary,
        chi_interval: tuple[float, float],
        common: dict[str, object],
    ) -> CheckResult:
        if obj.degrees_of_freedom <= 0:
            return self._not_relevant_or_unverifiable(
                obj,
                "model_p_value",
                obj.reported_p_value,
                "A positive chi-square reference degrees of freedom is required for the model-fit p-value.",
            )
        expected = (
            float(chi2.sf(chi_interval[1], obj.degrees_of_freedom)),
            float(chi2.sf(chi_interval[0], obj.degrees_of_freedom)),
        )
        return self._check_stat(
            obj,
            "model_p_value",
            obj.reported_p_value,
            expected,
            "Reported SEM model-fit chi-square p-value",
            common,
        )

    def _rmsea_check(
        self,
        obj: SEMFitSummary,
        chi_interval: tuple[float, float],
        common: dict[str, object],
    ) -> CheckResult:
        if obj.reported_rmsea is None:
            return self._not_relevant_or_unverifiable(obj, "rmsea", None, "RMSEA was not reported.")
        if obj.degrees_of_freedom <= 0 or obj.n_observations is None:
            return self._unverifiable_check(
                obj,
                "rmsea",
                "RMSEA reconstruction requires positive model df and a verified sample size.",
            )
        if obj.rmsea_sample_size_basis == "n":
            denominator_n = obj.n_observations
        elif obj.rmsea_sample_size_basis == "n_minus_1":
            denominator_n = obj.n_observations - 1
        else:
            return self._unverifiable_check(
                obj,
                "rmsea",
                "The paper/software convention for RMSEA sample-size scaling (N versus N-1) is not verified.",
            )
        if denominator_n <= 0:
            return self._unverifiable_check(obj, "rmsea", "The RMSEA sample-size denominator is not positive.")

        def rmsea(chi_square: float) -> float:
            excess = (chi_square - obj.degrees_of_freedom) / (
                obj.degrees_of_freedom * denominator_n
            )
            return sqrt(max(0.0, excess))

        expected = (rmsea(chi_interval[0]), rmsea(chi_interval[1]))
        return self._check_stat(
            obj,
            "rmsea",
            obj.reported_rmsea,
            expected,
            "Reported RMSEA",
            {
                **common,
                "n_observations": obj.n_observations,
                "rmsea_sample_size_basis": obj.rmsea_sample_size_basis,
                "formula": "sqrt(max((chi_square-df)/(df*N_basis), 0))",
            },
        )

    def _incremental_fit_checks(
        self,
        obj: SEMFitSummary,
        chi_interval: tuple[float, float],
        common: dict[str, object],
    ) -> list[CheckResult]:
        reported_any = obj.reported_cfi is not None or obj.reported_tli is not None
        if not reported_any:
            return []
        if (
            not obj.baseline_model_verified
            or obj.baseline_chi_square is None
            or obj.baseline_degrees_of_freedom is None
            or obj.baseline_degrees_of_freedom <= 0
            or obj.degrees_of_freedom <= 0
        ):
            reason = "CFI/TLI reconstruction requires a verified baseline-model chi-square and positive df values."
            return [
                self._not_relevant_or_unverifiable(obj, check_id, reported, reason)
                for check_id, reported in (("cfi", obj.reported_cfi), ("tli", obj.reported_tli))
            ]
        if obj.baseline_chi_square.operator is not ComparisonOperator.EQ:
            reason = "Baseline chi-square must be equality-reported for CFI/TLI rounding reconstruction."
            return [
                self._not_relevant_or_unverifiable(obj, check_id, reported, reason)
                for check_id, reported in (("cfi", obj.reported_cfi), ("tli", obj.reported_tli))
            ]

        raw_baseline = obj.baseline_chi_square.rounding_interval()
        if raw_baseline[1] < 0:
            return [
                self._hard_contradiction(
                    obj,
                    "baseline_chi_square",
                    "The entire reported rounding interval for the baseline-model chi-square is negative.",
                    {"reported_baseline_chi_square_interval": raw_baseline},
                )
            ]
        baseline = (max(0.0, raw_baseline[0]), max(0.0, raw_baseline[1]))
        target_misfit = (
            max(0.0, chi_interval[0] - obj.degrees_of_freedom),
            max(0.0, chi_interval[1] - obj.degrees_of_freedom),
        )
        baseline_misfit = (
            max(0.0, baseline[0] - obj.baseline_degrees_of_freedom),
            max(0.0, baseline[1] - obj.baseline_degrees_of_freedom),
        )
        evidence = {
            **common,
            "baseline_chi_square_interval": baseline,
            "baseline_degrees_of_freedom": obj.baseline_degrees_of_freedom,
            "target_noncentrality_interval": target_misfit,
            "baseline_noncentrality_interval": baseline_misfit,
        }

        checks: list[CheckResult] = []
        if baseline_misfit[0] <= 0:
            checks.append(
                self._not_relevant_or_unverifiable(
                    obj,
                    "cfi",
                    obj.reported_cfi,
                    "The rounded baseline noncentrality interval includes zero, so CFI is not stably identified.",
                )
            )
        else:
            def cfi(target: float, base: float) -> float:
                denominator = max(target, base)
                if denominator <= 0:
                    return 1.0
                return 1.0 - target / denominator

            cfi_values = [
                cfi(target, base)
                for target in target_misfit
                for base in baseline_misfit
            ]
            checks.append(
                self._check_stat(
                    obj,
                    "cfi",
                    obj.reported_cfi,
                    (min(cfi_values), max(cfi_values)),
                    "Reported Comparative Fit Index (CFI)",
                    {**evidence, "formula": "1 - max(chi_t-df_t,0)/max(chi_t-df_t,chi_b-df_b,0)"},
                )
            )

        baseline_ratio = (
            baseline[0] / obj.baseline_degrees_of_freedom,
            baseline[1] / obj.baseline_degrees_of_freedom,
        )
        target_ratio = (
            chi_interval[0] / obj.degrees_of_freedom,
            chi_interval[1] / obj.degrees_of_freedom,
        )
        if baseline_ratio[0] <= 1.0 + _TOL:
            checks.append(
                self._not_relevant_or_unverifiable(
                    obj,
                    "tli",
                    obj.reported_tli,
                    "The rounded baseline chi-square/df interval reaches 1, making the conventional TLI denominator unstable.",
                )
            )
        else:
            def tli(target: float, base: float) -> float:
                return (base - target) / (base - 1.0)

            tli_values = [tli(target, base) for target in target_ratio for base in baseline_ratio]
            checks.append(
                self._check_stat(
                    obj,
                    "tli",
                    obj.reported_tli,
                    (min(tli_values), max(tli_values)),
                    "Reported Tucker-Lewis Index (TLI)",
                    {**evidence, "formula": "(chi_b/df_b - chi_t/df_t)/(chi_b/df_b - 1)"},
                )
            )
        return checks

    def _information_criteria_checks(
        self,
        obj: SEMFitSummary,
        common: dict[str, object],
    ) -> list[CheckResult]:
        reported_any = obj.reported_aic is not None or obj.reported_bic is not None
        if not reported_any:
            return []
        if obj.information_criteria_definition != "standard_ml":
            reason = "The paper/software AIC/BIC definition is not verified as the standard ML information criterion."
            return [
                self._not_relevant_or_unverifiable(obj, check_id, reported, reason)
                for check_id, reported in (("aic", obj.reported_aic), ("bic", obj.reported_bic))
            ]
        if obj.log_likelihood is None or obj.free_parameters is None:
            reason = "AIC/BIC reconstruction requires the model log-likelihood and number of free parameters."
            return [
                self._not_relevant_or_unverifiable(obj, check_id, reported, reason)
                for check_id, reported in (("aic", obj.reported_aic), ("bic", obj.reported_bic))
            ]
        if obj.log_likelihood.operator is not ComparisonOperator.EQ:
            reason = "The model log-likelihood must be equality-reported for AIC/BIC rounding reconstruction."
            return [
                self._not_relevant_or_unverifiable(obj, check_id, reported, reason)
                for check_id, reported in (("aic", obj.reported_aic), ("bic", obj.reported_bic))
            ]

        ll_lo, ll_hi = obj.log_likelihood.rounding_interval()
        aic = (-2.0 * ll_hi + 2.0 * obj.free_parameters, -2.0 * ll_lo + 2.0 * obj.free_parameters)
        checks = [
            self._check_stat(
                obj,
                "aic",
                obj.reported_aic,
                aic,
                "Reported Akaike Information Criterion (AIC)",
                {**common, "log_likelihood_interval": (ll_lo, ll_hi), "free_parameters": obj.free_parameters},
            )
        ]
        if obj.n_observations is None:
            checks.append(
                self._not_relevant_or_unverifiable(
                    obj,
                    "bic",
                    obj.reported_bic,
                    "BIC reconstruction requires the sample size used by the information criterion.",
                )
            )
        else:
            penalty = obj.free_parameters * log(obj.n_observations)
            bic = (-2.0 * ll_hi + penalty, -2.0 * ll_lo + penalty)
            checks.append(
                self._check_stat(
                    obj,
                    "bic",
                    obj.reported_bic,
                    bic,
                    "Reported Bayesian Information Criterion (BIC)",
                    {
                        **common,
                        "log_likelihood_interval": (ll_lo, ll_hi),
                        "free_parameters": obj.free_parameters,
                        "n_observations": obj.n_observations,
                    },
                )
            )
        return checks

    def _check_stat(
        self,
        obj: SEMFitSummary,
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
                message=f"{title} is compatible with the verified rounding-aware SEM constraints.",
            )
        explanation = f"{title} is incompatible with every value allowed by the verified SEM reconstruction."
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
        obj: SEMFitSummary,
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
            title="SEM reporting contradiction",
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
        obj: SEMFitSummary,
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

    def _unverifiable_check(self, obj: SEMFitSummary, check_id: str, message: str) -> CheckResult:
        return CheckResult(
            self.detector_id,
            check_id,
            obj.object_id,
            CheckStatus.UNVERIFIABLE,
            EvidenceFamily.NUMERICAL_CONSISTENCY,
            message=message,
        )

    def _unverifiable(self, obj: SEMFitSummary, message: str) -> CheckResult:
        return self._unverifiable_check(obj, "sem_fit_applicability", message)


class SEMNestedDifferenceDetector(Detector):
    """Audit ordinary unscaled ML chi-square difference tests for verified nested SEM models."""

    detector_id = "sem_nested_difference_arithmetic"
    version = "0.7.0"

    def supports(self, obj: object) -> bool:
        return isinstance(obj, SEMNestedComparison)

    def run(self, obj: object) -> list[CheckResult]:
        assert isinstance(obj, SEMNestedComparison)
        if (
            obj.difference_method != "plain_unscaled_ml"
            or not obj.unscaled_ml_difference_verified
            or not obj.nested_models_verified
            or not obj.same_sample_verified
        ):
            reason = (
                "Direct chi-square subtraction is only implemented for verified ordinary unscaled ML nested-model "
                "comparisons. Scaled/robust/WLSMV difference tests require correction factors or DIFFTEST output."
            )
            return [
                self._not_relevant_or_unverifiable(obj, check_id, reported, reason)
                for check_id, reported in (
                    ("delta_chi_square", obj.reported_delta_chi_square),
                    ("delta_df", obj.reported_delta_df),
                    ("delta_p_value", obj.reported_delta_p_value),
                )
            ]
        if (
            obj.less_restricted_chi_square.operator is not ComparisonOperator.EQ
            or obj.more_restricted_chi_square.operator is not ComparisonOperator.EQ
        ):
            return [
                self._unverifiable_check(
                    obj,
                    "nested_difference",
                    "Both nested-model chi-square values must be equality-reported for rounding reconstruction.",
                )
            ]

        less = obj.less_restricted_chi_square.rounding_interval()
        more = obj.more_restricted_chi_square.rounding_interval()
        delta = _sub_interval(more, less)
        delta_df = obj.more_restricted_df - obj.less_restricted_df
        if delta_df <= 0:
            return [
                self._hard_contradiction(
                    obj,
                    "delta_df",
                    "The model labeled more restrictive does not have more degrees of freedom.",
                    {
                        "less_restricted_df": obj.less_restricted_df,
                        "more_restricted_df": obj.more_restricted_df,
                    },
                )
            ]

        evidence = {
            "less_restricted_chi_square_interval": less,
            "more_restricted_chi_square_interval": more,
            "delta_chi_square_interval": delta,
            "delta_df": delta_df,
            "difference_method": obj.difference_method,
        }
        checks = [
            self._check_stat(
                obj,
                "delta_chi_square",
                obj.reported_delta_chi_square,
                delta,
                "Reported nested-model chi-square difference",
                evidence,
            ),
            self._check_stat(
                obj,
                "delta_df",
                obj.reported_delta_df,
                (float(delta_df), float(delta_df)),
                "Reported nested-model degrees-of-freedom difference",
                evidence,
            ),
        ]
        nonnegative_delta = (max(0.0, delta[0]), max(0.0, delta[1]))
        expected_p = (
            float(chi2.sf(nonnegative_delta[1], delta_df)),
            float(chi2.sf(nonnegative_delta[0], delta_df)),
        )
        checks.append(
            self._check_stat(
                obj,
                "delta_p_value",
                obj.reported_delta_p_value,
                expected_p,
                "Reported nested-model chi-square difference p-value",
                evidence,
            )
        )
        return checks

    def _check_stat(
        self,
        obj: SEMNestedComparison,
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
                message=f"{title} is compatible with the verified nested-model arithmetic.",
            )
        explanation = f"{title} is incompatible with every rounding-compatible ordinary ML difference."
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
        obj: SEMNestedComparison,
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
            title="Nested SEM reporting contradiction",
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
        obj: SEMNestedComparison,
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

    def _unverifiable_check(self, obj: SEMNestedComparison, check_id: str, message: str) -> CheckResult:
        return CheckResult(
            self.detector_id,
            check_id,
            obj.object_id,
            CheckStatus.UNVERIFIABLE,
            EvidenceFamily.NUMERICAL_CONSISTENCY,
            message=message,
        )
