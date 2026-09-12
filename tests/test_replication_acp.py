from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

from veritas.replication import AcpTurnRunner, AgentCommand, PermissionPolicy
from veritas.replication.acp import _select_allow_once


def test_agent_command_forwards_only_explicit_environment() -> None:
    source = {
        "PATH": "/bin",
        "HOME": "/home/test",
        "OPENAI_API_KEY": "secret",
        "UNRELATED_SECRET": "nope",
    }
    command = AgentCommand(
        argv=("agent",),
        forward_env=("OPENAI_API_KEY",),
        env=(("INITIAL_AGENT_MODE", "agent"),),
    )

    result = command.process_env(source)

    assert result == {
        "PATH": "/bin",
        "HOME": "/home/test",
        "OPENAI_API_KEY": "secret",
        "INITIAL_AGENT_MODE": "agent",
    }
    assert "UNRELATED_SECRET" not in result


def test_allow_once_policy_never_upgrades_to_allow_always() -> None:
    options = [
        SimpleNamespace(kind="allow_always", option_id="forever"),
        SimpleNamespace(kind="reject_once", option_id="reject"),
    ]
    assert _select_allow_once(options) is None

    allow_once = SimpleNamespace(kind="allow_once", option_id="once")
    assert _select_allow_once([options[0], allow_once]) is allow_once


def test_acp_turn_streams_real_agent_process(tmp_path: Path) -> None:
    agent_script = tmp_path / "echo_agent.py"
    agent_script.write_text(
        '''from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from acp import Agent, InitializeResponse, NewSessionResponse, PromptResponse, run_agent
from acp.interfaces import Client
from acp.schema import AgentMessageChunk, TextContentBlock


class EchoAgent(Agent):
    def on_connect(self, conn: Client) -> None:
        self._conn = conn

    async def initialize(self, protocol_version: int, **_: Any) -> InitializeResponse:
        return InitializeResponse(protocol_version=protocol_version)

    async def new_session(self, cwd: str, **_: Any) -> NewSessionResponse:
        self._cwd = cwd
        return NewSessionResponse(session_id=uuid4().hex)

    async def prompt(self, session_id: str, prompt: list[object], **_: Any) -> PromptResponse:
        text = getattr(prompt[0], "text", "")
        message = AgentMessageChunk(
            session_update="agent_message_chunk",
            content=TextContentBlock(type="text", text=f"cwd={self._cwd}; prompt={text}"),
        )
        await self._conn.session_update(session_id=session_id, update=message)
        return PromptResponse(stop_reason="end_turn")


if __name__ == "__main__":
    asyncio.run(run_agent(EchoAgent()))
''',
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    runner = AcpTurnRunner(
        AgentCommand(argv=(sys.executable, str(agent_script)), name="fixture agent"),
        permission_policy=PermissionPolicy.DENY,
    )

    events = asyncio.run(runner.run_turn(workspace, "check the project"))

    assert events[0]["kind"] == "agent"
    updates = [event for event in events if event["kind"] == "agent_update"]
    assert len(updates) == 1
    assert "prompt=check the project" in updates[0]["detail"]
    assert str(workspace.resolve()) in updates[0]["detail"]
    assert events[-1]["kind"] == "turn_completed"
    assert events[-1]["payload"]["stop_reason"] == "end_turn"
