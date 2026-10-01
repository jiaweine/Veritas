from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_interactive_permission_path_has_real_browser_acceptance() -> None:
    agent = (ROOT / "scripts/browser_replication_permission_agent.py").read_text(encoding="utf-8")
    browser = (ROOT / "scripts/smoke_replication_permission_browser.py").read_text(
        encoding="utf-8"
    )
    workflow = (
        ROOT / ".github/workflows/replication-permission-ui-smoke.yml"
    ).read_text(encoding="utf-8")
    reproduction = (
        ROOT / "src/veritas/harness/static/reproduction.js"
    ).read_text(encoding="utf-8")
    web = (ROOT / "src/veritas/harness/web_core.py").read_text(encoding="utf-8")

    assert 'kind="allow_once"' in agent
    assert 'kind="allow_always"' in agent
    assert 'kind="reject_once"' in agent
    assert "request_permission(" in agent
    assert "permission-allowed.txt" in agent

    assert ".rep-permission.pending" in browser
    assert "replication-permission-pending.png" in browser
    assert "replication-permission-allowed.png" in browser
    assert "replication-permission-rejected.png" in browser
    assert 'decision="allow_once"' in browser
    assert 'decision="reject"' in browser
    assert "pending_permissions" in browser
    assert "selected_option_id" in browser
    assert "outputs/permission-allowed.txt" in browser

    assert 'item.kind === "allow_once"' in reproduction
    assert 'data-permission-decision="reject"' in reproduction
    assert 'data-permission-decision="allow_once"' in reproduction
    assert 'data-permission-decision="allow_always"' not in reproduction
    assert "/permissions/${encodeURIComponent(requestId)}" in reproduction

    assert '@app.get("/api/v1/replication/runs/{run_id}/control")' in web
    assert '@app.post("/api/v1/replication/runs/{run_id}/permissions/{request_id}")' in web
    assert "resolve_replication_permission(" in web

    assert 'VERITAS_REPLICATION_PERMISSION_POLICY="interactive"' in workflow
    assert "browser_replication_permission_agent.py" in workflow
    assert "smoke_replication_permission_browser.py" in workflow
    assert "actions/upload-artifact@v7" in workflow
