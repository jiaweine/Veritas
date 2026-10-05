from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
from playwright.sync_api import Route, sync_playwright

from smoke_harness_browser import _wait_for_server


def _audit(index: int) -> dict[str, object]:
    status = "error" if index < 5 else "running" if index < 15 else "ready"
    return {
        "audit_id": f"audit_browser_{index:06d}",
        "title": f"Paged audit fixture {index:02d}",
        "filename": f"paper-{index:02d}.pdf",
        "status": status,
        "created_at": f"2026-10-01T10:{index % 60:02d}:00Z",
        "updated_at": f"2026-10-02T12:{index % 60:02d}:00Z",
        "artifact_sha256": f"fixture-{index:064d}"[-64:],
        "paper_summary": {"pages": 8 + index, "tables_detected": 2, "words": 1000 + index},
        "latest_result": {
            "status": "verified",
            "verification_coverage": 0.75,
            "source": {
                "page": 3,
                "table": "Table 2",
                "row": f"Treatment {index:02d}",
            },
            "counts": {"verified": 3, "needs_review": 0, "contradictions": 0},
            "checks": [],
            "findings": [],
        },
        "notes_updated_at": None,
    }


def _audit_detail(item: dict[str, object]) -> dict[str, object]:
    return {
        **item,
        "events": [],
        "attachments": [],
        "notes": "",
        "notes_updated_at": None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Exercise bounded Audit pagination in real Chromium.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--output-dir", default="artifacts/ui")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        _wait_for_server(client)

    ordered = [_audit(index) for index in reversed(range(60))]
    audits_by_id = {str(item["audit_id"]): item for item in ordered}
    first_page = ordered[:50]
    second_page = ordered[50:]
    status_counts = {"ready": 45, "running": 10, "error": 5}
    page_requests: list[str | None] = []
    full_list_requests: list[str] = []
    detail_requests: list[str] = []
    page_errors: list[str] = []

    def handle_pages(route: Route) -> None:
        parsed = urlparse(route.request.url)
        query = parse_qs(parsed.query)
        cursor = query.get("cursor", [None])[0]
        page_requests.append(cursor)
        if cursor is None:
            payload = {
                "items": first_page,
                "next_cursor": "cursor-next",
                "has_more": True,
                "total": 60,
                "status_counts": status_counts,
            }
        elif cursor == "cursor-next":
            payload = {
                "items": second_page,
                "next_cursor": None,
                "has_more": False,
                "total": 60,
                "status_counts": status_counts,
            }
        else:
            route.fulfill(status=422, json={"detail": "unexpected browser cursor"})
            return
        route.fulfill(status=200, json=payload)

    def handle_audits(route: Route) -> None:
        parsed = urlparse(route.request.url)
        if parsed.path == "/api/v1/audits" and not parsed.query:
            full_list_requests.append(route.request.url)
            route.abort()
            return
        prefix = "/api/v1/audits/"
        if parsed.path.startswith(prefix) and parsed.path.count("/") == 4:
            audit_id = parsed.path[len(prefix) :]
            item = audits_by_id.get(audit_id)
            if item is not None:
                detail_requests.append(audit_id)
                route.fulfill(status=200, json=_audit_detail(item))
                return
        route.continue_()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1536, "height": 960},
            device_scale_factor=1,
            locale="en-US",
            color_scheme="dark",
        )
        page = context.new_page()
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.route("**/api/v1/audit-pages**", handle_pages)
        page.route("**/api/v1/audits**", handle_audits)
        page.goto(f"{base_url}/#audits", wait_until="domcontentloaded")

        page.wait_for_function(
            """() => document.querySelector('.page-title')?.textContent?.trim() === 'Audits'""",
            timeout=20_000,
        )
        rows = page.locator("[data-audit-page-id]")
        page.wait_for_function(
            """() => document.querySelectorAll('[data-audit-page-id]').length === 50""",
            timeout=10_000,
        )
        if rows.count() != 50:
            raise AssertionError("Audits UI did not stop at the bounded 50-row first page")
        if full_list_requests:
            raise AssertionError("Product boot escaped the bounded audit-page bootstrap")
        if page.locator("#audit-count").inner_text().strip() != "60":
            raise AssertionError("Sidebar audit count did not use the server total")

        pills = [value.strip() for value in page.locator(".filter-pill").all_inner_texts()]
        expected_pills = ["All 60", "Ready 45", "Running 10", "Error 5"]
        if pills[:4] != expected_pills:
            raise AssertionError(f"Audit status totals were derived from the page instead of the server: {pills!r}")

        footer = page.locator("[data-audit-page-footer='audits']")
        load_more = page.locator("[data-audit-load-more='audits']")
        load_more.wait_for(state="visible", timeout=10_000)
        if "50 of 60 audits loaded" not in footer.inner_text().lower():
            raise AssertionError("Audits footer did not expose bounded loaded-row state")
        load_more.click()
        page.wait_for_function(
            """() => document.querySelectorAll('[data-audit-page-id]').length === 60""",
            timeout=10_000,
        )
        if rows.count() != 60:
            raise AssertionError("Audits UI did not append the second validated page")
        ids = rows.evaluate_all("nodes => nodes.map((node) => node.dataset.auditPageId)")
        if len(ids) != len(set(ids)):
            raise AssertionError("Audit pagination introduced duplicate audit rows")
        if ids[0] != "audit_browser_000059" or ids[-1] != "audit_browser_000000":
            raise AssertionError(f"Audit pagination changed keyset order: {ids[:2]!r} … {ids[-2:]!r}")
        if page.locator("[data-audit-load-more='audits']").count() != 0:
            raise AssertionError("Audits UI kept Load more after the terminal page")
        terminal = page.locator("[data-audit-page-footer='audits']").inner_text().lower()
        if "60 audits loaded" not in terminal or "end of validated audit history" not in terminal:
            raise AssertionError(f"Audits footer lost terminal paging state: {terminal!r}")
        page.screenshot(path=output_dir / "audits-pagination.png", full_page=True)

        page.locator("[data-view='evidence']").first.click()
        page.wait_for_function(
            """() => document.querySelector('.page-title')?.textContent?.trim() === 'Evidence'""",
            timeout=10_000,
        )
        evidence_rows = page.locator("[data-audit-page-id]")
        page.wait_for_function(
            """() => document.querySelectorAll('[data-audit-page-id]').length === 60""",
            timeout=10_000,
        )
        if evidence_rows.count() != 60:
            raise AssertionError("Evidence surface did not preserve loaded audit history")
        evidence_footer = page.locator("[data-audit-page-footer='evidence']").inner_text().lower()
        if "60 audits scanned" not in evidence_footer or "end of validated audit history" not in evidence_footer:
            raise AssertionError(f"Evidence footer lost terminal audit state: {evidence_footer!r}")
        page.screenshot(path=output_dir / "evidence-pagination.png", full_page=True)

        paged_audit_id = "audit_browser_000000"
        page.locator(f"[data-audit-page-id='{paged_audit_id}']").click()
        page.wait_for_url(f"**?audit_open={paged_audit_id}#audit={paged_audit_id}", timeout=10_000)
        page.locator(
            f"[data-audit-harness='true'][data-audit-id='{paged_audit_id}']"
        ).wait_for(state="visible", timeout=20_000)
        if paged_audit_id not in detail_requests:
            raise AssertionError("Paged audit navigation did not reach the product detail API")
        page.screenshot(path=output_dir / "paged-audit-open.png", full_page=True)

        audits_by_id[paged_audit_id]["title"] = "Refreshed off-page audit"
        audits_by_id[paged_audit_id]["status"] = "running"
        page.locator("[data-ah-nav='audits']").click()
        page.wait_for_function(
            """() => document.querySelector('.page-title')?.textContent?.trim() === 'Audits'""",
            timeout=10_000,
        )
        page.locator("#sidebar [data-view='overview']").click()
        page.wait_for_function(
            """() => document.querySelector('.page-title')?.textContent?.trim() === 'Evidence, findings, and runs'""",
            timeout=10_000,
        )
        page.locator("[data-action='refresh']").click()
        page.wait_for_function(
            """() => document.querySelector('#sync-status')?.classList.contains('ready')""",
            timeout=10_000,
        )
        if detail_requests.count(paged_audit_id) < 2:
            raise AssertionError("Off-page active audit was not refreshed from the detail API")
        page.locator("#conversation-nav").click()
        page.wait_for_function(
            """() => document.querySelector('#agent-context')?.textContent?.includes('Refreshed off-page audit')""",
            timeout=10_000,
        )
        context_text = page.locator("#agent-context").inner_text().lower()
        if "running" not in context_text:
            raise AssertionError(f"Conversation retained stale off-page audit state: {context_text!r}")
        page.screenshot(path=output_dir / "off-page-audit-refresh.png", full_page=True)

        context.close()
        browser.close()

    if page_errors:
        raise AssertionError("Browser page errors: " + " | ".join(page_errors))
    if full_list_requests:
        raise AssertionError("Browser issued an unbounded /api/v1/audits request")
    if page_requests.count(None) < 1 or "cursor-next" not in page_requests:
        raise AssertionError(f"Audit-page request sequence was incomplete: {page_requests!r}")
    if detail_requests.count("audit_browser_000000") < 2:
        raise AssertionError(f"Off-page audit detail was not authoritatively refreshed: {detail_requests!r}")

    screenshots = ["audits-pagination.png", "evidence-pagination.png", "paged-audit-open.png", "off-page-audit-refresh.png"]
    for name in screenshots:
        if not (output_dir / name).is_file():
            raise AssertionError(f"Audit pagination screenshot was not captured: {name}")

    print(
        json.dumps(
            {
                "status": "success",
                "first_page_rows": 50,
                "total_rows": 60,
                "full_list_requests": len(full_list_requests),
                "detail_requests": detail_requests,
                "page_requests": page_requests,
                "screenshots": screenshots,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
