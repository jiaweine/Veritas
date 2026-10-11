"""Check that failed read-only workspace panels can recover without route changes."""

from __future__ import annotations

import argparse

from playwright.sync_api import Route, sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser(description="Chromium read failure recovery smoke.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    args = parser.parse_args()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 960})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.base_url.rstrip("/") + "/#overview", wait_until="networkidle")

        for view, url_pattern, retry_selector, resolved_selector in (
            ("runs", "**/api/v1/run-pages?*", "[data-runs-retry]", "[data-runs-surface]"),
            ("settings", "**/api/v1/model-providers", "[data-settings-retry]", "[data-settings-surface]"),
            ("benchmarks", "**/api/v1/benchmarks", "[data-benchmark-retry]", "[data-benchmark-surface]"),
        ):
            count = [0]

            def fail_first(route: Route) -> None:
                count[0] += 1
                if count[0] == 1:
                    route.fulfill(
                        status=503,
                        content_type="application/json",
                        body='{"detail":"Synthetic read-only outage"}',
                    )
                else:
                    route.continue_()

            page.route(url_pattern, fail_first)
            page.locator(f".sidebar [data-view='{view}']").click()
            retry = page.locator(retry_selector)
            retry.wait_for(state="visible", timeout=15_000)
            assert "Synthetic read-only outage" in page.locator("#main-content").inner_text()
            assert retry.is_enabled()
            retry.click()
            page.locator(resolved_selector).wait_for(state="visible", timeout=20_000)
            assert count[0] >= 2, f"{view} retry did not re-fetch authoritative API"
            assert retry.count() == 0, f"{view} error was not cleared after recovery"
            page.unroute(url_pattern, fail_first)

        browser.close()
        assert not errors, errors
        print("Read-only retry checks passed: Runs, Settings, Benchmarks")


if __name__ == "__main__":
    main()
