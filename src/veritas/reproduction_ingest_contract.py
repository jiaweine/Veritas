from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

_COMMON_EXECUTION_KEYS = frozenset(
    {
        "case_id",
        "track",
        "external_git_commit_sha",
        "source_manifest_sha256",
        "environment_freeze_sha256",
        "environment_lock_sha256",
        "base_image",
        "output_artifact_sha256",
        "exit_code",
        "network_disabled",
        "source_mount_read_only",
        "runtime_precommitted",
        "credentials_mounted",
        "veritas_repository_mounted",
    }
)
_EXECUTION_BOOL_FIELDS = (
    "network_disabled",
    "source_mount_read_only",
    "runtime_precommitted",
    "credentials_mounted",
    "veritas_repository_mounted",
)
_REVIEW_BOOL_FIELDS = (
    "reviewer_a_complete",
    "reviewer_b_complete",
    "adjudication_complete",
)

_SINGLE_TARGET_CONTRACT_REQUIRED = frozenset(
    {
        "target_id",
        "claim_id",
        "metric",
        "target_commitment_sha256",
        "reproduced_value_binding",
    }
)
_SINGLE_TARGET_CONTRACT_OPTIONAL = frozenset(
    {
        "status",
        "source_descriptor",
        "reported_numeric_value_stored_in_repository",
        *_REVIEW_BOOL_FIELDS,
    }
)

_TARGET_SET_CONTRACT_REQUIRED = frozenset(
    {"target_commitment_sha256", "reproduced_values_format", "targets"}
)
_TARGET_SET_CONTRACT_OPTIONAL = frozenset(
    {"status", "reported_numeric_values_stored_in_repository"}
)
_TARGET_SET_ROW_REQUIRED = frozenset({"target_id", "claim_id", "metric"})
_TARGET_SET_ROW_OPTIONAL = frozenset(
    {
        "source_descriptor",
        *_REVIEW_BOOL_FIELDS,
    }
)


def _require_mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    return value


