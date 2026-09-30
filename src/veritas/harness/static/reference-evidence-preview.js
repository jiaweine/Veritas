const main = document.querySelector("#main-content");

const previewState = {
  requestToken: 0,
  queued: false,
  selectedField: "",
};

const esc = (value = "") => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

function auditRoot() {
  return main?.querySelector("[data-audit-harness='true']") || null;
}

function pageFromFrame(frame) {
  if (!frame) return null;
  const source = frame.getAttribute("src") || "";
  const match = source.match(/#page=(\d+)/);
  return match ? Number(match[1]) : 1;
}

function cleanTableLabel(value = "") {
  return String(value)
    .replace(/\s*\[native-table:[^\]]+\]\s*/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
}

async function requestAudit(auditId) {
  const response = await fetch(`/api/v1/audits/${encodeURIComponent(auditId)}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

function previewMarkup(audit) {
  const result = audit?.latest_result || null;
  const consensus = result?.consensus || {};
  const source = result?.source || {};
  if (!result || consensus.beta == null || consensus.se == null || consensus.t_stat == null) return "";

  const parserFamilies = new Set(
    Object.values(result.fields || {})
      .flatMap((candidates) => Array.isArray(candidates) ? candidates : [])
      .map((candidate) => candidate?.parser_family)
      .filter(Boolean)
  );
  const table = cleanTableLabel(source.table || result.locator?.table_label || "Located regression table");
  const row = result.row_label || source.row || "Selected row";
  const distribution = consensus.inference_distribution && consensus.inference_distribution !== "unknown"
    ? consensus.inference_distribution
    : "reported statistic";

  return `<section class="ref-evidence-preview" data-reference-evidence-preview="true">
    <div class="ref-preview-stage">
      <article class="ref-paper-sheet">
        <header class="ref-paper-heading">
          <strong>${esc(table)}</strong>
          <span>Evidence extraction · page ${esc(source.page || 1)}</span>
        </header>
        <div class="ref-paper-rule"></div>
        <div class="ref-paper-subhead"><span>Reported regression result</span><em>${parserFamilies.size || 0} parser families agree</em></div>
        <div class="ref-paper-table" role="table" aria-label="Evidence extraction preview">
          <div class="ref-paper-tr ref-paper-th" role="row"><span>Variable</span><span>Estimate</span><span>Std. Error</span><span>Test stat</span><span>p-value</span></div>
          <div class="ref-paper-tr" role="row"><strong>${esc(row)}</strong><mark data-ref-field="beta">${esc(consensus.beta)}</mark><span data-ref-field="se">${esc(consensus.se)}</span><span data-ref-field="t_stat">${esc(consensus.t_stat)}</span><span data-ref-field="p_value">${esc(consensus.p_value ?? "—")}</span></div>
        </div>
        <div class="ref-paper-rule"></div>
        <p class="ref-paper-note">Source-bound preview from the persisted detector result. Inference: ${esc(distribution)}. Open the original PDF above for the immutable page artifact.</p>
      </article>
    </div>
  </section>`;
}

function applyFieldSelection(field = previewState.selectedField) {
  previewState.selectedField = field || "";
  const pane = auditRoot()?.querySelector(".ah-source-pane");
  if (!pane) return;
  pane.querySelectorAll("[data-ref-field]").forEach((node) => {
    const selected = Boolean(field) && node.dataset.refField === field;
    node.classList.toggle("is-linked-selection", selected);
    if (selected) node.setAttribute("aria-current", "true");
    else node.removeAttribute("aria-current");
  });
  const selected = field ? pane.querySelector(`[data-ref-field="${CSS.escape(field)}"]`) : null;
  selected?.scrollIntoView({ block: "center", inline: "center", behavior: "smooth" });
}

async function ensurePreview() {
  previewState.queued = false;
  const root = auditRoot();
  const pane = root?.querySelector(".ah-source-pane");
  const frame = pane?.querySelector("#ah-pdf");
  if (!root || !pane || !frame) return;
  if (pane.querySelector("[data-reference-evidence-preview]")) {
    applyFieldSelection();
    return;
  }

  const auditId = root.dataset.auditId || "";
  if (!auditId) return;
  const token = ++previewState.requestToken;
  try {
    const audit = await requestAudit(auditId);
    if (token !== previewState.requestToken) return;
    const resultPage = Number(audit?.latest_result?.source?.page || 1);
    if (pageFromFrame(frame) !== resultPage) return;
    const markup = previewMarkup(audit);
    if (!markup) return;
    const freshRoot = auditRoot();
    const freshPane = freshRoot?.querySelector(".ah-source-pane");
    if (!freshRoot || freshRoot.dataset.auditId !== auditId || !freshPane || freshPane.querySelector("[data-reference-evidence-preview]")) return;
    freshPane.querySelector(".ah-pdf-bar")?.insertAdjacentHTML("afterend", markup);
    applyFieldSelection();
  } catch (error) {
    console.error("Unable to render evidence extraction preview", error);
  }
}

function queuePreview() {
  if (previewState.queued) return;
  previewState.queued = true;
  queueMicrotask(ensurePreview);
}

window.addEventListener("veritas:evidence-field", (event) => {
  const field = String(event.detail?.field || "");
  previewState.selectedField = field;
  applyFieldSelection(field);
  if (field) window.setTimeout(() => applyFieldSelection(field), 120);
});

document.addEventListener("click", (event) => {
  const target = event.target instanceof Element ? event.target.closest("[data-ah-page], [data-ah-tab='source']") : null;
  if (!target || !auditRoot()?.contains(target)) return;
  previewState.selectedField = "";
  applyFieldSelection("");
}, true);

window.addEventListener("hashchange", () => {
  previewState.selectedField = "";
});

const observer = new MutationObserver(queuePreview);
if (main) observer.observe(main, { childList: true, subtree: true });
queuePreview();
