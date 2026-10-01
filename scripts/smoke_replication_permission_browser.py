from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx
from playwright.sync_api import Page, sync_playwright

from smoke_harness_browser import _seed_audit, _wait_for_server


def _open_reproduction(page: Page, base_url: str, audit_id: str) -> None:
    page.goto(base_url, wait_until="networkidle")
    page.locator("[data-view='reproduction']").first.click()
    page.locator("[data-reproduction-surface='true']").wait_for(state="visible", timeout=20_000)
    select = page.locator("#rep-audit-select")
    select.wait_for(state="visible", timeout=10_000)
    select.select_option(audit_id)
    page.locator("#rep-prompt").wait_for(state="visible", timeout=10_000)


def _permission_events(run: dict[str, object]) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for event in run.get("events") or []:
        if not isinstance(event, dict) or event.get("kind") != "replication":
            continue
        payload = event.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        agent_event = payload.get("agent_event") or {}
        if isinstance(agent_event, dict) and agent_event.get("kind") == "permission":
            events.append(agent_event)
    return events


def _wait_for_run_ready(page: Page) -> None:
    page.wait_for_function(
        """() => {
            const state = document.querySelector('#rep-live-state');
            const run = document.querySelector('#rep-run');
            return Boolean(state && !state.classList.contains('running') && run && !run.disabled);
        }""",
        timeout=20_000,
    )


