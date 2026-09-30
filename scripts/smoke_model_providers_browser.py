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
            raise AssertionError(f"Provider smoke did not reach a ready model link: {router}")
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
        page.goto(base_url, wait_until="networkidle")
        page.locator("[data-view='settings']").first.click()
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
            "ACP AGENT",
            "Evidence firewall active",
            "SERVER-ONLY",
            "ACP BRIDGE REQUIRED",
        ):
            if expected.lower() not in text.lower():
                raise AssertionError(f"Provider control plane lost {expected!r}: {text!r}")
        if SMOKE_SECRET in page.locator("body").inner_text():
            raise AssertionError("Provider secret leaked into rendered Settings UI")
        if matrix.get_attribute("data-model-router-state") != "online":
            raise AssertionError("Ready provider did not render the online router state")

        page.screenshot(path=output_dir / "settings-model-providers.png", full_page=True)
        context.close()
        browser.close()

    if page_errors:
        raise AssertionError("Browser page errors: " + " | ".join(page_errors))

    screenshot = output_dir / "settings-model-providers.png"
    if not screenshot.is_file():
        raise AssertionError("Model provider control-plane screenshot was not captured")

    print(
        json.dumps(
            {
                "status": "success",
                "provider": "deepseek",
                "model": "deepseek-chat",
                "screenshot": screenshot.name,
                "output_dir": str(output_dir),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
