const main = document.querySelector("#main-content");

const ahState = {
  auditId: "",
  audit: null,
  runs: [],
  selectedPage: null,
  selectedSource: null,
  inspectorTab: "source",
  sending: false,
  requestToken: 0,
};

const esc = (value = "") => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

const asNumber = (value) => Number.isFinite(Number(value)) ? Number(value) : 0;
const fmt = (value) => new Intl.NumberFormat().format(asNumber(value));
const time = (value) => {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
};

function auditIdFromLocation() {
  const hash = window.location.hash || "";
  if (!hash.startsWith("#audit=")) return "";
  try { return decodeURIComponent(hash.slice(7)); } catch { return hash.slice(7); }
}

async function requestJson(path) {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

function statusTone(status = "") {
  const value = String(status).toLowerCase();
  if (["verified", "success", "done", "finish", "ready"].some((item) => value.includes(item))) return "good";
  if (["contradiction", "danger", "error", "failed"].some((item) => value.includes(item))) return "bad";
  if (["review", "warning", "needs_review", "cancel"].some((item) => value.includes(item))) return "warn";
  if (["running", "working", "start"].some((item) => value.includes(item))) return "running";
  return "neutral";
}

function badge(status, label = null) {
  const text = label || String(status || "ready").replaceAll("_", " ");
  return `<span class="ah-badge ${statusTone(status)}"><i></i>${esc(text)}</span>`;
}

function latestResult() { return ahState.audit?.latest_result || null; }
function summary() { return ahState.audit?.paper_summary || {}; }
function findings() { return latestResult()?.findings || []; }
function events() { return ahState.audit?.events || []; }
function tables() { return summary().tables || []; }
function attachments() { return ahState.audit?.attachments || []; }
function source() { return latestResult()?.source || {}; }

function currentPage() {
  return ahState.selectedPage || ahState.selectedSource?.page || source().page || 1;
}

function resultCounts() {
  const result = latestResult();
  return result?.counts || { verified: 0, needs_review: 0, contradictions: 0 };
}

function eventIcon(event) {
  if (event.kind === "user_message") return "↗";
  if (event.kind === "finding") return "!";
  if (event.kind === "assistant_message") return "V";
  if (event.kind === "artifact") return "◇";
  if (event.kind === "tool") return event.payload?.phase === "finish" ? "✓" : "⌁";
  return "·";
}

function structuredEvent(event) {
  const payload = event.payload || {};
  const phase = payload.phase || "";
  if (event.kind === "user_message") {
    return `<article class="ah-message user">
      <div class="ah-message-meta"><span>You</span><time>${time(event.created_at)}</time></div>
      <div class="ah-message-copy">${esc(event.detail || event.title || "")}</div>
    </article>`;
  }
  if (event.kind === "assistant_message") {
    return `<article class="ah-message assistant">
      <div class="ah-agent-avatar">V</div><div class="ah-message-body">
        <div class="ah-message-meta"><span>Veritas</span><time>${time(event.created_at)}</time></div>
        <div class="ah-message-copy">${esc(event.detail || event.title || "")}</div>
      </div>
    </article>`;
  }
  if (event.kind === "finding") {
    return `<button class="ah-event finding" data-ah-source-page="${esc(payload.page || source().page || "")}" type="button">
      <span class="ah-event-icon ${statusTone(event.status)}">!</span><span class="ah-event-copy"><strong>${esc(event.title || "Finding")}</strong><small>${esc(event.detail || "Evidence-linked finding")}</small></span>${badge(event.status || "review")}
    </button>`;
  }
  if (event.kind === "tool") {
    const metric = payload.duration_ms != null ? ` · ${Math.round(asNumber(payload.duration_ms))} ms` : "";
    return `<div class="ah-event tool">
      <span class="ah-event-icon ${statusTone(event.status || phase)}">${eventIcon(event)}</span><span class="ah-event-copy"><strong>${esc(event.title || "Audit tool")}</strong><small>${esc(event.detail || phase || "tool event")}${metric}</small></span>${phase ? badge(event.status || phase, phase) : ""}
    </div>`;
  }
  return `<div class="ah-event">
    <span class="ah-event-icon ${statusTone(event.status)}">${eventIcon(event)}</span><span class="ah-event-copy"><strong>${esc(event.title || event.kind || "Event")}</strong><small>${esc(event.detail || event.kind || "")}</small></span><time>${time(event.created_at)}</time>
  </div>`;
}

function renderThread() {
  const items = events();
  if (!items.length) {
    return `<div class="ah-empty-thread"><div class="ah-orb">V</div><h2>Audit this paper with evidence in view</h2><p>The Audit Agent can inspect the parsed paper, locate a regression row, and run deterministic checks. It cannot execute shell commands.</p><div class="ah-suggestions"><button type="button" data-ah-suggest="/inspect">Inspect paper</button><button type="button" data-ah-suggest='/audit row="Treatment" table=2 page=1'>Audit a row</button><button type="button" data-ah-suggest="/help">Show commands</button></div></div>`;
  }
  return items.map(structuredEvent).join("");
}

function renderPaperRail() {
  const audit = ahState.audit;
  const list = tables();
  const runItems = ahState.runs.filter((run) => run.audit_id === audit.audit_id).slice(0, 8);
  return `<aside class="ah-left" aria-label="Audit project rail">
    <section class="ah-rail-section">
      <div class="ah-section-head"><span>Paper</span>${badge(audit.status)}</div>
      <button class="ah-paper-row selected" type="button" data-ah-page="1"><span class="ah-file-icon">▤</span><span><strong>${esc(audit.filename || "paper.pdf")}</strong><small>${fmt(summary().pages)} pages · ${fmt(summary().tables_detected)} tables</small></span></button>
      ${attachments().map((item) => `<a class="ah-paper-row" href="/api/v1/audits/${encodeURIComponent(audit.audit_id)}/attachments/${encodeURIComponent(item.attachment_id)}" download><span class="ah-file-icon">◇</span><span><strong>${esc(item.filename)}</strong><small>immutable attachment</small></span></a>`).join("")}
    </section>
    <section class="ah-rail-section ah-rail-grow">
      <div class="ah-section-head"><span>Detected tables</span><em>${list.length}</em></div>
      <div class="ah-scroll-list">${list.length ? list.slice(0, 24).map((table, index) => `<button class="ah-table-row ${Number(table.page) === Number(currentPage()) ? "active" : ""}" type="button" data-ah-page="${esc(table.page || 1)}" data-ah-table="${esc(table.caption || table.label || `Table ${index + 1}`)}"><span>${index + 1}</span><span><strong>${esc(table.caption || table.label || `Table ${index + 1}`)}</strong><small>page ${esc(table.page || "?")} · ${esc((table.parsers || []).join(" + ") || "parsed")}</small></span></button>`).join("") : `<div class="ah-mini-empty">No tables detected.</div>`}</div>
    </section>
    <section class="ah-rail-section ah-runs-section">
      <div class="ah-section-head"><span>Run history</span><em>${runItems.length}</em></div>
      <div class="ah-run-list">${runItems.length ? runItems.map((run) => `<button type="button" class="ah-run-row" data-ah-run="${esc(run.run_id)}"><span class="ah-run-dot ${statusTone(run.phase || run.status)}"></span><span><strong>${esc(run.tool || run.run_kind || "run")}</strong><small>${time(run.created_at)} · ${esc(run.phase || run.status || "done")}</small></span></button>`).join("") : `<div class="ah-mini-empty">No audit runs yet.</div>`}</div>
    </section>
  </aside>`;
}

function renderRunSummary() {
  const counts = resultCounts();
  return `<div class="ah-run-summary">
    <div><span>Verified</span><strong class="good">${fmt(counts.verified)}</strong></div>
    <div><span>Needs review</span><strong class="warn">${fmt(counts.needs_review)}</strong></div>
    <div><span>Contradictions</span><strong class="bad">${fmt(counts.contradictions)}</strong></div>
  </div>`;
}

function renderCenter() {
  const result = latestResult();
  return `<section class="ah-center" aria-label="Audit Agent conversation">
    <div class="ah-center-head">
      <div class="ah-agent-title"><span class="ah-agent-avatar">V</span><span><strong>Veritas Audit Agent</strong><small>read · parse · inspect · verify</small></span></div>
      <div class="ah-center-status">${result ? badge(result.status, result.status) : badge(ahState.sending ? "running" : "ready", ahState.sending ? "working" : "ready")}</div>
    </div>
    ${renderRunSummary()}
    <div id="ah-thread" class="ah-thread">${renderThread()}</div>
    <div class="ah-composer-wrap">
      <div class="ah-command-row"><button type="button" data-ah-suggest="/inspect">/inspect</button><button type="button" data-ah-suggest='/audit row="" table= page='>/audit</button><button type="button" data-ah-suggest="/help">/help</button><span>deterministic tools · no shell</span></div>
      <div class="ah-composer ${ahState.sending ? "busy" : ""}"><textarea id="ah-message" rows="2" ${ahState.sending ? "disabled" : ""} placeholder="Ask Veritas to inspect, locate evidence, or audit a reported result…"></textarea><button id="ah-send" type="button" ${ahState.sending ? "disabled" : ""} aria-label="Send audit command">${ahState.sending ? "…" : "↑"}</button></div>
    </div>
  </section>`;
}

function sourceSelectionCard() {
  const selected = ahState.selectedSource || source();
  if (!selected || (!selected.table && !selected.row && !selected.text_quote && !selected.page)) return "";
  return `<div class="ah-source-card"><div class="ah-card-head"><span>Selected evidence</span>${badge(latestResult()?.status || "ready")}</div><div class="ah-source-meta">${selected.table ? `<b>${esc(selected.table)}</b>` : ""}${selected.row ? `<span>${esc(selected.row)}</span>` : ""}${selected.page ? `<span>page ${esc(selected.page)}</span>` : ""}</div>${selected.text_quote ? `<pre>${esc(selected.text_quote)}</pre>` : ""}</div>`;
}

function renderFindingsInspector() {
  const list = findings();
  if (!list.length) return `<div class="ah-inspector-empty"><span>✓</span><strong>No contradiction findings</strong><p>The latest completed audit has not produced contradiction findings.</p></div>`;
  return `<div class="ah-finding-stack">${list.map((finding, index) => `<button type="button" class="ah-finding-card" data-ah-finding="${index}" data-ah-source-page="${esc(finding.page || finding.source?.page || source().page || "")}"><span class="ah-finding-severity">!</span><span><strong>${esc(finding.title || "Finding")}</strong><small>${esc(finding.explanation || finding.detail || "Review linked evidence")}</small></span></button>`).join("")}</div>`;
}

function renderStructureInspector() {
  return `<div class="ah-structure-grid">
    <div class="ah-metric"><span>Pages</span><strong>${fmt(summary().pages)}</strong></div><div class="ah-metric"><span>Words</span><strong>${fmt(summary().words)}</strong></div><div class="ah-metric"><span>Tables</span><strong>${fmt(summary().tables_detected)}</strong></div><div class="ah-metric"><span>Events</span><strong>${fmt(events().length)}</strong></div>
    <div class="ah-structure-list">${tables().slice(0, 20).map((table, index) => `<button type="button" data-ah-page="${esc(table.page || 1)}" data-ah-table="${esc(table.caption || table.label || `Table ${index + 1}`)}"><span>${esc(table.caption || table.label || `Table ${index + 1}`)}</span><em>p.${esc(table.page || "?")}</em></button>`).join("")}</div>
  </div>`;
}

function renderProvenanceInspector() {
  const audit = ahState.audit;
  const src = source();
  const parserNames = [...new Set(tables().flatMap((table) => table.parsers || []))];
  return `<div class="ah-provenance">
    <div class="ah-prov-row"><span>Artifact SHA-256</span><code>${esc(audit.artifact_sha256 || summary().artifact_sha256 || "unavailable")}</code></div>
    <div class="ah-prov-row"><span>Parsers observed</span><strong>${esc(parserNames.join(" + ") || "paper parser stack")}</strong></div>
    <div class="ah-prov-row"><span>Evidence binding</span><strong>${src.page ? `page ${esc(src.page)}${src.table ? ` · ${esc(src.table)}` : ""}` : "No detector source selected"}</strong></div>
    <div class="ah-prov-row"><span>Execution boundary</span><strong>Audit Agent · read / parse / inspect / verify</strong></div>
    <div class="ah-boundary-card"><span>Execution is intentionally unavailable here.</span><p>Code, terminal, package installation, filesystem writes, and network access belong to the separate Replication Workspace with explicit permissions.</p><button type="button" data-ah-nav="reproduction">Open Replication Workspace →</button></div>
  </div>`;
}

function renderInspectorBody() {
  if (ahState.inspectorTab === "findings") return renderFindingsInspector();
  if (ahState.inspectorTab === "structure") return renderStructureInspector();
  if (ahState.inspectorTab === "provenance") return renderProvenanceInspector();
  const audit = ahState.audit;
  return `<div class="ah-source-pane"><div class="ah-pdf-bar"><span><b>Source</b> · page ${esc(currentPage())}</span><a href="/api/v1/audits/${encodeURIComponent(audit.audit_id)}/paper#page=${encodeURIComponent(currentPage())}" target="_blank" rel="noreferrer">Open PDF ↗</a></div><iframe id="ah-pdf" class="ah-pdf" title="${esc(audit.title)} source PDF" src="/api/v1/audits/${encodeURIComponent(audit.audit_id)}/paper#page=${encodeURIComponent(currentPage())}"></iframe>${sourceSelectionCard()}</div>`;
}

function renderRight() {
  const tabs = [["source", "Source"], ["findings", `Findings ${findings().length}`], ["structure", "Structure"], ["provenance", "Provenance"]];
  return `<aside class="ah-right" aria-label="Evidence Inspector"><div class="ah-inspector-head"><div><strong>Evidence Inspector</strong><small>paper-grounded source of truth</small></div><span>p. ${esc(currentPage())} / ${fmt(summary().pages)}</span></div><div class="ah-tabs" role="tablist">${tabs.map(([id, label]) => `<button type="button" data-ah-tab="${id}" class="${ahState.inspectorTab === id ? "active" : ""}">${esc(label)}</button>`).join("")}</div><div id="ah-inspector" class="ah-inspector">${renderInspectorBody()}</div></aside>`;
}

function renderHarness() {
  const audit = ahState.audit;
  if (!audit) return;
  const result = latestResult();
  const status = result?.status || audit.status || "ready";
  main.innerHTML = `<div class="audit-harness" data-audit-harness="true" data-audit-id="${esc(audit.audit_id)}">
    <header class="ah-header"><div class="ah-header-main"><div class="ah-paper-mark">V</div><div><div class="ah-title-row"><h1>${esc(audit.title)}</h1>${badge(status)}</div><p>${esc(audit.filename || audit.audit_id)} · ${fmt(summary().pages)} pages · ${fmt(summary().tables_detected)} tables</p></div></div><div class="ah-header-actions"><button type="button" data-ah-nav="audits">All audits</button><button type="button" data-ah-nav="reproduction" class="primary">Replication workspace</button></div></header>
    <div class="ah-workspace-tabs"><button class="active" type="button">Audit</button><button type="button" data-ah-tab="structure">Files <span>${attachments().length + 1}</span></button><button type="button" data-ah-tab="findings">Findings <span>${findings().length}</span></button><button type="button" data-ah-nav="reproduction">Reproduction <span>${ahState.runs.filter((run) => run.run_kind === "replication").length}</span></button><button type="button" data-ah-tab="provenance">Provenance</button></div>
    <div class="ah-grid">${renderPaperRail()}${renderCenter()}${renderRight()}</div>
  </div>`;
  bindHarness();
  requestAnimationFrame(() => { const thread = document.querySelector("#ah-thread"); if (thread) thread.scrollTop = thread.scrollHeight; });
}

function setPage(page, table = "") {
  const parsed = Number(page);
  ahState.selectedPage = Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
  ahState.selectedSource = { ...source(), page: ahState.selectedPage, table: table || source().table || "" };
  ahState.inspectorTab = "source";
  renderHarness();
}

function navigate(view) {
  const target = document.querySelector(`[data-view="${CSS.escape(view)}"]`);
  if (target) target.click();
  else window.location.hash = `#${view}`;
}

function bindHarness() {
  document.querySelectorAll("[data-ah-page]").forEach((node) => node.addEventListener("click", () => setPage(node.dataset.ahPage, node.dataset.ahTable || "")));
  document.querySelectorAll("[data-ah-source-page]").forEach((node) => node.addEventListener("click", () => {
    const page = node.dataset.ahSourcePage;
    if (page) setPage(page);
  }));
  document.querySelectorAll("[data-ah-tab]").forEach((node) => node.addEventListener("click", () => {
    ahState.inspectorTab = node.dataset.ahTab;
    renderHarness();
  }));
  document.querySelectorAll("[data-ah-nav]").forEach((node) => node.addEventListener("click", () => navigate(node.dataset.ahNav)));
  document.querySelectorAll("[data-ah-suggest]").forEach((node) => node.addEventListener("click", () => {
    const input = document.querySelector("#ah-message");
    if (!input || ahState.sending) return;
    input.value = node.dataset.ahSuggest || "";
    input.focus();
    if (input.value.includes('row=""')) input.setSelectionRange(input.value.indexOf('""') + 1, input.value.indexOf('""') + 1);
  }));
  const input = document.querySelector("#ah-message");
  const send = document.querySelector("#ah-send");
  if (send) send.addEventListener("click", sendMessage);
  if (input) input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) { event.preventDefault(); sendMessage(); }
  });
}

