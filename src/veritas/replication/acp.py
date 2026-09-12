from __future__ import annotations

import asyncio
import os
import shlex
from collections.abc import AsyncIterator, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4


class PermissionPolicy(StrEnum):
    """Host-side policy for ACP permission requests.

    ``DENY`` is the safe default. ``ALLOW_ONCE`` may select only an explicit
    ``allow_once`` option offered by the agent; it never upgrades to
    ``allow_always``.
    """

    DENY = "deny"
    ALLOW_ONCE = "allow_once"


@dataclass(frozen=True)
class AgentCommand:
    """One ACP-compatible agent process launched through stdio."""

    argv: tuple[str, ...]
    name: str = "ACP agent"
    forward_env: tuple[str, ...] = ()
    env: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.argv or any(not isinstance(value, str) or not value for value in self.argv):
            raise ValueError("agent argv must contain at least one non-empty string")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("agent name must be non-empty")
        for key in self.forward_env:
            if not key or "=" in key or "\x00" in key:
                raise ValueError(f"invalid forwarded environment name: {key!r}")
        for key, value in self.env:
            if not key or "=" in key or "\x00" in key or "\x00" in value:
                raise ValueError("agent environment entries must be valid process environment strings")

    @classmethod
    def from_shell(
        cls,
        command: str,
        *,
        name: str = "ACP agent",
        forward_env: Iterable[str] = (),
        env: Mapping[str, str] | None = None,
    ) -> AgentCommand:
        argv = tuple(shlex.split(command))
        return cls(
            argv=argv,
            name=name,
            forward_env=tuple(forward_env),
            env=tuple(sorted((env or {}).items())),
        )

    def process_env(self, source: Mapping[str, str] | None = None) -> dict[str, str]:
        source = os.environ if source is None else source
        safe_names = (
            "PATH",
            "HOME",
            "USERPROFILE",
            "LANG",
            "LC_ALL",
            "TMPDIR",
            "TEMP",
            "TMP",
            "TERM",
        )
        result = {key: source[key] for key in safe_names if key in source}
        for key in self.forward_env:
            if key in source:
                result[key] = source[key]
        result.update(dict(self.env))
        return result


@dataclass(frozen=True)
class ReplicationEvent:
    kind: str
    title: str
    detail: str = ""
    status: str = "info"
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: f"rep_evt_{uuid4().hex[:12]}")
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z")
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "kind": self.kind,
            "title": self.title,
            "detail": self.detail,
            "status": self.status,
            "payload": self.payload,
            "created_at": self.created_at,
        }


class ReplicationDependencyError(RuntimeError):
    pass


