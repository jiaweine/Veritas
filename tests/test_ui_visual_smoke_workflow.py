from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ui_visual_smoke_workflow_captures_product_surfaces() -> None:
    workflow = (ROOT / ".github/workflows/ui-visual-smoke.yml").read_text(encoding="utf-8")
    script = (ROOT / "scripts/smoke_harness_browser.py").read_text(encoding="utf-8")
    finding_replication = (ROOT / "scripts/smoke_finding_replication_browser.py").read_text(
        encoding="utf-8"
    )
    diff_smoke = (ROOT / "scripts/smoke_replication_diff_browser.py").read_text(encoding="utf-8")
    diff_agent = (ROOT / "scripts/browser_replication_diff_agent.py").read_text(encoding="utf-8")

    assert "python -m playwright install --with-deps chromium" in workflow
    assert "python scripts/smoke_harness_browser.py" in workflow
    assert "python scripts/smoke_finding_replication_browser.py" in workflow
    assert "python scripts/smoke_replication_diff_browser.py" in workflow
    assert "scripts/browser_replication_diff_agent.py" in workflow
    assert "--port 8766" in workflow
    assert 'VERITAS_REPLICATION_AGENT_NAME="Browser diff fixture agent"' in workflow
    assert "actions/upload-artifact@" in workflow
    assert "veritas-ui-screenshots" in workflow

    assert '"audit-workspace.png"' in script
    assert '"claim-graph.png"' in script
    assert '"finding-graph-roundtrip.png"' in script
    assert '"audit-notes.png"' in script
    assert '"replication-workspace.png"' in script
    assert '"runs-workspace.png"' in script
    assert '"audit-mobile.png"' in script
    assert "[data-audit-harness='true']" in script
    assert "[data-reproduction-surface='true']" in script
    assert "[data-reference-analysis='true']" in script
    assert "[data-reference-claim-graph='true']" in script
    assert "[data-cg-field='beta']" in script
    assert "[data-cg-detail-panel='true']" in script
    assert "[data-cg-detail-action='source']" in script
    assert "[data-cg-detail-action='findings']" in script
    assert "[data-cg-detail-source='true']" in script
    assert "[data-fn-graph='true']" in script
    assert "[data-ref-field='beta'].is-linked-selection" in script
    assert "[data-ref-field='p_value'].is-linked-selection" in script
    assert "[data-runs-surface='true']" in script
    assert '/audit row="Minimum wage" table=4 page=1' in script
    assert 'consensus.get("beta") != "-0.021"' in script
    assert 'p_value="0.010"' in script
    assert 'result.get("status") != "contradiction"' in script
    assert 'check.get("check_id") == "p_value"' in script
    assert 'page.goto("about:blank", wait_until="load")' in script
    assert "Legacy nested project rail is still visible" in script
    assert "Evidence Inspector tabs remain visible while Notes is active" in script
    assert "Notes header timestamp did not refresh after save" in script
    assert "Notes did not persist through the real browser save path" in script

    assert "_seed_contradiction_audit" in finding_replication
    assert "[data-fn-reproduce='true']" in finding_replication
    assert "[data-rep-finding-context='true']" in finding_replication
    assert "[data-rep-return-finding='true']" in finding_replication
    assert '"finding-replication-context.png"' in finding_replication
    assert '"finding-replication-return.png"' in finding_replication
    assert "does not by itself verify or resolve this finding" in finding_replication
    assert "do not treat a successful code run as resolving the finding" in finding_replication

    assert '"replication-diff.png"' in diff_smoke
    assert '"replication-diff-unavailable.png"' in diff_smoke
    assert '"replication-diff-truncated.png"' in diff_smoke
    assert "[data-rep-diff-available='true']" in diff_smoke
    assert "[data-rep-diff-available='false']" in diff_smoke
    assert "[data-rep-diff-reason='current_too_large']" in diff_smoke
    assert 'binary.json().get("diff_reason") != "current_binary"' in diff_smoke
    assert 'large_payload.get("diff_reason") != "current_too_large"' in diff_smoke
    assert "source.content != original" in diff_smoke
    assert "workspace mutation" in diff_agent
    assert "binary.bin" in diff_agent
    assert "large.txt" in diff_agent


