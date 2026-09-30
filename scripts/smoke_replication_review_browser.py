from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import quote

import httpx
from playwright.sync_api import Page, sync_playwright

from smoke_harness_browser import _seed_contradiction_audit, _wait_for_server


REVIEW_NOTE = "The deterministic reproduction output is consistent with the detector concern."


def _seed_linked_replication(
    client: httpx.Client,
) -> tuple[str, str, str, str, dict[str, object]]:
    capabilities = client.get("/api/v1/capabilities")
    capabilities.raise_for_status()
    if not (capabilities.json().get("replication") or {}).get("configured"):
        raise AssertionError("Replication review smoke requires the deterministic ACP fixture agent")

    audit_id, detector_finding_id = _seed_contradiction_audit(client)
    binding_finding_id = f"{audit_id}:finding:0"
    audit_before = client.get(f"/api/v1/audits/{audit_id}")
    audit_before.raise_for_status()
    scientific_result = audit_before.json().get("latest_result") or {}

    attached = client.post(
        f"/api/v1/audits/{audit_id}/attachments",
        files={
            "file": (
                "review-replicate.py",
                b"print('immutable review fixture')\n",
                "text/x-python",
            )
        },
    )
    attached.raise_for_status()

    response = client.post(
        f"/api/v1/audits/{audit_id}/replication",
        json={
            "finding_id": binding_finding_id,
            "prompt": (
                "Create deterministic reproduction outputs for this linked finding. "
                "Completion is execution provenance only and must not resolve the finding."
            ),
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
        raise AssertionError(f"Linked replication did not expose exactly one run id: {run_ids}")
    run_id = run_ids.pop()

    detail = client.get(f"/api/v1/runs/{run_id}")
    detail.raise_for_status()
    run = detail.json()
    origin = run.get("origin_finding") or {}
    if origin.get("finding_id") != binding_finding_id:
        raise AssertionError(f"Run lost its server-owned finding context: {origin}")
    if origin.get("title") != "Regression reporting contradiction":
        raise AssertionError(f"Canonical binding did not resolve server-owned detector context: {origin}")
    if run.get("phase") != "finish":
        raise AssertionError(f"Fixture replication is not terminal: {run.get('phase')!r}")
    if run.get("evidence") is not False:
        raise AssertionError("Replication run must not be promoted to paper evidence")

    empty_review = client.get(f"/api/v1/runs/{run_id}/review")
    empty_review.raise_for_status()
    empty_payload = empty_review.json()
    if empty_payload.get("review") is not None:
        raise AssertionError("Fresh linked replication unexpectedly has an operator review")
    for boundary in ("review_only", "does_not_resolve_finding", "does_not_promote_evidence"):
        if empty_payload.get(boundary) is not True:
            raise AssertionError(f"Review API lost safety boundary {boundary!r}: {empty_payload}")

    return audit_id, detector_finding_id, binding_finding_id, run_id, scientific_result


def _open_review(page: Page, base_url: str, audit_id: str, run_id: str) -> None:
    page.goto(base_url, wait_until="networkidle")
    page.locator("[data-view='reproduction']").first.click()
    page.locator("[data-reproduction-surface='true']").wait_for(state="visible", timeout=20_000)
    select = page.locator("#rep-audit-select")
    select.wait_for(state="visible", timeout=10_000)
    select.select_option(audit_id)
    row = page.locator(f".rep-run-row[data-run-id='{run_id}']")
    row.wait_for(state="visible", timeout=10_000)
    row.click()
    page.locator("[data-rep-tab='run']").click()
    page.locator("[data-rep-run-origin='true']").wait_for(state="visible", timeout=10_000)
    page.locator(f"[data-rep-review-card='true'][data-rep-review-run-id='{run_id}']").wait_for(
        state="visible", timeout=10_000
    )


def _assert_finding_review_roundtrip(
    page: Page,
    base_url: str,
    audit_id: str,
    detector_finding_id: str,
    run_id: str,
    output_dir: Path,
) -> None:
    page.goto("about:blank", wait_until="load")
    page.goto(
        f"{base_url}/#audit={quote(audit_id, safe='')}",
        wait_until="networkidle",
    )
    page.locator("[data-audit-harness='true']").wait_for(state="visible", timeout=20_000)
    page.locator(".ah-tabs [data-ah-tab='findings']").click()
    finding = page.locator(
        f".fn-finding-row[data-fn-finding-id='{detector_finding_id}']"
    )
    finding.wait_for(state="visible", timeout=10_000)
    annotation = finding.locator(
        f"[data-finding-replication-review='true'][data-review-run-id='{run_id}']"
    )
    annotation.wait_for(state="visible", timeout=10_000)
    text = annotation.inner_text()
    for expected in (
        "Replication review",
        "supports",
        REVIEW_NOTE,
        "finding unchanged",
        "generated outputs untrusted",
    ):
        if expected.lower() not in text.lower():
            raise AssertionError(
                f"Finding review annotation lost {expected!r}: {text!r}"
            )
    page.screenshot(path=output_dir / "finding-replication-review.png", full_page=True)

    annotation.locator("[data-open-reviewed-run='true']").click()
    surface = page.locator("[data-reproduction-surface='true']")
    surface.wait_for(state="visible", timeout=20_000)
    selected = page.locator(f".rep-run-row.selected[data-run-id='{run_id}']")
    selected.wait_for(state="visible", timeout=20_000)
    run_tab = page.locator("[data-rep-tab='run'].active")
    run_tab.wait_for(state="visible", timeout=10_000)
    review_card = page.locator(
        f"[data-rep-review-card='true'][data-rep-review-run-id='{run_id}']"
    )
    review_card.wait_for(state="visible", timeout=10_000)
    if review_card.locator("[data-rep-review-disposition='supports']").get_attribute(
        "aria-checked"
    ) != "true":
        raise AssertionError("Finding → reviewed run roundtrip lost the saved disposition")
    page.screenshot(path=output_dir / "finding-review-run-roundtrip.png", full_page=True)


def _record_review(
    page: Page,
    base_url: str,
    audit_id: str,
    detector_finding_id: str,
    run_id: str,
    output_dir: Path,
) -> None:
    _open_review(page, base_url, audit_id, run_id)
    card = page.locator("[data-rep-review-card='true']")
    boundary = page.locator("[data-rep-review-boundary='true']")
    boundary_text = boundary.inner_text().lower()
    for expected in ("review-only", "finding remains open", "generated outputs remain untrusted"):
        if expected not in boundary_text:
            raise AssertionError(f"Review UI lost boundary copy {expected!r}: {boundary_text!r}")

    page.locator("[data-rep-review-disposition='supports']").click()
    card.locator("textarea").fill(REVIEW_NOTE)
    card.locator("[data-rep-review-save]").click()
    saved = page.locator(
        "[data-rep-review-card='true'][data-rep-review-saved='true'][data-rep-review-disposition='supports']"
    )
    saved.wait_for(state="visible", timeout=10_000)
    if "Saved" not in saved.locator("[data-rep-review-status]").inner_text():
        raise AssertionError("Saved operator review did not expose a persisted timestamp/state")
    page.screenshot(path=output_dir / "replication-review.png", full_page=True)

    _assert_finding_review_roundtrip(
        page,
        base_url,
        audit_id,
        detector_finding_id,
        run_id,
        output_dir,
    )

    page.goto("about:blank")
    _open_review(page, base_url, audit_id, run_id)
    persisted = page.locator("[data-rep-review-disposition='supports']")
    if persisted.get_attribute("aria-checked") != "true":
        raise AssertionError("Operator review disposition did not persist across a fresh page load")
    if page.locator("[data-rep-review-card='true'] textarea").input_value() != REVIEW_NOTE:
        raise AssertionError("Operator review note did not persist across a fresh page load")
    page.screenshot(path=output_dir / "replication-review-persisted.png", full_page=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exercise the human replication-review boundary in real Chromium."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8766")
    parser.add_argument("--output-dir", default="artifacts/ui")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(base_url=base_url, timeout=60.0) as client:
        _wait_for_server(client)
        (
            audit_id,
            detector_finding_id,
            binding_finding_id,
            run_id,
            scientific_result,
        ) = _seed_linked_replication(client)

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
            _record_review(
                page,
                base_url,
                audit_id,
                detector_finding_id,
                run_id,
                output_dir,
            )
            context.close()
            browser.close()

        review_response = client.get(f"/api/v1/runs/{run_id}/review")
        review_response.raise_for_status()
        review = review_response.json().get("review") or {}
        if review.get("disposition") != "supports" or review.get("note") != REVIEW_NOTE:
            raise AssertionError(f"Saved review did not round-trip through the API: {review}")
        if review.get("finding_id") != binding_finding_id:
            raise AssertionError(f"Review lost the server-owned canonical finding binding: {review}")
        for boundary in ("review_only", "does_not_resolve_finding", "does_not_promote_evidence"):
            if review.get(boundary) is not True:
                raise AssertionError(f"Saved review lost boundary {boundary!r}: {review}")

        projected = client.get(f"/api/v1/audits/{audit_id}/replication-reviews")
        projected.raise_for_status()
        projection_items = projected.json().get("items") or []
        matching = [item for item in projection_items if item.get("run_id") == run_id]
        if len(matching) != 1:
            raise AssertionError(f"Finding review projection lost the reviewed run: {projection_items}")
        if matching[0].get("origin_finding", {}).get("finding_id") != binding_finding_id:
            raise AssertionError("Finding review projection lost the canonical server binding")
        if matching[0].get("does_not_resolve_finding") is not True:
            raise AssertionError("Finding review projection lost the non-resolution boundary")

        run_after = client.get(f"/api/v1/runs/{run_id}")
        run_after.raise_for_status()
        run = run_after.json()
        if (
            run.get("phase") != "finish"
            or run.get("origin_finding", {}).get("finding_id") != binding_finding_id
        ):
            raise AssertionError("Review annotation changed terminal run/finding context")
        review_events = [
            event
            for event in run.get("events") or []
            if event.get("kind") == "replication_review"
        ]
        if len(review_events) != 1:
            raise AssertionError(f"Expected one append-only review event, got {len(review_events)}")

        audit_after = client.get(f"/api/v1/audits/{audit_id}")
        audit_after.raise_for_status()
        after_result = audit_after.json().get("latest_result") or {}
        if after_result != scientific_result:
            raise AssertionError("Operator review mutated the detector result or finding state")
        detector_ids = {
            str(item.get("finding_id") or "") for item in after_result.get("findings") or []
        }
        if detector_finding_id not in detector_ids:
            raise AssertionError("Detector-native finding disappeared after operator review")

    if page_errors:
        raise AssertionError("Browser page errors: " + " | ".join(page_errors))

    expected = {
        "replication-review.png",
        "finding-replication-review.png",
        "finding-review-run-roundtrip.png",
        "replication-review-persisted.png",
    }
    missing = sorted(name for name in expected if not (output_dir / name).is_file())
    if missing:
        raise AssertionError(f"Replication review screenshots were not captured: {missing}")

    print(
        json.dumps(
            {
                "status": "success",
                "audit_id": audit_id,
                "detector_finding_id": detector_finding_id,
                "binding_finding_id": binding_finding_id,
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
