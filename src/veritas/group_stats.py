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
