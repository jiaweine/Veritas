from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

import httpx
from playwright.sync_api import Route, sync_playwright

from smoke_harness_browser import _wait_for_server


def _audit_detail(audit_id: str) -> dict[str, object]:
    return {
        "audit_id": audit_id,
        "title": "Older authoritative audit",
        "filename": "older-authoritative.pdf",
        "status": "ready",
        "created_at": "2026-10-01T10:00:00Z",
        "updated_at": "2026-10-02T10:00:00Z",
        "artifact_sha256": "0" * 64,
        "paper_summary": {"pages": 1, "tables_detected": 0, "words": 10, "tables": []},
        "latest_result": None,
        "events": [],
        "attachments": [],
        "notes": "",
        "notes_updated_at": None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Exercise race-safe command search in real Chromium.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--output-dir", default="artifacts/ui")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        _wait_for_server(client)

    detail_requests: list[str] = []
    page_errors: list[str] = []
    target_audit = "audit_search_older"

    def handle_detail(route: Route) -> None:
        parsed = urlparse(route.request.url)
        if parsed.path == f"/api/v1/audits/{target_audit}":
            detail_requests.append(target_audit)
            route.fulfill(status=200, json=_audit_detail(target_audit))
            return
        route.continue_()

    init_script = r"""
(() => {
  const originalFetch = window.fetch.bind(window);
  const probe = { calls: [], aborted: [], failures: {} };
  window.__veritasCommandSearchProbe = probe;
  window.fetch = (input, init = {}) => {
    const request = input instanceof Request ? input : new Request(input, init);
    const url = new URL(request.url, window.location.href);
    if (url.pathname !== '/api/v1/search') return originalFetch(input, init);
    const query = url.searchParams.get('q') || '';
    probe.calls.push(query);
    const signal = init?.signal || request.signal;
    const payload = (items) => new Response(JSON.stringify(items), {
      status: 200,
      headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
    });
    const delayed = (ms, items) => new Promise((resolve, reject) => {
      const timer = setTimeout(() => resolve(payload(items)), ms);
      const abort = () => {
        clearTimeout(timer);
        probe.aborted.push(query);
        reject(new DOMException('Aborted', 'AbortError'));
      };
      if (signal?.aborted) abort();
      else signal?.addEventListener('abort', abort, { once: true });
    });
    if (query === 'alpha') {
      return delayed(700, [{ kind: 'audit', id: 'audit_stale_alpha', audit_id: 'audit_stale_alpha', title: 'STALE alpha result', detail: 'must never win' }]);
    }
    if (query === 'alphabet') {
      return delayed(40, [{ kind: 'audit', id: 'audit_fresh_alphabet', audit_id: 'audit_fresh_alphabet', title: 'Fresh alphabet result', detail: 'newest query wins' }]);
    }
    if (query === 'old') {
      return delayed(20, [{ kind: 'audit', id: 'audit_old', audit_id: 'audit_old', title: 'Debounced old result', detail: 'single request' }]);
    }
    if (query === 'recover') {
      probe.failures[query] = (probe.failures[query] || 0) + 1;
      if (probe.failures[query] === 1) return Promise.reject(new TypeError('synthetic network failure'));
      return delayed(20, [{ kind: 'audit', id: 'audit_recovered', audit_id: 'audit_recovered', title: 'Recovered search result', detail: 'retry succeeded' }]);
    }
    if (query === 'older') {
      return delayed(20, [{ kind: 'audit', id: 'audit_search_older', audit_id: 'audit_search_older', title: 'Older authoritative audit', detail: 'outside product boot head' }]);
    }
    return delayed(20, []);
  };
})();
"""

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1536, "height": 960},
            device_scale_factor=1,
            locale="en-US",
            color_scheme="dark",
        )
        page = context.new_page()
        page.add_init_script(init_script)
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.route("**/api/v1/audits/**", handle_detail)
        page.goto(f"{base_url}/", wait_until="domcontentloaded")
        page.locator("#command-trigger").click()
        command_input = page.locator("#command-input")
        command_input.wait_for(state="visible", timeout=10_000)

        # First request is allowed to leave the debounce window, then a newer
        # query must abort it and remain authoritative even after the stale
        # response's original completion time has passed.
        command_input.fill("alpha")
        page.wait_for_timeout(240)
        command_input.fill("alphabet")
        page.locator("text=Fresh alphabet result").wait_for(state="visible", timeout=5_000)
        page.wait_for_timeout(800)
        if page.locator("text=STALE alpha result").count():
            raise AssertionError("An older search response overwrote the newest command query")
        probe = page.evaluate("window.__veritasCommandSearchProbe")
        if "alpha" not in probe["aborted"]:
            raise AssertionError(f"Superseded command search was not aborted: {probe!r}")

        # Rapid typing inside the debounce window should produce only the final
        # server search, avoiding one full journal scan per keystroke.
        command_input.fill("o")
        page.wait_for_timeout(30)
        command_input.fill("ol")
        page.wait_for_timeout(30)
        command_input.fill("old")
        page.locator("text=Debounced old result").wait_for(state="visible", timeout=5_000)
        calls = page.evaluate("window.__veritasCommandSearchProbe.calls")
        if calls.count("old") != 1 or "o" in calls or "ol" in calls:
            raise AssertionError(f"Command search escaped its debounce boundary: {calls!r}")

        # Failure is explicit and recoverable rather than silently replacing a
        # remote query with stale/local-only results.
        command_input.fill("recover")
        retry = page.locator("[data-command-search-retry='true']")
        retry.wait_for(state="visible", timeout=5_000)
        if "synthetic network failure" not in page.locator("[data-command-search-error='true']").inner_text():
            raise AssertionError("Command search failure state did not expose the request error")
        retry.click()
        page.locator("text=Recovered search result").wait_for(state="visible", timeout=5_000)

        # A remote result that was never part of product boot state must still
        # enter the existing server-backed audit detail path.
        command_input.fill("older")
        result = page.locator("text=Older authoritative audit")
        result.wait_for(state="visible", timeout=5_000)
        page.screenshot(path=output_dir / "command-search-race-safe.png", full_page=True)
        result.click()
        page.wait_for_url(f"**?audit_open={target_audit}#audit={target_audit}", timeout=10_000)
        page.locator("[data-audit-harness='true']").wait_for(state="visible", timeout=20_000)
        if target_audit not in detail_requests:
            raise AssertionError("Search result did not reach the authoritative audit detail API")
        page.screenshot(path=output_dir / "command-search-open-remote.png", full_page=True)

        context.close()
        browser.close()

    if page_errors:
        raise AssertionError("Browser page errors: " + " | ".join(page_errors))
    if target_audit not in detail_requests:
        raise AssertionError(f"Missing command-search detail request: {detail_requests!r}")

    screenshots = ["command-search-race-safe.png", "command-search-open-remote.png"]
    for name in screenshots:
        if not (output_dir / name).is_file():
            raise AssertionError(f"Command search screenshot was not captured: {name}")

    print(
        json.dumps(
            {
                "status": "success",
                "detail_requests": detail_requests,
                "screenshots": screenshots,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
