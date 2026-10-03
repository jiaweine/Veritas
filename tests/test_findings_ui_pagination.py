from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "veritas" / "harness" / "static"


def test_findings_product_boot_and_surface_are_bounded() -> None:
    shell = (STATIC / "index.html").read_text(encoding="utf-8")
    bootstrap = (STATIC / "finding-page-bootstrap.js").read_text(encoding="utf-8")
    pager = (STATIC / "finding-pagination.js").read_text(encoding="utf-8")
    styles = (STATIC / "finding-pagination.css").read_text(encoding="utf-8")
    sw = (STATIC / "sw.js").read_text(encoding="utf-8")

    assert shell.index("/static/finding-page-bootstrap.js") < shell.index("/static/app.js")
    assert shell.index("/static/finding-pagination.js") > shell.index("/static/app.js")
    assert "/static/finding-pagination.css" in shell

    assert 'url.pathname !== "/api/v1/findings"' in bootstrap
    assert "url.search" in bootstrap
    assert '"/api/v1/finding-pages"' in bootstrap
    assert "FINDING_BOOT_LIMIT = 50" in bootstrap
    assert '"Cache-Control": "no-store"' in bootstrap
    assert '"X-Veritas-Finding-Page": "1"' in bootstrap
    assert "entity headers must be rebuilt" in bootstrap
    assert "veritas:finding-page-reset" in bootstrap

    assert "FINDING_PAGE_LIMIT = 50" in pager
    assert "replaceHead" in pager
    assert "Only explicit" in pager
    assert "appendTail" in pager
    assert "seen.has(item.finding_id)" in pager
    assert "loadMoreError" in pager
    assert "previousScrollTop" in pager
    assert "Loaded all" in pager
    assert "data-finding-page-id" in pager
    assert "audit_open" in pager
    assert "findingFeed.ready = true" in pager
    assert "globalCountObserver" in pager
    assert "node.textContent !== authoritative" in pager
    assert "server-reported total" in pager
    assert ".finding-page-footer" in styles

    assert 'const CACHE = "veritas-shell-v29";' in sw
    assert 'const CACHE_REVISION = "audit-pagination-1";' in sw
    assert 'const ACTIVE_CACHE = `${CACHE}-${CACHE_REVISION}`;' in sw
    assert 'const FINDING_CACHE_REVISION = "finding-pagination-1";' in sw
    assert 'const SHELL_CACHE = `${ACTIVE_CACHE}-${FINDING_CACHE_REVISION}`;' in sw
    assert 'caches.open(SHELL_CACHE)' in sw
    for asset in (
        "/static/finding-page-bootstrap.js",
        "/static/finding-pagination.js",
        "/static/finding-pagination.css",
    ):
        assert asset in sw


def test_findings_pagination_has_mobile_and_real_browser_gates() -> None:
    mobile = (ROOT / ".github" / "workflows" / "mobile.yml").read_text(encoding="utf-8")
    visual = (ROOT / ".github" / "workflows" / "ui-visual-smoke.yml").read_text(encoding="utf-8")
    smoke = (ROOT / "scripts" / "smoke_findings_pagination_browser.py").read_text(encoding="utf-8")

    assert "node --check ../src/veritas/harness/static/finding-page-bootstrap.js" in mobile
    assert "node --check ../src/veritas/harness/static/finding-pagination.js" in mobile
    assert "scripts/smoke_findings_pagination_browser.py" in visual

    assert 'first_page_rows": 50' in smoke
    assert 'total_rows": 60' in smoke
    assert 'full_list_requests": len(full_list_requests)' in smoke
    assert 'page.route("**/api/v1/findings**", handle_findings)' in smoke
    assert "reset_ids == [str(item[\"finding_id\"]) for item in first_page]" in smoke
    assert "paged-finding-open.png" in smoke
