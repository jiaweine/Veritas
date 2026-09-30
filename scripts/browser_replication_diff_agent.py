from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from uuid import uuid4

from acp import Agent, InitializeResponse, NewSessionResponse, PromptResponse, run_agent
from acp.interfaces import Client
from acp.schema import AgentMessageChunk, TextContentBlock


class BrowserReplicationDiffAgent(Agent):
    """Deterministic ACP fixture used only by the browser visual-smoke harness."""

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

    async def prompt(
        self,
        session_id: str,
        prompt: list[object],
        **_: Any,
    ) -> PromptResponse:
        workspace = self._workspaces[session_id]
        attachment = next((workspace / "attachments").glob("*/*.py"))
        attachment.chmod(0o644)
        attachment.write_text("print('workspace mutation')\n", encoding="utf-8")

        outputs = workspace / "outputs"
        outputs.mkdir(exist_ok=True)
        (outputs / "result.txt").write_text(
            "estimate=-0.021\nstandard_error=0.026\nstatus=matched\n",
            encoding="utf-8",
        )
        (outputs / "binary.bin").write_bytes(b"\x00\x01\x02browser-diff-fixture")
        (outputs / "large.txt").write_text(
            "bounded-preview-fixture-line\n" * 12_000,
            encoding="utf-8",
        )

        if self._client is not None:
            await self._client.session_update(
                session_id=session_id,
                update=AgentMessageChunk(
                    session_update="agent_message_chunk",
                    content=TextContentBlock(
                        type="text",
                        text=(
                            "Created deterministic reproduction outputs and mutated the staged "
                            "attachment copy for workspace-diff browser acceptance."
                        ),
                    ),
                ),
            )
        return PromptResponse(stop_reason="end_turn")


if __name__ == "__main__":
    asyncio.run(run_agent(BrowserReplicationDiffAgent()))
