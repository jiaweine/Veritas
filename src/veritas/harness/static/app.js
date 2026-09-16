const state = {
  view: "overview",
  audits: [],
  overview: null,
  findings: [],
  runs: [],
  activeAudit: null,
  selectedFile: null,
  sending: false,
  agentOpen: false,
  commandIndex: 0,
  commandItems: [],
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const els = {
  main: $("#main-content"),
  auditCount: $("#audit-count"),
  findingCount: $("#finding-count"),
  file: $("#file-input"),
  toast: $("#toast"),
  upload: $("#upload-dialog"),
  uploadForm: $("#upload-form"),
  uploadTitle: $("#upload-title"),
  uploadSubmit: $("#upload-submit"),
  drop: $("#drop-zone"),
  dropTitle: $("#drop-title"),
  dropCopy: $("#drop-copy"),
  command: $("#command-dialog"),
  commandInput: $("#command-input"),
  commandResults: $("#command-results"),
  agentContext: $("#agent-context"),
  agentTimeline: $("#agent-timeline"),
  agentMessage: $("#agent-message"),
  agentSend: $("#agent-send"),
  syncStatus: $("#sync-status"),
};

const escapeHtml = (value = "") => String(value)
  .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;").replaceAll("'", "&#039;");

const pct = (value) => `${Math.round((Number(value) || 0) * 100)}%`;
const num = (value) => new Intl.NumberFormat().format(Number(value) || 0);
const shortDate = (value) => {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleDateString([], { month: "short", day: "numeric" });
};
const shortTime = (value) => {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
};

function showToast(message) {
  els.toast.textContent = message;
  els.toast.classList.add("show");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => els.toast.classList.remove("show"), 2700);
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try { detail = (await response.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return response;
}

async function loadProductData({ keepAudit = true } = {}) {
  setSync("loading", "Refreshing…");
  try {
    const [overview, audits, findings, runs] = await Promise.all([
      api("/api/v1/overview").then((r) => r.json()),
      api("/api/v1/audits").then((r) => r.json()),
      api("/api/v1/findings").then((r) => r.json()),
      api("/api/v1/runs").then((r) => r.json()),
    ]);
    state.overview = overview;
    state.audits = audits;
    state.findings = findings;
    state.runs = runs;
    els.auditCount.textContent = audits.length;
    els.findingCount.textContent = findings.length;
    if (keepAudit && state.activeAudit) {
      const current = audits.find((item) => item.audit_id === state.activeAudit.audit_id);
      if (current) state.activeAudit = await api(`/api/v1/audits/${encodeURIComponent(current.audit_id)}`).then((r) => r.json());
    }
    setSync("ready", "System ready");
  } catch (error) {
    setSync("error", "Offline");
    showToast(error.message);
  }
}

function setSync(status, text) {
  els.syncStatus.className = `sync-status ${status}`;
  $("span", els.syncStatus).textContent = text;
}

function statusBadge(status = "ready", label = null) {
  const normalized = String(status || "ready").replaceAll("_", "-");
  const text = label || String(status || "ready").replaceAll("_", " ");
  return `<span class="badge ${escapeHtml(normalized)}">${escapeHtml(text)}</span>`;
}

function pageHead(eyebrow, title, subtitle, actions = "") {
  return `<div class="page-head"><div class="page-head-copy"><span class="eyebrow">${escapeHtml(eyebrow)}</span><h1 class="page-title">${escapeHtml(title)}</h1><p class="page-subtitle">${escapeHtml(subtitle)}</p></div>${actions ? `<div class="page-actions">${actions}</div>` : ""}</div>`;
}

function setView(view, { push = true } = {}) {
  state.view = view;
  $$('[data-view]').forEach((node) => node.classList.toggle("active", node.dataset.view === view));
  document.body.classList.remove("sidebar-open");
  if (push) history.replaceState(null, "", `#${view}`);
  renderMain();
  els.main.focus({ preventScroll: true });
}

function renderMain() {
  if (state.view === "audits") return renderAudits();
  if (state.view === "findings") return renderFindings();
  if (state.view === "runs") return renderRuns();
  if (state.view === "evidence") return renderEvidence();
  if (state.view === "reproduction") return renderReproduction();
  if (state.view === "benchmarks") return renderBenchmarks();
  if (state.view === "settings") return renderSettings();
  if (state.view === "audit" && state.activeAudit) return renderWorkbench();
  return renderOverview();
}

function sparkline(values = []) {
  if (!values.length) return "";
  const width = 76, height = 32;
  const min = Math.min(...values), max = Math.max(...values);
  const range = Math.max(max - min, .001);
  const points = values.map((value, i) => {
    const x = (i / Math.max(values.length - 1, 1)) * width;
    const y = height - 3 - ((value - min) / range) * (height - 7);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return `<svg class="kpi-mini" viewBox="0 0 ${width} ${height}" aria-hidden="true"><path d="M${points.replaceAll(" ", " L")}" /></svg>`;
}

function coverageChart(series = []) {
  if (!series.length) return `<div class="empty-chart">Run an audit to build a real verification coverage series.</div>`;
  const width = 720, height = 190, px = 24, py = 18;
  const points = series.map((item, i) => {
    const x = px + (i / Math.max(series.length - 1, 1)) * (width - px * 2);
    const y = height - py - Math.max(0, Math.min(1, item.coverage)) * (height - py * 2);
    return { x, y, item };
  });
  const line = points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  const area = `${px},${height - py} ${line} ${width - px},${height - py}`;
  return `<svg class="coverage-chart" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="Verification coverage by recent audit">
    <defs><linearGradient id="coverageFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#5368f5" stop-opacity=".18"/><stop offset="1" stop-color="#5368f5" stop-opacity="0"/></linearGradient></defs>
    ${[.25,.5,.75,1].map((level) => `<line class="chart-grid" x1="${px}" x2="${width-px}" y1="${height-py-level*(height-py*2)}" y2="${height-py-level*(height-py*2)}"/>`).join("")}
    <polygon class="chart-area" points="${area}"/><polyline class="chart-line" points="${line}"/>
    ${points.map((p) => `<circle class="chart-point" cx="${p.x}" cy="${p.y}" r="3"><title>${escapeHtml(p.item.title)} · ${pct(p.item.coverage)}</title></circle>`).join("")}
  </svg>`;
}

function renderOverview() {
  const o = state.overview || {};
  const audits = state.audits.slice(0, 6);
  const activity = o.recent_activity || [];
  const series = o.coverage_series || [];
  const values = series.map((item) => item.coverage);
  els.main.innerHTML = `<div class="page">
    ${pageHead("Research audit cockpit", "Good morning. What needs verification?", "Veritas turns papers into inspectable evidence, deterministic checks, findings, and reproducible audit traces.", `<button class="secondary-button" data-action="refresh">Refresh</button><button class="primary-button" data-action="new-audit">＋ New audit</button>`)}
    <section class="kpi-grid">
      <article class="kpi-card"><div class="kpi-label">Papers in workspace</div><div class="kpi-value">${num(o.audits_total)}</div><div class="kpi-foot"><strong class="good">${num(o.papers_pages)}</strong> pages parsed</div></article>
      <article class="kpi-card"><div class="kpi-label">Verification coverage</div><div class="kpi-value">${pct(o.mean_coverage)}</div><div class="kpi-foot">Across papers with completed checks</div>${sparkline(values)}</article>
      <article class="kpi-card"><div class="kpi-label">Verified checks</div><div class="kpi-value">${num(o.checks_verified)}</div><div class="kpi-foot"><strong class="good">${pct(o.verification_rate)}</strong> of resolved checks</div></article>
      <article class="kpi-card"><div class="kpi-label">Contradictions</div><div class="kpi-value">${num(o.checks_contradictions)}</div><div class="kpi-foot">${num(o.checks_review)} checks still need review</div></article>
    </section>

    <section class="dashboard-grid">
      <article class="panel">
        <div class="panel-head"><h2>Verification coverage</h2><button class="panel-link" data-view="audits">View audits →</button></div>
        <div class="panel-body chart-wrap"><div class="chart-meta"><span><b>${pct(o.mean_coverage)}</b> mean coverage</span><span><b>${num(o.checks_total)}</b> checks</span><span><b>${num(o.audits_running)}</b> running</span></div>${coverageChart(series)}</div>
      </article>
      <article class="panel">
        <div class="panel-head"><h2>Recent activity</h2><button class="panel-link" data-view="runs">All runs →</button></div>
        <div class="panel-body status-stack">${activity.length ? activity.slice(0,6).map((item) => `<div class="status-row"><span class="status-icon ${escapeHtml(item.status || "")}">${item.kind === "finding" ? "◇" : item.kind === "tool" ? "⌁" : "·"}</span><div class="status-copy"><strong>${escapeHtml(item.title || "Activity")}</strong><small>${escapeHtml(item.audit_title || "")}${item.detail ? ` · ${escapeHtml(item.detail)}` : ""}</small></div><time class="status-time">${shortTime(item.created_at)}</time></div>`).join("") : `<div class="empty-state" style="min-height:220px"><div class="empty-state-inner"><div class="empty-mark">⌁</div><h2>No audit activity yet</h2><p>Upload a paper and run an evidence check.</p></div></div>`}</div>
      </article>
    </section>

    <section class="content-row">
      <article class="panel"><div class="panel-head"><h2>Recent audits</h2><button class="panel-link" data-view="audits">View all →</button></div>${audits.length ? auditTable(audits) : emptyPanel("V", "No papers yet", "Upload a PDF to create the first evidence-linked audit.", true)}</article>
      <article class="panel"><div class="panel-head"><h2>Needs attention</h2><button class="panel-link" data-view="findings">All findings →</button></div><div class="panel-body status-stack">${state.findings.length ? state.findings.slice(0,5).map((finding) => `<div class="status-row clickable" data-audit-id="${escapeHtml(finding.audit_id)}"><span class="status-icon bad">!</span><div class="status-copy"><strong>${escapeHtml(finding.title)}</strong><small>${escapeHtml(finding.audit_title)}</small></div><span class="badge danger">review</span></div>`).join("") : `<div class="empty-state" style="min-height:230px;padding:20px"><div class="empty-state-inner"><div class="empty-mark">✓</div><h2>No open contradictions</h2><p>Latest completed detector runs have not produced contradiction findings.</p></div></div>`}</div></article>
    </section>

    <section class="panel"><div class="panel-head"><h2>Quick start</h2><span class="panel-link">Evidence-first actions</span></div><div class="panel-body action-grid">
      <button class="action-card" data-action="new-audit"><span class="action-icon">＋</span><span><strong>Audit a new paper</strong><small>Upload a PDF, parse tables, and keep immutable artifact provenance.</small></span></button>
      <button class="action-card" data-view="findings"><span class="action-icon">◇</span><span><strong>Review contradictions</strong><small>Inspect detector findings alongside the exact page and table source.</small></span></button>
      <button class="action-card" data-view="runs"><span class="action-icon">⌁</span><span><strong>Inspect audit traces</strong><small>See tool calls, coverage, evidence linkage, and run outcomes.</small></span></button>
    </div></section>
  </div>`;
  bindMainActions();
}

function auditTable(audits) {
  return `<div class="table-wrap"><table class="data-table"><thead><tr><th>Paper</th><th>Status</th><th>Evidence</th><th>Structure</th><th>Updated</th></tr></thead><tbody>${audits.map((audit) => {
    const result = audit.latest_result || {};
    const summary = audit.paper_summary || {};
    return `<tr class="clickable" data-audit-id="${escapeHtml(audit.audit_id)}"><td><div class="row-title">${escapeHtml(audit.title)}</div><div class="row-sub mono">${escapeHtml(audit.audit_id)}</div></td><td>${statusBadge(audit.status)}</td><td><div style="display:flex;align-items:center;gap:8px"><div class="progress"><i style="width:${Math.max(0,Math.min(100,(result.verification_coverage || 0)*100))}%"></i></div><span>${pct(result.verification_coverage)}</span></div></td><td>${num(summary.pages)} pages · ${num(summary.tables_detected)} tables</td><td>${shortDate(audit.updated_at)}</td></tr>`;
  }).join("")}</tbody></table></div>`;
}

function emptyPanel(mark, title, copy, action = false) {
  return `<div class="empty-state"><div class="empty-state-inner"><div class="empty-mark">${escapeHtml(mark)}</div><h2>${escapeHtml(title)}</h2><p>${escapeHtml(copy)}</p>${action ? `<button class="primary-button" data-action="new-audit">Upload paper</button>` : ""}</div></div>`;
}

function renderAudits() {
  els.main.innerHTML = `<div class="page">${pageHead("Workspace", "Audits", "Every paper has an immutable artifact, a parser record, evidence-linked detector results, and a replayable event history.", `<button class="primary-button" data-action="new-audit">＋ New audit</button>`)}
    <div class="filter-row"><button class="filter-pill active">All ${state.audits.length}</button><button class="filter-pill">Ready ${state.audits.filter(a=>a.status==='ready').length}</button><button class="filter-pill">Running ${state.audits.filter(a=>a.status==='running').length}</button><button class="filter-pill">Error ${state.audits.filter(a=>a.status==='error').length}</button></div>
    <section class="panel">${state.audits.length ? auditTable(state.audits) : emptyPanel("V", "No audits in this workspace", "Start with a PDF. Veritas will preserve the artifact and build evidence-aware structure around it.", true)}</section>
  </div>`;
  bindMainActions();
}

function renderFindings() {
  els.main.innerHTML = `<div class="page">${pageHead("Evidence review", "Findings", "Contradictions are review objects, not chat messages: each stays attached to its paper and source context.")}
    ${state.findings.length ? `<div class="finding-list">${state.findings.map((finding) => `<article class="finding-card" data-audit-id="${escapeHtml(finding.audit_id)}"><div><h3>${escapeHtml(finding.title)}</h3><p>${escapeHtml(finding.explanation)}</p><div class="finding-meta">${statusBadge(finding.severity, "contradiction")}<span>${escapeHtml(finding.audit_title)}</span><span>${shortDate(finding.updated_at)}</span></div></div><div class="finding-source"><strong>${escapeHtml(finding.source?.table || "Source")}</strong><br>${finding.source?.page ? `page ${escapeHtml(finding.source.page)}` : "open paper"}</div></article>`).join("")}</div>` : `<section class="panel">${emptyPanel("✓", "No contradiction findings", "Run paper audits to populate evidence-linked findings here.")}</section>`}
  </div>`;
  bindMainActions();
}

function renderRuns() {
  els.main.innerHTML = `<div class="page">${pageHead("Harness observability", "Agent runs", "A run is an inspectable trace of deterministic tool execution and its evidence outcome—not an opaque assistant transcript.")}
    <section class="panel">${state.runs.length ? `<div class="table-wrap"><table class="data-table"><thead><tr><th>Run</th><th>Task</th><th>Status</th><th>Evidence</th><th>Coverage</th><th>Checks</th><th>Time</th></tr></thead><tbody>${state.runs.map((run) => `<tr class="clickable" data-audit-id="${escapeHtml(run.audit_id)}"><td><div class="row-title mono">${escapeHtml(run.run_id || "run")}</div><div class="row-sub">${escapeHtml(run.audit_title)}</div></td><td><div class="row-title">${escapeHtml(run.task || run.tool)}</div><div class="row-sub mono">${escapeHtml(run.tool)}</div></td><td>${statusBadge(run.status)}</td><td>${run.evidence ? statusBadge("success", "linked") : statusBadge("review", "pending")}</td><td>${pct(run.coverage)}</td><td>${num((run.counts?.verified||0)+(run.counts?.needs_review||0)+(run.counts?.contradictions||0))}</td><td>${shortTime(run.created_at)}</td></tr>`).join("")}</tbody></table></div>` : emptyPanel("⌁", "No detector runs yet", "Open a paper and execute /audit to create an inspectable run trace.")}</section>
  </div>`;
  bindMainActions();
}

function renderEvidence() {
  const evidenceAudits = state.audits.filter((audit) => audit.latest_result?.source);
  els.main.innerHTML = `<div class="page">${pageHead("Provenance", "Evidence", "The product treats evidence as a first-class object: artifact → page → table → row → detector result.")}
    <section class="panel">${evidenceAudits.length ? `<div class="table-wrap"><table class="data-table"><thead><tr><th>Paper</th><th>Page</th><th>Table</th><th>Row</th><th>Coverage</th></tr></thead><tbody>${evidenceAudits.map((audit) => { const source=audit.latest_result.source||{}; return `<tr class="clickable" data-audit-id="${escapeHtml(audit.audit_id)}"><td><div class="row-title">${escapeHtml(audit.title)}</div></td><td>${escapeHtml(source.page || "—")}</td><td>${escapeHtml(source.table || "—")}</td><td>${escapeHtml(source.row || "—")}</td><td>${pct(audit.latest_result.verification_coverage)}</td></tr>`; }).join("")}</tbody></table></div>` : emptyPanel("▦", "No linked evidence yet", "Run an audit to create source-linked verification evidence.")}</section>
  </div>`;
  bindMainActions();
}

function renderReproduction() {
  els.main.innerHTML = `<div class="page">${pageHead("Reproducibility", "Reproduction", "Veritas already contains reproduction and replication primitives. This product surface keeps them separate from evidence checking so execution can be sandboxed and reviewed.")}
    <section class="content-row"><article class="panel"><div class="panel-head"><h2>Reproduction workflow</h2></div><div class="panel-body"><div class="status-stack">${[
      ["1", "Artifact intake", "Lock source PDF, code, data, and environment refs."],
      ["2", "Environment resolution", "Resolve dependency/runtime declarations before execution."],
      ["3", "Sandboxed execution", "Run reproduction jobs outside the product web process."],
      ["4", "Evidence comparison", "Compare reproduced outputs with reported claims and attach provenance."],
    ].map((x)=>`<div class="status-row"><span class="status-icon">${x[0]}</span><div class="status-copy"><strong>${x[1]}</strong><small>${x[2]}</small></div></div>`).join("")}</div></div></article><article class="panel"><div class="panel-head"><h2>Execution boundary</h2></div><div class="panel-body"><p class="page-subtitle" style="margin:0">The web harness does not execute arbitrary paper code. Reproduction should use the repository's replication bridge or an isolated runtime, preserving the security and repeatability boundary.</p><button class="secondary-button" style="margin-top:14px" data-view="runs">Inspect current traces</button></div></article></section>
  </div>`;
  bindMainActions();
}

function renderBenchmarks() {
  els.main.innerHTML = `<div class="page">${pageHead("Evaluation", "Benchmarks", "Evaluation is part of the harness identity. Keep benchmark cases independent from live workspace history and compare detector versions on locked cases.")}
    <section class="content-row"><article class="panel"><div class="panel-head"><h2>AuditBench</h2><span class="badge success">repository native</span></div><div class="panel-body"><h3 style="margin:0 0 8px;font-size:15px">Locked evidence-aware evaluation</h3><p class="page-subtitle" style="margin:0">Use existing AuditBench and locked evaluation tooling as the release gate for detector changes. The UI deliberately does not invent benchmark scores when they have not been run.</p></div></article><article class="panel"><div class="panel-head"><h2>Release rule</h2></div><div class="panel-body"><div class="status-stack"><div class="status-row"><span class="status-icon good">✓</span><div class="status-copy"><strong>Evidence linkage</strong><small>Every pass/fail verdict remains inspectable.</small></div></div><div class="status-row"><span class="status-icon">↻</span><div class="status-copy"><strong>Replayability</strong><small>Detector and parser behavior stays versionable.</small></div></div></div></div></article></section>
  </div>`;
}

function renderSettings() {
  els.main.innerHTML = `<div class="page">${pageHead("System", "Settings", "Local harness configuration for web, PWA, and mobile clients.")}
    <section class="content-row"><article class="panel"><div class="panel-head"><h2>API surface</h2></div><div class="panel-body"><div class="stat-list"><div class="stat-item"><span>API version</span><strong>v1</strong></div><div class="stat-item"><span>Streaming</span><strong>NDJSON</strong></div><div class="stat-item"><span>Upload limit</span><strong>80 MiB</strong></div><div class="stat-item"><span>Storage</span><strong>Local-first</strong></div></div></div></article><article class="panel"><div class="panel-head"><h2>Mobile access</h2></div><div class="panel-body"><p class="page-subtitle" style="margin:0">The Expo app uses the same versioned API. For physical devices set <span class="mono">EXPO_PUBLIC_VERITAS_API_URL</span> to a reachable LAN or HTTPS address. CORS is opt-in with <span class="mono">VERITAS_CORS_ORIGINS</span>.</p></div></article></section>
  </div>`;
}

async function openAudit(auditId) {
  try {
    state.activeAudit = await api(`/api/v1/audits/${encodeURIComponent(auditId)}`).then((r) => r.json());
    state.view = "audit";
    history.replaceState(null, "", `#audit=${encodeURIComponent(auditId)}`);
    $$('[data-view]').forEach((node) => node.classList.remove("active"));
    renderMain();
    renderAgent();
  } catch (error) { showToast(error.message); }
}

function renderWorkbench() {
  const audit = state.activeAudit;
  const summary = audit.paper_summary || {};
  const result = audit.latest_result || null;
  const source = result?.source || {};
  const tables = summary.tables || [];
  const events = audit.events || [];
  const findings = result?.findings || [];
  els.main.innerHTML = `<div class="page workbench">
    <div class="workbench-head"><div><div class="breadcrumb"><button data-view="audits">Audits</button><span>/</span><span>${escapeHtml(audit.audit_id)}</span></div><div class="workbench-title">${escapeHtml(audit.title)}</div></div><div class="page-actions"><button class="secondary-button" data-action="open-pdf">Open PDF ↗</button><button class="primary-button" data-action="agent-open">Open Agent</button></div></div>
    <div class="workbench-grid">
      <div class="workbench-column">
        <article class="panel summary-card"><h3>Paper structure</h3><div class="stat-list"><div class="stat-item"><span>Pages</span><strong>${num(summary.pages)}</strong></div><div class="stat-item"><span>Words</span><strong>${num(summary.words)}</strong></div><div class="stat-item"><span>Tables</span><strong>${num(summary.tables_detected)}</strong></div><div class="stat-item"><span>Status</span><strong>${String(audit.status||"ready")}</strong></div></div></article>
        <article class="panel summary-card"><h3>Detected tables</h3>${tables.length ? tables.slice(0,10).map((table, index) => `<div class="table-card" data-table-page="${escapeHtml(table.page || 1)}"><strong>${escapeHtml(table.caption || table.label || `Table ${index + 1}`)}</strong><small>page ${escapeHtml(table.page || "?")} · ${escapeHtml((table.parsers || []).join(" + ") || "parsed")}</small></div>`).join("") : `<p class="page-subtitle" style="margin:0">No tables detected in the parser summary.</p>`}</article>
        <article class="panel summary-card"><h3>Artifact provenance</h3><div class="hash">${escapeHtml(audit.artifact_sha256 || summary.artifact_sha256 || "No hash")}</div></article>
      </div>

      <div class="workbench-column">
        <article class="panel pdf-panel"><div class="pdf-toolbar"><div><strong>Evidence viewer</strong> <span>${source.page ? `· source page ${escapeHtml(source.page)}` : "· full paper"}</span></div><span>${escapeHtml(audit.filename)}</span></div><iframe class="pdf-frame" title="${escapeHtml(audit.title)} PDF" src="/api/v1/audits/${encodeURIComponent(audit.audit_id)}/paper${source.page ? `#page=${encodeURIComponent(source.page)}` : ""}"></iframe></article>
        ${result ? `<article class="panel result-card"><div class="result-head"><div><h3>${escapeHtml(result.status === "verified" ? "Latest audit verified" : result.status === "contradiction" ? "Latest audit found a contradiction" : "Latest audit needs review")}</h3><p>${escapeHtml(source.table || "Located source")}${source.page ? ` · page ${escapeHtml(source.page)}` : ""}${source.row ? ` · ${escapeHtml(source.row)}` : ""}</p></div>${statusBadge(result.status, result.status)}</div><div class="result-metrics"><div class="result-metric"><span>Verified</span><strong>${num(result.counts?.verified)}</strong></div><div class="result-metric"><span>Review</span><strong>${num(result.counts?.needs_review)}</strong></div><div class="result-metric"><span>Contradictions</span><strong>${num(result.counts?.contradictions)}</strong></div></div>${source.text_quote ? `<pre class="evidence-quote">${escapeHtml(source.text_quote)}</pre>` : ""}</article>` : `<article class="panel">${emptyPanel("⌁", "No detector result yet", "Open the Agent and run /audit row=\"…\" table=2 page=1 to create evidence-linked results.")}</article>`}
      </div>

      <div class="workbench-column">
        <article class="panel summary-card"><h3>Findings</h3>${findings.length ? findings.map((finding) => `<div class="status-row"><span class="status-icon bad">!</span><div class="status-copy"><strong>${escapeHtml(finding.title || "Finding")}</strong><small>${escapeHtml(finding.explanation || "")}</small></div></div>`).join("") : `<div class="status-row"><span class="status-icon good">✓</span><div class="status-copy"><strong>No contradiction findings</strong><small>Based on the latest completed audit.</small></div></div>`}</article>
        <article class="panel summary-card"><h3>Audit trace</h3>${events.length ? events.slice(-7).reverse().map((event)=>`<div class="status-row"><span class="status-icon ${escapeHtml(event.status || "")}">${event.kind === "tool" ? "⌁" : event.kind === "finding" ? "!" : "·"}</span><div class="status-copy"><strong>${escapeHtml(event.title)}</strong><small>${escapeHtml(event.kind)} · ${shortTime(event.created_at)}</small></div></div>`).join("") : `<p class="page-subtitle" style="margin:0">No events yet.</p>`}</article>
      </div>
    </div>
  </div>`;
  bindMainActions();
}

function bindMainActions() {
  $$('[data-action="new-audit"]', els.main).forEach((node) => node.addEventListener("click", openUpload));
  $$('[data-action="refresh"]', els.main).forEach((node) => node.addEventListener("click", async () => { await loadProductData(); renderMain(); renderAgent(); }));
  $$('[data-action="agent-open"]', els.main).forEach((node) => node.addEventListener("click", () => setAgent(true)));
  $$('[data-action="open-pdf"]', els.main).forEach((node) => node.addEventListener("click", () => state.activeAudit && window.open(`/api/v1/audits/${encodeURIComponent(state.activeAudit.audit_id)}/paper`, "_blank", "noopener")));
  $$('[data-view]', els.main).forEach((node) => node.addEventListener("click", () => setView(node.dataset.view)));
  $$('[data-audit-id]', els.main).forEach((node) => node.addEventListener("click", () => openAudit(node.dataset.auditId)));
  $$('[data-table-page]', els.main).forEach((node) => node.addEventListener("click", () => {
    const frame = $(".pdf-frame", els.main); if (frame && state.activeAudit) frame.src = `/api/v1/audits/${encodeURIComponent(state.activeAudit.audit_id)}/paper#page=${encodeURIComponent(node.dataset.tablePage)}`;
  }));
}

function openUpload() {
  state.selectedFile = null;
  els.uploadTitle.value = "";
  els.dropTitle.textContent = "Choose a PDF";
  els.dropCopy.textContent = "PDF · up to 80 MiB";
  els.drop.classList.remove("selected");
  els.uploadSubmit.disabled = true;
  els.upload.showModal();
}

function chooseFile() { els.file.click(); }
function setSelectedFile(file) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".pdf")) { showToast("Please choose a PDF file."); return; }
  state.selectedFile = file;
  els.dropTitle.textContent = file.name;
  els.dropCopy.textContent = `${(file.size / 1024 / 1024).toFixed(1)} MiB · ready to parse`;
  els.drop.classList.add("selected");
  if (!els.uploadTitle.value) els.uploadTitle.value = file.name.replace(/\.pdf$/i, "");
  els.uploadSubmit.disabled = false;
}

