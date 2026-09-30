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
    assert "/static/finding-navigation.css" in shell.text
    assert "/static/finding-navigation.js" in shell.text
    assert "/static/settings.css" in shell.text
    assert "/static/settings.js" in shell.text
    assert "/static/settings-interactions.css" in shell.text
    assert "/static/settings-interactions.js" in shell.text
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
    assert "data-cg-finding-id" in claim_script.text
    assert "veritas:claim-finding" in claim_script.text
    assert "veritas:finding-select" in claim_script.text
    assert "aria-current" in claim_script.text
    assert "veritas:evidence-field" in claim_script.text

    finding_script = client.get("/static/finding-navigation.js")
    assert finding_script.status_code == 200
    assert "data-fn-finding-id" in finding_script.text
    assert "data-fn-graph" in finding_script.text
    assert "data-fn-reproduce" in finding_script.text
    assert "veritas.replication.context.v1" in finding_script.text
    assert "veritas.finding.focus.v1" in finding_script.text
    assert "veritas:claim-finding" in finding_script.text
    assert "veritas:finding-select" in finding_script.text

    reproduction_script = client.get("/static/reproduction.js")
    assert reproduction_script.status_code == 200
    assert "data-rep-finding-context" in reproduction_script.text
    assert "finding_id" in reproduction_script.text
    assert "origin_finding" in reproduction_script.text
    assert "Context binding only" in reproduction_script.text
    assert "data-rep-return-finding" in reproduction_script.text

    settings_script = client.get("/static/settings.js")
    assert settings_script.status_code == 200
    assert 'getJson("/api/v1/model-providers")' in settings_script.text
    assert 'data-model-provider-matrix="true"' in settings_script.text
    assert "Evidence firewall active" in settings_script.text
    assert "ACP BRIDGE REQUIRED" in settings_script.text
    assert "secrets_exposed" in settings_script.text

    settings_styles = client.get("/static/settings.css")
    assert settings_styles.status_code == 200
    assert ".model-router" in settings_styles.text
    assert ".provider-node" in settings_styles.text
    assert "router-scan" in settings_styles.text
    assert "packet-flow" in settings_styles.text

    interaction_script = client.get("/static/settings-interactions.js")
    assert interaction_script.status_code == 200
    assert "data-router-pointer-inspector" in interaction_script.text
    assert "data-router-network-field" in interaction_script.text
    assert "networkFocus" in interaction_script.text
    assert "pointermove" in interaction_script.text
    assert "aria-pressed" in interaction_script.text
    assert "aria-controls" in interaction_script.text
    assert "requestAnimationFrame" in interaction_script.text

    interaction_styles = client.get("/static/settings-interactions.css")
    assert interaction_styles.status_code == 200
    assert "--router-x" in interaction_styles.text
    assert "--tilt-x" in interaction_styles.text
    assert ".router-pointer-inspector" in interaction_styles.text
    assert ".router-network-field" in interaction_styles.text
    assert "provider-pin-scan" in interaction_styles.text
    assert "prefers-reduced-motion" in interaction_styles.text

    finding_styles = client.get("/static/finding-navigation.css")
    assert finding_styles.status_code == 200
    assert ".fn-finding-row" in finding_styles.text
    assert ".is-linked-finding" in finding_styles.text

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
    assert 'const CACHE = "veritas-shell-v26"' in service_worker.text
    assert "/static/audit-harness-product.css" in service_worker.text
    assert "/static/audit-harness-product.js" in service_worker.text
    assert "/static/reference-workbench.css" in service_worker.text
    assert "/static/reference-workbench.js" in service_worker.text
    assert "/static/reference-surfaces.css" in service_worker.text
    assert "/static/reference-evidence-preview.js" in service_worker.text
    assert "/static/claim-graph.css" in service_worker.text
    assert "/static/claim-graph.js" in service_worker.text
    assert "/static/finding-navigation.css" in service_worker.text
    assert "/static/finding-navigation.js" in service_worker.text
    assert "/static/settings.css" in service_worker.text
    assert "/static/settings.js" in service_worker.text
    assert "/static/settings-interactions.css" in service_worker.text
    assert "/static/settings-interactions.js" in service_worker.text
    assert "/static/reproduction-diff-state.css" in service_worker.text
    assert "/static/reproduction-review.css" in service_worker.text
    assert "/static/finding-replication-review.css" in service_worker.text
    assert "/static/mobile-polish.css" in service_worker.text
