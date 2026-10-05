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
        "audit_id": "audit-browser-runs",
        "audit_title": "Paged browser run fixture",
        "run_kind": "replication",
        "task": f"Reproduce {run_id}",
        "tool": "replication.acp",
        "status": "completed",
        "coverage": 0.75,
        "duration_ms": 1250,
        "created_at": "2026-10-01T12:00:00Z",
        "counts": {"verified": 2, "needs_review": 1, "contradictions": 0},
        "evidence": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Exercise bounded Runs pagination in real Chromium.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--output-dir", default="artifacts/ui")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        _wait_for_server(client)

    first_page = [_run(f"run_{index:06d}") for index in reversed(range(10, 60))]
    second_page = [_run(f"run_{index:06d}") for index in reversed(range(10))]
    page_requests: list[str | None] = []
    full_list_requests: list[str] = []
    page_errors: list[str] = []

    def handle_pages(route: Route) -> None:
        parsed = urlparse(route.request.url)
        query = parse_qs(parsed.query)
        cursor = query.get("cursor", [None])[0]
        page_requests.append(cursor)
        if cursor is None:
            payload = {"items": first_page, "next_cursor": "cursor-next", "has_more": True}
        elif cursor == "cursor-next":
            payload = {"items": second_page, "next_cursor": None, "has_more": False}
        else:
            route.fulfill(status=422, json={"detail": "unexpected browser cursor"})
            return
        route.fulfill(status=200, json=payload)

    def handle_runs(route: Route) -> None:
        parsed = urlparse(route.request.url)
        if parsed.path == "/api/v1/runs":
            full_list_requests.append(route.request.url)
            route.abort()
            return
        run_id = parsed.path.rsplit("/", 1)[-1]
        detail = {
            **_run(run_id),
            "artifact_id": "paper-browser-runs",
            "started_at": "2026-10-01T11:59:58Z",
            "finished_at": "2026-10-01T12:00:00Z",
            "parsers": ["browser-fixture"],
            "source": {"table": "Table 1", "row": "Treatment", "page": 3},
            "events": [],
        }
        route.fulfill(status=200, json=detail)

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
        page.route("**/api/v1/run-pages**", handle_pages)
        page.route("**/api/v1/runs**", handle_runs)
        page.goto(f"{base_url}/#runs", wait_until="networkidle")

        surface = page.locator("[data-runs-surface='true']")
        surface.wait_for(state="visible", timeout=20_000)
        rows = page.locator(".run-inspector-row")
        page.wait_for_function(
            """() => document.querySelectorAll('.run-inspector-row').length === 50""",
            timeout=10_000,
        )
        if rows.count() != 50:
            raise AssertionError("Runs UI did not stop at the bounded 50-row first page")
        if full_list_requests:
            raise AssertionError("Product boot escaped the bounded run-page bootstrap")
        if page_requests != [None]:
            raise AssertionError(
                "Runs first page was not reused from product boot: " f"{page_requests!r}"
            )

        load_more = page.locator("[data-run-load-more]")
        load_more.wait_for(state="visible", timeout=10_000)
        if "50 runs loaded" not in page.locator(".run-page-footer").inner_text().lower():
            raise AssertionError("Runs footer did not expose bounded loaded-row state")
        load_more.click()
        page.wait_for_function(
            """() => document.querySelectorAll('.run-inspector-row').length === 60""",
            timeout=10_000,
        )
        if rows.count() != 60:
            raise AssertionError("Runs UI did not append the second validated page")
        ids = rows.evaluate_all("nodes => nodes.map((node) => node.dataset.runId)")
        if len(ids) != len(set(ids)):
            raise AssertionError("Runs pagination introduced duplicate run rows")
        if page.locator("[data-run-load-more]").count() != 0:
            raise AssertionError("Runs UI kept Load more after the terminal page")
        footer = page.locator(".run-page-footer").inner_text().lower()
        if "60 runs loaded" not in footer or "end of validated run history" not in footer:
            raise AssertionError(f"Runs footer lost terminal paging state: {footer!r}")
        if page_requests != [None, "cursor-next"]:
            raise AssertionError(f"Run-page request sequence was not minimal: {page_requests!r}")

        rows.last.click()
        page.wait_for_function(
            """() => document.querySelector('#run-inspector-detail .mono')?.textContent === 'run_000000'""",
            timeout=10_000,
        )
        page.screenshot(path=output_dir / "runs-pagination.png", full_page=True)
        context.close()
        browser.close()

    if page_errors:
        raise AssertionError("Browser page errors: " + " | ".join(page_errors))
    if full_list_requests:
        raise AssertionError("Browser issued an unbounded /api/v1/runs request")
    if page_requests != [None, "cursor-next"]:
        raise AssertionError(f"Run-page request sequence was incomplete: {page_requests!r}")

    screenshot = output_dir / "runs-pagination.png"
    if not screenshot.is_file():
        raise AssertionError("Runs pagination screenshot was not captured")

    print(
        json.dumps(
            {
                "status": "success",
                "first_page_rows": 50,
                "total_rows": 60,
                "full_list_requests": len(full_list_requests),
                "page_requests": page_requests,
                "screenshot": screenshot.name,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
