from __future__ import annotations

from dataclasses import dataclass, field

from veritas.models import ReportedNumber, SourceLocation
from veritas.reproduction import (
    CodeAgentProposal,
    MethodField,
    MethodSpecification,
    ReproductionArtifact,
    ReproductionMode,
    ReproductionTarget,
    build_code_agent_task,
)
from veritas.reproduction_agent_view import AgentTaskView
from veritas.reproduction_dispatch import dispatch_blind_code_agent
from veritas.reproduction_security import (
    AgentDispatchPolicy,
    AgentExecutionLocation,
    ArtifactAccessClassification,
    DataSensitivity,
)


@dataclass
class RecordingBackend:
    method_spec_sha256: str
    visibility_policy_sha256: str
    agent_id: str = "recording-agent"
    agent_version: str = "1"
    seen: list[AgentTaskView] = field(default_factory=list)

    def solve(self, task: AgentTaskView) -> CodeAgentProposal:
        self.seen.append(task)
        return CodeAgentProposal(
            agent_id=self.agent_id,
            agent_version=self.agent_version,
            task_sha256=task.task_sha256,
            method_spec_sha256=self.method_spec_sha256,
            visibility_policy_sha256=self.visibility_policy_sha256,
            generated_code_sha256="c" * 64,
            attempts=1,
        )


def _task():
    return build_code_agent_task(
        task_id="blind-dispatch",
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
        artifacts=(
            ReproductionArtifact(
                "analysis.csv",
                "analysis_data",
                "a" * 64,
                "https://repository.example/paper-and-code-deposit/analysis.csv",
            ),
        ),
        targets=(
            ReproductionTarget(
                "beta",
                "claim-main",
                "coefficient",
                ReportedNumber(0.125, decimals=3),
                SourceLocation(page=5, table="Table 2", row="x", column="B"),
            ),
        ),
    )


def test_blind_dispatch_exposes_only_sanitized_view_and_rebinds_proposal() -> None:
    task = _task()
    backend = RecordingBackend(
        method_spec_sha256=task.method_spec.sha256(),
        visibility_policy_sha256=task.visibility_policy.sha256(),
    )

    proposal = dispatch_blind_code_agent(
        task,
        backend=backend,
        classifications=(
            ArtifactAccessClassification(
                "a" * 64,
                DataSensitivity.PUBLIC,
                external_model_egress_authorized=True,
                basis="public data approved for model egress",
            ),
        ),
        dispatch_policy=AgentDispatchPolicy(
            AgentExecutionLocation.REMOTE_PROVIDER,
            "test-code-agent",
        ),
    )

    assert proposal.task_sha256 == task.sha256()
    assert len(backend.seen) == 1
    rendered = backend.seen[0].to_json()
    assert "0.125" not in rendered
    assert "repository.example" not in rendered
    assert "paper-and-code-deposit" not in rendered
    assert "analysis.csv" in rendered
