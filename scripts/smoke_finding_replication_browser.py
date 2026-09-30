from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import quote

import httpx
from playwright.sync_api import sync_playwright

from smoke_harness_browser import _seed_contradiction_audit, _wait_for_server


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exercise the real Finding → Replication Workspace → Finding browser loop."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--output-dir", default="artifacts/ui")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(base_url=base_url, timeout=60.0) as client:
        _wait_for_server(client)
        audit_id, finding_id = _seed_contradiction_audit(client)

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
            page.goto(
                f"{base_url}/#audit={quote(audit_id, safe='')}",
                wait_until="networkidle",
            )
            page.locator("[data-audit-harness='true']").wait_for(
                state="visible", timeout=20_000
            )
            page.locator(".ah-tabs [data-ah-tab='findings']").click()

            finding = page.locator(
                f".fn-finding-row[data-fn-finding-id='{finding_id}']"
            )
            finding.wait_for(state="visible", timeout=10_000)
            finding.locator("[data-fn-reproduce='true']").click()

            workspace = page.locator("[data-reproduction-surface='true']")
            workspace.wait_for(state="visible", timeout=20_000)
            context_card = page.locator("[data-rep-finding-context='true']")
            context_card.wait_for(state="visible", timeout=10_000)
            context_text = context_card.inner_text()
            if "Regression reporting contradiction" not in context_text:
                raise AssertionError(
                    f"Replication workspace lost detector finding context: {context_text!r}"
                )
            if "does not by itself verify or resolve this finding" not in context_text:
                raise AssertionError(
                    "Replication workspace does not expose the scientific-evidence boundary"
                )

            selected_audit = page.locator("#rep-audit-select").input_value()
            if selected_audit != audit_id:
                raise AssertionError(
                    f"Finding handoff selected the wrong audit: {selected_audit!r}"
                )
            prompt = page.locator("#rep-prompt").input_value()
            if "Reproduce the result linked to finding" not in prompt:
                raise AssertionError(f"Finding handoff did not prefill a reproduction goal: {prompt!r}")
            if "do not treat a successful code run as resolving the finding" not in prompt.lower():
                raise AssertionError("Prefilled reproduction goal lost the evidence-boundary instruction")

            page.screenshot(path=output_dir / "finding-replication-context.png", full_page=True)

            context_card.locator("[data-rep-return-finding='true']").click()
            returned = page.locator(
                f".fn-finding-row[data-fn-finding-id='{finding_id}'].is-linked-finding"
            )
            returned.wait_for(state="visible", timeout=20_000)
            if returned.get_attribute("aria-current") != "true":
                raise AssertionError(
                    "Replication Workspace → Finding did not restore the exact finding focus"
                )
            page.screenshot(path=output_dir / "finding-replication-return.png", full_page=True)

            context.close()
            browser.close()

    if page_errors:
        raise AssertionError("Browser page errors: " + " | ".join(page_errors))


if __name__ == "__main__":
    main()
