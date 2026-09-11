from veritas.detectors.designs import DIDDesignDetector, WeakIVDesignDetector
from veritas.models import DIDDesign, IVDesign, ReportedNumber
from veritas.types import CheckStatus, EvidenceGrade


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
    )

    result = DIDDesignDetector().run(design)[0]

    assert result.status is CheckStatus.REVIEW
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


def test_iv_with_anderson_rubin_passes():
    design = IVDesign(
        object_id="iv-2",
        single_instrument=True,
        single_endogenous_regressor=True,
        weak_robust_methods=("Anderson-Rubin",),
    )

    result = WeakIVDesignDetector().run(design)[0]

    assert result.status is CheckStatus.PASS
