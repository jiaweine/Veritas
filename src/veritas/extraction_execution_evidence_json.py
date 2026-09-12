from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from ._strict_json import load_strict_json_object, require_exact_object_keys
from .benchmark import BenchmarkSplit
from .extraction_execution_evidence import (
    AttestedExtractionEvidenceReleaseReceipt,
    ExtractionExecutionAttestation,
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
_EXECUTION_ATTESTATION_KEYS = frozenset(
    {
        "schema_version",
        "execution_id",
        "execution_plan_sha256",
        "split",
        "threshold_id",
        "threshold",
        "target_manifest_sha256",
        "prediction_artifact_sha256",
        "prediction_semantics_sha256",
        "exit_code",
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
    payload = load_strict_json_object(path, label="extraction execution plan")
    require_exact_object_keys(
        payload,
        _EXECUTION_PLAN_KEYS,
        label="extraction execution plan",
    )
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


def load_extraction_execution_attestation(
    path: str | Path,
) -> ExtractionExecutionAttestation:
    payload = load_strict_json_object(path, label="extraction execution attestation")
    require_exact_object_keys(
        payload,
        _EXECUTION_ATTESTATION_KEYS,
        label="extraction execution attestation",
    )
    split_value = payload["split"]
    if not isinstance(split_value, str):
        raise TypeError("extraction execution attestation split must be a string")
    try:
        split = BenchmarkSplit(split_value)
    except ValueError as exc:
        raise ValueError("extraction execution attestation split is unsupported") from exc
    return ExtractionExecutionAttestation(
        execution_id=payload["execution_id"],
        execution_plan_sha256=payload["execution_plan_sha256"],
        split=split,
        threshold_id=payload["threshold_id"],
        threshold=payload["threshold"],
        target_manifest_sha256=payload["target_manifest_sha256"],
        prediction_artifact_sha256=payload["prediction_artifact_sha256"],
        prediction_semantics_sha256=payload["prediction_semantics_sha256"],
        exit_code=payload["exit_code"],
        network_disabled=payload["network_disabled"],
        source_mount_read_only=payload["source_mount_read_only"],
        credentials_mounted=payload["credentials_mounted"],
        production_authorized=payload["production_authorized"],
        schema_version=payload["schema_version"],
    )


def load_attested_extraction_evidence_release_receipt(
    path: str | Path,
) -> AttestedExtractionEvidenceReleaseReceipt:
    payload = load_strict_json_object(
        path,
        label="attested extraction evidence release receipt",
    )
    require_exact_object_keys(
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


def extraction_execution_attestation_json_payload(
    attestation: ExtractionExecutionAttestation,
) -> dict[str, object]:
    if not isinstance(attestation, ExtractionExecutionAttestation):
        raise TypeError("attestation must be an ExtractionExecutionAttestation")
    payload = asdict(attestation)
    payload["split"] = attestation.split.value
    return payload


def attested_extraction_evidence_release_receipt_json_payload(
    receipt: AttestedExtractionEvidenceReleaseReceipt,
) -> dict[str, object]:
    if not isinstance(receipt, AttestedExtractionEvidenceReleaseReceipt):
        raise TypeError("receipt must be an AttestedExtractionEvidenceReleaseReceipt")
    return asdict(receipt)
