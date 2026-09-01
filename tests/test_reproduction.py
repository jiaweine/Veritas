from __future__ import annotations

import pytest

from veritas.models import ReportedNumber, SourceLocation
from veritas.reproduction import (
    AgentVisibilityPolicy,
    CellComparisonStatus,
    CodeAgentProposal,
    ExecutionAttestation,
    MethodField,
    MethodFidelityAttestation,
    MethodSpecification,
    ReproducedCell,
    ReproductionArtifact,
    ReproductionAuthority,
    ReproductionBlocked,
    ReproductionDecision,
    ReproductionMode,
    ReproductionTarget,
    SandboxPolicy,
    build_code_agent_task,
    build_reproduction_report,
    compare_reproduced_cells,
    validate_agent_proposal,
    validate_frozen_execution,
)
from veritas.types import ComparisonOperator, EvidenceGrade, Materiality


EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def _method_spec(*, confidence: float = 1.0) -> MethodSpecification:
    return MethodSpecification(
        spec_id="method-main",
        object_type="RegressionResult",
        fields=(
            MethodField("outcome", "knowledge_score", confidence=confidence),
            MethodField("treatment", "age", confidence=confidence),
            MethodField("estimator", "ols", confidence=confidence),
            MethodField("sample_rule", "complete cases", confidence=confidence),
            MethodField("inference", "classical standard errors", confidence=confidence),
        ),
    )


def _artifacts() -> tuple[ReproductionArtifact, ...]:
    return (
        ReproductionArtifact("data", "analysis_data", "a" * 64, "file:///data.csv"),
        ReproductionArtifact("code", "original_code", "b" * 64, "file:///analysis.R"),
    )


def _targets() -> tuple[ReproductionTarget, ...]:
    return (
        ReproductionTarget(
            target_id="table2-age-b",
            claim_id="claim-main",
            metric="coefficient",
            reported=ReportedNumber(0.02, decimals=2),
            source=SourceLocation(page=8, table="Table 2", row="Age", column="B"),
            materiality=Materiality.MAIN_EMPIRICAL_CLAIM,
        ),
        ReproductionTarget(
            target_id="table2-age-p",
            claim_id="claim-main",
            metric="p_value",
            reported=ReportedNumber(0.001, decimals=3, operator=ComparisonOperator.LT),
            source=SourceLocation(page=8, table="Table 2", row="Age", column="p-value"),
            materiality=Materiality.MAIN_EMPIRICAL_CLAIM,
        ),
    )


def _proposal(task) -> CodeAgentProposal:
    return CodeAgentProposal(
        agent_id="test-agent",
        agent_version="1",
        task_sha256=task.sha256(),
        method_spec_sha256=task.method_spec.sha256(),
        visibility_policy_sha256=task.visibility_policy.sha256(),
        generated_code_sha256="1" * 64,
        attempts=1,
        original_code_patch_sha256=EMPTY_SHA256,
    )


def test_independent_task_hides_original_code_and_numeric_targets() -> None:
    task = build_code_agent_task(
        task_id="blind-reimplementation",
        mode=ReproductionMode.INDEPENDENT_REIMPLEMENTATION,
        method_spec=_method_spec(),
        artifacts=_artifacts(),
        targets=_targets(),
    )

    assert {artifact.role for artifact in task.artifacts} == {"analysis_data"}
    assert task.target_ids == ("table2-age-b", "table2-age-p")
    assert [(target.claim_id, target.metric) for target in task.targets] == [
        ("claim-main", "coefficient"),
        ("claim-main", "p_value"),
    ]
    rendered = repr(task)
    assert "reported=ReportedNumber" not in rendered
    assert "original_code" not in rendered
    assert "0.02" not in rendered
    assert task.reference_commitment_sha256


def test_independent_task_refuses_target_feedback_or_original_code_visibility() -> None:
    with pytest.raises(ReproductionBlocked):
        build_code_agent_task(
            task_id="unsafe-feedback",
            mode=ReproductionMode.INDEPENDENT_REIMPLEMENTATION,
            method_spec=_method_spec(),
            artifacts=_artifacts(),
            targets=_targets(),
            visibility_policy=AgentVisibilityPolicy(reveal_numeric_comparison_during_iteration=True),
        )

    with pytest.raises(ReproductionBlocked):
        build_code_agent_task(
            task_id="unsafe-code-visibility",
            mode=ReproductionMode.INDEPENDENT_REIMPLEMENTATION,
            method_spec=_method_spec(),
            artifacts=_artifacts(),
            targets=_targets(),
            visibility_policy=AgentVisibilityPolicy(allow_original_code=True),
        )


def test_reproduction_blocks_missing_data_or_low_confidence_method_fields() -> None:
    with pytest.raises(ReproductionBlocked):
        build_code_agent_task(
            task_id="no-data",
            mode=ReproductionMode.AUTHOR_CODE,
            method_spec=_method_spec(),
            artifacts=(ReproductionArtifact("code", "original_code", "b" * 64),),
            targets=_targets(),
        )

    with pytest.raises(ReproductionBlocked):
        build_code_agent_task(
            task_id="weak-method",
            mode=ReproductionMode.INDEPENDENT_REIMPLEMENTATION,
            method_spec=_method_spec(confidence=0.7),
            artifacts=_artifacts(),
            targets=_targets(),
        )


