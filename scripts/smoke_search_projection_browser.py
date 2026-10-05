from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
from playwright.sync_api import sync_playwright

from smoke_harness_browser import _seed_audit, _wait_for_server


def _candidate_queries(audit: dict[str, object]) -> list[tuple[str, dict[str, object]]]:
    metadata = " ".join(
        str(audit.get(key) or "") for key in ("title", "filename", "audit_id")
    ).casefold()
    candidates: list[tuple[str, dict[str, object]]] = []
    for raw_event in reversed(audit.get("events") or []):
        if not isinstance(raw_event, dict):
            continue
        event = dict(raw_event)
        for key in ("detail", "title"):
            source = " ".join(str(event.get(key) or "").split())
            if len(source) < 6:
                continue
            windows = [source]
            if len(source) > 160:
                windows = [source[-160:], source[:160]]
            for value in windows:
                if len(value) > 200 or value.casefold() in metadata:
                    continue
                if len(value) >= 10:
                    inner = value[1:-1]
                    if inner and inner.casefold() not in metadata:
                        candidates.append((inner, event))
                candidates.append((value, event))
    return candidates


def _resolve_event_query(
    client: httpx.Client,
    audit: dict[str, object],
) -> tuple[str, dict[str, object]]:
    audit_id = str(audit.get("audit_id") or "")
    for query, event in _candidate_queries(audit):
        response = client.get("/api/v1/search", params={"q": query, "limit": 50})
        response.raise_for_status()
        payload = response.json()
        if any(
            item.get("kind") == "event"
            and str(item.get("audit_id") or "") == audit_id
            and str(item.get("id") or "") == str(event.get("event_id") or "")
            for item in payload
        ):
            return query, event
    raise AssertionError("Could not derive a real event substring for command search")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exercise authoritative warm event search in real Chromium."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--output-dir", default="artifacts/ui")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(base_url=base_url, timeout=60.0) as client:
        _wait_for_server(client)
        audit_id = _seed_audit(
            client,
            title="Authoritative Search Projection Fixture",
            attach_replication=False,
        )
        detail = client.get(f"/api/v1/audits/{audit_id}")
        detail.raise_for_status()
        audit = detail.json()
        query, event = _resolve_event_query(client, audit)

        # The resolver performs a cold authoritative search. These requests hit
        # the warm product path and must preserve the exact result.
        first_warm = client.get("/api/v1/search", params={"q": query, "limit": 50})
        first_warm.raise_for_status()
        second_warm = client.get("/api/v1/search", params={"q": query, "limit": 50})
        second_warm.raise_for_status()
        if second_warm.json() != first_warm.json():
            raise AssertionError("Warm authoritative search changed without a journal update")

    event_id = str(event.get("event_id") or "")
    page_errors: list[str] = []
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
        page.goto(base_url, wait_until="networkidle")
        page.locator("#command-trigger").click()
        command_input = page.locator("#command-input")
        command_input.wait_for(state="visible", timeout=10_000)

        with page.expect_response(
            lambda response: (
                urlparse(response.url).path == "/api/v1/search"
                and parse_qs(urlparse(response.url).query).get("q") == [query]
            ),
            timeout=20_000,
        ) as response_info:
            command_input.fill(query)
        response = response_info.value
        payload = response.json()
        if not any(
            item.get("kind") == "event"
            and str(item.get("audit_id") or "") == audit_id
            and str(item.get("id") or "") == event_id
            for item in payload
        ):
            raise AssertionError("Chromium search response lost the authoritative event result")

        results = page.locator("#command-results .command-result")
        results.first.wait_for(state="visible", timeout=10_000)
        expected_title = str(event.get("title") or "").strip()
        expected_detail = str(event.get("detail") or "").strip()
        marker = expected_detail or expected_title
        target = results.filter(has_text=marker).first if marker else results.first
        if target.count() == 0:
            raise AssertionError("Authoritative event result did not render in the command palette")

        page.screenshot(
            path=output_dir / "command-search-authoritative-event.png",
            full_page=True,
        )
        target.click()
        page.wait_for_url(f"**?audit_open={audit_id}#audit={audit_id}", timeout=15_000)
        page.locator("[data-audit-harness='true']").wait_for(state="visible", timeout=20_000)
        page.screenshot(
            path=output_dir / "command-search-authoritative-open.png",
            full_page=True,
        )
        context.close()
        browser.close()

    if page_errors:
        raise AssertionError("Browser page errors: " + " | ".join(page_errors))

    screenshots = [
        "command-search-authoritative-event.png",
        "command-search-authoritative-open.png",
    ]
    for name in screenshots:
        if not (output_dir / name).is_file():
            raise AssertionError(f"Search projection screenshot was not captured: {name}")

    print(
        json.dumps(
            {
                "status": "success",
                "audit_id": audit_id,
                "event_id": event_id,
                "query": query,
                "screenshots": screenshots,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
