from __future__ import annotations

import argparse
import re
from pathlib import Path

import httpx
from playwright.sync_api import Page, sync_playwright

from smoke_harness_browser import _wait_for_server


def _channels(css_color: str) -> tuple[int, int, int]:
    match = re.match(r"rgba?\(\s*(\d+),\s*(\d+),\s*(\d+)", css_color)
    if not match:
        raise AssertionError(f"Unexpected computed CSS color: {css_color!r}")
    return tuple(int(value) for value in match.groups())


def _assert_dark(page: Page, selector: str, label: str) -> None:
    node = page.locator(selector).first
    node.wait_for(state="attached", timeout=20_000)
    color = node.evaluate("(el) => getComputedStyle(el).backgroundColor")
    channels = _channels(color)
    if max(channels) > 50:
        raise AssertionError(
            f"{label}: {selector} has a light surface {color}; "
            "expected the Audit Workbench charcoal palette"
        )


def _close_conversation(page: Page) -> None:
    if page.evaluate("document.body.classList.contains('agent-open')"):
        page.locator("#agent-close").click()
        page.wait_for_function(
            "!document.body.classList.contains('agent-open')", timeout=10_000
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check consistent dark backgrounds across Veritas web workspace routes."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/ui"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    base_url = args.base_url.rstrip("/")

    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        _wait_for_server(client)
        response = client.get("/api/v1/audit-pages?limit=1")
        response.raise_for_status()
        audits = response.json().get("items") or []
        audit_id = audits[0].get("audit_id") if audits else None

    page_errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 960},
            device_scale_factor=1,
            color_scheme="dark",
        )
        page = context.new_page()
        page.on("pageerror", lambda error: page_errors.append(str(error)))

        for view in (
            "overview", "audits", "findings", "runs",
            "evidence", "reproduction", "benchmarks", "settings",
        ):
            # Exercise the same navigation path as users.  A hash alone is
            # not sufficient when the application has already booted and
            # asynchronous feature renderers are still initializing.
            page.goto(f"{base_url}/#overview", wait_until="networkidle")
            _close_conversation(page)
            if view != "overview":
                page.locator(f".sidebar [data-view='{view}']").click()
            page.wait_for_function(
                "(expected) => location.hash === '#' + expected",
                arg=view,
                timeout=20_000,
            )
            page.locator("#main-content > *").first.wait_for(
                state="visible", timeout=20_000
            )
            _assert_dark(page, "html", view)
            _assert_dark(page, "#main-content", view)
            _assert_dark(page, ".topbar", view)
            if page.locator(".panel").count():
                _assert_dark(page, ".panel", view)
            for selector in {
                "overview": (".kpi-card", ".data-table th"),
                "audits": (".data-table th",),
                "findings": (".finding-card",),
                "runs": (".run-detail-shell",),
                "benchmarks": (".benchmark-card",),
            }.get(view, ()):
                if page.locator(selector).count():
                    _assert_dark(page, selector, view)
            if view == "benchmarks":
                page.locator("[data-benchmark-surface='true']").wait_for(
                    state="visible", timeout=20_000
                )
                if page.locator(".benchmark-card").count():
                    _assert_dark(page, ".benchmark-card", view)
            page.screenshot(
                path=args.output_dir / f"workspace-dark-{view}.png",
                full_page=True,
            )

        if audit_id:
            # Exercise hash-only SPA navigation from a different view. This
            # guards the route-sync fix and the audit-specific theme together.
            page.goto(f"{base_url}/#audit={audit_id}", wait_until="networkidle")
            page.wait_for_function(
                "document.body.classList.contains('reference-audit-active')",
                timeout=20_000,
            )
            _close_conversation(page)
            _assert_dark(page, "#main-content", "audit workbench")
            page.screenshot(
                path=args.output_dir / "workspace-dark-audit-workbench.png",
                full_page=True,
            )

        # Navigate back without a full reload: the app must leave audit mode.
        page.goto(f"{base_url}/#overview", wait_until="networkidle")
        page.locator(".page-title").first.wait_for(state="visible", timeout=20_000)
        _close_conversation(page)
        page.locator("#command-trigger").click()
        _assert_dark(page, "#command-dialog", "command search")
        page.keyboard.press("Escape")
        page.locator("#new-audit").click()
        _assert_dark(page, "#upload-dialog", "upload dialog")
        page.locator("#upload-close").click()
        page.locator("#agent-toggle").click()
        _assert_dark(page, "#agent-sidecar", "conversation sidecar")

        mobile = browser.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=1,
            is_mobile=True,
            has_touch=True,
            color_scheme="dark",
        )
        mobile_page = mobile.new_page()
        mobile_page.goto(f"{base_url}/#overview", wait_until="networkidle")
        _assert_dark(mobile_page, "#main-content", "mobile web overview")
        _assert_dark(mobile_page, ".mobile-nav", "mobile web navigation")
        mobile_page.screenshot(
            path=args.output_dir / "workspace-dark-mobile-web.png",
            full_page=True,
        )
        mobile.close()
        context.close()
        browser.close()

    if page_errors:
        raise AssertionError("Browser page errors: " + " | ".join(page_errors))


if __name__ == "__main__":
    main()
