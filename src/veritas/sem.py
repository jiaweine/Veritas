from __future__ import annotations

from dataclasses import dataclass, field

from .models import ReportedNumber, SourceLocation
from .types import Materiality


@dataclass(frozen=True)
class SEMFitSummary:
    """Paper-only SEM/CFA fit statistics for one fitted model."""

    object_id: str
    chi_square: ReportedNumber
    degrees_of_freedom: int
    reported_p_value: ReportedNumber | None = None
    n_observations: int | None = None
    reported_rmsea: ReportedNumber | None = None
    rmsea_sample_size_basis: str = "unknown"  # n | n_minus_1 | unknown
    baseline_chi_square: ReportedNumber | None = None
    baseline_degrees_of_freedom: int | None = None
    reported_cfi: ReportedNumber | None = None
    reported_tli: ReportedNumber | None = None
    log_likelihood: ReportedNumber | None = None
    free_parameters: int | None = None
    reported_aic: ReportedNumber | None = None
    reported_bic: ReportedNumber | None = None
    estimator_path: str = "unknown"  # ml_unscaled | robust_scaled | wlsmv | unknown
    unscaled_fit_statistics_verified: bool = False
    baseline_model_verified: bool = False
    information_criteria_definition: str = "unknown"  # standard_ml | unknown
    materiality: Materiality = Materiality.SECONDARY_RESULT
    source: SourceLocation = field(default_factory=SourceLocation)

    def __post_init__(self) -> None:
        if self.degrees_of_freedom < 0:
            raise ValueError("SEM degrees_of_freedom cannot be negative")
        if self.n_observations is not None and self.n_observations <= 0:
            raise ValueError("SEM n_observations must be positive")
        if self.baseline_degrees_of_freedom is not None and self.baseline_degrees_of_freedom < 0:
            raise ValueError("baseline_degrees_of_freedom cannot be negative")
        if self.free_parameters is not None and self.free_parameters < 0:
            raise ValueError("free_parameters cannot be negative")


@dataclass(frozen=True)
class SEMNestedComparison:
    """Nested SEM/CFA comparison whose exact difference-test method must be identified."""

    object_id: str
    less_restricted_chi_square: ReportedNumber
    less_restricted_df: int
    more_restricted_chi_square: ReportedNumber
    more_restricted_df: int
    reported_delta_chi_square: ReportedNumber | None = None
    reported_delta_df: ReportedNumber | None = None
    reported_delta_p_value: ReportedNumber | None = None
    difference_method: str = "unknown"  # plain_unscaled_ml | scaled_or_robust | unknown
    nested_models_verified: bool = False
    same_sample_verified: bool = False
    unscaled_ml_difference_verified: bool = False
    materiality: Materiality = Materiality.SECONDARY_RESULT
    source: SourceLocation = field(default_factory=SourceLocation)

    def __post_init__(self) -> None:
        if self.less_restricted_df < 0 or self.more_restricted_df < 0:
            raise ValueError("nested SEM degrees of freedom cannot be negative")
