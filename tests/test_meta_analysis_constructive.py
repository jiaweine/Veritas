from __future__ import annotations

from math import sqrt
from random import Random

from scipy.stats import norm

from veritas.detectors.meta_analysis import (
    MetaAnalysisArithmeticDetector,
    _pooled_effect_bounds,
)
from veritas.meta_analysis import MetaAnalysisSummary, MetaStudyEffect
from veritas.models import ReportedNumber
from veritas.types import CheckStatus


def _rounded_study(study_id: str, effect: float, se: float) -> MetaStudyEffect:
    return MetaStudyEffect(
        study_id=study_id,
        effect=ReportedNumber(round(effect, 3), decimals=3),
        se=ReportedNumber(round(se, 3), decimals=3),
    )


def _latent_summary(effects: list[float], ses: list[float], tau_squared: float) -> tuple[float, float, float]:
    weights = [1.0 / (se**2 + tau_squared) for se in ses]
    pooled = sum(weight * effect for weight, effect in zip(weights, effects, strict=True)) / sum(weights)
    pooled_se = sqrt(1.0 / sum(weights))
    p_value = float(2.0 * norm.sf(abs(pooled / pooled_se)))
    return pooled, pooled_se, p_value


def test_constructive_fixed_effect_cases_do_not_false_alert():
    rng = Random(20260834)
    detector = MetaAnalysisArithmeticDetector()
    for case_id in range(24):
        study_count = rng.randint(3, 9)
        effects = [rng.uniform(-0.8, 0.9) for _ in range(study_count)]
        ses = [rng.uniform(0.05, 0.35) for _ in range(study_count)]
        pooled, pooled_se, p_value = _latent_summary(effects, ses, 0.0)
        critical = float(norm.ppf(0.975))

        summary = MetaAnalysisSummary(
            object_id=f"fixed-{case_id}",
            studies=tuple(
                _rounded_study(f"s{index}", effect, se)
                for index, (effect, se) in enumerate(zip(effects, ses, strict=True))
            ),
            model="fixed_inverse_variance",
            reported_pooled_effect=ReportedNumber(round(pooled, 3), decimals=3),
            reported_pooled_se=ReportedNumber(round(pooled_se, 3), decimals=3),
            reported_pooled_p_value=ReportedNumber(round(p_value, 4), decimals=4),
            reported_ci_lower=ReportedNumber(round(pooled - critical * pooled_se, 3), decimals=3),
            reported_ci_upper=ReportedNumber(round(pooled + critical * pooled_se, 3), decimals=3),
            inference_method="normal",
            effects_on_common_analysis_scale_verified=True,
            independent_effects_verified=True,
            inverse_variance_weighting_verified=True,
        )
        relevant = [
            result
            for result in detector.run(summary)
            if result.status is not CheckStatus.NOT_RELEVANT
        ]
        assert relevant
        assert all(result.status is CheckStatus.PASS for result in relevant)


def test_constructive_random_effect_cases_do_not_false_alert():
    rng = Random(20260835)
    detector = MetaAnalysisArithmeticDetector()
    for case_id in range(24):
        study_count = rng.randint(3, 9)
        effects = [rng.uniform(-0.8, 0.9) for _ in range(study_count)]
        ses = [rng.uniform(0.05, 0.35) for _ in range(study_count)]
        tau_squared = rng.uniform(0.005, 0.12)
        pooled, pooled_se, p_value = _latent_summary(effects, ses, tau_squared)

        summary = MetaAnalysisSummary(
            object_id=f"random-{case_id}",
            studies=tuple(
                _rounded_study(f"s{index}", effect, se)
                for index, (effect, se) in enumerate(zip(effects, ses, strict=True))
            ),
            model="random_inverse_variance_reported_tau2",
            reported_tau_squared=ReportedNumber(round(tau_squared, 4), decimals=4),
            tau_squared_estimator="REML",
            reported_pooled_effect=ReportedNumber(round(pooled, 3), decimals=3),
            reported_pooled_se=ReportedNumber(round(pooled_se, 3), decimals=3),
            reported_pooled_p_value=ReportedNumber(round(p_value, 4), decimals=4),
            inference_method="normal",
            effects_on_common_analysis_scale_verified=True,
            independent_effects_verified=True,
            inverse_variance_weighting_verified=True,
        )
        relevant = [
            result
            for result in detector.run(summary)
            if result.status is not CheckStatus.NOT_RELEVANT
        ]
        assert relevant
        assert all(result.status is CheckStatus.PASS for result in relevant)


def test_linear_fractional_pooled_bounds_cover_all_small_weight_vertices():
    effects = ((0.10, 0.12), (0.45, 0.48), (-0.20, -0.18))
    weights = ((1.0, 3.0), (2.0, 5.0), (1.5, 2.5))
    lower, upper = _pooled_effect_bounds(effects, weights)

    for effect_1 in effects[0]:
        for effect_2 in effects[1]:
            for effect_3 in effects[2]:
                for weight_1 in weights[0]:
                    for weight_2 in weights[1]:
                        for weight_3 in weights[2]:
                            pooled = (
                                weight_1 * effect_1
                                + weight_2 * effect_2
                                + weight_3 * effect_3
                            ) / (weight_1 + weight_2 + weight_3)
                            assert lower - 1e-10 <= pooled <= upper + 1e-10
