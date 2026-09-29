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
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((54, 58), "Card (1992) — Minimum Wages and Employment", fontsize=16)
    page.insert_text((54, 92), "Table 4. County-Level Estimates", fontsize=12)
    rows = [
        "Dependent variable      Total employment      Teenage employment",
        "Minimum wage           -0.021 (0.026)       -0.087 (0.043)",
        "Teenage share          -0.412 (0.228)       -1.102 (0.342)",
        "Unemployment rate      -0.073 (0.031)       -0.221 (0.052)",
        "County population      0.021 (0.007)        0.013 (0.011)",
        "N                      3,108                 3,108",
    ]
    y = 126
    for row in rows:
        page.insert_text((54, y), row, fontsize=9)
        y += 22
    page.insert_text(
        (54, y + 14),
        "Notes: Robust standard errors in parentheses. County and year fixed effects.",
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


def _seed_audit(client: httpx.Client) -> str:
    created = client.post(
        "/api/v1/audits",
        data={"title": "Card (1992) — Minimum Wages and Employment"},
        files={"file": ("card-1992.pdf", _demo_pdf(), "application/pdf")},
    )
    created.raise_for_status()
    audit_id = created.json()["audit_id"]

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

    with client.stream(
        "POST",
        f"/api/v1/audits/{audit_id}/messages",
        json={"message": "/inspect"},
    ) as response:
        response.raise_for_status()
        for _line in response.iter_lines():
            pass
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


def _capture_desktop(page: Page, base_url: str, audit_id: str, output_dir: Path) -> None:
    audit_url = f"{base_url}/#audit={quote(audit_id, safe='')}"
    page.goto(audit_url, wait_until="networkidle")
    page.locator("[data-audit-harness='true']").wait_for(state="visible", timeout=20_000)
    page.locator("[data-ah-notes-tab]").wait_for(state="visible", timeout=10_000)
    _assert_product_information_architecture(page)
    page.screenshot(path=output_dir / "audit-workspace.png", full_page=True)

    page.locator("[data-ah-notes-tab]").click()
    editor = page.locator("#ah-notes-editor")
    editor.wait_for(state="visible", timeout=10_000)
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
    page.screenshot(path=output_dir / "audit-notes.png", full_page=True)

    page.locator("[data-ah-nav='reproduction']").first.click()
    page.locator("[data-reproduction-surface='true']").wait_for(state="visible", timeout=20_000)
    page.screenshot(path=output_dir / "replication-workspace.png", full_page=True)


def _capture_mobile(page: Page, base_url: str, audit_id: str, output_dir: Path) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
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
            _capture_mobile(page, base_url, audit_id, output_dir)
            context.close()
            browser.close()

        audit = client.get(f"/api/v1/audits/{audit_id}")
        audit.raise_for_status()
        if not str(audit.json().get("notes") or "").startswith("Visual smoke fixture"):
            raise AssertionError("Notes did not persist through the real browser save path")

    if page_errors:
        raise AssertionError("Browser page errors: " + " | ".join(page_errors))

    captures = sorted(path.name for path in output_dir.glob("*.png"))
    if captures != [
        "audit-mobile.png",
        "audit-notes.png",
        "audit-workspace.png",
        "replication-workspace.png",
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
