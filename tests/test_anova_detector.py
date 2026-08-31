from veritas.detectors.anova import OneWayAnovaSummaryDetector
from veritas.group_stats import GroupSummary, OneWayAnovaComparison
from veritas.models import ReportedNumber
from veritas.types import CheckStatus, EvidenceGrade


def _group(label: str, mean: float) -> GroupSummary:
    return GroupSummary(
        label=label,
        n=10,
        mean=ReportedNumber(mean, decimals=2),
        sd=ReportedNumber(1.00, decimals=2),
        sd_definition="sample",
        weighted=False,
    )


def _comparison(**overrides) -> OneWayAnovaComparison:
    values = {
        "object_id": "anova-3",
        "groups": (_group("A", 1.00), _group("B", 2.00), _group("C", 3.00)),
        "reported_f": ReportedNumber(10.00, decimals=2),
        "reported_df_between": ReportedNumber(2.0, decimals=0),
        "reported_df_within": ReportedNumber(27.0, decimals=0),
        "reported_p_value": ReportedNumber(0.001, decimals=3),
        "reported_eta_squared": ReportedNumber(0.43, decimals=2),
        "test_definition": "classic_one_way",
        "independent_groups_verified": True,
        "same_outcome_scale_verified": True,
        "eta_squared_definition_verified": True,
    }
    values.update(overrides)
    return OneWayAnovaComparison(**values)


def test_three_group_hand_check_passes_rounding_aware_reconstruction():
    # Exact point values imply SS_between=20, SS_within=27, F=10,
    # df=(2,27), p≈0.00056246 and eta²=20/47≈0.42553.
    results = OneWayAnovaSummaryDetector().run(_comparison())
    relevant = [result for result in results if result.status is not CheckStatus.NOT_RELEVANT]
    assert relevant
    assert all(result.status is CheckStatus.PASS for result in relevant)


def test_impossible_f_is_internal_contradiction():
    result = next(
        item
        for item in OneWayAnovaSummaryDetector().run(
            _comparison(reported_f=ReportedNumber(15.00, decimals=2))
        )
        if item.check_id == "f_statistic"
    )
    assert result.status is CheckStatus.FAIL
    assert result.finding is not None
    assert result.finding.grade is EvidenceGrade.INTERNAL_CONTRADICTION


def test_adjusted_anova_p_value_abstains_without_adjustment_rule():
    result = next(
        item
        for item in OneWayAnovaSummaryDetector().run(_comparison(p_value_adjusted=True))
        if item.check_id == "p_value"
    )
    assert result.status is CheckStatus.UNVERIFIABLE


def test_unknown_anova_definition_abstains_before_reconstruction():
    results = OneWayAnovaSummaryDetector().run(_comparison(test_definition="unknown"))
    assert len(results) == 1
    assert results[0].status is CheckStatus.UNVERIFIABLE


def test_eta_squared_requires_verified_definition():
    result = next(
        item
        for item in OneWayAnovaSummaryDetector().run(
            _comparison(eta_squared_definition_verified=False)
        )
        if item.check_id == "eta_squared"
    )
    assert result.status is CheckStatus.UNVERIFIABLE
