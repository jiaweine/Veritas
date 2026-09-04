from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from .models import SourceLocation

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class RegistrationKind(str, Enum):
    PREREGISTRATION = "preregistration"
    PAP = "pap"
    REGISTRY = "registry"


class PlanItemKind(str, Enum):
    HYPOTHESIS = "hypothesis"
    OUTCOME = "outcome"
    TREATMENT = "treatment"
    SAMPLE_RULE = "sample_rule"
    EXCLUSION = "exclusion"
    TRANSFORMATION = "transformation"
    MODEL = "model"
    INFERENCE = "inference"


class PlanComparisonStatus(str, Enum):
    MATCH = "match"
    DEVIATION = "deviation"
    UNDECLARED = "undeclared"
    UNOBSERVED = "unobserved"
    UNVERIFIABLE = "unverifiable"


@dataclass(frozen=True)
class RegisteredPlanItem:
    item_id: str
    kind: PlanItemKind
    specification: str
    source: SourceLocation

    def __post_init__(self) -> None:
        _validate_item(self.item_id, self.kind, self.specification, label="registered plan item")


@dataclass(frozen=True)
class RegistrationPlan:
    registration_id: str
    kind: RegistrationKind
    artifact_sha256: str
    items: tuple[RegisteredPlanItem, ...]
    source: SourceLocation
    artifact_identity_verified: bool

    def __post_init__(self) -> None:
        if not isinstance(self.registration_id, str) or not self.registration_id.strip():
            raise ValueError("registration_id is required")
        if not isinstance(self.kind, RegistrationKind):
            raise TypeError("registration kind must be a RegistrationKind")
        if not _SHA256_RE.fullmatch(self.artifact_sha256):
            raise ValueError("registration artifact_sha256 must be lowercase hex")
        if type(self.artifact_identity_verified) is not bool:
            raise TypeError("registration artifact_identity_verified must be a boolean")
        ids = tuple(item.item_id for item in self.items)
        if len(ids) != len(set(ids)):
            raise ValueError("registered plan item ids must be unique")


@dataclass(frozen=True)
class ObservedAnalysisItem:
    observation_id: str
    kind: PlanItemKind
    specification: str
    source: SourceLocation
    declared_plan_item_id: str | None = None
    extraction_confidence: float = 1.0

    def __post_init__(self) -> None:
        _validate_item(self.observation_id, self.kind, self.specification, label="observed analysis item")
        if self.declared_plan_item_id is not None and (
            not isinstance(self.declared_plan_item_id, str) or not self.declared_plan_item_id.strip()
        ):
            raise ValueError("declared_plan_item_id must be a non-empty string or null")
        if isinstance(self.extraction_confidence, bool) or not isinstance(
            self.extraction_confidence, (int, float)
        ):
            raise TypeError("observed extraction_confidence must be numeric")
        if not 0.0 <= float(self.extraction_confidence) <= 1.0:
            raise ValueError("observed extraction_confidence must be in [0, 1]")


@dataclass(frozen=True)
class PlanComparison:
    plan_item_id: str | None
    observation_id: str | None
    kind: PlanItemKind
    status: PlanComparisonStatus
    registered_specification: str | None
    observed_specification: str | None
    registered_source: SourceLocation | None
    observed_source: SourceLocation | None
    explanation: str


@dataclass(frozen=True)
class RegistrationComparisonReport:
    registration_id: str
    registration_kind: RegistrationKind
    comparisons: tuple[PlanComparison, ...]

    @property
    def deviations(self) -> tuple[PlanComparison, ...]:
        return tuple(
            item
            for item in self.comparisons
            if item.status in {PlanComparisonStatus.DEVIATION, PlanComparisonStatus.UNDECLARED}
        )

    @property
    def fully_verifiable(self) -> bool:
        return all(item.status is not PlanComparisonStatus.UNVERIFIABLE for item in self.comparisons)