def _require_nonempty_string(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{label} must be a non-empty string")
    return value


def _require_bool(value: object, *, label: str) -> bool:
    if type(value) is not bool:
        raise TypeError(f"{label} must be a boolean")
    return value


def _require_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    return value


def _require_sha256(value: object, *, label: str) -> str:
    text = _require_nonempty_string(value, label=label)
    if not _SHA256_RE.fullmatch(text):
        raise ValueError(f"{label} must be a lowercase SHA-256 hex digest")
    return text


def _require_git_sha(value: object, *, label: str) -> str:
    text = _require_nonempty_string(value, label=label)
    if not _GIT_SHA_RE.fullmatch(text):
        raise ValueError(f"{label} must be a lowercase 40-character git commit SHA")
    return text


def _require_finite_number(value: object, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be a finite JSON number")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{label} must be finite")
    return numeric


def _require_keys(
    mapping: Mapping[str, Any],
    *,
    label: str,
    required: frozenset[str],
    optional: frozenset[str] = frozenset(),
) -> None:
    observed = set(mapping)
    missing = sorted(required - observed)
    if missing:
        raise ValueError(f"{label} is missing required fields: {missing!r}")
    unexpected = sorted(observed - required - optional)
    if unexpected:
        raise ValueError(f"{label} contains unexpected fields: {unexpected!r}")


def _validate_review_fields(mapping: Mapping[str, Any], *, label: str) -> None:
    for field in _REVIEW_BOOL_FIELDS:
        if field in mapping:
            _require_bool(mapping[field], label=f"{label} {field}")


def _validate_optional_metadata(mapping: Mapping[str, Any], *, label: str) -> None:
    for field in ("status", "source_descriptor"):
        if field in mapping:
            _require_nonempty_string(mapping[field], label=f"{label} {field}")
    for field in (
        "reported_numeric_value_stored_in_repository",
        "reported_numeric_values_stored_in_repository",
    ):
        if field in mapping:
            _require_bool(mapping[field], label=f"{label} {field}")


def _validate_binding(binding_value: object) -> None:
    binding = _require_mapping(binding_value, label="reproduced_value_binding")
    format_name = binding.get("format")
    if format_name == "csv":
        _require_keys(
            binding,
            label="csv reproduced_value_binding",
            required=frozenset({"format", "row_match", "value_column"}),
        )
        row_match = _require_mapping(binding["row_match"], label="csv row_match")
        if not row_match:
            raise ValueError("csv row_match must be non-empty")
        for key, expected in row_match.items():
            _require_nonempty_string(key, label="csv row_match key")
            if isinstance(expected, bool) or not isinstance(expected, (str, int, float)):
                raise TypeError("csv row_match values must be string or numeric scalars")
            if isinstance(expected, float) and not math.isfinite(expected):
                raise ValueError("csv row_match numeric values must be finite")
        _require_nonempty_string(binding["value_column"], label="csv value_column")
        return
    if format_name == "text_regex":
        _require_keys(
            binding,
            label="text_regex reproduced_value_binding",
            required=frozenset({"format", "pattern"}),
        )
        _require_nonempty_string(binding["pattern"], label="text_regex pattern")
        return
    if format_name == "json_path":
        _require_keys(
            binding,
            label="json_path reproduced_value_binding",
            required=frozenset({"format", "path"}),
        )
        path = binding["path"]
        if not isinstance(path, list) or not path:
            raise ValueError("json_path reproduced-value binding requires a non-empty path")
        if len(path) > 32:
            raise ValueError("json_path path is too deep")
        for component in path:
            if isinstance(component, bool) or not isinstance(component, (str, int)):
                raise TypeError("json_path components must be object keys or non-negative array indices")
            if isinstance(component, int) and component < 0:
                raise ValueError("json_path array indices must be non-negative")
        return
    raise ValueError(f"unsupported reproduced-value binding format: {format_name!r}")


def _validate_packet_envelope(packet: Mapping[str, Any]) -> None:
    if "schema_version" in packet:
        version = _require_int(packet["schema_version"], label="reproduction packet schema_version")
        if version != 1:
            raise ValueError("unsupported reproduction packet schema_version")
    _require_nonempty_string(packet.get("case_id"), label="packet case_id")

    package = _require_mapping(packet.get("replication_package"), label="replication_package")
    _require_git_sha(package.get("git_commit_sha"), label="replication package git_commit_sha")

    tracks = _require_mapping(packet.get("execution_tracks"), label="execution_tracks")
    author_track = _require_mapping(tracks.get("author_package"), label="author_package execution track")
    _require_nonempty_string(author_track.get("base_image"), label="author_package base_image")
    _require_sha256(
        author_track.get("environment_lock_sha256"),
        label="author_package environment_lock_sha256",
    )
    frozen = _require_mapping(author_track.get("frozen_rerun"), label="author_package frozen_rerun")
    for field in (
        "source_manifest_sha256",
        "environment_freeze_sha256",
        "output_artifact_sha256",
    ):
        _require_sha256(frozen.get(field), label=f"frozen_rerun {field}")


def _validate_execution_common(execution: Mapping[str, Any]) -> None:
    _require_nonempty_string(execution["case_id"], label="execution case_id")
    _require_nonempty_string(execution["track"], label="execution track")
    _require_git_sha(execution["external_git_commit_sha"], label="execution external_git_commit_sha")
    for field in (
        "source_manifest_sha256",
        "environment_freeze_sha256",
        "environment_lock_sha256",
        "output_artifact_sha256",
    ):
        _require_sha256(execution[field], label=f"execution {field}")
    _require_nonempty_string(execution["base_image"], label="execution base_image")
    _require_int(execution["exit_code"], label="execution exit_code")
    for field in _EXECUTION_BOOL_FIELDS:
        _require_bool(execution[field], label=f"execution {field}")


def _validate_target_identity(mapping: Mapping[str, Any], *, label: str) -> None:
    for field in ("target_id", "claim_id", "metric"):
        _require_nonempty_string(mapping[field], label=f"{label} {field}")


def validate_single_target_ingest_contract(
    packet: Mapping[str, Any],
    execution: Mapping[str, Any],
) -> None:
    """Fail closed on unknown or weakly typed result-binding/attestation fields."""

    _validate_packet_envelope(packet)
    if "target_set_contract" in packet:
        raise ValueError("single-target packet must not also contain target_set_contract")
    contract = _require_mapping(packet.get("target_contract"), label="target_contract")
    _require_keys(
        contract,
        label="target_contract",
        required=_SINGLE_TARGET_CONTRACT_REQUIRED,
        optional=_SINGLE_TARGET_CONTRACT_OPTIONAL,
    )
    _validate_target_identity(contract, label="target_contract")
    _require_sha256(
        contract["target_commitment_sha256"],
        label="target_contract target_commitment_sha256",
    )
    _validate_binding(contract["reproduced_value_binding"])
    _validate_review_fields(contract, label="target_contract")
    _validate_optional_metadata(contract, label="target_contract")

    execution = _require_mapping(execution, label="execution attestation")
    _require_keys(
        execution,
        label="single-target execution attestation",
        required=_COMMON_EXECUTION_KEYS | frozenset({"target_id"}),
        optional=frozenset({"reproduced_value"}),
    )
    _validate_execution_common(execution)
    _require_nonempty_string(execution["target_id"], label="execution target_id")
    if "reproduced_value" in execution:
        _require_finite_number(execution["reproduced_value"], label="execution reproduced_value")


def validate_target_set_ingest_contract(
    packet: Mapping[str, Any],
    execution: Mapping[str, Any],
) -> None:
    """Fail closed on unknown or weakly typed target-set/attestation fields."""

    _validate_packet_envelope(packet)
    if "target_contract" in packet:
        raise ValueError("target-set packet must not also contain target_contract")
    contract = _require_mapping(packet.get("target_set_contract"), label="target_set_contract")
    _require_keys(
        contract,
        label="target_set_contract",
        required=_TARGET_SET_CONTRACT_REQUIRED,
        optional=_TARGET_SET_CONTRACT_OPTIONAL,
    )
    _require_sha256(
        contract["target_commitment_sha256"],
        label="target_set_contract target_commitment_sha256",
    )
    if contract.get("reproduced_values_format") != "strict_target_json_v1":
        raise ValueError("target-set reproduced_values_format must be strict_target_json_v1")
    rows = contract.get("targets")
    if not isinstance(rows, list) or not rows:
        raise ValueError("target_set_contract targets must be a non-empty array")
    seen: set[str] = set()
    for index, row_value in enumerate(rows):
        row = _require_mapping(row_value, label=f"target_set_contract target row {index}")
        _require_keys(
            row,
            label=f"target_set_contract target row {index}",
            required=_TARGET_SET_ROW_REQUIRED,
            optional=_TARGET_SET_ROW_OPTIONAL,
        )
        _validate_target_identity(row, label=f"target_set_contract target row {index}")
        target_id = row["target_id"]
        if target_id in seen:
            raise ValueError(f"duplicate target_set_contract target_id: {target_id!r}")
        seen.add(target_id)
        _validate_review_fields(row, label=f"target_set_contract target row {index}")
        _validate_optional_metadata(row, label=f"target_set_contract target row {index}")
    _validate_optional_metadata(contract, label="target_set_contract")

    execution = _require_mapping(execution, label="execution attestation")
    if any(field in execution for field in ("target_id", "reproduced_value", "reproduced_values")):
        raise ValueError("target-set execution must not duplicate target identity or numeric output fields")
    _require_keys(
        execution,
        label="target-set execution attestation",
        required=_COMMON_EXECUTION_KEYS | frozenset({"target_ids"}),
    )
    _validate_execution_common(execution)
    target_ids = execution["target_ids"]
    if not isinstance(target_ids, list) or not target_ids:
        raise ValueError("target-set execution target_ids must be a non-empty array")
    normalized = tuple(
        _require_nonempty_string(value, label="target-set execution target_id")
        for value in target_ids
    )
    if len(set(normalized)) != len(normalized):
        raise ValueError("target-set execution target_ids must be unique")
