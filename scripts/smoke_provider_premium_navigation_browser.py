from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

from smoke_harness_browser import _wait_for_server


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exercise premium spatial provider navigation in real Chromium."
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
            viewport={"width": 1000, "height": 900},
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
            """() => document.querySelector('[data-model-provider-matrix="true"]')?.dataset.premiumNavigation === 'true'""",
            timeout=10_000,
        )

        cards = page.locator("[data-model-provider]")
        if cards.count() != 5:
            raise AssertionError("Premium provider navigation requires the complete provider catalog")

        tabbable = page.locator("[data-model-provider][tabindex='0']")
        if tabbable.count() != 1:
            raise AssertionError("Provider grid must expose exactly one roving tab stop")
        if tabbable.first.get_attribute("data-model-provider") != "deepseek":
            raise AssertionError("Selected provider must anchor the initial roving tab stop")

        deepseek = page.locator("[data-model-provider='deepseek']")
        deepseek.focus()
        shortcuts = deepseek.get_attribute("aria-keyshortcuts") or ""
        for expected in ("ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"):
            if expected not in shortcuts:
                raise AssertionError(f"Provider card lost keyboard discoverability for {expected}")

        # At 1000px the provider grid is three columns. Spatial Down from
        # DeepSeek (row 1, column 2) must land on OpenAI-compatible (row 2,
        # column 2), not on the next DOM sibling.
        page.keyboard.press("ArrowDown")
        page.wait_for_function(
            """() => document.activeElement?.dataset.modelProvider === 'openai_compatible'""",
            timeout=10_000,
        )
        if router.get_attribute("data-navigation-mode") != "spatial":
            raise AssertionError("Directional keyboard movement did not enter spatial navigation mode")
        if router.get_attribute("data-navigation-vector") != "down":
            raise AssertionError("Spatial navigation did not expose its direction vector")
        if page.locator("[data-model-provider][tabindex='0']").count() != 1:
            raise AssertionError("Spatial navigation broke the single roving tab stop")
        page.screenshot(path=output_dir / "settings-provider-spatial-navigation.png", full_page=True)

        page.keyboard.press("ArrowUp")
        page.wait_for_function(
            """() => document.activeElement?.dataset.modelProvider === 'deepseek'""",
            timeout=10_000,
        )
        page.keyboard.press("ArrowRight")
        page.wait_for_function(
            """() => document.activeElement?.dataset.modelProvider === 'anthropic'""",
            timeout=10_000,
        )

        # There is no card to the right of Anthropic on row 1. Premium
        # navigation keeps focus stable and provides a short non-destructive
        # edge response instead of wrapping unexpectedly.
        anthropic = page.locator("[data-model-provider='anthropic']")
        page.keyboard.press("ArrowRight")
        page.wait_for_function(
            """() => document.querySelector('[data-model-provider="anthropic"]')?.dataset.navEdge === 'right'""",
            timeout=10_000,
        )
        if page.evaluate("document.activeElement?.dataset.modelProvider") != "anthropic":
            raise AssertionError("Edge navigation unexpectedly wrapped focus")
        if router.get_attribute("data-navigation-mode") != "edge":
            raise AssertionError("Edge navigation did not expose its bounded state")

        # Custom interactive cards need a real press state. Verify trusted
        # pointer down/up changes visual state without relying on hover to act.
        box = anthropic.bounding_box()
        if not box:
            raise AssertionError("Anthropic card is not pointer addressable")
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.down()
        page.wait_for_function(
            """() => document.querySelector('[data-model-provider="anthropic"]')?.dataset.pressed === 'true'""",
            timeout=10_000,
        )
        page.screenshot(path=output_dir / "settings-provider-press-feedback.png", full_page=True)
        page.mouse.up()
        page.wait_for_function(
            """() => document.querySelector('[data-model-provider="anthropic"]')?.dataset.pressed === 'false'""",
            timeout=10_000,
        )

        page.keyboard.press("Home")
        page.wait_for_function(
            """() => document.activeElement?.dataset.modelProvider === 'openai'""",
            timeout=10_000,
        )
        page.keyboard.press("End")
        page.wait_for_function(
            """() => document.activeElement?.dataset.modelProvider === 'openai_compatible'""",
            timeout=10_000,
        )
        if router.get_attribute("data-navigation-mode") != "jump":
            raise AssertionError("Home/End did not expose jump navigation state")

        context.close()
        browser.close()

    if page_errors:
        raise AssertionError("Browser page errors: " + " | ".join(page_errors))

    screenshots = [
        output_dir / "settings-provider-spatial-navigation.png",
        output_dir / "settings-provider-press-feedback.png",
    ]
    if not all(path.is_file() for path in screenshots):
        raise AssertionError("Premium provider navigation screenshots were not captured")

    print(
        json.dumps(
            {
                "status": "success",
                "interaction_model": "spatial-roving-navigation-bounded-edges-press-feedback",
                "screenshots": [path.name for path in screenshots],
                "output_dir": str(output_dir),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
