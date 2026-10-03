from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
from playwright.sync_api import Route, sync_playwright


def _wait_for_server(client: httpx.Client, timeout_seconds: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            response = client.get("/api/v1/health")
            if response.status_code == 200:
                return
        except httpx.HTTPError as exc:
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"Veritas harness did not become ready: {last_error}")


def _result(index: int) -> dict[str, object]:
    finished = datetime(2026, 10, 3, 16, 0, tzinfo=UTC) - timedelta(minutes=index)
    return {
        "result_id": f"bmr_{index + 1:016x}",
        "benchmark_id": "pdf-regression",
        "title": "Locked PDF extraction regression",
        "kind": "pdf extraction",
        "gating": True,
        "status": "passed",
        "source": "ci",
        "finished_at": finished.isoformat().replace("+00:00", "Z"),
        "commit_sha": f"{index + 1:040x}",
        "summary": f"Persisted browser fixture result {index + 1}.",
        "metrics": {"cases": 48, "verification_rate": 1.0},
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate the Benchmarks product surface in Chromium."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/ui"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(base_url=args.base_url, timeout=10.0) as client:
        _wait_for_server(client)
        catalog_response = client.get("/api/v1/benchmarks")
        catalog_response.raise_for_status()
        catalog = catalog_response.json()
        if catalog.get("gating_count") != 5 or catalog.get("non_gating_count") != 4:
            raise AssertionError(f"Unexpected benchmark catalog counts: {catalog}")
        if len(catalog.get("suites") or []) != 9:
            raise AssertionError(f"Expected 9 product-visible benchmark suites: {catalog}")
        if catalog.get("results_available") or catalog.get("result_count") != 0:
            raise AssertionError(f"Expected isolated browser harness to start without results: {catalog}")

    results = [_result(index) for index in range(60)]
    browser_catalog = dict(catalog)
    browser_catalog["result_count"] = 60
    browser_catalog["results_available"] = True
    browser_catalog["latest_results"] = {"pdf-regression": results[0]}
    legacy_list_requests: list[str] = []
    page_requests: list[str] = []

    def handle_catalog(route: Route) -> None:
        route.fulfill(json=browser_catalog)

    def handle_pages(route: Route) -> None:
        page_requests.append(route.request.url)
        query = parse_qs(urlparse(route.request.url).query)
        cursor = (query.get("cursor") or [None])[0]
        limit = int((query.get("limit") or ["50"])[0])
        start = 0 if cursor is None else 50 if cursor == "benchmark-page-2" else -1
        if start < 0:
            route.fulfill(status=422, json={"detail": "invalid benchmark result cursor"})
            return
        items = results[start : start + limit]
        has_more = start + limit < len(results)
        route.fulfill(
            json={
                "items": items,
                "next_cursor": "benchmark-page-2" if has_more else None,
                "has_more": has_more,
                "total": len(results),
            }
        )

    def handle_legacy_list(route: Route) -> None:
        legacy_list_requests.append(route.request.url)
        route.abort()

    page_errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)

        # Keep the original empty-state acceptance path real and unmocked. The
        # paged fixture below then proves the 50 -> 60 persisted-history path.
        empty_page = browser.new_page(viewport={"width": 1440, "height": 1200})
        empty_page.on("pageerror", lambda error: page_errors.append(str(error)))
        empty_page.goto(args.base_url, wait_until="domcontentloaded")
        empty_nav = empty_page.locator(".sidebar [data-view='benchmarks']")
        empty_nav.wait_for(state="visible", timeout=20_000)
        empty_nav.click()
        empty_surface = empty_page.locator("[data-benchmark-surface='true']")
        empty_surface.wait_for(state="visible", timeout=20_000)
        empty_disclosure = "No result envelope has been ingested locally yet."
        if empty_disclosure not in empty_surface.inner_text():
            raise AssertionError("Benchmarks empty state stopped disclosing local result absence")
        empty_page.screenshot(path=args.output_dir / "benchmarks-workspace.png", full_page=True)
        empty_page.close()

        page = browser.new_page(viewport={"width": 1440, "height": 1200})
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.route("**/api/v1/benchmarks", handle_catalog)
        page.route("**/api/v1/benchmark-result-pages**", handle_pages)
        page.route("**/api/v1/benchmark-results**", handle_legacy_list)
        page.goto(args.base_url, wait_until="domcontentloaded")
        benchmarks_nav = page.locator(".sidebar [data-view='benchmarks']")
        benchmarks_nav.wait_for(state="visible", timeout=20_000)
        benchmarks_nav.click()

        surface = page.locator("[data-benchmark-surface='true']")
        surface.wait_for(state="visible", timeout=20_000)
        nav_class = benchmarks_nav.get_attribute("class") or ""
        if "active" not in nav_class:
            raise AssertionError(
                "Benchmarks navigation did not become active after user-visible click"
            )

        cards = page.locator(".benchmark-card")
        if cards.count() != 9:
            raise AssertionError(f"Expected 9 benchmark cards, found {cards.count()}")

        for benchmark_id in ("auditbench-v1", "auditbench-v02-pack"):
            card = page.locator(f"[data-benchmark-id='{benchmark_id}']")
            card.wait_for(state="visible", timeout=10_000)
            if "release gate" not in card.inner_text().lower():
                raise AssertionError(f"{benchmark_id} is not rendered as a release gate")
            if "no local result" not in card.inner_text().lower():
                raise AssertionError(f"{benchmark_id} did not disclose empty local ingestion state")

        rows = page.locator("[data-benchmark-result-id]")
        page.wait_for_function(
            "() => document.querySelectorAll('[data-benchmark-result-id]').length === 50",
            timeout=20_000,
        )
        if rows.count() != 50:
            raise AssertionError("Benchmarks UI did not stop at the bounded 50-row first page")
        if "50 / 60" not in page.locator("[data-benchmark-history]").inner_text():
            raise AssertionError("Benchmarks history did not disclose the server-reported total")
        page.screenshot(path=args.output_dir / "benchmarks-history-page-1.png", full_page=True)

        load_more = page.locator("[data-benchmark-load-more]")
        load_more.wait_for(state="visible", timeout=10_000)
        load_more.click()
        page.wait_for_function(
            "() => document.querySelectorAll('[data-benchmark-result-id]').length === 60",
            timeout=20_000,
        )
        ids = page.locator("[data-benchmark-result-id]").evaluate_all(
            "nodes => nodes.map(node => node.getAttribute('data-benchmark-result-id'))"
        )
        if len(ids) != 60 or len(set(ids)) != 60:
            raise AssertionError("Benchmarks pagination introduced duplicate result rows")
        history_text = page.locator("[data-benchmark-history]").inner_text()
        if "Loaded all 60 persisted results." not in history_text:
            raise AssertionError("Benchmarks history did not render a terminal loaded state")
        if legacy_list_requests:
            raise AssertionError(
                "Benchmarks product escaped cursor paging via legacy list requests: "
                f"{legacy_list_requests}"
            )

        page.locator("[data-benchmark-result-id]").last.locator("summary").click()
        page.screenshot(path=args.output_dir / "benchmarks-history-60.png", full_page=True)

        text = surface.inner_text()
        for expected in (
            "5 gating",
            "4 probes",
            "Locked AuditBench detector gate",
            "Locked AuditBench v0.2 detector pack",
            "Persisted result history",
        ):
            if expected not in text:
                raise AssertionError(f"Benchmarks surface is missing {expected!r}")

        if page_errors:
            raise AssertionError(f"Benchmarks page raised browser errors: {page_errors}")
        browser.close()

    print(
        json.dumps(
            {
                "empty_state": "verified",
                "first_page_rows": 50,
                "gating": 5,
                "legacy_list_requests": len(legacy_list_requests),
                "navigation": "sidebar-click",
                "non_gating": 4,
                "page_requests": len(page_requests),
                "screenshots": [
                    "benchmarks-workspace.png",
                    "benchmarks-history-page-1.png",
                    "benchmarks-history-60.png",
                ],
                "status": "success",
                "suite_count": 9,
                "total_rows": 60,
            },
            sort_keys=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
