from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

from smoke_harness_browser import _seed_audit, _wait_for_server
from smoke_replication_permission_browser import _open_reproduction, _wait_for_run_ready


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exercise permission-review polish and action locking in real Chromium."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8767")
    parser.add_argument("--output-dir", default="artifacts/permission-ui")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(base_url=base_url, timeout=60.0) as client:
        _wait_for_server(client)
        audit_id = _seed_audit(
            client,
            title="Interactive permission UI polish acceptance",
            attach_replication=True,
        )

        page_errors: list[str] = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1536, "height": 960},
                device_scale_factor=1,
                locale="en-US",
                color_scheme="dark",
                reduced_motion="no-preference",
            )
            page = context.new_page()
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            _open_reproduction(page, base_url, audit_id)

            # Delay only the decision POST so the atomic submitting state is observable.
            page.evaluate(
                """() => {
                    const originalFetch = window.fetch.bind(window);
                    window.fetch = (input, init) => {
                        const url = typeof input === 'string' ? input : String(input?.url || input);
                        if (url.includes('/api/v1/replication/runs/') && url.includes('/permissions/')) {
                            return new Promise((resolve, reject) => {
                                setTimeout(() => originalFetch(input, init).then(resolve, reject), 700);
                            });
                        }
                        return originalFetch(input, init);
                    };
                }"""
            )

            page.locator("#rep-prompt").fill(
                "Request approval for the synthetic checkpoint so the permission surface can be reviewed."
            )
            page.locator("#rep-run").click()

            pending = page.locator(".rep-permission.pending[data-permission-enhanced='true']").last
            pending.wait_for(state="visible", timeout=20_000)
            if pending.get_attribute("role") != "group":
                raise AssertionError("Permission card did not receive an accessible review group role")
            if pending.get_attribute("aria-label") != "Sensitive operation approval":
                raise AssertionError("Pending permission card lost its explicit accessibility label")
            if pending.get_attribute("data-permission-capability") != "execute":
                raise AssertionError("Permission surface did not expose the ACP capability kind")

            meta = pending.locator("[data-permission-meta='true']")
            meta.wait_for(state="visible", timeout=10_000)
            meta_text = meta.inner_text().lower()
            for expected in ("capability", "execute", "scope", "one operation", "persistence", "never remembered"):
                if expected not in meta_text:
                    raise AssertionError(f"Permission metadata lost {expected!r}: {meta_text!r}")

            command = pending.locator("[data-permission-command='true']")
            command.wait_for(state="visible", timeout=10_000)
            if "python replicate.py --write-checkpoint" not in command.inner_text():
                raise AssertionError("Permission surface lost the concrete requested command")

            boundary = pending.locator("[data-permission-boundary='true']")
            if "only to this request" not in boundary.inner_text().lower():
                raise AssertionError("Permission surface did not disclose one-request scope")
            if "never turns this into permanent approval" not in boundary.inner_text().lower():
                raise AssertionError("Permission surface lost its no-persistence disclosure")

            allow = pending.locator("[data-permission-decision='allow_once']")
            reject = pending.locator("[data-permission-decision='reject']")
            if allow.get_attribute("aria-label") != "Allow this operation once":
                raise AssertionError("Allow-once action lost its accessible one-shot label")
            if reject.get_attribute("aria-label") != "Reject this operation":
                raise AssertionError("Reject action lost its accessible label")
            if pending.locator("[data-permission-decision='allow_always']").count():
                raise AssertionError("Polished UI exposed permanent approval")

            allow_height = float(allow.evaluate("el => parseFloat(getComputedStyle(el).minHeight)"))
            reject_height = float(reject.evaluate("el => parseFloat(getComputedStyle(el).minHeight)"))
            if min(allow_height, reject_height) < 32:
                raise AssertionError(
                    f"Permission actions are below the hardened 32px minimum: {allow_height}, {reject_height}"
                )

            box = pending.bounding_box()
            if not box:
                raise AssertionError("Permission card has no browser layout box")
            page.mouse.move(box["x"] + box["width"] * 0.73, box["y"] + box["height"] * 0.28)
            page.wait_for_timeout(50)
            proximity = pending.evaluate("el => el.style.getPropertyValue('--permission-x')")
            if not proximity.endswith("px"):
                raise AssertionError(f"Pointer proximity state did not update: {proximity!r}")

            page.screenshot(
                path=output_dir / "replication-permission-polished-pending.png",
                full_page=True,
            )

            allow.click()
            page.wait_for_function(
                """() => {
                    const card = document.querySelector('.rep-permission.pending[data-permission-submitting="true"]');
                    if (!card || !card.classList.contains('submitting')) return false;
                    const actions = card.querySelector('.rep-permission-actions');
                    const buttons = [...card.querySelectorAll('[data-permission-decision]')];
                    return actions?.getAttribute('aria-busy') === 'true' && buttons.length === 2 && buttons.every((button) => button.disabled);
                }""",
                timeout=5_000,
            )
            page.screenshot(
                path=output_dir / "replication-permission-submitting.png",
                full_page=True,
            )

            pending.locator(".rep-decision-sent").wait_for(state="visible", timeout=10_000)
            _wait_for_run_ready(page)

            archived = page.locator(
                ".rep-permission.resolved[data-permission-enhanced='true']"
            ).first
            archived.wait_for(state="visible", timeout=20_000)
            archived_boundary = archived.locator("[data-permission-boundary='true']")
            if "historical request cannot be approved again" not in archived_boundary.inner_text().lower():
                raise AssertionError("Archived permission surface lost its non-replay disclosure")
            if archived.locator("[data-permission-decision]").count():
                raise AssertionError("Archived permission surface became actionable again")

            page.screenshot(
                path=output_dir / "replication-permission-polished-resolved.png",
                full_page=True,
            )
            context.close()
            browser.close()

    if page_errors:
        raise AssertionError("Browser page errors: " + " | ".join(page_errors))

    expected = {
        "replication-permission-polished-pending.png",
        "replication-permission-submitting.png",
        "replication-permission-polished-resolved.png",
    }
    missing = sorted(name for name in expected if not (output_dir / name).is_file())
    if missing:
        raise AssertionError(f"Permission polish screenshots were not captured: {missing}")

    print(
        json.dumps(
            {
                "status": "success",
                "audit_id": audit_id,
                "screenshots": sorted(expected),
                "output_dir": str(output_dir),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
