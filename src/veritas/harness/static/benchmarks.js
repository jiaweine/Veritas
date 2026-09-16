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

function suiteCard(suite) {
  const gating = Boolean(suite.gating);
  return `<article class="benchmark-card">
    <div class="benchmark-card-head"><div><span class="benchmark-kind">${escapeHtml(suite.kind || "benchmark")}</span><h3>${escapeHtml(suite.title || suite.benchmark_id)}</h3></div>${gating ? badge("success", "release gate") : badge("review", "non-gating")}</div>
    <p>${escapeHtml(suite.scope || "")}</p>
    <div class="benchmark-command"><span>command</span><code>${escapeHtml(suite.command || "")}</code></div>
    <div class="benchmark-source"><span>source</span><span class="mono">${escapeHtml(suite.source || "")}</span></div>
  </article>`;
}

function renderCatalog(catalog) {
  const suites = Array.isArray(catalog.suites) ? catalog.suites : [];
  const gating = suites.filter((suite) => suite.gating);
  const probes = suites.filter((suite) => !suite.gating);
  return `<div class="page" data-benchmark-surface="true">
    <div class="page-head"><div class="page-head-copy"><span class="eyebrow">Evaluation</span><h1 class="page-title">Benchmarks</h1><p class="page-subtitle">Repository-native release gates and diagnostic probes. This surface shows the benchmark inventory, not invented run scores.</p></div><div class="page-actions">${badge("success", `${gating.length} gating`)} ${badge("review", `${probes.length} probes`)}</div></div>

    <section class="benchmark-summary-grid">
      <article class="panel benchmark-summary"><span>Release gates</span><strong>${gating.length}</strong><small>Failures stop CI.</small></article>
      <article class="panel benchmark-summary"><span>Non-gating probes</span><strong>${probes.length}</strong><small>Diagnostics run with continue-on-error.</small></article>
      <article class="panel benchmark-summary"><span>Persisted scores</span><strong>${catalog.scores_available ? "yes" : "no"}</strong><small>${catalog.scores_available ? "Durable results available." : "No product score is fabricated."}</small></article>
      <article class="panel benchmark-summary"><span>Source of truth</span><strong class="benchmark-source-short">CI</strong><small class="mono">${escapeHtml(catalog.source_of_truth || ".github/workflows/ci.yml")}</small></article>
    </section>

    <section class="panel benchmark-section">
      <div class="panel-head"><h2>Release gates</h2><span class="panel-link">must pass</span></div>
      <div class="benchmark-grid">${gating.map(suiteCard).join("")}</div>
    </section>

    <section class="panel benchmark-section">
      <div class="panel-head"><h2>Diagnostic probes</h2><span class="panel-link">non-gating</span></div>
      <div class="benchmark-grid">${probes.map(suiteCard).join("")}</div>
    </section>

    <section class="benchmark-policy panel"><div><strong>Result policy</strong><p>Benchmark presence and benchmark execution are different facts. Until Veritas has a durable, versioned benchmark-result object, this page intentionally exposes commands and gate status only.</p></div>${catalog.result_persistence ? badge("success", "results persisted") : badge("review", "inventory only")}</section>
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
