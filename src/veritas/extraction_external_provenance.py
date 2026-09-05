from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from hashlib import sha256

from .extraction_execution_evidence import (
    AttestedExtractionEvidenceReleaseReceipt,
    ExtractionExecutionPlan,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_HEX_32_BYTES_RE = re.compile(r"^[0-9a-f]{64}$")
_ED25519_SIGNATURE_RE = re.compile(r"^[0-9a-f]{128}$")


@dataclass(frozen=True)
class ExtractionExternalTrustRoot:
    issuer: str
    runner_identity: str
    repository: str
    workflow_identity: str
    public_key_hex: str
    algorithm: str = "ed25519"
    schema_version: int = 1

    def __post_init__(self) -> None:
        for label, value in (
            ("issuer", self.issuer),
            ("runner_identity", self.runner_identity),
            ("repository", self.repository),
            ("workflow_identity", self.workflow_identity),
        ):
            _require_nonempty_string(value, label=label)
        if not isinstance(self.public_key_hex, str) or not _HEX_32_BYTES_RE.fullmatch(
            self.public_key_hex
        ):
            raise ValueError("external trust root public_key_hex must be 32 lowercase hex bytes")
        if self.algorithm != "ed25519":
            raise ValueError("external trust root algorithm must be ed25519")
        _require_schema_version(self.schema_version, label="external trust root")

    @property
    def key_id(self) -> str:
        return sha256(bytes.fromhex(self.public_key_hex)).hexdigest()

    def sha256(self) -> str:
        return _stable_sha256(asdict(self))


@dataclass(frozen=True)
class ExtractionExternalProvenanceStatement:
    trust_root_sha256: str
    issuer: str
    runner_identity: str
    repository: str
    workflow_identity: str
    run_id: str
    run_attempt: int
    commit_sha: str
    attested_release_receipt_sha256: str
    execution_plan_sha256: str
    development_execution_set_sha256: str
    test_execution_set_sha256: str
    input_artifact_manifest_sha256: str
    source_tree_sha256: str
    parser_registry_sha256: str
    numerical_runtime_sha256: str
    execution_command_sha256: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        for label, value in (
            ("trust_root_sha256", self.trust_root_sha256),
            ("attested_release_receipt_sha256", self.attested_release_receipt_sha256),
            ("execution_plan_sha256", self.execution_plan_sha256),
            ("development_execution_set_sha256", self.development_execution_set_sha256),
            ("test_execution_set_sha256", self.test_execution_set_sha256),
            ("input_artifact_manifest_sha256", self.input_artifact_manifest_sha256),
            ("source_tree_sha256", self.source_tree_sha256),
            ("parser_registry_sha256", self.parser_registry_sha256),
            ("numerical_runtime_sha256", self.numerical_runtime_sha256),
            ("execution_command_sha256", self.execution_command_sha256),
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
        if isinstance(self.run_attempt, bool) or not isinstance(self.run_attempt, int):
            raise TypeError("run_attempt must be an integer")
        if self.run_attempt < 1:
            raise ValueError("run_attempt must be positive")
        if not isinstance(self.commit_sha, str) or not _GIT_SHA_RE.fullmatch(self.commit_sha):
            raise ValueError("commit_sha must be a lowercase 40-character git SHA")
        _require_schema_version(self.schema_version, label="external provenance statement")

    def sha256(self) -> str:
        return sha256(extraction_external_provenance_statement_bytes(self)).hexdigest()


@dataclass(frozen=True)
class ExtractionSignedExternalProvenance:
    statement: ExtractionExternalProvenanceStatement
    signature_hex: str
    algorithm: str = "ed25519"
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.statement, ExtractionExternalProvenanceStatement):
            raise TypeError("statement must be an ExtractionExternalProvenanceStatement")
        if not isinstance(self.signature_hex, str) or not _ED25519_SIGNATURE_RE.fullmatch(
            self.signature_hex
        ):
            raise ValueError("signature_hex must be a 64-byte lowercase Ed25519 signature")
        if self.algorithm != "ed25519":
            raise ValueError("signed external provenance algorithm must be ed25519")
        _require_schema_version(self.schema_version, label="signed external provenance")

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
class ExternallyVerifiedExtractionEvidenceReceipt:
    attested_release_receipt_sha256: str
    execution_plan_sha256: str
    trust_root_sha256: str
    provenance_statement_sha256: str
    provenance_envelope_sha256: str
    production_authorized: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        for label, value in (
            ("attested_release_receipt_sha256", self.attested_release_receipt_sha256),
            ("execution_plan_sha256", self.execution_plan_sha256),
            ("trust_root_sha256", self.trust_root_sha256),
            ("provenance_statement_sha256", self.provenance_statement_sha256),
            ("provenance_envelope_sha256", self.provenance_envelope_sha256),
        ):
            _require_sha256(value, label=label)
        if type(self.production_authorized) is not bool or self.production_authorized:
            raise ValueError("externally verified extraction receipts are non-production only")
        _require_schema_version(
            self.schema_version,
            label="externally verified extraction evidence receipt",
        )

    def sha256(self) -> str:
        return _stable_sha256(asdict(self))


def build_extraction_external_provenance_statement(
    *,
    trust_root: ExtractionExternalTrustRoot,
    run_id: str,
    run_attempt: int,
    commit_sha: str,
    attested_release_receipt: AttestedExtractionEvidenceReleaseReceipt,
    execution_plan: ExtractionExecutionPlan,
) -> ExtractionExternalProvenanceStatement:
    if not isinstance(trust_root, ExtractionExternalTrustRoot):
        raise TypeError("trust_root must be an ExtractionExternalTrustRoot")
    if not isinstance(attested_release_receipt, AttestedExtractionEvidenceReleaseReceipt):
        raise TypeError(
            "attested_release_receipt must be an AttestedExtractionEvidenceReleaseReceipt"
        )
    if not isinstance(execution_plan, ExtractionExecutionPlan):
        raise TypeError("execution_plan must be an ExtractionExecutionPlan")
    if attested_release_receipt.execution_plan_sha256 != execution_plan.sha256():
        raise ValueError("attested release receipt is bound to a different execution plan")

    return ExtractionExternalProvenanceStatement(
        trust_root_sha256=trust_root.sha256(),
        issuer=trust_root.issuer,
        runner_identity=trust_root.runner_identity,
        repository=trust_root.repository,
        workflow_identity=trust_root.workflow_identity,
        run_id=run_id,
        run_attempt=run_attempt,
        commit_sha=commit_sha,
        attested_release_receipt_sha256=attested_release_receipt.sha256(),
        execution_plan_sha256=execution_plan.sha256(),
        development_execution_set_sha256=(
            attested_release_receipt.development_execution_set_sha256
        ),
        test_execution_set_sha256=attested_release_receipt.test_execution_set_sha256,
        input_artifact_manifest_sha256=execution_plan.input_artifact_manifest_sha256,
        source_tree_sha256=execution_plan.source_tree_sha256,
        parser_registry_sha256=execution_plan.parser_registry_sha256,
        numerical_runtime_sha256=execution_plan.numerical_runtime_sha256,
        execution_command_sha256=execution_plan.execution_command_sha256,
    )


def extraction_external_provenance_statement_bytes(
    statement: ExtractionExternalProvenanceStatement,
) -> bytes:
    if not isinstance(statement, ExtractionExternalProvenanceStatement):
        raise TypeError("statement must be an ExtractionExternalProvenanceStatement")
    return json.dumps(
        asdict(statement),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def verify_external_extraction_provenance(
    *,
    trust_root: ExtractionExternalTrustRoot,
    signed_provenance: ExtractionSignedExternalProvenance,
    attested_release_receipt: AttestedExtractionEvidenceReleaseReceipt,
    execution_plan: ExtractionExecutionPlan,
) -> ExternallyVerifiedExtractionEvidenceReceipt:
    if not isinstance(trust_root, ExtractionExternalTrustRoot):
        raise TypeError("trust_root must be an ExtractionExternalTrustRoot")
    if not isinstance(signed_provenance, ExtractionSignedExternalProvenance):
        raise TypeError("signed_provenance must be an ExtractionSignedExternalProvenance")
    if not isinstance(attested_release_receipt, AttestedExtractionEvidenceReleaseReceipt):
        raise TypeError(
            "attested_release_receipt must be an AttestedExtractionEvidenceReleaseReceipt"
        )
    if not isinstance(execution_plan, ExtractionExecutionPlan):
        raise TypeError("execution_plan must be an ExtractionExecutionPlan")

    statement = signed_provenance.statement
    expected_statement = build_extraction_external_provenance_statement(
        trust_root=trust_root,
        run_id=statement.run_id,
        run_attempt=statement.run_attempt,
        commit_sha=statement.commit_sha,
        attested_release_receipt=attested_release_receipt,
        execution_plan=execution_plan,
    )
    if statement != expected_statement:
        raise ValueError(
            "signed external provenance subject or trusted runner identity does not match"
        )
    _verify_ed25519_signature(
        public_key_hex=trust_root.public_key_hex,
        signature_hex=signed_provenance.signature_hex,
        message=extraction_external_provenance_statement_bytes(statement),
    )
    return ExternallyVerifiedExtractionEvidenceReceipt(
        attested_release_receipt_sha256=attested_release_receipt.sha256(),
        execution_plan_sha256=execution_plan.sha256(),
        trust_root_sha256=trust_root.sha256(),
        provenance_statement_sha256=statement.sha256(),
        provenance_envelope_sha256=signed_provenance.sha256(),
    )


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
        raise ValueError("external extraction provenance signature is invalid") from exc


def _require_nonempty_string(value: object, *, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")


def _require_sha256(value: object, *, label: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")


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
