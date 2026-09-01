from __future__ import annotations

import pytest

from veritas.models import ReportedNumber, SourceLocation
from veritas.reproduction import (
    CodeAgentProposal,
    ExecutionAttestation,
    MethodField,
    MethodFidelityAttestation,
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
from veritas.types import EvidenceGrade, Materiality


EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def _task():
    method = MethodSpecification(
        spec_id="main",
        object_type="RegressionResult",
        fields=(
            MethodField("outcome", "y"),
            MethodField("treatment", "x"),
            MethodField("estimator", "ols"),
            MethodField("inference", "clustered by village"),
        ),
    )
    targets = (
        ReproductionTarget(
            "claim-beta",
            "claim-main",
            "coefficient",
            ReportedNumber(0.10, decimals=2),
            SourceLocation(page=4, table="Table 2", row="Treatment", column="B"),
            Materiality.MAIN_EMPIRICAL_CLAIM,
        ),
    )
    task = build_code_agent_task(
        task_id="independent-main",
        mode=ReproductionMode.INDEPENDENT_REIMPLEMENTATION,
        method_spec=method,
        artifacts=(ReproductionArtifact("data", "analysis_data", "a" * 64),),
        targets=targets,
    )
    return task, targets


def _proposal(task) -> CodeAgentProposal:
    return CodeAgentProposal(
        agent_id="agent",
        agent_version="1",
        task_sha256=task.sha256(),
        method_spec_sha256=task.method_spec.sha256(),
        visibility_policy_sha256=task.visibility_policy.sha256(),
        generated_code_sha256="b" * 64,
        attempts=2,
    )


def _execution(task, proposal, policy) -> ExecutionAttestation:
    return ExecutionAttestation(
        executor_id="sandbox",
        executor_version="1",
        task_sha256=task.sha256(),
        code_sha256=proposal.generated_code_sha256,
        frozen_workspace_sha256="c" * 64,
        environment_sha256="d" * 64,
        sandbox_policy_sha256=policy.sha256(),
        input_artifact_sha256=tuple(artifact.sha256 for artifact in task.artifacts),
        output_artifact_sha256=("e" * 64,),
        exit_code=0,
        network_disabled=True,
        read_only_inputs=True,
    )


def test_method_fidelity_must_cover_every_required_method_field() -> None:
    task, _ = _task()
    proposal = _proposal(task)
    incomplete = MethodFidelityAttestation(
        verifier_id="verifier",
        verifier_version="1",
        method_spec_sha256=task.method_spec.sha256(),
        implementation_sha256=proposal.generated_code_sha256,
        verified_fields=("outcome", "treatment", "estimator"),
        independent=True,
    )

    with pytest.raises(ValueError, match="did not verify required fields"):
        validate_method_fidelity(task, proposal, incomplete)


def test_attested_builder_is_the_e4_capable_code_agent_path() -> None:
    task, targets = _task()
    proposal = _proposal(task)
    policy = SandboxPolicy()
    execution = _execution(task, proposal, policy)
    method_fidelity = MethodFidelityAttestation(
        verifier_id="verifier",
        verifier_version="1",
        method_spec_sha256=task.method_spec.sha256(),
        implementation_sha256=proposal.generated_code_sha256,
        verified_fields=tuple(field.name for field in task.method_spec.fields),
        independent=True,
    )
    artifact_identity = ArtifactIdentityAttestation(
        verifier_id="artifact-verifier",
        verifier_version="1",
        task_sha256=task.sha256(),
        expected_artifact_sha256=tuple(artifact.sha256 for artifact in task.artifacts),
        verified_artifact_sha256=tuple(artifact.sha256 for artifact in task.artifacts),
        independent=True,
    )
    comparisons = compare_reproduced_cells(
        targets,
        (ReproducedCell("claim-beta", 0.40, "e" * 64),),
    )

    report = build_attested_reproduction_report(
        comparisons,
        task=task,
        proposal=proposal,
        sandbox_policy=policy,
        execution=execution,
        method_fidelity=method_fidelity,
        artifact_identity=artifact_identity,
        authority=ReproductionAuthority.INDEPENDENT_ADJUDICATED,
    )
    assert report.max_evidence_grade is EvidenceGrade.REPRODUCTION_CONTRADICTION


def test_attested_builder_rejects_self_attested_method_fidelity() -> None:
    task, targets = _task()
    proposal = _proposal(task)
    policy = SandboxPolicy()
    execution = _execution(task, proposal, policy)
    method_fidelity = MethodFidelityAttestation(
        verifier_id="agent-itself",
        verifier_version="1",
        method_spec_sha256=task.method_spec.sha256(),
        implementation_sha256=proposal.generated_code_sha256,
        verified_fields=tuple(field.name for field in task.method_spec.fields),
        independent=False,
    )
    artifact_identity = ArtifactIdentityAttestation(
        verifier_id="artifact-verifier",
        verifier_version="1",
        task_sha256=task.sha256(),
        expected_artifact_sha256=tuple(artifact.sha256 for artifact in task.artifacts),
        verified_artifact_sha256=tuple(artifact.sha256 for artifact in task.artifacts),
        independent=True,
    )
    comparisons = compare_reproduced_cells(
        targets,
        (ReproducedCell("claim-beta", 0.40, "e" * 64),),
    )

    with pytest.raises(ValueError, match="verified independently"):
        build_attested_reproduction_report(
            comparisons,
            task=task,
            proposal=proposal,
            sandbox_policy=policy,
            execution=execution,
            method_fidelity=method_fidelity,
            artifact_identity=artifact_identity,
            authority=ReproductionAuthority.INDEPENDENT_ADJUDICATED,
        )
