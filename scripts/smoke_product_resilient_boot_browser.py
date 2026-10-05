from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
from playwright.sync_api import Route, sync_playwright

from smoke_harness_browser import _wait_for_server


def _run(run_id: str) -> dict[str, object]:
    return {
        "run_id": run_id,
        "audit_id": "audit-resilient-boot",
        "audit_title": "Resilient product boot fixture",
        "run_kind": "audit",
        "task": f"Inspect {run_id}",
        "tool": "audit.inspect",
        "status": "completed",
        "coverage": 1.0,
        "duration_ms": 420,
        "created_at": "2026-10-05T01:00:00Z",
        "counts": {"verified": 3, "needs_review": 0, "contradictions": 0},
        "evidence": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exercise partial product boot failure and bounded Runs recovery in real Chromium."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--output-dir", default="artifacts/ui")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        _wait_for_server(client)

    first_page = [_run("run_resilient_000002"), _run("run_resilient_000001")]
    page_requests: list[str | None] = []
    full_list_requests: list[str] = []
    page_errors: list[str] = []
    fail_first_page = True

    def handle_pages(route: Route) -> None:
        nonlocal fail_first_page
        parsed = urlparse(route.request.url)
        cursor = parse_qs(parsed.query).get("cursor", [None])[0]
        page_requests.append(cursor)
        if cursor is not None:
            route.fulfill(status=422, json={"detail": "unexpected resilient-boot cursor"})
            return
        if fail_first_page:
            fail_first_page = False
            route.fulfill(status=503, json={"detail": "temporary run-page failure"})
            return
        route.fulfill(
            status=200,
            json={"items": first_page, "next_cursor": None, "has_more": False},
        )

    def handle_runs(route: Route) -> None:
        parsed = urlparse(route.request.url)
        if parsed.path == "/api/v1/runs":
            full_list_requests.append(route.request.url)
            route.abort()
            return
        run_id = parsed.path.rsplit("/", 1)[-1]
        route.fulfill(
            status=200,
            json={
                **_run(run_id),
                "artifact_id": "paper-resilient-boot",
                "started_at": "2026-10-05T00:59:59Z",
                "finished_at": "2026-10-05T01:00:00Z",
                "parsers": ["browser-fixture"],
                "source": {"table": "Table 1", "row": "Treatment", "page": 2},
                "events": [],
            },
        )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1200},
            device_scale_factor=1,
            locale="en-US",
            color_scheme="dark",
        )
        page = context.new_page()
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.route("**/api/v1/run-pages**", handle_pages)
        page.route("**/api/v1/runs**", handle_runs)
        page.goto(f"{base_url}/#overview", wait_until="networkidle")

        page.locator("#sync-status").wait_for(state="visible", timeout=20_000)
        sync_text = page.locator("#sync-status").inner_text().strip().lower()
        if "partial data" not in sync_text:
            raise AssertionError(
                "A single Runs failure did not leave the rest of the workspace available: "
                f"{sync_text!r}"
            )
        if "offline" in sync_text:
            raise AssertionError("A single Runs failure incorrectly marked the whole product offline")
        if page.locator(".page-title").count() != 1:
            raise AssertionError("Overview did not render after the isolated Runs failure")
        page.screenshot(path=output_dir / "product-partial-data.png", full_page=True)

        page.locator("#sidebar [data-view='runs']").click()
        surface = page.locator("[data-runs-surface='true']")
        surface.wait_for(state="visible", timeout=20_000)
        page.wait_for_function(
            """() => document.querySelectorAll('.run-inspector-row').length === 2""",
            timeout=10_000,
        )
        if page_requests != [None, None]:
            raise AssertionError(
                "Runs did not recover with exactly one authoritative retry after boot failure: "
                f"{page_requests!r}"
            )

        page.locator("#sidebar [data-view='overview']").click()
        page.locator("[data-action='refresh']").click()
        page.wait_for_function(
            """() => document.querySelector('#sync-status span')?.textContent === 'System ready'""",
            timeout=20_000,
        )
        requests_after_refresh = len(page_requests)
        if requests_after_refresh != 3:
            raise AssertionError(
                "Product refresh did not issue exactly one bounded Runs head request: "
                f"{page_requests!r}"
            )

        page.locator("#sidebar [data-view='runs']").click()
        surface.wait_for(state="visible", timeout=20_000)
        page.wait_for_function(
            """() => document.querySelectorAll('.run-inspector-row').length === 2""",
            timeout=10_000,
        )
        if len(page_requests) != requests_after_refresh:
            raise AssertionError(
                "Runs discarded the successful refresh snapshot and re-requested its first page: "
                f"{page_requests!r}"
            )
        if full_list_requests:
            raise AssertionError("Resilient boot escaped to unbounded /api/v1/runs")

        page.screenshot(path=output_dir / "product-resilient-runs.png", full_page=True)
        context.close()
        browser.close()

    if page_errors:
        raise AssertionError("Browser page errors: " + " | ".join(page_errors))
    if full_list_requests:
        raise AssertionError("Browser issued an unbounded /api/v1/runs request")
    if page_requests != [None, None, None]:
        raise AssertionError(f"Unexpected resilient boot request sequence: {page_requests!r}")

    screenshots = ["product-partial-data.png", "product-resilient-runs.png"]
    for name in screenshots:
        if not (output_dir / name).is_file():
            raise AssertionError(f"Resilient boot screenshot was not captured: {name}")

    print(
        json.dumps(
            {
                "status": "success",
                "page_requests": page_requests,
                "full_list_requests": len(full_list_requests),
                "screenshots": screenshots,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
