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

async function getJson(path) {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try { detail = (await response.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return response.json();
}

function fetchCapabilities() {
  return getJson("/api/v1/capabilities");
}

function fetchModelProviders() {
  return getJson("/api/v1/model-providers");
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
  const requested = Boolean(observability.enabled);
  const active = Boolean(observability.active);
  const stateBadge = active
    ? badge("success", "OTLP active")
    : requested
      ? badge("review", "incomplete config")
      : badge("review", "local only");
  return `<article class="panel settings-card">
    <div class="panel-head"><h2>Observability export</h2>${stateBadge}</div>
    <div class="panel-body settings-body">
      <p class="settings-copy">Terminal detector and reproduction runs can be exported as OTLP spans after the local event is durable. Export requires both an explicit Veritas export flag and an explicit collector endpoint; export failure never changes an audit result.</p>
      <div class="settings-list">
        ${capabilityRow("Export request", requested ? badge("success", "requested") : badge("review", "disabled"), "VERITAS_OTEL_EXPORT=true opts in to export")}
        ${capabilityRow("Protocol", `<strong>${escapeHtml(observability.protocol || "otlp/http-protobuf")}</strong>`, "Exporter stays inactive until all required configuration is present")}
        ${capabilityRow("Dependencies", boolBadge(observability.dependencies_available, "installed", "optional extra missing"), "Install the observability extra only when exporting traces")}
        ${capabilityRow("Collector endpoint", boolBadge(observability.endpoint_configured, "configured", "required"), "Endpoint value is intentionally not disclosed through the API")}
        ${capabilityRow("Payload policy", observability.metadata_only ? badge("success", "metadata only") : badge("danger", "expanded"), "Raw prompts, audit titles, and evidence text stay local")}
      </div>
      <div class="settings-privacy-grid">
        <div><span>Raw prompts</span><strong>${observability.raw_prompts_exported ? "exported" : "not exported"}</strong></div>
        <div><span>Audit titles</span><strong>${observability.audit_titles_exported ? "exported" : "not exported"}</strong></div>
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

function providerMark(provider = {}) {
  const marks = {
    openai: "OAI",
    deepseek: "DS",
    anthropic: "CL",
    gemini: "GM",
    openai_compatible: "API",
  };
  return marks[provider.provider_id] || "AI";
}

function providerStateLabel(provider = {}) {
  const labels = {
    ready: "CONFIG READY",
    missing_model: "MODEL REQUIRED",
    missing_key: "KEY REQUIRED",
    missing_endpoint: "ENDPOINT REQUIRED",
    available: "STANDBY",
  };
  return labels[provider.state] || String(provider.state || "STANDBY").toUpperCase();
}

function providerEndpointLabel(provider = {}) {
  if (!provider.endpoint_configured) return "required";
  return provider.endpoint_mode === "provider_default" ? "provider default" : "configured";
}

function providerCard(provider = {}) {
  const selected = Boolean(provider.selected);
  const ready = provider.state === "ready";
  const statusClass = ready ? "ready" : selected ? "warning" : "standby";
  return `<article class="provider-node ${selected ? "selected" : ""} ${statusClass}" data-model-provider="${escapeHtml(provider.provider_id)}" data-provider-state="${escapeHtml(provider.state || "available")}" data-provider-selected="${selected}">
    <div class="provider-node-top">
      <span class="provider-mark">${escapeHtml(providerMark(provider))}</span>
      <span class="provider-link-state"><i></i>${escapeHtml(providerStateLabel(provider))}</span>
    </div>
    <div class="provider-node-name"><strong>${escapeHtml(provider.label || provider.provider_id)}</strong><span>${escapeHtml(provider.family || "Model family")}</span></div>
    <div class="provider-node-meta">
      <span><b>PROTOCOL</b>${escapeHtml(provider.api_style || "adapter")}</span>
      <span><b>AUTH</b>${provider.key_configured ? "configured" : escapeHtml(provider.api_key_env || "server env")}</span>
      <span><b>ENDPOINT</b>${escapeHtml(providerEndpointLabel(provider))}</span>
    </div>
  </article>`;
}

function modelProviderPanel(router = {}) {
  const providers = Array.isArray(router.providers) ? router.providers : [];
  const active = providers.find((provider) => provider.selected) || null;
  const ready = Boolean(router.active_ready);
  const valid = router.selection_valid !== false;
  const state = ready ? "CONFIGURED" : active ? "INCOMPLETE" : valid ? "UNBOUND" : "INVALID";
  const stateClass = ready ? "online" : active ? "degraded" : "offline";
  const configuration = router.configuration || {};
  const selectedLabel = active?.label || (router.requested_provider ? `Unsupported: ${router.requested_provider}` : "No provider selected");
  const modelLabel = router.model || "MODEL NOT PINNED";

  return `<section class="model-router" data-model-provider-matrix="true" data-model-router-state="${escapeHtml(state.toLowerCase())}">
    <div class="model-router-scan" aria-hidden="true"></div>
    <header class="model-router-head">
      <div>
        <span class="cyber-kicker">AI CONTROL PLANE // PROVIDER MATRIX</span>
        <h2>Model Router</h2>
        <p>Inspect provider configuration for replication intelligence without treating configuration readiness as network health or allowing model output to become detector evidence.</p>
      </div>
      <div class="router-state ${stateClass}"><span class="router-state-dot"></span><div><small>CONFIG STATE</small><strong>${escapeHtml(state)}</strong></div></div>
    </header>

    <div class="router-telemetry">
      <div><span>ACTIVE PROVIDER</span><strong>${escapeHtml(selectedLabel)}</strong></div>
      <div><span>MODEL ID</span><strong class="mono">${escapeHtml(modelLabel)}</strong></div>
      <div><span>TRANSPORT</span><strong>${escapeHtml(String(router.replication_transport || "acp").toUpperCase())}</strong></div>
      <div><span>SECRET POLICY</span><strong>${router.secrets_exposed ? "EXPOSED" : "SERVER-ONLY"}</strong></div>
    </div>

    <div class="router-flow" aria-label="Model execution boundary">
      <div class="router-flow-node deterministic"><small>01</small><strong>DETECTORS</strong><span>deterministic</span></div>
      <div class="router-flow-line"><i></i></div>
      <div class="router-flow-node"><small>02</small><strong>ACP AGENT</strong><span>execution boundary</span></div>
      <div class="router-flow-line active"><i></i></div>
      <div class="router-flow-node provider"><small>03</small><strong>MODEL ROUTER</strong><span>${escapeHtml(selectedLabel)}</span></div>
      <div class="router-flow-line"><i></i></div>
      <div class="router-flow-node untrusted"><small>04</small><strong>OUTPUT</strong><span>untrusted until reviewed</span></div>
    </div>

    <div class="provider-grid">${providers.map(providerCard).join("")}</div>

    <div class="router-boundary">
      <div class="router-boundary-icon">⌁</div>
      <div><strong>Evidence firewall active</strong><p>Provider credentials stay server-side. The browser cannot write provider secrets, and model output cannot directly change detector findings or verification coverage.</p></div>
      <span class="router-boundary-chip">ACP BRIDGE REQUIRED</span>
    </div>

    <div class="router-config-strip">
      <span><b>PROVIDER</b><code>${escapeHtml(configuration.provider_env || "VERITAS_MODEL_PROVIDER")}</code></span>
      <span><b>MODEL</b><code>${escapeHtml(configuration.model_env || "VERITAS_MODEL_NAME")}</code></span>
      <span><b>CUSTOM ENDPOINT</b><code>${escapeHtml(configuration.base_url_env || "VERITAS_MODEL_BASE_URL")}</code></span>
      <span><b>MODE</b><code>SERVER CONFIG / RESTART</code></span>
    </div>
  </section>`;
}

function renderSettings(caps, modelProviders) {
  return `<div class="page settings-cyber-page" data-settings-surface="true">
    <div class="page-head settings-cyber-head"><div class="page-head-copy"><span class="eyebrow">System // secure control plane</span><h1 class="page-title">Settings</h1><p class="page-subtitle">Inspect live configuration for provider routing, parser, reproduction, API, and telemetry boundaries without exposing credentials or turning model output into research evidence.</p></div><div class="page-actions"><span class="cyber-live"><i></i>LOCAL CONTROL</span></div></div>
    ${modelProviderPanel(modelProviders)}
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
  main.innerHTML = `<div class="page" data-settings-loading="true"><div class="settings-loading"><span class="status-icon running">⌁</span><strong>Synchronizing control plane…</strong></div></div>`;
  try {
    const [caps, modelProviders] = await Promise.all([fetchCapabilities(), fetchModelProviders()]);
    main.innerHTML = renderSettings(caps, modelProviders);
  } catch (error) {
    main.innerHTML = `<div class="page" data-settings-error="true"><div class="empty-state"><div class="empty-state-inner"><div class="empty-mark">!</div><h2>Settings unavailable</h2><p>${escapeHtml(error.message)}</p></div></div></div>`;
  }
}

const observer = new MutationObserver(() => {
  if (!main) return;
  const title = main.querySelector(".page-title")?.textContent?.trim();
  const settingsDom = Boolean(
    main.querySelector("[data-settings-surface]")
    || main.querySelector("[data-settings-loading]")
    || main.querySelector("[data-settings-error]")
  );
  if (title !== "Settings" && !settingsDom) {
    delete main.dataset.settingsEnhanced;
    return;
  }
  if (title === "Settings" && main.dataset.settingsEnhanced !== "true") {
    queueMicrotask(enhanceSettings);
  }
});

if (main) {
  observer.observe(main, { childList: true, subtree: true });
  queueMicrotask(enhanceSettings);
}