async function submitUpload(event) {
  event.preventDefault();
  if (!state.selectedFile || state.sending) return;
  state.sending = true;
  els.uploadSubmit.disabled = true;
  els.uploadSubmit.textContent = "Parsing…";
  const data = new FormData();
  data.append("file", state.selectedFile);
  data.append("title", els.uploadTitle.value.trim());
  try {
    const audit = await api("/api/v1/audits", { method: "POST", body: data }).then((r) => r.json());
    els.upload.close();
    await loadProductData({ keepAudit: false });
    state.activeAudit = audit;
    showToast("Paper parsed and evidence workspace created.");
    await openAudit(audit.audit_id);
  } catch (error) { showToast(error.message); }
  finally { state.sending = false; els.uploadSubmit.textContent = "Parse & create audit"; els.uploadSubmit.disabled = !state.selectedFile; els.file.value = ""; }
}

function setAgent(open) {
  state.agentOpen = open;
  document.body.classList.toggle("agent-open", open);
  renderAgent();
  if (open && state.activeAudit) setTimeout(() => els.agentMessage.focus(), 100);
}

function renderAgent() {
  const audit = state.activeAudit;
  els.agentMessage.disabled = !audit || state.sending;
  els.agentSend.disabled = !audit || state.sending;
  if (!audit) {
    els.agentContext.innerHTML = `<div class="context-label">Current context</div><div class="context-title">No paper selected</div><div class="context-meta">Open an audit to give the harness evidence context.</div>`;
    els.agentTimeline.innerHTML = `<div class="agent-empty"><div><div class="empty-mark">⌁</div><strong>Agent is a collaboration layer</strong><p>It operates on the selected paper and emits structured tool events, findings, and evidence—not hidden state.</p></div></div>`;
    return;
  }
  const summary = audit.paper_summary || {};
  els.agentContext.innerHTML = `<div class="context-label">Current paper</div><div class="context-title">${escapeHtml(audit.title)}</div><div class="context-meta">${num(summary.pages)} pages · ${num(summary.tables_detected)} tables · ${escapeHtml(audit.status)}</div>`;
  const events = audit.events || [];
  els.agentTimeline.innerHTML = events.length ? events.slice(-18).map((event) => `<div class="trace"><span class="trace-dot ${escapeHtml(event.status || "")}">${event.kind === "tool" ? "⌁" : event.kind === "finding" ? "!" : event.kind === "user_message" ? "→" : "·"}</span><div class="trace-card"><strong>${escapeHtml(event.title)}</strong>${event.detail ? `<p>${escapeHtml(event.detail)}</p>` : ""}<div class="trace-meta">${escapeHtml(event.kind)} · ${shortTime(event.created_at)}</div></div></div>`).join("") : `<div class="agent-empty">Run <span class="mono">/inspect</span> to start the trace.</div>`;
  els.agentTimeline.scrollTop = els.agentTimeline.scrollHeight;
}

