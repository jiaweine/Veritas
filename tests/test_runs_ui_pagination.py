from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_runs_ui_uses_bounded_server_pages_and_retryable_load_more() -> None:
    script = (ROOT / "src/veritas/harness/static/runs.js").read_text(encoding="utf-8")
    styles = (ROOT / "src/veritas/harness/static/runs.css").read_text(encoding="utf-8")

    assert "const RUN_PAGE_LIMIT = 50" in script
    assert "/api/v1/run-pages?" in script
    assert "data-run-load-more" in script
    assert "next_cursor" in script
    assert "has_more" in script
    assert "loadMoreError" in script
    assert "Unable to load the next page" in script
    assert "seen.has(item.run_id)" in script
    assert "previousScrollTop" in script
    assert 'json("/api/v1/runs")' not in script
    assert ".run-page-footer" in styles
    assert ".run-page-error" in styles


def test_product_boot_directly_pages_run_history() -> None:
    static = ROOT / "src/veritas/harness/static"
    shell = (static / "index.html").read_text(encoding="utf-8")
    app = (static / "app.js").read_text(encoding="utf-8")
    service_worker = (static / "sw.js").read_text(encoding="utf-8")

    assert "PRODUCT_BOOT_PAGE_LIMIT = 50" in app
    assert 'runs: `/api/v1/run-pages?limit=${PRODUCT_BOOT_PAGE_LIMIT}`' in app
    assert 'api(PRODUCT_BOOT_PAGE_PATHS.runs)' in app
    assert 'api("/api/v1/runs").then' not in app
    assert "/static/run-page-bootstrap.js" not in shell
    assert 'const CACHE = "veritas-shell-v29"' in service_worker
    assert 'const CACHE_REVISION = "direct-bounded-boot-1"' in service_worker
    assert '"/static/run-page-bootstrap.js"' not in service_worker


def test_runs_pagination_has_real_chromium_acceptance() -> None:
    browser = (ROOT / "scripts/smoke_runs_pagination_browser.py").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ui-visual-smoke.yml").read_text(encoding="utf-8")

    assert "Runs UI did not stop at the bounded 50-row first page" in browser
    assert "Runs pagination introduced duplicate run rows" in browser
    assert "Browser issued an unbounded /api/v1/runs request" in browser
    assert '"runs-pagination.png"' in browser
    assert "python scripts/smoke_runs_pagination_browser.py" in workflow
