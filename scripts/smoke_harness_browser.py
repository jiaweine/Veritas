from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from urllib.parse import quote

import httpx
import pymupdf
from playwright.sync_api import Page, sync_playwright


def _demo_pdf() -> bytes:
    """Build a deterministic PDF that both native parsers recognize as a regression table."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((54, 54), "Card (1992) — Minimum Wages and Employment", fontsize=16)
    page.insert_text((54, 88), "Table 4. County-Level Estimates", fontsize=12)
    page.insert_text(
        (54, 106),
        "Dependent variable: total employment. County and year controls included.",
        fontsize=8,
    )

    xs = (54, 230, 315, 390, 465, 550)
    ys = (122, 154, 188)
    for x in xs:
        page.draw_line((x, ys[0]), (x, ys[-1]), width=0.8)
    for y in ys:
        page.draw_line((xs[0], y), (xs[-1], y), width=0.8)

    header = ("Variable", "Coef.", "SE", "z", "p")
    data = ("Minimum wage", "-0.021", "0.026", "-0.808", "0.419")
    for column, text in enumerate(header):
        page.insert_text((xs[column] + 5, 145), text, fontsize=9)
    for column, text in enumerate(data):
        page.insert_text((xs[column] + 5, 179), text, fontsize=9)

    page.insert_text((54, 218), "N = 3,108", fontsize=9)
    page.insert_text(
        (54, 238),
        "Notes: Robust standard errors. This synthetic fixture exists only for browser acceptance.",
        fontsize=8,
    )
    payload = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return payload


def _wait_for_server(client: httpx.Client, timeout_seconds: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            response = client.get("/api/v1/health")
            if response.status_code == 200:
                return
        except httpx.HTTPError as exc:
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"Veritas harness did not become ready: {last_error}")


def _drain_message(client: httpx.Client, audit_id: str, message: str) -> None:
    with client.stream(
        "POST",
        f"/api/v1/audits/{audit_id}/messages",
        json={"message": message},
    ) as response:
        response.raise_for_status()
        for _line in response.iter_lines():
            pass


def _seed_audit(client: httpx.Client) -> str:
    created = client.post(
        "/api/v1/audits",
        data={"title": "Card (1992) — Minimum Wages and Employment"},
        files={"file": ("card-1992.pdf", _demo_pdf(), "application/pdf")},
    )
    created.raise_for_status()
    created_payload = created.json()
    audit_id = created_payload["audit_id"]
    if int((created_payload.get("paper_summary") or {}).get("tables_detected") or 0) < 1:
        raise AssertionError("Browser fixture did not reach the real table parser")

    attachment = client.post(
        f"/api/v1/audits/{audit_id}/attachments",
        files={
            "file": (
                "replicate.py",
                b"print('replication fixture: table 4')\n",
                "text/x-python",
            )
        },
    )
    attachment.raise_for_status()

    _drain_message(client, audit_id, "/inspect")
    _drain_message(client, audit_id, '/audit row="Minimum wage" table=4 page=1')

    audit = client.get(f"/api/v1/audits/{audit_id}")
    audit.raise_for_status()
    result = audit.json().get("latest_result") or {}
    consensus = result.get("consensus") or {}
    if consensus.get("beta") != "-0.021" or consensus.get("se") != "0.026":
        raise AssertionError(f"Real detector result did not round-trip into audit state: {consensus}")
    if result.get("status") not in {"verified", "review_required", "contradiction"}:
        raise AssertionError(f"Unexpected detector state: {result.get('status')!r}")
    return audit_id


def _assert_product_information_architecture(page: Page) -> None:
    top_labels = [value.strip() for value in page.locator(".ah-workspace-tabs button").all_inner_texts()]
    if not any(label.startswith("Notes") for label in top_labels):
        raise AssertionError(f"Notes tab missing from audit workspace: {top_labels}")
    if any(label.startswith("Provenance") for label in top_labels):
        raise AssertionError(f"Provenance must remain inspector-scoped: {top_labels}")

    inspector_labels = [value.strip() for value in page.locator(".ah-tabs button").all_inner_texts()]
    if not any(label.startswith("Provenance") for label in inspector_labels):
        raise AssertionError(f"Provenance missing from Evidence Inspector: {inspector_labels}")


def _assert_reference_topology(page: Page) -> None:
    page.locator("[data-reference-sidebar]").wait_for(state="visible", timeout=10_000)
    preview = page.locator("[data-reference-evidence-preview='true']")
    preview.wait_for(state="visible", timeout=10_000)
    if "Minimum wage" not in preview.inner_text() or "-0.021" not in preview.inner_text():
        raise AssertionError("Evidence preview is not backed by the persisted detector result")
    analysis = page.locator("[data-reference-analysis='true']")
    analysis.wait_for(state="visible", timeout=10_000)
    if "-0.021" not in analysis.inner_text() or "0.026" not in analysis.inner_text():
        raise AssertionError("Selected Cell Analysis is not backed by the persisted detector consensus")
    if page.locator(".ah-left").is_visible():
        raise AssertionError("Legacy nested project rail is still visible in the desktop audit workbench")
    if page.locator("#ah-pdf").is_visible():
        raise AssertionError("Headless PDF plug-in should be replaced by the detector-backed evidence preview")
    if not page.evaluate("document.body.classList.contains('reference-audit-active')"):
        raise AssertionError("Reference-aligned audit shell did not activate")


def _capture_desktop(page: Page, base_url: str, audit_id: str, output_dir: Path) -> None:
    audit_url = f"{base_url}/#audit={quote(audit_id, safe='')}"
    page.goto(audit_url, wait_until="networkidle")
    page.locator("[data-audit-harness='true']").wait_for(state="visible", timeout=20_000)
    page.locator("[data-ah-notes-tab]").wait_for(state="visible", timeout=10_000)
    _assert_product_information_architecture(page)
    _assert_reference_topology(page)
    page.screenshot(path=output_dir / "audit-workspace.png", full_page=True)

    page.locator("[data-ah-notes-tab]").click()
    editor = page.locator("#ah-notes-editor")
    editor.wait_for(state="visible", timeout=10_000)
    if page.locator(".ah-tabs").is_visible():
        raise AssertionError("Evidence Inspector tabs remain visible while Notes is active")
    note = (
        "Visual smoke fixture.\n"
        "Confirm the selected Table 4 evidence before handoff.\n"
        "Keep reviewer context separate from evidence and provenance."
    )
    editor.fill(note)
    page.locator("#ah-notes-save").click()
    page.wait_for_function(
        """() => {
          const node = document.querySelector('#ah-notes-status');
          return node && node.textContent && node.textContent.startsWith('Saved');
        }""",
        timeout=10_000,
    )
    saved_at = page.locator("#ah-notes-saved-at").inner_text()
    if not saved_at.startswith("Saved"):
        raise AssertionError(f"Notes header timestamp did not refresh after save: {saved_at!r}")
    page.screenshot(path=output_dir / "audit-notes.png", full_page=True)

    page.locator("[data-ah-nav='reproduction']").first.click()
    page.locator("[data-reproduction-surface='true']").wait_for(state="visible", timeout=20_000)
    page.screenshot(path=output_dir / "replication-workspace.png", full_page=True)


def _capture_runs(page: Page, base_url: str, output_dir: Path) -> None:
    page.goto(base_url, wait_until="networkidle")
    page.locator("[data-view='runs']").first.click()
    page.locator("[data-runs-surface='true']").wait_for(state="visible", timeout=20_000)
    page.locator(".run-inspector-row").first.wait_for(state="visible", timeout=10_000)
    page.locator("#run-inspector-detail").wait_for(state="visible", timeout=10_000)
    page.wait_for_function(
        """() => document.body.classList.contains('reference-runs-active')""",
        timeout=10_000,
    )
    page.screenshot(path=output_dir / "runs-workspace.png", full_page=True)


def _capture_mobile(page: Page, base_url: str, audit_id: str, output_dir: Path) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto("about:blank", wait_until="load")
    page.goto(f"{base_url}/#audit={quote(audit_id, safe='')}", wait_until="networkidle")
    page.locator("[data-audit-harness='true']").wait_for(state="visible", timeout=20_000)
    page.locator("[data-ah-notes-tab]").wait_for(state="visible", timeout=10_000)
    page.screenshot(path=output_dir / "audit-mobile.png", full_page=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a real Chromium smoke test against the Veritas Research Audit Workbench."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--output-dir", default="artifacts/ui")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(base_url=base_url, timeout=60.0) as client:
        _wait_for_server(client)
        audit_id = _seed_audit(client)

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
            _capture_desktop(page, base_url, audit_id, output_dir)
            _capture_runs(page, base_url, output_dir)
            _capture_mobile(page, base_url, audit_id, output_dir)
            context.close()
            browser.close()

        audit = client.get(f"/api/v1/audits/{audit_id}")
        audit.raise_for_status()
        payload = audit.json()
        if not str(payload.get("notes") or "").startswith("Visual smoke fixture"):
            raise AssertionError("Notes did not persist through the real browser save path")
        if (payload.get("latest_result") or {}).get("consensus", {}).get("beta") != "-0.021":
            raise AssertionError("Detector result did not persist through the browser acceptance workflow")

    if page_errors:
        raise AssertionError("Browser page errors: " + " | ".join(page_errors))

    captures = sorted(path.name for path in output_dir.glob("*.png"))
    if captures != [
        "audit-mobile.png",
        "audit-notes.png",
        "audit-workspace.png",
        "replication-workspace.png",
        "runs-workspace.png",
    ]:
        raise AssertionError(f"Unexpected screenshot set: {captures}")

    print(
        json.dumps(
            {
                "status": "success",
                "audit_id": audit_id,
                "screenshots": captures,
                "output_dir": str(output_dir),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
