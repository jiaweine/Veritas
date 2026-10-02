from veritas.detectors.designs import DIDDesignDetector, WeakIVDesignDetector
from veritas.models import DIDDesign, IVDesign, ReportedNumber
from veritas.types import CheckStatus, EvidenceFamily, EvidenceGrade


def test_canonical_did_passes_frontier_lint():
    design = DIDDesign(object_id="did-1", periods=2, staggered_adoption=False, estimator="twfe")

    result = DIDDesignDetector().run(design)[0]

    assert result.status is CheckStatus.PASS


def test_staggered_twfe_without_robust_comparison_is_review():
    design = DIDDesign(
        object_id="did-2",
        periods=8,
        staggered_adoption=True,
        estimator="twfe",
        event_study=True,
        heterogeneity_robust_estimator_reported=False,
        treatment_timing="state adoption year",
        comparison_group="not-yet-treated",
        event_time_window=(-4, 5),
        fixed_effects=("state", "year"),
        clustering=("state",),
    )

    result = DIDDesignDetector().run(design)[0]

    assert result.status is CheckStatus.REVIEW
    assert result.finding is not None
    assert result.finding.grade is EvidenceGrade.METHODOLOGICAL_RISK
    assert result.finding.family is EvidenceFamily.DESIGN_VALIDITY
    assert result.finding.evidence["comparison_group"] == "not-yet-treated"
    assert result.finding.evidence["event_time_window"] == (-4, 5)


def test_staggered_non_twfe_fails_closed_when_core_timing_semantics_are_missing():
    design = DIDDesign(
        object_id="did-3",
        periods=6,
        staggered_adoption=True,
        estimator="callaway_santanna",
    )

    result = DIDDesignDetector().run(design)[0]

    assert result.status is CheckStatus.UNVERIFIABLE
    assert result.finding is None
    assert "treatment timing" in result.message
    assert "comparison group" in result.message


def test_staggered_robust_comparison_passes_without_treating_twfe_name_as_error():
    design = DIDDesign(
        object_id="did-4",
        periods=8,
        staggered_adoption=True,
        estimator="twfe",
        event_study=True,
        heterogeneity_robust_estimator_reported=True,
    )

    result = DIDDesignDetector().run(design)[0]

    assert result.status is CheckStatus.PASS
    assert result.finding is None


def test_pointwise_pretrend_check_cannot_by_itself_establish_parallel_trends():
    design = DIDDesign(
        object_id="did-5",
        periods=10,
        staggered_adoption=False,
        estimator="event_study",
        event_study=True,
        treatment_timing="post-2012",
        comparison_group="never-treated",
        event_time_window=(-5, 5),
        pretrend_test="pointwise",
        parallel_trends_claimed=True,
    )

    result = DIDDesignDetector().run(design)[0]

    assert result.status is CheckStatus.REVIEW
    assert result.check_id == "pointwise_pretrend_overclaim"
    assert result.finding is not None
    assert result.finding.grade is EvidenceGrade.METHODOLOGICAL_RISK


def test_continuous_twfe_is_review_not_hard_invalidity():
    design = DIDDesign(
        object_id="did-6",
        periods=7,
        staggered_adoption=False,
        treatment_type="continuous",
        estimator="twfe",
        treatment_timing="annual exposure",
        comparison_group="lower-dose observations",
    )

    result = DIDDesignDetector().run(design)[0]

    assert result.status is CheckStatus.REVIEW
    assert result.check_id == "continuous_twfe"
    assert result.finding is not None
    assert result.finding.grade is EvidenceGrade.METHODOLOGICAL_RISK


def test_iv_detector_does_not_encode_f_greater_10_as_validity_rule():
    design = IVDesign(
        object_id="iv-1",
        single_instrument=True,
        single_endogenous_regressor=True,
        first_stage_f=ReportedNumber(12.0, decimals=1),
        uses_f_gt_10_rule_as_validity_claim=True,
    )

    result = WeakIVDesignDetector().run(design)[0]

    assert result.status is CheckStatus.REVIEW
    assert result.finding is not None
    assert result.finding.evidence["reported_first_stage_f"] == 12.0
    assert result.finding.grade is EvidenceGrade.METHODOLOGICAL_RISK


def test_iv_with_anderson_rubin_passes():
    design = IVDesign(
        object_id="iv-2",
        instrument_count=1,
        endogenous_regressor_count=1,
        weak_robust_methods=("Anderson-Rubin",),
    )

    result = WeakIVDesignDetector().run(design)[0]

    assert result.status is CheckStatus.PASS


def test_iv_missing_first_stage_is_review_with_stage_metadata():
    design = IVDesign(
        object_id="iv-3",
        instrument_count=1,
        endogenous_regressor_count=1,
        first_stage_reported=False,
        reduced_form_reported=True,
        two_stage_least_squares_reported=True,
    )

    result = WeakIVDesignDetector().run(design)[0]

    assert result.status is CheckStatus.REVIEW
    assert result.check_id == "first_stage_missing"
    assert result.finding is not None
    assert result.finding.evidence["reduced_form_reported"] is True
    assert result.finding.evidence["two_stage_least_squares_reported"] is True


def test_iv_counts_select_single_iv_check_without_legacy_boolean_flags():
    design = IVDesign(
        object_id="iv-4",
        instrument_count=1,
        endogenous_regressor_count=1,
        first_stage_reported=True,
        first_stage_f=ReportedNumber(8.4, decimals=1),
    )

    result = WeakIVDesignDetector().run(design)[0]

    assert result.status is CheckStatus.REVIEW
    assert result.check_id == "robust_inference_missing"
    assert result.finding is not None
    assert result.finding.evidence["no_hard_f_threshold_used"] is True


def test_iv_unknown_counts_fail_closed_instead_of_guessing_applicability():
    design = IVDesign(object_id="iv-5", first_stage_reported=True)

    result = WeakIVDesignDetector().run(design)[0]

    assert result.status is CheckStatus.UNVERIFIABLE
    assert result.finding is None
