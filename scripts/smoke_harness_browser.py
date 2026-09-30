from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from urllib.parse import quote

import httpx
import pymupdf
from playwright.sync_api import Page, sync_playwright


def _demo_pdf(*, p_value: str = "0.419", title: str = "Card (1992) — Minimum Wages and Employment") -> bytes:
    """Build a deterministic PDF that both native parsers recognize as a regression table."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((54, 54), title, fontsize=16)
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
    data = ("Minimum wage", "-0.021", "0.026", "-0.808", p_value)
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


def _seed_audit(
    client: httpx.Client,
    *,
    title: str = "Card (1992) — Minimum Wages and Employment",
    p_value: str = "0.419",
    attach_replication: bool = True,
) -> str:
    created = client.post(
        "/api/v1/audits",
        data={"title": title},
        files={"file": ("card-1992.pdf", _demo_pdf(p_value=p_value, title=title), "application/pdf")},
    )
    created.raise_for_status()
    created_payload = created.json()
    audit_id = created_payload["audit_id"]
    if int((created_payload.get("paper_summary") or {}).get("tables_detected") or 0) < 1:
        raise AssertionError("Browser fixture did not reach the real table parser")

    if attach_replication:
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
    if consensus.get("p_value") != p_value:
        raise AssertionError(f"Real detector p-value did not round-trip into audit state: {consensus}")
    if result.get("status") not in {"verified", "review_required", "contradiction"}:
        raise AssertionError(f"Unexpected detector state: {result.get('status')!r}")
    return audit_id


def _seed_contradiction_audit(client: httpx.Client) -> tuple[str, str]:
    audit_id = _seed_audit(
        client,
        title="Card (1992) — Deliberate reporting contradiction",
        p_value="0.010",
        attach_replication=False,
    )
    audit = client.get(f"/api/v1/audits/{audit_id}")
    audit.raise_for_status()
    result = audit.json().get("latest_result") or {}
    if result.get("status") != "contradiction":
        raise AssertionError(f"Contradiction fixture did not reach the real detector failure path: {result.get('status')!r}")
    findings = result.get("findings") or []
    if not findings:
        raise AssertionError("Contradiction fixture did not persist a real detector finding")
    finding = findings[0]
    if finding.get("title") != "Regression reporting contradiction":
        raise AssertionError(f"Unexpected contradiction finding: {finding}")
    finding_id = str(finding.get("finding_id") or "")
    if not finding_id:
        raise AssertionError("Persisted detector finding has no finding_id")
    failed_checks = [
        check for check in (result.get("checks") or [])
        if str(check.get("status") or "").lower() == "fail"
    ]
    if not any(check.get("check_id") == "p_value" for check in failed_checks):
        raise AssertionError(f"Contradiction fixture did not fail the real p-value check: {failed_checks}")
    return audit_id, finding_id


def _assert_product_information_architecture(page: Page) -> None:
    top_labels = [value.strip() for value in page.locator(".ah-workspace-tabs button").all_inner_texts()]
    if not any(label.startswith("Notes") for label in top_labels):
        raise AssertionError(f"Notes tab missing from audit workspace: {top_labels}")
    if any(label.startswith("Provenance") for label in top_labels):
        raise AssertionError(f"Provenance must remain inspector-scoped: {top_labels}")

    inspector_labels = [value.strip() for value in page.locator(".ah-tabs button").all_inner_texts()]
    if not any(label.startswith("Provenance") for label in inspector_labels):
        raise AssertionError(f"Provenance missing from Evidence Inspector: {inspector_labels}")
    if not any(label.startswith("Claim Graph") for label in inspector_labels):
        raise AssertionError(f"Claim Graph missing from Evidence Inspector: {inspector_labels}")


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


def _exercise_claim_graph(page: Page, output_dir: Path) -> None:
    page.locator("[data-reference-claim-tab]").click()
    graph = page.locator("[data-reference-claim-graph='true']")
    graph.wait_for(state="visible", timeout=10_000)
    graph_text = graph.inner_text()
    for expected in ("Minimum wage", "-0.021", "0.026", "Evidence source"):
        if expected not in graph_text:
            raise AssertionError(f"Claim graph is missing persisted audit content: {expected!r}")

    estimate_node = page.locator("[data-cg-field='beta']")
    estimate_node.click()
    detail = page.locator("[data-cg-detail-panel='true']")
    detail.wait_for(state="visible", timeout=10_000)
    detail_text = detail.inner_text()
    if "Estimate" not in detail_text or "-0.021" not in detail_text:
        raise AssertionError(f"Claim graph detail panel lost the selected persisted value: {detail_text!r}")
    if estimate_node.get_attribute("aria-current") != "true":
        raise AssertionError("Selected claim graph node is not exposed through aria-current")
    if page.locator("[data-reference-claim-graph='true']").count() != 1:
        raise AssertionError("Selecting a graph node unexpectedly navigated away from Claim Graph")
    page.screenshot(path=output_dir / "claim-graph.png", full_page=True)

    page.locator("[data-cg-detail-action='source']").click()
    linked = page.locator("[data-ref-field='beta'].is-linked-selection")
    linked.wait_for(state="visible", timeout=10_000)
    if linked.inner_text().strip() != "-0.021":
        raise AssertionError("Claim graph detail action did not navigate back to the matching evidence cell")
    if not page.locator("[data-ah-tab='source']").evaluate("node => node.classList.contains('active')"):
        raise AssertionError("Claim graph evidence navigation did not reactivate Source")


def _exercise_finding_roundtrip(
    page: Page,
    base_url: str,
    audit_id: str,
    finding_id: str,
    output_dir: Path,
) -> None:
    page.goto("about:blank", wait_until="load")
    page.goto(f"{base_url}/#audit={quote(audit_id, safe='')}", wait_until="networkidle")
    root = page.locator("[data-audit-harness='true']")
    root.wait_for(state="visible", timeout=20_000)
    page.locator("[data-reference-claim-tab]").wait_for(state="visible", timeout=10_000)
    page.locator(".ah-tabs [data-ah-tab='findings']").click()

    finding_row = page.locator(f".fn-finding-row[data-fn-finding-id='{finding_id}']")
    finding_row.wait_for(state="visible", timeout=10_000)
    if "Regression reporting contradiction" not in finding_row.inner_text():
        raise AssertionError("Real detector finding did not render in the Findings inspector")
    finding_row.locator("[data-fn-graph='true']").click()

    graph = page.locator("[data-reference-claim-graph='true']")
    graph.wait_for(state="visible", timeout=10_000)
    linked_node = page.locator(f"[data-cg-finding-id='{finding_id}'].is-selected")
    linked_node.wait_for(state="visible", timeout=10_000)
    if linked_node.get_attribute("data-cg-field") != "p_value":
        raise AssertionError("Finding → Claim Graph did not select the failed p-value check")
    detail = page.locator("[data-cg-detail-panel='true']")
    detail_text = detail.inner_text()
    if "Regression reporting contradiction" not in detail_text:
        raise AssertionError(f"Finding → Claim Graph lost the persisted finding context: {detail_text!r}")
    if "incompatible" not in detail_text.lower():
        raise AssertionError(f"Finding → Claim Graph lost the detector explanation: {detail_text!r}")
    page.screenshot(path=output_dir / "finding-graph-roundtrip.png", full_page=True)

    source_action = page.locator("[data-cg-detail-source='true']")
    source_action.wait_for(state="visible", timeout=10_000)
    source_action.click()
    linked_p = page.locator("[data-ref-field='p_value'].is-linked-selection")
    linked_p.wait_for(state="visible", timeout=10_000)
    if linked_p.inner_text().strip() != "0.010":
        raise AssertionError("Finding-linked p-value check did not navigate back to the exact contradictory evidence field")

    page.locator("[data-reference-claim-tab]").click()
    graph.wait_for(state="visible", timeout=10_000)
    linked_node = page.locator(f"[data-cg-finding-id='{finding_id}'].is-selected")
    linked_node.wait_for(state="visible", timeout=10_000)
    page.locator("[data-cg-detail-action='findings']").click()
    selected_finding = page.locator(f".fn-finding-row[data-fn-finding-id='{finding_id}'].is-linked-finding")
    selected_finding.wait_for(state="visible", timeout=10_000)
    if selected_finding.get_attribute("aria-current") != "true":
        raise AssertionError("Claim Graph → Findings did not expose the selected finding through aria-current")


def _capture_desktop(page: Page, base_url: str, audit_id: str, output_dir: Path) -> None:
    audit_url = f"{base_url}/#audit={quote(audit_id, safe='')}"
    page.goto(audit_url, wait_until="networkidle")
    page.locator("[data-audit-harness='true']").wait_for(state="visible", timeout=20_000)
    page.locator("[data-ah-notes-tab]").wait_for(state="visible", timeout=10_000)
    page.locator("[data-reference-claim-tab]").wait_for(state="visible", timeout=10_000)
    _assert_product_information_architecture(page)
    _assert_reference_topology(page)
    page.screenshot(path=output_dir / "audit-workspace.png", full_page=True)

    _exercise_claim_graph(page, output_dir)

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
    root = page.locator("[data-audit-harness='true']")
    root.wait_for(state="visible", timeout=20_000)
    page.locator("[data-ah-notes-tab]").wait_for(state="visible", timeout=10_000)
    page.locator("[data-reference-claim-tab]").wait_for(state="visible", timeout=10_000)
    if page.locator(".ah-left").is_visible():
        raise AssertionError("Mobile audit still exposes the duplicate paper/run rail")
    if page.locator(".ah-header-actions").is_visible():
        raise AssertionError("Mobile audit still exposes duplicate desktop header actions")
    title = page.locator(".ah-title-row h1")
    if "Card (1992)" not in title.inner_text():
        raise AssertionError("Mobile audit title lost primary paper context")
    if title.bounding_box() is None:
        raise AssertionError("Mobile audit title is not visible")
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
        contradiction_audit_id, contradiction_finding_id = _seed_contradiction_audit(client)

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
            _exercise_finding_roundtrip(
                page,
                base_url,
                contradiction_audit_id,
                contradiction_finding_id,
                output_dir,
            )
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

        contradiction = client.get(f"/api/v1/audits/{contradiction_audit_id}")
        contradiction.raise_for_status()
        contradiction_result = contradiction.json().get("latest_result") or {}
        if contradiction_result.get("status") != "contradiction":
            raise AssertionError("Real contradiction state did not persist through browser acceptance")

    if page_errors:
        raise AssertionError("Browser page errors: " + " | ".join(page_errors))

    captures = sorted(path.name for path in output_dir.glob("*.png"))
    if captures != [
        "audit-mobile.png",
        "audit-notes.png",
        "audit-workspace.png",
        "claim-graph.png",
        "finding-graph-roundtrip.png",
        "replication-workspace.png",
        "runs-workspace.png",
    ]:
        raise AssertionError(f"Unexpected screenshot set: {captures}")

    print(
        json.dumps(
            {
                "status": "success",
                "audit_id": audit_id,
                "contradiction_audit_id": contradiction_audit_id,
                "contradiction_finding_id": contradiction_finding_id,
                "screenshots": captures,
                "output_dir": str(output_dir),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
