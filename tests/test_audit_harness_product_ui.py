from __future__ import annotations

from fastapi.testclient import TestClient

from veritas.harness.web import create_app


def test_audit_harness_product_assets_are_wired_into_shell(tmp_path) -> None:
    client = TestClient(create_app(tmp_path))

    shell = client.get("/")
    assert shell.status_code == 200
    assert "/static/audit-harness-product.css" in shell.text
    assert "/static/audit-harness-product.js" in shell.text
    assert "/static/reference-workbench.css" in shell.text
    assert "/static/reference-workbench.js" in shell.text
    assert "/static/reference-surfaces.css" in shell.text
    assert "/static/reference-evidence-preview.js" in shell.text
    assert "/static/claim-graph.css" in shell.text
    assert "/static/claim-graph.js" in shell.text
    assert "/static/mobile-polish.css" in shell.text

    script = client.get("/static/audit-harness-product.js")
    assert script.status_code == 200
    assert "veritas:audit-harness:layout:v1" in script.text
    assert "veritas:audit-harness:session:v1:" in script.text
    assert "veritas:audit-harness:draft:v1:" in script.text
    assert "data-ah-split" in script.text
    assert "/api/v1/runs/" in script.text
    assert "data-ah-context-command" in script.text

    styles = client.get("/static/audit-harness-product.css")
    assert styles.status_code == 200
    assert "--ah-left-width" in styles.text
    assert ".ah-splitter" in styles.text
    assert ".ah-run-inspector" in styles.text

    reference_script = client.get("/static/reference-workbench.js")
    assert reference_script.status_code == 200
    assert 'json("/api/v1/audits")' in reference_script.text
    assert 'json("/api/v1/runs")' in reference_script.text
    assert "latest_result" in reference_script.text
    assert "data-reference-analysis" in reference_script.text

    evidence_script = client.get("/static/reference-evidence-preview.js")
    assert evidence_script.status_code == 200
    assert "/api/v1/audits/${encodeURIComponent(auditId)}" in evidence_script.text
    assert "result.fields" in evidence_script.text
    assert "data-reference-evidence-preview" in evidence_script.text

    claim_script = client.get("/static/claim-graph.js")
    assert claim_script.status_code == 200
    assert "data-reference-claim-graph" in claim_script.text
    assert "data-cg-detail-panel" in claim_script.text
    assert "data-cg-detail-action" in claim_script.text
    assert "aria-current" in claim_script.text
    assert "veritas:evidence-field" in claim_script.text

    reference_styles = client.get("/static/reference-workbench.css")
    assert reference_styles.status_code == 200
    assert "reference-audit-active" in reference_styles.text
    assert "ref-selected-analysis" in reference_styles.text
    assert "reference-runs-active" in reference_styles.text

    surface_styles = client.get("/static/reference-surfaces.css")
    assert surface_styles.status_code == 200
    assert "ref-evidence-preview" in surface_styles.text
    assert "data-reproduction-surface" in surface_styles.text

    mobile_styles = client.get("/static/mobile-polish.css")
    assert mobile_styles.status_code == 200
    assert ".ah-header-actions" in mobile_styles.text
    assert ".ah-event > .ah-badge" in mobile_styles.text

    service_worker = client.get("/sw.js")
    assert service_worker.status_code == 200
    assert 'const CACHE = "veritas-shell-v20"' in service_worker.text
    assert "/static/audit-harness-product.css" in service_worker.text
    assert "/static/audit-harness-product.js" in service_worker.text
    assert "/static/reference-workbench.css" in service_worker.text
    assert "/static/reference-workbench.js" in service_worker.text
    assert "/static/reference-surfaces.css" in service_worker.text
    assert "/static/reference-evidence-preview.js" in service_worker.text
    assert "/static/claim-graph.css" in service_worker.text
    assert "/static/claim-graph.js" in service_worker.text
    assert "/static/mobile-polish.css" in service_worker.text
