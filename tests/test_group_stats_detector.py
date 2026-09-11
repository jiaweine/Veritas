from veritas.detectors.group_stats import TwoGroupSummaryDetector
from veritas.group_stats import GroupSummary, TwoGroupComparison
from veritas.models import ReportedNumber
from veritas.types import CheckStatus, ComparisonOperator, EvidenceGrade


def _group(label: str, n: int, mean: float, sd: float) -> GroupSummary:
    return GroupSummary(
        label=label,
        n=n,
        mean=ReportedNumber(mean, decimals=2),
        sd=ReportedNumber(sd, decimals=2),
        sd_definition="sample",
        weighted=False,
    )


def _student(**overrides) -> TwoGroupComparison:
    values = {
        "object_id": "student",
        "group_a": _group("A", 20, 5.00, 2.00),
        "group_b": _group("B", 20, 4.00, 2.00),
        "reported_mean_difference": ReportedNumber(1.00, decimals=2),
        "reported_t": ReportedNumber(1.58, decimals=2),
        "reported_df": ReportedNumber(38.0, decimals=0),
        "reported_p_value": ReportedNumber(0.122, decimals=3),
        "reported_cohen_d": ReportedNumber(0.50, decimals=2),
        "reported_hedges_g": ReportedNumber(0.49, decimals=2),
        "test_definition": "student_equal_var",
        "hedges_correction": "exact_gamma",
        "independent_groups_verified": True,
        "same_outcome_scale_verified": True,
        "difference_direction_verified": True,
        "pooled_sd_effect_size_verified": True,
    }
    values.update(overrides)
    return TwoGroupComparison(**values)


def test_student_group_summary_reconstruction_passes_all_reported_statistics():
    results = TwoGroupSummaryDetector().run(_student())
    relevant = [result for result in results if result.status is not CheckStatus.NOT_RELEVANT]
    assert relevant
    assert all(result.status is CheckStatus.PASS for result in relevant)


def test_incompatible_student_t_is_internal_contradiction():
    results = TwoGroupSummaryDetector().run(_student(reported_t=ReportedNumber(2.40, decimals=2)))
    t_result = next(result for result in results if result.check_id == "t_statistic")
    assert t_result.status is CheckStatus.FAIL
    assert t_result.finding is not None
    assert t_result.finding.grade is EvidenceGrade.INTERNAL_CONTRADICTION


def test_welch_reconstruction_uses_welch_df_not_pooled_df():
    comparison = TwoGroupComparison(
        object_id="welch",
        group_a=_group("A", 15, 5.00, 1.50),
        group_b=_group("B", 20, 4.00, 2.50),
        reported_t=ReportedNumber(1.47, decimals=2),
        reported_df=ReportedNumber(31.70, decimals=2),
        reported_p_value=ReportedNumber(0.151, decimals=3),
        test_definition="welch",
        independent_groups_verified=True,
        same_outcome_scale_verified=True,
        difference_direction_verified=True,
    )
    results = TwoGroupSummaryDetector().run(comparison)
    by_id = {result.check_id: result for result in results}
    assert by_id["t_statistic"].status is CheckStatus.PASS
    assert by_id["degrees_of_freedom"].status is CheckStatus.PASS
    assert by_id["p_value"].status is CheckStatus.PASS


def test_p_inequality_is_checked_conservatively():
    comparison = _student(
        reported_p_value=ReportedNumber(0.05, operator=ComparisonOperator.LT),
    )
    result = next(
        item for item in TwoGroupSummaryDetector().run(comparison) if item.check_id == "p_value"
    )
    assert result.status is CheckStatus.FAIL


def test_unknown_test_definition_abstains_on_t_but_can_check_mean_difference():
    comparison = _student(test_definition="unknown")
    results = TwoGroupSummaryDetector().run(comparison)
    by_id = {result.check_id: result for result in results}
    assert by_id["mean_difference"].status is CheckStatus.PASS
    assert by_id["t_statistic"].status is CheckStatus.UNVERIFIABLE
    assert by_id["degrees_of_freedom"].status is CheckStatus.UNVERIFIABLE


def test_adjusted_p_value_is_not_reconstructed_as_raw_t_p_value():
    comparison = _student(p_value_adjusted=True)
    result = next(
        item for item in TwoGroupSummaryDetector().run(comparison) if item.check_id == "p_value"
    )
    assert result.status is CheckStatus.UNVERIFIABLE
