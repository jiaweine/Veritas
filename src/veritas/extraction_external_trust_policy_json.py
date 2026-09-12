from __future__ import annotations

from pathlib import Path

from ._strict_json import load_strict_json_object, require_exact_object_keys
from .extraction_external_trust_policy import (
    ExtractionExternalTrustPolicy,
    extraction_external_trust_policy_payload,
)

_POLICY_KEYS = frozenset(
    {
        "schema_version",
        "policy_id",
        "evidence_plan_sha256",
        "execution_plan_sha256",
        "source_commit_sha",
        "trust_root_sha256",
        "issuer",
        "runner_identity",
        "repository",
        "workflow_identity",
        "production_authorized",
    }
)


def load_extraction_external_trust_policy(path: str | Path) -> ExtractionExternalTrustPolicy:
    payload = load_strict_json_object(path, label="external trust policy")
    require_exact_object_keys(payload, _POLICY_KEYS, label="external trust policy")
    return ExtractionExternalTrustPolicy(
        policy_id=payload["policy_id"],
        evidence_plan_sha256=payload["evidence_plan_sha256"],
        execution_plan_sha256=payload["execution_plan_sha256"],
        source_commit_sha=payload["source_commit_sha"],
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
