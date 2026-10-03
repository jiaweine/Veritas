const main = document.querySelector("#main-content");

const annotationState = {
  auditId: "",
  findingId: "",
  requestToken: 0,
  queued: false,
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

async function requestClaimGraph(auditId) {
  const response = await fetch(`/api/v1/audits/${encodeURIComponent(auditId)}/claim-graph`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

function openEvidence(root, nodeElement) {
  const page = String(nodeElement.dataset.cgPage || "");
  const pageButton = [...root.querySelectorAll("[data-ah-page]")]
    .find((candidate) => String(candidate.dataset.ahPage) === page);
  if (pageButton) pageButton.click();
  else root.querySelector(".ah-tabs [data-ah-tab='source']")?.click();
  const field = nodeElement.dataset.cgField || "";
  if (field) {
    window.setTimeout(() => {
      window.dispatchEvent(new CustomEvent("veritas:evidence-field", { detail: { field } }));
    }, 80);
  }
}

function openFinding(root, findingId) {
  root.querySelector(".ah-tabs [data-ah-tab='findings']")?.click();
  window.setTimeout(() => {
    window.dispatchEvent(new CustomEvent("veritas:finding-select", { detail: { findingId } }));
  }, 80);
}

function decorateFinding(root, annotation) {
  const graph = root.querySelector("[data-reference-claim-graph='true'][data-cg-state='available']");
  if (!graph || !annotation?.field || !annotation?.finding_id) return false;
  const nodeElement = graph.querySelector(`[data-cg-field="${CSS.escape(annotation.field)}"]`);
  const panel = graph.querySelector("[data-cg-detail-panel='true']");
  if (!nodeElement || !panel) return false;

  graph.querySelectorAll("[data-cg-node]").forEach((candidate) => {
    const selected = candidate === nodeElement;
    candidate.classList.toggle("is-selected", selected);
    if (selected) candidate.setAttribute("aria-current", "true");
    else candidate.removeAttribute("aria-current");
  });
  nodeElement.dataset.cgFindingId = annotation.finding_id;
  nodeElement.dataset.cgFindingAnnotation = "true";

  const value = nodeElement.dataset.cgValue || "";
  const title = annotation.finding_title || "Detector finding";
  const explanation = annotation.explanation || "Detector annotation linked to this persisted field.";
  panel.innerHTML = `<div class="cg-detail-copy">
    <span class="cg-detail-kicker">Detector annotation</span>
    <div class="cg-detail-head"><strong>${esc(title)}</strong>${value ? `<em>${esc(value)}</em>` : ""}</div>
    <small>Navigation annotation only · graph_edge=false</small>
    <p>${esc(explanation)}</p>
  </div>
  <div class="cg-detail-actions">
    <div>
      <button type="button" data-cg-detail-source="true">Open evidence <span>→</span></button>
      <button type="button" class="primary" data-cg-detail-action="findings">Open linked finding <span>→</span></button>
    </div>
    <span>Detector annotations never become ClaimEdges</span>
  </div>`;
  panel.querySelector("[data-cg-detail-source]")?.addEventListener("click", () => openEvidence(root, nodeElement));
  panel.querySelector("[data-cg-detail-action='findings']")?.addEventListener("click", () => openFinding(root, annotation.finding_id));
  return true;
}

async function applyPendingAnnotation() {
  annotationState.queued = false;
  const root = auditRoot();
  if (!root || !annotationState.findingId) return;
  const auditId = String(root.dataset.auditId || "");
  if (!auditId || (annotationState.auditId && annotationState.auditId !== auditId)) return;
  if (!root.querySelector("[data-reference-claim-graph='true'][data-cg-state='available']")) return;

  const token = ++annotationState.requestToken;
  try {
    const payload = await requestClaimGraph(auditId);
    if (token !== annotationState.requestToken) return;
    if (payload?.authority?.detector_annotations_are_graph_edges !== false) {
      throw new Error("claim graph annotation authority contract missing");
    }
    const annotation = (payload.annotations || [])
      .find((item) => String(item?.finding_id || "") === annotationState.findingId);
    if (!annotation || annotation.graph_edge !== false) return;
    const freshRoot = auditRoot();
    if (!freshRoot || freshRoot.dataset.auditId !== auditId) return;
    decorateFinding(freshRoot, annotation);
  } catch (error) {
    console.error("Unable to bind detector annotation to Claim Graph", error);
  }
}

function queueApply() {
  if (annotationState.queued) return;
  annotationState.queued = true;
  queueMicrotask(applyPendingAnnotation);
}

window.addEventListener("veritas:claim-finding", (event) => {
  const root = auditRoot();
  const findingId = String(event.detail?.findingId || "");
  const auditId = String(event.detail?.auditId || root?.dataset.auditId || "");
  if (!root || !findingId || (auditId && auditId !== root.dataset.auditId)) return;
  annotationState.auditId = auditId;
  annotationState.findingId = findingId;
  annotationState.requestToken += 1;
  const tab = root.querySelector("[data-reference-claim-tab]");
  if (tab) tab.click();
  queueApply();
});

window.addEventListener("veritas:finding-select", (event) => {
  const findingId = String(event.detail?.findingId || "");
  if (findingId) annotationState.findingId = findingId;
});

const observer = new MutationObserver(queueApply);
if (main) observer.observe(main, { childList: true, subtree: true });
