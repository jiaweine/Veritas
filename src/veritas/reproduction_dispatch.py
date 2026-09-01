from __future__ import annotations

from .reproduction import CodeAgentProposal, CodeAgentTask, validate_agent_proposal
from .reproduction_agent_view import BlindCodeAgentBackend, build_agent_task_view
from .reproduction_security import (
    AgentDispatchPolicy,
    ArtifactAccessClassification,
    validate_agent_dispatch,
)


def dispatch_blind_code_agent(
    task: CodeAgentTask,
    *,
    backend: BlindCodeAgentBackend,
    classifications: tuple[ArtifactAccessClassification, ...],
    dispatch_policy: AgentDispatchPolicy,
) -> CodeAgentProposal:
    """Only supported boundary for sending a locked reproduction task to a coding agent.

    Artifact egress is authorized before task projection. The backend receives only the leak-safe
    ``AgentTaskView``; it never receives paper target values, rich source quotes, upstream artifact
    URIs, or the full ``CodeAgentTask``. The returned proposal is then rebound to the original locked
    task before it can enter execution or comparison.
    """

    validate_agent_dispatch(task, classifications, dispatch_policy)
    agent_view = build_agent_task_view(task)
    proposal = backend.solve(agent_view)
    validate_agent_proposal(task, proposal)
    return proposal
