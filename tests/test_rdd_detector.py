from veritas.detectors.rdd import RDDDesignDetector
from veritas.models import RDDDesign
from veritas.types import CheckStatus, EvidenceGrade


def test_modern_continuity_rdd_passes():
    design = RDDDesign(
        object_id="rdd-1",
        framework="continuity",
        robust_bias_corrected_inference=True,
        bandwidth_selection="mse-optimal",
    )

    result = RDDDesignDetector().run(design)[0]

    assert result.status is CheckStatus.PASS


def test_high_order_global_polynomial_is_review_signal():
    design = RDDDesign(
        object_id="rdd-2",
        framework="continuity",
        global_polynomial_order=5,
    )

    result = RDDDesignDetector().run(design)[0]

    assert result.status is CheckStatus.REVIEW
    assert result.finding is not None
    assert result.finding.grade is EvidenceGrade.METHODOLOGICAL_RISK


def test_missing_density_test_is_not_by_itself_a_failure():
    design = RDDDesign(
        object_id="rdd-3",
        framework="continuity",
        robust_bias_corrected_inference=True,
        density_test_reported=False,
    )

    result = RDDDesignDetector().run(design)[0]

    assert result.status is CheckStatus.PASS
