from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from enum import Enum

from .claims import (
    ClaimEdge,
    EvidenceNodeKind,
    RelationType,
    StatisticalClaimGraph,
)
from .models import SourceLocation

_LABEL_SPACE_RE = re.compile(r"\s+")
_LABEL_PUNCT_RE = re.compile(r"[^\w%]+", flags=re.UNICODE)


class ScaleTransformation(str, Enum):
    LEVEL = "level"
    LOG = "log"
    LOG1P = "log1p"
    STANDARDIZED = "standardized"
    PERCENT = "percent"
    PERCENTAGE_POINT = "percentage_point"
    PROBABILITY = "probability"
    LOG_ODDS = "log_odds"
    ODDS_RATIO = "odds_ratio"
    UNKNOWN = "unknown"


_TRANSFORMATION_ALIASES = {
    "level": ScaleTransformation.LEVEL,
    "levels": ScaleTransformation.LEVEL,
    "raw": ScaleTransformation.LEVEL,
    "untransformed": ScaleTransformation.LEVEL,
    "log": ScaleTransformation.LOG,
    "ln": ScaleTransformation.LOG,
    "natural log": ScaleTransformation.LOG,
    "natural logarithm": ScaleTransformation.LOG,
    "log1p": ScaleTransformation.LOG1P,
    "log 1 plus x": ScaleTransformation.LOG1P,
    "standardized": ScaleTransformation.STANDARDIZED,
    "standardised": ScaleTransformation.STANDARDIZED,
    "z score": ScaleTransformation.STANDARDIZED,
    "zscore": ScaleTransformation.STANDARDIZED,
    "standard deviation units": ScaleTransformation.STANDARDIZED,
    "percent": ScaleTransformation.PERCENT,
    "percentage": ScaleTransformation.PERCENT,
    "%": ScaleTransformation.PERCENT,
    "percentage point": ScaleTransformation.PERCENTAGE_POINT,
    "percentage points": ScaleTransformation.PERCENTAGE_POINT,
    "pp": ScaleTransformation.PERCENTAGE_POINT,
    "probability": ScaleTransformation.PROBABILITY,
    "probability scale": ScaleTransformation.PROBABILITY,
    "log odds": ScaleTransformation.LOG_ODDS,
    "logit": ScaleTransformation.LOG_ODDS,
    "odds ratio": ScaleTransformation.ODDS_RATIO,
    "or": ScaleTransformation.ODDS_RATIO,
    "unknown": ScaleTransformation.UNKNOWN,
    "": ScaleTransformation.UNKNOWN,
}


@dataclass(frozen=True)
class EstimandIdentity:
    outcome: str
    treatment: str
    transformation: ScaleTransformation = ScaleTransformation.LEVEL
    population: str | None = None
    time_horizon: str | None = None
    unit: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, str) or not self.outcome.strip():
            raise ValueError("estimand outcome is required")
        if not isinstance(self.treatment, str) or not self.treatment.strip():
            raise ValueError("estimand treatment is required")
        if not isinstance(self.transformation, ScaleTransformation):
            raise TypeError("estimand transformation must be a ScaleTransformation")
        for label, value in (
            ("population", self.population),
            ("time_horizon", self.time_horizon),
            ("unit", self.unit),
        ):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"estimand {label} must be a non-empty string or null")


@dataclass(frozen=True)
class IdentityMatch:
    claim: EstimandIdentity
    estimate: EstimandIdentity
    confidence: float
    matched_dimensions: tuple[str, ...]
    conflicting_dimensions: tuple[str, ...]
    unresolved_dimensions: tuple[str, ...]

    def __post_init__(self) -> None:
        if not math.isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("identity match confidence must be finite and in [0, 1]")

    @property
    def exact_core_identity(self) -> bool:
        return not self.conflicting_dimensions and all(
            name in self.matched_dimensions for name in ("outcome", "treatment", "transformation")
        )


@dataclass(frozen=True)
class ClaimEstimateAlignment:
    claim_id: str
    estimate_object_id: str
    identity_match: IdentityMatch
    extraction_confidence: float
    matcher_confidence: float
    claim_source: SourceLocation
    estimate_source: SourceLocation

    def __post_init__(self) -> None:
        for label, value in (
            ("extraction_confidence", self.extraction_confidence),
            ("matcher_confidence", self.matcher_confidence),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{label} must be numeric")
            if not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"{label} must be finite and in [0, 1]")

    @property
    def effective_confidence(self) -> float:
        return min(
            self.identity_match.confidence,
            float(self.extraction_confidence),
            float(self.matcher_confidence),
        )

    def eligible_for_cross_location_e3(
        self,
        *,
        minimum_identity_confidence: float = 0.90,
        minimum_effective_confidence: float = 0.90,
    ) -> bool:
        return (
            self.identity_match.exact_core_identity
            and self.identity_match.confidence >= minimum_identity_confidence
            and self.effective_confidence >= minimum_effective_confidence
        )


