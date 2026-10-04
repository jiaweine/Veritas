const dialog = document.querySelector("#command-dialog");
const trigger = document.querySelector("#command-trigger");
const originalInput = document.querySelector("#command-input");
const results = document.querySelector("#command-results");
const SEARCH_DEBOUNCE_MS = 160;

let input = originalInput;
let commandItems = [];
let commandIndex = 0;
let searchSequence = 0;
let searchTimer = 0;
let searchController = null;
let lastQuery = "";
let lastError = "";

const esc = (value = "") => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

function auditHead() {
  const items = window.__veritasAuditPageFeed?.items;
  return Array.isArray(items) ? items.slice(0, 5) : [];
}

function commandDefaults() {
  return [
    { kind: "view", id: "overview", title: "Overview", detail: "Research audit cockpit", icon: "⌂" },
    { kind: "view", id: "audits", title: "Audits", detail: "Papers and evidence workspaces", icon: "▤" },
    { kind: "view", id: "findings", title: "Findings", detail: "Contradictions requiring review", icon: "◇" },
    { kind: "view", id: "runs", title: "Agent runs", detail: "Tool traces and evidence outcomes", icon: "⌁" },
    ...auditHead().map((audit) => ({
      kind: "audit",
      id: audit.audit_id,
      audit_id: audit.audit_id,
      title: audit.title || "Untitled audit",
      detail: audit.filename || audit.audit_id,
      icon: "V",
    })),
  ];
}

function localViewMatches(query) {
  const needle = query.toLocaleLowerCase();
  return commandDefaults().filter((item) => (
    item.kind === "view"
    && `${item.title} ${item.detail}`.toLocaleLowerCase().includes(needle)
  ));
}

function normalizeRemote(items) {
  if (!Array.isArray(items)) return [];
  return items.filter((item) => item && item.id).map((item) => ({
    kind: item.kind || "event",
    id: item.id,
    audit_id: item.audit_id || null,
    title: item.title || "Result",
    detail: item.detail || item.kind || "",
    icon: item.kind === "audit" ? "V" : item.kind === "finding" ? "◇" : "·",
  }));
}

function dedupeItems(items) {
  const seen = new Set();
  return items.filter((item) => {
    const key = `${item.kind}:${item.id}:${item.audit_id || ""}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function render({ busy = false } = {}) {
  if (!results) return;
  const busyMarkup = busy
    ? `<div class="command-section-label" data-command-search-status="loading">Searching authoritative workspace…</div>`
    : `<div class="command-section-label">Navigate & search</div>`;
  const itemMarkup = commandItems.length
    ? commandItems.map((item, index) => `<button class="command-result ${index === commandIndex ? "selected" : ""}" data-command-search-index="${index}"><span class="command-result-icon">${esc(item.icon || "·")}</span><span><strong>${esc(item.title || "Result")}</strong><small>${esc(item.detail || item.kind || "")}</small></span></button>`).join("")
    : `<div class="empty-state" style="min-height:150px"><div class="empty-state-inner"><p>No matching papers, findings, or runs.</p></div></div>`;
  const errorMarkup = lastError
    ? `<div class="command-search-error" role="status" data-command-search-error="true"><span>Workspace search unavailable: ${esc(lastError)}</span><button type="button" class="panel-link" data-command-search-retry="true">Retry</button></div>`
    : "";
  results.innerHTML = `${busyMarkup}${itemMarkup}${errorMarkup}`;
  results.setAttribute("aria-busy", String(busy));
  results.querySelectorAll("[data-command-search-index]").forEach((node) => {
    node.addEventListener("click", () => activate(Number(node.dataset.commandSearchIndex)));
  });
  results.querySelector("[data-command-search-retry]")?.addEventListener("click", () => {
    scheduleSearch(lastQuery, { immediate: true });
  });
}

function openAudit(auditId) {
  if (!auditId) return;
  const target = new URL(window.location.href);
  target.searchParams.set("audit_open", auditId);
  target.hash = `audit=${encodeURIComponent(auditId)}`;
  window.location.assign(target.toString());
}

function activate(index = commandIndex) {
  const item = commandItems[index];
  if (!item) return;
  dialog?.close();
  if (item.kind === "view") {
    const target = document.querySelector(`[data-view="${CSS.escape(item.id)}"]`);
    target?.click();
    return;
  }
  const auditId = item.audit_id || (item.kind === "audit" ? item.id : null);
  if (auditId) openAudit(String(auditId));
}

function cancelPending() {
  searchSequence += 1;
  if (searchTimer) {
    clearTimeout(searchTimer);
    searchTimer = 0;
  }
  if (searchController) {
    searchController.abort();
    searchController = null;
  }
}

async function executeSearch(query, sequence, local) {
  const controller = new AbortController();
  searchController = controller;
  try {
    const url = new URL("/api/v1/search", window.location.origin);
    url.searchParams.set("q", query);
    url.searchParams.set("limit", "12");
    const response = await fetch(url.toString(), {
      headers: { Accept: "application/json" },
      cache: "no-store",
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    const remote = normalizeRemote(await response.json());
    if (sequence !== searchSequence || input?.value.trim() !== query) return;
    commandItems = dedupeItems([...local, ...remote]);
    commandIndex = 0;
    lastError = "";
    render();
  } catch (error) {
    if (error?.name === "AbortError") return;
    if (sequence !== searchSequence || input?.value.trim() !== query) return;
    commandItems = local;
    commandIndex = 0;
    lastError = error?.message || "request failed";
    render();
  } finally {
    if (sequence === searchSequence) searchController = null;
  }
}

function scheduleSearch(value, { immediate = false } = {}) {
  const query = String(value || "").trim();
  cancelPending();
  const sequence = searchSequence;
  lastQuery = query;
  lastError = "";
  commandIndex = 0;

  if (!query) {
    commandItems = commandDefaults();
    render();
    return;
  }

  const local = localViewMatches(query);
  commandItems = local;
  render({ busy: true });
  searchTimer = window.setTimeout(() => {
    searchTimer = 0;
    executeSearch(query, sequence, local);
  }, immediate ? 0 : SEARCH_DEBOUNCE_MS);
}

function resetPalette() {
  cancelPending();
  lastQuery = "";
  lastError = "";
  commandIndex = 0;
  commandItems = commandDefaults();
  if (input) input.value = "";
  render();
  window.setTimeout(() => input?.focus(), 0);
}

function bindInput() {
  if (!originalInput || !dialog || !results) return;
  const replacement = originalInput.cloneNode(true);
  originalInput.replaceWith(replacement);
  input = replacement;

  input.addEventListener("input", (event) => scheduleSearch(event.target.value));
  input.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      commandIndex = Math.min(Math.max(commandItems.length - 1, 0), commandIndex + 1);
      render();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      commandIndex = Math.max(0, commandIndex - 1);
      render();
    } else if (event.key === "Enter") {
      event.preventDefault();
      activate();
    } else if (event.key === "Escape") {
      cancelPending();
      dialog.close();
    }
  });

  dialog.addEventListener("close", cancelPending);
  new MutationObserver(() => {
    if (dialog.open) resetPalette();
  }).observe(dialog, { attributes: true, attributeFilter: ["open"] });

  trigger?.addEventListener("click", () => queueMicrotask(() => {
    if (dialog.open) resetPalette();
  }));
  document.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      queueMicrotask(() => {
        if (dialog.open) resetPalette();
      });
    }
  });
}

bindInput();