async function sendAgentMessage() {
  const audit = state.activeAudit;
  const message = els.agentMessage.value.trim();
  if (!audit || !message || state.sending) return;
  state.sending = true;
  els.agentMessage.value = "";
  els.agentMessage.disabled = true;
  els.agentSend.disabled = true;
  try {
    const response = await api(`/api/v1/audits/${encodeURIComponent(audit.audit_id)}/messages`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message }),
    });
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n"); buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line);
        state.activeAudit.events = [...(state.activeAudit.events || []), event];
        if (event.payload?.result) state.activeAudit.latest_result = event.payload.result;
        renderAgent();
        if (state.view === "audit") renderWorkbench();
      }
    }
    await loadProductData();
    if (state.activeAudit) state.activeAudit = await api(`/api/v1/audits/${encodeURIComponent(audit.audit_id)}`).then((r) => r.json());
    renderAgent(); renderMain();
  } catch (error) { showToast(error.message); }
  finally { state.sending = false; els.agentMessage.disabled = !state.activeAudit; els.agentSend.disabled = !state.activeAudit; }
}

function commandDefaults() {
  return [
    { kind: "view", id: "overview", title: "Overview", detail: "Research audit cockpit", icon: "⌂" },
    { kind: "view", id: "audits", title: "Audits", detail: "Papers and evidence workspaces", icon: "▤" },
    { kind: "view", id: "findings", title: "Findings", detail: "Contradictions requiring review", icon: "◇" },
    { kind: "view", id: "runs", title: "Agent runs", detail: "Tool traces and evidence outcomes", icon: "⌁" },
    ...state.audits.slice(0, 5).map((audit) => ({ kind: "audit", id: audit.audit_id, title: audit.title, detail: audit.filename, icon: "V" })),
  ];
}

