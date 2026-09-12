const state = {
  audits: [],
  activeAudit: null,
  activePanel: "source",
  selectedEvidence: null,
  sending: false,
};

const $ = (selector) => document.querySelector(selector);
const els = {
  list: $("#audit-list"),
  count: $("#audit-count"),
  conversation: $("#conversation"),
  title: $("#paper-title"),
  status: $("#run-status"),
  findingCount: $("#finding-count"),
  inspector: $("#inspector-body"),
  inspectorSubtitle: $("#inspector-subtitle"),
  message: $("#message"),
  send: $("#send"),
  file: $("#file-input"),
  newAudit: $("#new-audit"),
  emptyUpload: $("#empty-upload"),
  attach: $("#attach"),
  refresh: $("#refresh"),
  openPaper: $("#open-paper"),
  toast: $("#toast"),
};

const escapeHtml = (value = "") =>
  String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

function showToast(message) {
  els.toast.textContent = message;
  els.toast.classList.add("show");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => els.toast.classList.remove("show"), 2600);
}

function timeLabel(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function statusClass(value) {
  if (value === "running") return "running";
  if (value === "error") return "error";
  return "ready";
}

function compactStatus(value) {
  if (value === "running") return "Running";
  if (value === "error") return "Error";
  return "Ready";
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch {}
    throw new Error(detail);
  }
  return response;
}

async function loadAudits({ preserveSelection = true } = {}) {
  const response = await api("/api/audits");
  state.audits = await response.json();
  renderAuditList();

  if (preserveSelection && state.activeAudit) {
    const found = state.audits.find((item) => item.audit_id === state.activeAudit.audit_id);
    if (found) {
      await selectAudit(found.audit_id, { silent: true });
      return;
    }
  }
  if (!state.activeAudit && state.audits.length) {
    await selectAudit(state.audits[0].audit_id, { silent: true });
  }
}

function renderAuditList() {
  els.count.textContent = state.audits.length;
  if (!state.audits.length) {
    els.list.innerHTML = `<div class="audit-meta" style="padding:8px">No audits yet</div>`;
    return;
  }
  els.list.innerHTML = state.audits
    .map((audit) => {
      const active = state.activeAudit?.audit_id === audit.audit_id ? "active" : "";
      const summary = audit.paper_summary || {};
      return `
        <div class="audit-item ${active}" data-audit="${escapeHtml(audit.audit_id)}">
          <div class="audit-title">${escapeHtml(audit.title)}</div>
          <div class="audit-meta">
            <span class="status-dot ${statusClass(audit.status)}"></span>
            <span>${compactStatus(audit.status)}</span><span>·</span><span>${summary.pages || "?"} pages</span>
          </div>
        </div>`;
    })
    .join("");

  els.list.querySelectorAll("[data-audit]").forEach((node) => {
    node.addEventListener("click", () => selectAudit(node.dataset.audit));
  });
}

async function selectAudit(auditId, { silent = false } = {}) {
  try {
    const response = await api(`/api/audits/${encodeURIComponent(auditId)}`);
    state.activeAudit = await response.json();
    state.selectedEvidence = state.activeAudit.latest_result?.source || null;
    renderAll();
  } catch (error) {
    if (!silent) showToast(error.message);
  }
}

function renderAll() {
  renderAuditList();
  const audit = state.activeAudit;
  const enabled = Boolean(audit) && !state.sending;
  els.message.disabled = !enabled;
  els.send.disabled = !enabled;
  els.openPaper.disabled = !audit;
  els.title.textContent = audit?.title || "No paper selected";
  els.status.textContent = audit ? compactStatus(audit.status) : "Idle";
  els.status.className = `status-pill ${audit?.status || "idle"}`;
  const result = audit?.latest_result;
  els.findingCount.textContent = result?.findings?.length || 0;
  els.inspectorSubtitle.textContent = audit
    ? `${audit.filename} · ${audit.paper_summary?.pages || "?"} pages`
    : "Select an audit to inspect its source.";
  renderConversation();
  renderInspector();
}

function renderConversation() {
  const audit = state.activeAudit;
  if (!audit) {
    els.conversation.innerHTML = `
      <div class="empty-state">
        <div class="empty-orb">V</div>
        <h1>Audit a paper with evidence in view.</h1>
        <p>Upload a PDF. Veritas will parse it with independent PDF engines, surface detected tables, and keep every check connected to its source.</p>
        <button id="empty-upload-inline" class="primary-button">Upload paper</button>
        <div class="empty-hints"><span>/inspect</span><span>/audit row="Treatment" table=2 page=1</span></div>
      </div>`;
    $("#empty-upload-inline")?.addEventListener("click", () => els.file.click());
    return;
  }
  const events = audit.events || [];
  els.conversation.innerHTML = events.map(renderEvent).join("");
  els.conversation.querySelectorAll("[data-evidence-event]").forEach((node) => {
    node.addEventListener("click", () => {
      const index = Number(node.dataset.evidenceEvent);
      const event = events[index];
      const result = event?.payload?.result;
      const source = result?.source || event?.payload?.source || event?.payload?.finding?.source;
      if (source) {
        state.selectedEvidence = source;
        activateInspector("source");
      }
    });
  });
  els.conversation.scrollTop = els.conversation.scrollHeight;
}

