from __future__ import annotations

from fastapi.testclient import TestClient

from veritas.harness.web import create_app


def test_product_boot_keeps_successful_slices_and_reuses_run_head(tmp_path) -> None:
    client = TestClient(create_app(tmp_path))

    app_script = client.get("/static/app.js")
    assert app_script.status_code == 200
    assert "Promise.allSettled" in app_script.text
    assert 'setSync("partial", "Partial data")' in app_script.text
    assert "Some workspace data could not refresh" in app_script.text
    assert 'setSync("error", "Offline")' in app_script.text

    run_bootstrap = client.get("/static/run-page-bootstrap.js")
    assert run_bootstrap.status_code == 200
    assert "window.__veritasRunPageFeed" in run_bootstrap.text
    assert 'CustomEvent("veritas:run-page-reset"' in run_bootstrap.text
    assert 'new URL("/api/v1/run-pages"' in run_bootstrap.text
    assert '"X-Veritas-Run-Page": "1"' in run_bootstrap.text

    runs_script = client.get("/static/runs.js")
    assert runs_script.status_code == 200
    assert "runFeed.ready" in runs_script.text
    assert "window.__veritasRunPageFeed" in runs_script.text
    assert 'window.addEventListener("veritas:run-page-reset"' in runs_script.text
    assert 'main.querySelector("[data-runs-surface=\'true\']")' in runs_script.text

    service_worker = client.get("/sw.js")
    assert service_worker.status_code == 200
    assert 'PRODUCT_BOOT_CACHE_REVISION = "resilient-product-boot-1"' in service_worker.text
    assert "PRODUCT_BOOT_CACHE_REVISION" in service_worker.text
