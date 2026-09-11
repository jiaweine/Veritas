from __future__ import annotations

from math import log, sqrt
from random import Random

from scipy.stats import chi2

from veritas.detectors.sem import SEMFitArithmeticDetector, SEMNestedDifferenceDetector
from veritas.models import ReportedNumber
from veritas.sem import SEMFitSummary, SEMNestedComparison
from veritas.types import CheckStatus, EvidenceGrade


def _rn(value: float, decimals: int = 3) -> ReportedNumber:
    return ReportedNumber(round(value, decimals), decimals=decimals)


def _lavaan_example(**overrides) -> SEMFitSummary:
    values = {
        "object_id": "lavaan-hs",
        "chi_square": _rn(85.306),
        "degrees_of_freedom": 24,
        "reported_p_value": _rn(float(chi2.sf(85.306, 24))),
        "n_observations": 301,
        "reported_rmsea": _rn(0.092, 3),
        "rmsea_sample_size_basis": "n",
        "baseline_chi_square": _rn(918.852),
        "baseline_degrees_of_freedom": 36,
        "reported_cfi": _rn(0.931),
        "reported_tli": _rn(0.896),
        "log_likelihood": _rn(-3737.745),
        "free_parameters": 21,
        "reported_aic": _rn(7517.490),
        "reported_bic": _rn(7595.339),
        "estimator_path": "ml_unscaled",
        "unscaled_fit_statistics_verified": True,
        "baseline_model_verified": True,
        "information_criteria_definition": "standard_ml",
    }
    values.update(overrides)
    return SEMFitSummary(**values)


def test_current_lavaan_cfa_example_passes_rounding_aware_reconstruction():
    by_id = {result.check_id: result for result in SEMFitArithmeticDetector().run(_lavaan_example())}
    for check_id in ("model_p_value", "rmsea", "cfi", "tli", "aic", "bic"):
        assert by_id[check_id].status is CheckStatus.PASS


def test_impossible_cfi_is_internal_contradiction():
    summary = _lavaan_example(reported_cfi=ReportedNumber(0.700, decimals=3))
    result = next(item for item in SEMFitArithmeticDetector().run(summary) if item.check_id == "cfi")
    assert result.status is CheckStatus.FAIL
    assert result.finding is not None
    assert result.finding.grade is EvidenceGrade.INTERNAL_CONTRADICTION


def test_rmsea_sample_size_convention_must_be_verified():
    summary = _lavaan_example(rmsea_sample_size_basis="unknown")
    result = next(item for item in SEMFitArithmeticDetector().run(summary) if item.check_id == "rmsea")
    assert result.status is CheckStatus.UNVERIFIABLE


def test_robust_scaled_fit_indices_are_not_forced_through_plain_ml_formulas():
    summary = _lavaan_example(
        estimator_path="robust_scaled",
        unscaled_fit_statistics_verified=False,
        information_criteria_definition="unknown",
    )
    by_id = {result.check_id: result for result in SEMFitArithmeticDetector().run(summary)}
    for check_id in ("model_p_value", "rmsea", "cfi", "tli", "aic", "bic"):
        assert by_id[check_id].status is CheckStatus.UNVERIFIABLE


def test_plain_unscaled_nested_model_difference_passes():
    delta = 92.500 - 85.306
    summary = SEMNestedComparison(
        object_id="nested-ml",
        less_restricted_chi_square=_rn(85.306),
        less_restricted_df=24,
        more_restricted_chi_square=_rn(92.500),
        more_restricted_df=27,
        reported_delta_chi_square=_rn(delta),
        reported_delta_df=ReportedNumber(3.0, decimals=0),
        reported_delta_p_value=_rn(float(chi2.sf(delta, 3))),
        difference_method="plain_unscaled_ml",
        nested_models_verified=True,
        same_sample_verified=True,
        unscaled_ml_difference_verified=True,
    )
    by_id = {result.check_id: result for result in SEMNestedDifferenceDetector().run(summary)}
    assert by_id["delta_chi_square"].status is CheckStatus.PASS
    assert by_id["delta_df"].status is CheckStatus.PASS
    assert by_id["delta_p_value"].status is CheckStatus.PASS


def test_scaled_nested_chi_square_is_never_naively_subtracted():
    summary = SEMNestedComparison(
        object_id="nested-scaled",
        less_restricted_chi_square=_rn(80.0),
        less_restricted_df=20,
        more_restricted_chi_square=_rn(90.0),
        more_restricted_df=25,
        reported_delta_chi_square=_rn(10.0),
        reported_delta_df=ReportedNumber(5.0, decimals=0),
        reported_delta_p_value=_rn(float(chi2.sf(10.0, 5))),
        difference_method="scaled_or_robust",
        nested_models_verified=True,
        same_sample_verified=True,
        unscaled_ml_difference_verified=False,
    )
    results = SEMNestedDifferenceDetector().run(summary)
    assert results
    assert all(result.status is CheckStatus.UNVERIFIABLE for result in results)


