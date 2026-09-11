from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from hashlib import sha256

from .extraction_execution_evidence import ExtractionExecutionPlan
from .extraction_external_provenance import ExtractionExternalTrustRoot

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_ED25519_SIGNATURE_RE = re.compile(r"^[0-9a-f]{128}$")


@dataclass(frozen=True)
class ExtractionSourceArchiveTrustPolicy:
    policy_id: str
    execution_plan_sha256: str
    source_commit_sha: str
    source_tree_sha256: str
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
        for label, value in (
            ("execution_plan_sha256", self.execution_plan_sha256),
            ("source_tree_sha256", self.source_tree_sha256),
            ("trust_root_sha256", self.trust_root_sha256),
        ):
            _require_sha256(value, label=label)
        _require_git_sha(self.source_commit_sha, label="source_commit_sha")
        if type(self.production_authorized) is not bool or self.production_authorized:
            raise ValueError("source archive trust policies are non-production only")
        _require_schema_version(self.schema_version, label="source archive trust policy")

    def sha256(self) -> str:
        return _stable_sha256(asdict(self))


@dataclass(frozen=True)
class ExtractionSourceArchiveProvenanceStatement:
    trust_root_sha256: str
    issuer: str
    runner_identity: str
    repository: str
    workflow_identity: str
    run_id: str
    run_attempt: int
    source_commit_sha: str
    execution_plan_sha256: str
    source_tree_sha256: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        for label, value in (
            ("trust_root_sha256", self.trust_root_sha256),
            ("execution_plan_sha256", self.execution_plan_sha256),
            ("source_tree_sha256", self.source_tree_sha256),
        ):
            _require_sha256(value, label=label)
        for label, value in (
            ("issuer", self.issuer),
            ("runner_identity", self.runner_identity),
            ("repository", self.repository),
            ("workflow_identity", self.workflow_identity),
            ("run_id", self.run_id),
        ):
            _require_nonempty_string(value, label=label)
        _require_run_attempt(self.run_attempt)
        _require_git_sha(self.source_commit_sha, label="source_commit_sha")
        _require_schema_version(self.schema_version, label="source archive provenance statement")

    def sha256(self) -> str:
        return sha256(extraction_source_archive_provenance_statement_bytes(self)).hexdigest()


@dataclass(frozen=True)
class ExtractionSignedSourceArchiveProvenance:
    statement: ExtractionSourceArchiveProvenanceStatement
    signature_hex: str
    algorithm: str = "ed25519"
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.statement, ExtractionSourceArchiveProvenanceStatement):
            raise TypeError("statement must be an ExtractionSourceArchiveProvenanceStatement")
        if not isinstance(self.signature_hex, str) or not _ED25519_SIGNATURE_RE.fullmatch(
            self.signature_hex
        ):
            raise ValueError("signature_hex must be a 64-byte lowercase Ed25519 signature")
        if self.algorithm != "ed25519":
            raise ValueError("signed source archive provenance algorithm must be ed25519")
        _require_schema_version(self.schema_version, label="signed source archive provenance")

    def sha256(self) -> str:
        return _stable_sha256(
            {
                "schema_version": self.schema_version,
                "algorithm": self.algorithm,
                "statement": asdict(self.statement),
                "signature_hex": self.signature_hex,
            }
        )


@dataclass(frozen=True)
class PrecommittedExtractionSourceArchiveReceipt:
    trust_policy_sha256: str
    trust_root_sha256: str
    execution_plan_sha256: str
    source_commit_sha: str
    source_tree_sha256: str
    provenance_statement_sha256: str
    provenance_envelope_sha256: str
    run_id: str
    run_attempt: int
    production_authorized: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        for label, value in (
            ("trust_policy_sha256", self.trust_policy_sha256),
            ("trust_root_sha256", self.trust_root_sha256),
            ("execution_plan_sha256", self.execution_plan_sha256),
            ("source_tree_sha256", self.source_tree_sha256),
            ("provenance_statement_sha256", self.provenance_statement_sha256),
            ("provenance_envelope_sha256", self.provenance_envelope_sha256),
        ):
            _require_sha256(value, label=label)
        _require_git_sha(self.source_commit_sha, label="source_commit_sha")
        _require_nonempty_string(self.run_id, label="run_id")
        _require_run_attempt(self.run_attempt)
        if type(self.production_authorized) is not bool or self.production_authorized:
            raise ValueError("source archive provenance receipts are non-production only")
        _require_schema_version(self.schema_version, label="source archive provenance receipt")

    def sha256(self) -> str:
        return _stable_sha256(asdict(self))


