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

function boolBadge(value, yes = "enabled", no = "disabled") {
  return value ? badge("success", yes) : badge("review", no);
}

function capabilityRow(label, value, detail = "") {
  return `<div class="settings-capability-row"><div><strong>${escapeHtml(label)}</strong>${detail ? `<small>${escapeHtml(detail)}</small>` : ""}</div><div>${value}</div></div>`;
}

async function fetchCapabilities() {
  const response = await fetch("/api/v1/capabilities", { headers: { Accept: "application/json" } });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try { detail = (await response.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return response.json();
}

function parserPanel(parser = {}) {
  const baseline = Array.isArray(parser.baseline) ? parser.baseline : [];
  const families = Array.isArray(parser.baseline_families) ? parser.baseline_families : [];
  const optional = parser.third_parser_enabled
    ? `${escapeHtml(parser.third_parser || "optional")} ${parser.docling_available ? badge("success", "dependency ready") : badge("review", "dependency missing")}`
    : badge("success", "locked dual baseline");
  return `<article class="panel settings-card">
    <div class="panel-head"><h2>Parser stack</h2>${parser.consensus_policy_changed ? badge("danger", "policy changed") : badge("success", "consensus unchanged")}</div>
    <div class="panel-body settings-body">
      <p class="settings-copy">The product always retains two independent native parser families. An optional third parser is observational until locked evaluation justifies a promotion-policy change.</p>
      <div class="settings-list">
        ${capabilityRow("Baseline", baseline.map((item) => `<span class="settings-chip">${escapeHtml(item)}</span>`).join(" ") || "—", families.join(" · "))}
        ${capabilityRow("Third parser", optional, parser.third_parser_enabled ? "VERITAS_PDF_THIRD_PARSER is explicitly configured" : "Not configured")}
        ${capabilityRow("Consensus policy", parser.consensus_policy_changed ? badge("danger", "changed") : badge("success", "unchanged"), "Optional parsing cannot silently weaken the current two-family requirement")}
      </div>
    </div>
  </article>`;
}

function replicationPanel(replication = {}) {
  const configured = Boolean(replication.configured);
  return `<article class="panel settings-card">
    <div class="panel-head"><h2>Reproduction runtime</h2>${configured ? badge("success", "agent configured") : badge("review", "fail-closed")}</div>
    <div class="panel-body settings-body">
      <p class="settings-copy">ACP execution is server-selected. Browser and mobile clients can submit a reproduction objective, but cannot choose a shell command.</p>
      <div class="settings-list">
        ${capabilityRow("Agent", configured ? `<strong>${escapeHtml(replication.agent || "ACP agent")}</strong>` : badge("review", "not configured"), "VERITAS_REPLICATION_AGENT controls the server-side adapter")}
        ${capabilityRow("Permission policy", badge(replication.permission_policy === "deny" ? "success" : "review", replication.permission_policy || "deny"), replication.permission_policy_valid === false ? "Invalid configuration was reduced to the safe default" : "Default is deny; allow_once never upgrades to allow_always")}
        ${capabilityRow("Client shell commands", replication.client_supplied_commands ? badge("danger", "accepted") : badge("success", "rejected"), "Execution argv is never supplied by the client")}
        ${capabilityRow("Workspace boundary", replication.workspace_is_security_boundary ? badge("success", "sandbox") : badge("review", "agent-defined"), "The selected ACP agent remains responsible for its execution sandbox")}
      </div>
    </div>
  </article>`;
}

function observabilityPanel(observability = {}) {
  return `<article class="panel settings-card">
    <div class="panel-head"><h2>Observability export</h2>${observability.enabled ? badge("success", "OTLP enabled") : badge("review", "local only")}</div>
    <div class="panel-body settings-body">
      <p class="settings-copy">Terminal detector and reproduction runs can be exported as OTLP spans after the local event is durable. Export failure never changes an audit result.</p>
      <div class="settings-list">
        ${capabilityRow("Protocol", `<strong>${escapeHtml(observability.protocol || "otlp/http-protobuf")}</strong>`, "Enable with VERITAS_OTEL_EXPORT=true")}
        ${capabilityRow("Dependencies", boolBadge(observability.dependencies_available, "installed", "optional extra missing"), "Install the observability extra only when exporting traces")}
        ${capabilityRow("Collector endpoint", boolBadge(observability.endpoint_configured, "configured", "not configured"), "Endpoint value is intentionally not disclosed through the API")}
        ${capabilityRow("Payload policy", observability.metadata_only ? badge("success", "metadata only") : badge("danger", "expanded"), "Raw prompts and evidence text stay local")}
      </div>
      <div class="settings-privacy-grid">
        <div><span>Raw prompts</span><strong>${observability.raw_prompts_exported ? "exported" : "not exported"}</strong></div>
        <div><span>Evidence text</span><strong>${observability.evidence_text_exported ? "exported" : "not exported"}</strong></div>
      </div>
    </div>
  </article>`;
}

function apiPanel(caps = {}) {
  const uploadMiB = Math.round(Number(caps.max_upload_bytes || 0) / 1024 / 1024);
  return `<article class="panel settings-card">
    <div class="panel-head"><h2>Product contract</h2>${badge("success", `API ${caps.api_version || "v1"}`)}</div>
    <div class="panel-body settings-body">
      <div class="settings-list">
        ${capabilityRow("Streaming", `<strong>${escapeHtml(String(caps.streaming || "ndjson").toUpperCase())}</strong>`, "Audit and replication event streams use the same versioned contract")}
        ${capabilityRow("Upload limit", `<strong>${uploadMiB || 80} MiB</strong>`, "PDF artifacts remain local-first")}
        ${capabilityRow("Clients", `<span>${(caps.clients || []).map((item) => `<span class="settings-chip">${escapeHtml(item)}</span>`).join(" ")}</span>`, "Web, installable PWA, and Expo share /api/v1")}
      </div>
      <div class="settings-actions"><a class="secondary-button" href="/api/docs" target="_blank" rel="noreferrer">Open API docs</a></div>
    </div>
  </article>`;
}

function renderSettings(caps) {
  return `<div class="page" data-settings-surface="true">
    <div class="page-head"><div class="page-head-copy"><span class="eyebrow">System</span><h1 class="page-title">Settings</h1><p class="page-subtitle">Inspect the live parser, reproduction, API, and telemetry safety contract without exposing secrets or changing server configuration from the browser.</p></div><div class="page-actions">${badge("success", "local-first")}</div></div>
    <section class="settings-grid">
      ${apiPanel(caps)}
      ${parserPanel(caps.parser_stack || {})}
      ${replicationPanel(caps.replication || {})}
      ${observabilityPanel(caps.observability || {})}
    </section>
    <section class="panel settings-mobile-card"><div class="panel-head"><h2>Mobile connectivity</h2></div><div class="panel-body settings-body"><p class="settings-copy">Physical devices use the same API contract. Set <span class="mono">EXPO_PUBLIC_VERITAS_API_URL</span> to a reachable LAN or HTTPS address. Browser cross-origin access remains opt-in through <span class="mono">VERITAS_CORS_ORIGINS</span>.</p></div></section>
  </div>`;
}

async function enhanceSettings() {
  if (!main || main.dataset.settingsEnhanced === "true") return;
  const title = main.querySelector(".page-title")?.textContent?.trim();
  if (title !== "Settings") return;
  main.dataset.settingsEnhanced = "true";
  main.innerHTML = `<div class="page"><div class="settings-loading"><span class="status-icon running">⌁</span><strong>Loading live capabilities…</strong></div></div>`;
  try {
    const caps = await fetchCapabilities();
    main.innerHTML = renderSettings(caps);
  } catch (error) {
    main.innerHTML = `<div class="page"><div class="empty-state"><div class="empty-state-inner"><div class="empty-mark">!</div><h2>Settings unavailable</h2><p>${escapeHtml(error.message)}</p></div></div></div>`;
  }
}

const observer = new MutationObserver(() => {
  if (!main) return;
  const title = main.querySelector(".page-title")?.textContent?.trim();
  if (title !== "Settings" && !main.querySelector("[data-settings-surface]")) {
    delete main.dataset.settingsEnhanced;
    return;
  }
  queueMicrotask(enhanceSettings);
});

if (main) {
  observer.observe(main, { childList: true, subtree: true });
  queueMicrotask(enhanceSettings);
}
