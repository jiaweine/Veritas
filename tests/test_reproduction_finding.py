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
from veritas.reproduction_attestation import ArtifactIdentityAttestation
from veritas.reproduction_finding import build_attested_reproduction_e4_check
from veritas.types import CheckStatus, EvidenceGrade, Materiality


def _bundle(reproduced_value: float):
    target = ReproductionTarget(
        "beta",
        "claim-main",
        "coefficient",
        ReportedNumber(0.10, decimals=2),
        SourceLocation(artifact_id="paper", page=4, table="Table 2"),
        Materiality.MAIN_EMPIRICAL_CLAIM,
    )
    method = MethodSpecification(
        "method",
        "RegressionResult",
        (
            MethodField("outcome", "y"),
            MethodField("estimator", "ols"),
            MethodField("inference", "HC2"),
        ),
    )
    task = build_code_agent_task(
        task_id="e4-finding",
        mode=ReproductionMode.INDEPENDENT_REIMPLEMENTATION,
        method_spec=method,
        artifacts=(ReproductionArtifact("data", "analysis_data", "a" * 64),),
        targets=(target,),
    )
    proposal = CodeAgentProposal(
        "agent",
        "1",
        task.sha256(),
        method.sha256(),
        task.visibility_policy.sha256(),
        "b" * 64,
        1,
    )
    policy = SandboxPolicy()
    execution = ExecutionAttestation(
        executor_id="executor",
        executor_version="1",
        task_sha256=task.sha256(),
        code_sha256=proposal.generated_code_sha256,
        frozen_workspace_sha256="c" * 64,
        environment_sha256="d" * 64,
        sandbox_policy_sha256=policy.sha256(),
        input_artifact_sha256=("a" * 64,),
        output_artifact_sha256=("e" * 64,),
        exit_code=0,
        network_disabled=True,
        read_only_inputs=True,
    )
    method_attestation = MethodFidelityAttestation(
        "method-verifier",
        "1",
        method.sha256(),
        proposal.generated_code_sha256,
        ("outcome", "estimator", "inference"),
        independent=True,
    )
    artifact_attestation = ArtifactIdentityAttestation(
        "artifact-verifier",
        "1",
        task.sha256(),
        ("a" * 64,),
        ("a" * 64,),
        independent=True,
    )
    comparisons = compare_reproduced_cells(
        (target,),
        (ReproducedCell("beta", reproduced_value, "e" * 64),),
    )
    return (
        target,
        task,
        proposal,
        policy,
        execution,
        method_attestation,
        artifact_attestation,
        comparisons,
    )


def _build(bundle, comparisons=None):
    target, task, proposal, policy, execution, method, artifact, canonical = bundle
    return build_attested_reproduction_e4_check(
        canonical if comparisons is None else comparisons,
        task=task,
        targets=(target,),
        proposal=proposal,
        sandbox_policy=policy,
        execution=execution,
        method_fidelity=method,
        artifact_identity=artifact,
        authority=ReproductionAuthority.INDEPENDENT_ADJUDICATED,
        object_id="regression-main",
        source=target.source,
    )


def test_fully_attested_mismatch_becomes_e4_without_numeric_value_leak() -> None:
    check = _build(_bundle(0.40))

    assert check.status is CheckStatus.FAIL
    assert check.finding is not None
    assert check.finding.grade is EvidenceGrade.REPRODUCTION_CONTRADICTION
    assert check.finding.evidence["numeric_values_persisted_in_finding"] is False
    rendered = repr(check.finding.evidence)
    assert "0.4" not in rendered
    assert "0.1" not in rendered
    assert check.finding.evidence["mismatch_target_ids"] == ["beta"]


def test_fully_attested_match_returns_pass_without_hard_finding() -> None:
    check = _build(_bundle(0.101))

    assert check.status is CheckStatus.PASS
    assert check.finding is None


def test_e4_finding_path_recomputes_and_rejects_forged_comparison_status() -> None:
    bundle = _bundle(0.101)
    canonical = bundle[-1]
    assert canonical[0].status is CellComparisonStatus.MATCH
    forged = (replace(canonical[0], status=CellComparisonStatus.MISMATCH),)

    with pytest.raises(ValueError, match="canonical Veritas comparison"):
        _build(bundle, forged)
