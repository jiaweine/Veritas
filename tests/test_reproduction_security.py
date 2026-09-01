from __future__ import annotations

import pytest

from veritas.models import ReportedNumber, SourceLocation
from veritas.reproduction import (
    MethodField,
    MethodSpecification,
    ReproductionArtifact,
    ReproductionMode,
    ReproductionTarget,
    build_code_agent_task,
)
from veritas.reproduction_security import (
    AgentDispatchBlocked,
    AgentDispatchPolicy,
    AgentExecutionLocation,
    ArtifactAccessClassification,
    DataSensitivity,
    validate_agent_dispatch,
)


def _task():
    return build_code_agent_task(
        task_id="dispatch",
        mode=ReproductionMode.INDEPENDENT_REIMPLEMENTATION,
        method_spec=MethodSpecification(
            spec_id="method",
            object_type="RegressionResult",
            fields=(
                MethodField("outcome", "y"),
                MethodField("focal_predictor", "x"),
                MethodField("sample_rule", "complete cases"),
                MethodField("estimator", "ols"),
                MethodField("model_formula", "y ~ x"),
                MethodField("inference", "HC2"),
            ),
        ),
        artifacts=(ReproductionArtifact("data", "analysis_data", "a" * 64),),
        targets=(
            ReproductionTarget(
                "beta",
                "claim",
                "coefficient",
                ReportedNumber(0.1, decimals=2),
                SourceLocation(page=1, table="Table 1", row="x", column="B"),
            ),
        ),
    )


def test_remote_agent_allows_only_public_explicitly_authorized_artifacts() -> None:
    task = _task()
    validate_agent_dispatch(
        task,
        (
            ArtifactAccessClassification(
                "a" * 64,
                DataSensitivity.PUBLIC,
                external_model_egress_authorized=True,
                basis="public repository with verified terms",
            ),
        ),
        AgentDispatchPolicy(AgentExecutionLocation.REMOTE_PROVIDER, "codex-remote"),
    )


@pytest.mark.parametrize(
    "sensitivity",
    [
        DataSensitivity.LICENSED,
        DataSensitivity.RESTRICTED,
        DataSensitivity.SENSITIVE_PERSONAL,
        DataSensitivity.UNKNOWN,
    ],
)
def test_remote_agent_rejects_nonpublic_or_unknown_data(sensitivity: DataSensitivity) -> None:
    task = _task()
    with pytest.raises(AgentDispatchBlocked, match="restricted to public artifacts"):
        validate_agent_dispatch(
            task,
            (ArtifactAccessClassification("a" * 64, sensitivity),),
            AgentDispatchPolicy(AgentExecutionLocation.REMOTE_PROVIDER, "remote-provider"),
        )


def test_remote_agent_rejects_public_data_without_explicit_egress_authorization() -> None:
    task = _task()
    with pytest.raises(AgentDispatchBlocked, match="egress_not_authorized"):
        validate_agent_dispatch(
            task,
            (ArtifactAccessClassification("a" * 64, DataSensitivity.PUBLIC),),
            AgentDispatchPolicy(AgentExecutionLocation.REMOTE_PROVIDER, "remote-provider"),
        )


def test_local_agent_can_process_restricted_data_after_exact_artifact_classification() -> None:
    task = _task()
    validate_agent_dispatch(
        task,
        (ArtifactAccessClassification("a" * 64, DataSensitivity.RESTRICTED),),
        AgentDispatchPolicy(AgentExecutionLocation.LOCAL_SANDBOX, "local-agent"),
    )


def test_confidential_compute_rejects_unknown_data_and_requires_approval() -> None:
    task = _task()
    with pytest.raises(AgentDispatchBlocked, match="explicitly approved"):
        validate_agent_dispatch(
            task,
            (ArtifactAccessClassification("a" * 64, DataSensitivity.RESTRICTED),),
            AgentDispatchPolicy(
                AgentExecutionLocation.TRUSTED_CONFIDENTIAL_COMPUTE,
                "secure-enclave",
            ),
        )

    with pytest.raises(AgentDispatchBlocked, match="unknown-sensitivity"):
        validate_agent_dispatch(
            task,
            (ArtifactAccessClassification("a" * 64, DataSensitivity.UNKNOWN),),
            AgentDispatchPolicy(
                AgentExecutionLocation.TRUSTED_CONFIDENTIAL_COMPUTE,
                "secure-enclave",
                confidential_compute_approved=True,
            ),
        )


def test_dispatch_requires_exact_classification_of_locked_artifacts() -> None:
    task = _task()
    with pytest.raises(AgentDispatchBlocked, match="do not exactly match"):
        validate_agent_dispatch(
            task,
            (),
            AgentDispatchPolicy(AgentExecutionLocation.LOCAL_SANDBOX, "local-agent"),
        )