def normalize_identity_label(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("identity labels must be non-empty strings")
    text = unicodedata.normalize("NFKC", value).casefold().strip()
    text = text.replace("&", " and ")
    text = _LABEL_PUNCT_RE.sub(" ", text)
    return _LABEL_SPACE_RE.sub(" ", text).strip()


def normalize_scale_transformation(value: str | ScaleTransformation | None) -> ScaleTransformation:
    if value is None:
        return ScaleTransformation.UNKNOWN
    if isinstance(value, ScaleTransformation):
        return value
    normalized = normalize_identity_label(value)
    try:
        return _TRANSFORMATION_ALIASES[normalized]
    except KeyError as exc:
        raise ValueError(f"unsupported scale transformation: {value!r}") from exc


def normalize_estimand_identity(
    *,
    outcome: str,
    treatment: str,
    transformation: str | ScaleTransformation | None = ScaleTransformation.LEVEL,
    population: str | None = None,
    time_horizon: str | None = None,
    unit: str | None = None,
) -> EstimandIdentity:
    return EstimandIdentity(
        outcome=normalize_identity_label(outcome),
        treatment=normalize_identity_label(treatment),
        transformation=normalize_scale_transformation(transformation),
        population=_normalize_optional_label(population),
        time_horizon=_normalize_optional_label(time_horizon),
        unit=_normalize_optional_label(unit),
    )


def compare_estimand_identity(
    claim: EstimandIdentity,
    estimate: EstimandIdentity,
) -> IdentityMatch:
    """Compare estimands dimension by dimension without fuzzy semantic guessing.

    The three core dimensions carry 0.90 of the score. Population and time horizon account for
    the remaining 0.10 when both sides provide them. Unknown optional dimensions never become
    implicit matches, so cross-location hard evidence cannot be promoted by missing metadata.
    """

    weights = {
        "outcome": 0.40,
        "treatment": 0.35,
        "transformation": 0.15,
        "population": 0.05,
        "time_horizon": 0.05,
    }
    matched: list[str] = []
    conflicting: list[str] = []
    unresolved: list[str] = []
    score = 0.0

    for dimension, weight in weights.items():
        claim_value = getattr(claim, dimension)
        estimate_value = getattr(estimate, dimension)
        if dimension == "transformation":
            if (
                claim_value is ScaleTransformation.UNKNOWN
                or estimate_value is ScaleTransformation.UNKNOWN
            ):
                unresolved.append(dimension)
                continue
        elif claim_value is None or estimate_value is None:
            unresolved.append(dimension)
            continue

        if claim_value == estimate_value:
            matched.append(dimension)
            score += weight
        else:
            conflicting.append(dimension)

    if claim.unit is not None and estimate.unit is not None:
        if claim.unit == estimate.unit:
            matched.append("unit")
        else:
            conflicting.append("unit")

    return IdentityMatch(
        claim=claim,
        estimate=estimate,
        confidence=round(score, 12),
        matched_dimensions=tuple(matched),
        conflicting_dimensions=tuple(conflicting),
        unresolved_dimensions=tuple(unresolved),
    )


def build_claim_estimate_alignment(
    graph: StatisticalClaimGraph,
    *,
    claim_id: str,
    estimate_object_id: str,
    claim_identity: EstimandIdentity,
    estimate_identity: EstimandIdentity,
    matcher_confidence: float = 1.0,
) -> ClaimEstimateAlignment:
    try:
        claim = graph.claims[claim_id]
    except KeyError as exc:
        raise ValueError(f"unknown claim id: {claim_id!r}") from exc
    try:
        estimate = graph.objects[estimate_object_id]
    except KeyError as exc:
        raise ValueError(f"unknown estimate object id: {estimate_object_id!r}") from exc

    field_confidence = min(
        (field.extraction_confidence for field in estimate.fields.values()),
        default=1.0,
    )
    extraction_confidence = min(claim.extraction_confidence, field_confidence)
    return ClaimEstimateAlignment(
        claim_id=claim_id,
        estimate_object_id=estimate_object_id,
        identity_match=compare_estimand_identity(claim_identity, estimate_identity),
        extraction_confidence=extraction_confidence,
        matcher_confidence=matcher_confidence,
        claim_source=claim.source,
        estimate_source=estimate.source,
    )


def add_claim_estimate_candidate(
    graph: StatisticalClaimGraph,
    alignment: ClaimEstimateAlignment,
) -> ClaimEdge:
    """Persist a candidate claim→estimate link while carrying uncertainty and source spans."""

    edge = ClaimEdge(
        source_id=alignment.claim_id,
        target_id=alignment.estimate_object_id,
        relation=RelationType.REPORTS,
        confidence=alignment.matcher_confidence,
        extraction_confidence=alignment.extraction_confidence,
        identity_confidence=alignment.identity_match.confidence,
        sources=(alignment.claim_source, alignment.estimate_source),
    )
    graph.add_edge(edge)
    return edge


def require_cross_location_e3_identity(
    alignment: ClaimEstimateAlignment,
    *,
    minimum_identity_confidence: float = 0.90,
    minimum_effective_confidence: float = 0.90,
) -> None:
    """Fail closed before a claim/object link can justify cross-location E3 evidence."""

    if not alignment.eligible_for_cross_location_e3(
        minimum_identity_confidence=minimum_identity_confidence,
        minimum_effective_confidence=minimum_effective_confidence,
    ):
        raise ValueError(
            "cross-location E3 requires high-confidence claim/estimand identity with "
            "high-confidence extraction"
        )


def link_empirical_evidence_chain(
    graph: StatisticalClaimGraph,
    *,
    estimate_object_id: str,
    sample_id: str,
    data_id: str,
    code_id: str,
    assumption_ids: tuple[str, ...] = (),
    confidence: float = 1.0,
) -> tuple[ClaimEdge, ...]:
    """Build Estimate→Sample→Data→Code→Assumption links from artifact-derived nodes."""

    if estimate_object_id not in graph.objects:
        raise ValueError(f"unknown estimate object id: {estimate_object_id!r}")
    _require_evidence_kind(graph, sample_id, EvidenceNodeKind.SAMPLE)
    _require_evidence_kind(graph, data_id, EvidenceNodeKind.DATA)
    _require_evidence_kind(graph, code_id, EvidenceNodeKind.CODE)
    for assumption_id in assumption_ids:
        _require_evidence_kind(graph, assumption_id, EvidenceNodeKind.ASSUMPTION)

    estimate = graph.objects[estimate_object_id]
    sample = graph.evidence_nodes[sample_id]
    data = graph.evidence_nodes[data_id]
    code = graph.evidence_nodes[code_id]
    links = [
        ClaimEdge(
            estimate_object_id,
            sample_id,
            RelationType.USES_SAMPLE,
            confidence=confidence,
            extraction_confidence=min(sample.extraction_confidence, _object_confidence(estimate)),
            sources=(estimate.source, sample.source),
        ),
        ClaimEdge(
            sample_id,
            data_id,
            RelationType.DERIVED_FROM,
            confidence=confidence,
            extraction_confidence=min(sample.extraction_confidence, data.extraction_confidence),
            sources=(sample.source, data.source),
        ),
        ClaimEdge(
            data_id,
            code_id,
            RelationType.GENERATED_BY,
            confidence=confidence,
            extraction_confidence=min(data.extraction_confidence, code.extraction_confidence),
            sources=(data.source, code.source),
        ),
    ]
    for assumption_id in assumption_ids:
        assumption = graph.evidence_nodes[assumption_id]
        links.append(
            ClaimEdge(
                code_id,
                assumption_id,
                RelationType.REQUIRES_ASSUMPTION,
                confidence=confidence,
                extraction_confidence=min(
                    code.extraction_confidence,
                    assumption.extraction_confidence,
                ),
                sources=(code.source, assumption.source),
            )
        )
    for edge in links:
        graph.add_edge(edge)
    return tuple(links)


def _object_confidence(graph_object) -> float:
    return min(
        (field.extraction_confidence for field in graph_object.fields.values()),
        default=1.0,
    )


def _require_evidence_kind(
    graph: StatisticalClaimGraph,
    node_id: str,
    expected: EvidenceNodeKind,
) -> None:
    try:
        node = graph.evidence_nodes[node_id]
    except KeyError as exc:
        raise ValueError(f"unknown evidence node id: {node_id!r}") from exc
    if node.kind is not expected:
        raise ValueError(
            f"evidence node {node_id!r} must have kind {expected.value!r}, got {node.kind.value!r}"
        )


def _normalize_optional_label(value: str | None) -> str | None:
    if value is None:
        return None
    return normalize_identity_label(value)
