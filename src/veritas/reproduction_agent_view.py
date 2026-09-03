from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Protocol

from .reproduction import CodeAgentProposal, CodeAgentTask, ReproductionMode

INDEPENDENT_AGENT_ALLOWED_ARTIFACT_ROLES = frozenset(
    {"raw_data", "analysis_data", "data_dictionary", "schema"}
)


class AgentTaskViewBlocked(RuntimeError):
    """Raised when a locked task cannot be projected into a leak-safe agent view."""


@dataclass(frozen=True)
class AgentMethodFieldView:
    """Semantic method choice only; publication provenance remains internal to Veritas."""

    name: str
    value: str | int | float | bool | None
    confidence: float
    required_for_execution: bool


@dataclass(frozen=True)
class AgentArtifactView:
    """Opaque artifact identity exposed to an agent after the orchestrator mounts inputs.

    Upstream URIs are intentionally excluded. A URI can lead to a repository or deposit that also
    contains the paper, author code, outputs, or other target-leaking material. Backends should map
    ``artifact_id`` to a sandbox mount outside the model-visible task payload.
    """

    artifact_id: str
    role: str
    sha256: str


@dataclass(frozen=True)
class AgentTargetView:
    """Only the output identity and metric required for machine-readable result emission."""

    target_id: str
    metric: str


@dataclass(frozen=True)
class AgentTaskView:
    """Model-visible projection with internal task/spec/claim identifiers removed."""

    task_sha256: str
    mode: ReproductionMode
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


def _validate_independent_view_boundary(task: CodeAgentTask) -> None:
    if task.mode is not ReproductionMode.INDEPENDENT_REIMPLEMENTATION:
        return

    policy = task.visibility_policy
    if policy.allow_reported_outcomes:
        raise AgentTaskViewBlocked("independent agent view cannot expose reported outcomes")
    if policy.allow_original_code:
        raise AgentTaskViewBlocked("independent agent view cannot expose original author code")
    if policy.reveal_numeric_comparison_during_iteration:
        raise AgentTaskViewBlocked("independent agent view cannot expose numeric target feedback")
    if policy.allow_network:
        raise AgentTaskViewBlocked("independent blind reproduction must disable agent network access")

    disallowed = tuple(
        sorted(
            {
                artifact.role
                for artifact in task.artifacts
                if artifact.role not in INDEPENDENT_AGENT_ALLOWED_ARTIFACT_ROLES
            }
        )
    )
    if disallowed:
        raise AgentTaskViewBlocked(
            "independent agent artifacts must be leak-reviewed data/schema inputs; "
            f"disallowed roles={disallowed!r}"
        )


def build_agent_task_view(task: CodeAgentTask) -> AgentTaskView:
    _validate_independent_view_boundary(task)

    fields = tuple(
        AgentMethodFieldView(
            name=item.name,
            value=item.value,
            confidence=item.confidence,
            required_for_execution=item.required_for_execution,
        )
        for item in task.method_spec.fields
    )
    artifacts = tuple(
        AgentArtifactView(
            artifact_id=item.artifact_id,
            role=item.role,
            sha256=item.sha256,
        )
        for item in task.artifacts
    )
    targets = tuple(
        AgentTargetView(
            target_id=item.target_id,
            metric=item.metric,
        )
        for item in task.targets
    )
    policy = task.visibility_policy
    return AgentTaskView(
        task_sha256=task.sha256(),
        mode=task.mode,
        method_object_type=task.method_spec.object_type,
        method_spec_version=task.method_spec.version,
        method_fields=fields,
        artifacts=artifacts,
        targets=targets,
        network_allowed=policy.allow_network,
        package_install_allowed=policy.allow_package_install,
        numeric_target_feedback_allowed=policy.reveal_numeric_comparison_during_iteration,
    )
