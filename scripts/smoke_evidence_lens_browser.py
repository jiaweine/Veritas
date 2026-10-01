from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import quote

import httpx
from playwright.sync_api import sync_playwright

from smoke_harness_browser import _seed_audit, _wait_for_server


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exercise the pointer-reactive evidence lens in real Chromium."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--output-dir", default="artifacts/ui")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(base_url=base_url, timeout=60.0) as client:
        _wait_for_server(client)
        audit_id = _seed_audit(client, title="Cyber Evidence Lens")

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
        page.goto(f"{base_url}/#audit={quote(audit_id, safe='')}", wait_until="networkidle")

        preview = page.locator("[data-reference-evidence-preview='true']")
        preview.wait_for(state="visible", timeout=20_000)
        page.wait_for_function(
            """() => document.querySelector('[data-reference-evidence-preview="true"]')?.dataset.evidenceLensBound === 'true'""",
            timeout=10_000,
        )
        hud = page.locator("[data-evidence-lens-hud='true']")
        hud.wait_for(state="visible", timeout=10_000)
        beta = page.locator("[data-ref-field='beta']")
        beta.hover(position={"x": 20, "y": 12})
        page.wait_for_function(
            """() => {
              const preview = document.querySelector('[data-reference-evidence-preview="true"]');
              const beta = document.querySelector('[data-ref-field="beta"]');
              return preview?.dataset.evidenceLensPointer === 'active'
                && preview?.dataset.evidenceLensState === 'hover'
                && beta?.dataset.lensHover === 'true';
            }""",
            timeout=10_000,
        )
        hover_text = hud.inner_text()
        if "Estimate" not in hover_text or "-0.021" not in hover_text:
            raise AssertionError(f"Evidence lens did not expose the hovered persisted value: {hover_text!r}")

        beta.click()
        page.wait_for_function(
            """() => {
              const preview = document.querySelector('[data-reference-evidence-preview="true"]');
              const beta = document.querySelector('[data-ref-field="beta"]');
              return preview?.dataset.evidenceLensState === 'pinned'
                && preview?.dataset.evidenceLensPinned === 'beta'
                && beta?.dataset.lensPinned === 'true';
            }""",
            timeout=10_000,
        )
        if beta.get_attribute("aria-pressed") != "true":
            raise AssertionError("Pinned evidence field is not exposed through aria-pressed")
        if "FIELD LOCK" not in hud.inner_text():
            raise AssertionError("Evidence lens HUD did not enter the pinned field-lock state")
        page.screenshot(path=output_dir / "audit-evidence-lens.png", full_page=True)

        page.locator("[data-evidence-open-graph='beta']").click()
        graph = page.locator("[data-reference-claim-graph='true']")
        graph.wait_for(state="visible", timeout=10_000)
        graph_beta = page.locator("[data-cg-field='beta']")
        page.wait_for_function(
            """() => document.querySelector('[data-cg-field="beta"]')?.getAttribute('aria-current') === 'true'""",
            timeout=10_000,
        )
        if graph_beta.get_attribute("aria-current") != "true":
            raise AssertionError("Evidence Lens → Claim Graph did not select the matching metric node")
        detail = page.locator("[data-cg-detail-panel='true']")
        if "Estimate" not in detail.inner_text() or "-0.021" not in detail.inner_text():
            raise AssertionError("Evidence Lens → Claim Graph lost persisted estimate context")
        page.screenshot(path=output_dir / "audit-evidence-lens-graph.png", full_page=True)

        page.locator("[data-cg-detail-action='source']").click()
        preview.wait_for(state="visible", timeout=10_000)
        page.wait_for_function(
            """() => document.querySelector('[data-reference-evidence-preview="true"]')?.dataset.evidenceLensState === 'linked'""",
            timeout=10_000,
        )
        linked = page.locator("[data-ref-field='beta'].is-linked-selection")
        linked.wait_for(state="visible", timeout=10_000)
        if "GRAPH LINK" not in hud.inner_text():
            raise AssertionError("Claim Graph → Evidence Lens did not restore linked evidence state")
        page.screenshot(path=output_dir / "audit-evidence-lens-linked.png", full_page=True)

        beta.focus()
        beta.press("Escape")
        page.wait_for_function(
            """() => {
              const preview = document.querySelector('[data-reference-evidence-preview="true"]');
              const beta = document.querySelector('[data-ref-field="beta"]');
              return preview?.dataset.evidenceLensState === 'idle'
                && preview?.dataset.evidenceLensPinned === ''
                && beta?.getAttribute('aria-pressed') === 'false';
            }""",
            timeout=10_000,
        )

        context.close()
        browser.close()

    if page_errors:
        raise AssertionError("Browser page errors: " + " | ".join(page_errors))

    screenshots = [
        "audit-evidence-lens.png",
        "audit-evidence-lens-graph.png",
        "audit-evidence-lens-linked.png",
    ]
    for name in screenshots:
        if not (output_dir / name).is_file():
            raise AssertionError(f"Evidence lens screenshot was not captured: {name}")

    print(
        json.dumps(
            {
                "status": "success",
                "audit_id": audit_id,
                "screenshots": screenshots,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
