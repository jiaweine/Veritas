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
    assert '/static/projects.css' in index.text
    assert '/static/projects.js' in index.text
    assert '/static/projects-reference.js' in index.text
    assert '/static/reference-workbench.css' in index.text
    assert '/static/reference-workbench.js' in index.text
    assert '/static/reference-surfaces.css' in index.text
    assert '/static/reference-evidence-preview.js' in index.text
    assert '/static/claim-graph.css' in index.text
    assert '/static/claim-graph.js' in index.text
    assert '/static/finding-navigation.css' in index.text
    assert '/static/finding-navigation.js' in index.text
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

    projects_script = client.get("/static/projects.js")
    assert projects_script.status_code == 200
    assert '/api/v1/projects' in projects_script.text
    assert '/project`' in projects_script.text
    assert 'Organization only' in projects_script.text
    assert 'data-pw-assignment' in projects_script.text

    reference_projects_script = client.get("/static/projects-reference.js")
    assert reference_projects_script.status_code == 200
    assert 'data-pw-reference-projects' in reference_projects_script.text
    assert 'data-pw-ref-assignment' in reference_projects_script.text
    assert 'outside evidence provenance' in reference_projects_script.text
    assert '/api/v1/projects' in reference_projects_script.text

    claim_script = client.get("/static/claim-graph.js")
    assert claim_script.status_code == 200
    assert 'data-reference-claim-tab' in claim_script.text
    assert 'data-reference-claim-graph' in claim_script.text
    assert 'data-cg-detail-panel' in claim_script.text
    assert 'data-cg-detail-action' in claim_script.text
    assert 'data-cg-finding-id' in claim_script.text
    assert '/api/v1/audits/${encodeURIComponent(auditId)}' in claim_script.text
    assert 'veritas:evidence-field' in claim_script.text
    assert 'veritas:finding-select' in claim_script.text

    finding_script = client.get("/static/finding-navigation.js")
    assert finding_script.status_code == 200
    assert 'data-fn-finding-id' in finding_script.text
    assert 'data-fn-graph' in finding_script.text
    assert 'veritas:claim-finding' in finding_script.text
    assert 'veritas:finding-select' in finding_script.text

    stylesheet = client.get("/static/audit-harness.css")
    assert stylesheet.status_code == 200
    assert '.audit-harness-active' in stylesheet.text
    assert '.ah-grid' in stylesheet.text
    assert '.ah-pdf' in stylesheet.text

    notes_stylesheet = client.get("/static/audit-notes.css")
    assert notes_stylesheet.status_code == 200
    assert '.ah-notes-pane' in notes_stylesheet.text
    assert '#ah-notes-editor' in notes_stylesheet.text

    projects_stylesheet = client.get("/static/projects.css")
    assert projects_stylesheet.status_code == 200
    assert '.pw-project-group' in projects_stylesheet.text
    assert '.pw-audit-project' in projects_stylesheet.text
    assert '.pw-filter-banner' in projects_stylesheet.text
    assert '.pw-ref-projects' in projects_stylesheet.text
    assert '.pw-ref-current' in projects_stylesheet.text

    claim_stylesheet = client.get("/static/claim-graph.css")
    assert claim_stylesheet.status_code == 200
    assert '.claim-graph' in claim_stylesheet.text
    assert '.cg-detail' in claim_stylesheet.text
    assert '.is-linked-selection' in claim_stylesheet.text

    finding_stylesheet = client.get("/static/finding-navigation.css")
    assert finding_stylesheet.status_code == 200
    assert '.fn-finding-row' in finding_stylesheet.text
    assert '.is-linked-finding' in finding_stylesheet.text

    mobile_stylesheet = client.get("/static/mobile-polish.css")
    assert mobile_stylesheet.status_code == 200
    assert "@media (max-width: 620px)" in mobile_stylesheet.text
    assert ".ah-header-actions" in mobile_stylesheet.text
    assert ".audit-harness .ah-left" in mobile_stylesheet.text

    service_worker = client.get("/sw.js")
    assert service_worker.status_code == 200
    assert 'veritas-shell-v23' in service_worker.text
    assert '/static/audit-harness.js' in service_worker.text
    assert '/static/audit-harness.css' in service_worker.text
    assert '/static/audit-harness-product.js' in service_worker.text
    assert '/static/audit-harness-product.css' in service_worker.text
    assert '/static/audit-notes.js' in service_worker.text
    assert '/static/audit-notes.css' in service_worker.text
    assert '/static/projects.js' in service_worker.text
    assert '/static/projects-reference.js' in service_worker.text
    assert '/static/projects.css' in service_worker.text
    assert '/static/reference-workbench.js' in service_worker.text
    assert '/static/reference-workbench.css' in service_worker.text
    assert '/static/reference-evidence-preview.js' in service_worker.text
    assert '/static/reference-surfaces.css' in service_worker.text
    assert '/static/claim-graph.js' in service_worker.text
    assert '/static/claim-graph.css' in service_worker.text
    assert '/static/finding-navigation.js' in service_worker.text
    assert '/static/finding-navigation.css' in service_worker.text
    assert '/static/mobile-polish.css' in service_worker.text
