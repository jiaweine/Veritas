const main = document.querySelector("#main-content");
const sidebar = document.querySelector("#sidebar");
const commandTrigger = document.querySelector("#command-trigger");

const refState = {
  auditId: "",
  audits: [],
  runs: [],
  sidebarRequest: 0,
  analysisRequest: 0,
  enhancementQueued: false,
};

const esc = (value = "") => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

function activeAuditRoot() {
  return main?.querySelector("[data-audit-harness='true']") || null;
}

function statusTone(status = "") {
  const value = String(status).toLowerCase();
  if (["verified", "success", "done", "finish", "ready"].some((item) => value.includes(item))) return "good";
  if (["contradiction", "danger", "error", "failed"].some((item) => value.includes(item))) return "bad";
  if (["review", "warning", "needs_review", "cancel"].some((item) => value.includes(item))) return "warn";
  if (["running", "working", "start"].some((item) => value.includes(item))) return "running";
  return "neutral";
}

function humanStatus(status = "ready") {
  return String(status || "ready")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

async function json(path) {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

function routeToView(view) {
  const target = document.querySelector(`[data-view="${CSS.escape(view)}"]`);
  if (target) target.click();
}

function routeToAudit(auditId) {
  if (!auditId) return;
  const current = activeAuditRoot()?.dataset.auditId || "";
  if (current === auditId) return;
  window.location.assign(`/#audit=${encodeURIComponent(auditId)}`);
}

function renderReferenceSidebar() {
  if (!sidebar) return;
  let shell = sidebar.querySelector("[data-reference-sidebar]");
  if (!shell) {
    shell = document.createElement("div");
    shell.dataset.referenceSidebar = "true";
    shell.className = "ref-sidebar-shell";
    sidebar.querySelector(".brand-row")?.after(shell);
  }

  const auditCount = refState.audits.length;
  const runCount = refState.runs.length;
  const recent = refState.audits.slice(0, 7);
  shell.innerHTML = `
    <button class="ref-sidebar-search" type="button" data-ref-command>
      <span>⌕</span><span>Search…</span><kbd>⌘ K</kbd>
    </button>
    <section class="ref-sidebar-group">
      <div class="ref-sidebar-heading"><span>Workspace</span><button type="button" data-ref-new>＋ New</button></div>
      <button class="ref-sidebar-link" type="button" data-ref-view="audits"><span>▤</span><strong>All audits</strong><em>${auditCount}</em></button>
      <button class="ref-sidebar-link" type="button" data-ref-view="runs"><span>⌁</span><strong>Runs</strong><em>${runCount}</em></button>
      <button class="ref-sidebar-link" type="button" data-ref-view="reproduction"><span>↻</span><strong>Replication</strong></button>
      <button class="ref-sidebar-link" type="button" data-ref-view="benchmarks"><span>⌗</span><strong>Benchmark</strong></button>
    </section>
    <section class="ref-sidebar-group ref-sidebar-recents">
      <div class="ref-sidebar-heading"><span>Recent Audits</span></div>
      <div class="ref-recent-list">
        ${recent.length ? recent.map((audit) => {
          const active = audit.audit_id === refState.auditId ? " active" : "";
          return `<button class="ref-recent-audit${active}" type="button" data-ref-audit="${esc(audit.audit_id)}">
            <span class="ref-recent-copy"><strong>${esc(audit.title || audit.filename || "Untitled audit")}</strong><small>${esc(audit.filename || audit.audit_id)}</small></span>
            <span class="ref-status ${statusTone(audit.status)}"><i></i>${esc(humanStatus(audit.status))}</span>
          </button>`;
        }).join("") : `<div class="ref-sidebar-empty">No audits yet.</div>`}
      </div>
      <button class="ref-sidebar-more" type="button" data-ref-view="runs">View all runs <span>→</span></button>
    </section>
    <div class="ref-sidebar-spacer"></div>
    <div class="ref-sidebar-promise"><strong>Empirical claims,<br>auditable evidence.</strong><small>Turn papers into verifiable facts.</small></div>
  `;

  shell.querySelector("[data-ref-command]")?.addEventListener("click", () => commandTrigger?.click());
  shell.querySelector("[data-ref-new]")?.addEventListener("click", () => document.querySelector("#new-audit")?.click());
  shell.querySelectorAll("[data-ref-view]").forEach((node) => node.addEventListener("click", () => routeToView(node.dataset.refView)));
  shell.querySelectorAll("[data-ref-audit]").forEach((node) => node.addEventListener("click", () => routeToAudit(node.dataset.refAudit)));
}

async function hydrateSidebar(auditId) {
  const token = ++refState.sidebarRequest;
  try {
    const [audits, runs] = await Promise.all([json("/api/v1/audits"), json("/api/v1/runs")]);
    if (token !== refState.sidebarRequest) return;
    refState.auditId = auditId;
    refState.audits = Array.isArray(audits) ? audits : [];
    refState.runs = Array.isArray(runs) ? runs : [];
    renderReferenceSidebar();
  } catch (error) {
    console.error("Unable to hydrate reference sidebar", error);
  }
}

function valueLabel(value) {
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

function checkStatus(check = {}) {
  const raw = typeof check.status === "object" ? check.status?.value : check.status;
  return String(raw || "info");
}

function checkTitle(check = {}, index = 0) {
  return check.title || check.name || check.kind || check.check || check.rule || `Verification check ${index + 1}`;
}

function checkDetail(check = {}) {
  return check.explanation || check.detail || check.message || check.reason || "Deterministic consistency check recorded by the audit engine.";
}

function selectedAnalysisMarkup(audit) {
  const result = audit?.latest_result || null;
  if (!result) return "";
  const consensus = result.consensus || {};
  const source = result.source || {};
  const hasEstimate = [consensus.beta, consensus.se, consensus.t_stat, consensus.p_value].some((value) => value !== null && value !== undefined && value !== "");
  if (!hasEstimate && !result.review_reasons?.length) return "";
  const coverage = Math.round((Number(result.verification_coverage) || 0) * 100);
  const checks = Array.isArray(result.checks) ? result.checks : [];
  const sourceBits = [source.table, result.row_label || source.row, source.page ? `p. ${source.page}` : ""].filter(Boolean);
  const status = String(result.status || "review_required");
  return `<section class="ref-selected-analysis" data-reference-analysis="true">
    <div class="ref-analysis-head">
      <div><strong>Selected Cell Analysis</strong><small>${esc(sourceBits.join(" · ") || "Evidence-linked regression row")}</small></div>
      <span class="ref-analysis-status ${statusTone(status)}"><i></i>${esc(humanStatus(status))}</span>
    </div>
    <div class="ref-analysis-metrics">
      <div><span>Parameter</span><strong>${esc(result.row_label || source.row || "Selected row")}</strong></div>
      <div><span>Estimate</span><strong>${esc(valueLabel(consensus.beta))}</strong></div>
      <div><span>Std. Error</span><strong>${esc(valueLabel(consensus.se))}</strong></div>
      <div><span>Test stat</span><strong>${esc(valueLabel(consensus.t_stat))}</strong></div>
      <div><span>p-value</span><strong>${esc(valueLabel(consensus.p_value))}</strong></div>
      <div><span>Coverage</span><strong>${coverage}%</strong></div>
    </div>
    ${checks.length ? `<div class="ref-analysis-checks">${checks.slice(0, 5).map((check, index) => {
      const tone = statusTone(checkStatus(check));
      return `<div class="ref-analysis-check"><span class="${tone}">${tone === "bad" ? "!" : tone === "warn" ? "•" : "✓"}</span><div><strong>${esc(checkTitle(check, index))}</strong><small>${esc(checkDetail(check))}</small></div></div>`;
    }).join("")}</div>` : result.review_reasons?.length ? `<div class="ref-analysis-checks">${result.review_reasons.slice(0, 4).map((reason) => `<div class="ref-analysis-check"><span class="warn">•</span><div><strong>Review required</strong><small>${esc(reason)}</small></div></div>`).join("")}</div>` : ""}
  </section>`;
}

async function ensureSelectedAnalysis(root) {
  const sourcePane = root.querySelector(".ah-source-pane");
  if (!sourcePane || sourcePane.querySelector("[data-reference-analysis]")) return;
  const auditId = root.dataset.auditId || "";
  if (!auditId) return;
  const token = ++refState.analysisRequest;
  try {
    const audit = await json(`/api/v1/audits/${encodeURIComponent(auditId)}`);
    if (token !== refState.analysisRequest) return;
    const freshRoot = activeAuditRoot();
    const freshPane = freshRoot?.querySelector(".ah-source-pane");
    if (!freshRoot || freshRoot.dataset.auditId !== auditId || !freshPane || freshPane.querySelector("[data-reference-analysis]")) return;
    const markup = selectedAnalysisMarkup(audit);
    if (!markup) return;
    freshPane.insertAdjacentHTML("beforeend", markup);
  } catch (error) {
    console.error("Unable to hydrate selected-cell analysis", error);
  }
}

function enhanceAudit(root) {
  const auditId = root.dataset.auditId || "";
  document.body.classList.add("reference-audit-active");
  document.body.classList.remove("reference-runs-active");
  if (refState.auditId !== auditId || !refState.audits.length) hydrateSidebar(auditId);
  else renderReferenceSidebar();

  const header = root.querySelector(".ah-header-actions");
  if (header && !header.querySelector("[data-reference-boundary]")) {
    const boundary = document.createElement("span");
    boundary.dataset.referenceBoundary = "true";
    boundary.className = "ref-boundary-pill";
    boundary.innerHTML = `<i></i><span>Research</span>`;
    header.prepend(boundary);
  }

  ensureSelectedAnalysis(root);
}

function enhanceRuns() {
  const surface = main?.querySelector("[data-runs-surface='true']");
  document.body.classList.toggle("reference-runs-active", Boolean(surface));
  if (!surface) return;
  document.body.classList.remove("reference-audit-active");
}

function enhance() {
  refState.enhancementQueued = false;
  const root = activeAuditRoot();
  if (root) {
    enhanceAudit(root);
    return;
  }
  document.body.classList.remove("reference-audit-active");
  enhanceRuns();
}

function queueEnhance() {
  if (refState.enhancementQueued) return;
  refState.enhancementQueued = true;
  queueMicrotask(enhance);
}

const observer = new MutationObserver(queueEnhance);
if (main) observer.observe(main, { childList: true, subtree: true });
window.addEventListener("hashchange", queueEnhance);
queueEnhance();
