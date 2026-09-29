from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

from veritas.harness.web import create_app
from veritas.replication import (
    AcpTurnRunner,
    AgentCommand,
    PermissionPolicy,
    activate_replication_control,
    deactivate_replication_control,
    replication_control_state,
    resolve_replication_permission,
)


def _make_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((60, 72), "Synthetic replication workspace paper", fontsize=14)
    payload = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return payload


def test_interactive_permission_requires_offered_allow_once(tmp_path: Path) -> None:
    agent_script = tmp_path / "permission_agent.py"
    agent_script.write_text(
        '''from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from acp import Agent, InitializeResponse, NewSessionResponse, PromptResponse, run_agent
from acp.interfaces import Client
from acp.schema import AgentMessageChunk, PermissionOption, TextContentBlock, ToolCallUpdate


class PermissionAgent(Agent):
    def on_connect(self, conn: Client) -> None:
        self._conn = conn

    async def initialize(self, protocol_version: int, **_: Any) -> InitializeResponse:
        return InitializeResponse(protocol_version=protocol_version)

    async def new_session(self, cwd: str, **_: Any) -> NewSessionResponse:
        return NewSessionResponse(session_id=uuid4().hex)

    async def prompt(self, session_id: str, prompt: list[object], **_: Any) -> PromptResponse:
        permission = await self._conn.request_permission(
            session_id=session_id,
            tool_call=ToolCallUpdate(tool_call_id="call-1", title="Run project tests"),
            options=[
                PermissionOption(option_id="forever", name="Always allow", kind="allow_always"),
                PermissionOption(option_id="once", name="Allow once", kind="allow_once"),
                PermissionOption(option_id="reject", name="Reject", kind="reject_once"),
            ],
        )
        selected = getattr(permission.outcome, "option_id", "cancelled")
        await self._conn.session_update(
            session_id=session_id,
            update=AgentMessageChunk(
                session_update="agent_message_chunk",
                content=TextContentBlock(type="text", text=f"permission={selected}"),
            ),
        )
        return PromptResponse(stop_reason="end_turn")


if __name__ == "__main__":
    asyncio.run(run_agent(PermissionAgent()))
''',
        encoding="utf-8",
    )
    workspace = tmp_path / "run_fixture1"
    workspace.mkdir()
    runner = AcpTurnRunner(
        AgentCommand(argv=(sys.executable, str(agent_script)), name="permission fixture"),
        permission_policy=PermissionPolicy.INTERACTIVE,
    )

    async def scenario() -> list[dict[str, object]]:
        events: list[dict[str, object]] = []
        activate_replication_control("run_fixture1", interactive_permissions=True)
        try:
            async for event in runner.stream_turn(workspace, "run the tests"):
                events.append(event)
                payload = event.get("payload") or {}
                if event.get("kind") == "permission" and payload.get("decision") == "pending":
                    request_id = str(payload["request_id"])
                    with pytest.raises(ValueError, match="not an offered allow_once"):
                        resolve_replication_permission(
                            "run_fixture1",
                            request_id,
                            decision="allow_once",
                            option_id="forever",
                        )
                    resolve_replication_permission(
                        "run_fixture1",
                        request_id,
                        decision="allow_once",
                        option_id="once",
                    )
        finally:
            deactivate_replication_control("run_fixture1")
        return events

    events = asyncio.run(scenario())
    permissions = [event for event in events if event["kind"] == "permission"]
    assert [event["payload"]["decision"] for event in permissions] == ["pending", "selected"]
    assert permissions[-1]["payload"]["selected_option_id"] == "once"
    messages = [event for event in events if event["kind"] == "agent_update"]
    assert any("permission=once" in event["detail"] for event in messages)
    assert replication_control_state("run_fixture1")["active"] is False