function openCommand() {
  state.commandIndex = 0;
  state.commandItems = commandDefaults();
  renderCommandResults();
  els.commandInput.value = "";
  els.command.showModal();
  setTimeout(() => els.commandInput.focus(), 40);
}

async function searchCommand(value) {
  const query = value.trim();
  state.commandIndex = 0;
  if (!query) { state.commandItems = commandDefaults(); renderCommandResults(); return; }
  const local = commandDefaults().filter((item) => `${item.title} ${item.detail}`.toLowerCase().includes(query.toLowerCase()));
  try {
    const remote = await api(`/api/v1/search?q=${encodeURIComponent(query)}&limit=12`).then((r) => r.json());
    state.commandItems = [...local.filter((x)=>x.kind==='view'), ...remote.map((item) => ({ kind: item.kind, id: item.id, audit_id: item.audit_id, title: item.title, detail: item.detail, icon: item.kind === "audit" ? "V" : "·" }))];
  } catch { state.commandItems = local; }
  renderCommandResults();
}

function renderCommandResults() {
  const items = state.commandItems;
  els.commandResults.innerHTML = `<div class="command-section-label">Navigate & search</div>${items.length ? items.map((item, index) => `<button class="command-result ${index === state.commandIndex ? "selected" : ""}" data-command-index="${index}"><span class="command-result-icon">${escapeHtml(item.icon || "·")}</span><span><strong>${escapeHtml(item.title || "Result")}</strong><small>${escapeHtml(item.detail || item.kind || "")}</small></span></button>`).join("") : `<div class="empty-state" style="min-height:150px"><div class="empty-state-inner"><p>No matching papers, findings, or runs.</p></div></div>`}`;
  $$('[data-command-index]', els.commandResults).forEach((node) => node.addEventListener("click", () => activateCommand(Number(node.dataset.commandIndex))));
}

