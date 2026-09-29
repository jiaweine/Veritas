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

    stylesheet = client.get("/static/audit-harness.css")
    assert stylesheet.status_code == 200
    assert '.audit-harness-active' in stylesheet.text
    assert '.ah-grid' in stylesheet.text
    assert '.ah-pdf' in stylesheet.text

    notes_stylesheet = client.get("/static/audit-notes.css")
    assert notes_stylesheet.status_code == 200
    assert '.ah-notes-pane' in notes_stylesheet.text
    assert '#ah-notes-editor' in notes_stylesheet.text

    service_worker = client.get("/sw.js")
    assert service_worker.status_code == 200
    assert 'veritas-shell-v15' in service_worker.text
    assert '/static/audit-harness.js' in service_worker.text
    assert '/static/audit-harness.css' in service_worker.text
    assert '/static/audit-harness-product.js' in service_worker.text
    assert '/static/audit-harness-product.css' in service_worker.text
    assert '/static/audit-notes.js' in service_worker.text
    assert '/static/audit-notes.css' in service_worker.text
