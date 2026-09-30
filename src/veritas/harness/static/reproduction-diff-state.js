const main = document.querySelector("#main-content");
const diffStateCache = new Map();
let enhanceTimer = null;

function formatBound(value) {
  const bytes = Number(value) || 0;
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(bytes % (1024 * 1024) ? 1 : 0)} MiB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(bytes % 1024 ? 1 : 0)} KiB`;
  return `${bytes} B`;
}

function selectedRunId() {
  return document.querySelector(".rep-run-row.selected[data-run-id]")?.dataset.runId || "";
}

function activeFilePath() {
  return document.querySelector(".rep-file-detail-head strong")?.textContent?.trim() || "";
}

function changedFile(value) {
  return ["created", "modified", "deleted"].includes(String(value || ""));
}

function baselineCopy(file) {
  if (file.diff_baseline === "immutable_source") {
    return "Compared with the immutable source copy held in the audit store.";
  }
  if (file.diff_baseline === "empty") {
    return "Compared with an empty baseline because this file was created during the run.";
  }
  return "Compared only within the server-declared bounded workspace diff contract.";
}

function unavailableCopy(file) {
  const inputLimit = formatBound(file.diff_input_limit_bytes);
  const outputLimit = formatBound(file.diff_output_limit_bytes);
  const reason = String(file.diff_reason || "diff_unavailable");
  const messages = {
    current_too_large: `The current workspace file exceeds the ${inputLimit} comparison limit. Veritas will not present a partial diff as complete.`,
    baseline_too_large: `The immutable baseline exceeds the ${inputLimit} comparison limit. Veritas will not present a partial diff as complete.`,
    diff_too_large: `The rendered unified diff would exceed the ${outputLimit} output limit, so the comparison is withheld rather than truncated into a misleading diff.`,
    current_binary: "The current workspace file is binary, so Veritas does not decode it into a text diff.",
    baseline_binary: "The immutable baseline is binary, so Veritas does not decode it into a text diff.",
    current_non_utf8: "The current workspace file is not valid UTF-8 text, so a text diff is unavailable.",
    baseline_non_utf8: "The immutable baseline is not valid UTF-8 text, so a text diff is unavailable.",
    baseline_unavailable: "A trusted immutable baseline is not available for this changed file.",
    unsupported_change_type: "This workspace object type is intentionally excluded from text diff rendering.",
    unchanged: "This staged file is unchanged, so no diff is required.",
  };
  return messages[reason] || `The server declined to render a complete text diff (${reason.replaceAll("_", " ")}).`;
}

function buildDiffState(file) {
  if (!changedFile(file.change)) return null;
  const available = Boolean(file.diff_available);
  const panel = document.createElement("div");
  panel.className = `rep-diff-state ${available ? "available" : "unavailable"}`;
  panel.dataset.repDiffState = "true";
  panel.dataset.repDiffAvailable = String(available);
  panel.dataset.repDiffReason = String(file.diff_reason || "");
  panel.dataset.repDiffBaseline = String(file.diff_baseline || "");

  const kicker = document.createElement("span");
  kicker.className = "rep-diff-kicker";
  kicker.textContent = "BOUNDED WORKSPACE COMPARISON";

  const title = document.createElement("strong");
  title.textContent = available ? "Unified diff available" : "Diff unavailable";

  const copy = document.createElement("p");
  copy.textContent = available ? baselineCopy(file) : unavailableCopy(file);

  const meta = document.createElement("small");
  meta.textContent = `Comparison ≤ ${formatBound(file.diff_input_limit_bytes)} per side · rendered diff ≤ ${formatBound(file.diff_output_limit_bytes)} · generated outputs remain untrusted`;

  panel.append(kicker, title, copy, meta);
  return panel;
}

function decorateDiff(code, diff) {
  if (!code || !diff) return;
  const lines = String(diff).split("\n");
  const fragment = document.createDocumentFragment();
  lines.forEach((line, index) => {
    const span = document.createElement("span");
    span.className = "rep-diff-line";
    if (line.startsWith("@@")) span.classList.add("hunk");
    else if (line.startsWith("+++ ") || line.startsWith("--- ")) span.classList.add("header");
    else if (line.startsWith("+")) span.classList.add("add");
    else if (line.startsWith("-")) span.classList.add("remove");
    else span.classList.add("context");
    span.textContent = line + (index < lines.length - 1 ? "\n" : "");
    fragment.append(span);
  });
  code.replaceChildren(fragment);
  code.dataset.repDiffRendered = "true";
}

async function loadDiffState(runId, path) {
  const key = `${runId}:${path}`;
  if (!diffStateCache.has(key)) {
    diffStateCache.set(
      key,
      fetch(`/api/v1/runs/${encodeURIComponent(runId)}/workspace/file?path=${encodeURIComponent(path)}`, {
        headers: { Accept: "application/json" },
        cache: "no-store",
      }).then(async (response) => {
        if (!response.ok) throw new Error(`workspace diff state unavailable: ${response.status}`);
        return response.json();
      }),
    );
  }
  try {
    return await diffStateCache.get(key);
  } catch (error) {
    diffStateCache.delete(key);
    throw error;
  }
}

async function enhanceFileDetail() {
  const detail = document.querySelector(".rep-file-detail");
  if (!detail) return;
  const runId = selectedRunId();
  const path = activeFilePath();
  if (!runId || !path) return;
  const key = `${runId}:${path}`;
  if (detail.dataset.repDiffStateKey === key) return;
  detail.dataset.repDiffStateKey = key;

  let file;
  try {
    file = await loadDiffState(runId, path);
  } catch {
    delete detail.dataset.repDiffStateKey;
    return;
  }

  if (selectedRunId() !== runId || activeFilePath() !== path) return;
  const current = document.querySelector(".rep-file-detail");
  if (!current || current !== detail) return;

  current.querySelector("[data-rep-diff-state='true']")?.remove();
  const state = buildDiffState(file);
  const head = current.querySelector(".rep-file-detail-head");
  if (state && head) head.insertAdjacentElement("afterend", state);

  const code = current.querySelector(".rep-code.diff");
  if (file.diff_available && file.diff && code) decorateDiff(code, file.diff);

  const truncated = current.querySelector(".rep-truncated");
  if (file.truncated && truncated) {
    truncated.dataset.repPreviewTruncated = "true";
    truncated.textContent = `Preview capped at ${formatBound(file.diff_input_limit_bytes)}; content below is incomplete.`;
  }
}

function scheduleEnhancement() {
  clearTimeout(enhanceTimer);
  enhanceTimer = setTimeout(() => { void enhanceFileDetail(); }, 0);
}

if (main) {
  const observer = new MutationObserver(scheduleEnhancement);
  observer.observe(main, { childList: true, subtree: true });
  document.addEventListener("click", (event) => {
    if (event.target.closest?.("[data-workspace-file], #rep-file-back, [data-run-id]")) {
      scheduleEnhancement();
    }
  });
  scheduleEnhancement();
}