async function sendMessage() {
  const input = document.querySelector("#ah-message");
  const message = input?.value.trim() || "";
  if (!message || ahState.sending || !ahState.auditId) return;
  ahState.sending = true;
  ahState.audit.events = [...events(), { kind: "user_message", title: message, detail: message, status: "running", created_at: new Date().toISOString(), payload: { optimistic: true } }];
  renderHarness();
  try {
    const response = await fetch(`/api/v1/audits/${encodeURIComponent(ahState.auditId)}/messages`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message }) });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let first = true;
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line);
        if (first) {
          ahState.audit.events = events().filter((item) => !item.payload?.optimistic);
          first = false;
        }
        ahState.audit.events = [...events(), event];
        if (event.payload?.result) {
          ahState.audit.latest_result = event.payload.result;
          const page = event.payload.result?.source?.page;
          if (page) ahState.selectedPage = page;
        }
        renderHarness();
      }
    }
    await hydrate(ahState.auditId, { preserveTab: true, preservePage: true });
  } catch (error) {
    ahState.audit.events = [...events().filter((item) => !item.payload?.optimistic), { kind: "tool", title: "Audit command failed", detail: error.message, status: "danger", created_at: new Date().toISOString(), payload: { phase: "error" } }];
  } finally {
    ahState.sending = false;
    renderHarness();
  }
}

