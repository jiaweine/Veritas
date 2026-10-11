"""A severed live stream must not be treated as failed or retried by POST."""

from __future__ import annotations

import argparse

from playwright.sync_api import sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser(description="Exercise safe replication disconnect recovery.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    args = parser.parse_args()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 960})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.base_url.rstrip("/") + "/#overview", wait_until="networkidle")
        page.evaluate(
            r"""() => {
              const original = window.fetch.bind(window);
              window.__replicationPostCount = 0;
              window.__replicationTerminal = false;
              const json = (value) => new Response(JSON.stringify(value), {
                status: 200,
                headers: { "Content-Type": "application/json" }
              });
              const mockRun = () => ({
                run_id: "run_mock_disconnected",
                audit_id: "audit_mock_disconnected",
                run_kind: "replication",
                tool: "replication.acp",
                phase: window.__replicationTerminal ? "finish" : "update",
                status: window.__replicationTerminal ? "success" : "running",
                events: [{
                  kind: "tool", title: "Agent started", status: "running",
                  payload: {
                    run_id: "run_mock_disconnected", run_kind: "replication",
                    phase: "start"
                  }
                }, {
                  kind: "replication", title: "Permission", status: "review",
                  payload: {run_id:"run_mock_disconnected",
                    agent_event: {kind:"permission",payload:{
                      decision:"pending",request_id:"request_replayed",
                      tool_call:{title:"Read local project"},
                      options:[{kind:"allow_once",optionId:"allow_one",name:"Allow once"}]
                    }}}
                }]
              });
              window.fetch = (input, init) => {
                const url = new URL(typeof input === "string" ? input : input.url, location.origin);
                const path = url.pathname;
                const method = init?.method || input?.method || "GET";
                if (path === "/api/v1/capabilities") {
                  return Promise.resolve(json({
                    replication: { configured: true, agent: "Fixture ACP agent",
                      interactive_approval_enabled: true,
                      permission_policy: "interactive" },
                    max_attachment_bytes: 83886080
                  }));
                }
                if (path === "/api/v1/audits" && method === "GET") {
                  return Promise.resolve(json([{
                    audit_id: "audit_mock_disconnected",
                    title: "Disconnected audit",
                    filename: "paper.pdf"
                  }]));
                }
                if (path === "/api/v1/runs" && method === "GET") {
                  return Promise.resolve(json(window.__replicationPostCount ? [mockRun()] : []));
                }
                if (path === "/api/v1/audits/audit_mock_disconnected/attachments") {
                  return Promise.resolve(json([]));
                }
                if (path === "/api/v1/runs/run_mock_disconnected" && method === "GET") {
                  return Promise.resolve(json(mockRun()));
                }
                if (path === "/api/v1/runs/run_mock_disconnected/workspace") {
                  return Promise.resolve(json({ files: [], changed_files: [], staged_inputs_unchanged: true }));
                }
                if (path === "/api/v1/audits/audit_mock_disconnected/replication" && method === "POST") {
                  window.__replicationPostCount += 1;
                  const bytes = new TextEncoder().encode(JSON.stringify({
                    kind: "tool", title: "Agent started", status: "running",
                    payload: {
                      run_id: "run_mock_disconnected", phase: "start",
                      run_kind: "replication"
                    }
                  () + "\n" + JSON.stringify({
                    kind:"replication",title:"Permission",status:"review",
                    payload:{run_id:"run_mock_disconnected",
                      agent_event:{kind:"permission",payload:{
                        decision:"pending",request_id:"request_replayed",
                        tool_call:{title:"Read local project"},
                        options:[{kind:"allow_once",optionId:"allow_one",name:"Allow once"}]
                      }}}
                  }) + "\n");
                  const stream = new ReadableStream({
                    start(controller) {
                      controller.enqueue(bytes);
                      setTimeout(() => controller.error(new Error("Fixture stream disconnected")), 2500);
                    }
                  });
                  return Promise.resolve(new Response(stream, {
                    status: 200,
                    headers: { "Content-Type": "application/x-ndjson" }
                  }));
                }
                return original(input, init);
              };
            }"""
        )
        page.locator(".sidebar [data-view='reproduction']").click()
        page.locator("#rep-run").wait_for(state="visible", timeout=20_000)
        page.locator("#rep-prompt").fill("Inspect the staged paper, do not change files.")
        page.locator("#rep-run").click()
        page.locator(".rep-permission.pending").wait_for(state="visible", timeout=15_000)
        # Changing an inspector tab and refreshing run history must not
        # detach the live event stream from its visible message surface.
        page.locator('[data-rep-tab="files"]').click()
        assert page.locator(".rep-permission.pending").is_visible()
        page.locator("#rep-refresh-runs").click()
        assert page.locator(".rep-permission.pending").is_visible()
        warning = page.locator(".rep-connection-warning")
        warning.wait_for(state="visible", timeout=20_000)
        assert "may still be active" in warning.inner_text().lower()
        assert page.locator("[data-permission-decision]").count() == 0, (
            "Replayed permission requests must never remain actionable"
        )
        assert page.evaluate("() => window.__replicationPostCount") == 1
        page.locator("[data-rep-recover]").wait_for(state="visible")
        page.evaluate("() => { window.__replicationTerminal = true; }")
        page.locator("[data-rep-recover]").click()
        warning.wait_for(state="hidden", timeout=15_000)
        assert page.evaluate("() => window.__replicationPostCount") == 1, (
            "A disconnected request must never be re-submitted as a new execution"
        )
        browser.close()
        assert not errors, errors
        print("Live replication disconnect reconciled by GET, no repeated POST")


if __name__ == "__main__":
    main()
