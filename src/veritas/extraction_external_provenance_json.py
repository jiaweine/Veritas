from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from ._strict_json import load_strict_json_object, require_exact_object_keys
from .extraction_external_provenance import (
    ExtractionExternalProvenanceStatement,
    ExtractionExternalTrustRoot,
    ExtractionSignedExternalProvenance,
)

_TRUST_ROOT_KEYS = frozenset(
    {
        "schema_version",
        "issuer",
        "runner_identity",
        "repository",
        "workflow_identity",
        "public_key_hex",
        "algorithm",
    }
)
_SIGNED_PROVENANCE_KEYS = frozenset(
    {
        "schema_version",
        "algorithm",
        "statement",
        "signature_hex",
    }
)
_STATEMENT_KEYS = frozenset(
    {
        "schema_version",
        "trust_root_sha256",
        "issuer",
        "runner_identity",
        "repository",
        "workflow_identity",
        "run_id",
        "run_attempt",
        "commit_sha",
        "attested_release_receipt_sha256",
        "execution_plan_sha256",
        "development_execution_set_sha256",
        "test_execution_set_sha256",
        "input_artifact_manifest_sha256",
        "source_tree_sha256",
        "parser_registry_sha256",
        "numerical_runtime_sha256",
        "execution_command_sha256",
    }
)


def load_extraction_external_trust_root(path: str | Path) -> ExtractionExternalTrustRoot:
    payload = load_strict_json_object(path, label="external trust-root manifest")
    require_exact_object_keys(payload, _TRUST_ROOT_KEYS, label="external trust-root manifest")
    return ExtractionExternalTrustRoot(
        issuer=payload["issuer"],
        runner_identity=payload["runner_identity"],
        repository=payload["repository"],
        workflow_identity=payload["workflow_identity"],
        public_key_hex=payload["public_key_hex"],
        algorithm=payload["algorithm"],
        schema_version=payload["schema_version"],
    )


def load_extraction_signed_external_provenance(
    path: str | Path,
) -> ExtractionSignedExternalProvenance:
    payload = load_strict_json_object(path, label="signed external provenance")
    require_exact_object_keys(
        payload,
        _SIGNED_PROVENANCE_KEYS,
        label="signed external provenance",
    )
    statement_payload = payload["statement"]
    require_exact_object_keys(
        statement_payload,
        _STATEMENT_KEYS,
        label="external provenance statement",
    )
    statement = ExtractionExternalProvenanceStatement(
        trust_root_sha256=statement_payload["trust_root_sha256"],
        issuer=statement_payload["issuer"],
        runner_identity=statement_payload["runner_identity"],
        repository=statement_payload["repository"],
        workflow_identity=statement_payload["workflow_identity"],
        run_id=statement_payload["run_id"],
        run_attempt=statement_payload["run_attempt"],
        commit_sha=statement_payload["commit_sha"],
        attested_release_receipt_sha256=(
            statement_payload["attested_release_receipt_sha256"]
        ),
        execution_plan_sha256=statement_payload["execution_plan_sha256"],
        development_execution_set_sha256=(
            statement_payload["development_execution_set_sha256"]
        ),
        test_execution_set_sha256=statement_payload["test_execution_set_sha256"],
        input_artifact_manifest_sha256=(
            statement_payload["input_artifact_manifest_sha256"]
        ),
        source_tree_sha256=statement_payload["source_tree_sha256"],
        parser_registry_sha256=statement_payload["parser_registry_sha256"],
        numerical_runtime_sha256=statement_payload["numerical_runtime_sha256"],
        execution_command_sha256=statement_payload["execution_command_sha256"],
        schema_version=statement_payload["schema_version"],
    )
    return ExtractionSignedExternalProvenance(
        statement=statement,
        signature_hex=payload["signature_hex"],
        algorithm=payload["algorithm"],
        schema_version=payload["schema_version"],
    )


def extraction_external_trust_root_payload(
    trust_root: ExtractionExternalTrustRoot,
) -> dict[str, Any]:
    if not isinstance(trust_root, ExtractionExternalTrustRoot):
        raise TypeError("trust_root must be an ExtractionExternalTrustRoot")
    return asdict(trust_root)


def extraction_signed_external_provenance_payload(
    signed_provenance: ExtractionSignedExternalProvenance,
) -> dict[str, Any]:
    if not isinstance(signed_provenance, ExtractionSignedExternalProvenance):
        raise TypeError("signed_provenance must be an ExtractionSignedExternalProvenance")
    return {
        "schema_version": signed_provenance.schema_version,
        "algorithm": signed_provenance.algorithm,
        "statement": asdict(signed_provenance.statement),
        "signature_hex": signed_provenance.signature_hex,
    }
