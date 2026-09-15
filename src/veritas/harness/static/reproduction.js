const main = document.querySelector("#main-content");

const escapeHtml = (value = "") => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

async function getJson(path) {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

function badge(status, text = status) {
  const normalized = String(status || "info").replaceAll("_", "-");
  return `<span class="badge ${escapeHtml(normalized)}">${escapeHtml(text)}</span>`;
}

function traceRow(event) {
  const status = event.status || "info";
  const kind = event.kind || "event";
  const payload = event.payload || {};
  const phase = payload.phase ? ` · ${payload.phase}` : "";
  const duration = payload.duration_ms != null ? ` · ${Number(payload.duration_ms).toFixed(0)} ms` : "";
  return `<div class="status-row">
    <span class="status-icon ${escapeHtml(status)}">${kind === "tool" ? "⌁" : kind === "replication" ? "↻" : "·"}</span>
    <div class="status-copy">
      <strong>${escapeHtml(event.title || "Replication event")}</strong>
      <small>${escapeHtml(kind)}${escapeHtml(phase)}${escapeHtml(duration)}${event.detail ? ` · ${escapeHtml(event.detail)}` : ""}</small>
    </div>
    ${badge(status)}
  </div>`;
}

async function streamReplication(auditId, prompt, timeline, button) {
  button.disabled = true;
  button.textContent = "Running…";
  timeline.innerHTML = `<div class="status-row"><span class="status-icon running">↻</span><div class="status-copy"><strong>Opening replication stream</strong><small>Waiting for structured ACP events…</small></div></div>`;
  try {
    const response = await fetch(`/api/v1/audits/${encodeURIComponent(auditId)}/replication`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/x-ndjson" },
      body: JSON.stringify({ prompt }),
    });
    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      try { detail = (await response.json()).detail || detail; } catch {}
      throw new Error(detail);
    }
    if (!response.body) throw new Error("Streaming response body is unavailable in this browser.");

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let rows = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.trim()) continue;
        rows += traceRow(JSON.parse(line));
        timeline.innerHTML = rows;
        timeline.scrollTop = timeline.scrollHeight;
      }
    }
    if (buffer.trim()) {
      rows += traceRow(JSON.parse(buffer));
      timeline.innerHTML = rows;
    }
  } catch (error) {
    timeline.innerHTML += `<div class="status-row"><span class="status-icon danger">!</span><div class="status-copy"><strong>Replication request failed</strong><small>${escapeHtml(error.message)}</small></div>${badge("danger", "error")}</div>`;
  } finally {
    button.disabled = false;
    button.textContent = "Run reproduction";
  }
}

