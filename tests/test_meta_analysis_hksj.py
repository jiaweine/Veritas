from __future__ import annotations

from itertools import product
from math import sqrt
from random import Random

from scipy.stats import t as student_t

from veritas.detectors.meta_analysis import (
    MetaAnalysisArithmeticDetector,
    _maximum_residual_ss,
    _minimum_residual_ss,
    _weighted_residual_ss,
)
from veritas.meta_analysis import MetaAnalysisSummary, MetaStudyEffect
from veritas.models import ReportedNumber
from veritas.types import CheckStatus, EvidenceGrade


def _rn(value: float, decimals: int = 3) -> ReportedNumber:
    return ReportedNumber(round(value, decimals), decimals=decimals)


def _study(study_id: str, effect: float, se: float) -> MetaStudyEffect:
    return MetaStudyEffect(study_id=study_id, effect=_rn(effect), se=_rn(se))


def test_verified_hksj_reconstructs_q_se_ci_and_p_value():
    summary = MetaAnalysisSummary(
        object_id="hksj-hand",
        studies=(
            _study("s1", 0.200, 0.100),
            _study("s2", 0.500, 0.200),
            _study("s3", -0.100, 0.150),
        ),
        model="fixed_inverse_variance",
        reported_pooled_effect=_rn(0.1655737705),
        reported_hksj_q=_rn(3.024590164),
        reported_pooled_se=_rn(0.133604043),
        reported_ci_lower=_rn(-0.409278030),
        reported_ci_upper=_rn(0.740425571),
        reported_pooled_p_value=_rn(0.340938274),
        inference_method="hksj",
        hksj_definition_verified=True,
        effects_on_common_analysis_scale_verified=True,
        independent_effects_verified=True,
        inverse_variance_weighting_verified=True,
    )
    by_id = {result.check_id: result for result in MetaAnalysisArithmeticDetector().run(summary)}
    for check_id in ("pooled_effect", "hksj_q", "pooled_se", "ci_lower", "ci_upper", "pooled_p_value"):
        assert by_id[check_id].status is CheckStatus.PASS


def test_verified_hksj_contradiction_can_emit_e3():
    summary = MetaAnalysisSummary(
        object_id="hksj-bad",
        studies=(
            _study("s1", 0.200, 0.100),
            _study("s2", 0.500, 0.200),
            _study("s3", -0.100, 0.150),
        ),
        model="fixed_inverse_variance",
        reported_pooled_se=ReportedNumber(0.500, decimals=3),
        inference_method="hksj",
        hksj_definition_verified=True,
        effects_on_common_analysis_scale_verified=True,
        independent_effects_verified=True,
        inverse_variance_weighting_verified=True,
    )
    result = next(
        item for item in MetaAnalysisArithmeticDetector().run(summary) if item.check_id == "pooled_se"
    )
    assert result.status is CheckStatus.FAIL
    assert result.finding is not None
    assert result.finding.grade is EvidenceGrade.INTERNAL_CONTRADICTION


def test_modified_hksj_uses_q_floor_at_one():
    effects = (0.20, 0.22, 0.18)
    ses = (0.10, 0.10, 0.10)
    weights = tuple(1.0 / se**2 for se in ses)
    pooled = sum(weight * effect for weight, effect in zip(weights, effects, strict=True)) / sum(weights)
    residual = sum(
        weight * (effect - pooled) ** 2 for weight, effect in zip(weights, effects, strict=True)
    )
    q = residual / 2.0
    modified_se = sqrt(max(1.0, q) / sum(weights))
    critical = float(student_t.ppf(0.975, 2))
    p_value = float(2.0 * student_t.sf(abs(pooled / modified_se), 2))

    summary = MetaAnalysisSummary(
        object_id="hksj-modified",
        studies=tuple(_study(f"s{index}", effect, se) for index, (effect, se) in enumerate(zip(effects, ses), 1)),
        model="fixed_inverse_variance",
        reported_pooled_effect=_rn(pooled),
        reported_hksj_q=_rn(q),
        reported_pooled_se=_rn(modified_se),
        reported_ci_lower=_rn(pooled - critical * modified_se),
        reported_ci_upper=_rn(pooled + critical * modified_se),
        reported_pooled_p_value=_rn(p_value),
        inference_method="hksj_modified",
        hksj_definition_verified=True,
        effects_on_common_analysis_scale_verified=True,
        independent_effects_verified=True,
        inverse_variance_weighting_verified=True,
    )
    by_id = {result.check_id: result for result in MetaAnalysisArithmeticDetector().run(summary)}
    assert by_id["hksj_q"].status is CheckStatus.PASS
    assert by_id["pooled_se"].status is CheckStatus.PASS
    assert by_id["ci_lower"].status is CheckStatus.PASS
    assert by_id["ci_upper"].status is CheckStatus.PASS
    assert by_id["pooled_p_value"].status is CheckStatus.PASS


