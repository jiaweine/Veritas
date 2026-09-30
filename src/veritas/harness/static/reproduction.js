const main = document.querySelector("#main-content");
const REPLICATION_CONTEXT_KEY = "veritas.replication.context.v1";
const FINDING_FOCUS_KEY = "veritas.finding.focus.v1";

const repState = {
  capabilities: null,
  audits: [],
  selectedAuditId: "",
  attachments: [],
  runs: [],
  selectedRunId: "",
  selectedRun: null,
  workspace: null,
  selectedFile: null,
  inspectorTab: "changes",
  streaming: false,
  maxAttachmentBytes: 80 * 1024 * 1024,
  findingContext: null,
  draftPrompt: "",
};

const escapeHtml = (value = "") => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

async function request(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try { detail = (await response.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return response;
}

async function getJson(path) {
  return request(path, { headers: { Accept: "application/json" } }).then((response) => response.json());
}

function formatBytes(value) {
  const bytes = Number(value) || 0;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(bytes < 10 * 1024 ? 1 : 0)} KiB`;
  return `${(bytes / 1024 / 1024).toFixed(bytes < 10 * 1024 * 1024 ? 1 : 0)} MiB`;
}

function formatDuration(value) {
  const ms = Number(value);
  if (!Number.isFinite(ms)) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(ms < 10000 ? 2 : 1)} s`;
}

function formatTime(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function badge(status, label = status) {
  const normalized = String(status || "info").replaceAll("_", "-");
  return `<span class="badge ${escapeHtml(normalized)}">${escapeHtml(label || "info")}</span>`;
}

function selectedAudit() {
  return repState.audits.find((audit) => audit.audit_id === repState.selectedAuditId) || null;
}

function normalizeFindingContext(value, auditId = "") {
  if (!value || typeof value !== "object") return null;
  const findingId = String(value.findingId || value.finding_id || "").trim();
  const resolvedAuditId = String(value.auditId || value.audit_id || auditId || "").trim();
  if (!findingId || !resolvedAuditId) return null;
  return {
    auditId: resolvedAuditId,
    findingId,
    title: String(value.title || "Finding"),
    explanation: String(value.explanation || ""),
    severity: String(value.severity || "review"),
    source: value.source && typeof value.source === "object" ? value.source : {},
    bindingOnly: value.binding_only !== false,
  };
}

function takePendingFindingContext() {
  let value = null;
  try {
    const raw = sessionStorage.getItem(REPLICATION_CONTEXT_KEY);
    if (raw) value = JSON.parse(raw);
    sessionStorage.removeItem(REPLICATION_CONTEXT_KEY);
  } catch {}
  return normalizeFindingContext(value);
}

function findingSourceSummary(context = repState.findingContext) {
  const source = context?.source || {};
  return [
    source.table,
    source.row,
    source.column,
    source.page ? `p.${source.page}` : "",
  ].filter(Boolean).join(" · ");
}

function findingPrompt(context) {
  const source = findingSourceSummary(context);
  const location = source ? ` at ${source}` : "";
  return `Reproduce the result linked to finding “${context.title}”${location}. Inspect the attached code/data, identify the command and output that correspond to this paper result, compare the reproduced value with the paper evidence, and report any discrepancy. Do not treat a successful code run as resolving the finding; preserve the evidence trail and request approval before sensitive actions.`;
}

function renderFindingContext(context = repState.findingContext) {
  if (!context) return "";
  const source = findingSourceSummary(context);
  return `<div class="rep-plan-card" data-rep-finding-context="true">
    <div class="rep-card-kicker">SCIENTIFIC CONTEXT · ${escapeHtml(context.severity || "review")}</div>
    <strong>${escapeHtml(context.title || "Finding")}</strong>
    ${source ? `<p>${escapeHtml(source)}</p>` : ""}
    <p>Context binding only. A completed coding-agent run records execution provenance; it does not by itself verify or resolve this finding.</p>
    <div class="rep-permission-actions"><button type="button" class="rep-reject" data-rep-return-finding="true">← Back to finding</button></div>
  </div>`;
}

function returnToFinding(context = repState.findingContext) {
  if (!context?.auditId || !context?.findingId) return;
  try {
    sessionStorage.setItem(FINDING_FOCUS_KEY, JSON.stringify({
      auditId: context.auditId,
      findingId: context.findingId,
    }));
  } catch {}
  location.hash = `audit=${encodeURIComponent(context.auditId)}`;
  location.reload();
}

function replicationRuns() {
  return repState.runs.filter((run) => run.run_kind === "replication" && (!repState.selectedAuditId || run.audit_id === repState.selectedAuditId));
}

function renderShell() {
  const capability = repState.capabilities?.replication || {};
  const configured = Boolean(capability.configured);
  const interactive = Boolean(capability.interactive_approval_enabled);
  const audits = repState.audits;
  const selected = selectedAudit();
  const runs = replicationRuns();
  const auditOptions = audits.map((audit) => `<option value="${escapeHtml(audit.audit_id)}" ${audit.audit_id === repState.selectedAuditId ? "selected" : ""}>${escapeHtml(audit.title || audit.filename || audit.audit_id)}</option>`).join("");

  main.innerHTML = `<div class="page replication-product" data-reproduction-surface="true">
    <div class="rep-topbar">
      <div class="rep-title-block">
        <span class="eyebrow">Replication workspace</span>
        <div class="rep-title-row"><h1>Reproduce with an agent</h1>${configured ? badge("success", capability.agent || "ACP agent") : badge("review", "agent not configured")}</div>
        <p>Code-agent execution stays separate from the Audit Agent. Veritas supplies immutable paper/artifact copies, records ACP events, and independently inspects the run workspace.</p>
      </div>
      <div class="rep-boundary-pills">
        <span>Permission · <b>${escapeHtml(capability.permission_policy || "deny")}</b></span>
        <span>Approval UI · <b>${interactive ? "interactive" : "off"}</b></span>
        <span>Sandbox · <b>agent-owned</b></span>
      </div>
    </div>

    ${!audits.length ? `<div class="empty-state rep-empty"><div class="empty-state-inner"><div class="empty-mark">↻</div><h2>No paper available</h2><p>Upload a research paper first, then attach code/data and open a replication workspace.</p></div></div>` : `
    <div class="rep-grid">
      <aside class="rep-left" aria-label="Replication project">
        <section class="rep-section">
          <div class="rep-section-head"><span>Project</span><span class="rep-dot ${configured ? "online" : ""}"></span></div>
          <label class="rep-label" for="rep-audit-select">Paper</label>
          <select id="rep-audit-select" class="rep-select" ${repState.streaming ? "disabled" : ""}>${auditOptions}</select>
          <div class="rep-project-meta">
            <span class="mono">${escapeHtml(repState.selectedAuditId)}</span>
            <small>${selected ? escapeHtml(selected.filename || "paper.pdf") : ""}</small>
          </div>
        </section>

        <section class="rep-section rep-artifact-section">
          <div class="rep-section-head"><span>Artifacts</span><button id="rep-add-artifact" class="rep-icon-action" title="Attach immutable files" ${repState.streaming ? "disabled" : ""}>＋</button></div>
          <input id="rep-artifact-input" type="file" multiple hidden />
          <div id="rep-artifact-list" class="rep-artifact-list">${renderArtifactList()}</div>
        </section>

        <section class="rep-section rep-history-section">
          <div class="rep-section-head"><span>Runs</span><button id="rep-refresh-runs" class="rep-icon-action" title="Refresh runs">↻</button></div>
          <div id="rep-run-list" class="rep-run-list">${renderRunList(runs)}</div>
        </section>
      </aside>

      <section class="rep-center" aria-label="Agent conversation">
        <div class="rep-center-head">
          <div><strong>${escapeHtml(capability.agent || "Replication agent")}</strong><small>${configured ? "ACP session · structured events" : "Configure VERITAS_REPLICATION_AGENT"}</small></div>
          <div class="rep-run-actions"><span id="rep-live-state" class="rep-live-state ${repState.streaming ? "running" : ""}"><i></i>${repState.streaming ? "running" : "ready"}</span><button id="rep-cancel" class="rep-cancel" ${repState.streaming && repState.selectedRunId ? "" : "disabled"}>Stop</button></div>
        </div>
        ${renderFindingContext()}
        <div id="rep-thread" class="rep-thread">${renderPersistedThread(repState.selectedRun)}</div>
        <div class="rep-composer-wrap">
          ${interactive ? `<div class="rep-approval-note">Tool permissions pause here until you choose <b>Allow once</b> or <b>Reject</b>. Permanent approval is never offered by Veritas.</div>` : ""}
          <div class="rep-composer">
            <textarea id="rep-prompt" rows="3" ${configured && !repState.streaming ? "" : "disabled"} placeholder="Ask the replication agent to inspect code, run the project, reproduce a table or figure, compare outputs, or explain a discrepancy…">${escapeHtml(repState.draftPrompt)}</textarea>
            <div class="rep-composer-foot"><span>⌘/Ctrl + Enter to run · natural-language goal only</span><button id="rep-run" class="primary-button" ${configured && !repState.streaming ? "" : "disabled"}>Run agent ↑</button></div>
          </div>
        </div>
      </section>

      <aside class="rep-right" aria-label="Workspace inspector">
        <div class="rep-tabs" role="tablist">
          <button data-rep-tab="changes" class="${repState.inspectorTab === "changes" ? "active" : ""}">Changes</button>
          <button data-rep-tab="files" class="${repState.inspectorTab === "files" ? "active" : ""}">Files</button>
          <button data-rep-tab="run" class="${repState.inspectorTab === "run" ? "active" : ""}">Run</button>
          <button id="rep-refresh-workspace" class="rep-tab-refresh" title="Refresh workspace">↻</button>
        </div>
        <div id="rep-inspector" class="rep-inspector">${renderInspector()}</div>
      </aside>
    </div>`}
  </div>`;

  if (audits.length) bindSurface();
}

function renderArtifactList() {
  if (!repState.attachments.length) return `<div class="rep-mini-empty">No code or data attached yet.</div>`;
  return repState.attachments.map((item) => `<a class="rep-artifact" href="/api/v1/audits/${encodeURIComponent(repState.selectedAuditId)}/attachments/${encodeURIComponent(item.attachment_id)}" download>
    <span class="rep-file-icon">◇</span><span><strong>${escapeHtml(item.filename)}</strong><small>${formatBytes(item.size_bytes)} · ${escapeHtml(String(item.sha256 || "").slice(0, 10))}…</small></span>
  </a>`).join("");
}

function renderRunList(runs) {
  if (!runs.length) return `<div class="rep-mini-empty">No replication runs for this paper.</div>`;
  return runs.map((run) => `<button class="rep-run-row ${run.run_id === repState.selectedRunId ? "selected" : ""}" data-run-id="${escapeHtml(run.run_id)}">
    <span class="rep-run-glyph ${escapeHtml(run.status || "")}">↻</span>
    <span><strong>${escapeHtml(run.phase === "cancelled" ? "Cancelled run" : run.task || "Replication run")}</strong><small>${formatTime(run.created_at)} · ${formatDuration(run.duration_ms)}</small></span>
    <em>${escapeHtml(run.phase || run.status || "done")}</em>
  </button>`).join("");
}

function renderPersistedThread(detail) {
  if (!detail?.events?.length) {
    return `<div class="rep-thread-empty"><div class="rep-agent-orb">V</div><h2>Ready to reproduce</h2><p>Attach the paper's code/data, describe a target result, then inspect commands, approvals, file changes, and outputs as one auditable run.</p><div class="rep-suggestions"><button data-suggest="Inspect the attached project and explain how to reproduce the paper's main result. Do not change files yet.">Inspect project</button><button data-suggest="Run the project's existing tests and reproduction commands, then compare outputs with the paper.">Run reproduction</button><button data-suggest="Identify which files and commands produce the paper's main table or figure, and report any discrepancy.">Trace table/figure</button></div></div>`;
  }
  return detail.events.map((event) => eventCard(event, detail.run_id)).join("");
}

function eventCard(event, runId) {
  if (event.kind === "replication_context") {
    const context = normalizeFindingContext(event.payload?.origin_finding, event.audit_id || repState.selectedAuditId);
    const source = findingSourceSummary(context);
    return `<div class="rep-system-event"><span class="rep-system-icon review">◇</span><div><strong>${escapeHtml(event.title || "Scientific finding linked")}</strong><small>${escapeHtml(context?.title || event.detail || "Finding context")}${source ? ` · ${escapeHtml(source)}` : ""}</small></div>${badge("review", "context")}</div>`;
  }
  if (event.kind === "tool") {
    const payload = event.payload || {};
    const phase = payload.phase || "update";
    const icon = phase === "error" ? "!" : phase === "finish" ? "✓" : "↻";
    return `<div class="rep-system-event"><span class="rep-system-icon ${escapeHtml(event.status || "")}">${icon}</span><div><strong>${escapeHtml(event.title || "Replication run")}</strong><small>${escapeHtml(event.detail || "")}${payload.duration_ms != null ? ` · ${formatDuration(payload.duration_ms)}` : ""}</small></div>${badge(event.status || "info", phase)}</div>`;
  }
  if (event.kind !== "replication") return "";
  const agent = event.payload?.agent_event || {};
  return agentEventCard(agent, runId || event.payload?.run_id || "");
}

function agentEventCard(agent, runId) {
  const kind = agent.kind || "agent_update";
  const payload = agent.payload || {};
  if (kind === "permission") return permissionCard(agent, runId);
  if (kind === "turn_cancelled") return `<div class="rep-system-event"><span class="rep-system-icon review">■</span><div><strong>Run cancelled</strong><small>${escapeHtml(agent.detail || "Agent process stopped")}</small></div>${badge("review", "cancelled")}</div>`;
  if (kind === "turn_completed") return `<div class="rep-system-event"><span class="rep-system-icon success">✓</span><div><strong>Agent turn completed</strong><small>${escapeHtml(agent.detail || "end_turn")}</small></div>${badge("success", "done")}</div>`;
  if (kind === "agent") return `<div class="rep-system-event"><span class="rep-system-icon running">↻</span><div><strong>${escapeHtml(agent.title || "Starting agent")}</strong><small>${escapeHtml(agent.detail || "")}</small></div></div>`;

  const update = payload.update || {};
  const updateKind = String(payload.update_kind || update.sessionUpdate || update.session_update || agent.title || "update");
  const content = update.content || {};
  const text = typeof content.text === "string" ? content.text : agent.detail || "";
  const normalized = updateKind.toLowerCase();

  if (normalized.includes("agent_message")) {
    return `<article class="rep-message agent"><div class="rep-avatar">V</div><div class="rep-message-body"><div class="rep-message-label">Replication agent</div><div class="rep-message-text">${escapeHtml(text)}</div></div></article>`;
  }
  if (normalized.includes("thought") || normalized.includes("reason")) {
    return `<details class="rep-reasoning"><summary>Reasoning update</summary><div>${escapeHtml(text || "Structured reasoning event")}</div></details>`;
  }
  if (normalized.includes("plan")) {
    return `<div class="rep-plan-card"><div class="rep-card-kicker">PLAN</div><strong>${escapeHtml(update.title || agent.title || "Agent plan")}</strong>${text ? `<p>${escapeHtml(text)}</p>` : ""}${structuredPayload(update)}</div>`;
  }
  if (normalized.includes("tool") || normalized.includes("terminal") || normalized.includes("command")) {
    const title = update.title || update.name || agent.title || "Tool call";
    const status = update.status || agent.status || "running";
    return `<div class="rep-tool-card"><div class="rep-tool-head"><span>⌘</span><strong>${escapeHtml(title)}</strong>${badge(status, status)}</div>${text ? `<pre>${escapeHtml(text)}</pre>` : ""}${structuredPayload(update)}</div>`;
  }
  if (normalized.includes("file") || normalized.includes("diff")) {
    return `<div class="rep-tool-card file"><div class="rep-tool-head"><span>Δ</span><strong>${escapeHtml(update.title || "File update")}</strong>${badge(agent.status || "info")}</div>${text ? `<pre>${escapeHtml(text)}</pre>` : ""}${structuredPayload(update)}</div>`;
  }
  return `<div class="rep-update-card"><span>${escapeHtml(updateKind)}</span>${text ? `<p>${escapeHtml(text)}</p>` : structuredPayload(update)}</div>`;
}

function permissionCard(agent, runId) {
  const payload = agent.payload || {};
  const pending = payload.decision === "pending";
  const options = Array.isArray(payload.options) ? payload.options : [];
  const allowOptions = options.filter((item) => item.kind === "allow_once" && (item.optionId || item.option_id));
  const tool = payload.tool_call || {};
  const detail = tool.title || tool.name || agent.title || "Agent tool request";
  return `<div class="rep-permission ${pending ? "pending" : "resolved"}" data-permission-card="${escapeHtml(payload.request_id || "")}">
    <div class="rep-permission-icon">!</div><div class="rep-permission-copy"><div class="rep-card-kicker">PERMISSION</div><strong>${escapeHtml(detail)}</strong><p>${pending ? "This operation is paused. Review it before continuing." : escapeHtml(agent.detail || "Permission resolved.")}</p>${structuredPayload(tool)}</div>
    ${pending ? `<div class="rep-permission-actions"><button class="rep-reject" data-permission-decision="reject" data-run-id="${escapeHtml(runId)}" data-request-id="${escapeHtml(payload.request_id || "")}">Reject</button>${allowOptions.map((item) => `<button class="rep-allow" data-permission-decision="allow_once" data-run-id="${escapeHtml(runId)}" data-request-id="${escapeHtml(payload.request_id || "")}" data-option-id="${escapeHtml(item.optionId || item.option_id)}">${escapeHtml(item.name || "Allow once")}</button>`).join("")}</div>` : `<div class="rep-permission-result">${badge(agent.status || "info", payload.decision || "resolved")}</div>`}
  </div>`;
}

function structuredPayload(value) {
  if (!value || typeof value !== "object") return "";
  const interesting = {};
  for (const key of ["status", "kind", "rawInput", "raw_input", "locations", "content", "terminalId", "terminal_id"]) {
    if (value[key] != null && key !== "content") interesting[key] = value[key];
  }
  if (!Object.keys(interesting).length) return "";
  const text = JSON.stringify(interesting, null, 2);
  return `<pre class="rep-json">${escapeHtml(text.slice(0, 12000))}</pre>`;
}

function renderInspector() {
  if (repState.selectedFile) return renderFileInspector(repState.selectedFile);
  if (repState.inspectorTab === "run") return renderRunInspector();
  if (!repState.workspace) {
    return `<div class="rep-inspector-empty"><span>▦</span><strong>No workspace snapshot</strong><p>Run the agent or select a previous replication run. Files are inspected from disk, independently of the agent's narrative.</p></div>`;
  }
  const files = repState.workspace.files || [];
  const visible = repState.inspectorTab === "changes" ? files.filter((item) => item.change !== "original") : files;
  if (!visible.length) {
    return `<div class="rep-inspector-empty"><span>✓</span><strong>${repState.inspectorTab === "changes" ? "No workspace changes" : "No files"}</strong><p>${repState.workspace.staged_inputs_unchanged ? "Staged paper and artifacts match their immutable source hashes." : "Inspect the workspace integrity warning above."}</p></div>`;
  }
  return `${repState.workspace.staged_inputs_unchanged ? "" : `<div class="rep-integrity-warning"><strong>Staged input drift detected</strong><span>${escapeHtml((repState.workspace.staged_input_drift || []).join(", "))}</span></div>`}<div class="rep-file-list">${visible.map((file) => `<button class="rep-workspace-file" data-workspace-file="${escapeHtml(file.path)}"><span class="rep-change ${escapeHtml(file.change)}">${file.change === "created" ? "+" : file.change === "deleted" ? "−" : file.change === "modified" ? "M" : file.change === "unsafe_link" ? "!" : "·"}</span><span><strong>${escapeHtml(file.path)}</strong><small>${formatBytes(file.size_bytes)} · ${escapeHtml(file.change)}</small></span>${file.binary ? `<em>binary</em>` : ""}</button>`).join("")}</div>`;
}

function renderRunInspector() {
  const run = repState.selectedRun;
  if (!run) return `<div class="rep-inspector-empty"><span>⌁</span><strong>No run selected</strong><p>Select a run from the left rail.</p></div>`;
  const workspace = repState.workspace;
  const origin = normalizeFindingContext(run.origin_finding, run.audit_id || repState.selectedAuditId);
  const originSource = findingSourceSummary(origin);
  return `<div class="rep-run-inspector">
    <div class="rep-inspector-metric"><span>Status</span><strong>${escapeHtml(run.phase || run.status || "—")}</strong></div>
    <div class="rep-inspector-metric"><span>Duration</span><strong>${formatDuration(run.duration_ms)}</strong></div>
    <div class="rep-inspector-metric"><span>Events</span><strong>${run.events?.length || 0}</strong></div>
    <div class="rep-inspector-metric"><span>Changed files</span><strong>${workspace?.changed_files?.length || 0}</strong></div>
    <div class="rep-inspector-block"><span>Run ID</span><code>${escapeHtml(run.run_id)}</code></div>
    <div class="rep-inspector-block"><span>Artifact</span><code>${escapeHtml(run.artifact_id || "—")}</code></div>
    ${origin ? `<div class="rep-inspector-block" data-rep-run-origin="true"><span>Scientific context</span><p><b>${escapeHtml(origin.title)}</b>${originSource ? `<br>${escapeHtml(originSource)}` : ""}<br>Binding only — this run does not automatically resolve the detector finding.</p><button type="button" class="rep-reject" data-rep-return-finding="true">Open finding</button></div>` : ""}
    <div class="rep-inspector-block"><span>Workspace trust</span><p>Veritas inspects this directory, but the directory itself is not a sandbox. Process, filesystem, and network isolation belong to the configured agent runtime.</p></div>
  </div>`;
}

function renderFileInspector(file) {
  const title = escapeHtml(file.path || "file");
  const mode = file.diff ? "Diff" : "Preview";
  const body = file.diff || file.content || (file.binary ? "Binary file preview is intentionally disabled." : "No text content.");
  return `<div class="rep-file-detail"><div class="rep-file-detail-head"><button id="rep-file-back">←</button><div><strong>${title}</strong><small>${escapeHtml(file.change || "file")} · ${formatBytes(file.size_bytes)}</small></div><span>${mode}</span></div>${file.immutable_input && file.change !== "original" ? `<div class="rep-integrity-warning"><strong>Staged input changed inside the agent workspace</strong><span>The immutable source artifact stored by Veritas is unchanged; this copy drifted during the run.</span></div>` : ""}<pre class="rep-code ${file.diff ? "diff" : ""}">${escapeHtml(body)}</pre>${file.truncated ? `<div class="rep-truncated">Preview capped at 512 KiB.</div>` : ""}</div>`;
}

function bindSurface() {
  document.querySelector("#rep-audit-select")?.addEventListener("change", async (event) => {
    if (repState.streaming) return;
    repState.selectedAuditId = event.target.value;
    repState.selectedRunId = "";
    repState.selectedRun = null;
    repState.workspace = null;
    repState.selectedFile = null;
    repState.findingContext = null;
    repState.draftPrompt = "";
    try { sessionStorage.removeItem(REPLICATION_CONTEXT_KEY); } catch {}
    await Promise.all([loadAttachments(), loadRuns()]);
    const first = replicationRuns()[0];
    if (first) await selectRun(first.run_id, false);
    renderShell();
  });

  document.querySelector("#rep-add-artifact")?.addEventListener("click", () => document.querySelector("#rep-artifact-input")?.click());
  document.querySelector("#rep-artifact-input")?.addEventListener("change", uploadArtifacts);
  document.querySelector("#rep-refresh-runs")?.addEventListener("click", async () => { await loadRuns(); renderShell(); });
  document.querySelector("#rep-run")?.addEventListener("click", runAgent);
  document.querySelector("#rep-cancel")?.addEventListener("click", cancelRun);
  document.querySelector("#rep-refresh-workspace")?.addEventListener("click", async () => { await loadWorkspace(repState.selectedRunId); renderShell(); });
  document.querySelectorAll("[data-rep-return-finding]").forEach((button) => button.addEventListener("click", () => returnToFinding()));

  document.querySelector("#rep-prompt")?.addEventListener("input", (event) => { repState.draftPrompt = event.target.value; });
  document.querySelector("#rep-prompt")?.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      void runAgent();
    }
  });
  document.querySelectorAll("[data-suggest]").forEach((button) => button.addEventListener("click", () => {
    const input = document.querySelector("#rep-prompt");
    if (input) { input.value = button.dataset.suggest || ""; repState.draftPrompt = input.value; input.focus(); }
  }));
  document.querySelectorAll("[data-run-id]").forEach((button) => {
    if (button.dataset.permissionDecision) return;
    button.addEventListener("click", async () => { await selectRun(button.dataset.runId); renderShell(); });
  });
  document.querySelectorAll("[data-rep-tab]").forEach((button) => button.addEventListener("click", () => {
    repState.inspectorTab = button.dataset.repTab;
    repState.selectedFile = null;
    renderShell();
  }));
  document.querySelectorAll("[data-workspace-file]").forEach((button) => button.addEventListener("click", async () => {
    await openWorkspaceFile(button.dataset.workspaceFile);
    renderShell();
  }));
  document.querySelector("#rep-file-back")?.addEventListener("click", () => { repState.selectedFile = null; renderShell(); });
  bindPermissionButtons();
}

