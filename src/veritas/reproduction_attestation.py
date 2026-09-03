from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .reproduction import (
    CellComparisonStatus,
    CodeAgentProposal,
    CodeAgentTask,
    ExecutionAttestation,
    MethodFidelityAttestation,
    ReproducedCell,
    ReproductionAuthority,
    ReproductionEvidenceBinding,
    ReproductionMode,
    ReproductionReport,
    ReproductionRootCause,
    ReproductionTarget,
    SandboxPolicy,
    _build_reproduction_report,
    compare_reproduced_cells,
    validate_frozen_execution,
    validate_target_commitment,
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
        if not isinstance(self.verifier_id, str) or not self.verifier_id.strip():
            raise ValueError("artifact verifier identity is required")
        if not isinstance(self.verifier_version, str) or not self.verifier_version.strip():
            raise ValueError("artifact verifier identity is required")
        if type(self.independent) is not bool:
            raise TypeError("artifact verifier independent must be a boolean")
        for name, value in (
            ("task_sha256", self.task_sha256),
            *(("expected_artifact_sha256", value) for value in self.expected_artifact_sha256),
            *(("verified_artifact_sha256", value) for value in self.verified_artifact_sha256),
        ):
            if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
                raise ValueError(f"{name} must contain lowercase SHA-256 hex digests")


def _require_runtime_bool(value: object, *, label: str) -> None:
    if type(value) is not bool:
        raise TypeError(f"{label} must be a boolean")


def _require_runtime_positive_int(value: object, *, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value <= 0:
        raise ValueError(f"{label} must be positive")


def _require_runtime_int(value: object, *, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")


def _validate_e4_runtime_types(
    proposal: CodeAgentProposal,
    sandbox_policy: SandboxPolicy,
    execution: ExecutionAttestation,
    method_fidelity: MethodFidelityAttestation,
    artifact_identity: ArtifactIdentityAttestation,
) -> None:
    """Reject Python truthiness/int-subclass ambiguities at the E4 authority boundary."""

    _require_runtime_positive_int(proposal.attempts, label="agent proposal attempts")
    _require_runtime_bool(sandbox_policy.network_disabled, label="sandbox network_disabled")
    _require_runtime_bool(sandbox_policy.read_only_inputs, label="sandbox read_only_inputs")
    for field in ("max_wall_seconds", "max_memory_mb", "max_cpus"):
        _require_runtime_positive_int(getattr(sandbox_policy, field), label=f"sandbox {field}")

    _require_runtime_int(execution.exit_code, label="execution exit_code")
    _require_runtime_bool(execution.network_disabled, label="execution network_disabled")
    _require_runtime_bool(execution.read_only_inputs, label="execution read_only_inputs")
    _require_runtime_bool(method_fidelity.independent, label="method verifier independent")
    _require_runtime_bool(artifact_identity.independent, label="artifact verifier independent")


def _validate_actor_separation(
    proposal: CodeAgentProposal,
    execution: ExecutionAttestation,
    method_fidelity: MethodFidelityAttestation,
    artifact_identity: ArtifactIdentityAttestation,
) -> None:
    for label, actor_id in (
        ("executor", execution.executor_id),
        ("method verifier", method_fidelity.verifier_id),
        ("artifact verifier", artifact_identity.verifier_id),
    ):
        if actor_id == proposal.agent_id:
            raise ValueError(f"{label} must be independent of the code agent identity")


def validate_method_fidelity(
    task: CodeAgentTask,
    proposal: CodeAgentProposal,
    attestation: MethodFidelityAttestation,
) -> None:
    if attestation.independent is not True:
        raise ValueError("method fidelity must be verified independently of the code agent")
    if attestation.verifier_id == proposal.agent_id:
        raise ValueError("method verifier must be independent of the code agent identity")
    if attestation.method_spec_sha256 != task.method_spec.sha256():
        raise ValueError("method-fidelity attestation is bound to a different MethodSpecification")
    if attestation.implementation_sha256 != proposal.generated_code_sha256:
        raise ValueError("method-fidelity verifier inspected a different implementation")
    if attestation.mismatched_fields:
        raise ValueError(f"method implementation mismatches required choices: {attestation.mismatched_fields!r}")
    if attestation.unresolved_fields:
        raise ValueError(f"method implementation has unresolved choices: {attestation.unresolved_fields!r}")

    must_verify = {field.name for field in task.method_spec.fields if field.value is not None}
    verified = set(attestation.verified_fields)
    missing = tuple(sorted(must_verify - verified))
    if missing:
        raise ValueError(f"method-fidelity attestation did not verify required fields: {missing!r}")


def validate_artifact_identity(
    task: CodeAgentTask,
    attestation: ArtifactIdentityAttestation,
) -> None:
    if attestation.independent is not True:
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


def validate_comparison_evidence(
    task: CodeAgentTask,
    targets: tuple[ReproductionTarget, ...],
    comparisons,
    execution: ExecutionAttestation,
):
    """Recompute canonical comparisons from values bound to attested execution output hashes."""

    validate_target_commitment(task, targets)
    supplied = tuple(comparisons)
    comparison_ids = tuple(item.target_id for item in supplied)
    if comparison_ids != task.target_ids:
        raise ValueError("comparison target identities do not match the locked reproduction task")

    allowed_outputs = set(execution.output_artifact_sha256)
    reproduced: list[ReproducedCell] = []
    for comparison in supplied:
        if comparison.status is CellComparisonStatus.MISSING:
            if any(
                value is not None
                for value in (
                    comparison.reproduced_value,
                    comparison.reported_interval,
                    comparison.output_artifact_sha256,
                )
            ):
                raise ValueError("missing comparison must not carry numeric or output evidence")
            continue

        value = comparison.reproduced_value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("reproduced comparison value must be one finite numeric value")
        if not math.isfinite(float(value)):
            raise ValueError("reproduced comparison value must be finite")
        output_sha256 = comparison.output_artifact_sha256
        if output_sha256 is None:
            raise ValueError("reproduced comparison is missing its output artifact identity")
        if output_sha256 not in allowed_outputs:
            raise ValueError("reproduced comparison was not produced by the attested execution")
        reproduced.append(ReproducedCell(comparison.target_id, float(value), output_sha256))

    canonical = compare_reproduced_cells(targets, tuple(reproduced))
    if supplied != canonical:
        raise ValueError(
            "supplied comparison evidence does not equal the canonical Veritas comparison"
        )
    return canonical


def build_attested_reproduction_report(
    comparisons,
    *,
    task: CodeAgentTask,
    targets: tuple[ReproductionTarget, ...],
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
    _validate_e4_runtime_types(
        proposal,
        sandbox_policy,
        execution,
        method_fidelity,
        artifact_identity,
    )
    _validate_actor_separation(proposal, execution, method_fidelity, artifact_identity)
    validate_frozen_execution(task, proposal, sandbox_policy, execution)
    validate_method_fidelity(task, proposal, method_fidelity)
    validate_artifact_identity(task, artifact_identity)
    canonical_comparisons = validate_comparison_evidence(task, targets, comparisons, execution)
    evidence_binding = ReproductionEvidenceBinding(
        task_sha256=task.sha256(),
        method_spec_sha256=task.method_spec.sha256(),
        target_commitment_sha256=task.reference_commitment_sha256,
        code_sha256=execution.code_sha256,
        frozen_workspace_sha256=execution.frozen_workspace_sha256,
        environment_sha256=execution.environment_sha256,
        sandbox_policy_sha256=execution.sandbox_policy_sha256,
        input_artifact_sha256=execution.input_artifact_sha256,
        output_artifact_sha256=execution.output_artifact_sha256,
    )
    return _build_reproduction_report(
        canonical_comparisons,
        authority=authority,
        method_fidelity_verified=True,
        artifact_identity_verified=True,
        execution_attested=True,
        root_cause=root_cause,
        allow_e4=True,
        evidence_binding=evidence_binding,
    )
