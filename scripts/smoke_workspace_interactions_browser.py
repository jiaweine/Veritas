"""Check search ownership, stale audit navigation and local PDF validation."""

from __future__ import annotations

import argparse

from playwright.sync_api import sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser(description="Check cross-view workspace interactions in Chromium.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    args = parser.parse_args()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 960})
        page.goto(args.base_url.rstrip("/") + "/#overview", wait_until="networkidle")

        # Navigation must preserve browser Back/Forward semantics.
        page.locator(".sidebar [data-view='runs']").click()
        page.wait_for_function("() => location.hash === '#runs'")
        page.go_back(wait_until="domcontentloaded")
        page.wait_for_function(
            "() => location.hash === '#overview' && document.querySelector('.page-title')?.textContent?.trim() === 'Overview'",
            timeout=15_000,
        )

        # Only command-search.js should own the palette, not a second copy in app.js.
        page.evaluate(
            """() => {
              const original = window.fetch.bind(window);
              window.__countSearch = 0;
              window.__resetSearchFetch = () => { window.fetch = original; };
              window.fetch = (input, options) => {
                const url = String(typeof input === "string" ? input : input.url);
                if (url.includes("/api/v1/search")) {
                  window.__countSearch++;
                  return Promise.resolve(new Response(JSON.stringify([]), {
                    status: 200, headers: { "Content-Type": "application/json" }
                  }));
                }
                return original(input, options);
              };
            }"""
        )
        page.locator("#command-trigger").click()
        page.locator("#command-input").fill("unmatched-ui-contract-test")
        page.wait_for_function("() => window.__countSearch >= 1", timeout=10_000)
        page.wait_for_timeout(260)
        assert page.evaluate("() => window.__countSearch") == 1, "Duplicate search fetch"
        page.locator("#command-dialog").evaluate("(dialog) => dialog.close()")
        page.evaluate("() => window.__resetSearchFetch()")

        # Fast navigation must not be overwritten by the first slow audit detail.
        page.evaluate(
            """() => {
              const original = window.fetch.bind(window);
              const audit = (id, title) => JSON.stringify({
                audit_id: id, title, filename: id + ".pdf", status: "ready",
                events: [], paper_summary: { pages: 1, tables_detected: 0, tables: [] }
              });
              window.__resolveSlowAudit = null;
              window.__resetAuditFetch = () => { window.fetch = original; };
              window.fetch = (input, options) => {
                const url = String(typeof input === "string" ? input : input.url);
                if (url.endsWith("/api/v1/audits/audit_slow_a")) {
                  return new Promise((resolve) => {
                    window.__resolveSlowAudit = () => resolve(new Response(
                      audit("audit_slow_a", "Stale paper A"), {
                        status: 200, headers: { "Content-Type": "application/json" }
                      }));
                  });
                }
                if (url.endsWith("/api/v1/audits/audit_fast_b")) {
                  return Promise.resolve(new Response(audit("audit_fast_b", "Selected paper B"), {
                    status: 200, headers: { "Content-Type": "application/json" }
                  }));
                }
                return original(input, options);
              };
            }"""
        )
        page.evaluate("""() => { location.hash = "#audit=audit_slow_a"; }""")
        page.wait_for_function("() => typeof window.__resolveSlowAudit === 'function'")
        page.evaluate("""() => { location.hash = "#audit=audit_fast_b"; }""")
        page.wait_for_function(
            """() => Boolean(document.querySelector(
              '[data-audit-harness="true"][data-audit-id="audit_fast_b"]'
            ) || document.querySelector('.workbench-title')?.textContent === 'Selected paper B')""",
            timeout=15_000,
        )
        page.evaluate("() => window.__resolveSlowAudit()")
        page.wait_for_timeout(100)
        assert page.evaluate(
            """() => location.hash === "#audit=audit_fast_b" &&
              !document.querySelector('[data-audit-harness="true"][data-audit-id="audit_slow_a"]') &&
              document.querySelector('.workbench-title')?.textContent !== 'Stale paper A'"""
        ), "Slow audit response hijacked the selected paper"
        page.evaluate("() => window.__resetAuditFetch()")
        page.goto(args.base_url.rstrip("/") + "/#overview", wait_until="domcontentloaded")
        page.wait_for_function(
            "() => document.querySelector('.page-title')?.textContent?.trim() === 'Overview'",
            timeout=15_000,
        )

        # Validate client-side failures before any POST reaches the backend.
        page.locator("#new-audit").click()
        page.locator("#file-input").set_input_files(
            {"name": "invalid.txt", "mimeType": "text/plain", "buffer": b"not a PDF"}
        )
        assert page.locator("#upload-submit").is_disabled(), "Invalid file accepted"
        assert "Only PDF" in page.locator("#drop-copy").inner_text()
        page.locator("#file-input").set_input_files(
            {"name": "empty.pdf", "mimeType": "application/pdf", "buffer": b""}
        )
        assert page.locator("#upload-submit").is_disabled(), "Empty PDF accepted"
        assert "Empty PDF" in page.locator("#drop-copy").inner_text()
        browser.close()
        print("Interaction checks passed: palette ownership, audit race, invalid upload")


if __name__ == "__main__":
    main()