def build_extraction_source_archive_trust_policy(
    *,
    policy_id: str,
    execution_plan: ExtractionExecutionPlan,
    source_commit_sha: str,
    trust_root: ExtractionExternalTrustRoot,
) -> ExtractionSourceArchiveTrustPolicy:
    if not isinstance(execution_plan, ExtractionExecutionPlan):
        raise TypeError("execution_plan must be an ExtractionExecutionPlan")
    if not isinstance(trust_root, ExtractionExternalTrustRoot):
        raise TypeError("trust_root must be an ExtractionExternalTrustRoot")
    _require_git_sha(source_commit_sha, label="source_commit_sha")
    return ExtractionSourceArchiveTrustPolicy(
        policy_id=policy_id,
        execution_plan_sha256=execution_plan.sha256(),
        source_commit_sha=source_commit_sha,
        source_tree_sha256=execution_plan.source_tree_sha256,
        trust_root_sha256=trust_root.sha256(),
        issuer=trust_root.issuer,
        runner_identity=trust_root.runner_identity,
        repository=trust_root.repository,
        workflow_identity=trust_root.workflow_identity,
    )


def build_extraction_source_archive_provenance_statement(
    *,
    trust_root: ExtractionExternalTrustRoot,
    run_id: str,
    run_attempt: int,
    source_commit_sha: str,
    execution_plan: ExtractionExecutionPlan,
) -> ExtractionSourceArchiveProvenanceStatement:
    if not isinstance(trust_root, ExtractionExternalTrustRoot):
        raise TypeError("trust_root must be an ExtractionExternalTrustRoot")
    if not isinstance(execution_plan, ExtractionExecutionPlan):
        raise TypeError("execution_plan must be an ExtractionExecutionPlan")
    return ExtractionSourceArchiveProvenanceStatement(
        trust_root_sha256=trust_root.sha256(),
        issuer=trust_root.issuer,
        runner_identity=trust_root.runner_identity,
        repository=trust_root.repository,
        workflow_identity=trust_root.workflow_identity,
        run_id=run_id,
        run_attempt=run_attempt,
        source_commit_sha=source_commit_sha,
        execution_plan_sha256=execution_plan.sha256(),
        source_tree_sha256=execution_plan.source_tree_sha256,
    )


