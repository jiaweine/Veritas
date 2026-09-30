from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx
from playwright.sync_api import Page, sync_playwright

from smoke_harness_browser import _demo_pdf, _wait_for_server


def _seed_replication_diff_run(client: httpx.Client) -> tuple[str, str, str]:
    capabilities = client.get("/api/v1/capabilities")
    capabilities.raise_for_status()
    replication = capabilities.json().get("replication") or {}
    if not replication.get("configured"):
        raise AssertionError("Diff visual smoke requires the deterministic ACP fixture agent")
    if replication.get("workspace_diff") is not True:
        raise AssertionError("Server did not advertise workspace_diff=true")

    created = client.post(
        "/api/v1/audits",
        data={"title": "Replication diff browser fixture"},
        files={
            "file": (
                "diff-fixture.pdf",
                _demo_pdf(title="Replication diff browser fixture"),
                "application/pdf",
            )
        },
    )
    created.raise_for_status()
    audit_id = str(created.json()["audit_id"])

    original = b"print('immutable source')\n"
    attached = client.post(
        f"/api/v1/audits/{audit_id}/attachments",
        files={"file": ("analysis.py", original, "text/x-python")},
    )
    attached.raise_for_status()
    attachment_id = str(attached.json()["attachment_id"])
    attachment_path = f"attachments/{attachment_id}/analysis.py"

    response = client.post(
        f"/api/v1/audits/{audit_id}/replication",
        json={
            "prompt": (
                "Create the deterministic browser acceptance outputs. This is a fixture run; "
                "do not infer scientific correctness from completion."
            )
        },
    )
    response.raise_for_status()
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    run_ids = {
        str(event.get("payload", {}).get("run_id") or "")
        for event in events
        if event.get("payload", {}).get("run_id")
    }
    if len(run_ids) != 1:
        raise AssertionError(f"Fixture replication stream did not expose one run id: {run_ids}")
    run_id = run_ids.pop()

    snapshot = client.get(f"/api/v1/runs/{run_id}/workspace")
    snapshot.raise_for_status()
    payload = snapshot.json()
    by_path = {str(item.get("path")): item for item in payload.get("files") or []}
    for expected in (attachment_path, "outputs/result.txt", "outputs/binary.bin", "outputs/large.txt"):
        if expected not in by_path:
            raise AssertionError(f"Replication workspace is missing {expected!r}: {sorted(by_path)}")
    if by_path[attachment_path].get("change") != "modified":
        raise AssertionError("Fixture agent did not mutate the staged attachment copy")
    if payload.get("staged_inputs_unchanged") is not False:
        raise AssertionError("Staged-input drift was not surfaced by the workspace inspector")

    modified = client.get(
        f"/api/v1/runs/{run_id}/workspace/file",
        params={"path": attachment_path},
    )
    modified.raise_for_status()
    modified_payload = modified.json()
    if modified_payload.get("diff_available") is not True:
        raise AssertionError(f"Modified staged text diff is unavailable: {modified_payload}")
    if modified_payload.get("diff_baseline") != "immutable_source":
        raise AssertionError("Modified staged text did not use the immutable source baseline")
    diff_text = str(modified_payload.get("diff") or "")
    if "immutable source" not in diff_text or "workspace mutation" not in diff_text:
        raise AssertionError("Modified staged text diff lost baseline/current content")

    created_output = client.get(
        f"/api/v1/runs/{run_id}/workspace/file",
        params={"path": "outputs/result.txt"},
    )
    created_output.raise_for_status()
    created_payload = created_output.json()
    if created_payload.get("diff_available") is not True:
        raise AssertionError("Created UTF-8 output did not receive an empty-baseline diff")
    if created_payload.get("diff_baseline") != "empty":
        raise AssertionError("Created UTF-8 output did not use the empty baseline")
    if "+++ b/outputs/result.txt" not in str(created_payload.get("diff") or ""):
        raise AssertionError("Created-output unified diff header is missing")

    binary = client.get(
        f"/api/v1/runs/{run_id}/workspace/file",
        params={"path": "outputs/binary.bin"},
    )
    binary.raise_for_status()
    if binary.json().get("diff_reason") != "current_binary":
        raise AssertionError(f"Binary diff did not fail closed: {binary.json()}")

    large = client.get(
        f"/api/v1/runs/{run_id}/workspace/file",
        params={"path": "outputs/large.txt"},
    )
    large.raise_for_status()
    large_payload = large.json()
    if large_payload.get("diff_reason") != "current_too_large":
        raise AssertionError(f"Oversized diff did not fail bounded: {large_payload}")
    if large_payload.get("truncated") is not True:
        raise AssertionError("Oversized workspace preview did not disclose truncation")

    source = client.get(f"/api/v1/audits/{audit_id}/attachments/{attachment_id}")
    source.raise_for_status()
    if source.content != original:
        raise AssertionError("Fixture run mutated the immutable audit-store attachment")

    return audit_id, run_id, attachment_path


