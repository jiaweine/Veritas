from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the Benchmarks product surface in Chromium.")
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

    page_errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1200})
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.goto(args.base_url, wait_until="domcontentloaded")
        benchmarks_nav = page.locator(".sidebar [data-view='benchmarks']")
        benchmarks_nav.wait_for(state="visible", timeout=20_000)
        benchmarks_nav.click()

        surface = page.locator("[data-benchmark-surface='true']")
        surface.wait_for(state="visible", timeout=20_000)
        if benchmarks_nav.get_attribute("class") is None or "active" not in benchmarks_nav.get_attribute("class"):
            raise AssertionError("Benchmarks navigation did not become active after user-visible click")

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

        text = surface.inner_text()
        for expected in (
            "5 gating",
            "4 probes",
            "Locked AuditBench detector gate",
            "Locked AuditBench v0.2 detector pack",
            "No result envelope has been ingested locally yet.",
        ):
            if expected not in text:
                raise AssertionError(f"Benchmarks surface is missing {expected!r}")

        if page_errors:
            raise AssertionError(f"Benchmarks page raised browser errors: {page_errors}")
        page.screenshot(path=args.output_dir / "benchmarks-workspace.png", full_page=True)
        browser.close()

    print(
        json.dumps(
            {
                "gating": 5,
                "navigation": "sidebar-click",
                "non_gating": 4,
                "screenshot": "benchmarks-workspace.png",
                "status": "success",
                "suite_count": 9,
            },
            sort_keys=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
