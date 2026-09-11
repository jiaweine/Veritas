from __future__ import annotations

from dataclasses import replace

import pytest

from veritas.models import ReportedNumber, SourceLocation
from veritas.reproduction import (
    CellComparisonStatus,
    CodeAgentProposal,
    ExecutionAttestation,
    MethodFidelityAttestation,
    MethodField,
    MethodSpecification,
    ReproducedCell,
    ReproductionArtifact,
    ReproductionAuthority,
    ReproductionMode,
    ReproductionTarget,
    SandboxPolicy,
    build_code_agent_task,
    compare_reproduced_cells,
)
from veritas.reproduction_attestation import (
    ArtifactIdentityAttestation,
    build_attested_reproduction_report,
    validate_method_fidelity,
)
from veritas.types import Materiality


def _targets() -> tuple[ReproductionTarget, ...]:
    return (
        ReproductionTarget(
            "beta",
            "claim-main",
            "coefficient",
            ReportedNumber(0.10, decimals=2),
            SourceLocation(page=4, table="Table 2", row="Treatment", column="B"),
            Materiality.MAIN_EMPIRICAL_CLAIM,
        ),
    )


def _task(*, include_optional: bool = False):
    fields = [
        MethodField("outcome", "y"),
        MethodField("estimator", "ols"),
        MethodField("inference", "clustered"),
    ]
    if include_optional:
        fields.append(MethodField("weights", "sampling_weight", required_for_execution=False))
    targets = _targets()
    task = build_code_agent_task(
        task_id="authority-hardening",
        mode=ReproductionMode.INDEPENDENT_REIMPLEMENTATION,
        method_spec=MethodSpecification(
            spec_id="method",
            object_type="RegressionResult",
            fields=tuple(fields),
        ),
        artifacts=(ReproductionArtifact("data", "analysis_data", "a" * 64),),
        targets=targets,
    )
    return task, targets


def _proposal(task, *, agent_id: str = "agent", attempts: int = 1) -> CodeAgentProposal:
    return CodeAgentProposal(
        agent_id=agent_id,
        agent_version="1",
        task_sha256=task.sha256(),
        method_spec_sha256=task.method_spec.sha256(),
        visibility_policy_sha256=task.visibility_policy.sha256(),
        generated_code_sha256="b" * 64,
        attempts=attempts,
    )


def _execution(task, proposal, policy, *, executor_id: str = "executor", **overrides):
    values = {
        "executor_id": executor_id,
        "executor_version": "1",
        "task_sha256": task.sha256(),
        "code_sha256": proposal.generated_code_sha256,
        "frozen_workspace_sha256": "c" * 64,
        "environment_sha256": "d" * 64,
        "sandbox_policy_sha256": policy.sha256(),
        "input_artifact_sha256": tuple(artifact.sha256 for artifact in task.artifacts),
        "output_artifact_sha256": ("e" * 64,),
        "exit_code": 0,
        "network_disabled": True,
        "read_only_inputs": True,
    }
    values.update(overrides)
    return ExecutionAttestation(**values)


def _method_attestation(task, proposal, *, verifier_id: str = "method-verifier", fields=None, independent=True):
    if fields is None:
        fields = tuple(field.name for field in task.method_spec.fields)
    return MethodFidelityAttestation(
        verifier_id=verifier_id,
        verifier_version="1",
        method_spec_sha256=task.method_spec.sha256(),
        implementation_sha256=proposal.generated_code_sha256,
        verified_fields=tuple(fields),
        independent=independent,
    )


def _artifact_attestation(task, *, verifier_id: str = "artifact-verifier", independent=True):
    hashes = tuple(artifact.sha256 for artifact in task.artifacts)
    return ArtifactIdentityAttestation(
        verifier_id=verifier_id,
        verifier_version="1",
        task_sha256=task.sha256(),
        expected_artifact_sha256=hashes,
        verified_artifact_sha256=hashes,
        independent=independent,
    )


def _build(comparisons, task, targets, proposal, policy, execution, method=None, artifact=None):
    return build_attested_reproduction_report(
        comparisons,
        task=task,
        targets=targets,
        proposal=proposal,
        sandbox_policy=policy,
        execution=execution,
        method_fidelity=method or _method_attestation(task, proposal),
        artifact_identity=artifact or _artifact_attestation(task),
        authority=ReproductionAuthority.INDEPENDENT_ADJUDICATED,
    )


def test_e4_rejects_forged_mismatch_status_on_matching_value() -> None:
    task, targets = _task()
    proposal = _proposal(task)
    policy = SandboxPolicy()
    execution = _execution(task, proposal, policy)
    canonical = compare_reproduced_cells(
        targets,
        (ReproducedCell("beta", 0.101, "e" * 64),),
    )
    assert canonical[0].status is CellComparisonStatus.MATCH
    forged = (replace(canonical[0], status=CellComparisonStatus.MISMATCH),)

    with pytest.raises(ValueError, match="canonical Veritas comparison"):
        _build(forged, task, targets, proposal, policy, execution)


