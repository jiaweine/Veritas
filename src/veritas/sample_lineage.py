from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from enum import Enum

from .models import SourceLocation

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class LineageOperationKind(str, Enum):
    EXCLUSION = "exclusion"
    FILTER = "filter"
    TRANSFORMATION = "transformation"
    MERGE = "merge"
    DERIVATION = "derivation"


@dataclass(frozen=True)
class SampleSnapshot:
    snapshot_id: str
    artifact_sha256: str
    row_identity_sha256: str
    n_rows: int
    source: SourceLocation

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot_id, str) or not self.snapshot_id.strip():
            raise ValueError("sample snapshot_id is required")
        for label, value in (
            ("artifact_sha256", self.artifact_sha256),
            ("row_identity_sha256", self.row_identity_sha256),
        ):
            if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
                raise ValueError(f"sample {label} must be lowercase SHA-256 hex")
        if isinstance(self.n_rows, bool) or not isinstance(self.n_rows, int):
            raise TypeError("sample n_rows must be an integer")
        if self.n_rows < 0:
            raise ValueError("sample n_rows must be non-negative")


@dataclass(frozen=True)
class LineageOperation:
    operation_id: str
    kind: LineageOperationKind
    input_snapshot_ids: tuple[str, ...]
    output_snapshot_id: str
    description: str
    evidence_sha256: str
    source: SourceLocation
    declared_plan_item_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.operation_id, str) or not self.operation_id.strip():
            raise ValueError("lineage operation_id is required")
        if not isinstance(self.kind, LineageOperationKind):
            raise TypeError("lineage operation kind must be a LineageOperationKind")
        if not self.input_snapshot_ids:
            raise ValueError("lineage operation requires at least one input snapshot")
        if len(set(self.input_snapshot_ids)) != len(self.input_snapshot_ids):
            raise ValueError("lineage operation input snapshot ids must be unique")
        if not isinstance(self.output_snapshot_id, str) or not self.output_snapshot_id.strip():
            raise ValueError("lineage output_snapshot_id is required")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("lineage operation description is required")
        if not _SHA256_RE.fullmatch(self.evidence_sha256):
            raise ValueError("lineage evidence_sha256 must be lowercase hex")
        if self.declared_plan_item_id is not None and (
            not isinstance(self.declared_plan_item_id, str) or not self.declared_plan_item_id.strip()
        ):
            raise ValueError("declared_plan_item_id must be a non-empty string or null")


@dataclass(frozen=True)
class UndocumentedLineageOperation:
    operation_id: str
    kind: LineageOperationKind
    reason: str
    source: SourceLocation
    evidence_sha256: str


