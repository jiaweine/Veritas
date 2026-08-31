from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from enum import Enum
from hashlib import sha256
from typing import Any

from .claims import ArtifactRef, JsonScalar
from .extraction import ExtractionDecision, ExtractionResolution
from .models import SourceLocation

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class EvidenceKind(str, Enum):
    FIELD = "field"
    SEMANTIC_GATE = "semantic_gate"


class PromotionDecision(str, Enum):
    PROMOTE = "promote"
    REVIEW = "review"
    UNVERIFIABLE = "unverifiable"


class CalibrationScope(str, Enum):
    """Authority carried by the calibration used for an ingestion protocol.

    Scope is deliberately independent of detector arithmetic. Benchmark and research calibrations
    may promote an object into a detector for evaluation, but only PRODUCTION_CERTIFIED calibration
    can make the object eligible for a production hard-audit path.
    """

    UNVERIFIED = "unverified"
    BENCHMARK = "benchmark"
    RESEARCH = "research"
    PRODUCTION_CERTIFIED = "production_certified"


@dataclass(frozen=True)
class IngestionProtocol:
    """Identity and calibration authority of the extraction/promotion protocol for one audit run."""

    protocol_id: str
    protocol_version: str
    object_schema_version: str
    calibration_sha256: str
    parser_versions: tuple[tuple[str, str], ...]
    calibration_scope: CalibrationScope = CalibrationScope.UNVERIFIED
    policy_note: str = ""

    def __post_init__(self) -> None:
        if not self.protocol_id.strip() or not self.protocol_version.strip():
            raise ValueError("protocol_id and protocol_version are required")
        if not self.object_schema_version.strip():
            raise ValueError("object_schema_version is required")
        if not _SHA256_RE.fullmatch(self.calibration_sha256):
            raise ValueError("calibration_sha256 must be a lowercase SHA-256 hex digest")
        parser_ids = [parser_id for parser_id, _ in self.parser_versions]
        if len(set(parser_ids)) != len(parser_ids):
            raise ValueError("parser_versions must contain unique parser ids")

    def sha256(self) -> str:
        payload = {
            "protocol_id": self.protocol_id,
            "protocol_version": self.protocol_version,
            "object_schema_version": self.object_schema_version,
            "calibration_sha256": self.calibration_sha256,
            "calibration_scope": self.calibration_scope.value,
            "parser_versions": sorted(self.parser_versions),
            "policy_note": self.policy_note,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return sha256(raw).hexdigest()


@dataclass(frozen=True)
class ResolvedEvidence:
    """A calibrated field or semantic assertion with all supporting parser evidence."""

    key: str
    kind: EvidenceKind
    value: JsonScalar
    resolution: ExtractionResolution
    extraction_confidence: float
    evidence_note: str = ""

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("evidence key is required")
        if not 0.0 <= self.extraction_confidence <= 1.0:
            raise ValueError("extraction_confidence must be in [0, 1]")
        if self.resolution.decision is ExtractionDecision.ACCEPT:
            if self.resolution.normalized_value is None:
                raise ValueError("accepted evidence requires a normalized value")
            if not self.resolution.accepted_candidates:
                raise ValueError("accepted evidence requires supporting candidates")

    @property
    def parser_families(self) -> frozenset[str]:
        return frozenset(candidate.parser_family for candidate in self.resolution.accepted_candidates)

    @property
    def sources(self) -> tuple[SourceLocation, ...]:
        return tuple(candidate.source for candidate in self.resolution.accepted_candidates)


@dataclass(frozen=True)
class ObjectDraft:
    draft_id: str
    object_type: str
    artifact_id: str
    fields: dict[str, ResolvedEvidence] = field(default_factory=dict)
    semantic_gates: dict[str, ResolvedEvidence] = field(default_factory=dict)
    source: SourceLocation = field(default_factory=SourceLocation)

    def __post_init__(self) -> None:
        if not self.draft_id.strip() or not self.object_type.strip() or not self.artifact_id.strip():
            raise ValueError("draft_id, object_type, and artifact_id are required")
        if any(item.kind is not EvidenceKind.FIELD for item in self.fields.values()):
            raise ValueError("ObjectDraft.fields may only contain FIELD evidence")
        if any(item.kind is not EvidenceKind.SEMANTIC_GATE for item in self.semantic_gates.values()):
            raise ValueError("ObjectDraft.semantic_gates may only contain SEMANTIC_GATE evidence")
        if any(key != item.key for key, item in self.fields.items()):
            raise ValueError("field evidence dictionary keys must match evidence.key")
        if any(key != item.key for key, item in self.semantic_gates.items()):
            raise ValueError("semantic gate dictionary keys must match evidence.key")


@dataclass(frozen=True)
class PromotionSpec:
    object_type: str
    required_fields: tuple[str, ...]
    critical_semantic_gates: tuple[str, ...]
    min_extraction_confidence: float = 0.98
    min_independent_parser_families: int = 2
    require_page_anchor: bool = True
    require_location_anchor: bool = True
    spec_version: str = "1"

    def __post_init__(self) -> None:
        if not 0.0 <= self.min_extraction_confidence <= 1.0:
            raise ValueError("min_extraction_confidence must be in [0, 1]")
        if self.min_independent_parser_families < 1:
            raise ValueError("min_independent_parser_families must be positive")
        if len(set(self.required_fields)) != len(self.required_fields):
            raise ValueError("required_fields must be unique")
        if len(set(self.critical_semantic_gates)) != len(self.critical_semantic_gates):
            raise ValueError("critical_semantic_gates must be unique")

    def sha256(self) -> str:
        payload = asdict(self)
        payload["required_fields"] = sorted(self.required_fields)
        payload["critical_semantic_gates"] = sorted(self.critical_semantic_gates)
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return sha256(raw).hexdigest()


@dataclass(frozen=True)
class PromotionReport:
    draft_id: str
    object_type: str
    decision: PromotionDecision
    reasons: tuple[str, ...]
    field_values: dict[str, JsonScalar]
    semantic_values: dict[str, JsonScalar]
    artifact_sha256: str | None
    protocol_sha256: str
    promotion_spec_sha256: str
    evidence_sha256: str
    calibration_scope: CalibrationScope

    @property
    def detector_ready(self) -> bool:
        """Whether the object may enter deterministic detectors for evaluation/research."""
        return self.decision is PromotionDecision.PROMOTE

    @property
    def hard_audit_ready(self) -> bool:
        """Whether the promoted object carries production-certified calibration authority."""
        return self.detector_ready and self.calibration_scope is CalibrationScope.PRODUCTION_CERTIFIED


@dataclass(frozen=True)
class DetectorInputEnvelope:
    """A promotion-gated detector input with explicit calibration authority."""

    statistical_object: object
    object_id: str
    artifact_sha256: str
    protocol_sha256: str
    promotion_spec_sha256: str
    evidence_sha256: str
    calibration_scope: CalibrationScope

    def __post_init__(self) -> None:
        for name, value in (
            ("artifact_sha256", self.artifact_sha256),
            ("protocol_sha256", self.protocol_sha256),
            ("promotion_spec_sha256", self.promotion_spec_sha256),
            ("evidence_sha256", self.evidence_sha256),
        ):
            if not _SHA256_RE.fullmatch(value):
                raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")

    @property
    def production_authorized(self) -> bool:
        return self.calibration_scope is CalibrationScope.PRODUCTION_CERTIFIED


@dataclass
class EvidenceLedger:
    artifact: ArtifactRef
    protocol: IngestionProtocol
    drafts: dict[str, ObjectDraft] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.artifact.sha256 is not None and not _SHA256_RE.fullmatch(self.artifact.sha256):
            raise ValueError("artifact.sha256 must be a lowercase SHA-256 hex digest when present")

    def add_draft(self, draft: ObjectDraft) -> None:
        if draft.draft_id in self.drafts:
            raise ValueError(f"duplicate draft id: {draft.draft_id}")
        if draft.artifact_id != self.artifact.artifact_id:
            raise ValueError("draft artifact_id does not match ledger artifact")
        self.drafts[draft.draft_id] = draft

    def sha256(self) -> str:
        payload = {
            "artifact": asdict(self.artifact),
            "protocol_sha256": self.protocol.sha256(),
            "drafts": [
                _draft_payload(draft)
                for draft in sorted(self.drafts.values(), key=lambda item: item.draft_id)
            ],
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return sha256(raw).hexdigest()

    def evaluate(self, draft_id: str, spec: PromotionSpec) -> PromotionReport:
        draft = self.drafts[draft_id]
        reasons: list[str] = []
        review_reasons: list[str] = []

        if draft.object_type != spec.object_type:
            reasons.append(f"draft object_type {draft.object_type!r} does not match spec {spec.object_type!r}")
        if self.artifact.sha256 is None:
            reasons.append("source artifact has no content SHA-256")

        field_values: dict[str, JsonScalar] = {}
        semantic_values: dict[str, JsonScalar] = {}

        for key in spec.required_fields:
            item = draft.fields.get(key)
            if item is None:
                reasons.append(f"missing required field: {key}")
                continue
            item_reasons, item_review = _evidence_problems(
                item,
                artifact_id=self.artifact.artifact_id,
                spec=spec,
            )
            reasons.extend(f"field {key}: {reason}" for reason in item_reasons)
            review_reasons.extend(f"field {key}: {reason}" for reason in item_review)
            if not item_reasons and not item_review:
                field_values[key] = item.value

        for key in spec.critical_semantic_gates:
            item = draft.semantic_gates.get(key)
            if item is None:
                reasons.append(f"missing critical semantic gate: {key}")
                continue
            item_reasons, item_review = _evidence_problems(
                item,
                artifact_id=self.artifact.artifact_id,
                spec=spec,
            )
            reasons.extend(f"semantic gate {key}: {reason}" for reason in item_reasons)
            review_reasons.extend(f"semantic gate {key}: {reason}" for reason in item_review)
            if not item_reasons and not item_review:
                semantic_values[key] = item.value

        if reasons:
            decision = PromotionDecision.UNVERIFIABLE
            all_reasons = tuple(reasons + review_reasons)
        elif review_reasons:
            decision = PromotionDecision.REVIEW
            all_reasons = tuple(review_reasons)
        else:
            decision = PromotionDecision.PROMOTE
            all_reasons = ()

        evidence_hash = _draft_evidence_sha256(draft)
        return PromotionReport(
            draft_id=draft.draft_id,
            object_type=draft.object_type,
            decision=decision,
            reasons=all_reasons,
            field_values=field_values,
            semantic_values=semantic_values,
            artifact_sha256=self.artifact.sha256,
            protocol_sha256=self.protocol.sha256(),
            promotion_spec_sha256=spec.sha256(),
            evidence_sha256=evidence_hash,
            calibration_scope=self.protocol.calibration_scope,
        )

    def promote(
        self,
        draft_id: str,
        spec: PromotionSpec,
        builder: Callable[[dict[str, JsonScalar], dict[str, JsonScalar], ObjectDraft], object],
    ) -> tuple[PromotionReport, DetectorInputEnvelope | None]:
        report = self.evaluate(draft_id, spec)
        if not report.detector_ready:
            return report, None
        draft = self.drafts[draft_id]
        statistical_object = builder(report.field_values, report.semantic_values, draft)
        object_id = getattr(statistical_object, "object_id", draft.draft_id)
        assert report.artifact_sha256 is not None
        envelope = DetectorInputEnvelope(
            statistical_object=statistical_object,
            object_id=str(object_id),
            artifact_sha256=report.artifact_sha256,
            protocol_sha256=report.protocol_sha256,
            promotion_spec_sha256=report.promotion_spec_sha256,
            evidence_sha256=report.evidence_sha256,
            calibration_scope=report.calibration_scope,
        )
        return report, envelope


def _source_is_precise(source: SourceLocation, *, artifact_id: str, spec: PromotionSpec) -> bool:
    if source.artifact_id != artifact_id:
        return False
    if spec.require_page_anchor and source.page is None:
        return False
    if spec.require_location_anchor:
        location = any(
            value is not None and value != ""
            for value in (
                source.section,
                source.table,
                source.figure,
                source.row,
                source.column,
                source.text_quote,
                source.bbox,
            )
        )
        if not location:
            return False
    return True


def _evidence_problems(
    item: ResolvedEvidence,
    *,
    artifact_id: str,
    spec: PromotionSpec,
) -> tuple[list[str], list[str]]:
    hard: list[str] = []
    review: list[str] = []
    decision = item.resolution.decision
    if decision is ExtractionDecision.CONFLICT:
        review.append("calibrated parser families disagree")
        return hard, review
    if decision is ExtractionDecision.DOMAIN_SHIFT:
        hard.append("input was rejected by the calibrated domain-shift gate")
        return hard, review
    if decision is not ExtractionDecision.ACCEPT:
        hard.append("extraction did not receive conformal ACCEPT")
        return hard, review
    if item.extraction_confidence < spec.min_extraction_confidence:
        review.append(
            f"extraction confidence {item.extraction_confidence:.3f} is below promotion threshold "
            f"{spec.min_extraction_confidence:.3f}"
        )
    if len(item.parser_families) < spec.min_independent_parser_families:
        hard.append(
            f"only {len(item.parser_families)} independent parser families support the accepted value"
        )
    imprecise = [
        source for source in item.sources if not _source_is_precise(source, artifact_id=artifact_id, spec=spec)
    ]
    if imprecise:
        hard.append("one or more accepted candidates lack the required precise source anchor")
    return hard, review


def _candidate_payload(candidate: Any) -> dict[str, Any]:
    return {
        "parser_id": candidate.parser_id,
        "parser_family": candidate.parser_family,
        "raw": candidate.raw,
        "normalized_value": candidate.normalized_value,
        "nonconformity_score": candidate.nonconformity_score,
        "source": asdict(candidate.source),
    }


def _resolution_payload(resolution: ExtractionResolution) -> dict[str, Any]:
    return {
        "decision": resolution.decision.value,
        "normalized_value": resolution.normalized_value,
        "accepted_candidates": sorted(
            (_candidate_payload(candidate) for candidate in resolution.accepted_candidates),
            key=lambda item: (item["parser_family"], item["parser_id"], item["normalized_value"]),
        ),
        "calibration_threshold": resolution.calibration_threshold,
        "shift_p_value": resolution.shift_p_value,
        "reason": resolution.reason,
    }


def _evidence_payload(item: ResolvedEvidence) -> dict[str, Any]:
    return {
        "key": item.key,
        "kind": item.kind.value,
        "value": item.value,
        "resolution": _resolution_payload(item.resolution),
        "extraction_confidence": item.extraction_confidence,
        "evidence_note": item.evidence_note,
    }


def _draft_payload(draft: ObjectDraft) -> dict[str, Any]:
    return {
        "draft_id": draft.draft_id,
        "object_type": draft.object_type,
        "artifact_id": draft.artifact_id,
        "source": asdict(draft.source),
        "fields": [
            _evidence_payload(item) for item in sorted(draft.fields.values(), key=lambda evidence: evidence.key)
        ],
        "semantic_gates": [
            _evidence_payload(item)
            for item in sorted(draft.semantic_gates.values(), key=lambda evidence: evidence.key)
        ],
    }


def _draft_evidence_sha256(draft: ObjectDraft) -> str:
    raw = json.dumps(_draft_payload(draft), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return sha256(raw).hexdigest()
