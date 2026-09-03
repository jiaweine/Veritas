from __future__ import annotations

from .reproduction import (
    AuthorCodeAgentBackend,
    CodeAgentProposal,
    CodeAgentTask,
    ReproductionMode,
    validate_agent_proposal,
)
from .reproduction_agent_view import BlindCodeAgentBackend, build_agent_task_view
from .reproduction_methods import validate_method_specification_contract
from .reproduction_security import (
    AgentDispatchPolicy,
    ArtifactAccessClassification,
    validate_agent_dispatch,
)


def dispatch_author_code_agent(
    task: CodeAgentTask,
    *,
    backend: AuthorCodeAgentBackend,
) -> CodeAgentProposal:
    """Only supported full-task dispatch boundary for author-package reproduction."""

    if task.mode is not ReproductionMode.AUTHOR_CODE:
        raise ValueError("full-task agent dispatch is reserved for author-code reproduction")
    allow_original_code = task.visibility_policy.allow_original_code
    if type(allow_original_code) is not bool:
        raise TypeError("author-code allow_original_code authorization must be a boolean")
    if allow_original_code is not True:
        raise ValueError("author-code dispatch requires explicit original-code visibility")
    proposal = backend.solve(task)
    validate_agent_proposal(task, proposal)
    return proposal


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

    validate_method_specification_contract(task.method_spec)
    validate_agent_dispatch(task, classifications, dispatch_policy)
    agent_view = build_agent_task_view(task)
    proposal = backend.solve(agent_view)
    validate_agent_proposal(task, proposal)
    return proposal