@dataclass
class SampleLineage:
    snapshots: dict[str, SampleSnapshot] = field(default_factory=dict)
    operations: dict[str, LineageOperation] = field(default_factory=dict)

    def add_snapshot(self, snapshot: SampleSnapshot) -> None:
        if snapshot.snapshot_id in self.snapshots:
            raise ValueError(f"duplicate sample snapshot id: {snapshot.snapshot_id!r}")
        self.snapshots[snapshot.snapshot_id] = snapshot

    def add_operation(self, operation: LineageOperation) -> None:
        if operation.operation_id in self.operations:
            raise ValueError(f"duplicate lineage operation id: {operation.operation_id!r}")
        referenced = set(operation.input_snapshot_ids) | {operation.output_snapshot_id}
        missing = sorted(referenced - set(self.snapshots))
        if missing:
            raise ValueError(f"lineage operation references unknown snapshots: {missing!r}")
        if operation.output_snapshot_id in operation.input_snapshot_ids:
            raise ValueError("lineage operation output cannot also be one of its inputs")
        if any(existing.output_snapshot_id == operation.output_snapshot_id for existing in self.operations.values()):
            raise ValueError("each sample snapshot may have at most one producing operation")
        self.operations[operation.operation_id] = operation
        self.validate()

    def validate(self) -> None:
        adjacency: dict[str, set[str]] = {snapshot_id: set() for snapshot_id in self.snapshots}
        for operation in self.operations.values():
            for input_id in operation.input_snapshot_ids:
                adjacency[input_id].add(operation.output_snapshot_id)
            self._validate_row_count_semantics(operation)
        _require_acyclic(adjacency)

    def trace_ancestors(self, snapshot_id: str) -> tuple[str, ...]:
        if snapshot_id not in self.snapshots:
            raise ValueError(f"unknown sample snapshot id: {snapshot_id!r}")
        reverse: dict[str, set[str]] = {key: set() for key in self.snapshots}
        for operation in self.operations.values():
            for input_id in operation.input_snapshot_ids:
                reverse[operation.output_snapshot_id].add(input_id)
        seen: set[str] = set()
        stack = list(reverse[snapshot_id])
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(reverse[current])
        return tuple(sorted(seen))

    def sha256(self) -> str:
        self.validate()
        payload = {
            "snapshots": {
                key: asdict(value) for key, value in sorted(self.snapshots.items())
            },
            "operations": {
                key: {
                    **asdict(value),
                    "kind": value.kind.value,
                }
                for key, value in sorted(self.operations.items())
            },
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def _validate_row_count_semantics(self, operation: LineageOperation) -> None:
        output = self.snapshots[operation.output_snapshot_id]
        inputs = tuple(self.snapshots[item] for item in operation.input_snapshot_ids)
        if operation.kind in {LineageOperationKind.EXCLUSION, LineageOperationKind.FILTER}:
            if len(inputs) != 1:
                raise ValueError("exclusion/filter lineage operations require exactly one input")
            if output.n_rows > inputs[0].n_rows:
                raise ValueError("exclusion/filter operation cannot increase sample row count")
        elif operation.kind in {LineageOperationKind.TRANSFORMATION, LineageOperationKind.DERIVATION}:
            if len(inputs) != 1:
                raise ValueError("transformation/derivation lineage operations require exactly one input")
            if output.n_rows != inputs[0].n_rows:
                raise ValueError("transformation/derivation operation must preserve sample row count")


def find_undocumented_lineage_operations(
    lineage: SampleLineage,
    *,
    registered_plan_item_ids: tuple[str, ...],
) -> tuple[UndocumentedLineageOperation, ...]:
    """Find only exclusion/filter/transformation operations lacking a verified plan link."""

    lineage.validate()
    registered = set(registered_plan_item_ids)
    if len(registered) != len(registered_plan_item_ids):
        raise ValueError("registered plan item ids must be unique")
    concerns: list[UndocumentedLineageOperation] = []
    for operation in lineage.operations.values():
        if operation.kind not in {
            LineageOperationKind.EXCLUSION,
            LineageOperationKind.FILTER,
            LineageOperationKind.TRANSFORMATION,
        }:
            continue
        declared = operation.declared_plan_item_id
        if declared is None:
            reason = "lineage operation has no linked registered exclusion/transformation"
        elif declared not in registered:
            reason = "lineage operation references an unknown registered plan item"
        else:
            continue
        concerns.append(
            UndocumentedLineageOperation(
                operation.operation_id,
                operation.kind,
                reason,
                operation.source,
                operation.evidence_sha256,
            )
        )
    return tuple(concerns)


def row_identity_sha256(row_ids: tuple[str, ...]) -> str:
    if len(row_ids) != len(set(row_ids)):
        raise ValueError("row identities must be unique")
    if any(not isinstance(value, str) or not value for value in row_ids):
        raise ValueError("row identities must be non-empty strings")
    raw = json.dumps(tuple(sorted(row_ids)), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _require_acyclic(adjacency: dict[str, set[str]]) -> None:
    state = {node: 0 for node in adjacency}

    def visit(node: str) -> None:
        if state[node] == 1:
            raise ValueError("sample lineage must be acyclic")
        if state[node] == 2:
            return
        state[node] = 1
        for child in adjacency[node]:
            visit(child)
        state[node] = 2

    for node in adjacency:
        visit(node)
