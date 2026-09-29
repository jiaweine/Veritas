from __future__ import annotations

from fastapi.testclient import TestClient

from veritas.harness.web import create_app


def test_audit_harness_assets_are_part_of_product_shell(tmp_path) -> None:
    client = TestClient(create_app(tmp_path))

    index = client.get("/")
    assert index.status_code == 200
    assert '/static/audit-harness.css' in index.text
    assert '/static/audit-harness.js' in index.text

    script = client.get("/static/audit-harness.js")
    assert script.status_code == 200
    assert 'data-audit-harness="true"' in script.text
    assert 'Veritas Audit Agent' in script.text
    assert '/messages' in script.text
    assert 'Replication Workspace' in script.text
    assert 'read · parse · inspect · verify' in script.text

    stylesheet = client.get("/static/audit-harness.css")
    assert stylesheet.status_code == 200
    assert '.audit-harness-active' in stylesheet.text
    assert '.ah-grid' in stylesheet.text
    assert '.ah-pdf' in stylesheet.text

    service_worker = client.get("/sw.js")
    assert service_worker.status_code == 200
    assert 'veritas-shell-v13' in service_worker.text
    assert '/static/audit-harness.js' in service_worker.text
    assert '/static/audit-harness.css' in service_worker.text
