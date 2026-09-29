from __future__ import annotations

from fastapi.testclient import TestClient

from veritas.harness.web import create_app


def test_audit_harness_product_assets_are_wired_into_shell(tmp_path) -> None:
    client = TestClient(create_app(tmp_path))

    shell = client.get("/")
    assert shell.status_code == 200
    assert "/static/audit-harness-product.css" in shell.text
    assert "/static/audit-harness-product.js" in shell.text

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

    service_worker = client.get("/sw.js")
    assert service_worker.status_code == 200
    assert 'const CACHE = "veritas-shell-v14"' in service_worker.text
    assert "/static/audit-harness-product.css" in service_worker.text
    assert "/static/audit-harness-product.js" in service_worker.text