function renderEvent(event, index) {
  if (event.kind === "user_message") {
    return `<div class="event event-user"><div class="event-header"><div class="event-title">${escapeHtml(event.title)}</div><div class="event-time">${timeLabel(event.created_at)}</div></div></div>`;
  }
  const result = event.payload?.result;
  const counts = result?.counts;
  const metrics = counts
    ? `<div class="event-status-row"><span class="metric good">✓ ${counts.verified || 0} verified</span><span class="metric review">● ${counts.needs_review || 0} review</span><span class="metric bad">× ${counts.contradictions || 0} contradictions</span></div>`
    : "";
  const tool = event.kind === "tool"
    ? `<div class="tool-label">⌁ ${escapeHtml(event.payload?.tool || "tool")}</div>`
    : event.kind === "finding" ? `<div class="tool-label">◆ finding</div>` : "";
  const clickable = result?.source || event.payload?.source || event.payload?.finding?.source ? "clickable" : "";
  return `<div class="event agent-row"><div class="agent-avatar">V</div><div class="event-card ${escapeHtml(event.status || "info")} ${clickable}" ${clickable ? `data-evidence-event="${index}"` : ""}>${tool}<div class="event-header"><div class="event-title">${escapeHtml(event.title)}</div><div class="event-time">${timeLabel(event.created_at)}</div></div>${event.detail ? `<div class="event-detail">${escapeHtml(event.detail)}</div>` : ""}${metrics}</div></div>`;
}

