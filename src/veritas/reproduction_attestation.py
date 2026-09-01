from __future__ import annotations

import re
from dataclasses import dataclass

from .reproduction import (
    CodeAgentProposal,
    CodeAgentTask,
    ExecutionAttestation,
    MethodFidelityAttestation,
    ReproductionAuthority,
    ReproductionMode,
    ReproductionReport,
    ReproductionRootCause,
    SandboxPolicy,
    _build_reproduction_report,
    validate_frozen_execution,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ArtifactIdentityAttestation:
    """Independent verification that the task artifacts are the intended research artifacts."""

    verifier_id: str
    verifier_version: str
    task_sha256: str
    expected_artifact_sha256: tuple[str, ...]
    verified_artifact_sha256: tuple[str, ...]
    independent: bool = False

    def __post_init__(self) -> None:
        if not self.verifier_id.strip() or not self.verifier_version.strip():
            raise ValueError("artifact verifier identity is required")
        for name, value in (
            ("task_sha256", self.task_sha256),
            *(("expected_artifact_sha256", value) for value in self.expected_artifact_sha256),
            *(("verified_artifact_sha256", value) for value in self.verified_artifact_sha256),
        ):
            if not _SHA256_RE.fullmatch(value):
                raise ValueError(f"{name} must contain lowercase SHA-256 hex digests")


def validate_method_fidelity(
    task: CodeAgentTask,
    proposal: CodeAgentProposal,
    attestation: MethodFidelityAttestation,
) -> None:
    if not attestation.independent:
        raise ValueError("method fidelity must be verified independently of the code agent")
    if attestation.method_spec_sha256 != task.method_spec.sha256():
        raise ValueError("method-fidelity attestation is bound to a different MethodSpecification")
    if attestation.implementation_sha256 != proposal.generated_code_sha256:
        raise ValueError("method-fidelity verifier inspected a different implementation")
    if attestation.mismatched_fields:
        raise ValueError(f"method implementation mismatches required choices: {attestation.mismatched_fields!r}")
    if attestation.unresolved_fields:
        raise ValueError(f"method implementation has unresolved choices: {attestation.unresolved_fields!r}")

    required = {
        field.name for field in task.method_spec.fields if field.required_for_execution
    }
    verified = set(attestation.verified_fields)
    missing = tuple(sorted(required - verified))
    if missing:
        raise ValueError(f"method-fidelity attestation did not verify required fields: {missing!r}")


def validate_artifact_identity(
    task: CodeAgentTask,
    attestation: ArtifactIdentityAttestation,
) -> None:
    if not attestation.independent:
        raise ValueError("artifact identity must be verified independently")
    if attestation.task_sha256 != task.sha256():
        raise ValueError("artifact-identity attestation is bound to a different task")
    expected = tuple(sorted(artifact.sha256 for artifact in task.artifacts))
    if tuple(sorted(attestation.expected_artifact_sha256)) != expected:
        raise ValueError("artifact verifier expected a different input set than the locked task")
    if tuple(sorted(attestation.verified_artifact_sha256)) != expected:
        raise ValueError("one or more locked task artifacts were not independently verified")


def validate_reproduction_authority(
    task: CodeAgentTask,
    authority: ReproductionAuthority,
) -> None:
    """Bind hard reproduction authority to the execution mode that can justify it."""

    if authority is ReproductionAuthority.EXPERIMENTAL_AGENT:
        return
    if authority is ReproductionAuthority.AUTHOR_PACKAGE_RERUN:
        if task.mode is not ReproductionMode.AUTHOR_CODE:
            raise ValueError("author-package authority requires an author-code reproduction task")
        return
    if authority is ReproductionAuthority.INDEPENDENT_ADJUDICATED:
        if task.mode is not ReproductionMode.INDEPENDENT_REIMPLEMENTATION:
            raise ValueError(
                "independent-adjudicated authority requires an independent-reimplementation task"
            )
        return
    raise ValueError(f"unsupported reproduction authority: {authority!r}")


def build_attested_reproduction_report(
    comparisons,
    *,
    task: CodeAgentTask,
    proposal: CodeAgentProposal,
    sandbox_policy: SandboxPolicy,
    execution: ExecutionAttestation,
    method_fidelity: MethodFidelityAttestation,
    artifact_identity: ArtifactIdentityAttestation,
    authority: ReproductionAuthority,
    root_cause: ReproductionRootCause = ReproductionRootCause.UNKNOWN,
) -> ReproductionReport:
    """Only E4-capable construction path for a code-agent reproduction report."""

    validate_reproduction_authority(task, authority)
    validate_frozen_execution(task, proposal, sandbox_policy, execution)
    validate_method_fidelity(task, proposal, method_fidelity)
    validate_artifact_identity(task, artifact_identity)
    return _build_reproduction_report(
        comparisons,
        authority=authority,
        method_fidelity_verified=True,
        artifact_identity_verified=True,
        execution_attested=True,
        root_cause=root_cause,
        allow_e4=True,
    )
