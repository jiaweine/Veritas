const main = document.querySelector("#main-content");

const escapeHtml = (value = "") => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

function badge(tone, label) {
  return `<span class="badge ${escapeHtml(tone)}">${escapeHtml(label)}</span>`;
}

async function fetchJson(path) {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try { detail = (await response.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return response.json();
}

const formatDuration = (value) => Number.isInteger(value) ? `${value} ms` : "—";
const formatCommit = (value) => value ? String(value).slice(0, 10) : "local / unknown";
function formatTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

function resultBadge(result) {
  if (!result) return badge("review", "no recorded run");
  return result.status === "passed" ? badge("success", "passed") : badge("danger", "failed");
}

function latestResult(result) {
  if (!result) {
    return `<div class="benchmark-result empty"><span>Latest recorded execution</span><strong>None</strong><small>Record a completed suite with <code>veritas-benchmark-result record</code>.</small></div>`;
  }
  return `<div class="benchmark-result">
    <div><span>Latest recorded execution</span>${resultBadge(result)}</div>
    <strong>${escapeHtml(formatCommit(result.commit_sha))}</strong>
    <small>${escapeHtml(formatTime(result.recorded_at))} · exit ${escapeHtml(result.exit_code)} · ${escapeHtml(formatDuration(result.duration_ms))}</small>
  </div>`;
}

function suiteCard(suite) {
  const gating = Boolean(suite.gating);
  return `<article class="benchmark-card">
    <div class="benchmark-card-head"><div><span class="benchmark-kind">${escapeHtml(suite.kind || "benchmark")}</span><h3>${escapeHtml(suite.title || suite.benchmark_id)}</h3></div>${gating ? badge("success", "release gate") : badge("review", "non-gating")}</div>
    <p>${escapeHtml(suite.scope || "")}</p>
    <div class="benchmark-command"><span>command</span><code>${escapeHtml(suite.command || "")}</code></div>
    <div class="benchmark-source"><span>source</span><span class="mono">${escapeHtml(suite.source || "")}</span></div>
    ${latestResult(suite.latest_result)}
  </article>`;
}

function historyRow(result) {
  const gate = result.gating ? "gate" : "probe";
  return `<div class="benchmark-history-row">
    <div><strong>${escapeHtml(result.title || result.benchmark_id)}</strong><small>${escapeHtml(result.benchmark_id)} · ${escapeHtml(gate)}</small></div>
    <div>${resultBadge(result)}</div>
    <div class="mono">${escapeHtml(formatCommit(result.commit_sha))}</div>
    <div>${escapeHtml(formatDuration(result.duration_ms))}</div>
    <div>${escapeHtml(formatTime(result.recorded_at))}</div>
  </div>`;
}

function renderHistory(results) {
  if (!results.length) {
    return `<div class="benchmark-history-empty"><strong>No persisted executions yet.</strong><p>The result store is enabled, but Veritas will not infer historical passes from repository files or CI badges. Record only executions you actually ran.</p></div>`;
  }
  return `<div class="benchmark-history-head"><span>Suite</span><span>Status</span><span>Commit</span><span>Duration</span><span>Recorded</span></div>
    <div class="benchmark-history-list">${results.map(historyRow).join("")}</div>`;
}

function renderCatalog(catalog, resultsPayload) {
  const suites = Array.isArray(catalog.suites) ? catalog.suites : [];
  const results = Array.isArray(resultsPayload.results) ? resultsPayload.results : [];
  const gating = suites.filter((suite) => suite.gating);
  const probes = suites.filter((suite) => !suite.gating);
  return `<div class="page" data-benchmark-surface="true">
    <div class="page-head"><div class="page-head-copy"><span class="eyebrow">Evaluation</span><h1 class="page-title">Benchmarks</h1><p class="page-subtitle">Repository-native release gates plus durable execution provenance. Results are persisted facts; scores and trends are not invented.</p></div><div class="page-actions">${badge("success", `${gating.length} gating`)} ${badge("review", `${probes.length} probes`)}</div></div>

    <section class="benchmark-summary-grid">
      <article class="panel benchmark-summary"><span>Release gates</span><strong>${gating.length}</strong><small>Failures stop CI.</small></article>
      <article class="panel benchmark-summary"><span>Non-gating probes</span><strong>${probes.length}</strong><small>Diagnostics do not define release success.</small></article>
      <article class="panel benchmark-summary"><span>Persisted executions</span><strong>${escapeHtml(catalog.result_count || 0)}</strong><small>${catalog.results_available ? "Append-only provenance is available." : "Result store ready; no execution recorded yet."}</small></article>
      <article class="panel benchmark-summary"><span>Benchmark scores</span><strong>${catalog.scores_available ? "yes" : "no"}</strong><small>${catalog.scores_available ? "Explicit score schema available." : "No product score is fabricated."}</small></article>
    </section>

    <section class="panel benchmark-section">
      <div class="panel-head"><h2>Release gates</h2><span class="panel-link">must pass</span></div>
      <div class="benchmark-grid">${gating.map(suiteCard).join("")}</div>
    </section>

    <section class="panel benchmark-section">
      <div class="panel-head"><h2>Diagnostic probes</h2><span class="panel-link">non-gating</span></div>
      <div class="benchmark-grid">${probes.map(suiteCard).join("")}</div>
    </section>

    <section class="panel benchmark-section">
      <div class="panel-head"><h2>Execution provenance</h2><span class="panel-link">latest ${results.length}</span></div>
      <div class="benchmark-history">${renderHistory(results)}</div>
    </section>

    <section class="benchmark-policy panel"><div><strong>Result policy</strong><p>Inventory, execution status, and benchmark score are separate facts. Veritas persists only explicitly recorded executions of known suites, verifies each result file on read, and keeps scores unavailable until a dedicated versioned score schema exists.</p></div>${catalog.result_persistence ? badge("success", "provenance persisted") : badge("review", "inventory only")}</section>
  </div>`;
}

async function enhanceBenchmarks() {
  if (!main || main.dataset.benchmarksEnhanced === "true") return;
  const title = main.querySelector(".page-title")?.textContent?.trim();
  if (title !== "Benchmarks") return;
  main.dataset.benchmarksEnhanced = "true";
  main.innerHTML = `<div class="page"><div class="benchmark-loading"><span class="status-icon running">⌗</span><strong>Loading repository benchmark provenance…</strong></div></div>`;
  try {
    const [catalog, results] = await Promise.all([
      fetchJson("/api/v1/benchmarks"),
      fetchJson("/api/v1/benchmarks/results?limit=20"),
    ]);
    main.innerHTML = renderCatalog(catalog, results);
  } catch (error) {
    main.innerHTML = `<div class="page"><div class="empty-state"><div class="empty-state-inner"><div class="empty-mark">!</div><h2>Benchmark provenance unavailable</h2><p>${escapeHtml(error.message)}</p></div></div></div>`;
  }
}

const observer = new MutationObserver(() => {
  if (!main) return;
  const title = main.querySelector(".page-title")?.textContent?.trim();
  if (title !== "Benchmarks" && !main.querySelector("[data-benchmark-surface]")) {
    delete main.dataset.benchmarksEnhanced;
    return;
  }
  queueMicrotask(enhanceBenchmarks);
});

if (main) {
  observer.observe(main, { childList: true, subtree: true });
  queueMicrotask(enhanceBenchmarks);
}
