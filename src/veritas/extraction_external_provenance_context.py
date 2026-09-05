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
    verify_external_extraction_provenance,
)

_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ExternallyVerifiedExtractionRunReceipt:
    verified_evidence_receipt_sha256: str
    trust_root_sha256: str
    issuer: str
    runner_identity: str
    repository: str
    workflow_identity: str
    run_id: str
    run_attempt: int
    commit_sha: str
    production_authorized: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        _require_sha256(
            self.verified_evidence_receipt_sha256,
            label="verified_evidence_receipt_sha256",
        )
        _require_sha256(self.trust_root_sha256, label="trust_root_sha256")
        for label, value in (
            ("issuer", self.issuer),
            ("runner_identity", self.runner_identity),
            ("repository", self.repository),
            ("workflow_identity", self.workflow_identity),
            ("run_id", self.run_id),
        ):
            _require_nonempty_string(value, label=label)
        _require_run_attempt(self.run_attempt)
        _require_git_sha(self.commit_sha)
        if type(self.production_authorized) is not bool or self.production_authorized:
            raise ValueError("externally verified extraction run receipts are non-production only")
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int):
            raise TypeError("externally verified extraction run receipt schema_version must be an integer")
        if self.schema_version != 1:
            raise ValueError("externally verified extraction run receipt schema_version must be 1")

    def sha256(self) -> str:
        raw = json.dumps(
            asdict(self),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return sha256(raw).hexdigest()


def verify_external_extraction_provenance_for_run(
    *,
    trust_root: ExtractionExternalTrustRoot,
    signed_provenance: ExtractionSignedExternalProvenance,
    attested_release_receipt: AttestedExtractionEvidenceReleaseReceipt,
    execution_plan: ExtractionExecutionPlan,
    expected_run_id: str,
    expected_run_attempt: int,
    expected_commit_sha: str,
) -> ExternallyVerifiedExtractionRunReceipt:
    _require_nonempty_string(expected_run_id, label="expected_run_id")
    _require_run_attempt(expected_run_attempt)
    _require_git_sha(expected_commit_sha)

    statement = signed_provenance.statement
    if statement.run_id != expected_run_id:
        raise ValueError("signed external provenance run_id differs from expected run")
    if statement.run_attempt != expected_run_attempt:
        raise ValueError("signed external provenance run_attempt differs from expected run")
    if statement.commit_sha != expected_commit_sha:
        raise ValueError("signed external provenance commit_sha differs from expected commit")

    verified = verify_external_extraction_provenance(
        trust_root=trust_root,
        signed_provenance=signed_provenance,
        attested_release_receipt=attested_release_receipt,
        execution_plan=execution_plan,
    )
    return ExternallyVerifiedExtractionRunReceipt(
        verified_evidence_receipt_sha256=verified.sha256(),
        trust_root_sha256=trust_root.sha256(),
        issuer=trust_root.issuer,
        runner_identity=trust_root.runner_identity,
        repository=trust_root.repository,
        workflow_identity=trust_root.workflow_identity,
        run_id=expected_run_id,
        run_attempt=expected_run_attempt,
        commit_sha=expected_commit_sha,
    )


def _require_nonempty_string(value: object, *, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")


def _require_run_attempt(value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("run attempt must be an integer")
    if value < 1:
        raise ValueError("run attempt must be positive")


def _require_git_sha(value: object) -> None:
    if not isinstance(value, str) or not _GIT_SHA_RE.fullmatch(value):
        raise ValueError("expected commit SHA must be a lowercase 40-character git SHA")


def _require_sha256(value: object, *, label: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
