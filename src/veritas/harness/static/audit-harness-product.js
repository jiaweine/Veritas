const main = document.querySelector("#main-content");
const commandDialog = document.querySelector("#command-dialog");
const commandResults = document.querySelector("#command-results");

const LAYOUT_KEY = "veritas:audit-harness:layout:v1";
const SESSION_PREFIX = "veritas:audit-harness:session:v1:";
const DRAFT_PREFIX = "veritas:audit-harness:draft:v1:";

const enhancementState = {
  auditId: "",
  restoredAuditId: "",
  restoring: false,
  selectedRunId: "",
  selectedRun: null,
  runRequestToken: 0,
};

const esc = (value = "") => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

function readJson(key, fallback = null) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function writeJson(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch {}
}

function readText(key) {
  try { return localStorage.getItem(key) || ""; } catch { return ""; }
}

function writeText(key, value) {
  try {
    if (value) localStorage.setItem(key, value);
    else localStorage.removeItem(key);
  } catch {}
}

function auditRoot() {
  return main?.querySelector("[data-audit-harness='true']") || null;
}

function activeAuditId() {
  return auditRoot()?.dataset.auditId || "";
}

function sessionKey(auditId) { return `${SESSION_PREFIX}${auditId}`; }
function draftKey(auditId) { return `${DRAFT_PREFIX}${auditId}`; }

function currentSession(auditId) {
  return readJson(sessionKey(auditId), {}) || {};
}

