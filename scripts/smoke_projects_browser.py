from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from urllib.parse import quote

import httpx
import pymupdf
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright


def _paper_pdf(title: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((54, 64), title, fontsize=16)
    page.insert_text(
        (54, 96),
        "Project grouping is organizational metadata and is not audit evidence.",
        fontsize=10,
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


def _create_audit(client: httpx.Client, title: str) -> str:
    response = client.post(
        "/api/v1/audits",
        data={"title": title},
        files={"file": ("project-paper.pdf", _paper_pdf(title), "application/pdf")},
    )
    response.raise_for_status()
    return str(response.json()["audit_id"])


def _seed_project(client: httpx.Client, audit_id: str) -> tuple[str, str]:
    name = "Labor market evidence"
    project = client.post("/api/v1/projects", json={"name": name})
    project.raise_for_status()
    project_id = str(project.json()["project_id"])
    assigned = client.post(
        f"/api/v1/audits/{audit_id}/project",
        json={"project_id": project_id},
    )
    assigned.raise_for_status()
    return project_id, name


def _assert_assignment_response(response, project_id: str | None) -> None:
    if response.status != 200:
        raise AssertionError(f"Project assignment UI returned HTTP {response.status}")
    payload = response.json()
    if payload.get("project_id") != project_id:
        raise AssertionError(f"Project assignment UI persisted wrong project: {payload}")


def _navigation_debug(page: Page, output_dir: Path) -> str:
    debug = page.evaluate(
        """() => ({
          url: location.href,
          hash: location.hash,
          bodyClass: document.body.className,
          pageTitles: [...document.querySelectorAll('.page-title')].map(node => ({text: node.textContent, visible: !!(node.offsetWidth || node.offsetHeight || node.getClientRects().length)})),
          mainText: (document.querySelector('#main-content')?.innerText || '').slice(0, 1800),
          auditRoot: document.querySelector('[data-audit-harness="true"]')?.dataset.auditId || '',
          navAudits: [...document.querySelectorAll('[data-view="audits"]')].map(node => ({tag: node.tagName, text: node.textContent, connected: node.isConnected, hidden: getComputedStyle(node).display === 'none'})),
        })"""
    )
    page.screenshot(path=output_dir / "project-navigation-debug.png", full_page=True)
    return json.dumps(debug, ensure_ascii=False, sort_keys=True)


def _exercise_projects(
    page: Page,
    base_url: str,
    assigned_audit_id: str,
    other_audit_id: str,
    project_id: str,
    project_name: str,
    output_dir: Path,
) -> None:
    page.goto(
        f"{base_url}/#audit={quote(assigned_audit_id, safe='')}",
        wait_until="networkidle",
    )
    page.locator("[data-audit-harness='true']").wait_for(state="visible", timeout=20_000)
    projects = page.locator("[data-pw-reference-projects]")
    projects.wait_for(state="visible", timeout=10_000)

    project_link = projects.locator(f"[data-pw-ref-open='{project_id}']")
    project_link.wait_for(state="visible", timeout=10_000)
    if project_name not in project_link.inner_text():
        raise AssertionError("Reference sidebar project did not render its persisted name")
    if "1" not in project_link.inner_text():
        raise AssertionError("Reference sidebar project did not render its paper count")

    selector = projects.locator("[data-pw-ref-assignment]")
    if selector.input_value() != project_id:
        raise AssertionError("Reference sidebar did not load the current paper assignment")
    if "outside evidence provenance" not in projects.inner_text().lower():
        raise AssertionError("Project control lost its non-evidentiary boundary copy")

    projects.locator("[data-pw-ref-create]").click()
    dialog = page.locator("#project-create-dialog")
    dialog.wait_for(state="visible", timeout=5_000)
    if "do not modify evidence" not in dialog.inner_text().lower():
        raise AssertionError("Project creation dialog lost its evidence-boundary copy")
    dialog.locator("[data-pw-cancel]").click()
    dialog.wait_for(state="hidden", timeout=5_000)

    with page.expect_response(
        lambda response: response.request.method == "POST"
        and response.url.endswith(f"/api/v1/audits/{assigned_audit_id}/project"),
        timeout=10_000,
    ) as unassign_info:
        page.locator("[data-pw-ref-assignment]").select_option("")
    _assert_assignment_response(unassign_info.value, None)
    page.wait_for_function(
        """() => document.querySelector('[data-pw-ref-assignment]')?.value === ''""",
        timeout=10_000,
    )

    with page.expect_response(
        lambda response: response.request.method == "POST"
        and response.url.endswith(f"/api/v1/audits/{assigned_audit_id}/project"),
        timeout=10_000,
    ) as reassign_info:
        page.locator("[data-pw-ref-assignment]").select_option(project_id)
    _assert_assignment_response(reassign_info.value, project_id)
    page.wait_for_function(
        """projectId => document.querySelector('[data-pw-ref-assignment]')?.value === projectId""",
        arg=project_id,
        timeout=10_000,
    )

    page.locator(f"[data-pw-ref-open='{project_id}']").click()
    page.wait_for_url(f"{base_url}/#audits", timeout=10_000)
    try:
        page.locator(".page-title").filter(has_text="Audits").wait_for(
            state="visible", timeout=10_000
        )
    except PlaywrightTimeoutError as exc:
        debug = _navigation_debug(page, output_dir)
        raise AssertionError(f"Project navigation did not render Audits: {debug}") from exc

    banner = page.locator("[data-pw-filter-banner]")
    banner.wait_for(state="visible", timeout=10_000)
    if project_name not in banner.inner_text():
        raise AssertionError("Project navigation did not carry the persisted project filter into Audits")
    if "1 paper" not in banner.inner_text():
        raise AssertionError(f"Project filter count is incorrect: {banner.inner_text()!r}")

    assigned_row = page.locator(f"tr[data-audit-id='{assigned_audit_id}']")
    other_row = page.locator(f"tr[data-audit-id='{other_audit_id}']")
    assigned_row.wait_for(state="visible", timeout=10_000)
    if other_row.is_visible():
        raise AssertionError("Project filter leaked an audit assigned outside the selected project")
    if project_name not in assigned_row.inner_text():
        raise AssertionError("Assigned audit row did not expose its project badge")

    page.screenshot(path=output_dir / "project-workspace.png", full_page=True)

    banner.locator("[data-pw-clear-filter]").click()
    other_row.wait_for(state="visible", timeout=10_000)
    if page.locator("[data-pw-filter-banner]").count() != 0:
        raise AssertionError("Clearing the project filter left the project banner active")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exercise persistent project grouping through the real Veritas browser UI."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--output-dir", default="artifacts/ui")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(base_url=base_url, timeout=60.0) as client:
        _wait_for_server(client)
        assigned_audit_id = _create_audit(client, "Project browser acceptance — assigned")
        other_audit_id = _create_audit(client, "Project browser acceptance — outside project")
        project_id, project_name = _seed_project(client, assigned_audit_id)

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
            _exercise_projects(
                page,
                base_url,
                assigned_audit_id,
                other_audit_id,
                project_id,
                project_name,
                output_dir,
            )
            context.close()
            browser.close()

        snapshot = client.get("/api/v1/projects")
        snapshot.raise_for_status()
        payload = snapshot.json()
        if payload.get("assignments", {}).get(assigned_audit_id) != project_id:
            raise AssertionError("Browser assignment round trip did not persist in the project store")
        if other_audit_id not in payload.get("unassigned_audit_ids", []):
            raise AssertionError("Unassigned audit disappeared from the project snapshot")

        audit = client.get(f"/api/v1/audits/{assigned_audit_id}")
        audit.raise_for_status()
        if "project_id" in audit.json():
            raise AssertionError("Project metadata leaked into the audit/evidence record")

    if page_errors:
        raise AssertionError("Browser page errors: " + " | ".join(page_errors))
    if not (output_dir / "project-workspace.png").is_file():
        raise AssertionError("Project browser acceptance did not capture project-workspace.png")

    print(
        json.dumps(
            {
                "status": "success",
                "project_id": project_id,
                "project_name": project_name,
                "assigned_audit_id": assigned_audit_id,
                "unassigned_audit_id": other_audit_id,
                "screenshot": "project-workspace.png",
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
