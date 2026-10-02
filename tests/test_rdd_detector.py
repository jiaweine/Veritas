from veritas.detectors.rdd import RDDDesignDetector
from veritas.models import RDDDesign, ReportedNumber
from veritas.types import CheckStatus, EvidenceFamily, EvidenceGrade


def test_modern_continuity_rdd_passes():
    design = RDDDesign(
        object_id="rdd-1",
        framework="continuity",
        running_variable="score",
        cutoff=ReportedNumber(50.0, decimals=0),
        bandwidth=ReportedNumber(8.5, decimals=1),
        bandwidth_selection="mse-optimal",
        kernel="triangular",
        robust_bias_corrected_inference=True,
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
    assert result.finding.family is EvidenceFamily.DESIGN_VALIDITY


def test_missing_density_test_is_not_by_itself_a_failure():
    design = RDDDesign(
        object_id="rdd-3",
        framework="continuity",
        robust_bias_corrected_inference=True,
        density_test_reported=False,
    )

    result = RDDDesignDetector().run(design)[0]

    assert result.status is CheckStatus.PASS


def test_claimed_manipulation_check_without_reported_density_evidence_is_review():
    design = RDDDesign(
        object_id="rdd-4",
        framework="continuity",
        running_variable="vote margin",
        cutoff=ReportedNumber(0.0, decimals=0),
        bandwidth=ReportedNumber(0.08, decimals=2),
        kernel="triangular",
        robust_bias_corrected_inference=True,
        manipulation_check_claimed=True,
        density_test_reported=False,
    )

    result = RDDDesignDetector().run(design)[0]

    assert result.status is CheckStatus.REVIEW
    assert result.check_id == "manipulation_check_not_reported"
    assert result.finding is not None
    assert result.finding.grade is EvidenceGrade.METHODOLOGICAL_RISK
    assert "author intent" in result.message
    assert result.finding.evidence["running_variable"] == "vote margin"
    assert result.finding.evidence["cutoff"] == 0.0


def test_claimed_continuity_check_without_reported_diagnostic_is_review():
    design = RDDDesign(
        object_id="rdd-5",
        framework="continuity",
        robust_bias_corrected_inference=True,
        continuity_check_claimed=True,
        continuity_check_reported=False,
    )

    result = RDDDesignDetector().run(design)[0]

    assert result.status is CheckStatus.REVIEW
    assert result.check_id == "continuity_check_not_reported"


def test_local_randomization_requires_randomization_inference_when_explicitly_classified():
    design = RDDDesign(
        object_id="rdd-6",
        framework="local_randomization",
        randomization_inference_reported=False,
        bandwidth=ReportedNumber(2.0, decimals=1),
    )

    result = RDDDesignDetector().run(design)[0]

    assert result.status is CheckStatus.REVIEW
    assert result.check_id == "local_randomization_inference"
    assert result.finding is not None
    assert result.finding.grade is EvidenceGrade.METHODOLOGICAL_RISK


def test_unknown_rdd_framework_fails_closed():
    design = RDDDesign(object_id="rdd-7")

    result = RDDDesignDetector().run(design)[0]

    assert result.status is CheckStatus.UNVERIFIABLE
    assert result.finding is None