def test_hts_k_minus_2_prediction_interval_reconstructs_when_verified():
    effects = (0.2, 0.5, -0.1)
    ses = (0.1, 0.2, 0.15)
    tau_squared = 0.04
    weights = tuple(1.0 / (se**2 + tau_squared) for se in ses)
    pooled = sum(weight * effect for weight, effect in zip(weights, effects, strict=True)) / sum(weights)
    conventional_se = sqrt(1.0 / sum(weights))
    critical = float(student_t.ppf(0.975, 1))
    predictive_sd = sqrt(tau_squared + conventional_se**2)

    summary = MetaAnalysisSummary(
        object_id="hts-hand",
        studies=tuple(_study(f"s{index}", effect, se) for index, (effect, se) in enumerate(zip(effects, ses), 1)),
        model="random_inverse_variance_reported_tau2",
        reported_tau_squared=_rn(tau_squared),
        reported_pooled_effect=_rn(pooled),
        inference_method="normal",
        reported_prediction_lower=_rn(pooled - critical * predictive_sd),
        reported_prediction_upper=_rn(pooled + critical * predictive_sd),
        prediction_method="hts_t_k_minus_2_conventional",
        prediction_method_verified=True,
        effects_on_common_analysis_scale_verified=True,
        independent_effects_verified=True,
        inverse_variance_weighting_verified=True,
    )
    by_id = {result.check_id: result for result in MetaAnalysisArithmeticDetector().run(summary)}
    assert by_id["prediction_lower"].status is CheckStatus.PASS
    assert by_id["prediction_upper"].status is CheckStatus.PASS


def test_unverified_prediction_formula_abstains():
    summary = MetaAnalysisSummary(
        object_id="prediction-unverified",
        studies=(_study("s1", 0.1, 0.1), _study("s2", 0.2, 0.1), _study("s3", 0.3, 0.1)),
        model="random_inverse_variance_reported_tau2",
        reported_tau_squared=_rn(0.02),
        reported_prediction_lower=_rn(-0.3),
        reported_prediction_upper=_rn(0.7),
        prediction_method="hts_t_k_minus_2_conventional",
        prediction_method_verified=False,
        effects_on_common_analysis_scale_verified=True,
        independent_effects_verified=True,
        inverse_variance_weighting_verified=True,
    )
    by_id = {result.check_id: result for result in MetaAnalysisArithmeticDetector().run(summary)}
    assert by_id["prediction_lower"].status is CheckStatus.UNVERIFIABLE
    assert by_id["prediction_upper"].status is CheckStatus.UNVERIFIABLE


def test_residual_ss_outer_bounds_cover_effect_and_weight_boxes():
    effects = ((-0.15, -0.05), (0.10, 0.20), (0.35, 0.50))
    weights = ((8.0, 12.0), (4.0, 7.0), (2.0, 5.0))
    lower = _minimum_residual_ss(effects, weights)
    upper, method = _maximum_residual_ss(effects, weights, max_vertex_studies=6)
    assert method == "effect_vertex_enumeration"

    effect_grids = tuple((lo, (lo + hi) / 2.0, hi) for lo, hi in effects)
    weight_grids = tuple((lo, (lo + hi) / 2.0, hi) for lo, hi in weights)
    for values in product(*effect_grids):
        for actual_weights in product(*weight_grids):
            residual = _weighted_residual_ss(values, actual_weights)
            assert lower <= residual + 1e-10
            assert residual <= upper + 1e-10