def test_cell_comparison_is_rounding_aware_and_handles_reported_inequalities() -> None:
    comparisons = compare_reproduced_cells(
        _targets(),
        (
            ReproducedCell("table2-age-b", 0.0249, "c" * 64),
            ReproducedCell("table2-age-p", 0.0008, "d" * 64),
        ),
    )

    assert [item.status for item in comparisons] == [
        CellComparisonStatus.MATCH,
        CellComparisonStatus.MATCH,
    ]
    assert comparisons[0].reported_interval == pytest.approx((0.015, 0.025))


def test_experimental_agent_mismatch_is_never_promoted_to_e4() -> None:
    comparisons = compare_reproduced_cells(
        _targets(),
        (
            ReproducedCell("table2-age-b", 0.20, "c" * 64),
            ReproducedCell("table2-age-p", 0.20, "d" * 64),
        ),
    )
    report = build_reproduction_report(
        comparisons,
        authority=ReproductionAuthority.EXPERIMENTAL_AGENT,
        method_fidelity_verified=True,
        artifact_identity_verified=True,
        execution_attested=True,
    )

    assert report.decision is ReproductionDecision.MISMATCH
    assert report.max_evidence_grade is EvidenceGrade.WEAK_SIGNAL
    assert report.agreement.material_mismatch_target_ids == ("table2-age-b", "table2-age-p")
    assert "experimental code-agent attempts cannot emit E4 evidence" in report.reasons


def test_verified_author_package_mismatch_may_emit_e4() -> None:
    comparisons = compare_reproduced_cells(
        _targets(),
        (
            ReproducedCell("table2-age-b", 0.20, "c" * 64),
            ReproducedCell("table2-age-p", 0.20, "d" * 64),
        ),
    )
    report = build_reproduction_report(
        comparisons,
        authority=ReproductionAuthority.AUTHOR_PACKAGE_RERUN,
        method_fidelity_verified=True,
        artifact_identity_verified=True,
        execution_attested=True,
    )

    assert report.decision is ReproductionDecision.MISMATCH
    assert report.max_evidence_grade is EvidenceGrade.REPRODUCTION_CONTRADICTION


def test_unverified_method_fidelity_caps_mismatch_at_weak_signal() -> None:
    comparisons = compare_reproduced_cells(
        _targets(),
        (ReproducedCell("table2-age-b", 0.20, "c" * 64),),
    )
    report = build_reproduction_report(
        comparisons,
        authority=ReproductionAuthority.INDEPENDENT_ADJUDICATED,
        method_fidelity_verified=False,
        artifact_identity_verified=True,
        execution_attested=True,
    )

    assert report.max_evidence_grade is EvidenceGrade.WEAK_SIGNAL
    assert "method fidelity has not been independently verified" in report.reasons


def test_agent_proposal_and_executor_are_independently_bound_to_locked_task() -> None:
    task = build_code_agent_task(
        task_id="author-rerun",
        mode=ReproductionMode.AUTHOR_CODE,
        method_spec=_method_spec(),
        artifacts=_artifacts(),
        targets=_targets(),
    )
    proposal = _proposal(task)
    validate_agent_proposal(task, proposal)

    policy = SandboxPolicy()
    attestation = ExecutionAttestation(
        executor_id="sandbox-worker",
        executor_version="1",
        task_sha256=task.sha256(),
        code_sha256=proposal.generated_code_sha256,
        frozen_workspace_sha256="2" * 64,
        environment_sha256="3" * 64,
        sandbox_policy_sha256=policy.sha256(),
        input_artifact_sha256=tuple(artifact.sha256 for artifact in task.artifacts),
        output_artifact_sha256=("4" * 64,),
        exit_code=0,
        network_disabled=True,
        read_only_inputs=True,
    )
    validate_frozen_execution(task, proposal, policy, attestation)

    wrong_code = ExecutionAttestation(
        executor_id="sandbox-worker",
        executor_version="1",
        task_sha256=task.sha256(),
        code_sha256="9" * 64,
        frozen_workspace_sha256="2" * 64,
        environment_sha256="3" * 64,
        sandbox_policy_sha256=policy.sha256(),
        input_artifact_sha256=tuple(artifact.sha256 for artifact in task.artifacts),
        output_artifact_sha256=("4" * 64,),
        exit_code=0,
        network_disabled=True,
        read_only_inputs=True,
    )
    with pytest.raises(ValueError, match="frozen code"):
        validate_frozen_execution(task, proposal, policy, wrong_code)


def test_method_fidelity_attestation_requires_independent_clean_verification() -> None:
    spec = _method_spec()
    attestation = MethodFidelityAttestation(
        verifier_id="method-verifier",
        verifier_version="1",
        method_spec_sha256=spec.sha256(),
        implementation_sha256="1" * 64,
        verified_fields=tuple(field.name for field in spec.fields),
        independent=True,
    )
    assert attestation.passed

    unresolved = MethodFidelityAttestation(
        verifier_id="method-verifier",
        verifier_version="1",
        method_spec_sha256=spec.sha256(),
        implementation_sha256="1" * 64,
        verified_fields=("outcome", "treatment"),
        unresolved_fields=("inference",),
        independent=True,
    )
    assert not unresolved.passed