async function enhanceReproduction() {
  if (!main || main.dataset.reproductionEnhanced === "true") return;
  if (!main.textContent.includes("Reproduction workflow")) return;
  main.dataset.reproductionEnhanced = "true";

  try {
    const [capabilities, audits] = await Promise.all([
      getJson("/api/v1/capabilities"),
      getJson("/api/v1/audits"),
    ]);
    const replication = capabilities.replication || {};
    const configured = Boolean(replication.configured);
    const options = audits.map((audit) => `<option value="${escapeHtml(audit.audit_id)}">${escapeHtml(audit.title || audit.filename || audit.audit_id)}</option>`).join("");

    main.innerHTML = `<div class="page" data-reproduction-surface="true">
      <div class="page-head">
        <div class="page-head-copy">
          <span class="eyebrow">Reproducibility</span>
          <h1 class="page-title">Reproduction</h1>
          <p class="page-subtitle">Run a server-configured ACP replication agent against a paper-specific workspace and inspect every structured update. The browser never supplies an executable command.</p>
        </div>
        <div class="page-actions">${configured ? badge("success", "agent configured") : badge("review", "fail-closed")}</div>
      </div>

      <section class="content-row">
        <article class="panel">
          <div class="panel-head"><h2>Execution boundary</h2>${configured ? `<span class="panel-link">${escapeHtml(replication.agent || "ACP agent")}</span>` : ""}</div>
          <div class="panel-body">
            <div class="stat-list">
              <div class="stat-item"><span>Agent</span><strong>${escapeHtml(replication.agent || "Not configured")}</strong></div>
              <div class="stat-item"><span>Permission policy</span><strong>${escapeHtml(replication.permission_policy || "deny")}</strong></div>
              <div class="stat-item"><span>Client-supplied commands</span><strong>${replication.client_supplied_commands ? "Allowed" : "Disabled"}</strong></div>
              <div class="stat-item"><span>Workspace security boundary</span><strong>${replication.workspace_is_security_boundary ? "Yes" : "Agent-owned"}</strong></div>
            </div>
            <p class="page-subtitle" style="margin:16px 0 0">Veritas copies only the immutable paper into a dedicated replication workspace. The selected ACP agent is responsible for its own execution sandbox. Permission requests default to deny unless the server operator explicitly opts into allow-once.</p>
          </div>
        </article>

        <article class="panel">
          <div class="panel-head"><h2>Reproduction target</h2></div>
          <div class="panel-body">
            ${configured && audits.length ? `
              <label class="field"><span>Paper</span><select id="replication-audit" class="secondary-button" style="width:100%;text-align:left">${options}</select></label>
              <label class="field" style="margin-top:14px"><span>Goal</span><textarea id="replication-prompt" rows="5" placeholder="Reproduce the paper's main reported result and record the steps, environment, outputs, and discrepancies."></textarea></label>
              <button id="replication-run" class="primary-button" style="margin-top:14px">Run reproduction</button>
            ` : `<div class="empty-state" style="min-height:220px"><div class="empty-state-inner"><div class="empty-mark">↻</div><h2>${audits.length ? "Replication agent not configured" : "No paper available"}</h2><p>${audits.length ? "Set VERITAS_REPLICATION_AGENT on the server. Veritas will keep permission policy at deny unless explicitly changed." : "Upload a paper before starting a reproduction run."}</p></div></div>`}
          </div>
        </article>
      </section>

      <section class="panel">
        <div class="panel-head"><h2>Live replication trace</h2><span class="panel-link">NDJSON · persisted to audit history</span></div>
        <div id="replication-timeline" class="panel-body status-stack" style="max-height:480px;overflow:auto">
          <div class="status-row"><span class="status-icon">·</span><div class="status-copy"><strong>No replication run in this session</strong><small>Start a run to stream agent updates, tool permissions, and completion state.</small></div></div>
        </div>
      </section>
    </div>`;

    const button = document.querySelector("#replication-run");
    if (button) {
      button.addEventListener("click", async () => {
        const auditId = document.querySelector("#replication-audit")?.value;
        const prompt = document.querySelector("#replication-prompt")?.value.trim();
        const timeline = document.querySelector("#replication-timeline");
        if (!auditId || !timeline) return;
        if (!prompt) {
          timeline.innerHTML = `<div class="status-row"><span class="status-icon review">!</span><div class="status-copy"><strong>Describe the reproduction goal</strong><small>The server accepts a goal/prompt, never a client-supplied executable command.</small></div>${badge("review")}</div>`;
          return;
        }
        await streamReplication(auditId, prompt, timeline, button);
      });
    }
  } catch (error) {
    main.innerHTML = `<div class="page"><div class="empty-state"><div class="empty-state-inner"><div class="empty-mark">!</div><h2>Reproduction surface unavailable</h2><p>${escapeHtml(error.message)}</p></div></div></div>`;
  }
}

const observer = new MutationObserver(() => {
  if (!main) return;
  if (!main.textContent.includes("Reproduction workflow")) {
    if (!main.querySelector("[data-reproduction-surface]")) delete main.dataset.reproductionEnhanced;
    return;
  }
  queueMicrotask(enhanceReproduction);
});

if (main) {
  observer.observe(main, { childList: true, subtree: true });
  queueMicrotask(enhanceReproduction);
}