def test_workspace_api_uses_filesystem_truth_and_rejects_escape(tmp_path, monkeypatch) -> None:
    artifact_bytes = b'print("original")\n'
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")

    class FakeRunner:
        def __init__(self, agent, *, permission_policy) -> None:
            self.agent = agent
            self.permission_policy = permission_policy

        async def stream_turn(self, workspace, prompt):
            attachment = next((workspace / "attachments").glob("*/*.py"))
            attachment.chmod(0o644)
            attachment.write_text('print("changed")\n', encoding="utf-8")
            (workspace / "generated.txt").write_text("result=42\n", encoding="utf-8")
            (workspace / "escape-link").symlink_to(outside)
            yield {
                "event_id": "rep_evt_workspace",
                "kind": "agent_update",
                "title": "agent_message_chunk",
                "detail": "finished",
                "status": "info",
                "payload": {"update_kind": "agent_message_chunk"},
                "created_at": "2026-09-29T00:00:00Z",
            }

    monkeypatch.setenv("VERITAS_REPLICATION_AGENT", "fake-agent --stdio")
    monkeypatch.setenv("VERITAS_REPLICATION_AGENT_NAME", "Workspace fixture")
    monkeypatch.setenv("VERITAS_REPLICATION_PERMISSION_POLICY", "interactive")
    monkeypatch.setattr("veritas.harness.service.AcpTurnRunner", FakeRunner)

    client = TestClient(create_app(tmp_path / "data"))
    caps = client.get("/api/v1/capabilities").json()["replication"]
    assert caps["permission_policy"] == "interactive"
    assert caps["interactive_approval_supported"] is True
    assert caps["interactive_approval_enabled"] is True
    assert caps["workspace_inspector"] is True
    assert caps["workspace_diff"] is True
    assert caps["cancellation_supported"] is True

    created = client.post(
        "/api/v1/audits",
        data={"title": "Workspace paper"},
        files={"file": ("paper.pdf", _make_pdf(), "application/pdf")},
    ).json()
    audit_id = created["audit_id"]
    attached = client.post(
        f"/api/v1/audits/{audit_id}/attachments",
        files={"file": ("analysis.py", artifact_bytes, "text/x-python")},
    ).json()

    response = client.post(
        f"/api/v1/audits/{audit_id}/replication",
        json={"prompt": "reproduce the result"},
    )
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines() if line]
    run_id = events[0]["payload"]["run_id"]

    control = client.get(f"/api/v1/replication/runs/{run_id}/control")
    assert control.status_code == 200
    assert control.json()["active"] is False

    snapshot_response = client.get(f"/api/v1/runs/{run_id}/workspace")
    assert snapshot_response.status_code == 200
    snapshot = snapshot_response.json()
    by_path = {item["path"]: item for item in snapshot["files"]}
    attachment_path = f'attachments/{attached["attachment_id"]}/analysis.py'
    assert by_path["paper.pdf"]["change"] == "original"
    assert by_path[attachment_path]["change"] == "modified"
    assert by_path[attachment_path]["immutable_input"] is True
    assert by_path["generated.txt"]["change"] == "created"
    assert by_path["escape-link"]["change"] == "unsafe_link"
    assert snapshot["staged_inputs_unchanged"] is False
    assert attachment_path in snapshot["staged_input_drift"]

    generated = client.get(
        f"/api/v1/runs/{run_id}/workspace/file",
        params={"path": "generated.txt"},
    )
    assert generated.status_code == 200
    assert generated.json()["content"] == "result=42\n"
    assert generated.json()["change"] == "created"

    modified = client.get(
        f"/api/v1/runs/{run_id}/workspace/file",
        params={"path": attachment_path},
    )
    assert modified.status_code == 200
    assert '-print("original")' in modified.json()["diff"]
    assert '+print("changed")' in modified.json()["diff"]

    assert client.get(
        f"/api/v1/runs/{run_id}/workspace/file",
        params={"path": "../audit.json"},
    ).status_code == 422
    assert client.get(
        f"/api/v1/runs/{run_id}/workspace/file",
        params={"path": "escape-link"},
    ).status_code == 422


def test_replication_workspace_ui_contract() -> None:
    root = Path(__file__).parents[1]
    javascript = (root / "src/veritas/harness/static/reproduction.js").read_text(encoding="utf-8")
    css = (root / "src/veritas/harness/static/reproduction.css").read_text(encoding="utf-8")

    for contract in (
        "rep-grid",
        "rep-left",
        "rep-center",
        "rep-right",
        "data-permission-decision",
        "Allow once",
        "/workspace/file?path=",
        "/cancel",
        "agent-owned",
    ):
        assert contract in javascript or contract in css
    assert "client-supplied executable command" not in javascript
    assert "allow_always" not in javascript
