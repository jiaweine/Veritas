from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from hashlib import sha256

from .extraction_execution_evidence import (
    AttestedExtractionEvidenceReleaseReceipt,
    ExtractionExecutionPlan,
)
from .extraction_external_provenance import (
    ExtractionExternalTrustRoot,
    ExtractionSignedExternalProvenance,
)
from .extraction_external_provenance_context import (
    ExternallyVerifiedExtractionRunReceipt,
    verify_external_extraction_provenance_for_run,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ExtractionExternalTrustPolicy:
    policy_id: str
    evidence_plan_sha256: str
    trust_root_sha256: str
    issuer: str
    runner_identity: str
    repository: str
    workflow_identity: str
    production_authorized: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        for label, value in (
            ("policy_id", self.policy_id),
            ("issuer", self.issuer),
            ("runner_identity", self.runner_identity),
            ("repository", self.repository),
            ("workflow_identity", self.workflow_identity),
        ):
            _require_nonempty_string(value, label=label)
        _require_sha256(self.evidence_plan_sha256, label="evidence_plan_sha256")
        _require_sha256(self.trust_root_sha256, label="trust_root_sha256")
        if type(self.production_authorized) is not bool or self.production_authorized:
            raise ValueError("external extraction trust policies are non-production only")
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int):
            raise TypeError("external extraction trust policy schema_version must be an integer")
        if self.schema_version != 1:
            raise ValueError("external extraction trust policy schema_version must be 1")

    def sha256(self) -> str:
        return _stable_sha256(asdict(self))


@dataclass(frozen=True)
class PrecommittedExternalExtractionRunReceipt:
    trust_policy_sha256: str
    evidence_plan_sha256: str
    trust_root_sha256: str
    verified_run_receipt_sha256: str
    production_authorized: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        for label, value in (
            ("trust_policy_sha256", self.trust_policy_sha256),
            ("evidence_plan_sha256", self.evidence_plan_sha256),
            ("trust_root_sha256", self.trust_root_sha256),
            ("verified_run_receipt_sha256", self.verified_run_receipt_sha256),
        ):
            _require_sha256(value, label=label)
        if type(self.production_authorized) is not bool or self.production_authorized:
            raise ValueError("precommitted external extraction run receipts are non-production only")
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int):
            raise TypeError(
                "precommitted external extraction run receipt schema_version must be an integer"
            )
        if self.schema_version != 1:
            raise ValueError("precommitted external extraction run receipt schema_version must be 1")

    def sha256(self) -> str:
        return _stable_sha256(asdict(self))


def build_extraction_external_trust_policy(
    *,
    policy_id: str,
    evidence_plan_sha256: str,
    trust_root: ExtractionExternalTrustRoot,
) -> ExtractionExternalTrustPolicy:
    if not isinstance(trust_root, ExtractionExternalTrustRoot):
        raise TypeError("trust_root must be an ExtractionExternalTrustRoot")
    return ExtractionExternalTrustPolicy(
        policy_id=policy_id,
        evidence_plan_sha256=evidence_plan_sha256,
        trust_root_sha256=trust_root.sha256(),
        issuer=trust_root.issuer,
        runner_identity=trust_root.runner_identity,
        repository=trust_root.repository,
        workflow_identity=trust_root.workflow_identity,
    )


def verify_precommitted_external_extraction_provenance_for_run(
    *,
    trust_policy: ExtractionExternalTrustPolicy,
    evidence_plan_sha256: str,
    trust_root: ExtractionExternalTrustRoot,
    signed_provenance: ExtractionSignedExternalProvenance,
    attested_release_receipt: AttestedExtractionEvidenceReleaseReceipt,
    execution_plan: ExtractionExecutionPlan,
    expected_run_id: str,
    expected_run_attempt: int,
    expected_commit_sha: str,
) -> PrecommittedExternalExtractionRunReceipt:
    if not isinstance(trust_policy, ExtractionExternalTrustPolicy):
        raise TypeError("trust_policy must be an ExtractionExternalTrustPolicy")
    if not isinstance(trust_root, ExtractionExternalTrustRoot):
        raise TypeError("trust_root must be an ExtractionExternalTrustRoot")
    if not isinstance(attested_release_receipt, AttestedExtractionEvidenceReleaseReceipt):
        raise TypeError(
            "attested_release_receipt must be an AttestedExtractionEvidenceReleaseReceipt"
        )
    _require_sha256(evidence_plan_sha256, label="evidence_plan_sha256")

    if trust_policy.evidence_plan_sha256 != evidence_plan_sha256:
        raise ValueError("external trust policy is bound to a different evidence plan")
    if attested_release_receipt.evidence_plan_sha256 != evidence_plan_sha256:
        raise ValueError("signed attested release is bound to a different evidence plan")
    if trust_policy.trust_root_sha256 != trust_root.sha256():
        raise ValueError("external trust policy is bound to a different trust root")
    expected_identity = (
        trust_policy.issuer,
        trust_policy.runner_identity,
        trust_policy.repository,
        trust_policy.workflow_identity,
    )
    actual_identity = (
        trust_root.issuer,
        trust_root.runner_identity,
        trust_root.repository,
        trust_root.workflow_identity,
    )
    if expected_identity != actual_identity:
        raise ValueError("external trust policy runner identity differs from trust root")

    verified_run: ExternallyVerifiedExtractionRunReceipt = (
        verify_external_extraction_provenance_for_run(
            trust_root=trust_root,
            signed_provenance=signed_provenance,
            attested_release_receipt=attested_release_receipt,
            execution_plan=execution_plan,
            expected_run_id=expected_run_id,
            expected_run_attempt=expected_run_attempt,
            expected_commit_sha=expected_commit_sha,
        )
    )
    return PrecommittedExternalExtractionRunReceipt(
        trust_policy_sha256=trust_policy.sha256(),
        evidence_plan_sha256=evidence_plan_sha256,
        trust_root_sha256=trust_root.sha256(),
        verified_run_receipt_sha256=verified_run.sha256(),
    )


def extraction_external_trust_policy_payload(
    policy: ExtractionExternalTrustPolicy,
) -> dict[str, object]:
    if not isinstance(policy, ExtractionExternalTrustPolicy):
        raise TypeError("policy must be an ExtractionExternalTrustPolicy")
    return asdict(policy)


def _require_nonempty_string(value: object, *, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")


def _require_sha256(value: object, *, label: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")


def _stable_sha256(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(raw).hexdigest()