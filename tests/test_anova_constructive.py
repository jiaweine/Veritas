from __future__ import annotations

from random import Random

from scipy.stats import f as f_distribution

from veritas.detectors.anova import (
    OneWayAnovaSummaryDetector,
    _maximum_between_ss,
    _minimum_between_ss,
    _weighted_ss,
)
from veritas.group_stats import GroupSummary, OneWayAnovaComparison
from veritas.models import ReportedNumber
from veritas.types import CheckStatus


def _rounded_group(label: str, n: int, mean: float, sd: float) -> GroupSummary:
    return GroupSummary(
        label=label,
        n=n,
        mean=ReportedNumber(round(mean, 2), decimals=2),
        sd=ReportedNumber(round(sd, 2), decimals=2),
        sd_definition="sample",
        weighted=False,
    )


def test_constructive_one_way_anovas_do_not_false_alert():
    rng = Random(20260833)
    detector = OneWayAnovaSummaryDetector()

    for case_id in range(24):
        group_count = rng.randint(3, 5)
        latent = []
        for index in range(group_count):
            latent.append(
                (
                    f"G{index + 1}",
                    rng.randint(8, 55),
                    rng.uniform(-1.5, 2.5),
                    rng.uniform(0.6, 2.8),
                )
            )

        total_n = sum(item[1] for item in latent)
        grand_mean = sum(n * mean for _, n, mean, _ in latent) / total_n
        ss_between = sum(n * (mean - grand_mean) ** 2 for _, n, mean, _ in latent)
        ss_within = sum((n - 1) * sd**2 for _, n, _, sd in latent)
        df_between = float(group_count - 1)
        df_within = float(total_n - group_count)
        f_value = (ss_between / df_between) / (ss_within / df_within)
        p_value = float(f_distribution.sf(f_value, df_between, df_within))
        eta_squared = ss_between / (ss_between + ss_within)

        comparison = OneWayAnovaComparison(
            object_id=f"anova-{case_id}",
            groups=tuple(_rounded_group(*item) for item in latent),
            reported_f=ReportedNumber(round(f_value, 3), decimals=3),
            reported_df_between=ReportedNumber(df_between, decimals=0),
            reported_df_within=ReportedNumber(df_within, decimals=0),
            reported_p_value=ReportedNumber(round(p_value, 4), decimals=4),
            reported_eta_squared=ReportedNumber(round(eta_squared, 3), decimals=3),
            test_definition="classic_one_way",
            independent_groups_verified=True,
            same_outcome_scale_verified=True,
            eta_squared_definition_verified=True,
        )
        results = detector.run(comparison)
        relevant = [result for result in results if result.status is not CheckStatus.NOT_RELEVANT]
        assert relevant
        assert all(result.status is CheckStatus.PASS for result in relevant)


def test_between_ss_bounds_cover_dense_three_group_grid():
    intervals = ((0.95, 1.05), (1.90, 2.10), (2.95, 3.05))
    weights = (7, 11, 13)
    lower = _minimum_between_ss(intervals, weights)
    upper, method = _maximum_between_ss(intervals, weights, max_vertex_groups=12)
    assert method == "vertex_enumeration"

    for i in range(9):
        a = intervals[0][0] + (intervals[0][1] - intervals[0][0]) * i / 8.0
        for j in range(9):
            b = intervals[1][0] + (intervals[1][1] - intervals[1][0]) * j / 8.0
            for k in range(9):
                c = intervals[2][0] + (intervals[2][1] - intervals[2][0]) * k / 8.0
                value = _weighted_ss((a, b, c), weights)
                assert lower - 1e-9 <= value <= upper + 1e-9


def test_large_group_count_uses_safe_coarse_upper_bound():
    intervals = tuple((float(index), float(index) + 0.1) for index in range(13))
    weights = tuple(10 for _ in intervals)
    upper, method = _maximum_between_ss(intervals, weights, max_vertex_groups=12)
    midpoint_value = _weighted_ss(tuple((lo + hi) / 2.0 for lo, hi in intervals), weights)
    assert method == "coarse_range_bound"
    assert upper >= midpoint_value
