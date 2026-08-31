from veritas.detectors.meta_analysis import MetaAnalysisArithmeticDetector
from veritas.meta_analysis import MetaAnalysisSummary, MetaStudyEffect
from veritas.models import ReportedNumber
from veritas.types import CheckStatus, EvidenceGrade


def _study(study_id: str, effect: float, se: float, weight: float | None = None) -> MetaStudyEffect:
    return MetaStudyEffect(
        study_id=study_id,
        effect=ReportedNumber(effect, decimals=3),
        se=ReportedNumber(se, decimals=3),
        reported_weight_percent=None if weight is None else ReportedNumber(weight, decimals=1),
    )


def _fixed(**overrides) -> MetaAnalysisSummary:
    values = {
        "object_id": "meta-fixed",
        "studies": (
            _study("s1", 0.200, 0.100, 59.0),
            _study("s2", 0.500, 0.200, 14.8),
            _study("s3", -0.100, 0.150, 26.2),
        ),
        "model": "fixed_inverse_variance",
        "reported_pooled_effect": ReportedNumber(0.166, decimals=3),
        "reported_pooled_se": ReportedNumber(0.077, decimals=3),
        "reported_pooled_p_value": ReportedNumber(0.031, decimals=3),
        "reported_ci_lower": ReportedNumber(0.015, decimals=3),
        "reported_ci_upper": ReportedNumber(0.316, decimals=3),
        "inference_method": "normal",
        "reported_q": ReportedNumber(6.05, decimals=2),
        "reported_q_df": ReportedNumber(2.0, decimals=0),
        "reported_q_p_value": ReportedNumber(0.049, decimals=3),
        "reported_i_squared": ReportedNumber(66.9, decimals=1),
        "effects_on_common_analysis_scale_verified": True,
        "independent_effects_verified": True,
        "inverse_variance_weighting_verified": True,
        "q_definition_verified": True,
    }
    values.update(overrides)
    return MetaAnalysisSummary(**values)


def test_fixed_effect_meta_analysis_arithmetic_passes():
    results = MetaAnalysisArithmeticDetector().run(_fixed())
    relevant = [result for result in results if result.status is not CheckStatus.NOT_RELEVANT]
    assert relevant
    assert all(result.status is CheckStatus.PASS for result in relevant)


def test_impossible_pooled_effect_is_internal_contradiction():
    result = next(
        item
        for item in MetaAnalysisArithmeticDetector().run(
            _fixed(reported_pooled_effect=ReportedNumber(0.400, decimals=3))
        )
        if item.check_id == "pooled_effect"
    )
    assert result.status is CheckStatus.FAIL
    assert result.finding is not None
    assert result.finding.grade is EvidenceGrade.INTERNAL_CONTRADICTION


def test_hksj_path_does_not_reuse_normal_ci_formula():
    summary = _fixed(
        inference_method="hksj",
        reported_pooled_se=ReportedNumber(0.090, decimals=3),
        reported_ci_lower=ReportedNumber(-0.050, decimals=3),
        reported_ci_upper=ReportedNumber(0.380, decimals=3),
        reported_pooled_p_value=ReportedNumber(0.080, decimals=3),
    )
    by_id = {result.check_id: result for result in MetaAnalysisArithmeticDetector().run(summary)}
    assert by_id["pooled_effect"].status is CheckStatus.PASS
    assert by_id["pooled_se"].status is CheckStatus.UNVERIFIABLE
    assert by_id["ci_lower"].status is CheckStatus.UNVERIFIABLE
    assert by_id["ci_upper"].status is CheckStatus.UNVERIFIABLE
    assert by_id["pooled_p_value"].status is CheckStatus.UNVERIFIABLE


def test_random_effects_with_reported_tau_squared_reconstructs_safe_outer_bounds():
    summary = MetaAnalysisSummary(
        object_id="meta-random",
        studies=(
            _study("s1", 0.200, 0.100),
            _study("s2", 0.500, 0.200),
            _study("s3", -0.100, 0.150),
        ),
        model="random_inverse_variance_reported_tau2",
        reported_tau_squared=ReportedNumber(0.040, decimals=3),
        tau_squared_estimator="REML",
        reported_pooled_effect=ReportedNumber(0.178, decimals=3),
        reported_pooled_se=ReportedNumber(0.144, decimals=3),
        inference_method="normal",
        effects_on_common_analysis_scale_verified=True,
        independent_effects_verified=True,
        inverse_variance_weighting_verified=True,
    )
    by_id = {result.check_id: result for result in MetaAnalysisArithmeticDetector().run(summary)}
    assert by_id["pooled_effect"].status is CheckStatus.PASS
    assert by_id["pooled_se"].status is CheckStatus.PASS


def test_negative_tau_squared_interval_is_hard_contradiction():
    summary = MetaAnalysisSummary(
        object_id="bad-tau",
        studies=(_study("s1", 0.2, 0.1), _study("s2", 0.3, 0.2)),
        model="random_inverse_variance_reported_tau2",
        reported_tau_squared=ReportedNumber(-0.10, decimals=2),
        effects_on_common_analysis_scale_verified=True,
        independent_effects_verified=True,
        inverse_variance_weighting_verified=True,
    )
    result = MetaAnalysisArithmeticDetector().run(summary)[0]
    assert result.status is CheckStatus.FAIL
    assert result.finding is not None
    assert result.finding.grade is EvidenceGrade.INTERNAL_CONTRADICTION


def test_unverified_common_scale_abstains_before_arithmetic():
    summary = _fixed(effects_on_common_analysis_scale_verified=False)
    result = MetaAnalysisArithmeticDetector().run(summary)
    assert len(result) == 1
    assert result[0].status is CheckStatus.UNVERIFIABLE
