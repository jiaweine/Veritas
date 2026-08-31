from __future__ import annotations

from dataclasses import dataclass, field

from .models import ReportedNumber, SourceLocation
from .types import Materiality


@dataclass(frozen=True)
class MetaStudyEffect:
    study_id: str
    effect: ReportedNumber
    se: ReportedNumber
    reported_weight_percent: ReportedNumber | None = None

    def __post_init__(self) -> None:
        if not self.study_id.strip():
            raise ValueError("study_id is required")
        if self.se.value < 0:
            raise ValueError("reported study SE cannot be negative")


@dataclass(frozen=True)
class MetaAnalysisSummary:
    """Inverse-variance meta-analysis quantities reported on one additive analysis scale."""

    object_id: str
    studies: tuple[MetaStudyEffect, ...]
    model: str = "unknown"  # fixed_inverse_variance | random_inverse_variance_reported_tau2 | unknown
    reported_tau_squared: ReportedNumber | None = None
    tau_squared_estimator: str = "unknown"
    reported_pooled_effect: ReportedNumber | None = None
    reported_pooled_se: ReportedNumber | None = None
    reported_pooled_p_value: ReportedNumber | None = None
    reported_ci_lower: ReportedNumber | None = None
    reported_ci_upper: ReportedNumber | None = None
    confidence_level: float = 0.95
    inference_method: str = "unknown"  # normal | hksj | hksj_modified | unknown
    reported_hksj_q: ReportedNumber | None = None
    reported_prediction_lower: ReportedNumber | None = None
    reported_prediction_upper: ReportedNumber | None = None
    prediction_level: float = 0.95
    prediction_method: str = "unknown"  # hts_t_k_minus_2_conventional | unknown
    reported_q: ReportedNumber | None = None
    reported_q_df: ReportedNumber | None = None
    reported_q_p_value: ReportedNumber | None = None
    reported_i_squared: ReportedNumber | None = None
    effects_on_common_analysis_scale_verified: bool = False
    independent_effects_verified: bool = False
    inverse_variance_weighting_verified: bool = False
    q_definition_verified: bool = False
    p_value_adjusted: bool = False
    materiality: Materiality = Materiality.MAIN_EMPIRICAL_CLAIM
    source: SourceLocation = field(default_factory=SourceLocation)

    def __post_init__(self) -> None:
        if len(self.studies) < 2:
            raise ValueError("meta-analysis requires at least two study effects")
        study_ids = [study.study_id for study in self.studies]
        if len(set(study_ids)) != len(study_ids):
            raise ValueError("meta-analysis study_id values must be unique")
        if not 0.0 < self.confidence_level < 1.0:
            raise ValueError("confidence_level must lie strictly between 0 and 1")
        if not 0.0 < self.prediction_level < 1.0:
            raise ValueError("prediction_level must lie strictly between 0 and 1")
