from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Protocol

from .reproduction import CodeAgentProposal, CodeAgentTask, ReproductionMode


@dataclass(frozen=True)
class AgentSourceLocator:
    """Publication locator safe to expose to a blind implementation agent.

    Free text, character ranges and bounding boxes are deliberately excluded because a nearby
    result value can leak through an otherwise-methodological source quote.
    """

    artifact_id: str
    page: int | None
    section: str | None
    table: str | None
    figure: str | None
    row: str | None
    column: str | None


@dataclass(frozen=True)
class AgentMethodFieldView:
    name: str
    value: str | int | float | bool | None
    confidence: float
    required_for_execution: bool
    source: AgentSourceLocator


@dataclass(frozen=True)
class AgentArtifactView:
    artifact_id: str
    role: str
    sha256: str
    uri: str | None


@dataclass(frozen=True)
class AgentTargetView:
    target_id: str
    claim_id: str
    metric: str


@dataclass(frozen=True)
class AgentTaskView:
    task_sha256: str
    task_id: str
    mode: ReproductionMode
    method_spec_id: str
    method_object_type: str
    method_spec_version: str
    method_fields: tuple[AgentMethodFieldView, ...]
    artifacts: tuple[AgentArtifactView, ...]
    targets: tuple[AgentTargetView, ...]
    network_allowed: bool
    package_install_allowed: bool
    numeric_target_feedback_allowed: bool

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


class BlindCodeAgentBackend(Protocol):
    """Production coding-agent adapters should consume only this leak-safe task projection."""

    agent_id: str
    agent_version: str

    def solve(self, task: AgentTaskView) -> CodeAgentProposal: ...


def build_agent_task_view(task: CodeAgentTask) -> AgentTaskView:
    fields = tuple(
        AgentMethodFieldView(
            name=item.name,
            value=item.value,
            confidence=item.confidence,
            required_for_execution=item.required_for_execution,
            source=AgentSourceLocator(
                artifact_id=item.source.artifact_id,
                page=item.source.page,
                section=item.source.section,
                table=item.source.table,
                figure=item.source.figure,
                row=item.source.row,
                column=item.source.column,
            ),
        )
        for item in task.method_spec.fields
    )
    artifacts = tuple(
        AgentArtifactView(
            artifact_id=item.artifact_id,
            role=item.role,
            sha256=item.sha256,
            uri=item.uri,
        )
        for item in task.artifacts
    )
    targets = tuple(
        AgentTargetView(
            target_id=item.target_id,
            claim_id=item.claim_id,
            metric=item.metric,
        )
        for item in task.targets
    )
    policy = task.visibility_policy
    return AgentTaskView(
        task_sha256=task.sha256(),
        task_id=task.task_id,
        mode=task.mode,
        method_spec_id=task.method_spec.spec_id,
        method_object_type=task.method_spec.object_type,
        method_spec_version=task.method_spec.version,
        method_fields=fields,
        artifacts=artifacts,
        targets=targets,
        network_allowed=policy.allow_network,
        package_install_allowed=policy.allow_package_install,
        numeric_target_feedback_allowed=policy.reveal_numeric_comparison_during_iteration,
    )
