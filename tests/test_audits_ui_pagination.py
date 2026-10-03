from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_product_boot_bounds_audit_history_and_pages_audit_surfaces() -> None:
    shell = (ROOT / "src/veritas/harness/static/index.html").read_text(encoding="utf-8")
    bootstrap = (ROOT / "src/veritas/harness/static/audit-page-bootstrap.js").read_text(
        encoding="utf-8"
    )
    pager = (ROOT / "src/veritas/harness/static/audit-pagination.js").read_text(
        encoding="utf-8"
    )
    styles = (ROOT / "src/veritas/harness/static/audit-pagination.css").read_text(
        encoding="utf-8"
    )
    service_worker = (ROOT / "src/veritas/harness/static/sw.js").read_text(encoding="utf-8")

    bootstrap_src = '<script src="/static/audit-page-bootstrap.js"></script>'
    app_src = '<script type="module" src="/static/app.js"></script>'
    pager_src = '<script type="module" src="/static/audit-pagination.js"></script>'
    assert bootstrap_src in shell
    assert shell.index(bootstrap_src) < shell.index(app_src)
    assert pager_src in shell
    assert shell.index(app_src) < shell.index(pager_src)
    assert 'url.pathname !== "/api/v1/audits"' in bootstrap
    assert 'new URL("/api/v1/audit-pages"' in bootstrap
    assert "AUDIT_BOOT_LIMIT = 50" in bootstrap
    assert '"Cache-Control": "no-store"' in bootstrap
    assert '"X-Veritas-Audit-Page": "1"' in bootstrap
    assert "entity headers must be rebuilt" in bootstrap

    assert "const AUDIT_PAGE_LIMIT = 50" in pager
    assert 'new URL("/api/v1/audit-pages"' in pager
    assert "data-audit-load-more" in pager
    assert "data-audit-page-footer" in pager
    assert "Unable to load the next audit page" in pager
    assert "function mergeHead" in pager
    assert "function appendTail" in pager
    assert "auditFeed.items = appendTail(auditFeed.items, page.items)" in pager
    assert "seen.has(auditId)" in pager
    assert "preserveCursor" in pager
    assert "auditCount.textContent !== total" in pager
    assert 'data-audit-id="${auditId}" data-audit-page-id="${auditId}"' in pager
    assert 'target.searchParams.set("audit_open", auditId)' in pager
    assert 'target.hash = `audit=${encodeURIComponent(auditId)}`' in pager
    assert "re-enter that existing server-backed open path" in pager
    assert "End of validated audit history" in pager
    assert ".audit-page-footer" in styles
    assert ".audit-page-error" in styles

    assert 'const CACHE = "veritas-shell-v29"' in service_worker
    assert 'const CACHE_REVISION = "audit-pagination-1"' in service_worker
    assert '"/static/audit-page-bootstrap.js"' in service_worker
    assert '"/static/audit-pagination.js"' in service_worker
    assert '"/static/audit-pagination.css"' in service_worker


def test_audit_pagination_is_syntax_checked_and_has_real_chromium_acceptance() -> None:
    mobile = (ROOT / ".github/workflows/mobile.yml").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ui-visual-smoke.yml").read_text(encoding="utf-8")
    browser = (ROOT / "scripts/smoke_audits_pagination_browser.py").read_text(encoding="utf-8")

    assert "node --check ../src/veritas/harness/static/audit-page-bootstrap.js" in mobile
    assert "node --check ../src/veritas/harness/static/audit-pagination.js" in mobile
    assert "python scripts/smoke_audits_pagination_browser.py" in workflow
    assert "Audits UI did not stop at the bounded 50-row first page" in browser
    assert "Product boot escaped the bounded audit-page bootstrap" in browser
    assert "Audit pagination introduced duplicate audit rows" in browser
    assert "Audit pagination changed keyset order" in browser
    assert "Evidence surface did not preserve loaded audit history" in browser
    assert "Paged audit navigation did not reach the product detail API" in browser
    assert 'wait_until="domcontentloaded"' in browser
    assert '"audits-pagination.png"' in browser
    assert '"evidence-pagination.png"' in browser
    assert '"paged-audit-open.png"' in browser
