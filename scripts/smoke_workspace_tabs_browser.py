"""Check that Audit/Files/Findings/Notes controls switch the real inspector."""

from __future__ import annotations

import argparse

from playwright.sync_api import sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Workbench tab interaction regression.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    args = parser.parse_args()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 960})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        api = page.request.get(args.base_url.rstrip("/") + "/api/v1/audit-pages?limit=1")
        assert api.ok, f"Audit fixture list failed: {api.status}"
        audits = api.json()["items"]
        assert audits, "The earlier harness smoke should create a PDF audit fixture"
        audit_id = audits[0]["audit_id"]
        page.goto(
            args.base_url.rstrip("/") + "/#audit=" + audit_id,
            wait_until="domcontentloaded",
        )
        page.locator('[data-audit-harness="true"]').wait_for(state="visible", timeout=20_000)

        def select_tab(key: str) -> None:
            tab = page.locator(
                f'.ah-workspace-tabs [data-ah-workspace-tab="{key}"]'
                if key == "source"
                else f'.ah-workspace-tabs [data-ah-tab="{key}"]'
            )
            tab.click()
            tab = page.locator(
                f'.ah-workspace-tabs [data-ah-workspace-tab="{key}"]'
                if key == "source"
                else f'.ah-workspace-tabs [data-ah-tab="{key}"]'
            )
            tab.wait_for(state="visible")
            assert tab.get_attribute("aria-selected") == "true"
            assert "active" in (tab.get_attribute("class") or "").split()

        select_tab("structure")
        assert page.locator('.ah-workspace-tabs [data-ah-workspace-tab="source"]').get_attribute("aria-selected") == "false"
        select_tab("findings")
        select_tab("source")

        notes = page.locator(".ah-workspace-tabs [data-ah-notes-tab]")
        notes.wait_for(state="visible", timeout=10_000)
        notes.click()
        page.locator("[data-ah-notes-pane]").wait_for(state="visible")
        select_tab("structure")
        assert page.locator("[data-ah-notes-pane]").count() == 0, (
            "Selecting Files from Notes must not immediately reopen Notes"
        )
        select_tab("source")
        page.locator("[data-ah-notes-tab]").click()
        page.locator("[data-ah-notes-pane]").wait_for(state="visible")
        select_tab("source")
        assert page.locator("[data-ah-notes-pane]").count() == 0
        browser.close()
        assert not errors, errors
        print("Audit Workbench buttons passed: Audit, Files, Findings, Notes and return")


if __name__ == "__main__":
    main()