def extraction_source_archive_provenance_statement_bytes(
    statement: ExtractionSourceArchiveProvenanceStatement,
) -> bytes:
    if not isinstance(statement, ExtractionSourceArchiveProvenanceStatement):
        raise TypeError("statement must be an ExtractionSourceArchiveProvenanceStatement")
    return json.dumps(
        asdict(statement),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def verify_precommitted_extraction_source_archive_provenance_for_run(
    *,
    trust_policy: ExtractionSourceArchiveTrustPolicy,
    trust_root: ExtractionExternalTrustRoot,
    signed_provenance: ExtractionSignedSourceArchiveProvenance,
    execution_plan: ExtractionExecutionPlan,
    expected_run_id: str,
    expected_run_attempt: int,
    expected_commit_sha: str,
) -> PrecommittedExtractionSourceArchiveReceipt:
    if not isinstance(trust_policy, ExtractionSourceArchiveTrustPolicy):
        raise TypeError("trust_policy must be an ExtractionSourceArchiveTrustPolicy")
    if not isinstance(trust_root, ExtractionExternalTrustRoot):
        raise TypeError("trust_root must be an ExtractionExternalTrustRoot")
    if not isinstance(signed_provenance, ExtractionSignedSourceArchiveProvenance):
        raise TypeError("signed_provenance must be an ExtractionSignedSourceArchiveProvenance")
    if not isinstance(execution_plan, ExtractionExecutionPlan):
        raise TypeError("execution_plan must be an ExtractionExecutionPlan")
    _require_nonempty_string(expected_run_id, label="expected_run_id")
    _require_run_attempt(expected_run_attempt)
    _require_git_sha(expected_commit_sha, label="expected_commit_sha")

    if trust_policy.execution_plan_sha256 != execution_plan.sha256():
        raise ValueError("source archive trust policy is bound to a different execution plan")
    if trust_policy.source_tree_sha256 != execution_plan.source_tree_sha256:
        raise ValueError("source archive trust policy is bound to a different source tree")
    if trust_policy.source_commit_sha != expected_commit_sha:
        raise ValueError("source archive trust policy is bound to a different source commit")
    if trust_policy.trust_root_sha256 != trust_root.sha256():
        raise ValueError("source archive trust policy is bound to a different trust root")
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
        raise ValueError("source archive trust policy runner identity differs from trust root")

    statement = signed_provenance.statement
    if statement.run_id != expected_run_id:
        raise ValueError("signed source archive provenance run_id differs from expected build run")
    if statement.run_attempt != expected_run_attempt:
        raise ValueError("signed source archive provenance run_attempt differs from expected build run")
    if statement.source_commit_sha != expected_commit_sha:
        raise ValueError("signed source archive provenance uses a different source commit")
    expected_statement = build_extraction_source_archive_provenance_statement(
        trust_root=trust_root,
        run_id=expected_run_id,
        run_attempt=expected_run_attempt,
        source_commit_sha=expected_commit_sha,
        execution_plan=execution_plan,
    )
    if statement != expected_statement:
        raise ValueError("signed source archive provenance subject or builder identity does not match")
    _verify_ed25519_signature(
        public_key_hex=trust_root.public_key_hex,
        signature_hex=signed_provenance.signature_hex,
        message=extraction_source_archive_provenance_statement_bytes(statement),
    )
    return PrecommittedExtractionSourceArchiveReceipt(
        trust_policy_sha256=trust_policy.sha256(),
        trust_root_sha256=trust_root.sha256(),
        execution_plan_sha256=execution_plan.sha256(),
        source_commit_sha=expected_commit_sha,
        source_tree_sha256=execution_plan.source_tree_sha256,
        provenance_statement_sha256=statement.sha256(),
        provenance_envelope_sha256=signed_provenance.sha256(),
        run_id=expected_run_id,
        run_attempt=expected_run_attempt,
    )


def extraction_source_archive_trust_policy_payload(
    policy: ExtractionSourceArchiveTrustPolicy,
) -> dict[str, object]:
    if not isinstance(policy, ExtractionSourceArchiveTrustPolicy):
        raise TypeError("policy must be an ExtractionSourceArchiveTrustPolicy")
    return asdict(policy)


def extraction_signed_source_archive_provenance_payload(
    signed_provenance: ExtractionSignedSourceArchiveProvenance,
) -> dict[str, object]:
    if not isinstance(signed_provenance, ExtractionSignedSourceArchiveProvenance):
        raise TypeError("signed_provenance must be an ExtractionSignedSourceArchiveProvenance")
    return {
        "schema_version": signed_provenance.schema_version,
        "algorithm": signed_provenance.algorithm,
        "statement": asdict(signed_provenance.statement),
        "signature_hex": signed_provenance.signature_hex,
    }


def _verify_ed25519_signature(*, public_key_hex: str, signature_hex: str, message: bytes) -> None:
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as exc:  # pragma: no cover - exercised only without the optional extra
        raise RuntimeError(
            "Ed25519 provenance verification requires veritas-audit[attestation]"
        ) from exc

    public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
    try:
        public_key.verify(bytes.fromhex(signature_hex), message)
    except InvalidSignature as exc:
        raise ValueError("source archive provenance signature is invalid") from exc


def _require_nonempty_string(value: object, *, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")


def _require_sha256(value: object, *, label: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")


def _require_git_sha(value: object, *, label: str) -> None:
    if not isinstance(value, str) or not _GIT_SHA_RE.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase 40-character git SHA")


def _require_run_attempt(value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("run_attempt must be an integer")
    if value < 1:
        raise ValueError("run_attempt must be positive")


def _require_schema_version(value: object, *, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value != 1:
        raise ValueError(f"{label} schema_version must be 1")


def _stable_sha256(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(raw).hexdigest()
