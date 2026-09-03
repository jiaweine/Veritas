from __future__ import annotations

from collections.abc import Mapping
from typing import Any

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
        "reviewer_a_complete",
        "reviewer_b_complete",
        "adjudication_complete",
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
        "reviewer_a_complete",
        "reviewer_b_complete",
        "adjudication_complete",
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


def _validate_binding(binding_value: object) -> None:
    binding = _require_mapping(binding_value, label="reproduced_value_binding")
    format_name = binding.get("format")
    if format_name == "csv":
        _require_keys(
            binding,
            label="csv reproduced_value_binding",
            required=frozenset({"format", "row_match", "value_column"}),
        )
        return
    if format_name == "text_regex":
        _require_keys(
            binding,
            label="text_regex reproduced_value_binding",
            required=frozenset({"format", "pattern"}),
        )
        return
    if format_name == "json_path":
        _require_keys(
            binding,
            label="json_path reproduced_value_binding",
            required=frozenset({"format", "path"}),
        )
        return
    raise ValueError(f"unsupported reproduced-value binding format: {format_name!r}")


def _validate_packet_envelope(packet: Mapping[str, Any]) -> None:
    if "schema_version" in packet and packet["schema_version"] != 1:
        raise ValueError("unsupported reproduction packet schema_version")
    _require_nonempty_string(packet.get("case_id"), label="packet case_id")

    package = _require_mapping(packet.get("replication_package"), label="replication_package")
    _require_nonempty_string(package.get("git_commit_sha"), label="replication package git_commit_sha")

    tracks = _require_mapping(packet.get("execution_tracks"), label="execution_tracks")
    author_track = _require_mapping(tracks.get("author_package"), label="author_package execution track")
    _require_nonempty_string(author_track.get("base_image"), label="author_package base_image")
    _require_nonempty_string(
        author_track.get("environment_lock_sha256"),
        label="author_package environment_lock_sha256",
    )
    frozen = _require_mapping(author_track.get("frozen_rerun"), label="author_package frozen_rerun")
    for field in (
        "source_manifest_sha256",
        "environment_freeze_sha256",
        "output_artifact_sha256",
    ):
        _require_nonempty_string(frozen.get(field), label=f"frozen_rerun {field}")


def validate_single_target_ingest_contract(
    packet: Mapping[str, Any],
    execution: Mapping[str, Any],
) -> None:
    """Fail closed on unknown result-binding or execution-attestation fields."""

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
    _validate_binding(contract["reproduced_value_binding"])

    execution = _require_mapping(execution, label="execution attestation")
    _require_keys(
        execution,
        label="single-target execution attestation",
        required=_COMMON_EXECUTION_KEYS | frozenset({"target_id"}),
        optional=frozenset({"reproduced_value"}),
    )


def validate_target_set_ingest_contract(
    packet: Mapping[str, Any],
    execution: Mapping[str, Any],
) -> None:
    """Fail closed on unknown target-set or execution-attestation fields."""

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
    if contract.get("reproduced_values_format") != "strict_target_json_v1":
        raise ValueError("target-set reproduced_values_format must be strict_target_json_v1")
    rows = contract.get("targets")
    if not isinstance(rows, list) or not rows:
        raise ValueError("target_set_contract targets must be a non-empty array")
    for index, row_value in enumerate(rows):
        row = _require_mapping(row_value, label=f"target_set_contract target row {index}")
        _require_keys(
            row,
            label=f"target_set_contract target row {index}",
            required=_TARGET_SET_ROW_REQUIRED,
            optional=_TARGET_SET_ROW_OPTIONAL,
        )

    execution = _require_mapping(execution, label="execution attestation")
    if any(field in execution for field in ("target_id", "reproduced_value", "reproduced_values")):
        raise ValueError("target-set execution must not duplicate target identity or numeric output fields")
    _require_keys(
        execution,
        label="target-set execution attestation",
        required=_COMMON_EXECUTION_KEYS | frozenset({"target_ids"}),
    )
