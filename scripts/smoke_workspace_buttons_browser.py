"""Exercise real UI controls across Settings, Audits and paginated history."""

from __future__ import annotations

import argparse

from playwright.sync_api import sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser(description="Click previously inert workspace buttons.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    args = parser.parse_args()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 960})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.base_url.rstrip("/") + "/#overview", wait_until="networkidle")

        page.get_by_role("button", name="Open workspace settings").click()
        page.wait_for_function("() => location.hash === '#settings'")
        page.locator("[data-settings-surface]").wait_for(state="visible", timeout=20_000)
        page.locator(".sidebar [data-view='audits']").click()
        page.wait_for_function("() => location.hash === '#audits'")

        # Server-confirmed totals differ from loaded records. Never claim a
        # filtered result is absent from all history merely because it isn't
        # on the first loaded page.
        page.evaluate(
            """() => window.dispatchEvent(new CustomEvent(
              "veritas:audit-page-reset", { detail: {
                items: [
                  {audit_id:"audit_filter_ready", title:"Ready paper", status:"ready",
                   paper_summary:{pages:1}, latest_result:{}},
                  {audit_id:"audit_filter_error", title:"Error paper", status:"error",
                   paper_summary:{pages:1}, latest_result:{}}
                ],
                next_cursor:"filter_cursor", has_more:true, total:3,
                status_counts:{ready:1,running:1,error:1}
              }}
            ))"""
        )
        page.locator('tr[data-audit-page-id="audit_filter_error"]').wait_for(state="visible")
        page.locator('[data-audit-status="ready"]').click()
        assert page.locator('[data-audit-status="ready"]').get_attribute("aria-pressed") == "true"
        assert page.locator('tr[data-audit-page-id="audit_filter_ready"]').is_visible()
        assert not page.locator('tr[data-audit-page-id="audit_filter_error"]').is_visible()
        page.locator('[data-audit-status="running"]').click()
        assert not page.locator('tr[data-audit-page-id="audit_filter_ready"]').is_visible()
        assert "Load more" in page.locator("[data-audit-filter-empty]").inner_text()

        def next_page(route):
            route.fulfill(
                status=200,
                content_type="application/json",
                body="""{"items":[{"audit_id":"audit_filter_running",
                "title":"Running paper","status":"running",
                "paper_summary":{"pages":1},"latest_result":{}}],
                "next_cursor":null,"has_more":false,"total":3,
                "status_counts":{"ready":1,"running":1,"error":1}}""",
            )

        page.route("**/api/v1/audit-pages?*cursor=filter_cursor", next_page)
        page.locator('[data-audit-load-more="audits"]').click()
        page.locator('tr[data-audit-page-id="audit_filter_running"]').wait_for(state="visible")
        assert not page.locator('tr[data-audit-page-id="audit_filter_ready"]').is_visible()
        page.locator('[data-audit-status="all"]').click()
        assert page.locator('[data-audit-status="all"]').get_attribute("aria-pressed") == "true"
        for audit_id in ("audit_filter_ready", "audit_filter_error", "audit_filter_running"):
            assert page.locator(f'tr[data-audit-page-id="{audit_id}"]').is_visible()
        browser.close()

        assert not errors, errors
        print("Buttons passed: Workspace Settings, status pills, paged filtering and All reset")


if __name__ == "__main__":
    main()