class AcpTurnRunner:
    """Run one ACP turn inside a caller-selected workspace.

    The ACP agent owns its own execution sandbox. Veritas supplies only the
    workspace ``cwd`` and a conservative environment. Callers must not treat
    ``cwd`` as a security boundary unless the selected agent documents and
    enables one.
    """

    def __init__(
        self,
        agent: AgentCommand,
        *,
        permission_policy: PermissionPolicy = PermissionPolicy.DENY,
    ) -> None:
        if not isinstance(agent, AgentCommand):
            raise TypeError("agent must be an AgentCommand")
        if not isinstance(permission_policy, PermissionPolicy):
            raise TypeError("permission_policy must be a PermissionPolicy")
        self.agent = agent
        self.permission_policy = permission_policy

    async def stream_turn(self, workspace: str | Path, prompt: str) -> AsyncIterator[dict[str, Any]]:
        workspace_path = Path(workspace).expanduser().resolve()
        if not workspace_path.is_dir():
            raise ValueError(f"replication workspace does not exist: {workspace_path}")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("replication prompt must be non-empty")

        try:
            from acp import PROTOCOL_VERSION, spawn_agent_process
            from acp.interfaces import Client
            from acp.schema import (
                AllowedOutcome,
                DeniedOutcome,
                RequestPermissionResponse,
                TextContentBlock,
            )
        except ImportError as exc:
            raise ReplicationDependencyError(
                "ACP replication support requires `pip install -e '.[replication]'`"
            ) from exc

        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        policy = self.permission_policy

        class StreamingClient(Client):
            async def session_update(
                self,
                session_id: str,
                update: object,
                **_: Any,
            ) -> None:
                payload = _jsonable(update)
                update_kind = str(
                    payload.get("sessionUpdate")
                    or payload.get("session_update")
                    or type(update).__name__
                )
                detail = _update_detail(payload)
                await queue.put(
                    ReplicationEvent(
                        kind="agent_update",
                        title=update_kind,
                        detail=detail,
                        status=_status_for_update(update_kind, payload),
                        payload={"session_id": session_id, "update": payload},
                    ).to_dict()
                )

            async def request_permission(
                self,
                session_id: str,
                tool_call: object,
                options: list[object],
                **_: Any,
            ) -> object:
                call_payload = _jsonable(tool_call)
                option_payloads = [_jsonable(option) for option in options]
                selected = _select_allow_once(options) if policy is PermissionPolicy.ALLOW_ONCE else None
                decision = "selected" if selected is not None else "cancelled"
                await queue.put(
                    ReplicationEvent(
                        kind="permission",
                        title=str(call_payload.get("title") or call_payload.get("name") or "Tool permission"),
                        detail=(
                            "Allowed once by explicit Veritas policy."
                            if selected is not None
                            else "Denied by Veritas replication policy."
                        ),
                        status="review" if selected is not None else "blocked",
                        payload={
                            "session_id": session_id,
                            "tool_call": call_payload,
                            "options": option_payloads,
                            "decision": decision,
                            "policy": policy.value,
                        },
                    ).to_dict()
                )
                if selected is None:
                    return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))
                return RequestPermissionResponse(
                    outcome=AllowedOutcome(option_id=selected.option_id, outcome="selected")
                )

        yield ReplicationEvent(
            kind="agent",
            title=f"Starting {self.agent.name}",
            detail=str(workspace_path),
            status="running",
            payload={
                "agent": self.agent.name,
                "argv": list(self.agent.argv),
                "permission_policy": self.permission_policy.value,
                "workspace": str(workspace_path),
                "workspace_is_security_boundary": False,
            },
        ).to_dict()

        client = StreamingClient()
        async with spawn_agent_process(
            client,
            *self.agent.argv,
            env=self.agent.process_env(),
        ) as (connection, process):
            initialized = await connection.initialize(protocol_version=PROTOCOL_VERSION)
            session = await connection.new_session(cwd=str(workspace_path), mcp_servers=[])
            prompt_task = asyncio.create_task(
                connection.prompt(
                    session_id=session.session_id,
                    prompt=[TextContentBlock(text=prompt.strip())],
                )
            )

            while not prompt_task.done() or not queue.empty():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.1)
                except TimeoutError:
                    continue
                yield event

            response = await prompt_task
            while not queue.empty():
                yield queue.get_nowait()

            yield ReplicationEvent(
                kind="turn_completed",
                title="Replication turn completed",
                detail=str(getattr(response, "stop_reason", "end_turn")),
                status="success",
                payload={
                    "session_id": session.session_id,
                    "protocol_version": getattr(initialized, "protocol_version", PROTOCOL_VERSION),
                    "stop_reason": getattr(response, "stop_reason", None),
                    "process_returncode": process.returncode,
                },
            ).to_dict()

    async def run_turn(self, workspace: str | Path, prompt: str) -> tuple[dict[str, Any], ...]:
        events = [event async for event in self.stream_turn(workspace, prompt)]
        return tuple(events)


def agent_from_environment() -> AgentCommand | None:
    raw = os.environ.get("VERITAS_REPLICATION_AGENT", "").strip()
    if not raw:
        return None
    name = os.environ.get("VERITAS_REPLICATION_AGENT_NAME", "ACP agent").strip() or "ACP agent"
    forward = tuple(
        item.strip()
        for item in os.environ.get("VERITAS_REPLICATION_FORWARD_ENV", "").split(",")
        if item.strip()
    )
    return AgentCommand.from_shell(raw, name=name, forward_env=forward)


def _select_allow_once(options: Iterable[object]) -> object | None:
    for option in options:
        if getattr(option, "kind", None) == "allow_once" and getattr(option, "option_id", None):
            return option
    return None


def _jsonable(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(mode="json", by_alias=True, exclude_none=True)
        if isinstance(dumped, dict):
            return {str(key): _json_value(item) for key, item in dumped.items()}
    return {"value": str(value)}


def _json_value(value: object) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _json_value(model_dump(mode="json", by_alias=True, exclude_none=True))
    return str(value)


def _update_detail(payload: Mapping[str, Any]) -> str:
    content = payload.get("content")
    if isinstance(content, dict) and isinstance(content.get("text"), str):
        return content["text"]
    title = payload.get("title")
    if isinstance(title, str):
        return title
    return ""


def _status_for_update(update_kind: str, payload: Mapping[str, Any]) -> str:
    normalized = update_kind.casefold()
    status = str(payload.get("status", "")).casefold()
    if status in {"failed", "error"}:
        return "danger"
    if "tool" in normalized or "plan" in normalized:
        return "running"
    return "info"
