from __future__ import annotations

import os

from .acp import (
    AcpTurnRunner,
    AgentCommand,
    PermissionPolicy,
    ReplicationCancelledError,
    ReplicationDependencyError,
    ReplicationEvent,
    activate_replication_control,
    cancel_replication_run,
    deactivate_replication_control,
    replication_control_state,
    resolve_replication_permission,
)
from .acp import agent_from_environment as _agent_from_environment

_PROVIDER_ALIASES = {
    "gpt": "openai",
    "claude": "anthropic",
    "google": "gemini",
    "custom": "openai_compatible",
    "openai-compatible": "openai_compatible",
}
_PROVIDER_KEYS = {
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openai_compatible": "VERITAS_MODEL_API_KEY",
}
_PROVIDER_STYLES = {
    "openai": "responses",
    "deepseek": "openai-compatible",
    "anthropic": "messages",
    "gemini": "generate-content",
    "openai_compatible": "openai-compatible",
}


def _selected_model_provider() -> tuple[str, str] | None:
    requested = os.environ.get("VERITAS_MODEL_PROVIDER", "").strip().casefold()
    resolved = _PROVIDER_ALIASES.get(requested, requested)
    key_name = _PROVIDER_KEYS.get(resolved)
    model = os.environ.get("VERITAS_MODEL_NAME", "").strip()
    if not key_name or not model or not os.environ.get(key_name, "").strip():
        return None
    if resolved == "openai_compatible" and not os.environ.get("VERITAS_MODEL_BASE_URL", "").strip():
        return None
    return resolved, key_name


def agent_from_environment() -> AgentCommand | None:
    """Build the ACP command and bind only the selected provider configuration.

    The base ACP loader still forwards only an allow-list of environment names.
    When Veritas has a complete model-provider selection, this wrapper adds the
    selected provider key plus model-routing variables to that allow-list. Keys
    remain process-local: they are never copied into event payloads or browser
    capabilities, and credentials for unselected providers are not forwarded.
    """

    agent = _agent_from_environment()
    if agent is None:
        return None

    selected = _selected_model_provider()
    if selected is None:
        return agent

    provider_id, key_name = selected
    forwarded = list(agent.forward_env)
    for name in (
        "VERITAS_MODEL_PROVIDER",
        "VERITAS_MODEL_NAME",
        "VERITAS_MODEL_BASE_URL",
        key_name,
    ):
        if name in os.environ and name not in forwarded:
            forwarded.append(name)

    derived_env = dict(agent.env)
    derived_env["VERITAS_MODEL_PROVIDER_RESOLVED"] = provider_id
    derived_env["VERITAS_MODEL_API_STYLE"] = _PROVIDER_STYLES[provider_id]
    return AgentCommand(
        argv=agent.argv,
        name=agent.name,
        forward_env=tuple(forwarded),
        env=tuple(sorted(derived_env.items())),
    )


__all__ = [
    "AcpTurnRunner",
    "AgentCommand",
    "PermissionPolicy",
    "ReplicationCancelledError",
    "ReplicationDependencyError",
    "ReplicationEvent",
    "activate_replication_control",
    "agent_from_environment",
    "cancel_replication_run",
    "deactivate_replication_control",
    "replication_control_state",
    "resolve_replication_permission",
]