async function hydrate(auditId, options = {}) {
  const token = ++ahState.requestToken;
  try {
    const [audit, runs] = await Promise.all([requestJson(`/api/v1/audits/${encodeURIComponent(auditId)}`), requestJson("/api/v1/runs")]);
    if (token !== ahState.requestToken || auditIdFromLocation() !== auditId) return;
    ahState.auditId = auditId;
    ahState.audit = audit;
    ahState.runs = Array.isArray(runs) ? runs : [];
    if (!options.preservePage) ahState.selectedPage = audit.latest_result?.source?.page || 1;
    if (!options.preserveTab) ahState.inspectorTab = "source";
    document.body.classList.add("audit-harness-active");
    renderHarness();
  } catch (error) {
    console.error("Unable to load audit harness", error);
  }
}

function activateIfNeeded() {
  const existing = main.querySelector("[data-audit-harness='true']");
  if (existing) return;
  const workbench = main.querySelector(".page.workbench");
  const auditId = auditIdFromLocation();
  if (workbench && auditId) {
    hydrate(auditId, { preserveTab: ahState.auditId === auditId, preservePage: ahState.auditId === auditId });
    return;
  }
  if (!auditId) {
    ahState.auditId = "";
    ahState.audit = null;
    document.body.classList.remove("audit-harness-active");
  }
}

const observer = new MutationObserver(activateIfNeeded);
observer.observe(main, { childList: true });
window.addEventListener("hashchange", () => queueMicrotask(activateIfNeeded));
activateIfNeeded();
