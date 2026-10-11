"""Ensure late UI API responses cannot overwrite a newer SPA route."""

from __future__ import annotations

import argparse

from playwright.sync_api import sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser(description="Check stale route responses with real Chromium.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    args = parser.parse_args()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 960})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.base_url.rstrip("/") + "/#overview", wait_until="networkidle")

        for view, endpoint, ready in (
            ("settings", "/api/v1/model-providers", "[data-settings-loading]"),
            ("runs", "/api/v1/run-pages", "runsEnhanced"),
            ("reproduction", "/api/v1/capabilities", "reproductionEnhanced"),
        ):
            page.evaluate(
                """(endpoint) => {
                  const original = window.fetch.bind(window);
                  window.__restoreFetch = () => { window.fetch = original; };
                  window.__releaseDelayedFetch = null;
                  window.fetch = (input, options) => {
                    const path = typeof input === "string" ? input : input.url;
                    if (path.includes(endpoint)) {
                      return new Promise((resolve) => {
                        window.__releaseDelayedFetch = () =>
                          resolve(new Response("{}", {
                            status: 200, headers: { "Content-Type": "application/json" }
                          }));
                      });
                    }
                    return original(input, options);
                  };
                }""",
                endpoint,
            )
            page.locator(f".sidebar [data-view='{view}']").click()
            if ready.startswith("["):
                page.locator(ready).wait_for(state="visible", timeout=20_000)
            else:
                page.wait_for_function(
                    "(name) => document.querySelector('#main-content')?.dataset[name] === 'true'",
                    arg=ready,
                    timeout=20_000,
                )
            page.locator(".sidebar [data-view='overview']").click()
            page.evaluate(
                """async () => {
                  if (typeof window.__releaseDelayedFetch !== "function") {
                    throw new Error("Feature request was not captured.");
                  }
                  window.__releaseDelayedFetch();
                  window.__restoreFetch();
                  await new Promise((resolve) => setTimeout(resolve, 80));
                }"""
            )
            assert page.evaluate(
                """() => location.hash === "#overview"
                  && Boolean(document.querySelector("#main-content .page-title"))
                  && !document.querySelector("#main-content [data-settings-surface]")
                  && !document.querySelector("#main-content [data-runs-surface]")
                  && !document.querySelector("#main-content [data-reproduction-surface]")"""
            ), f"{view} late response overwrote Overview"
        browser.close()

    assert not errors, errors
    print("Stale response navigation checks: settings, runs, reproduction passed")


if __name__ == "__main__":
    main()