def test_constructive_hksj_and_modified_hksj_cases_do_not_false_alert():
    rng = Random(20260831)
    detector = MetaAnalysisArithmeticDetector()
    for case_index in range(36):
        k = rng.randint(3, 7)
        effects = tuple(rng.uniform(-0.6, 0.8) for _ in range(k))
        ses = tuple(rng.uniform(0.08, 0.35) for _ in range(k))
        weights = tuple(1.0 / se**2 for se in ses)
        pooled = sum(weight * effect for weight, effect in zip(weights, effects, strict=True)) / sum(weights)
        residual = sum(
            weight * (effect - pooled) ** 2
            for weight, effect in zip(weights, effects, strict=True)
        )
        q = residual / (k - 1)
        method = "hksj" if case_index % 2 == 0 else "hksj_modified"
        variance_q = q if method == "hksj" else max(1.0, q)
        pooled_se = sqrt(variance_q / sum(weights))
        critical = float(student_t.ppf(0.975, k - 1))
        p_value = float(2.0 * student_t.sf(abs(pooled / pooled_se), k - 1)) if pooled_se > 0 else 0.0

        summary = MetaAnalysisSummary(
            object_id=f"constructive-hk-{case_index}",
            studies=tuple(
                _study(f"s{index}", effect, se)
                for index, (effect, se) in enumerate(zip(effects, ses, strict=True), 1)
            ),
            model="fixed_inverse_variance",
            reported_pooled_effect=_rn(pooled),
            reported_hksj_q=_rn(q),
            reported_pooled_se=_rn(pooled_se),
            reported_ci_lower=_rn(pooled - critical * pooled_se),
            reported_ci_upper=_rn(pooled + critical * pooled_se),
            reported_pooled_p_value=_rn(p_value),
            inference_method=method,
            hksj_definition_verified=True,
            effects_on_common_analysis_scale_verified=True,
            independent_effects_verified=True,
            inverse_variance_weighting_verified=True,
        )
        findings = [
            result
            for result in detector.run(summary)
            if result.status is CheckStatus.FAIL and result.finding is not None
        ]
        assert not findings, (case_index, findings)


def test_constructive_random_effect_hts_prediction_intervals_do_not_false_alert():
    rng = Random(20260901)
    detector = MetaAnalysisArithmeticDetector()
    for case_index in range(24):
        k = rng.randint(3, 8)
        effects = tuple(rng.uniform(-0.5, 0.7) for _ in range(k))
        ses = tuple(rng.uniform(0.08, 0.30) for _ in range(k))
        tau_squared = rng.uniform(0.005, 0.12)
        weights = tuple(1.0 / (se**2 + tau_squared) for se in ses)
        pooled = sum(weight * effect for weight, effect in zip(weights, effects, strict=True)) / sum(weights)
        pooled_se = sqrt(1.0 / sum(weights))
        critical = float(student_t.ppf(0.975, k - 2))
        predictive_sd = sqrt(tau_squared + pooled_se**2)

        summary = MetaAnalysisSummary(
            object_id=f"constructive-pi-{case_index}",
            studies=tuple(
                _study(f"s{index}", effect, se)
                for index, (effect, se) in enumerate(zip(effects, ses, strict=True), 1)
            ),
            model="random_inverse_variance_reported_tau2",
            reported_tau_squared=_rn(tau_squared),
            reported_pooled_effect=_rn(pooled),
            inference_method="normal",
            reported_prediction_lower=_rn(pooled - critical * predictive_sd),
            reported_prediction_upper=_rn(pooled + critical * predictive_sd),
            prediction_method="hts_t_k_minus_2_conventional",
            prediction_method_verified=True,
            effects_on_common_analysis_scale_verified=True,
            independent_effects_verified=True,
            inverse_variance_weighting_verified=True,
        )
        by_id = {result.check_id: result for result in detector.run(summary)}
        assert by_id["prediction_lower"].status is CheckStatus.PASS
        assert by_id["prediction_upper"].status is CheckStatus.PASS