def compare_registration_plan(
    plan: RegistrationPlan,
    observed: tuple[ObservedAnalysisItem, ...],
    *,
    minimum_extraction_confidence: float = 0.90,
) -> RegistrationComparisonReport:
    """Compare preregistration/PAP/registry commitments without inferring author intent."""

    if not 0.0 <= minimum_extraction_confidence <= 1.0:
        raise ValueError("minimum_extraction_confidence must be in [0, 1]")
    observation_ids = tuple(item.observation_id for item in observed)
    if len(observation_ids) != len(set(observation_ids)):
        raise ValueError("observed analysis item ids must be unique")

    planned = {item.item_id: item for item in plan.items}
    comparisons: list[PlanComparison] = []
    seen_plan_ids: set[str] = set()

    for item in observed:
        if not plan.artifact_identity_verified or item.extraction_confidence < minimum_extraction_confidence:
            registered = planned.get(item.declared_plan_item_id or "")
            comparisons.append(
                PlanComparison(
                    plan_item_id=registered.item_id if registered else item.declared_plan_item_id,
                    observation_id=item.observation_id,
                    kind=item.kind,
                    status=PlanComparisonStatus.UNVERIFIABLE,
                    registered_specification=registered.specification if registered else None,
                    observed_specification=item.specification,
                    registered_source=registered.source if registered else None,
                    observed_source=item.source,
                    explanation="registration identity or observed-analysis extraction is not verified",
                )
            )
            if registered:
                seen_plan_ids.add(registered.item_id)
            continue

        if item.declared_plan_item_id is None:
            comparisons.append(
                PlanComparison(
                    None,
                    item.observation_id,
                    item.kind,
                    PlanComparisonStatus.UNDECLARED,
                    None,
                    item.specification,
                    None,
                    item.source,
                    "observed analysis item has no linked registered plan item",
                )
            )
            continue

        registered = planned.get(item.declared_plan_item_id)
        if registered is None:
            comparisons.append(
                PlanComparison(
                    item.declared_plan_item_id,
                    item.observation_id,
                    item.kind,
                    PlanComparisonStatus.UNDECLARED,
                    None,
                    item.specification,
                    None,
                    item.source,
                    "observed analysis item references an unknown registered plan item",
                )
            )
            continue
        if registered.item_id in seen_plan_ids:
            raise ValueError(f"multiple observations claim the same registered plan item: {registered.item_id!r}")
        seen_plan_ids.add(registered.item_id)

        if registered.kind is not item.kind:
            status = PlanComparisonStatus.DEVIATION
            explanation = "registered and observed item kinds differ"
        elif _normalize_specification(registered.specification) == _normalize_specification(item.specification):
            status = PlanComparisonStatus.MATCH
            explanation = "observed analysis matches the registered specification"
        else:
            status = PlanComparisonStatus.DEVIATION
            explanation = "observed analysis differs from the registered specification"
        comparisons.append(
            PlanComparison(
                registered.item_id,
                item.observation_id,
                item.kind,
                status,
                registered.specification,
                item.specification,
                registered.source,
                item.source,
                explanation,
            )
        )

    for item in plan.items:
        if item.item_id not in seen_plan_ids:
            comparisons.append(
                PlanComparison(
                    item.item_id,
                    None,
                    item.kind,
                    PlanComparisonStatus.UNOBSERVED if plan.artifact_identity_verified else PlanComparisonStatus.UNVERIFIABLE,
                    item.specification,
                    None,
                    item.source,
                    None,
                    "registered plan item was not observed in the analyzed artifact",
                )
            )

    return RegistrationComparisonReport(plan.registration_id, plan.kind, tuple(comparisons))


def _validate_item(item_id: str, kind: PlanItemKind, specification: str, *, label: str) -> None:
    if not isinstance(item_id, str) or not item_id.strip():
        raise ValueError(f"{label} id is required")
    if not isinstance(kind, PlanItemKind):
        raise TypeError(f"{label} kind must be a PlanItemKind")
    if not isinstance(specification, str) or not specification.strip():
        raise ValueError(f"{label} specification is required")


def _normalize_specification(value: str) -> str:
    return " ".join(value.casefold().split())
