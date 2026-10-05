from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

from smoke_conversation_browser import run as run_conversation
from smoke_harness_browser import _drain_message, _seed_audit, _wait_for_server


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exercise validated warm Overview activity in real Chromium."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--output-dir", default="artifacts/ui")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    fixture_title = "Overview warm projection fixture"

    with httpx.Client(base_url=base_url, timeout=60.0) as client:
        _wait_for_server(client)
        audit_id = _seed_audit(
            client,
            title=fixture_title,
            attach_replication=False,
        )

        cold = client.get("/api/v1/overview")
        cold.raise_for_status()
        warm = client.get("/api/v1/overview")
        warm.raise_for_status()
        if warm.json() != cold.json():
            raise AssertionError("Warm Overview changed without an authoritative journal update")

        before = [
            item
            for item in (warm.json().get("recent_activity") or [])
            if item.get("audit_id") == audit_id
        ]
        if not before:
            raise AssertionError("Overview fixture is missing from authoritative recent activity")
        previous_event_id = before[0].get("event_id")

        _drain_message(client, audit_id, "/inspect")
        refreshed = client.get("/api/v1/overview")
        refreshed.raise_for_status()
        after = [
            item
            for item in (refreshed.json().get("recent_activity") or [])
            if item.get("audit_id") == audit_id
        ]
        if not after:
            raise AssertionError("Store-managed append disappeared from Overview activity")
        newest = after[0]
        if newest.get("event_id") == previous_event_id:
            raise AssertionError("Overview recent-event projection did not advance after /inspect")
        newest_title = str(newest.get("title") or "")
        if not newest_title:
            raise AssertionError("Newest Overview activity has no renderable title")

        page_errors: list[str] = []
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
            page.goto(base_url, wait_until="networkidle")

            if page.evaluate("document.body.classList.contains('agent-open')"):
                page.locator("#agent-close").click()
                page.wait_for_function(
                    "!document.body.classList.contains('agent-open')",
                    timeout=10_000,
                )

            heading = page.get_by_role("heading", name="Recent activity")
            heading.wait_for(state="visible", timeout=20_000)
            panel = heading.locator("xpath=ancestor::article[1]")
            rows = panel.locator(".status-row")
            rows.first.wait_for(state="visible", timeout=10_000)
            rendered = "\n".join(rows.all_inner_texts())
            if fixture_title not in rendered or newest_title not in rendered:
                raise AssertionError(
                    "Chromium Overview did not render the latest authoritative activity: "
                    f"{rendered!r}"
                )

            with page.expect_response(
                lambda response: response.url.endswith("/api/v1/overview")
                and response.request.method == "GET",
                timeout=20_000,
            ):
                page.locator("[data-action='refresh']").click()
            page.wait_for_function(
                """() => document.querySelector('#sync-status span')?.textContent === 'System ready'""",
                timeout=20_000,
            )
            refreshed_rows = page.get_by_role("heading", name="Recent activity").locator(
                "xpath=ancestor::article[1]"
            ).locator(".status-row")
            rendered_after_refresh = "\n".join(refreshed_rows.all_inner_texts())
            if fixture_title not in rendered_after_refresh or newest_title not in rendered_after_refresh:
                raise AssertionError("Browser Refresh lost warm projected Overview activity")

            screenshot = output_dir / "overview-warm-activity.png"
            page.screenshot(path=screenshot, full_page=True)
            context.close()
            browser.close()

    if page_errors:
        raise AssertionError("Browser page errors: " + " | ".join(page_errors))
    if not (output_dir / "overview-warm-activity.png").is_file():
        raise AssertionError("Overview warm activity screenshot was not captured")

    # Keep the conversation product contract on the existing Chromium workflow path.
    run_conversation(base_url, output_dir)

    print(
        json.dumps(
            {
                "status": "success",
                "audit_id": audit_id,
                "newest_event_id": newest.get("event_id"),
                "newest_title": newest_title,
                "screenshot": "overview-warm-activity.png",
                "conversation_screenshot": "conversation-home.png",
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