function saveSessionPatch(auditId, patch) {
  if (!auditId) return;
  writeJson(sessionKey(auditId), { ...currentSession(auditId), ...patch });
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function applyLayout(grid) {
  const saved = readJson(LAYOUT_KEY, {}) || {};
  const left = Number(saved.left);
  const right = Number(saved.right);
  if (Number.isFinite(left)) grid.style.setProperty("--ah-left-width", `${clamp(left, 190, 420)}px`);
  if (Number.isFinite(right)) grid.style.setProperty("--ah-right-width", `${clamp(right, 360, 760)}px`);
}

function persistLayout(grid) {
  const left = grid.querySelector(".ah-left")?.getBoundingClientRect().width;
  const right = grid.querySelector(".ah-right")?.getBoundingClientRect().width;
  if (Number.isFinite(left) && Number.isFinite(right)) writeJson(LAYOUT_KEY, { left: Math.round(left), right: Math.round(right) });
}

function attachSplitter(handle, side) {
  if (handle.dataset.bound === "true") return;
  handle.dataset.bound = "true";
  handle.addEventListener("pointerdown", (event) => {
    if (window.matchMedia("(max-width: 1120px)").matches) return;
    const grid = handle.closest(".ah-grid");
    const leftPane = grid?.querySelector(".ah-left");
    const rightPane = grid?.querySelector(".ah-right");
    if (!grid || !leftPane || !rightPane) return;
    event.preventDefault();
    handle.setPointerCapture(event.pointerId);
    document.body.classList.add("ah-resizing");
    const startX = event.clientX;
    const startLeft = leftPane.getBoundingClientRect().width;
    const startRight = rightPane.getBoundingClientRect().width;
    const gridWidth = grid.getBoundingClientRect().width;

    const move = (moveEvent) => {
      const delta = moveEvent.clientX - startX;
      if (side === "left") {
        const maxLeft = Math.max(220, Math.min(420, gridWidth - 820));
        grid.style.setProperty("--ah-left-width", `${clamp(startLeft + delta, 190, maxLeft)}px`);
      } else {
        const maxRight = Math.max(420, Math.min(760, gridWidth - 610));
        grid.style.setProperty("--ah-right-width", `${clamp(startRight - delta, 360, maxRight)}px`);
      }
    };

    const end = () => {
      document.body.classList.remove("ah-resizing");
      persistLayout(grid);
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", end);
      handle.removeEventListener("pointercancel", end);
    };

    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", end);
    handle.addEventListener("pointercancel", end);
  });
}

function ensureSplitters(root) {
  const grid = root.querySelector(".ah-grid");
  if (!grid) return;
  applyLayout(grid);
  let leftHandle = grid.querySelector("[data-ah-split='left']");
  if (!leftHandle) {
    leftHandle = document.createElement("div");
    leftHandle.className = "ah-splitter ah-splitter-left";
    leftHandle.dataset.ahSplit = "left";
    leftHandle.setAttribute("role", "separator");
    leftHandle.setAttribute("aria-label", "Resize project rail");
    leftHandle.setAttribute("aria-orientation", "vertical");
    grid.insertBefore(leftHandle, grid.querySelector(".ah-center"));
  }
  let rightHandle = grid.querySelector("[data-ah-split='right']");
  if (!rightHandle) {
    rightHandle = document.createElement("div");
    rightHandle.className = "ah-splitter ah-splitter-right";
    rightHandle.dataset.ahSplit = "right";
    rightHandle.setAttribute("role", "separator");
    rightHandle.setAttribute("aria-label", "Resize Evidence Inspector");
    rightHandle.setAttribute("aria-orientation", "vertical");
    grid.insertBefore(rightHandle, grid.querySelector(".ah-right"));
  }
  attachSplitter(leftHandle, "left");
  attachSplitter(rightHandle, "right");
}

function ensureComposerPersistence(root, auditId) {
  const input = root.querySelector("#ah-message");
  if (!input) return;
  if (!input.value && !input.disabled) input.value = readText(draftKey(auditId));
  if (input.dataset.productBound === "true") return;
  input.dataset.productBound = "true";
  input.addEventListener("input", () => writeText(draftKey(auditId), input.value));
  input.addEventListener("blur", () => writeText(draftKey(auditId), input.value));
}

function clearDraft(auditId) {
  if (auditId) writeText(draftKey(auditId), "");
}

function formatDuration(value) {
  const ms = Number(value);
  if (!Number.isFinite(ms)) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(ms < 10000 ? 2 : 1)} s`;
}

function formatTimestamp(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

function runEventCard(event) {
  const payload = event.payload || {};
  const phase = payload.phase || event.kind || "event";
  const detail = event.detail || "";
  return `<div class="ah-run-event"><span class="ah-run-event-mark ${esc(event.status || phase)}">${event.kind === "finding" ? "!" : event.kind === "assistant_message" ? "V" : event.kind === "user_message" ? "↗" : "⌁"}</span><div><strong>${esc(event.title || event.kind || "Run event")}</strong>${detail ? `<p>${esc(detail)}</p>` : ""}<small>${esc(phase)} · ${esc(formatTimestamp(event.created_at))}</small></div></div>`;
}

function runInspector(detail) {
  const counts = detail.counts || {};
  const source = detail.source || {};
  const events = Array.isArray(detail.events) ? detail.events : [];
  return `<div class="ah-run-inspector">
    <div class="ah-run-hero"><div><span>Persisted run</span><h3>${esc(detail.tool || detail.run_kind || "Audit run")}</h3><p>${esc(detail.run_id || "")}</p></div><strong class="ah-run-phase">${esc(detail.phase || detail.status || "done")}</strong></div>
    <div class="ah-run-metrics"><div><span>Duration</span><strong>${esc(formatDuration(detail.duration_ms))}</strong></div><div><span>Coverage</span><strong>${Math.round((Number(detail.coverage) || 0) * 100)}%</strong></div><div><span>Verified</span><strong>${Number(counts.verified) || 0}</strong></div><div><span>Review</span><strong>${Number(counts.needs_review) || 0}</strong></div></div>
    ${source.page ? `<button type="button" class="ah-run-source" data-ah-run-source-page="${esc(source.page)}"><span>Evidence source</span><strong>${esc(source.table || "Paper source")} · page ${esc(source.page)}</strong><em>Open source →</em></button>` : ""}
    <div class="ah-run-meta"><div><span>Started</span><strong>${esc(formatTimestamp(detail.started_at))}</strong></div><div><span>Finished</span><strong>${esc(formatTimestamp(detail.finished_at))}</strong></div><div><span>Artifact</span><code>${esc(detail.artifact_id || "—")}</code></div><div><span>Parsers</span><strong>${esc((detail.parsers || []).map((item) => typeof item === "string" ? item : item.parser_id || item.parser_family || "parser").join(" + ") || "—")}</strong></div></div>
    <div class="ah-run-trace-head"><strong>Run trace</strong><span>${events.length} events</span></div>
    <div class="ah-run-trace">${events.map(runEventCard).join("") || `<div class="ah-run-empty">No persisted events for this run.</div>`}</div>
  </div>`;
}

function ensureRunTab(root) {
  if (!enhancementState.selectedRun) return;
  const tabs = root.querySelector(".ah-tabs");
  const inspector = root.querySelector("#ah-inspector");
  if (!tabs || !inspector) return;
  let tab = tabs.querySelector("[data-ah-product-run-tab]");
  if (!tab) {
    tab = document.createElement("button");
    tab.type = "button";
    tab.dataset.ahProductRunTab = "true";
    tab.textContent = "Run";
    tabs.append(tab);
  }
  tab.addEventListener("click", () => showSelectedRun(root), { once: true });
  const session = currentSession(activeAuditId());
  if (session.tab === "run" && session.runId === enhancementState.selectedRunId) showSelectedRun(root);
}

function showSelectedRun(root = auditRoot()) {
  if (!root || !enhancementState.selectedRun) return;
  root.querySelectorAll(".ah-tabs button").forEach((node) => node.classList.remove("active"));
  const runTab = root.querySelector("[data-ah-product-run-tab]");
  if (runTab) runTab.classList.add("active");
  const inspector = root.querySelector("#ah-inspector");
  if (inspector) inspector.innerHTML = runInspector(enhancementState.selectedRun);
  const auditId = activeAuditId();
  saveSessionPatch(auditId, { tab: "run", runId: enhancementState.selectedRunId });
  const sourceButton = inspector?.querySelector("[data-ah-run-source-page]");
  if (sourceButton) sourceButton.addEventListener("click", () => openRunSource(sourceButton.dataset.ahRunSourcePage));
}

function openRunSource(page) {
  const root = auditRoot();
  if (!root) return;
  const match = [...root.querySelectorAll("[data-ah-page]")].find((node) => String(node.dataset.ahPage) === String(page));
  if (match) {
    saveSessionPatch(activeAuditId(), { page: Number(page) || 1, tab: "source" });
    match.click();
    return;
  }
  root.querySelector("[data-ah-tab='source']")?.click();
}

async function selectRun(runId) {
  const auditId = activeAuditId();
  if (!auditId || !runId) return;
  const token = ++enhancementState.runRequestToken;
  saveSessionPatch(auditId, { tab: "run", runId });
  try {
    const response = await fetch(`/api/v1/runs/${encodeURIComponent(runId)}`, { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    const detail = await response.json();
    if (token !== enhancementState.runRequestToken || auditId !== activeAuditId()) return;
    enhancementState.selectedRunId = runId;
    enhancementState.selectedRun = detail;
    const root = auditRoot();
    ensureRunTab(root);
    showSelectedRun(root);
  } catch (error) {
    console.error("Unable to inspect persisted run", error);
  }
}

function bindRunRows(root) {
  root.querySelectorAll("[data-ah-run]").forEach((node) => {
    if (node.dataset.productBound === "true") return;
    node.dataset.productBound = "true";
    node.addEventListener("click", () => selectRun(node.dataset.ahRun || ""));
  });
  ensureRunTab(root);
}

function contextualCommandMarkup(root) {
  const activeTable = root.querySelector(".ah-table-row.active");
  const table = activeTable?.dataset.ahTable || "";
  const page = activeTable?.dataset.ahPage || root.querySelector(".ah-inspector-head > span")?.textContent?.match(/p\.\s*(\d+)/)?.[1] || "";
  const auditTemplate = `/audit row=""${table ? ` table="${table}"` : ""}${page ? ` page=${page}` : ""}`;
  return `<div class="command-section-label ah-command-context" data-ah-command-context-label>Current audit</div>
    <button class="command-result ah-command-context" type="button" data-ah-context-command="/inspect" data-ah-context-send="true"><span class="command-result-icon">⌁</span><span><strong>Inspect current paper</strong><small>Run deterministic paper inspection in the active Audit Agent thread.</small></span></button>
    <button class="command-result ah-command-context" type="button" data-ah-context-command='${esc(auditTemplate)}'><span class="command-result-icon">✓</span><span><strong>Audit a regression row</strong><small>${table ? `Target ${esc(table)}${page ? ` · page ${esc(page)}` : ""}` : "Fill a row label and optional table/page locator."}</small></span></button>`;
}

function injectContextCommands() {
  const root = auditRoot();
  if (!root || !commandDialog?.open || !commandResults) return;
  commandResults.querySelectorAll(".ah-command-context").forEach((node) => node.remove());
  commandResults.insertAdjacentHTML("afterbegin", contextualCommandMarkup(root));
  commandResults.querySelectorAll("[data-ah-context-command]").forEach((node) => node.addEventListener("click", () => {
    const command = node.dataset.ahContextCommand || "";
    const sendNow = node.dataset.ahContextSend === "true";
    commandDialog.close();
    const input = auditRoot()?.querySelector("#ah-message");
    if (!input || input.disabled) return;
    input.value = command;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.focus();
    if (command.includes('row=""')) {
      const position = command.indexOf('""') + 1;
      input.setSelectionRange(position, position);
    } else if (sendNow) {
      auditRoot()?.querySelector("#ah-send")?.click();
    }
  }));
}

function persistClickState(event) {
  const root = auditRoot();
  const auditId = activeAuditId();
  if (!root || !auditId) return;
  const pageNode = event.target.closest?.("[data-ah-page]");
  if (pageNode && root.contains(pageNode)) saveSessionPatch(auditId, { page: Number(pageNode.dataset.ahPage) || 1, tab: "source" });
  const tabNode = event.target.closest?.("[data-ah-tab]");
  if (tabNode && root.contains(tabNode)) saveSessionPatch(auditId, { tab: tabNode.dataset.ahTab || "source" });
  const sendNode = event.target.closest?.("#ah-send");
  if (sendNode && root.contains(sendNode)) clearDraft(auditId);
}

function restoreSession(root, auditId) {
  if (!auditId || enhancementState.restoring || enhancementState.restoredAuditId === auditId) return;
  enhancementState.restoring = true;
  enhancementState.restoredAuditId = auditId;
  const saved = currentSession(auditId);
  const page = Number(saved.page);
  const tab = saved.tab || "source";
  const runId = saved.runId || "";
  if (Number.isFinite(page) && page > 0) {
    const pageNode = [...root.querySelectorAll("[data-ah-page]")].find((node) => Number(node.dataset.ahPage) === page);
    if (pageNode && !pageNode.classList.contains("active")) pageNode.click();
  }
  setTimeout(() => {
    enhancementState.restoring = false;
    const fresh = auditRoot();
    if (!fresh || activeAuditId() !== auditId) return;
    if (tab === "run" && runId) selectRun(runId);
    else if (tab !== "source") fresh.querySelector(`[data-ah-tab="${CSS.escape(tab)}"]`)?.click();
  }, 0);
}

function ensureKeyboardHints(root) {
  const row = root.querySelector(".ah-command-row");
  if (row && !row.querySelector("[data-ah-shortcut-hint]")) {
    const hint = document.createElement("span");
    hint.dataset.ahShortcutHint = "true";
    hint.className = "ah-shortcut-hint";
    hint.textContent = "⌘/Ctrl J focus · ⌘/Ctrl K commands";
    row.append(hint);
  }
}

function enhance() {
  const root = auditRoot();
  if (!root) {
    enhancementState.auditId = "";
    enhancementState.restoredAuditId = "";
    enhancementState.selectedRunId = "";
    enhancementState.selectedRun = null;
    return;
  }
  const auditId = activeAuditId();
  if (enhancementState.auditId && enhancementState.auditId !== auditId) {
    enhancementState.restoredAuditId = "";
    enhancementState.selectedRunId = "";
    enhancementState.selectedRun = null;
  }
  enhancementState.auditId = auditId;
  ensureSplitters(root);
  ensureComposerPersistence(root, auditId);
  bindRunRows(root);
  ensureKeyboardHints(root);
  restoreSession(root, auditId);
  injectContextCommands();
}

const mainObserver = new MutationObserver(() => queueMicrotask(enhance));
if (main) mainObserver.observe(main, { childList: true });
if (commandDialog) new MutationObserver(() => queueMicrotask(injectContextCommands)).observe(commandDialog, { attributes: true, attributeFilter: ["open"] });
if (commandResults) new MutationObserver(() => {
  if (!commandResults.querySelector(".ah-command-context")) queueMicrotask(injectContextCommands);
}).observe(commandResults, { childList: true });

document.addEventListener("click", persistClickState, true);
document.addEventListener("keydown", (event) => {
  const root = auditRoot();
  if (!root) return;
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "j") {
    event.preventDefault();
    root.querySelector("#ah-message")?.focus();
    return;
  }
  if ((event.metaKey || event.ctrlKey) && event.key === "Enter" && event.target?.id === "ah-message") clearDraft(activeAuditId());
});

enhance();
