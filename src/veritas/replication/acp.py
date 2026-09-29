from __future__ import annotations

import asyncio
import contextlib
import os
import shlex
import threading
from collections.abc import AsyncIterator, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4


class PermissionPolicy(StrEnum):
    """Host-side policy for ACP permission requests.

    ``DENY`` remains the safe default. ``ALLOW_ONCE`` may select only an
    explicit ``allow_once`` option offered by the agent. ``INTERACTIVE`` is
    fail-closed unless a host control plane has explicitly activated the run;
    when active, a human decision may select only an offered ``allow_once``
    option and can never upgrade to ``allow_always``.
    """

    DENY = "deny"
    ALLOW_ONCE = "allow_once"
    INTERACTIVE = "interactive"


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


class ReplicationCancelledError(RuntimeError):
    pass


@dataclass
class _PendingPermission:
    run_id: str
    request_id: str
    options: tuple[dict[str, Any], ...]
    future: asyncio.Future[str | None]
    loop: asyncio.AbstractEventLoop
    created_at: str


@dataclass
class _RunControl:
    run_id: str
    interactive_permissions: bool
    cancelled: bool = False
    pending: dict[str, _PendingPermission] = field(default_factory=dict)


class _InteractiveControlPlane:
    """Process-local control plane for a currently streaming ACP run.

    The web harness activates runs explicitly. CLI callers never enter this
    registry, so ``PermissionPolicy.INTERACTIVE`` remains deny-by-default when
    no host UI is present. Futures are resolved through their owning event loop
    so approval requests may arrive on another ASGI request/thread safely.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._runs: dict[str, _RunControl] = {}

    def activate(self, run_id: str, *, interactive_permissions: bool) -> None:
        _validate_run_id(run_id)
        with self._lock:
            self._runs[run_id] = _RunControl(
                run_id=run_id,
                interactive_permissions=interactive_permissions,
            )

    def deactivate(self, run_id: str) -> None:
        with self._lock:
            control = self._runs.pop(run_id, None)
        if control is None:
            return
        for pending in tuple(control.pending.values()):
            pending.loop.call_soon_threadsafe(_resolve_future, pending.future, None)

    def state(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            control = self._runs.get(run_id)
            if control is None:
                return {
                    "run_id": run_id,
                    "active": False,
                    "cancel_requested": False,
                    "interactive_permissions": False,
                    "pending_permissions": [],
                }
            pending = [
                {
                    "request_id": item.request_id,
                    "options": list(item.options),
                    "created_at": item.created_at,
                }
                for item in control.pending.values()
            ]
            return {
                "run_id": run_id,
                "active": True,
                "cancel_requested": control.cancelled,
                "interactive_permissions": control.interactive_permissions,
                "pending_permissions": pending,
            }

    def active(self, run_id: str) -> bool:
        with self._lock:
            return run_id in self._runs

    def interactive(self, run_id: str) -> bool:
        with self._lock:
            control = self._runs.get(run_id)
            return bool(control and control.interactive_permissions)

    def cancelled(self, run_id: str) -> bool:
        with self._lock:
            control = self._runs.get(run_id)
            return bool(control and control.cancelled)

    def cancel(self, run_id: str) -> bool:
        with self._lock:
            control = self._runs.get(run_id)
            if control is None:
                return False
            control.cancelled = True
            pending = tuple(control.pending.values())
            control.pending.clear()
        for item in pending:
            item.loop.call_soon_threadsafe(_resolve_future, item.future, None)
        return True

    async def request(
        self,
        run_id: str,
        request_id: str,
        options: tuple[dict[str, Any], ...],
        *,
        timeout_seconds: float = 300.0,
    ) -> str | None:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str | None] = loop.create_future()
        pending = _PendingPermission(
            run_id=run_id,
            request_id=request_id,
            options=options,
            future=future,
            loop=loop,
            created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )
        with self._lock:
            control = self._runs.get(run_id)
            if control is None or not control.interactive_permissions or control.cancelled:
                return None
            control.pending[request_id] = pending
        try:
            return await asyncio.wait_for(future, timeout=timeout_seconds)
        except TimeoutError:
            return None
        finally:
            with self._lock:
                control = self._runs.get(run_id)
                if control is not None:
                    control.pending.pop(request_id, None)

    def resolve(
        self,
        run_id: str,
        request_id: str,
        *,
        decision: str,
        option_id: str | None = None,
    ) -> dict[str, Any]:
        normalized = decision.strip().casefold()
        if normalized not in {"allow_once", "reject"}:
            raise ValueError("permission decision must be allow_once or reject")
        with self._lock:
            control = self._runs.get(run_id)
            if control is None:
                raise KeyError("replication run is not active")
            if control.cancelled:
                raise KeyError("replication run cancellation already requested")
            pending = control.pending.get(request_id)
            if pending is None:
                raise KeyError("permission request is not pending")
            allow_once_options = [
                item
                for item in pending.options
                if item.get("kind") == "allow_once" and item.get("optionId")
            ]
            selected_id: str | None = None
            if normalized == "allow_once":
                if not allow_once_options:
                    raise ValueError("agent did not offer an allow_once permission option")
                if option_id:
                    match = next(
                        (item for item in allow_once_options if item.get("optionId") == option_id),
                        None,
                    )
                    if match is None:
                        raise ValueError("selected permission option is not an offered allow_once option")
                    selected_id = str(match["optionId"])
                elif len(allow_once_options) == 1:
                    selected_id = str(allow_once_options[0]["optionId"])
                else:
                    raise ValueError("option_id is required when multiple allow_once options are offered")
            consumed = control.pending.pop(request_id, None)
            if consumed is not pending:
                raise KeyError("permission request is not pending")
            loop = pending.loop
            future = pending.future
        loop.call_soon_threadsafe(_resolve_future, future, selected_id)
        return {
            "run_id": run_id,
            "request_id": request_id,
            "decision": normalized,
            "selected_option_id": selected_id,
        }


_CONTROL_PLANE = _InteractiveControlPlane()


def activate_replication_control(run_id: str, *, interactive_permissions: bool) -> None:
    _CONTROL_PLANE.activate(run_id, interactive_permissions=interactive_permissions)


def deactivate_replication_control(run_id: str) -> None:
    _CONTROL_PLANE.deactivate(run_id)


def replication_control_state(run_id: str) -> dict[str, Any]:
    _validate_run_id(run_id)
    return _CONTROL_PLANE.state(run_id)


def resolve_replication_permission(
    run_id: str,
    request_id: str,
    *,
    decision: str,
    option_id: str | None = None,
) -> dict[str, Any]:
    _validate_run_id(run_id)
    if not request_id.startswith("perm_") or not request_id[5:].isalnum():
        raise ValueError("invalid permission request id")
    return _CONTROL_PLANE.resolve(
        run_id,
        request_id,
        decision=decision,
        option_id=option_id,
    )


def cancel_replication_run(run_id: str) -> bool:
    _validate_run_id(run_id)
    return _CONTROL_PLANE.cancel(run_id)


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
        run_id = workspace_path.name if workspace_path.name.startswith("run_") else ""

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
                        payload={
                            "session_id": session_id,
                            "update_kind": update_kind,
                            "update": payload,
                        },
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
                option_payloads = tuple(_jsonable(option) for option in options)
                request_id = f"perm_{uuid4().hex[:12]}"
                title = str(
                    call_payload.get("title")
                    or call_payload.get("name")
                    or "Tool permission"
                )

                selected: object | None = None
                if (
                    policy is PermissionPolicy.INTERACTIVE
                    and run_id
                    and _CONTROL_PLANE.interactive(run_id)
                ):
                    await queue.put(
                        ReplicationEvent(
                            kind="permission",
                            title=title,
                            detail="Waiting for an explicit allow-once or reject decision.",
                            status="review",
                            payload={
                                "request_id": request_id,
                                "session_id": session_id,
                                "tool_call": call_payload,
                                "options": list(option_payloads),
                                "decision": "pending",
                                "policy": policy.value,
                            },
                        ).to_dict()
                    )
                    selected_id = await _CONTROL_PLANE.request(
                        run_id,
                        request_id,
                        option_payloads,
                    )
                    selected = _select_allow_once_by_id(options, selected_id)
                elif policy is PermissionPolicy.ALLOW_ONCE:
                    selected = _select_allow_once(options)

                decision = "selected" if selected is not None else "cancelled"
                await queue.put(
                    ReplicationEvent(
                        kind="permission",
                        title=title,
                        detail=(
                            "Allowed once by explicit Veritas policy or human approval."
                            if selected is not None
                            else "Denied by Veritas replication policy or reviewer decision."
                        ),
                        status="success" if selected is not None else "blocked",
                        payload={
                            "request_id": request_id,
                            "session_id": session_id,
                            "tool_call": call_payload,
                            "options": list(option_payloads),
                            "decision": decision,
                            "policy": policy.value,
                            "selected_option_id": getattr(selected, "option_id", None),
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
            detail="Run-specific workspace prepared.",
            status="running",
            payload={
                "agent": self.agent.name,
                "permission_policy": self.permission_policy.value,
                "workspace_scope": "run_specific",
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
                    prompt=[TextContentBlock(type="text", text=prompt.strip())],
                )
            )

            while not prompt_task.done() or not queue.empty():
                if run_id and _CONTROL_PLANE.cancelled(run_id):
                    prompt_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await prompt_task
                    while not queue.empty():
                        yield queue.get_nowait()
                    yield ReplicationEvent(
                        kind="turn_cancelled",
                        title="Replication turn cancelled",
                        detail="The host requested cancellation; the agent process is being terminated.",
                        status="review",
                        payload={"session_id": session.session_id},
                    ).to_dict()
                    raise ReplicationCancelledError("replication run cancelled by user")
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


def _select_allow_once_by_id(options: Iterable[object], option_id: str | None) -> object | None:
    if not option_id:
        return None
    for option in options:
        if (
            getattr(option, "kind", None) == "allow_once"
            and getattr(option, "option_id", None) == option_id
        ):
            return option
    return None


def _resolve_future(future: asyncio.Future[str | None], value: str | None) -> None:
    if not future.done():
        future.set_result(value)


def _validate_run_id(run_id: str) -> None:
    if not isinstance(run_id, str) or not run_id.startswith("run_") or not run_id[4:].isalnum():
        raise ValueError("invalid replication run id")


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