def test_reference_workbench_uses_live_backend_contracts() -> None:
    script = (ROOT / "src/veritas/harness/static/reference-workbench.js").read_text(encoding="utf-8")
    evidence = (ROOT / "src/veritas/harness/static/reference-evidence-preview.js").read_text(
        encoding="utf-8"
    )
    graph = (ROOT / "src/veritas/harness/static/claim-graph.js").read_text(encoding="utf-8")
    annotations = (ROOT / "src/veritas/harness/static/claim-graph-annotations.js").read_text(
        encoding="utf-8"
    )
    finding_navigation = (ROOT / "src/veritas/harness/static/finding-navigation.js").read_text(
        encoding="utf-8"
    )
    styles = (ROOT / "src/veritas/harness/static/reference-workbench.css").read_text(encoding="utf-8")
    surfaces = (ROOT / "src/veritas/harness/static/reference-surfaces.css").read_text(encoding="utf-8")
    graph_styles = (ROOT / "src/veritas/harness/static/claim-graph.css").read_text(encoding="utf-8")
    finding_styles = (ROOT / "src/veritas/harness/static/finding-navigation.css").read_text(
        encoding="utf-8"
    )
    shell = (ROOT / "src/veritas/harness/static/index.html").read_text(encoding="utf-8")

    assert 'json(`/api/v1/audit-pages?limit=${REFERENCE_AUDIT_LIMIT}`)' in script
    assert 'json(`/api/v1/run-pages?limit=${REFERENCE_RUN_LIMIT}`)' in script
    assert 'json("/api/v1/audits")' not in script
    assert 'json("/api/v1/runs")' not in script
    assert "/api/v1/audits/${encodeURIComponent(auditId)}" in script
    assert "latest_result" in script
    assert "result.consensus" in script
    assert 'data-reference-analysis="true"' in script
    assert "/api/v1/audits/${encodeURIComponent(auditId)}" in evidence
    assert "result.fields" in evidence
    assert "data-reference-evidence-preview" in evidence
    assert 'data-ref-field="beta"' in evidence
    assert "veritas:evidence-field" in evidence

    claim_endpoint = "/api/v1/audits/${encodeURIComponent(auditId)}/claim-graph"
    assert claim_endpoint in graph
    assert "latest_result" not in graph
    assert "result.consensus" not in graph
    assert "result.checks" not in graph
    assert "result.findings" not in graph
    assert "data-reference-claim-graph" in graph
    assert "data-cg-detail-panel" in graph
    assert "data-cg-detail-action" in graph
    assert "data-cg-persisted-edge" in graph
    assert "No publication claim identity bound" in graph
    assert claim_endpoint in annotations
    assert "dataset.cgFindingId" in annotations
    assert "annotation.graph_edge !== false" in annotations
    assert "Detector annotations never become ClaimEdges" in annotations
    assert "veritas:finding-select" in annotations

    assert "/api/v1/audits/${encodeURIComponent(auditId)}" in finding_navigation
    assert "data-fn-finding-id" in finding_navigation
    assert "data-fn-reproduce" in finding_navigation
    assert "veritas.replication.context.v1" in finding_navigation
    assert "veritas.finding.focus.v1" in finding_navigation
    assert "veritas:claim-finding" in finding_navigation
    assert ".audit-harness .ah-left" in styles
    assert "display: none !important" in styles
    assert "ref-evidence-preview" in surfaces
    assert "data-reproduction-surface" in surfaces
    assert ".claim-graph" in graph_styles
    assert ".cg-detail" in graph_styles
    assert ".is-linked-selection" in graph_styles
    assert ".fn-finding-row" in finding_styles
    assert ".is-linked-finding" in finding_styles
    assert "/static/reference-workbench.css" in shell
    assert "/static/reference-workbench.js" in shell
    assert "/static/reference-surfaces.css" in shell
    assert "/static/reference-evidence-preview.js" in shell
    assert "/static/claim-graph.css" in shell
    assert "/static/claim-graph.js" in shell
    assert "/static/claim-graph-annotations.js" in shell
    assert "/static/finding-navigation.css" in shell
    assert "/static/finding-navigation.js" in shell


def test_notes_workspace_has_explicit_visual_state_contracts() -> None:
    script = (ROOT / "src/veritas/harness/static/audit-notes.js").read_text(encoding="utf-8")
    styles = (ROOT / "src/veritas/harness/static/audit-notes.css").read_text(encoding="utf-8")

    assert 'id="ah-notes-saved-at"' in script
    assert 'savedAt.textContent = formatTimestamp(notesState.serverUpdatedAt)' in script
    assert ".ah-right.ah-notes-active .ah-tabs" in styles
    assert "display: none" in styles


def test_replication_diff_ui_discloses_bounded_states() -> None:
    script = (ROOT / "src/veritas/harness/static/reproduction-diff-state.js").read_text(
        encoding="utf-8"
    )
    styles = (ROOT / "src/veritas/harness/static/reproduction-diff-state.css").read_text(
        encoding="utf-8"
    )
    shell = (ROOT / "src/veritas/harness/static/index.html").read_text(encoding="utf-8")

    assert "Diff unavailable" in script
    assert "current_too_large" in script
    assert "baseline_too_large" in script
    assert "diff_too_large" in script
    assert "current_binary" in script
    assert "baseline_binary" in script
    assert "No partial diff" not in script
    assert "will not present a partial diff as complete" in script
    assert "generated outputs remain untrusted" in script
    assert "data-rep-diff-state" in script or "repDiffState" in script
    assert "data-rep-diff-rendered" in script or "repDiffRendered" in script
    assert "Preview capped at" in script
    assert "/api/v1/runs/${encodeURIComponent(runId)}/workspace/file?path=" in script
    assert ".rep-diff-state.unavailable" in styles
    assert ".rep-diff-line.add" in styles
    assert ".rep-diff-line.remove" in styles
    assert "/static/reproduction-diff-state.css" in shell
    assert "/static/reproduction-diff-state.js" in shell


def test_mobile_workflow_syntax_checks_all_workbench_modules() -> None:
    workflow = (ROOT / ".github/workflows/mobile.yml").read_text(encoding="utf-8")
    expected_modules = {
        "app.js",
        "audit-harness.js",
        "audit-harness-product.js",
        "audit-notes.js",
        "reproduction.js",
        "reproduction-diff-state.js",
        "runs.js",
        "settings.js",
        "benchmarks.js",
        "reference-workbench.js",
        "reference-evidence-preview.js",
        "claim-graph.js",
        "claim-graph-annotations.js",
        "finding-navigation.js",
    }

    for module in expected_modules:
        assert f"node --check ../src/veritas/harness/static/{module}" in workflow