def _open_reproduction(page: Page, base_url: str, run_id: str) -> None:
    page.goto(base_url, wait_until="networkidle")
    page.locator("[data-view='reproduction']").first.click()
    page.locator("[data-reproduction-surface='true']").wait_for(state="visible", timeout=20_000)
    row = page.locator(f".rep-run-row[data-run-id='{run_id}']")
    row.wait_for(state="visible", timeout=10_000)
    row.click()
    page.locator("[data-workspace-file='outputs/result.txt']").wait_for(
        state="visible", timeout=10_000
    )


def _open_file(page: Page, path: str) -> None:
    page.locator(f"[data-workspace-file='{path}']").click()
    page.locator(".rep-file-detail").wait_for(state="visible", timeout=10_000)


def _back_to_changes(page: Page) -> None:
    page.locator("#rep-file-back").click()
    page.locator(".rep-file-list").wait_for(state="visible", timeout=10_000)


def _capture_diff_states(
    page: Page,
    base_url: str,
    run_id: str,
    attachment_path: str,
    output_dir: Path,
) -> None:
    _open_reproduction(page, base_url, run_id)

    _open_file(page, attachment_path)
    available = page.locator(
        "[data-rep-diff-state='true'][data-rep-diff-available='true']"
    )
    available.wait_for(state="visible", timeout=10_000)
    if "immutable source" not in available.inner_text().lower():
        raise AssertionError("Diff UI does not disclose the immutable-source baseline")
    code = page.locator(".rep-code.diff[data-rep-diff-rendered='true']")
    code.wait_for(state="visible", timeout=10_000)
    code_text = code.inner_text()
    if "immutable source" not in code_text or "workspace mutation" not in code_text:
        raise AssertionError("Rendered workspace diff lost baseline/current lines")
    if page.locator(".rep-integrity-warning").count() < 1:
        raise AssertionError("Modified staged input is missing its integrity warning")
    page.screenshot(path=output_dir / "replication-diff.png", full_page=True)

    _back_to_changes(page)
    _open_file(page, "outputs/binary.bin")
    unavailable = page.locator(
        "[data-rep-diff-state='true'][data-rep-diff-available='false']"
    )
    unavailable.wait_for(state="visible", timeout=10_000)
    unavailable_text = unavailable.inner_text().lower()
    if "diff unavailable" not in unavailable_text or "binary" not in unavailable_text:
        raise AssertionError(f"Binary diff state is not explicit: {unavailable_text!r}")
    page.screenshot(path=output_dir / "replication-diff-unavailable.png", full_page=True)

    _back_to_changes(page)
    _open_file(page, "outputs/large.txt")
    bounded = page.locator(
        "[data-rep-diff-state='true'][data-rep-diff-reason='current_too_large']"
    )
    bounded.wait_for(state="visible", timeout=10_000)
    bounded_text = bounded.inner_text()
    if "256 KiB" not in bounded_text or "partial diff" not in bounded_text:
        raise AssertionError(f"Oversized diff state lost its bounded explanation: {bounded_text!r}")
    truncated = page.locator(".rep-truncated[data-rep-preview-truncated='true']")
    truncated.wait_for(state="visible", timeout=10_000)
    if "256 KiB" not in truncated.inner_text() or "incomplete" not in truncated.inner_text():
        raise AssertionError("Bounded preview does not disclose the actual 256 KiB cap")
    page.screenshot(path=output_dir / "replication-diff-truncated.png", full_page=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exercise bounded replication diffs in the real Chromium workbench."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8766")
    parser.add_argument("--output-dir", default="artifacts/ui")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(base_url=base_url, timeout=60.0) as client:
        _wait_for_server(client)
        audit_id, run_id, attachment_path = _seed_replication_diff_run(client)

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
            _capture_diff_states(page, base_url, run_id, attachment_path, output_dir)
            context.close()
            browser.close()

    if page_errors:
        raise AssertionError("Browser page errors: " + " | ".join(page_errors))

    expected = {
        "replication-diff.png",
        "replication-diff-unavailable.png",
        "replication-diff-truncated.png",
    }
    missing = sorted(name for name in expected if not (output_dir / name).is_file())
    if missing:
        raise AssertionError(f"Replication diff screenshots were not captured: {missing}")

    print(
        json.dumps(
            {
                "status": "success",
                "audit_id": audit_id,
                "run_id": run_id,
                "screenshots": sorted(expected),
                "output_dir": str(output_dir),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
