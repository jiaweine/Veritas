from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from enum import Enum

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ProvenanceArtifactRole(str, Enum):
    RAW_DATA = "raw_data"
    ANALYSIS_DATA = "analysis_data"
    CODE = "code"
    GENERATED_TABLE = "generated_table"
    GENERATED_FIGURE = "generated_figure"
    OTHER_OUTPUT = "other_output"


@dataclass(frozen=True)
class ProvenanceArtifact:
    artifact_id: str
    role: ProvenanceArtifactRole
    sha256: str
    uri: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_id, str) or not self.artifact_id.strip():
            raise ValueError("provenance artifact_id is required")
        if not isinstance(self.role, ProvenanceArtifactRole):
            raise TypeError("provenance artifact role must be a ProvenanceArtifactRole")
        if not isinstance(self.sha256, str) or not _SHA256_RE.fullmatch(self.sha256):
            raise ValueError("provenance artifact sha256 must be lowercase hex")
        if self.uri is not None and not isinstance(self.uri, str):
            raise TypeError("provenance artifact uri must be a string or null")


@dataclass(frozen=True)
class ProvenanceTransform:
    transform_id: str
    code_artifact_id: str
    input_artifact_ids: tuple[str, ...]
    output_artifact_ids: tuple[str, ...]
    environment_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.transform_id, str) or not self.transform_id.strip():
            raise ValueError("provenance transform_id is required")
        if not isinstance(self.code_artifact_id, str) or not self.code_artifact_id.strip():
            raise ValueError("provenance code_artifact_id is required")
        if not self.input_artifact_ids or not self.output_artifact_ids:
            raise ValueError("provenance transforms require at least one input and one output")
        if len(set(self.input_artifact_ids)) != len(self.input_artifact_ids):
            raise ValueError("provenance transform input ids must be unique")
        if len(set(self.output_artifact_ids)) != len(self.output_artifact_ids):
            raise ValueError("provenance transform output ids must be unique")
        if not _SHA256_RE.fullmatch(self.environment_sha256):
            raise ValueError("environment_sha256 must be lowercase hex")


@dataclass
class ReproductionProvenanceGraph:
    artifacts: dict[str, ProvenanceArtifact] = field(default_factory=dict)
    transforms: dict[str, ProvenanceTransform] = field(default_factory=dict)

    def add_artifact(self, artifact: ProvenanceArtifact) -> None:
        if artifact.artifact_id in self.artifacts:
            raise ValueError(f"duplicate provenance artifact id: {artifact.artifact_id!r}")
        self.artifacts[artifact.artifact_id] = artifact

    def add_transform(self, transform: ProvenanceTransform) -> None:
        if transform.transform_id in self.transforms:
            raise ValueError(f"duplicate provenance transform id: {transform.transform_id!r}")
        known = set(self.artifacts)
        referenced = (
            {transform.code_artifact_id}
            | set(transform.input_artifact_ids)
            | set(transform.output_artifact_ids)
        )
        missing = sorted(referenced - known)
        if missing:
            raise ValueError(f"provenance transform references unknown artifacts: {missing!r}")
        if self.artifacts[transform.code_artifact_id].role is not ProvenanceArtifactRole.CODE:
            raise ValueError("provenance transform code_artifact_id must reference a code artifact")
        if transform.code_artifact_id in transform.output_artifact_ids:
            raise ValueError("code artifact cannot also be a transform output")
        self.transforms[transform.transform_id] = transform
        try:
            self.validate()
        except Exception:
            del self.transforms[transform.transform_id]
            raise

    def validate(self) -> None:
        producer: dict[str, str] = {}
        adjacency: dict[str, set[str]] = {artifact_id: set() for artifact_id in self.artifacts}
        for transform in self.transforms.values():
            for output_id in transform.output_artifact_ids:
                if output_id in producer:
                    raise ValueError(
                        f"provenance artifact {output_id!r} has multiple producing transforms"
                    )
                producer[output_id] = transform.transform_id
            dependencies = set(transform.input_artifact_ids) | {transform.code_artifact_id}
            for source_id in dependencies:
                adjacency[source_id].update(transform.output_artifact_ids)
        _require_acyclic(adjacency)

    def ancestors(self, artifact_id: str) -> tuple[str, ...]:
        if artifact_id not in self.artifacts:
            raise ValueError(f"unknown provenance artifact id: {artifact_id!r}")
        reverse: dict[str, set[str]] = {key: set() for key in self.artifacts}
        for transform in self.transforms.values():
            dependencies = set(transform.input_artifact_ids) | {transform.code_artifact_id}
            for output_id in transform.output_artifact_ids:
                reverse[output_id].update(dependencies)
        seen: set[str] = set()
        stack = list(reverse[artifact_id])
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(reverse[current])
        return tuple(sorted(seen))

    def validate_reproducible_output(self, artifact_id: str) -> None:
        artifact = self.artifacts.get(artifact_id)
        if artifact is None:
            raise ValueError(f"unknown provenance artifact id: {artifact_id!r}")
        if artifact.role not in {
            ProvenanceArtifactRole.GENERATED_TABLE,
            ProvenanceArtifactRole.GENERATED_FIGURE,
            ProvenanceArtifactRole.OTHER_OUTPUT,
        }:
            raise ValueError("reproducible output validation requires a generated output artifact")
        ancestors = {self.artifacts[item].role for item in self.ancestors(artifact_id)}
        if ProvenanceArtifactRole.CODE not in ancestors:
            raise ValueError("generated output has no code ancestor")
        if not ancestors & {ProvenanceArtifactRole.RAW_DATA, ProvenanceArtifactRole.ANALYSIS_DATA}:
            raise ValueError("generated output has no data ancestor")

    def sha256(self) -> str:
        self.validate()
        payload = {
            "artifacts": {
                key: {
                    **asdict(value),
                    "role": value.role.value,
                }
                for key, value in sorted(self.artifacts.items())
            },
            "transforms": {
                key: asdict(value)
                for key, value in sorted(self.transforms.items())
            },
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


def _require_acyclic(adjacency: dict[str, set[str]]) -> None:
    state: dict[str, int] = {node: 0 for node in adjacency}

    def visit(node: str) -> None:
        if state[node] == 1:
            raise ValueError("provenance graph must be acyclic")
        if state[node] == 2:
            return
        state[node] = 1
        for child in adjacency[node]:
            visit(child)
        state[node] = 2

    for node in adjacency:
        visit(node)