def test_e4_rejects_noncanonical_custom_tolerance_result() -> None:
    task, targets = _task()
    proposal = _proposal(task)
    policy = SandboxPolicy()
    execution = _execution(task, proposal, policy)
    permissive = compare_reproduced_cells(
        targets,
        (ReproducedCell("beta", 0.106, "e" * 64),),
        absolute_tolerance=0.01,
    )
    assert permissive[0].status is CellComparisonStatus.MATCH

    with pytest.raises(ValueError, match="canonical Veritas comparison"):
        _build(permissive, task, targets, proposal, policy, execution)


def test_e4_rejects_forged_reported_interval() -> None:
    task, targets = _task()
    proposal = _proposal(task)
    policy = SandboxPolicy()
    execution = _execution(task, proposal, policy)
    canonical = compare_reproduced_cells(
        targets,
        (ReproducedCell("beta", 0.40, "e" * 64),),
    )
    forged = (replace(canonical[0], reported_interval=(-99.0, 99.0)),)

    with pytest.raises(ValueError, match="canonical Veritas comparison"):
        _build(forged, task, targets, proposal, policy, execution)


def test_e4_rejects_missing_comparison_with_hidden_value_channel() -> None:
    task, targets = _task()
    proposal = _proposal(task)
    policy = SandboxPolicy()
    execution = _execution(task, proposal, policy)
    missing = compare_reproduced_cells(targets, ())
    forged = (replace(missing[0], reproduced_value=0.40),)

    with pytest.raises(ValueError, match="missing comparison must not carry"):
        _build(forged, task, targets, proposal, policy, execution)


def test_method_fidelity_must_cover_supplied_optional_fields() -> None:
    task, _ = _task(include_optional=True)
    proposal = _proposal(task)
    attestation = _method_attestation(
        task,
        proposal,
        fields=("outcome", "estimator", "inference"),
    )

    with pytest.raises(ValueError, match="did not verify required fields.*weights"):
        validate_method_fidelity(task, proposal, attestation)


@pytest.mark.parametrize("role", ["executor", "method", "artifact"])
def test_e4_rejects_code_agent_reused_as_independent_actor(role: str) -> None:
    task, targets = _task()
    proposal = _proposal(task)
    policy = SandboxPolicy()
    execution = _execution(
        task,
        proposal,
        policy,
        executor_id="agent" if role == "executor" else "executor",
    )
    method = _method_attestation(
        task,
        proposal,
        verifier_id="agent" if role == "method" else "method-verifier",
    )
    artifact = _artifact_attestation(
        task,
        verifier_id="agent" if role == "artifact" else "artifact-verifier",
    )
    comparisons = compare_reproduced_cells(
        targets,
        (ReproducedCell("beta", 0.40, "e" * 64),),
    )

    with pytest.raises(ValueError, match="independent of the code agent identity"):
        _build(comparisons, task, targets, proposal, policy, execution, method, artifact)


def test_e4_rejects_truthy_string_execution_boolean() -> None:
    task, targets = _task()
    proposal = _proposal(task)
    policy = SandboxPolicy()
    execution = _execution(task, proposal, policy, network_disabled="true")
    comparisons = compare_reproduced_cells(
        targets,
        (ReproducedCell("beta", 0.40, "e" * 64),),
    )

    with pytest.raises(TypeError, match="network_disabled.*boolean"):
        _build(comparisons, task, targets, proposal, policy, execution)


def test_e4_rejects_boolean_exit_code_and_attempt_count() -> None:
    task, targets = _task()
    policy = SandboxPolicy()
    proposal = _proposal(task, attempts=True)
    execution = _execution(task, proposal, policy, exit_code=False)
    comparisons = compare_reproduced_cells(
        targets,
        (ReproducedCell("beta", 0.40, "e" * 64),),
    )

    with pytest.raises(TypeError, match="attempts.*integer"):
        _build(comparisons, task, targets, proposal, policy, execution)


def test_e4_rejects_boolean_sandbox_resource_limit() -> None:
    task, targets = _task()
    proposal = _proposal(task)
    policy = SandboxPolicy(max_cpus=True)
    execution = _execution(task, proposal, policy)
    comparisons = compare_reproduced_cells(
        targets,
        (ReproducedCell("beta", 0.40, "e" * 64),),
    )

    with pytest.raises(TypeError, match="max_cpus.*integer"):
        _build(comparisons, task, targets, proposal, policy, execution)


def test_artifact_independence_flag_requires_real_boolean() -> None:
    task, _ = _task()
    with pytest.raises(TypeError, match="independent.*boolean"):
        _artifact_attestation(task, independent="false")
