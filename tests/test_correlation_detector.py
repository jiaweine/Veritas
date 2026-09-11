from veritas.detectors.correlation import CorrelationPSDDetector
from veritas.models import CorrelationMatrix, ReportedNumber
from veritas.types import CheckStatus, EvidenceGrade


def _n(value: float, decimals: int = 2) -> ReportedNumber:
    return ReportedNumber(value, decimals=decimals)


def test_rounding_aware_psd_matrix_passes():
    matrix = CorrelationMatrix(
        object_id="corr-1",
        labels=("x", "y", "z"),
        cells=(
            (_n(1.0), _n(0.50), _n(0.40)),
            (None, _n(1.0), _n(0.30)),
            (None, None, _n(1.0)),
        ),
    )

    result = CorrelationPSDDetector().run(matrix)[0]

    assert result.status is CheckStatus.PASS


def test_impossible_correlation_is_hard_contradiction():
    matrix = CorrelationMatrix(
        object_id="corr-2",
        labels=("x", "y"),
        cells=((_n(1.0), _n(1.20)), (None, _n(1.0))),
    )

    result = CorrelationPSDDetector().run(matrix)[0]

    assert result.status is CheckStatus.FAIL
    assert result.finding is not None
    assert result.finding.grade is EvidenceGrade.INTERNAL_CONTRADICTION
