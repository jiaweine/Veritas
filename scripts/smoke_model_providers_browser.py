from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

from smoke_harness_browser import _wait_for_server


SMOKE_SECRET = "veritas-browser-smoke-secret"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exercise the model-provider control plane in real Chromium."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--output-dir", default="artifacts/ui")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        _wait_for_server(client)
        response = client.get("/api/v1/model-providers")
        response.raise_for_status()
        router = response.json()
        if router.get("selected_provider") != "deepseek":
            raise AssertionError(f"Provider smoke expected DeepSeek selection: {router}")
        if router.get("model") != "deepseek-chat" or router.get("active_ready") is not True:
            raise AssertionError(f"Provider smoke did not reach a complete model configuration: {router}")
        if router.get("secrets_exposed") is not False or SMOKE_SECRET in response.text:
            raise AssertionError("Provider capability leaked the configured API key")
        if router.get("direct_detector_access") is not False:
            raise AssertionError("Provider router must remain outside deterministic detector evidence")
        if router.get("replication_bridge_required") is not True:
            raise AssertionError("Provider router lost the ACP bridge boundary")

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
        page.locator("[data-settings-surface='true']").wait_for(state="visible", timeout=20_000)
        matrix = page.locator("[data-model-provider-matrix='true']")
        matrix.wait_for(state="visible", timeout=10_000)
        selected = page.locator(
            "[data-model-provider='deepseek'][data-provider-selected='true'][data-provider-state='ready']"
        )
        selected.wait_for(state="visible", timeout=10_000)

        if page.locator("[data-model-provider]").count() != 5:
            raise AssertionError("Provider matrix did not render the complete supported adapter catalog")
        text = matrix.inner_text()
        for expected in (
            "Model Router",
            "DeepSeek",
            "deepseek-chat",
            "CONFIG READY",
            "ACP AGENT",
            "Evidence firewall active",
            "SERVER-ONLY",
            "ACP BRIDGE REQUIRED",
        ):
            if expected.lower() not in text.lower():
                raise AssertionError(f"Provider control plane lost {expected!r}: {text!r}")
        if SMOKE_SECRET in page.locator("body").inner_text():
            raise AssertionError("Provider secret leaked into rendered Settings UI")
        if matrix.get_attribute("data-model-router-state") != "configured":
            raise AssertionError("Complete provider configuration did not render the configured router state")

        inspector = page.locator("[data-router-pointer-inspector='true']")
        inspector.wait_for(state="visible", timeout=10_000)
        network = page.locator("[data-router-network-field='true']")
        network.wait_for(state="visible", timeout=10_000)
        page.wait_for_function(
            """() => document.querySelector('[data-router-network-field="true"]')?.dataset.networkReady === 'true'""",
            timeout=10_000,
        )

        selected.hover(position={"x": 110, "y": 70})
        page.wait_for_function(
            """() => {
                const card = document.querySelector('[data-model-provider="deepseek"]');
                const router = document.querySelector('[data-model-provider-matrix="true"]');
                const network = document.querySelector('[data-router-network-field="true"]');
                return card?.dataset.pointerActive === 'true'
                    && router?.dataset.cursorActive === 'true'
                    && network?.dataset.networkPointer === 'active'
                    && network?.dataset.networkFocus === 'deepseek'
                    && Number(network?.dataset.networkLinks || 0) > 0;
            }""",
            timeout=10_000,
        )
        hover_text = inspector.inner_text()
        if "DeepSeek" not in hover_text or "POINTER LINK" not in hover_text:
            raise AssertionError(f"Pointer inspector did not follow the hovered provider: {hover_text!r}")

        page.screenshot(path=output_dir / "settings-model-providers-network.png", full_page=True)

        selected.click(position={"x": 110, "y": 70})
        page.wait_for_function(
            """() => {
                const card = document.querySelector('[data-model-provider="deepseek"]');
                const network = document.querySelector('[data-router-network-field="true"]');
                return card?.dataset.pinned === 'true'
                    && network?.dataset.networkFocus === 'deepseek'
                    && network?.dataset.networkFocusMode === 'pinned';
            }""",
            timeout=10_000,
        )
        if selected.get_attribute("aria-pressed") != "true":
            raise AssertionError("Provider pin interaction is not exposed through aria-pressed")
        if selected.get_attribute("aria-controls") != "router-pointer-inspector":
            raise AssertionError("Provider card is not linked to the interactive inspector")
        pinned_text = inspector.inner_text()
        if "PINNED NODE" not in pinned_text or "READY" not in pinned_text:
            raise AssertionError(f"Pinned provider inspector lost readiness context: {pinned_text!r}")

        page.mouse.move(25, 25)
        page.wait_for_function(
            """() => document.querySelector('[data-router-network-field="true"]')?.dataset.networkFocus === 'deepseek'""",
            timeout=10_000,
        )
        page.screenshot(path=output_dir / "settings-model-providers.png", full_page=True)
        page.screenshot(path=output_dir / "settings-model-providers-interactive.png", full_page=True)

        selected.focus()
        selected.press("Escape")
        page.wait_for_function(
            """() => {
                const card = document.querySelector('[data-model-provider="deepseek"]');
                const network = document.querySelector('[data-router-network-field="true"]');
                return card?.dataset.pinned === 'false' && (network?.dataset.networkFocus || '') === '';
            }""",
            timeout=10_000,
        )
        if selected.get_attribute("aria-pressed") != "false":
            raise AssertionError("Escape did not release the pinned provider")

        context.close()
        browser.close()

    if page_errors:
        raise AssertionError("Browser page errors: " + " | ".join(page_errors))

    screenshot_names = (
        "settings-model-providers.png",
        "settings-model-providers-interactive.png",
        "settings-model-providers-network.png",
    )
    for screenshot_name in screenshot_names:
        screenshot = output_dir / screenshot_name
        if not screenshot.is_file():
            raise AssertionError(f"Model provider control-plane screenshot was not captured: {screenshot_name}")

    print(
        json.dumps(
            {
                "status": "success",
                "provider": "deepseek",
                "model": "deepseek-chat",
                "configuration": "ready",
                "screenshots": list(screenshot_names),
                "output_dir": str(output_dir),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
