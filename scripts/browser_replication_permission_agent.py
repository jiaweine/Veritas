from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from uuid import uuid4

from acp import Agent, InitializeResponse, NewSessionResponse, PromptResponse, run_agent
from acp.interfaces import Client
from acp.schema import AgentMessageChunk, PermissionOption, TextContentBlock, ToolCallUpdate


class BrowserReplicationPermissionAgent(Agent):
    """Deterministic ACP fixture for real-browser human permission acceptance."""

    def __init__(self) -> None:
        self._client: Client | None = None
        self._workspaces: dict[str, Path] = {}

    def on_connect(self, conn: Client) -> None:
        self._client = conn

    async def initialize(self, protocol_version: int, **_: Any) -> InitializeResponse:
        return InitializeResponse(protocol_version=protocol_version)

    async def new_session(self, cwd: str, **_: Any) -> NewSessionResponse:
        session_id = uuid4().hex
        self._workspaces[session_id] = Path(cwd)
        return NewSessionResponse(session_id=session_id)

    async def _message(self, session_id: str, text: str) -> None:
        if self._client is None:
            return
        await self._client.session_update(
            session_id=session_id,
            update=AgentMessageChunk(
                session_update="agent_message_chunk",
                content=TextContentBlock(type="text", text=text),
            ),
        )

    async def prompt(
        self,
        session_id: str,
        prompt: list[object],
        **_: Any,
    ) -> PromptResponse:
        if self._client is None:
            raise RuntimeError("ACP client is not connected")

        workspace = self._workspaces[session_id]
        tool_call = ToolCallUpdate(
            tool_call_id=f"permission-fixture-{session_id[:8]}",
            kind="execute",
            status="pending",
            title="Write synthetic reproduction checkpoint",
            raw_input={
                "command": "python replicate.py --write-checkpoint",
                "scope": "browser-acceptance",
            },
        )
        options = [
            PermissionOption(option_id="once", name="Allow once", kind="allow_once"),
            PermissionOption(
                option_id="always",
                name="Always allow this operation",
                kind="allow_always",
            ),
            PermissionOption(option_id="reject", name="Reject", kind="reject_once"),
        ]

        await self._message(
            session_id,
            "A synthetic write-like operation requires an explicit human decision before it can run.",
        )
        response = await self._client.request_permission(
            session_id=session_id,
            tool_call=tool_call,
            options=options,
        )
        outcome = response.outcome
        selected = getattr(outcome, "outcome", None) == "selected"
        option_id = getattr(outcome, "option_id", None)

        if selected and option_id == "once":
            outputs = workspace / "outputs"
            outputs.mkdir(exist_ok=True)
            (outputs / "permission-allowed.txt").write_text(
                "decision=allow_once\noperation=synthetic_checkpoint\n",
                encoding="utf-8",
            )
            await self._message(
                session_id,
                "Human approved this operation once. The synthetic checkpoint was created and the turn resumed.",
            )
        else:
            await self._message(
                session_id,
                "Human rejected the operation. No synthetic checkpoint was created; the turn resumed without it.",
            )

        return PromptResponse(stop_reason="end_turn")


if __name__ == "__main__":
    asyncio.run(run_agent(BrowserReplicationPermissionAgent()))
