from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .extraction_execution_evidence import (
    AttestedExtractionEvidenceReleaseReceipt,
    ExtractionExecutionPlan,
)

_EXECUTION_PLAN_KEYS = frozenset(
    {
        "schema_version",
        "input_artifact_manifest_sha256",
        "source_tree_sha256",
        "parser_registry_sha256",
        "numerical_runtime_sha256",
        "execution_command_sha256",
        "network_disabled",
        "source_mount_read_only",
        "credentials_mounted",
        "production_authorized",
    }
)
_ATTESTED_RELEASE_KEYS = frozenset(
    {
        "schema_version",
        "base_release_receipt_sha256",
        "evidence_plan_sha256",
        "execution_plan_sha256",
        "development_execution_set_sha256",
        "test_execution_set_sha256",
        "production_authorized",
    }
)


def load_extraction_execution_plan(path: str | Path) -> ExtractionExecutionPlan:
    payload = _load_strict_json_file(path, label="extraction execution plan")
    _require_exact_object_keys(payload, _EXECUTION_PLAN_KEYS, label="extraction execution plan")
    return ExtractionExecutionPlan(
        input_artifact_manifest_sha256=payload["input_artifact_manifest_sha256"],
        source_tree_sha256=payload["source_tree_sha256"],
        parser_registry_sha256=payload["parser_registry_sha256"],
        numerical_runtime_sha256=payload["numerical_runtime_sha256"],
        execution_command_sha256=payload["execution_command_sha256"],
        network_disabled=payload["network_disabled"],
        source_mount_read_only=payload["source_mount_read_only"],
        credentials_mounted=payload["credentials_mounted"],
        production_authorized=payload["production_authorized"],
        schema_version=payload["schema_version"],
    )


def load_attested_extraction_evidence_release_receipt(
    path: str | Path,
) -> AttestedExtractionEvidenceReleaseReceipt:
    payload = _load_strict_json_file(path, label="attested extraction evidence release receipt")
    _require_exact_object_keys(
        payload,
        _ATTESTED_RELEASE_KEYS,
        label="attested extraction evidence release receipt",
    )
    return AttestedExtractionEvidenceReleaseReceipt(
        base_release_receipt_sha256=payload["base_release_receipt_sha256"],
        evidence_plan_sha256=payload["evidence_plan_sha256"],
        execution_plan_sha256=payload["execution_plan_sha256"],
        development_execution_set_sha256=payload["development_execution_set_sha256"],
        test_execution_set_sha256=payload["test_execution_set_sha256"],
        production_authorized=payload["production_authorized"],
        schema_version=payload["schema_version"],
    )


def extraction_execution_plan_json_payload(
    plan: ExtractionExecutionPlan,
) -> dict[str, object]:
    if not isinstance(plan, ExtractionExecutionPlan):
        raise TypeError("plan must be an ExtractionExecutionPlan")
    return asdict(plan)


def attested_extraction_evidence_release_receipt_json_payload(
    receipt: AttestedExtractionEvidenceReleaseReceipt,
) -> dict[str, object]:
    if not isinstance(receipt, AttestedExtractionEvidenceReleaseReceipt):
        raise TypeError("receipt must be an AttestedExtractionEvidenceReleaseReceipt")
    return asdict(receipt)


def _load_strict_json_file(path: str | Path, *, label: str) -> dict[str, Any]:
    source_path = Path(path)
    raw = source_path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} must be UTF-8 JSON") from exc
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_object_keys,
            parse_constant=_reject_json_constant,
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must contain valid JSON") from exc
    if not isinstance(payload, dict):
        raise TypeError(f"{label} root must be an object")
    return payload


def _reject_duplicate_object_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate object key is not allowed: {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON numeric constant is not allowed: {value}")


def _require_exact_object_keys(
    value: object,
    expected: frozenset[str],
    *,
    label: str,
) -> None:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object")
    actual = frozenset(value)
    if actual != expected:
        missing = tuple(sorted(expected - actual))
        unknown = tuple(sorted(actual - expected))
        raise ValueError(
            f"{label} keys differ from schema; missing={missing!r}, unknown={unknown!r}"
        )
