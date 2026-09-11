from __future__ import annotations

from dataclasses import dataclass, field

from .models import ReportedNumber, SourceLocation
from .types import Materiality


@dataclass(frozen=True)
class GroupSummary:
    label: str
    n: int
    mean: ReportedNumber
    sd: ReportedNumber
    sd_definition: str = "unknown"  # sample | population | unknown
    weighted: bool | None = None

    def __post_init__(self) -> None:
        if self.n < 2:
            raise ValueError("group summary requires N >= 2")
        if self.sd.value < 0:
            raise ValueError("reported SD cannot be negative")


@dataclass(frozen=True)
class TwoGroupComparison:
    """A paper-only independent two-group comparison reconstructed from summary statistics."""

    object_id: str
    group_a: GroupSummary
    group_b: GroupSummary
    reported_mean_difference: ReportedNumber | None = None
    reported_t: ReportedNumber | None = None
    reported_df: ReportedNumber | None = None
    reported_p_value: ReportedNumber | None = None
    reported_cohen_d: ReportedNumber | None = None
    reported_hedges_g: ReportedNumber | None = None
    test_definition: str = "unknown"  # student_equal_var | welch | unknown
    hedges_correction: str = "unknown"  # exact_gamma | approx_4df_minus_1 | unknown
    independent_groups_verified: bool = False
    same_outcome_scale_verified: bool = False
    difference_direction_verified: bool = False
    pooled_sd_effect_size_verified: bool = False
    p_value_adjusted: bool = False
    materiality: Materiality = Materiality.SECONDARY_RESULT
    source: SourceLocation = field(default_factory=SourceLocation)


@dataclass(frozen=True)
class OneWayAnovaComparison:
    """Classical independent-groups one-way ANOVA reconstructed from group summaries."""

    object_id: str
    groups: tuple[GroupSummary, ...]
    reported_f: ReportedNumber | None = None
    reported_df_between: ReportedNumber | None = None
    reported_df_within: ReportedNumber | None = None
    reported_p_value: ReportedNumber | None = None
    reported_eta_squared: ReportedNumber | None = None
    test_definition: str = "unknown"  # classic_one_way | unknown
    independent_groups_verified: bool = False
    same_outcome_scale_verified: bool = False
    eta_squared_definition_verified: bool = False
    p_value_adjusted: bool = False
    materiality: Materiality = Materiality.SECONDARY_RESULT
    source: SourceLocation = field(default_factory=SourceLocation)

    def __post_init__(self) -> None:
        if len(self.groups) < 2:
            raise ValueError("one-way ANOVA requires at least two groups")
        labels = [group.label for group in self.groups]
        if len(set(labels)) != len(labels):
            raise ValueError("ANOVA group labels must be unique")