function activateInspector(panel) {
  state.activePanel = panel;
  document.querySelectorAll(".inspector-tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.panel === panel));
  renderInspector();
}

function renderInspector() {
  const audit = state.activeAudit;
  if (!audit) {
    els.inspector.innerHTML = `<div class="inspector-empty"><div><div class="grid-icon">▦</div><p>Source evidence will appear here.</p></div></div>`;
    return;
  }
  if (state.activePanel === "findings") return renderFindings(audit);
  if (state.activePanel === "structure") return renderStructure(audit);
  if (state.activePanel === "provenance") return renderProvenance(audit);
  return renderSource(audit);
}

function renderSource(audit) {
  const source = state.selectedEvidence || audit.latest_result?.source || {};
  const page = source.page || 1;
  const paperUrl = `/api/audits/${encodeURIComponent(audit.audit_id)}/paper#page=${page}`;
  const details = source.page || source.table || source.row
    ? `<div class="evidence-summary"><h3>Selected evidence</h3><dl class="key-value-grid"><dt>Page</dt><dd>${escapeHtml(source.page || "—")}</dd><dt>Table</dt><dd>${escapeHtml(source.table || "—")}</dd><dt>Row</dt><dd>${escapeHtml(source.row || "—")}</dd><dt>Artifact</dt><dd>${escapeHtml(source.artifact_id || audit.paper_summary?.artifact_id || "—")}</dd></dl>${source.text_quote ? `<div class="quote">${escapeHtml(source.text_quote)}</div>` : ""}</div>`
    : `<div class="evidence-summary"><h3>Paper source</h3><p style="margin:0;color:var(--muted);font-size:9px;line-height:1.5">Run an audit or select a detected table to jump to evidence.</p></div>`;
  els.inspector.innerHTML = `<div class="pdf-wrap"><iframe class="pdf-frame" title="Paper PDF" src="${paperUrl}"></iframe>${details}</div>`;
}

function renderFindings(audit) {
  const findings = audit.latest_result?.findings || [];
  if (!findings.length) {
    els.inspector.innerHTML = `<div class="inspector-empty"><div><div class="grid-icon">◇</div><p>No contradiction findings in the latest audit.</p></div></div>`;
    return;
  }
  els.inspector.innerHTML = `<div class="panel-stack">${findings.map((finding) => `<div class="info-card finding-card"><h3>${escapeHtml(finding.title || "Finding")}</h3><p>${escapeHtml(finding.explanation || "")}</p></div>`).join("")}</div>`;
}

function renderStructure(audit) {
  const tables = audit.paper_summary?.tables || [];
  if (!tables.length) {
    els.inspector.innerHTML = `<div class="inspector-empty"><p>No tables detected by the current parsers.</p></div>`;
    return;
  }
  els.inspector.innerHTML = `<div class="panel-stack">${tables.map((table, index) => `<div class="info-card table-card" data-table-index="${index}"><div class="table-head"><div class="table-label">${escapeHtml(table.caption || table.label || `Table ${index + 1}`)}</div><div class="table-page">page ${escapeHtml(table.page)}</div></div><p>${escapeHtml((table.parsers || []).join(" · "))}</p>${table.rows_preview?.length ? `<div class="table-preview"><table><tbody>${table.rows_preview.map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell ?? "")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>` : ""}</div>`).join("")}</div>`;
  els.inspector.querySelectorAll("[data-table-index]").forEach((node) => {
    node.addEventListener("click", () => {
      const table = tables[Number(node.dataset.tableIndex)];
      state.selectedEvidence = { artifact_id: audit.paper_summary?.artifact_id, page: table.page, table: table.caption || table.label, row: null, text_quote: (table.rows_preview || []).map((row) => row.join(" | ")).join("\n") };
      activateInspector("source");
    });
  });
}

function renderProvenance(audit) {
  const summary = audit.paper_summary || {};
  const parsers = summary.parser_snapshots || [];
  els.inspector.innerHTML = `<div class="panel-stack"><div class="info-card"><h3>Artifact SHA-256</h3><div class="provenance-hash">${escapeHtml(summary.artifact_sha256 || audit.artifact_sha256)}</div></div><div class="info-card"><h3>Parser snapshots</h3>${parsers.map((parser) => `<div class="parser-row"><div><div class="parser-name">${escapeHtml(parser.parser_id)}</div><div class="parser-meta">${escapeHtml(parser.parser_family)}</div></div><div class="parser-meta">${escapeHtml(parser.parser_version)} · ${escapeHtml(parser.tables)} tables</div></div>`).join("")}</div><div class="info-card"><h3>Latest run</h3><p>${audit.latest_result ? `Scope: ${escapeHtml(audit.latest_result.scope)} · coverage ${Math.round((audit.latest_result.verification_coverage || 0) * 100)}%` : "No detector run yet."}</p></div></div>`;
}

async function uploadFile(file) {
  if (!file) return;
  const data = new FormData();
  data.append("file", file);
  data.append("title", file.name.replace(/\.pdf$/i, ""));
  state.sending = true;
  els.newAudit.disabled = true;
  showToast("Parsing paper with both PDF engines…");
  try {
    const response = await api("/api/audits", { method: "POST", body: data });
    state.activeAudit = await response.json();
    state.selectedEvidence = null;
    await loadAudits({ preserveSelection: true });
    showToast("Paper ready");
  } catch (error) {
    showToast(error.message);
  } finally {
    state.sending = false;
    els.newAudit.disabled = false;
    els.file.value = "";
    renderAll();
  }
}

async function sendMessage() {
  const audit = state.activeAudit;
  const message = els.message.value.trim();
  if (!audit || !message || state.sending) return;
  state.sending = true;
  els.message.value = "";
  resizeComposer();
  renderAll();
  try {
    const response = await api(`/api/audits/${encodeURIComponent(audit.audit_id)}/messages`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message }) });
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line);
        state.activeAudit.events = [...(state.activeAudit.events || []), event];
        if (event.payload?.result) {
          state.activeAudit.latest_result = event.payload.result;
          if (event.payload.result.source) state.selectedEvidence = event.payload.result.source;
        }
        renderAll();
      }
    }
    await selectAudit(audit.audit_id, { silent: true });
  } catch (error) {
    showToast(error.message);
  } finally {
    state.sending = false;
    renderAll();
  }
}

function resizeComposer() {
  els.message.style.height = "auto";
  els.message.style.height = `${Math.min(els.message.scrollHeight, 126)}px`;
}

els.newAudit.addEventListener("click", () => els.file.click());
els.emptyUpload?.addEventListener("click", () => els.file.click());
els.attach.addEventListener("click", () => els.file.click());
els.file.addEventListener("change", () => uploadFile(els.file.files?.[0]));
els.refresh.addEventListener("click", () => loadAudits().catch((error) => showToast(error.message)));
els.send.addEventListener("click", sendMessage);
els.message.addEventListener("input", resizeComposer);
els.message.addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); sendMessage(); } });
els.openPaper.addEventListener("click", () => {
  if (!state.activeAudit) return;
  const page = state.selectedEvidence?.page || 1;
  window.open(`/api/audits/${encodeURIComponent(state.activeAudit.audit_id)}/paper#page=${page}`, "_blank");
});
document.querySelectorAll(".command-chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    if (!state.activeAudit) return;
    els.message.value = chip.dataset.command || "";
    els.message.focus();
    resizeComposer();
  });
});
document.querySelectorAll(".inspector-tab").forEach((tab) => tab.addEventListener("click", () => activateInspector(tab.dataset.panel)));

loadAudits({ preserveSelection: false }).catch((error) => showToast(error.message));
