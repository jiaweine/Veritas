from veritas.detectors.group_stats import TwoGroupSummaryDetector
from veritas.group_stats import GroupSummary, TwoGroupComparison
from veritas.models import ReportedNumber
from veritas.types import CheckStatus, ComparisonOperator


def test_non_equality_group_summary_abstains_before_reconstruction():
    group_a = GroupSummary(
        label="A",
        n=20,
        mean=ReportedNumber(5.0, operator=ComparisonOperator.LT),
        sd=ReportedNumber(2.0, decimals=2),
        sd_definition="sample",
        weighted=False,
    )
    group_b = GroupSummary(
        label="B",
        n=20,
        mean=ReportedNumber(4.0, decimals=2),
        sd=ReportedNumber(2.0, decimals=2),
        sd_definition="sample",
        weighted=False,
    )
    comparison = TwoGroupComparison(
        object_id="inequality-input",
        group_a=group_a,
        group_b=group_b,
        reported_t=ReportedNumber(1.58, decimals=2),
        test_definition="student_equal_var",
        independent_groups_verified=True,
        same_outcome_scale_verified=True,
        difference_direction_verified=True,
    )
    result = TwoGroupSummaryDetector().run(comparison)
    assert len(result) == 1
    assert result[0].status is CheckStatus.UNVERIFIABLE
