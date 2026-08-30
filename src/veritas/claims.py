from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from .models import SourceLocation

JsonScalar = str | int | float | bool | None


class ClaimRole(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    ROBUSTNESS = "robustness"
    DESCRIPTIVE = "descriptive"
    METHOD = "method"


class RelationType(str, Enum):
    REPORTS = "reports"
    SUPPORTS = "supports"
    DERIVED_FROM = "derived_from"
    USES_SAMPLE = "uses_sample"
    USES_DESIGN = "uses_design"
    SAME_ESTIMAND_AS = "same_estimand_as"
    CONTRADICTS = "contradicts"


@dataclass(frozen=True)
class ArtifactRef:
    artifact_id: str
    kind: str
    sha256: str | None = None
    uri: str | None = None


@dataclass(frozen=True)
class ExtractedField:
    raw: str
    value: JsonScalar
    source: SourceLocation
    extraction_confidence: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.extraction_confidence <= 1.0:
            raise ValueError("extraction_confidence must be in [0, 1]")


@dataclass(frozen=True)
class ClaimNode:
    claim_id: str
    text: str
    role: ClaimRole
    source: SourceLocation
    estimand: str | None = None
    extraction_confidence: float = 1.0
    identity_confidence: float = 1.0

    def __post_init__(self) -> None:
        for name, value in (
            ("extraction_confidence", self.extraction_confidence),
            ("identity_confidence", self.identity_confidence),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")


@dataclass(frozen=True)
class StatisticalObjectNode:
    object_id: str
    object_type: str
    fields: dict[str, ExtractedField]
    source: SourceLocation


@dataclass(frozen=True)
class ClaimEdge:
    source_id: str
    target_id: str
    relation: RelationType
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("edge confidence must be in [0, 1]")


@dataclass
class StatisticalClaimGraph:
    artifacts: dict[str, ArtifactRef] = field(default_factory=dict)
    claims: dict[str, ClaimNode] = field(default_factory=dict)
    objects: dict[str, StatisticalObjectNode] = field(default_factory=dict)
    edges: list[ClaimEdge] = field(default_factory=list)

    def add_artifact(self, artifact: ArtifactRef) -> None:
        self._ensure_new_id(artifact.artifact_id)
        self.artifacts[artifact.artifact_id] = artifact

    def add_claim(self, claim: ClaimNode) -> None:
        self._ensure_new_id(claim.claim_id)
        self.claims[claim.claim_id] = claim

    def add_object(self, obj: StatisticalObjectNode) -> None:
        self._ensure_new_id(obj.object_id)
        self.objects[obj.object_id] = obj

    def add_edge(self, edge: ClaimEdge) -> None:
        known = set(self.claims) | set(self.objects) | set(self.artifacts)
        if edge.source_id not in known or edge.target_id not in known:
            raise ValueError("edge endpoints must already exist in the graph")
        self.edges.append(edge)

    def validate(self) -> None:
        known = set(self.claims) | set(self.objects) | set(self.artifacts)
        for edge in self.edges:
            if edge.source_id not in known or edge.target_id not in known:
                raise ValueError(f"dangling edge: {edge.source_id} -> {edge.target_id}")
        for claim in self.claims.values():
            if claim.source.artifact_id not in self.artifacts:
                raise ValueError(f"claim {claim.claim_id} references unknown artifact")
        for obj in self.objects.values():
            if obj.source.artifact_id not in self.artifacts:
                raise ValueError(f"object {obj.object_id} references unknown artifact")
            for field_value in obj.fields.values():
                if field_value.source.artifact_id not in self.artifacts:
                    raise ValueError(f"object field in {obj.object_id} references unknown artifact")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "artifacts": {key: asdict(value) for key, value in self.artifacts.items()},
            "claims": {
                key: {
                    **asdict(value),
                    "role": value.role.value,
                }
                for key, value in self.claims.items()
            },
            "objects": {
                key: {
                    "object_id": value.object_id,
                    "object_type": value.object_type,
                    "source": asdict(value.source),
                    "fields": {
                        field_name: {
                            **asdict(field_value),
                            "source": asdict(field_value.source),
                        }
                        for field_name, field_value in value.fields.items()
                    },
                }
                for key, value in self.objects.items()
            },
            "edges": [
                {
                    **asdict(edge),
                    "relation": edge.relation.value,
                }
                for edge in self.edges
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> StatisticalClaimGraph:
        graph = cls()
        for artifact in payload.get("artifacts", {}).values():
            graph.add_artifact(ArtifactRef(**artifact))
        for claim in payload.get("claims", {}).values():
            claim_data = dict(claim)
            claim_data["role"] = ClaimRole(claim_data["role"])
            claim_data["source"] = _source_from_dict(claim_data["source"])
            graph.add_claim(ClaimNode(**claim_data))
        for obj in payload.get("objects", {}).values():
            fields = {
                name: ExtractedField(
                    raw=value["raw"],
                    value=value["value"],
                    source=_source_from_dict(value["source"]),
                    extraction_confidence=value["extraction_confidence"],
                )
                for name, value in obj.get("fields", {}).items()
            }
            graph.add_object(
                StatisticalObjectNode(
                    object_id=obj["object_id"],
                    object_type=obj["object_type"],
                    fields=fields,
                    source=_source_from_dict(obj["source"]),
                )
            )
        for edge in payload.get("edges", []):
            graph.add_edge(
                ClaimEdge(
                    source_id=edge["source_id"],
                    target_id=edge["target_id"],
                    relation=RelationType(edge["relation"]),
                    confidence=edge.get("confidence", 1.0),
                )
            )
        graph.validate()
        return graph

    @classmethod
    def from_json(cls, payload: str) -> StatisticalClaimGraph:
        return cls.from_dict(json.loads(payload))

    def _ensure_new_id(self, node_id: str) -> None:
        if node_id in self.artifacts or node_id in self.claims or node_id in self.objects:
            raise ValueError(f"duplicate graph node id: {node_id}")


def _source_from_dict(payload: dict[str, Any]) -> SourceLocation:
    source = dict(payload)
    if source.get("bbox") is not None:
        source["bbox"] = tuple(source["bbox"])
    return SourceLocation(**source)
