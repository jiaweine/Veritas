from __future__ import annotations

from math import sqrt
from random import Random

from scipy.stats import t as student_t

from veritas.detectors.group_stats import TwoGroupSummaryDetector
from veritas.group_stats import GroupSummary, TwoGroupComparison
from veritas.models import ReportedNumber
from veritas.types import CheckStatus


def _summary(label: str, n: int, mean: float, sd: float) -> GroupSummary:
    return GroupSummary(
        label=label,
        n=n,
        mean=ReportedNumber(round(mean, 2), decimals=2),
        sd=ReportedNumber(round(sd, 2), decimals=2),
        sd_definition="sample",
        weighted=False,
    )


def _assert_core_statistics_pass(comparison: TwoGroupComparison) -> None:
    by_id = {result.check_id: result for result in TwoGroupSummaryDetector().run(comparison)}
    assert by_id["t_statistic"].status is CheckStatus.PASS
    assert by_id["degrees_of_freedom"].status is CheckStatus.PASS
    assert by_id["p_value"].status is CheckStatus.PASS


def test_constructive_student_cases_do_not_false_alert():
    rng = Random(20260831)
    for case_id in range(20):
        n_a = rng.randint(12, 80)
        n_b = rng.randint(12, 80)
        mean_a = rng.uniform(-2.0, 3.0)
        mean_b = rng.uniform(-2.0, 3.0)
        sd_a = rng.uniform(0.6, 3.0)
        sd_b = rng.uniform(0.6, 3.0)
        pooled = sqrt(((n_a - 1) * sd_a**2 + (n_b - 1) * sd_b**2) / (n_a + n_b - 2))
        t_value = (mean_a - mean_b) / (pooled * sqrt(1.0 / n_a + 1.0 / n_b))
        df = float(n_a + n_b - 2)
        p_value = float(2.0 * student_t.sf(abs(t_value), df))

        comparison = TwoGroupComparison(
            object_id=f"student-{case_id}",
            group_a=_summary("A", n_a, mean_a, sd_a),
            group_b=_summary("B", n_b, mean_b, sd_b),
            reported_t=ReportedNumber(round(t_value, 3), decimals=3),
            reported_df=ReportedNumber(df, decimals=0),
            reported_p_value=ReportedNumber(round(p_value, 4), decimals=4),
            test_definition="student_equal_var",
            independent_groups_verified=True,
            same_outcome_scale_verified=True,
            difference_direction_verified=True,
        )
        _assert_core_statistics_pass(comparison)


def test_constructive_welch_cases_do_not_false_alert():
    rng = Random(20260832)
    for case_id in range(20):
        n_a = rng.randint(12, 80)
        n_b = rng.randint(12, 80)
        mean_a = rng.uniform(-2.0, 3.0)
        mean_b = rng.uniform(-2.0, 3.0)
        sd_a = rng.uniform(0.6, 3.0)
        sd_b = rng.uniform(0.6, 3.0)
        a_term = sd_a**2 / n_a
        b_term = sd_b**2 / n_b
        se = sqrt(a_term + b_term)
        t_value = (mean_a - mean_b) / se
        df = (a_term + b_term) ** 2 / (a_term**2 / (n_a - 1) + b_term**2 / (n_b - 1))
        p_value = float(2.0 * student_t.sf(abs(t_value), df))

        comparison = TwoGroupComparison(
            object_id=f"welch-{case_id}",
            group_a=_summary("A", n_a, mean_a, sd_a),
            group_b=_summary("B", n_b, mean_b, sd_b),
            reported_t=ReportedNumber(round(t_value, 3), decimals=3),
            reported_df=ReportedNumber(round(df, 2), decimals=2),
            reported_p_value=ReportedNumber(round(p_value, 4), decimals=4),
            test_definition="welch",
            independent_groups_verified=True,
            same_outcome_scale_verified=True,
            difference_direction_verified=True,
        )
        _assert_core_statistics_pass(comparison)


def test_welch_df_interval_contains_dense_rounding_grid():
    detector = TwoGroupSummaryDetector()
    comparison = TwoGroupComparison(
        object_id="grid",
        group_a=_summary("A", 17, 0.2, 1.23),
        group_b=_summary("B", 29, -0.1, 2.34),
        test_definition="welch",
        independent_groups_verified=True,
        same_outcome_scale_verified=True,
        difference_direction_verified=True,
    )
    sd_a = detector._sd_interval(comparison.group_a.sd)
    sd_b = detector._sd_interval(comparison.group_b.sd)
    bounds = detector._welch_df_interval(comparison, sd_a, sd_b)
    assert bounds is not None

    for i in range(21):
        s_a = sd_a[0] + (sd_a[1] - sd_a[0]) * i / 20.0
        for j in range(21):
            s_b = sd_b[0] + (sd_b[1] - sd_b[0]) * j / 20.0
            a_term = s_a**2 / comparison.group_a.n
            b_term = s_b**2 / comparison.group_b.n
            df = (a_term + b_term) ** 2 / (
                a_term**2 / (comparison.group_a.n - 1)
                + b_term**2 / (comparison.group_b.n - 1)
            )
            assert bounds[0] - 1e-9 <= df <= bounds[1] + 1e-9
