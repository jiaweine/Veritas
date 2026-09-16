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

async function fetchCatalog() {
  const response = await fetch("/api/v1/benchmarks", { headers: { Accept: "application/json" } });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try { detail = (await response.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return response.json();
}

function resultBadge(result) {
  if (!result) return badge("review", "no persisted run");
  const tones = { passed: "success", failed: "danger", error: "danger", skipped: "review" };
  return badge(tones[result.status] || "review", result.status || "unknown");
}

function resultMeta(result) {
  if (!result) {
    return `<div class="benchmark-result-empty">No Benchmark Result Envelope v1 has been ingested for this suite.</div>`;
  }
  const commit = result.commit_sha ? String(result.commit_sha).slice(0, 10) : "uncommitted/operator";
  const metrics = result.metrics && typeof result.metrics === "object"
    ? Object.entries(result.metrics).slice(0, 4)
    : [];
  const metricRows = metrics.length
    ? `<div class="benchmark-metrics">${metrics.map(([key, value]) => `<span><strong>${escapeHtml(key)}</strong>${escapeHtml(value)}</span>`).join("")}</div>`
    : `<div class="benchmark-result-empty">No scalar metrics were recorded.</div>`;
  return `<div class="benchmark-result">
    <div class="benchmark-result-row"><span>finished</span><strong>${escapeHtml(result.finished_at || "")}</strong></div>
    <div class="benchmark-result-row"><span>commit</span><strong class="mono">${escapeHtml(commit)}</strong></div>
    <div class="benchmark-result-row"><span>source</span><strong>${escapeHtml(result.source || "")}</strong></div>
    ${metricRows}
  </div>`;
}

function suiteCard(suite, latest) {
  const gating = Boolean(suite.gating);
  return `<article class="benchmark-card">
    <div class="benchmark-card-head"><div><span class="benchmark-kind">${escapeHtml(suite.kind || "benchmark")}</span><h3>${escapeHtml(suite.title || suite.benchmark_id)}</h3></div>${gating ? badge("success", "release gate") : badge("review", "non-gating")}</div>
    <p>${escapeHtml(suite.scope || "")}</p>
    <div class="benchmark-command"><span>command</span><code>${escapeHtml(suite.command || "")}</code></div>
    <div class="benchmark-source"><span>source</span><span class="mono">${escapeHtml(suite.source || "")}</span></div>
    <div class="benchmark-result-head"><span>latest persisted result</span>${resultBadge(latest)}</div>
    ${resultMeta(latest)}
  </article>`;
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
      <article class="panel benchmark-summary"><span>Persisted runs</span><strong>${resultCount}</strong><small>${resultCount ? "Versioned execution envelopes available." : "No result envelope has been ingested yet."}</small></article>
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

    <section class="benchmark-policy panel"><div><strong>Result policy</strong><p>Benchmark inventory, execution status, and benchmark metrics remain separate facts. Veritas persists validated Benchmark Result Envelope v1 objects only when an operator explicitly ingests them; heterogeneous metrics are shown as recorded and are never collapsed into a synthetic global score or trend.</p></div>${catalog.result_persistence ? badge("success", "versioned persistence") : badge("review", "inventory only")}</section>
  </div>`;
}

async function enhanceBenchmarks() {
  if (!main || main.dataset.benchmarksEnhanced === "true") return;
  const title = main.querySelector(".page-title")?.textContent?.trim();
  if (title !== "Benchmarks") return;
  main.dataset.benchmarksEnhanced = "true";
  main.innerHTML = `<div class="page"><div class="benchmark-loading"><span class="status-icon running">⌗</span><strong>Loading repository benchmark inventory…</strong></div></div>`;
  try {
    const catalog = await fetchCatalog();
    main.innerHTML = renderCatalog(catalog);
  } catch (error) {
    main.innerHTML = `<div class="page"><div class="empty-state"><div class="empty-state-inner"><div class="empty-mark">!</div><h2>Benchmark inventory unavailable</h2><p>${escapeHtml(error.message)}</p></div></div></div>`;
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
