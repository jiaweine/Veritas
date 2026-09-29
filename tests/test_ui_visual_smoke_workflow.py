from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ui_visual_smoke_workflow_captures_product_surfaces() -> None:
    workflow = (ROOT / ".github/workflows/ui-visual-smoke.yml").read_text(encoding="utf-8")
    script = (ROOT / "scripts/smoke_harness_browser.py").read_text(encoding="utf-8")

    assert "python -m playwright install --with-deps chromium" in workflow
    assert "python scripts/smoke_harness_browser.py" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "veritas-ui-screenshots" in workflow

    assert '"audit-workspace.png"' in script
    assert '"audit-notes.png"' in script
    assert '"replication-workspace.png"' in script
    assert '"runs-workspace.png"' in script
    assert '"audit-mobile.png"' in script
    assert "[data-audit-harness='true']" in script
    assert "[data-reproduction-surface='true']" in script
    assert "[data-reference-analysis='true']" in script
    assert "[data-runs-surface='true']" in script
    assert '/audit row="Minimum wage" table=4 page=1' in script
    assert 'consensus.get("beta") != "-0.021"' in script
    assert 'page.goto("about:blank", wait_until="load")' in script
    assert "Legacy nested project rail is still visible" in script
    assert "Evidence Inspector tabs remain visible while Notes is active" in script
    assert "Notes header timestamp did not refresh after save" in script
    assert "Notes did not persist through the real browser save path" in script


def test_reference_workbench_uses_live_backend_contracts() -> None:
    script = (ROOT / "src/veritas/harness/static/reference-workbench.js").read_text(encoding="utf-8")
    styles = (ROOT / "src/veritas/harness/static/reference-workbench.css").read_text(encoding="utf-8")
    shell = (ROOT / "src/veritas/harness/static/index.html").read_text(encoding="utf-8")

    assert 'json("/api/v1/audits")' in script
    assert 'json("/api/v1/runs")' in script
    assert "/api/v1/audits/${encodeURIComponent(auditId)}" in script
    assert "latest_result" in script
    assert "result.consensus" in script
    assert 'data-reference-analysis="true"' in script
    assert ".audit-harness .ah-left" in styles
    assert "display: none !important" in styles
    assert "/static/reference-workbench.css" in shell
    assert "/static/reference-workbench.js" in shell


def test_notes_workspace_has_explicit_visual_state_contracts() -> None:
    script = (ROOT / "src/veritas/harness/static/audit-notes.js").read_text(encoding="utf-8")
    styles = (ROOT / "src/veritas/harness/static/audit-notes.css").read_text(encoding="utf-8")

    assert 'id="ah-notes-saved-at"' in script
    assert 'savedAt.textContent = formatTimestamp(notesState.serverUpdatedAt)' in script
    assert ".ah-right.ah-notes-active .ah-tabs" in styles
    assert "display: none" in styles


def test_mobile_workflow_syntax_checks_all_workbench_modules() -> None:
    workflow = (ROOT / ".github/workflows/mobile.yml").read_text(encoding="utf-8")
    expected_modules = {
        "app.js",
        "audit-harness.js",
        "audit-harness-product.js",
        "audit-notes.js",
        "reproduction.js",
        "runs.js",
        "settings.js",
        "benchmarks.js",
        "reference-workbench.js",
    }

    for module in expected_modules:
        assert f"node --check ../src/veritas/harness/static/{module}" in workflow
