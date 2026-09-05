from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .extraction_external_trust_policy import (
    ExtractionExternalTrustPolicy,
    extraction_external_trust_policy_payload,
)

_POLICY_KEYS = frozenset(
    {
        "schema_version",
        "policy_id",
        "evidence_plan_sha256",
        "trust_root_sha256",
        "issuer",
        "runner_identity",
        "repository",
        "workflow_identity",
        "production_authorized",
    }
)


def load_extraction_external_trust_policy(path: str | Path) -> ExtractionExternalTrustPolicy:
    source_path = Path(path)
    raw = source_path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("external trust policy must be UTF-8 JSON") from exc
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_object_keys,
            parse_constant=_reject_json_constant,
        )
    except json.JSONDecodeError as exc:
        raise ValueError("external trust policy must contain valid JSON") from exc
    if not isinstance(payload, dict):
        raise TypeError("external trust policy root must be an object")
    actual = frozenset(payload)
    if actual != _POLICY_KEYS:
        missing = tuple(sorted(_POLICY_KEYS - actual))
        unknown = tuple(sorted(actual - _POLICY_KEYS))
        raise ValueError(
            "external trust policy keys differ from schema; "
            f"missing={missing!r}, unknown={unknown!r}"
        )
    return ExtractionExternalTrustPolicy(
        policy_id=payload["policy_id"],
        evidence_plan_sha256=payload["evidence_plan_sha256"],
        trust_root_sha256=payload["trust_root_sha256"],
        issuer=payload["issuer"],
        runner_identity=payload["runner_identity"],
        repository=payload["repository"],
        workflow_identity=payload["workflow_identity"],
        production_authorized=payload["production_authorized"],
        schema_version=payload["schema_version"],
    )


def extraction_external_trust_policy_json_payload(
    policy: ExtractionExternalTrustPolicy,
) -> dict[str, object]:
    return extraction_external_trust_policy_payload(policy)


def _reject_duplicate_object_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate object key is not allowed: {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON numeric constant is not allowed: {value}")
