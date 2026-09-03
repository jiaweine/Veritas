from __future__ import annotations

from dataclasses import replace

import pytest

from veritas.models import ReportedNumber, SourceLocation
from veritas.reproduction import (
    AgentTargetDescriptor,
    AgentVisibilityPolicy,
    ExecutionAttestation,
    MethodField,
    MethodSpecification,
    ReproductionArtifact,
    ReproductionMode,
    ReproductionTarget,
    build_code_agent_task,
)
from veritas.reproduction_agent_view import AgentTaskViewBlocked, build_agent_task_view
from veritas.reproduction_attestation import validate_comparison_evidence
from veritas.types import ComparisonOperator, Materiality


def _target() -> ReproductionTarget:
    return ReproductionTarget(
        target_id="beta",
        claim_id="claim-main",
        metric="coefficient",
        reported=ReportedNumber(0.10, decimals=2),
        source=SourceLocation(page=4, table="Table 2", row="Treatment", column="B"),
        materiality=Materiality.MAIN_EMPIRICAL_CLAIM,
    )


def _task():
    target = _target()
    return build_code_agent_task(
        task_id="runtime-boundaries",
        mode=ReproductionMode.INDEPENDENT_REIMPLEMENTATION,
        method_spec=MethodSpecification(
            spec_id="method",
            object_type="RegressionResult",
            fields=(MethodField("estimator", "ols"),),
        ),
        artifacts=(ReproductionArtifact("data", "analysis_data", "a" * 64),),
        targets=(target,),
    )


def _execution(task) -> ExecutionAttestation:
    return ExecutionAttestation(
        executor_id="executor",
        executor_version="1",
        task_sha256=task.sha256(),
        code_sha256="b" * 64,
        frozen_workspace_sha256="c" * 64,
        environment_sha256="d" * 64,
        sandbox_policy_sha256="e" * 64,
        input_artifact_sha256=tuple(artifact.sha256 for artifact in task.artifacts),
        output_artifact_sha256=("f" * 64,),
        exit_code=0,
        network_disabled=True,
        read_only_inputs=True,
    )


def _replace_target(*, reported=None, materiality=None) -> ReproductionTarget:
    base = _target()
    return ReproductionTarget(
        target_id=base.target_id,
        claim_id=base.claim_id,
        metric=base.metric,
        reported=reported if reported is not None else base.reported,
        source=base.source,
        materiality=materiality if materiality is not None else base.materiality,
    )


@pytest.mark.parametrize(
    "reported,error,exception_type",
    [
        (ReportedNumber(True, decimals=2), "reported value.*finite numeric", TypeError),
        (ReportedNumber(float("nan"), decimals=2), "reported value must be finite", ValueError),
        (ReportedNumber(0.1, decimals=-1), "decimals must be non-negative", ValueError),
        (ReportedNumber(0.1, decimals=True), "decimals.*non-negative integer", TypeError),
    ],
)
def test_e4_rejects_invalid_direct_reported_number_objects(
    reported: ReportedNumber,
    error: str,
    exception_type: type[Exception],
) -> None:
    task = _task()
    target = _replace_target(reported=reported)

    with pytest.raises(exception_type, match=error):
        validate_comparison_evidence(task, (target,), (), _execution(task))


def test_e4_rejects_untyped_direct_operator_and_materiality() -> None:
    task = _task()
    invalid_operator = _replace_target(
        reported=ReportedNumber(0.1, decimals=2, operator="="),  # type: ignore[arg-type]
    )
    with pytest.raises(TypeError, match="comparison operator"):
        validate_comparison_evidence(task, (invalid_operator,), (), _execution(task))

    invalid_materiality = _replace_target(materiality=2)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="materiality"):
        validate_comparison_evidence(task, (invalid_materiality,), (), _execution(task))


def test_e4_rejects_task_descriptor_claim_or_metric_drift() -> None:
    task = _task()
    target = _target()
    drifted = replace(
        task,
        targets=(AgentTargetDescriptor("beta", "different-claim", "coefficient"),),
    )

    with pytest.raises(ValueError, match="target descriptors drifted"):
        validate_comparison_evidence(drifted, (target,), (), _execution(drifted))


def test_blind_view_rejects_truthy_string_visibility_flag() -> None:
    task = _task()
    unsafe = replace(
        task,
        visibility_policy=AgentVisibilityPolicy(allow_network="false"),  # type: ignore[arg-type]
    )

    with pytest.raises(AgentTaskViewBlocked, match="allow_network.*boolean"):
        build_agent_task_view(unsafe)


def test_blind_view_rejects_truthy_string_required_method_flag() -> None:
    task = _task()
    unsafe_spec = MethodSpecification(
        spec_id="method",
        object_type="RegressionResult",
        fields=(
            MethodField(
                "estimator",
                "ols",
                required_for_execution="false",  # type: ignore[arg-type]
            ),
        ),
    )
    unsafe = replace(task, method_spec=unsafe_spec)

    with pytest.raises(AgentTaskViewBlocked, match="required_for_execution.*boolean"):
        build_agent_task_view(unsafe)


def test_blind_view_rejects_string_reproduction_mode() -> None:
    task = _task()
    unsafe = replace(task, mode="independent_reimplementation")  # type: ignore[arg-type]

    with pytest.raises(AgentTaskViewBlocked, match="ReproductionMode"):
        build_agent_task_view(unsafe)


def test_valid_direct_target_types_still_reach_commitment_check() -> None:
    task = _task()
    target = _replace_target(
        reported=ReportedNumber(0.11, decimals=2, operator=ComparisonOperator.EQ)
    )

    with pytest.raises(ValueError, match="locked target commitment"):
        validate_comparison_evidence(task, (target,), (), _execution(task))