def _exercise_decision(
    page: Page,
    client: httpx.Client,
    *,
    prompt: str,
    decision: str,
    output_dir: Path,
    screenshot_name: str,
    pending_screenshot_name: str | None = None,
) -> tuple[str, str]:
    prompt_node = page.locator("#rep-prompt")
    prompt_node.fill(prompt)
    page.locator("#rep-run").click()

    pending = page.locator(".rep-permission.pending").last
    pending.wait_for(state="visible", timeout=20_000)
    pending_text = pending.inner_text().lower()
    if "this operation is paused" not in pending_text:
        raise AssertionError(f"Permission gate did not explain the paused run: {pending_text!r}")
    if "write synthetic reproduction checkpoint" not in pending_text:
        raise AssertionError(f"Permission gate lost the real ACP tool title: {pending_text!r}")

    request_id = str(pending.get_attribute("data-permission-card") or "")
    if not request_id.startswith("perm_"):
        raise AssertionError(f"Permission card has no server-issued request id: {request_id!r}")

    allow = pending.locator("[data-permission-decision='allow_once']")
    reject = pending.locator("[data-permission-decision='reject']")
    if allow.count() != 1 or reject.count() != 1:
        raise AssertionError("Permission UI must expose exactly Allow once and Reject")
    if pending.locator("[data-permission-decision='allow_always']").count():
        raise AssertionError("Permanent approval must never be exposed by the Veritas UI")

    decision_button = allow if decision == "allow_once" else reject
    run_id = str(decision_button.get_attribute("data-run-id") or "")
    if not run_id.startswith("run_"):
        raise AssertionError(f"Permission action has no live run id: {run_id!r}")

    control_response = client.get(f"/api/v1/replication/runs/{run_id}/control")
    control_response.raise_for_status()
    control = control_response.json()
    if control.get("active") is not True or control.get("interactive_permissions") is not True:
        raise AssertionError(f"Interactive control plane is not active: {control}")
    pending_permissions = control.get("pending_permissions") or []
    if len(pending_permissions) != 1 or pending_permissions[0].get("request_id") != request_id:
        raise AssertionError(f"Control plane lost the browser-visible permission request: {control}")
    offered_kinds = {str(item.get("kind") or "") for item in pending_permissions[0].get("options") or []}
    if not {"allow_once", "allow_always", "reject_once"}.issubset(offered_kinds):
        raise AssertionError(f"Fixture did not exercise permanent-option filtering: {offered_kinds}")

    if pending_screenshot_name:
        page.screenshot(path=output_dir / pending_screenshot_name, full_page=True)

    decision_button.click()
    sent = pending.locator(".rep-decision-sent")
    sent.wait_for(state="visible", timeout=10_000)
    expected_sent = "allow-once sent" if decision == "allow_once" else "rejected"
    if expected_sent not in sent.inner_text().lower():
        raise AssertionError(f"Permission UI did not acknowledge the reviewer decision: {sent.inner_text()!r}")

    resolved = page.locator(f".rep-permission.resolved[data-permission-card='{request_id}']").last
    resolved.wait_for(state="visible", timeout=20_000)
    _wait_for_run_ready(page)

    archived_cards = page.locator(f".rep-permission[data-permission-card='{request_id}']")
    if archived_cards.locator("[data-permission-decision]").count():
        raise AssertionError("Historical permission request remained actionable after the run ended")
    archived_text = archived_cards.first.inner_text().lower()
    if "historical permission request" not in archived_text:
        raise AssertionError(f"Archived approval did not disclose its non-actionable state: {archived_text!r}")

    page.screenshot(path=output_dir / screenshot_name, full_page=True)

    control_after = client.get(f"/api/v1/replication/runs/{run_id}/control")
    control_after.raise_for_status()
    after = control_after.json()
    if after.get("active") is not False or after.get("pending_permissions"):
        raise AssertionError(f"Completed run left a live permission behind: {after}")

    detail_response = client.get(f"/api/v1/runs/{run_id}")
    detail_response.raise_for_status()
    run = detail_response.json()
    if run.get("phase") != "finish":
        raise AssertionError(f"Permission fixture run did not finish after the decision: {run.get('phase')!r}")
    permission_events = _permission_events(run)
    event_decisions = [str((event.get("payload") or {}).get("decision") or "") for event in permission_events]
    expected_terminal = "selected" if decision == "allow_once" else "cancelled"
    if event_decisions != ["historical_pending", expected_terminal]:
        raise AssertionError(
            "Permission audit trail is incomplete or archived unsafely: "
            f"expected historical_pending/{expected_terminal}, got {event_decisions}"
        )
    historical_payload = permission_events[0].get("payload") or {}
    if historical_payload.get("policy") != "interactive":
        raise AssertionError(f"Archived permission event lost the interactive policy: {historical_payload}")
    if "historical permission request" not in str(permission_events[0].get("detail") or "").lower():
        raise AssertionError(f"Archived permission event lost its non-actionable disclosure: {permission_events[0]}")

    terminal_payload = permission_events[-1].get("payload") or {}
    if terminal_payload.get("policy") != "interactive":
        raise AssertionError(f"Permission event lost the interactive policy: {terminal_payload}")
    if decision == "allow_once" and terminal_payload.get("selected_option_id") != "once":
        raise AssertionError(f"Allow-once event lost its exact selected option: {terminal_payload}")
    if decision == "reject" and terminal_payload.get("selected_option_id") is not None:
        raise AssertionError(f"Rejected permission unexpectedly selected an allow option: {terminal_payload}")

    workspace_response = client.get(f"/api/v1/runs/{run_id}/workspace")
    workspace_response.raise_for_status()
    files = {str(item.get("path") or ""): item for item in workspace_response.json().get("files") or []}
    checkpoint = files.get("outputs/permission-allowed.txt")
    if decision == "allow_once":
        if checkpoint is None or checkpoint.get("change") != "created":
            raise AssertionError("Approved operation did not create the synthetic checkpoint")
        preview = client.get(
            f"/api/v1/runs/{run_id}/workspace/file",
            params={"path": "outputs/permission-allowed.txt"},
        )
        preview.raise_for_status()
        if "decision=allow_once" not in str(preview.json().get("content") or ""):
            raise AssertionError("Approved checkpoint did not preserve the allow-once decision")
    elif checkpoint is not None:
        raise AssertionError("Rejected operation created a checkpoint anyway")

    return run_id, request_id


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exercise real interactive ACP permission gates in Chromium."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8767")
    parser.add_argument("--output-dir", default="artifacts/permission-ui")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(base_url=base_url, timeout=60.0) as client:
        _wait_for_server(client)
        capabilities = client.get("/api/v1/capabilities")
        capabilities.raise_for_status()
        replication = capabilities.json().get("replication") or {}
        if replication.get("configured") is not True:
            raise AssertionError("Permission smoke requires the deterministic ACP fixture agent")
        if replication.get("permission_policy") != "interactive":
            raise AssertionError(f"Permission smoke requires interactive policy: {replication}")
        if replication.get("interactive_approval_enabled") is not True:
            raise AssertionError(f"Server did not advertise interactive approval: {replication}")

        audit_id = _seed_audit(
            client,
            title="Interactive permission browser acceptance",
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
            )
            page = context.new_page()
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            _open_reproduction(page, base_url, audit_id)

            allowed_run_id, allowed_request_id = _exercise_decision(
                page,
                client,
                prompt=(
                    "Request approval for the synthetic reproduction checkpoint. "
                    "Proceed only if the operator explicitly allows it once."
                ),
                decision="allow_once",
                output_dir=output_dir,
                pending_screenshot_name="replication-permission-pending.png",
                screenshot_name="replication-permission-allowed.png",
            )
            rejected_run_id, rejected_request_id = _exercise_decision(
                page,
                client,
                prompt=(
                    "Request approval for the same synthetic checkpoint again. "
                    "This time the operator will reject it."
                ),
                decision="reject",
                output_dir=output_dir,
                screenshot_name="replication-permission-rejected.png",
            )
            context.close()
            browser.close()

    if page_errors:
        raise AssertionError("Browser page errors: " + " | ".join(page_errors))

    expected = {
        "replication-permission-pending.png",
        "replication-permission-allowed.png",
        "replication-permission-rejected.png",
    }
    missing = sorted(name for name in expected if not (output_dir / name).is_file())
    if missing:
        raise AssertionError(f"Permission acceptance screenshots were not captured: {missing}")

    print(
        json.dumps(
            {
                "status": "success",
                "audit_id": audit_id,
                "allowed_run_id": allowed_run_id,
                "allowed_request_id": allowed_request_id,
                "rejected_run_id": rejected_run_id,
                "rejected_request_id": rejected_request_id,
                "screenshots": sorted(expected),
                "output_dir": str(output_dir),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
