from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
from playwright.sync_api import Route, sync_playwright

from smoke_harness_browser import _wait_for_server


def _finding(index: int) -> dict[str, object]:
    audit_id = f"audit_finding_{index:06d}"
    return {
        "finding_id": f"{audit_id}:finding:0",
        "audit_id": audit_id,
        "audit_title": f"Finding audit {index:02d}",
        "title": f"Contradiction {index:02d}",
        "explanation": f"Evidence-linked finding {index:02d}.",
        "severity": "contradiction" if index >= 15 else "warning" if index >= 5 else "info",
        "source": {"page": 3, "table": "Table 2", "row": f"Treatment {index:02d}"},
        "updated_at": f"2026-10-02T12:{index % 60:02d}:00Z",
    }


def _audit_detail(item: dict[str, object]) -> dict[str, object]:
    audit_id = str(item["audit_id"])
    return {
        "audit_id": audit_id,
        "title": item["audit_title"],
        "filename": f"{audit_id}.pdf",
        "status": "ready",
        "created_at": item["updated_at"],
        "updated_at": item["updated_at"],
        "artifact_sha256": f"{audit_id:0<64}"[:64],
        "paper_summary": {"pages": 12, "words": 4200, "tables_detected": 3, "tables": []},
        "latest_result": {
            "status": "contradiction",
            "verification_coverage": 0.8,
            "source": item["source"],
            "counts": {"verified": 3, "needs_review": 0, "contradictions": 1},
            "checks": [],
            "findings": [
                {
                    "title": item["title"],
                    "explanation": item["explanation"],
                    "severity": item["severity"],
                    "source": item["source"],
                }
            ],
        },
        "attachments": [],
        "events": [],
        "notes": "",
        "notes_updated_at": None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Exercise bounded Finding pagination in real Chromium.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--output-dir", default="artifacts/ui")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        _wait_for_server(client)

    ordered = [_finding(index) for index in reversed(range(60))]
    findings_by_audit = {str(item["audit_id"]): item for item in ordered}
    first_page = ordered[:50]
    second_page = ordered[50:]
    severity_counts = {"contradiction": 45, "warning": 10, "info": 5}
    page_requests: list[str | None] = []
    full_list_requests: list[str] = []
    detail_requests: list[str] = []
    page_errors: list[str] = []

    def handle_pages(route: Route) -> None:
        parsed = urlparse(route.request.url)
        query = parse_qs(parsed.query)
        cursor = query.get("cursor", [None])[0]
        page_requests.append(cursor)
        if cursor is None:
            payload = {
                "items": first_page,
                "next_cursor": "cursor-next",
                "has_more": True,
                "total": 60,
                "severity_counts": severity_counts,
            }
        elif cursor == "cursor-next":
            payload = {
                "items": second_page,
                "next_cursor": None,
                "has_more": False,
                "total": 60,
                "severity_counts": severity_counts,
            }
        else:
            route.fulfill(status=422, json={"detail": "unexpected browser cursor"})
            return
        route.fulfill(status=200, json=payload)

    def handle_findings(route: Route) -> None:
        parsed = urlparse(route.request.url)
        if parsed.path == "/api/v1/findings" and not parsed.query:
            full_list_requests.append(route.request.url)
            route.abort()
            return
        route.continue_()

    def handle_audits(route: Route) -> None:
        parsed = urlparse(route.request.url)
        prefix = "/api/v1/audits/"
        if parsed.path.startswith(prefix) and parsed.path.count("/") == 4:
            audit_id = parsed.path[len(prefix) :]
            item = findings_by_audit.get(audit_id)
            if item is not None:
                detail_requests.append(audit_id)
                route.fulfill(status=200, json=_audit_detail(item))
                return
        route.continue_()

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
        page.route("**/api/v1/finding-pages**", handle_pages)
        page.route("**/api/v1/findings**", handle_findings)
        page.route("**/api/v1/audits/**", handle_audits)
        page.goto(f"{base_url}/#findings", wait_until="domcontentloaded")

        page.wait_for_function(
            """() => document.querySelector('.page-title')?.textContent?.trim() === 'Findings'""",
            timeout=20_000,
        )
        page.wait_for_function(
            """() => document.querySelectorAll('[data-finding-page-id]').length === 50""",
            timeout=20_000,
        )
        assert page.locator("#finding-count").inner_text() == "60"
        initial_ids = page.locator("[data-finding-page-id]").evaluate_all(
            "(nodes) => nodes.map((node) => node.dataset.findingPageId)"
        )
        assert initial_ids == [str(item["finding_id"]) for item in first_page]
        page.screenshot(path=str(output_dir / "findings-pagination.png"), full_page=True)

        page.get_by_role("button", name="Load 50 more").click()
        page.wait_for_function(
            """() => document.querySelectorAll('[data-finding-page-id]').length === 60""",
            timeout=20_000,
        )
        all_ids = page.locator("[data-finding-page-id]").evaluate_all(
            "(nodes) => nodes.map((node) => node.dataset.findingPageId)"
        )
        assert all_ids == [str(item["finding_id"]) for item in ordered]
        assert len(all_ids) == len(set(all_ids)) == 60
        assert "Loaded all 60 findings" in page.locator(".finding-page-footer").inner_text()

        # A fresh legacy product read must reset the mutable latest-result projection
        # to the new first page instead of keeping older findings from a prior feed.
        page.evaluate("() => fetch('/api/v1/findings').then((response) => response.json())")
        page.wait_for_function(
            """() => document.querySelectorAll('[data-finding-page-id]').length === 50""",
            timeout=20_000,
        )
        reset_ids = page.locator("[data-finding-page-id]").evaluate_all(
            "(nodes) => nodes.map((node) => node.dataset.findingPageId)"
        )
        assert reset_ids == [str(item["finding_id"]) for item in first_page]

        page.get_by_role("button", name="Load 50 more").click()
        page.wait_for_function(
            """() => document.querySelectorAll('[data-finding-page-id]').length === 60""",
            timeout=20_000,
        )

        target = second_page[-1]
        target_id = str(target["finding_id"])
        page.locator(f'[data-finding-page-id="{target_id}"]').click()
        page.wait_for_function(
            f"""() => location.hash === '#audit={target["audit_id"]}'""",
            timeout=20_000,
        )
        page.wait_for_function(
            f"""() => document.querySelector('.workbench-title')?.textContent?.trim() === '{target["audit_title"]}'""",
            timeout=20_000,
        )
        assert str(target["audit_id"]) in detail_requests
        page.screenshot(path=str(output_dir / "paged-finding-open.png"), full_page=True)

        context.close()
        browser.close()

    assert not full_list_requests, full_list_requests
    assert not page_errors, page_errors
    assert page_requests.count(None) >= 2
    assert page_requests.count("cursor-next") >= 2

    print(
        json.dumps(
            {
                "status": "success",
                "first_page_rows": 50,
                "total_rows": 60,
                "full_list_requests": len(full_list_requests),
                "page_requests": page_requests,
                "detail_requests": detail_requests,
                "screenshots": ["findings-pagination.png", "paged-finding-open.png"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