function bindPermissionButtons(root = document) {
  root.querySelectorAll("[data-permission-decision]").forEach((button) => button.addEventListener("click", async () => {
    button.disabled = true;
    const runId = button.dataset.runId;
    const requestId = button.dataset.requestId;
    const decision = button.dataset.permissionDecision;
    const optionId = button.dataset.optionId || null;
    try {
      await request(`/api/v1/replication/runs/${encodeURIComponent(runId)}/permissions/${encodeURIComponent(requestId)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, option_id: optionId }),
      });
      const card = button.closest(".rep-permission");
      if (card) card.querySelector(".rep-permission-actions").innerHTML = `<span class="rep-decision-sent">${decision === "allow_once" ? "Allow-once sent" : "Rejected"}</span>`;
    } catch (error) {
      button.disabled = false;
      showInlineError(error.message);
    }
  }));
}

async function loadAttachments() {
  if (!repState.selectedAuditId) { repState.attachments = []; return; }
  repState.attachments = await getJson(`/api/v1/audits/${encodeURIComponent(repState.selectedAuditId)}/attachments`);
}

async function loadRuns() {
  repState.runs = await getJson("/api/v1/runs");
}

async function selectRun(runId, refresh = true) {
  if (!runId) return;
  repState.selectedRunId = runId;
  repState.selectedFile = null;
  try {
    const [detail] = await Promise.all([
      getJson(`/api/v1/runs/${encodeURIComponent(runId)}`),
      loadWorkspace(runId),
    ]);
    repState.selectedRun = detail;
    repState.findingContext = normalizeFindingContext(detail.origin_finding, detail.audit_id || repState.selectedAuditId);
    repState.draftPrompt = "";
  } catch (error) {
    if (refresh) showInlineError(error.message);
  }
}

async function loadWorkspace(runId) {
  if (!runId) { repState.workspace = null; return; }
  try {
    repState.workspace = await getJson(`/api/v1/runs/${encodeURIComponent(runId)}/workspace`);
  } catch (error) {
    repState.workspace = null;
    if (!repState.streaming && !String(error.message).includes("not found")) throw error;
  }
}

async function openWorkspaceFile(path) {
  if (!repState.selectedRunId || !path) return;
  repState.selectedFile = await getJson(`/api/v1/runs/${encodeURIComponent(repState.selectedRunId)}/workspace/file?path=${encodeURIComponent(path)}`);
}

async function uploadArtifacts(event) {
  const files = [...(event.target.files || [])];
  event.target.value = "";
  if (!files.length || !repState.selectedAuditId || repState.streaming) return;
  const oversized = files.find((file) => file.size > repState.maxAttachmentBytes);
  if (oversized) { showInlineError(`${oversized.name} exceeds ${formatBytes(repState.maxAttachmentBytes)}.`); return; }
  try {
    for (const file of files) {
      const body = new FormData();
      body.append("file", file, file.name);
      await request(`/api/v1/audits/${encodeURIComponent(repState.selectedAuditId)}/attachments`, { method: "POST", body });
    }
    await loadAttachments();
    renderShell();
  } catch (error) { showInlineError(error.message); }
}

async function runAgent() {
  if (repState.streaming || !repState.selectedAuditId) return;
  const promptNode = document.querySelector("#rep-prompt");
  const prompt = promptNode?.value.trim();
  if (!prompt) { showInlineError("Describe a reproduction goal first."); return; }
  repState.draftPrompt = prompt;

  repState.streaming = true;
  repState.selectedRunId = "";
  repState.selectedRun = null;
  repState.workspace = null;
  repState.selectedFile = null;
  const thread = document.querySelector("#rep-thread");
  if (thread) thread.innerHTML = `<article class="rep-message user"><div class="rep-avatar user">You</div><div class="rep-message-body"><div class="rep-message-label">Reproduction goal</div><div class="rep-message-text">${escapeHtml(prompt)}</div></div></article>`;
  setRunningUi(true);

  try {
    const response = await request(`/api/v1/audits/${encodeURIComponent(repState.selectedAuditId)}/replication`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/x-ndjson" },
      body: JSON.stringify({ prompt, finding_id: repState.findingContext?.findingId || null }),
    });
    if (!response.body) throw new Error("Streaming response body is unavailable.");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    const observed = [];
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line);
        observed.push(event);
        consumeLiveEvent(event, thread);
      }
    }
    if (buffer.trim()) {
      const event = JSON.parse(buffer);
      observed.push(event);
      consumeLiveEvent(event, thread);
    }
    const finalRunId = repState.selectedRunId || [...observed].reverse().map((event) => event.payload?.run_id).find(Boolean);
    repState.streaming = false;
    await loadRuns();
    if (finalRunId) await selectRun(finalRunId, false);
    renderShell();
  } catch (error) {
    repState.streaming = false;
    setRunningUi(false);
    if (thread) thread.insertAdjacentHTML("beforeend", `<div class="rep-system-event"><span class="rep-system-icon danger">!</span><div><strong>Replication request failed</strong><small>${escapeHtml(error.message)}</small></div>${badge("danger", "error")}</div>`);
  }
}

function consumeLiveEvent(event, thread) {
  const runId = event.payload?.run_id;
  if (runId && !repState.selectedRunId) {
    repState.selectedRunId = runId;
    const cancel = document.querySelector("#rep-cancel");
    if (cancel) cancel.disabled = false;
  }
  if (event.kind === "replication_context") {
    const context = normalizeFindingContext(event.payload?.origin_finding, repState.selectedAuditId);
    if (context) repState.findingContext = context;
  }
  if (!thread) return;
  const html = eventCard(event, repState.selectedRunId);
  if (html) {
    thread.insertAdjacentHTML("beforeend", html);
    bindPermissionButtons(thread);
    thread.scrollTop = thread.scrollHeight;
  }
}

async function cancelRun() {
  if (!repState.streaming || !repState.selectedRunId) return;
  try {
    await request(`/api/v1/replication/runs/${encodeURIComponent(repState.selectedRunId)}/cancel`, { method: "POST" });
    const button = document.querySelector("#rep-cancel");
    if (button) { button.disabled = true; button.textContent = "Stopping…"; }
  } catch (error) { showInlineError(error.message); }
}

function setRunningUi(running) {
  const state = document.querySelector("#rep-live-state");
  const run = document.querySelector("#rep-run");
  const cancel = document.querySelector("#rep-cancel");
  const select = document.querySelector("#rep-audit-select");
  const prompt = document.querySelector("#rep-prompt");
  if (state) { state.classList.toggle("running", running); state.innerHTML = `<i></i>${running ? "running" : "ready"}`; }
  if (run) run.disabled = running;
  if (cancel) cancel.disabled = !running || !repState.selectedRunId;
  if (select) select.disabled = running;
  if (prompt) prompt.disabled = running;
}

function showInlineError(message) {
  let toast = document.querySelector("#toast");
  if (toast) {
    toast.textContent = message;
    toast.classList.add("show");
    clearTimeout(showInlineError.timer);
    showInlineError.timer = setTimeout(() => toast.classList.remove("show"), 3200);
  }
}

async function enhanceReproduction() {
  if (!main || main.dataset.reproductionEnhanced === "true") return;
  if (!main.textContent.includes("Reproduction workflow")) return;
  main.dataset.reproductionEnhanced = "true";
  try {
    const [capabilities, audits, runs] = await Promise.all([
      getJson("/api/v1/capabilities"),
      getJson("/api/v1/audits"),
      getJson("/api/v1/runs"),
    ]);
    repState.capabilities = capabilities;
    repState.audits = audits;
    repState.runs = runs;
    repState.maxAttachmentBytes = Number(capabilities.max_attachment_bytes || 80 * 1024 * 1024);
    const pendingContext = takePendingFindingContext();
    const pendingIsValid = pendingContext && audits.some((audit) => audit.audit_id === pendingContext.auditId);
    if (pendingIsValid) {
      repState.findingContext = pendingContext;
      repState.selectedAuditId = pendingContext.auditId;
      repState.selectedRunId = "";
      repState.selectedRun = null;
      repState.workspace = null;
      repState.selectedFile = null;
      repState.draftPrompt = findingPrompt(pendingContext);
    } else {
      repState.findingContext = null;
      repState.draftPrompt = "";
      repState.selectedAuditId = repState.selectedAuditId && audits.some((audit) => audit.audit_id === repState.selectedAuditId) ? repState.selectedAuditId : audits[0]?.audit_id || "";
    }
    if (repState.selectedAuditId) await loadAttachments();
    if (!pendingIsValid) {
      const first = replicationRuns()[0];
      if (first) await selectRun(first.run_id, false);
    }
    renderShell();
  } catch (error) {
    main.innerHTML = `<div class="page"><div class="empty-state"><div class="empty-state-inner"><div class="empty-mark">!</div><h2>Replication workspace unavailable</h2><p>${escapeHtml(error.message)}</p></div></div></div>`;
  }
}

const observer = new MutationObserver(() => {
  if (!main) return;
  if (!main.textContent.includes("Reproduction workflow")) {
    if (!main.querySelector("[data-reproduction-surface]")) {
      delete main.dataset.reproductionEnhanced;
      repState.findingContext = null;
      repState.draftPrompt = "";
    }
    return;
  }
  queueMicrotask(enhanceReproduction);
});

if (main) {
  observer.observe(main, { childList: true, subtree: true });
  queueMicrotask(enhanceReproduction);
}
