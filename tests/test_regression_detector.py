from veritas.detectors.regression import RegressionConsistencyDetector
from veritas.models import RegressionResult, ReportedNumber
from veritas.types import CheckStatus, ComparisonOperator, EvidenceGrade, Materiality


def test_rounding_compatible_regression_passes():
    obj = RegressionResult(
        object_id="table2-col1",
        beta=ReportedNumber(0.18, decimals=2),
        se=ReportedNumber(0.09, decimals=2),
        t_stat=ReportedNumber(2.00, decimals=2),
        p_value=ReportedNumber(0.05, decimals=2, operator=ComparisonOperator.EQ),
        materiality=Materiality.MAIN_EMPIRICAL_CLAIM,
    )
    checks = RegressionConsistencyDetector().run(obj)
    assert checks[0].status is CheckStatus.PASS
    assert not any(c.status is CheckStatus.FAIL for c in checks)


def test_incompatible_p_value_is_hard_contradiction():
    obj = RegressionResult(
        object_id="table4-col3",
        beta=ReportedNumber(0.183, decimals=3),
        se=ReportedNumber(0.041, decimals=3),
        p_value=ReportedNumber(0.017, decimals=3),
        materiality=Materiality.CHANGES_SUBSTANTIVE_CONCLUSION,
    )
    checks = RegressionConsistencyDetector().run(obj)
    failure = next(c for c in checks if c.check_id == "p_value")
    assert failure.status is CheckStatus.FAIL
    assert failure.finding is not None
    assert failure.finding.grade is EvidenceGrade.INTERNAL_CONTRADICTION


def test_adjusted_p_value_is_unverifiable_not_failure():
    obj = RegressionResult(
        object_id="table5-col2",
        beta=ReportedNumber(0.2, decimals=2),
        se=ReportedNumber(0.05, decimals=2),
        p_value=ReportedNumber(0.04, decimals=2),
        p_value_adjusted=True,
    )
    checks = RegressionConsistencyDetector().run(obj)
    p_check = next(c for c in checks if c.check_id == "p_value")
    assert p_check.status is CheckStatus.UNVERIFIABLE
