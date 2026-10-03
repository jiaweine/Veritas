const main = document.querySelector("#main-content");
let enhancementGeneration = 0;
const BENCHMARK_PAGE_LIMIT = 50;

const benchmarkHistory = {
  items: [],
  nextCursor: null,
  hasMore: false,
  total: 0,
  loadingMore: false,
  loadMoreError: "",
};

const escapeHtml = (value = "") => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

const METRIC_PRIORITY = [
  "cases",
  "detector_families",
  "alert_precision",
  "alert_recall",
  "false_hard_alert_rate_per_clean_paper",
  "grade_violations",
  "production_certificate",
];

function badge(tone, label) {
  return `<span class="badge ${escapeHtml(tone)}">${escapeHtml(label)}</span>`;
}

async function fetchJson(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try { detail = (await response.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return response.json();
}

async function fetchCatalog() {
  return fetchJson("/api/v1/benchmarks");
}

async function fetchHistoryPage(cursor = null) {
  const url = new URL("/api/v1/benchmark-result-pages", window.location.origin);
  url.searchParams.set("limit", String(BENCHMARK_PAGE_LIMIT));
  if (cursor) url.searchParams.set("cursor", cursor);
  return fetchJson(`${url.pathname}${url.search}`);
}

function resultBadge(result) {
  if (!result) return badge("review", "no local result");
  const tones = { passed: "success", failed: "danger", error: "danger", skipped: "review" };
  return badge(tones[result.status] || "review", result.status || "unknown");
}

function orderedMetrics(metrics) {
  if (!metrics || typeof metrics !== "object") return [];
  const entries = Object.entries(metrics);
  const byKey = new Map(entries);
  const prioritized = METRIC_PRIORITY
    .filter((key) => byKey.has(key))
    .map((key) => [key, byKey.get(key)]);
  const remaining = entries.filter(([key]) => !METRIC_PRIORITY.includes(key));
  return [...prioritized, ...remaining].slice(0, 6);
}

function resultMeta(result) {
  if (!result) {
    return `<div class="benchmark-result-empty">No Benchmark Result Envelope v1 has been ingested locally for this suite.</div>`;
  }
  const commit = result.commit_sha ? String(result.commit_sha).slice(0, 10) : "uncommitted/operator";
  const metrics = result.metrics && typeof result.metrics === "object" ? result.metrics : {};
  const metricEntries = orderedMetrics(metrics);
  const metricRows = metricEntries.length
    ? `<div class="benchmark-metrics">${metricEntries.map(([key, value]) => `<span><strong>${escapeHtml(key)}</strong>${escapeHtml(value)}</span>`).join("")}</div>`
    : `<div class="benchmark-result-empty">No scalar metrics were recorded.</div>`;
  const authorityBoundary = metrics.production_certificate === false
    ? `<div class="benchmark-authority-note">Synthetic CI result — not a production certificate.</div>`
    : "";
  return `<div class="benchmark-result">
    <div class="benchmark-result-row"><span>finished</span><strong>${escapeHtml(result.finished_at || "")}</strong></div>
    <div class="benchmark-result-row"><span>commit</span><strong class="mono">${escapeHtml(commit)}</strong></div>
    <div class="benchmark-result-row"><span>source</span><strong>${escapeHtml(result.source || "")}</strong></div>
    ${metricRows}
    ${authorityBoundary}
  </div>`;
}

function suiteCard(suite, latest) {
  const gating = Boolean(suite.gating);
  return `<article class="benchmark-card" data-benchmark-id="${escapeHtml(suite.benchmark_id || "")}">
    <div class="benchmark-card-head"><div><span class="benchmark-kind">${escapeHtml(suite.kind || "benchmark")}</span><h3>${escapeHtml(suite.title || suite.benchmark_id)}</h3></div>${gating ? badge("success", "release gate") : badge("review", "non-gating")}</div>
    <p>${escapeHtml(suite.scope || "")}</p>
    <div class="benchmark-command"><span>command</span><code>${escapeHtml(suite.command || "")}</code></div>
    <div class="benchmark-source"><span>source</span><span class="mono">${escapeHtml(suite.source || "")}</span></div>
    <div class="benchmark-result-head"><span>latest persisted result</span>${resultBadge(latest)}</div>
    ${resultMeta(latest)}
  </article>`;
}

function resetHistoryFeed() {
  benchmarkHistory.items = [];
  benchmarkHistory.nextCursor = null;
  benchmarkHistory.hasMore = false;
  benchmarkHistory.total = 0;
  benchmarkHistory.loadingMore = false;
  benchmarkHistory.loadMoreError = "";
}

function mergeHistoryItems(items) {
  const seen = new Set(benchmarkHistory.items.map((item) => item.result_id));
  for (const item of items) {
    if (!item || !item.result_id || seen.has(item.result_id)) continue;
    seen.add(item.result_id);
    benchmarkHistory.items.push(item);
  }
}

function applyHistoryPage(page, { replace = false } = {}) {
  if (replace) benchmarkHistory.items = [];
  mergeHistoryItems(Array.isArray(page.items) ? page.items : []);
  benchmarkHistory.nextCursor = page.next_cursor || null;
  benchmarkHistory.hasMore = Boolean(page.has_more);
  benchmarkHistory.total = Number(page.total || 0);
  benchmarkHistory.loadMoreError = "";
}

function historyRow(result) {
  const commit = result.commit_sha ? String(result.commit_sha).slice(0, 10) : "operator";
  const title = result.title || result.benchmark_id || "Benchmark result";
  return `<article class="benchmark-history-row" data-benchmark-result-id="${escapeHtml(result.result_id || "")}">
    <div class="benchmark-history-primary">
      <div><span class="benchmark-kind">${escapeHtml(result.benchmark_id || "benchmark")}</span><strong>${escapeHtml(title)}</strong></div>
      ${resultBadge(result)}
    </div>
    <div class="benchmark-history-meta">
      <span><small>finished</small>${escapeHtml(result.finished_at || "")}</span>
      <span><small>commit</small><span class="mono">${escapeHtml(commit)}</span></span>
      <span><small>source</small>${escapeHtml(result.source || "")}</span>
    </div>
    <details>
      <summary>Envelope details</summary>
      ${resultMeta(result)}
    </details>
  </article>`;
}

function renderHistorySection() {
  const loaded = benchmarkHistory.items.length;
  const total = benchmarkHistory.total;
  const body = loaded
    ? `<div class="benchmark-history-list">${benchmarkHistory.items.map(historyRow).join("")}</div>`
    : `<div class="benchmark-history-empty">No persisted benchmark history yet.</div>`;

  let footer = "";
  if (benchmarkHistory.loadMoreError) {
    footer = `<div class="benchmark-history-footer benchmark-history-error">
      <span>Unable to load the next benchmark result page. ${escapeHtml(benchmarkHistory.loadMoreError)}</span>
      <button type="button" class="btn btn-secondary" data-benchmark-load-more>Retry</button>
    </div>`;
  } else if (benchmarkHistory.hasMore) {
    footer = `<div class="benchmark-history-footer">
      <span>${loaded} of ${total} persisted results loaded.</span>
      <button type="button" class="btn btn-secondary" data-benchmark-load-more ${benchmarkHistory.loadingMore ? "disabled" : ""}>${benchmarkHistory.loadingMore ? "Loading…" : `Load ${BENCHMARK_PAGE_LIMIT} more`}</button>
    </div>`;
  } else if (loaded) {
    footer = `<div class="benchmark-history-footer"><span>Loaded all ${total} persisted results.</span></div>`;
  }

  return `<section class="panel benchmark-section benchmark-history-section" data-benchmark-history>
    <div class="panel-head"><div><h2>Persisted result history</h2><p>Validated Benchmark Result Envelope v1 records, newest first. Metrics are shown as recorded; no cross-suite score or trend is inferred.</p></div><span class="panel-link">${loaded} / ${total}</span></div>
    ${body}
    ${footer}
  </section>`;
}

function renderCatalog(catalog) {
  const suites = Array.isArray(catalog.suites) ? catalog.suites : [];
  const latest = catalog.latest_results && typeof catalog.latest_results === "object" ? catalog.latest_results : {};
  const gating = suites.filter((suite) => suite.gating);
  const probes = suites.filter((suite) => !suite.gating);
  const resultCount = Number(catalog.result_count || 0);
  return `<div class="page" data-benchmark-surface="true">
    <div class="page-head"><div class="page-head-copy"><span class="eyebrow">Evaluation</span><h1 class="page-title">Benchmarks</h1><p class="page-subtitle">Repository-native release gates, diagnostic probes, and explicitly ingested result envelopes. No normalized score or trend is inferred.</p></div><div class="page-actions">${badge("success", `${gating.length} gating`)} ${badge("review", `${probes.length} probes`)}</div></div>

    <section class="benchmark-summary-grid">
      <article class="panel benchmark-summary"><span>Release gates</span><strong>${gating.length}</strong><small>Failures stop CI.</small></article>
      <article class="panel benchmark-summary"><span>Non-gating probes</span><strong>${probes.length}</strong><small>Diagnostics do not define release success.</small></article>
      <article class="panel benchmark-summary"><span>Persisted runs</span><strong>${resultCount}</strong><small>${resultCount ? "Versioned execution envelopes available." : "No result envelope has been ingested locally yet."}</small></article>
      <article class="panel benchmark-summary"><span>Source of truth</span><strong class="benchmark-source-short">CI</strong><small class="mono">${escapeHtml(catalog.source_of_truth || ".github/workflows/ci.yml")}</small></article>
    </section>

    <section class="panel benchmark-section">
      <div class="panel-head"><h2>Release gates</h2><span class="panel-link">must pass</span></div>
      <div class="benchmark-grid">${gating.map((suite) => suiteCard(suite, latest[suite.benchmark_id])).join("")}</div>
    </section>

    <section class="panel benchmark-section">
      <div class="panel-head"><h2>Diagnostic probes</h2><span class="panel-link">non-gating</span></div>
      <div class="benchmark-grid">${probes.map((suite) => suiteCard(suite, latest[suite.benchmark_id])).join("")}</div>
    </section>

    ${renderHistorySection()}

    <section class="benchmark-policy panel"><div><strong>Result policy</strong><p>Benchmark inventory, execution status, and benchmark metrics remain separate facts. Veritas persists validated Benchmark Result Envelope v1 objects only when an operator explicitly ingests them; heterogeneous metrics are shown as recorded and are never collapsed into a synthetic global score or trend.</p></div>${catalog.result_persistence ? badge("success", "versioned persistence") : badge("review", "inventory only")}</section>
  </div>`;
}

function benchmarkTitleIsActive() {
  return main?.querySelector(".page-title")?.textContent?.trim() === "Benchmarks";
}

function replaceHistorySection() {
  if (!main || !benchmarkTitleIsActive()) return;
  const section = main.querySelector("[data-benchmark-history]");
  if (!section) return;
  const previousScrollY = window.scrollY;
  section.outerHTML = renderHistorySection();
  window.scrollTo(0, previousScrollY);
}

async function enhanceBenchmarks() {
  if (!main) return;
  const phase = main.dataset.benchmarksEnhanced;
  if (phase === "loading" || phase === "true") return;
  if (!benchmarkTitleIsActive()) return;

  const generation = ++enhancementGeneration;
  main.dataset.benchmarksEnhanced = "loading";
  resetHistoryFeed();
  try {
    const [catalog, historyPage] = await Promise.all([fetchCatalog(), fetchHistoryPage()]);
    if (generation !== enhancementGeneration || !benchmarkTitleIsActive()) return;
    applyHistoryPage(historyPage, { replace: true });
    main.innerHTML = renderCatalog(catalog);
    main.dataset.benchmarksEnhanced = "true";
  } catch (error) {
    if (generation !== enhancementGeneration || !benchmarkTitleIsActive()) return;
    main.innerHTML = `<div class="page"><div class="empty-state"><div class="empty-state-inner"><div class="empty-mark">!</div><h2>Benchmark inventory unavailable</h2><p>${escapeHtml(error.message)}</p></div></div></div>`;
    main.dataset.benchmarksEnhanced = "true";
  }
}

async function loadMoreBenchmarkHistory() {
  if (!benchmarkHistory.hasMore || benchmarkHistory.loadingMore) return;
  benchmarkHistory.loadingMore = true;
  benchmarkHistory.loadMoreError = "";
  replaceHistorySection();
  try {
    const page = await fetchHistoryPage(benchmarkHistory.nextCursor);
    if (!benchmarkTitleIsActive()) return;
    applyHistoryPage(page);
  } catch (error) {
    benchmarkHistory.loadMoreError = error.message || String(error);
  } finally {
    benchmarkHistory.loadingMore = false;
    replaceHistorySection();
  }
}

const observer = new MutationObserver(() => {
  if (!main) return;
  const title = main.querySelector(".page-title")?.textContent?.trim();
  const hasSurface = Boolean(main.querySelector("[data-benchmark-surface]"));
  if (title !== "Benchmarks" && !hasSurface) {
    enhancementGeneration += 1;
    delete main.dataset.benchmarksEnhanced;
    resetHistoryFeed();
    return;
  }
  queueMicrotask(enhanceBenchmarks);
});

if (main) {
  main.addEventListener("click", (event) => {
    const button = event.target.closest?.("[data-benchmark-load-more]");
    if (button) void loadMoreBenchmarkHistory();
  });
  observer.observe(main, { childList: true, subtree: true });
  queueMicrotask(enhanceBenchmarks);
}
