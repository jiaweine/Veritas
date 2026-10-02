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


def test_product_boot_bounds_legacy_run_fetch_before_app_executes() -> None:
    shell = (ROOT / "src/veritas/harness/static/index.html").read_text(encoding="utf-8")
    bootstrap = (ROOT / "src/veritas/harness/static/run-page-bootstrap.js").read_text(
        encoding="utf-8"
    )
    service_worker = (ROOT / "src/veritas/harness/static/sw.js").read_text(encoding="utf-8")

    bootstrap_src = '<script src="/static/run-page-bootstrap.js"></script>'
    app_src = '<script type="module" src="/static/app.js"></script>'
    assert bootstrap_src in shell
    assert shell.index(bootstrap_src) < shell.index(app_src)
    assert 'url.pathname === "/api/v1/runs"' in bootstrap
    assert 'new URL("/api/v1/run-pages"' in bootstrap
    assert "const RUN_BOOT_LIMIT = 50" in bootstrap
    assert '"Cache-Control": "no-store"' in bootstrap
    assert '"X-Veritas-Run-Page": "1"' in bootstrap
    assert "entity headers must be rebuilt" in bootstrap
    assert 'const CACHE = "veritas-shell-v29"' in service_worker
    assert 'const CACHE_REVISION = "runs-pagination-1"' in service_worker
    assert "ACTIVE_CACHE" in service_worker
    assert '"/static/run-page-bootstrap.js"' in service_worker


def test_runs_pagination_has_real_chromium_acceptance() -> None:
    browser = (ROOT / "scripts/smoke_runs_pagination_browser.py").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ui-visual-smoke.yml").read_text(encoding="utf-8")

    assert "Runs UI did not stop at the bounded 50-row first page" in browser
    assert "Runs pagination introduced duplicate run rows" in browser
    assert "Product boot escaped the bounded run-page bootstrap" in browser
    assert '"runs-pagination.png"' in browser
    assert "python scripts/smoke_runs_pagination_browser.py" in workflow
