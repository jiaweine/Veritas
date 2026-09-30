from __future__ import annotations

from fastapi.testclient import TestClient

from veritas.harness.web import create_app


def test_audit_harness_assets_are_part_of_product_shell(tmp_path) -> None:
    client = TestClient(create_app(tmp_path))

    index = client.get("/")
    assert index.status_code == 200
    assert '/static/audit-harness.css' in index.text
    assert '/static/audit-harness.js' in index.text
    assert '/static/audit-harness-product.css' in index.text
    assert '/static/audit-harness-product.js' in index.text
    assert '/static/audit-notes.css' in index.text
    assert '/static/audit-notes.js' in index.text
    assert '/static/reference-workbench.css' in index.text
    assert '/static/reference-workbench.js' in index.text
    assert '/static/reference-surfaces.css' in index.text
    assert '/static/reference-evidence-preview.js' in index.text
    assert '/static/claim-graph.css' in index.text
    assert '/static/claim-graph.js' in index.text
    assert '/static/mobile-polish.css' in index.text

    script = client.get("/static/audit-harness.js")
    assert script.status_code == 200
    assert 'data-audit-harness="true"' in script.text
    assert 'Veritas Audit Agent' in script.text
    assert '/messages' in script.text
    assert 'Replication Workspace' in script.text
    assert 'read · parse · inspect · verify' in script.text

    notes_script = client.get("/static/audit-notes.js")
    assert notes_script.status_code == 200
    assert 'data-ah-notes-tab' in notes_script.text
    assert '/notes' in notes_script.text
    assert 'Save notes' in notes_script.text

    claim_script = client.get("/static/claim-graph.js")
    assert claim_script.status_code == 200
    assert 'data-reference-claim-tab' in claim_script.text
    assert 'data-reference-claim-graph' in claim_script.text
    assert 'data-cg-detail-panel' in claim_script.text
    assert 'data-cg-detail-action' in claim_script.text
    assert '/api/v1/audits/${encodeURIComponent(auditId)}' in claim_script.text
    assert 'veritas:evidence-field' in claim_script.text

    stylesheet = client.get("/static/audit-harness.css")
    assert stylesheet.status_code == 200
    assert '.audit-harness-active' in stylesheet.text
    assert '.ah-grid' in stylesheet.text
    assert '.ah-pdf' in stylesheet.text

    notes_stylesheet = client.get("/static/audit-notes.css")
    assert notes_stylesheet.status_code == 200
    assert '.ah-notes-pane' in notes_stylesheet.text
    assert '#ah-notes-editor' in notes_stylesheet.text

    claim_stylesheet = client.get("/static/claim-graph.css")
    assert claim_stylesheet.status_code == 200
    assert '.claim-graph' in claim_stylesheet.text
    assert '.cg-detail' in claim_stylesheet.text
    assert '.is-linked-selection' in claim_stylesheet.text

    mobile_stylesheet = client.get("/static/mobile-polish.css")
    assert mobile_stylesheet.status_code == 200
    assert "@media (max-width: 620px)" in mobile_stylesheet.text
    assert ".ah-header-actions" in mobile_stylesheet.text
    assert ".audit-harness .ah-left" in mobile_stylesheet.text

    service_worker = client.get("/sw.js")
    assert service_worker.status_code == 200
    assert 'veritas-shell-v20' in service_worker.text
    assert '/static/audit-harness.js' in service_worker.text
    assert '/static/audit-harness.css' in service_worker.text
    assert '/static/audit-harness-product.js' in service_worker.text
    assert '/static/audit-harness-product.css' in service_worker.text
    assert '/static/audit-notes.js' in service_worker.text
    assert '/static/audit-notes.css' in service_worker.text
    assert '/static/reference-workbench.js' in service_worker.text
    assert '/static/reference-workbench.css' in service_worker.text
    assert '/static/reference-evidence-preview.js' in service_worker.text
    assert '/static/reference-surfaces.css' in service_worker.text
    assert '/static/claim-graph.js' in service_worker.text
    assert '/static/claim-graph.css' in service_worker.text
    assert '/static/mobile-polish.css' in service_worker.text
