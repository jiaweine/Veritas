from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .extraction_source_archive_provenance import (
    ExtractionSignedSourceArchiveProvenance,
    ExtractionSourceArchiveProvenanceStatement,
    ExtractionSourceArchiveTrustPolicy,
    extraction_signed_source_archive_provenance_payload,
    extraction_source_archive_trust_policy_payload,
)

_POLICY_KEYS = frozenset(
    {
        "schema_version",
        "policy_id",
        "execution_plan_sha256",
        "source_commit_sha",
        "source_tree_sha256",
        "trust_root_sha256",
        "issuer",
        "runner_identity",
        "repository",
        "workflow_identity",
        "production_authorized",
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
        "source_commit_sha",
        "execution_plan_sha256",
        "source_tree_sha256",
    }
)


def load_extraction_source_archive_trust_policy(
    path: str | Path,
) -> ExtractionSourceArchiveTrustPolicy:
    payload = _load_strict_json_file(path, label="source archive trust policy")
    _require_exact_object_keys(payload, _POLICY_KEYS, label="source archive trust policy")
    return ExtractionSourceArchiveTrustPolicy(
        policy_id=payload["policy_id"],
        execution_plan_sha256=payload["execution_plan_sha256"],
        source_commit_sha=payload["source_commit_sha"],
        source_tree_sha256=payload["source_tree_sha256"],
        trust_root_sha256=payload["trust_root_sha256"],
        issuer=payload["issuer"],
        runner_identity=payload["runner_identity"],
        repository=payload["repository"],
        workflow_identity=payload["workflow_identity"],
        production_authorized=payload["production_authorized"],
        schema_version=payload["schema_version"],
    )


def load_extraction_signed_source_archive_provenance(
    path: str | Path,
) -> ExtractionSignedSourceArchiveProvenance:
    payload = _load_strict_json_file(path, label="signed source archive provenance")
    _require_exact_object_keys(
        payload,
        _SIGNED_PROVENANCE_KEYS,
        label="signed source archive provenance",
    )
    statement_payload = payload["statement"]
    _require_exact_object_keys(
        statement_payload,
        _STATEMENT_KEYS,
        label="source archive provenance statement",
    )
    statement = ExtractionSourceArchiveProvenanceStatement(
        trust_root_sha256=statement_payload["trust_root_sha256"],
        issuer=statement_payload["issuer"],
        runner_identity=statement_payload["runner_identity"],
        repository=statement_payload["repository"],
        workflow_identity=statement_payload["workflow_identity"],
        run_id=statement_payload["run_id"],
        run_attempt=statement_payload["run_attempt"],
        source_commit_sha=statement_payload["source_commit_sha"],
        execution_plan_sha256=statement_payload["execution_plan_sha256"],
        source_tree_sha256=statement_payload["source_tree_sha256"],
        schema_version=statement_payload["schema_version"],
    )
    return ExtractionSignedSourceArchiveProvenance(
        statement=statement,
        signature_hex=payload["signature_hex"],
        algorithm=payload["algorithm"],
        schema_version=payload["schema_version"],
    )


def extraction_source_archive_trust_policy_json_payload(
    policy: ExtractionSourceArchiveTrustPolicy,
) -> dict[str, object]:
    return extraction_source_archive_trust_policy_payload(policy)


def extraction_signed_source_archive_provenance_json_payload(
    signed_provenance: ExtractionSignedSourceArchiveProvenance,
) -> dict[str, object]:
    return extraction_signed_source_archive_provenance_payload(signed_provenance)


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
