from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_product_boot_directly_pages_audit_history() -> None:
    static = ROOT / "src/veritas/harness/static"
    shell = (static / "index.html").read_text(encoding="utf-8")
    app = (static / "app.js").read_text(encoding="utf-8")
    pager = (static / "audit-pagination.js").read_text(encoding="utf-8")
    styles = (static / "audit-pagination.css").read_text(encoding="utf-8")
    service_worker = (static / "sw.js").read_text(encoding="utf-8")

    assert "PRODUCT_BOOT_PAGE_LIMIT = 50" in app
    assert 'audits: `/api/v1/audit-pages?limit=${PRODUCT_BOOT_PAGE_LIMIT}`' in app
    assert 'api(PRODUCT_BOOT_PAGE_PATHS.audits)' in app
    assert 'api("/api/v1/audits").then' not in app
    assert "window.__veritasAuditPageFeed = page" in app
    assert 'new CustomEvent("veritas:audit-page-reset", { detail: page })' in app
    assert "pageTotal(auditPage, audits)" in app

    assert "/static/audit-page-bootstrap.js" not in shell
    assert '<script type="module" src="/static/app.js"></script>' in shell
    assert '<script type="module" src="/static/audit-pagination.js"></script>' in shell

    assert "const AUDIT_PAGE_LIMIT = 50" in pager
    assert 'new URL("/api/v1/audit-pages"' in pager
    assert "data-audit-load-more" in pager
    assert "function mergeHead" in pager
    assert "function appendTail" in pager
    assert "auditFeed.items = appendTail(auditFeed.items, page.items)" in pager
    assert "preserveCursor" in pager
    assert "End of validated audit history" in pager
    assert ".audit-page-footer" in styles
    assert ".audit-page-error" in styles

    assert 'const CACHE = "veritas-shell-v29"' in service_worker
    assert 'const CACHE_REVISION = "direct-bounded-boot-1"' in service_worker
    assert '"/static/audit-page-bootstrap.js"' not in service_worker
    assert '"/static/audit-pagination.js"' in service_worker
    assert '"/static/audit-pagination.css"' in service_worker


def test_audit_pagination_is_syntax_checked_and_has_real_chromium_acceptance() -> None:
    mobile = (ROOT / ".github/workflows/mobile.yml").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ui-visual-smoke.yml").read_text(encoding="utf-8")
    browser = (ROOT / "scripts/smoke_audits_pagination_browser.py").read_text(encoding="utf-8")

    assert "node --check ../src/veritas/harness/static/app.js" in mobile
    assert "audit-page-bootstrap.js" not in mobile
    assert "node --check ../src/veritas/harness/static/audit-pagination.js" in mobile
    assert "python scripts/smoke_audits_pagination_browser.py" in workflow
    assert "Audits UI did not stop at the bounded 50-row first page" in browser
    assert "Browser issued an unbounded /api/v1/audits request" in browser
    assert "Audit pagination introduced duplicate audit rows" in browser
    assert "Audit pagination changed keyset order" in browser
    assert "Evidence surface did not preserve loaded audit history" in browser
    assert "Paged audit navigation did not reach the product detail API" in browser
    assert 'wait_until="domcontentloaded"' in browser
    assert '"audits-pagination.png"' in browser
    assert '"evidence-pagination.png"' in browser
    assert '"paged-audit-open.png"' in browser
