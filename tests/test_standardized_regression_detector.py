from veritas.detectors.standardized_regression import StandardizedRegressionReconstructionDetector
from veritas.models import CorrelationMatrix, ReportedNumber, StandardizedRegressionReconstruction
from veritas.types import CheckStatus, EvidenceGrade


def _number(value: float, decimals: int = 2) -> ReportedNumber:
    return ReportedNumber(value, decimals=decimals)


def _correlation_matrix(*, missing_x1_y: bool = False) -> CorrelationMatrix:
    x1_y = None if missing_x1_y else _number(0.50)
    return CorrelationMatrix(
        object_id="corr",
        labels=("x1", "x2", "y"),
        cells=(
            (_number(1.00), _number(0.20), x1_y),
            (_number(0.20), _number(1.00), _number(0.30)),
            (x1_y, _number(0.30), _number(1.00)),
        ),
    )


def _result(beta1: float, beta2: float, *, matrix=None) -> StandardizedRegressionReconstruction:
    return StandardizedRegressionReconstruction(
        object_id="std-reg",
        correlation_matrix=matrix or _correlation_matrix(),
        outcome="y",
        predictors=("x1", "x2"),
        standardized_betas=(_number(beta1), _number(beta2)),
        ols_identity_verified=True,
        same_sample_verified=True,
        complete_predictor_set_verified=True,
    )


def test_standardized_regression_compatible_witness_passes():
    # With r12=.20, r1y=.50, r2y=.30, exact standardized betas are
    # approximately (.4583, .2083), both compatible with (.46, .21) rounding.
    result = StandardizedRegressionReconstructionDetector().run(_result(0.46, 0.21))[0]
    assert result.status is CheckStatus.PASS


def test_standardized_regression_incompatible_outer_relaxation_is_e2():
    result = StandardizedRegressionReconstructionDetector().run(_result(0.80, 0.20))[0]
    assert result.status is CheckStatus.REVIEW
    assert result.finding is not None
    assert result.finding.grade is EvidenceGrade.METHODOLOGICAL_RISK
    assert result.finding.evidence["severity_ceiling"] == "E2 until AuditBench certification"


def test_standardized_regression_requires_same_sample_identity():
    obj = _result(0.46, 0.21)
    obj = StandardizedRegressionReconstruction(
        object_id=obj.object_id,
        correlation_matrix=obj.correlation_matrix,
        outcome=obj.outcome,
        predictors=obj.predictors,
        standardized_betas=obj.standardized_betas,
        ols_identity_verified=True,
        same_sample_verified=False,
        complete_predictor_set_verified=True,
    )
    result = StandardizedRegressionReconstructionDetector().run(obj)[0]
    assert result.status is CheckStatus.UNVERIFIABLE


def test_standardized_regression_missing_required_correlation_abstains():
    result = StandardizedRegressionReconstructionDetector().run(
        _result(0.46, 0.21, matrix=_correlation_matrix(missing_x1_y=True))
    )[0]
    assert result.status is CheckStatus.UNVERIFIABLE
