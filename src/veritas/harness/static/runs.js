const main = document.querySelector("#main-content");
const RUN_PAGE_LIMIT = 50;

const runFeed = {
  items: [],
  nextCursor: null,
  hasMore: false,
  loadingMore: false,
  loadMoreError: null,
  selectedRunId: null,
  ready: false,
};

const escapeHtml = (value = "") => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

const percent = (value) => `${Math.round((Number(value) || 0) * 100)}%`;
const duration = (value) => {
  if (value == null) return "—";
  const ms = Number(value);
  if (!Number.isFinite(ms)) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(ms < 10000 ? 2 : 1)} s`;
};
const shortTime = (value) => {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" });
};

async function json(path) {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try { detail = (await response.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return response.json();
}

function badge(status = "info", label = status) {
  const normalized = String(status || "info").replaceAll("_", "-");
  return `<span class="badge ${escapeHtml(normalized)}">${escapeHtml(label || "info")}</span>`;
}

function runRow(run, selected = false) {
  const checkCount = (run.counts?.verified || 0) + (run.counts?.needs_review || 0) + (run.counts?.contradictions || 0);
  return `<button class="run-inspector-row ${selected ? "selected" : ""}" data-run-id="${escapeHtml(run.run_id)}">
    <span class="run-kind-mark">${run.run_kind === "replication" ? "↻" : "⌁"}</span>
    <span class="run-row-copy">
      <strong>${escapeHtml(run.task || run.tool || "Run")}</strong>
      <small>${escapeHtml(run.audit_title || "")} · ${escapeHtml(run.run_kind || "audit")} · ${duration(run.duration_ms)}</small>
    </span>
    <span class="run-row-tail">${badge(run.status)}<small>${checkCount ? `${checkCount} checks` : percent(run.coverage)}</small></span>
  </button>`;
}

function eventRow(event, index) {
  const payload = event.payload || {};
  const phase = payload.phase || (event.kind === "replication" ? "update" : "event");
  const icon = event.kind === "tool" ? "⌁" : event.kind === "replication" ? "↻" : event.kind === "finding" ? "!" : "·";
  const eventDuration = payload.duration_ms != null ? ` · ${duration(payload.duration_ms)}` : "";
  return `<div class="run-trace-event">
    <div class="run-trace-rail"><span>${index + 1}</span><i></i></div>
    <div class="run-trace-card">
      <div class="run-trace-head"><div><span class="run-event-icon">${icon}</span><strong>${escapeHtml(event.title || "Event")}</strong></div>${badge(event.status || "info")}</div>
      ${event.detail ? `<p>${escapeHtml(event.detail)}</p>` : ""}
      <div class="run-event-meta"><span>${escapeHtml(event.kind || "event")}</span><span>${escapeHtml(phase)}${escapeHtml(eventDuration)}</span><span>${escapeHtml(shortTime(event.created_at))}</span></div>
    </div>
  </div>`;
}

function parserList(parsers = []) {
  if (!parsers.length) return `<span class="run-muted">—</span>`;
  return parsers.map((parser) => {
    if (typeof parser === "string") return `<span class="run-parser-chip">${escapeHtml(parser)}</span>`;
    const name = parser?.parser || parser?.name || parser?.engine || "parser";
    const version = parser?.version ? ` ${parser.version}` : "";
    return `<span class="run-parser-chip">${escapeHtml(name + version)}</span>`;
  }).join("");
}

function detailView(detail) {
  const counts = detail.counts || {};
  const source = detail.source || {};
  return `<div class="run-detail-shell">
    <div class="run-detail-header">
      <div><span class="eyebrow">${escapeHtml(detail.run_kind || "run")} trace</span><h2>${escapeHtml(detail.tool || "Run")}</h2><p class="mono">${escapeHtml(detail.run_id)}</p></div>
      ${badge(detail.status || "info")}
    </div>
    <div class="run-detail-metrics">
      <div><span>Duration</span><strong>${duration(detail.duration_ms)}</strong></div>
      <div><span>Coverage</span><strong>${percent(detail.coverage)}</strong></div>
      <div><span>Evidence</span><strong>${detail.evidence ? "linked" : "none"}</strong></div>
      <div><span>Checks</span><strong>${Number(counts.verified || 0) + Number(counts.needs_review || 0) + Number(counts.contradictions || 0)}</strong></div>
    </div>
    <div class="run-detail-grid">
      <div class="run-detail-field"><span>Paper</span><strong>${escapeHtml(detail.audit_title || detail.audit_id || "—")}</strong></div>
      <div class="run-detail-field"><span>Artifact</span><strong class="mono">${escapeHtml(detail.artifact_id || "—")}</strong></div>
      <div class="run-detail-field"><span>Started</span><strong>${escapeHtml(shortTime(detail.started_at))}</strong></div>
      <div class="run-detail-field"><span>Finished</span><strong>${escapeHtml(shortTime(detail.finished_at))}</strong></div>
      <div class="run-detail-field run-detail-wide"><span>Parsers</span><div class="run-parser-list">${parserList(detail.parsers)}</div></div>
      <div class="run-detail-field run-detail-wide"><span>Source</span><strong>${escapeHtml([source.table, source.row, source.page ? `page ${source.page}` : ""].filter(Boolean).join(" · ") || "No evidence source attached")}</strong></div>
      ${detail.error_type ? `<div class="run-detail-field run-detail-wide"><span>Error</span><strong>${escapeHtml(detail.error_type)}</strong></div>` : ""}
    </div>
    <div class="run-detail-actions"><a class="secondary-button" target="_blank" rel="noreferrer" href="/api/v1/audits/${encodeURIComponent(detail.audit_id)}/paper">Open paper</a></div>
    <div class="run-trace-title"><h3>Event timeline</h3><span>${detail.events?.length || 0} persisted events</span></div>
    <div class="run-trace-list">${(detail.events || []).map(eventRow).join("") || `<div class="run-empty">No correlated events found.</div>`}</div>
  </div>`;
}

async function selectRun(runId, rows, detailNode) {
  runFeed.selectedRunId = runId;
  rows.forEach((row) => row.classList.toggle("selected", row.dataset.runId === runId));
  detailNode.innerHTML = `<div class="run-detail-loading"><span class="status-icon running">⌁</span><strong>Loading correlated trace…</strong></div>`;
  try {
    const detail = await json(`/api/v1/runs/${encodeURIComponent(runId)}`);
    if (runFeed.selectedRunId === runId) detailNode.innerHTML = detailView(detail);
  } catch (error) {
    if (runFeed.selectedRunId === runId) {
      detailNode.innerHTML = `<div class="run-empty"><strong>Unable to load run</strong><p>${escapeHtml(error.message)}</p></div>`;
    }
  }
}

function pagePath(cursor = null) {
  const params = new URLSearchParams({ limit: String(RUN_PAGE_LIMIT) });
  if (cursor) params.set("cursor", cursor);
  return `/api/v1/run-pages?${params.toString()}`;
}

function mergePageItems(items) {
  const seen = new Set(runFeed.items.map((item) => item.run_id));
  for (const item of items || []) {
    if (!item?.run_id || seen.has(item.run_id)) continue;
    seen.add(item.run_id);
    runFeed.items.push(item);
  }
}

function adoptPage(page) {
  const items = Array.isArray(page?.items) ? page.items : [];
  const previousSelection = runFeed.selectedRunId;
  runFeed.items = [];
  mergePageItems(items);
  runFeed.nextCursor = page?.next_cursor || null;
  runFeed.hasMore = Boolean(page?.has_more && runFeed.nextCursor);
  runFeed.loadingMore = false;
  runFeed.loadMoreError = null;
  runFeed.ready = true;
  runFeed.selectedRunId = runFeed.items.some((item) => item.run_id === previousSelection)
    ? previousSelection
    : runFeed.items[0]?.run_id || null;
}

function runListMarkup() {
  const selected = runFeed.selectedRunId || runFeed.items[0]?.run_id || null;
  const rows = runFeed.items.map((run) => runRow(run, run.run_id === selected)).join("");
  const error = runFeed.loadMoreError
    ? `<div class="run-page-error" role="alert"><strong>Unable to load the next page.</strong><small>${escapeHtml(runFeed.loadMoreError)}</small></div>`
    : "";
  const footer = runFeed.hasMore
    ? `<div class="run-page-footer">${error}<button class="secondary-button" data-run-load-more aria-busy="${runFeed.loadingMore ? "true" : "false"}" ${runFeed.loadingMore ? "disabled" : ""}>${runFeed.loadingMore ? "Loading…" : "Load 50 more"}</button><small>${runFeed.items.length} runs loaded · newest first</small></div>`
    : `<div class="run-page-footer">${error}<small>${runFeed.items.length} runs loaded · end of validated run history</small></div>`;
  return `${rows}${footer}`;
}

function bindRunList(detailNode) {
  const rows = [...document.querySelectorAll(".run-inspector-row")];
  rows.forEach((row) => row.addEventListener("click", () => selectRun(row.dataset.runId, rows, detailNode)));
  const loadMore = document.querySelector("[data-run-load-more]");
  if (loadMore) loadMore.addEventListener("click", () => loadMoreRuns(detailNode));
  return rows;
}

function updateRunList(detailNode) {
  const list = document.querySelector(".run-inspector-list");
  if (!list) return [];
  const previousScrollTop = list.scrollTop;
  list.innerHTML = runListMarkup();
  list.scrollTop = previousScrollTop;
  return bindRunList(detailNode);
}

async function loadMoreRuns(detailNode) {
  if (runFeed.loadingMore || !runFeed.hasMore || !runFeed.nextCursor) return;
  runFeed.loadingMore = true;
  runFeed.loadMoreError = null;
  updateRunList(detailNode);
  try {
    const page = await json(pagePath(runFeed.nextCursor));
    mergePageItems(page.items);
    runFeed.nextCursor = page.next_cursor || null;
    runFeed.hasMore = Boolean(page.has_more && runFeed.nextCursor);
  } catch (error) {
    runFeed.loadMoreError = error.message || "Unknown run paging error";
  } finally {
    runFeed.loadingMore = false;
    updateRunList(detailNode);
  }
}

async function enhanceRuns() {
  if (!main || main.querySelector("[data-runs-surface='true']")) return;
  if (!main.textContent.includes("Agent runs")) return;
  main.dataset.runsEnhanced = "true";

  try {
    if (!runFeed.ready) adoptPage(await json(pagePath()));

    main.innerHTML = `<div class="page" data-runs-surface="true">
      <div class="page-head">
        <div class="page-head-copy"><span class="eyebrow">Harness observability</span><h1 class="page-title">Agent runs</h1><p class="page-subtitle">Inspect deterministic detector and ACP replication runs as correlated start → update → finish traces. History is loaded in bounded validated pages.</p></div>
        <div class="page-actions">${badge("success", `${runFeed.items.length}${runFeed.hasMore ? "+" : ""} terminal runs`)}</div>
      </div>
      ${runFeed.items.length ? `<section class="run-inspector-grid">
        <article class="panel run-list-panel"><div class="panel-head"><h2>Runs</h2><span class="panel-link">Newest first · paged</span></div><div class="run-inspector-list" aria-live="polite">${runListMarkup()}</div></article>
        <article id="run-inspector-detail" class="panel run-detail-panel"></article>
      </section>` : `<section class="panel"><div class="empty-state"><div class="empty-state-inner"><div class="empty-mark">⌁</div><h2>No runs yet</h2><p>Run a detector audit or configured reproduction job to create a correlated trace.</p></div></div></section>`}
    </div>`;

    const detailNode = document.querySelector("#run-inspector-detail");
    if (detailNode && runFeed.items.length) {
      const rows = bindRunList(detailNode);
      await selectRun(runFeed.selectedRunId, rows, detailNode);
    }
  } catch (error) {
    main.innerHTML = `<div class="page"><div class="empty-state"><div class="empty-state-inner"><div class="empty-mark">!</div><h2>Run inspector unavailable</h2><p>${escapeHtml(error.message)}</p></div></div></div>`;
  }
}

window.addEventListener("veritas:run-page-reset", (event) => adoptPage(event.detail || {}));
if (window.__veritasRunPageFeed) adoptPage(window.__veritasRunPageFeed);

const observer = new MutationObserver(() => {
  if (!main) return;
  if (!main.textContent.includes("Agent runs")) {
    if (!main.querySelector("[data-runs-surface]")) {
      delete main.dataset.runsEnhanced;
      runFeed.items = [];
      runFeed.nextCursor = null;
      runFeed.hasMore = false;
      runFeed.loadingMore = false;
      runFeed.loadMoreError = null;
      runFeed.selectedRunId = null;
      runFeed.ready = false;
    }
    return;
  }
  queueMicrotask(enhanceRuns);
});

if (main) {
  observer.observe(main, { childList: true, subtree: true });
  queueMicrotask(enhanceRuns);
}
