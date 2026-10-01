from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from smoke_harness_browser import _wait_for_server

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exercise power-user model-provider interactions in real Chromium."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--output-dir", default="artifacts/ui")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        _wait_for_server(client)

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
        page.goto(f"{base_url}/#settings", wait_until="networkidle")

        router = page.locator("[data-model-provider-matrix='true']")
        router.wait_for(state="visible", timeout=20_000)
        page.wait_for_function(
            """() => document.querySelector('[data-model-provider-matrix="true"]')?.dataset.providerPower === 'true'""",
            timeout=10_000,
        )

        cards = page.locator("[data-model-provider]")
        if cards.count() != 5:
            raise AssertionError("Provider power interactions require the complete provider catalog")

        selected = page.locator("[data-model-provider='deepseek']")
        selected.wait_for(state="visible", timeout=10_000)
        selected.focus()
        if selected.get_attribute("tabindex") != "0":
            raise AssertionError("Selected provider did not receive the roving focus anchor")

        page.keyboard.down("Space")
        quicklook = page.locator("[data-provider-quicklook='true']")
        quicklook.wait_for(state="visible", timeout=10_000)
        page.wait_for_function(
            """() => document.querySelector('[data-provider-quicklook="true"]')?.dataset.provider === 'deepseek'""",
            timeout=10_000,
        )
        text = quicklook.inner_text()
        for expected in ("QUICK LOOK", "DeepSeek", "ACTIVE", "deepseek-chat", "Shift+F10 actions"):
            if expected.lower() not in text.lower():
                raise AssertionError(f"Provider Quick Look lost {expected!r}: {text!r}")

        page.keyboard.press("ArrowRight")
        page.wait_for_function(
            """() => document.activeElement?.dataset.modelProvider === 'anthropic'""",
            timeout=10_000,
        )
        page.wait_for_function(
            """() => document.querySelector('[data-provider-quicklook="true"]')?.dataset.provider === 'anthropic'""",
            timeout=10_000,
        )
        page.screenshot(path=output_dir / "settings-provider-quicklook.png", full_page=True)
        page.keyboard.up("Space")
        if quicklook.is_visible():
            raise AssertionError("Hold-to-preview Quick Look did not close when Space was released")

        anthropic = page.locator("[data-model-provider='anthropic']")
        anthropic.click(button="right", position={"x": 100, "y": 70})
        actions = page.locator("[data-provider-action-panel='true']")
        actions.wait_for(state="visible", timeout=10_000)
        action_text = actions.inner_text()
        for expected in ("ACTION PANEL", "Anthropic", "Pin details", "Keep Quick Look open", "Copy provider ID"):
            if expected.lower() not in action_text.lower():
                raise AssertionError(f"Provider action panel lost {expected!r}: {action_text!r}")

        first_action = actions.locator("[data-provider-action]").first
        first_action.focus()
        page.keyboard.press("ArrowDown")
        page.wait_for_function(
            """() => document.activeElement?.dataset.providerAction === 'quicklook'""",
            timeout=10_000,
        )
        page.screenshot(path=output_dir / "settings-provider-actions.png", full_page=True)
        page.keyboard.press("Escape")
        if actions.is_visible():
            raise AssertionError("Provider action panel did not close on Escape")
        page.wait_for_function(
            """() => document.activeElement?.dataset.modelProvider === 'anthropic'""",
            timeout=10_000,
        )

        page.keyboard.press("j")
        page.wait_for_function(
            """() => document.activeElement?.dataset.modelProvider === 'gemini'""",
            timeout=10_000,
        )
        page.keyboard.press("k")
        page.wait_for_function(
            """() => document.activeElement?.dataset.modelProvider === 'anthropic'""",
            timeout=10_000,
        )

        context.close()
        browser.close()

    if page_errors:
        raise AssertionError("Browser page errors: " + " | ".join(page_errors))

    screenshots = [
        output_dir / "settings-provider-quicklook.png",
        output_dir / "settings-provider-actions.png",
    ]
    if not all(path.is_file() for path in screenshots):
        raise AssertionError("Provider interaction screenshots were not captured")

    print(
        json.dumps(
            {
                "status": "success",
                "interaction_model": "hover-preview-click-pin-space-quicklook-context-actions",
                "screenshots": [path.name for path in screenshots],
                "output_dir": str(output_dir),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