function activateCommand(index = state.commandIndex) {
  const item = state.commandItems[index]; if (!item) return;
  els.command.close();
  if (item.kind === "view") return setView(item.id);
  const auditId = item.audit_id || (item.kind === "audit" ? item.id : null);
  if (auditId) openAudit(auditId);
}

function bindGlobal() {
  $$('[data-view]').forEach((node) => node.addEventListener("click", () => setView(node.dataset.view)));
  $("#new-audit").addEventListener("click", openUpload);
  $("#mobile-new").addEventListener("click", openUpload);
  $("#drop-zone").addEventListener("click", chooseFile);
  els.file.addEventListener("change", () => setSelectedFile(els.file.files?.[0]));
  $("#upload-close").addEventListener("click", () => els.upload.close());
  $("#upload-cancel").addEventListener("click", () => els.upload.close());
  els.uploadForm.addEventListener("submit", submitUpload);
  $("#command-trigger").addEventListener("click", openCommand);
  els.commandInput.addEventListener("input", (event) => searchCommand(event.target.value));
  els.commandInput.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") { event.preventDefault(); state.commandIndex = Math.min(state.commandItems.length - 1, state.commandIndex + 1); renderCommandResults(); }
    if (event.key === "ArrowUp") { event.preventDefault(); state.commandIndex = Math.max(0, state.commandIndex - 1); renderCommandResults(); }
    if (event.key === "Enter") { event.preventDefault(); activateCommand(); }
  });
  $("#agent-toggle").addEventListener("click", () => setAgent(!state.agentOpen));
  $("#mobile-agent").addEventListener("click", () => setAgent(true));
  $("#agent-close").addEventListener("click", () => setAgent(false));
  els.agentSend.addEventListener("click", sendAgentMessage);
  els.agentMessage.addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); sendAgentMessage(); } });
  $$('[data-agent-command]').forEach((node) => node.addEventListener("click", () => { els.agentMessage.value = node.dataset.agentCommand; els.agentMessage.focus(); }));
  $("#sidebar-open").addEventListener("click", () => document.body.classList.add("sidebar-open"));
  $("#sidebar-close").addEventListener("click", () => document.body.classList.remove("sidebar-open"));
  $("#sidebar-backdrop").addEventListener("click", () => document.body.classList.remove("sidebar-open"));
  document.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); els.command.open ? els.command.close() : openCommand(); }
  });
}

async function boot() {
  bindGlobal();
  await loadProductData({ keepAudit: false });
  const hash = location.hash.slice(1);
  if (hash.startsWith("audit=")) {
    await openAudit(decodeURIComponent(hash.split("=").slice(1).join("=")));
  } else if (["overview","audits","findings","runs","evidence","reproduction","benchmarks","settings"].includes(hash)) {
    setView(hash, { push: false });
  } else renderMain();
  renderAgent();
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
}

boot();