def test_more_restrictive_model_must_have_more_df_when_plain_difference_is_verified():
    summary = SEMNestedComparison(
        object_id="nested-bad-df",
        less_restricted_chi_square=_rn(80.0),
        less_restricted_df=25,
        more_restricted_chi_square=_rn(90.0),
        more_restricted_df=20,
        difference_method="plain_unscaled_ml",
        nested_models_verified=True,
        same_sample_verified=True,
        unscaled_ml_difference_verified=True,
    )
    result = SEMNestedDifferenceDetector().run(summary)[0]
    assert result.status is CheckStatus.FAIL
    assert result.finding is not None
    assert result.finding.grade is EvidenceGrade.INTERNAL_CONTRADICTION


def test_constructive_sem_fit_tables_do_not_false_alert_after_rounding():
    rng = Random(20260902)
    detector = SEMFitArithmeticDetector()
    for case_index in range(48):
        df = rng.randint(2, 80)
        n = rng.randint(120, 1500)
        target_ratio = rng.uniform(1.05, 4.5)
        chi_square_value = df * target_ratio
        baseline_df = df + rng.randint(5, 80)
        baseline_ratio = target_ratio + rng.uniform(2.0, 18.0)
        baseline_chi = baseline_df * baseline_ratio
        denominator_n = n if case_index % 2 == 0 else n - 1
        basis = "n" if case_index % 2 == 0 else "n_minus_1"
        rmsea = sqrt(max((chi_square_value - df) / (df * denominator_n), 0.0))
        target_misfit = max(chi_square_value - df, 0.0)
        baseline_misfit = max(baseline_chi - baseline_df, 0.0)
        cfi = 1.0 - target_misfit / max(target_misfit, baseline_misfit)
        tli = (baseline_chi / baseline_df - chi_square_value / df) / (
            baseline_chi / baseline_df - 1.0
        )
        free_parameters = rng.randint(5, 80)
        log_likelihood = -rng.uniform(500.0, 8000.0)
        aic = -2.0 * log_likelihood + 2.0 * free_parameters
        bic = -2.0 * log_likelihood + free_parameters * log(n)

        summary = SEMFitSummary(
            object_id=f"constructive-sem-{case_index}",
            chi_square=_rn(chi_square_value),
            degrees_of_freedom=df,
            reported_p_value=_rn(float(chi2.sf(chi_square_value, df))),
            n_observations=n,
            reported_rmsea=_rn(rmsea),
            rmsea_sample_size_basis=basis,
            baseline_chi_square=_rn(baseline_chi),
            baseline_degrees_of_freedom=baseline_df,
            reported_cfi=_rn(cfi),
            reported_tli=_rn(tli),
            log_likelihood=_rn(log_likelihood),
            free_parameters=free_parameters,
            reported_aic=_rn(aic),
            reported_bic=_rn(bic),
            estimator_path="ml_unscaled",
            unscaled_fit_statistics_verified=True,
            baseline_model_verified=True,
            information_criteria_definition="standard_ml",
        )
        failures = [result for result in detector.run(summary) if result.status is CheckStatus.FAIL]
        assert not failures, (case_index, failures)


def test_constructive_nested_ml_differences_do_not_false_alert_after_rounding():
    rng = Random(20260903)
    detector = SEMNestedDifferenceDetector()
    for case_index in range(36):
        less_df = rng.randint(5, 80)
        delta_df = rng.randint(1, 12)
        less_chi = rng.uniform(less_df * 0.8, less_df * 4.0)
        delta_chi = rng.uniform(0.2, 30.0)
        more_chi = less_chi + delta_chi
        summary = SEMNestedComparison(
            object_id=f"constructive-nested-{case_index}",
            less_restricted_chi_square=_rn(less_chi),
            less_restricted_df=less_df,
            more_restricted_chi_square=_rn(more_chi),
            more_restricted_df=less_df + delta_df,
            reported_delta_chi_square=_rn(delta_chi),
            reported_delta_df=ReportedNumber(float(delta_df), decimals=0),
            reported_delta_p_value=_rn(float(chi2.sf(delta_chi, delta_df))),
            difference_method="plain_unscaled_ml",
            nested_models_verified=True,
            same_sample_verified=True,
            unscaled_ml_difference_verified=True,
        )
        failures = [result for result in detector.run(summary) if result.status is CheckStatus.FAIL]
        assert not failures, (case_index, failures)
