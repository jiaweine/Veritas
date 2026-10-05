from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx
from playwright.sync_api import Route, sync_playwright

from smoke_harness_browser import _seed_contradiction_audit, _wait_for_server


def run(base_url: str, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        _wait_for_server(client)
        audit_id, _ = _seed_contradiction_audit(client)
        audit = client.get(f"/api/v1/audits/{audit_id}").json()
        audit_title = audit["title"]
        # Build a history longer than the product detail tail. The browser must
        # still request only the bounded product projection.
        for _ in range(16):
            response = client.post(
                f"/api/v1/audits/{audit_id}/messages",
                json={"message": "What needs attention?"},
            )
            response.raise_for_status()
            _ = response.read()
        assert len(client.get(f"/api/v1/audits/{audit_id}").json()["events"]) > 24

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1536, "height": 960})
        detail_gets: list[str] = []
        legacy_detail_gets: list[str] = []

        def observe_request(request) -> None:
            if request.method != "GET" or f"/api/v1/audits/{audit_id}" not in request.url:
                return
            if "/product-detail" in request.url:
                detail_gets.append(request.url)
                return
            if request.url.split("?", 1)[0].rstrip("/").endswith(f"/api/v1/audits/{audit_id}"):
                legacy_detail_gets.append(request.url)

        page.on("request", observe_request)
        page.goto(f"{base_url}/", wait_until="networkidle")
        page.wait_for_function("document.body.classList.contains('agent-open')", timeout=20_000)

        sidecar = page.locator("#agent-sidecar")
        sidecar.wait_for(state="visible", timeout=10_000)
        if "Research conversation" not in sidecar.inner_text():
            raise AssertionError("Default product entry is not the research conversation")
        context = page.locator("#agent-context")
        if audit_title not in context.inner_text():
            raise AssertionError("Conversation did not select the latest authoritative paper context")

        composer = page.locator("#agent-message")
        if composer.is_disabled():
            raise AssertionError("Conversation composer stayed disabled with an active audit")
        if not detail_gets or any("event_limit=24" not in url for url in detail_gets):
            raise AssertionError(f"Conversation did not use bounded audit detail: {detail_gets!r}")
        if legacy_detail_gets:
            raise AssertionError(f"Browser hydrated legacy full audit detail: {legacy_detail_gets!r}")
        if page.locator("#agent-timeline .trace").count() > 24:
            raise AssertionError("Conversation rendered more than the bounded event tail")

        failed_once = {"value": False}

        def fail_first_message(route: Route) -> None:
            if failed_once["value"]:
                route.continue_()
                return
            failed_once["value"] = True
            route.fulfill(
                status=503,
                content_type="application/json",
                body=json.dumps({"detail": "temporary conversation failure"}),
            )

        page.route("**/api/v1/audits/*/messages", fail_first_message)
        composer.fill("What needs attention?")
        page.locator("#agent-send").click()
        page.wait_for_function(
            """() => (document.querySelector('#toast')?.textContent || '').includes('Conversation failed')""",
            timeout=10_000,
        )
        toast_text = page.locator("#toast").inner_text()
        if "Conversation failed" not in toast_text:
            raise AssertionError(f"Conversation failure was not surfaced clearly: {toast_text!r}")
        if composer.input_value() != "What needs attention?":
            raise AssertionError("Failed conversation request did not restore the user's draft")
        if composer.is_disabled():
            raise AssertionError("Conversation composer did not recover after request failure")
        page.unroute("**/api/v1/audits/*/messages", fail_first_message)

        page.locator("#agent-send").click()
        page.wait_for_function(
            """() => {
              const text = document.querySelector('#agent-timeline')?.textContent || '';
              return text.includes('Current audit summary') && text.includes('Regression reporting contradiction');
            }""",
            timeout=20_000,
        )
        if composer.input_value():
            raise AssertionError("Successful conversation send did not clear the composer")
        if page.locator("#toast").evaluate("node => node.classList.contains(\'show\')"):
            raise AssertionError("Recovered conversation still shows a stale failure toast")
        if page.locator("#toast").inner_text().strip():
            raise AssertionError("Recovered conversation retained stale failure text")

        page.screenshot(path=output_dir / "conversation-home.png", full_page=True)
        page.reload(wait_until="networkidle")
        page.wait_for_function("document.body.classList.contains('agent-open')", timeout=20_000)
        page.wait_for_function(
            """() => (document.querySelector('#agent-timeline')?.textContent || '').includes('Current audit summary')""",
            timeout=20_000,
        )
        timeline = page.locator("#agent-timeline").inner_text()
        if any("event_limit=24" not in url for url in detail_gets):
            raise AssertionError(f"Refresh escaped bounded audit detail: {detail_gets!r}")
        if legacy_detail_gets:
            raise AssertionError(f"Refresh hydrated legacy full audit detail: {legacy_detail_gets!r}")
        if "What needs attention?" not in timeline:
            raise AssertionError("Persisted user message disappeared after refresh")

        page.locator("#agent-close").click()
        page.wait_for_function("!document.body.classList.contains('agent-open')", timeout=10_000)
        workspace = page.locator("#main-content")
        if "Evidence, findings, and runs" not in workspace.inner_text():
            raise AssertionError("Closing conversation did not reveal the secondary workspace")
        page.locator("#conversation-nav").click()
        page.wait_for_function("document.body.classList.contains('agent-open')", timeout=10_000)
        browser.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    run(args.base_url.rstrip("/"), args.output_dir)


if __name__ == "__main__":
    main()
