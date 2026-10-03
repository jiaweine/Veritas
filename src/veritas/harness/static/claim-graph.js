const main = document.querySelector("#main-content");

const graphState = {
  auditId: "",
  active: false,
  queued: false,
  rendering: false,
  requestToken: 0,
  selectedNodeId: "",
};

const GRAPH_WIDTH = 640;
const NODE_WIDTH = 190;
const NODE_HEIGHT = 64;

const esc = (value = "") => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

function auditRoot() {
  return main?.querySelector("[data-audit-harness='true']") || null;
}

function inspectorTab(root, name) {
  return root?.querySelector(`.ah-tabs [data-ah-tab="${CSS.escape(name)}"]`) || null;
}

function truncate(value, length = 24) {
  const text = String(value ?? "");
  return text.length > length ? `${text.slice(0, Math.max(1, length - 1))}…` : text;
}

function sourceLabel(source = {}) {
  const table = String(source.table || "")
    .replace(/\s*\[[^\]]+\]\s*/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  const page = Number(source.page || 0);
  if (table && page) return `${truncate(table, 20)} · p.${page}`;
  if (table) return truncate(table, 26);
  if (page) return `Paper source · p.${page}`;
  return source.artifact_id || "Persisted paper artifact";
}

function fieldLabel(name) {
  return {
    beta: "Estimate",
    se: "Std. Error",
    t_stat: "Test statistic",
    p_value: "p-value",
    ci_lower: "CI lower",
    ci_upper: "CI upper",
  }[name] || name.replaceAll("_", " ");
}

async function requestClaimGraph(auditId) {
  const response = await fetch(`/api/v1/audits/${encodeURIComponent(auditId)}/claim-graph`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

function node({
  id,
  x,
  y,
  title,
  value = "",
  kind = "neutral",
  field = "",
  page = "",
  detail = "",
  meta = "",
}) {
  const attrs = [
    `data-cg-node="${esc(id)}"`,
    `data-cg-title="${esc(title)}"`,
    `data-cg-value="${esc(value)}"`,
    `data-cg-detail="${esc(detail)}"`,
    `data-cg-meta="${esc(meta)}"`,
    field ? `data-cg-field="${esc(field)}"` : "",
    page ? `data-cg-page="${esc(page)}"` : "",
    'data-cg-action="source"',
    'tabindex="0"',
    'role="button"',
    `aria-label="${esc(`${title}${value ? `: ${value}` : ""}`)}"`,
  ].filter(Boolean).join(" ");
  return `<g class="cg-node cg-${esc(kind)}" transform="translate(${x} ${y})" ${attrs}>
    <rect width="${NODE_WIDTH}" height="${NODE_HEIGHT}" rx="10"></rect>
    <text class="cg-node-title" x="14" y="23">${esc(truncate(title, 29))}</text>
    ${value ? `<text class="cg-node-value" x="14" y="46">${esc(truncate(value, 27))}</text>` : ""}
  </g>`;
}

function persistedEdge(sourcePosition, targetPosition, relation) {
  const x1 = sourcePosition.x + NODE_WIDTH / 2;
  const y1 = sourcePosition.y + NODE_HEIGHT;
  const x2 = targetPosition.x + NODE_WIDTH / 2;
  const y2 = targetPosition.y;
  const midY = (y1 + y2) / 2;
  return `<g class="cg-edge" data-cg-persisted-edge="true">
    <path d="M ${x1} ${y1} C ${x1} ${midY}, ${x2} ${midY}, ${x2} ${y2}" marker-end="url(#cg-arrow)"></path>
    <text x="${(x1 + x2) / 2}" y="${midY - 7}">${esc(relation)}</text>
  </g>`;
}

function unavailableMarkup(payload) {
  const reason = payload?.reason
    || "No validated persisted StatisticalClaimGraph is available for this audit.";
  return `<div class="cg-empty" data-reference-claim-graph="true" data-cg-state="${esc(payload?.state || "unavailable")}">
    <span>◇</span>
    <strong>Claim graph unavailable</strong>
    <p>${esc(reason)}</p>
    <small>Veritas does not infer publication claims or claim-object edges from detector checks and findings.</small>
  </div>`;
}

function graphMarkup(payload) {
  if (!payload?.available || !payload.graph) return unavailableMarkup(payload);
  const graph = payload.graph;
  const objects = Object.values(graph.objects || {});
  const claims = Object.values(graph.claims || {});
  const persistedEdges = Array.isArray(graph.edges) ? graph.edges : [];
  const object = objects[0] || null;
  if (!object) {
    return `<div class="cg-empty" data-reference-claim-graph="true" data-cg-state="empty">
      <span>◇</span><strong>Validated graph has no statistical objects</strong>
      <p>The persisted StatisticalClaimGraph passed schema validation, but there is no detector object to inspect.</p>
    </div>`;
  }

  const claim = claims[0] || null;
  const source = object.source || {};
  const row = source.row || object.object_id || "Statistical object";
  const fields = Object.entries(object.fields || {})
    .filter(([name]) => ["beta", "se", "t_stat", "p_value", "ci_lower", "ci_upper"].includes(name))
    .slice(0, 4);
  const sourcePosition = { x: 225, y: 24 };
  const claimPosition = claim ? { x: 225, y: 126 } : null;
  const objectPosition = { x: 225, y: claim ? 228 : 132 };
  const fieldPositions = claim
    ? [
        { x: 38, y: 370 },
        { x: 412, y: 370 },
        { x: 38, y: 468 },
        { x: 412, y: 468 },
      ]
    : [
        { x: 38, y: 278 },
        { x: 412, y: 278 },
        { x: 38, y: 386 },
        { x: 412, y: 386 },
      ];
  const nodes = [];
  const graphPositions = new Map([[object.object_id, objectPosition]]);

  nodes.push(node({
    id: `artifact:${source.artifact_id || "paper"}`,
    ...sourcePosition,
    title: "Evidence source",
    value: sourceLabel(source),
    kind: "source",
    page: source.page || "",
    detail: "Persisted source address referenced by the StatisticalObjectNode. It is shown as provenance and is not rendered as a ClaimEdge.",
    meta: source.artifact_id || "paper artifact",
  }));

  if (claim && claimPosition) {
    graphPositions.set(claim.claim_id, claimPosition);
    nodes.push(node({
      id: claim.claim_id,
      ...claimPosition,
      title: claim.text || claim.claim_id,
      value: claim.role || "Publication claim",
      kind: "neutral",
      page: claim.source?.page || "",
      detail: "Persisted ClaimNode. Any semantic line attached to this node must come from graph.edges.",
      meta: claim.estimand || sourceLabel(claim.source || {}),
    }));
  }

  nodes.push(node({
    id: object.object_id,
    ...objectPosition,
    title: row,
    value: object.object_type || "Statistical object",
    kind: "metric",
    page: source.page || "",
    detail: "Validated StatisticalObjectNode from the persisted StatisticalClaimGraph.",
    meta: `${Object.keys(object.fields || {}).length} persisted fields`,
  }));

  fields.forEach(([name, field], index) => {
    const position = fieldPositions[index];
    const fieldSource = field?.source || source;
    const value = field?.raw ?? field?.value ?? "";
    nodes.push(node({
      id: `${object.object_id}:${name}`,
      ...position,
      title: fieldLabel(name),
      value,
      kind: "metric",
      field: name,
      page: fieldSource.page || source.page || "",
      detail: "Source-addressable ExtractedField persisted inside the StatisticalClaimGraph. Fields are nested object provenance, not standalone ClaimEdges.",
      meta: sourceLabel(fieldSource),
    }));
  });

  const semanticEdges = persistedEdges.flatMap((item) => {
    const sourcePositionForEdge = graphPositions.get(item.source_id);
    const targetPositionForEdge = graphPositions.get(item.target_id);
    if (!sourcePositionForEdge || !targetPositionForEdge) return [];
    return [persistedEdge(sourcePositionForEdge, targetPositionForEdge, item.relation || "related")];
  });
  const claimBound = payload.authority?.publication_claim_bound === true;
  const claimSummary = claimBound
    ? `${claims.length} persisted publication claim${claims.length === 1 ? "" : "s"} · ${persistedEdges.length} persisted claim edge${persistedEdges.length === 1 ? "" : "s"}`
    : "No publication claim identity bound · no claim edge inferred";
  const reconstruction = payload.reconstruction?.[object.object_id];
  const reconstructionSummary = reconstruction?.available
    ? "parser-independent reconstruction available"
    : `reconstruction withheld${reconstruction?.reason ? ` · ${reconstruction.reason}` : ""}`;
  const height = claim ? 580 : 500;

  return `<section class="claim-graph" data-reference-claim-graph="true" data-cg-state="available">
    <div class="cg-toolbar">
      <div><strong>Claim Graph</strong><small>Validated persisted StatisticalClaimGraph</small></div>
      <div class="cg-legend"><span><i class="source"></i>provenance</span><span><i class="metric"></i>graph object / field</span></div>
    </div>
    <div class="cg-authority" data-cg-authority="true"><strong>${claimBound ? "Persisted claim identity" : "No publication claim identity bound"}</strong><span>${esc(claimSummary)}</span></div>
    <div class="cg-canvas" role="region" aria-label="Persisted statistical claim graph">
      <svg viewBox="0 0 ${GRAPH_WIDTH} ${height}" role="img" aria-label="Statistical graph for ${esc(row)}">
        <defs><marker id="cg-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z"></path></marker></defs>
        ${semanticEdges.join("")}
        ${nodes.join("")}
      </svg>
    </div>
    <aside class="cg-detail" data-cg-detail-panel="true" aria-live="polite">
      <div class="cg-detail-empty"><strong>Select a graph node</strong><span>Inspect persisted provenance without inventing claim semantics.</span></div>
    </aside>
    <div class="cg-foot"><span>${esc(claimSummary)}</span><span>${esc(reconstructionSummary)}</span></div>
  </section>`;
}

function openSource(root, nodeElement) {
  graphState.active = false;
  const page = String(nodeElement.dataset.cgPage || "");
  const pageButton = [...root.querySelectorAll("[data-ah-page]")]
    .find((candidate) => String(candidate.dataset.ahPage) === page);
  if (pageButton) pageButton.click();
  else inspectorTab(root, "source")?.click();
  const field = nodeElement.dataset.cgField || "";
  if (field) {
    window.setTimeout(() => {
      window.dispatchEvent(new CustomEvent("veritas:evidence-field", { detail: { field } }));
    }, 80);
  }
}

function selectGraphNode(root, nodeElement) {
  const graph = root.querySelector("[data-reference-claim-graph='true']");
  const panel = graph?.querySelector("[data-cg-detail-panel='true']");
  if (!graph || !panel || !nodeElement) return;
  graph.querySelectorAll("[data-cg-node]").forEach((candidate) => {
    const selected = candidate === nodeElement;
    candidate.classList.toggle("is-selected", selected);
    if (selected) candidate.setAttribute("aria-current", "true");
    else candidate.removeAttribute("aria-current");
  });
  graphState.selectedNodeId = nodeElement.dataset.cgNode || "";
  const title = nodeElement.dataset.cgTitle || "Graph node";
  const value = nodeElement.dataset.cgValue || "";
  const detail = nodeElement.dataset.cgDetail || "Persisted graph context.";
  const meta = nodeElement.dataset.cgMeta || "";
  const field = nodeElement.dataset.cgField || "";
  const actionLabel = field ? "Open highlighted evidence" : "Open evidence";
  panel.innerHTML = `<div class="cg-detail-copy">
    <span class="cg-detail-kicker">Selected persisted node</span>
    <div class="cg-detail-head"><strong>${esc(title)}</strong>${value ? `<em>${esc(value)}</em>` : ""}</div>
    ${meta ? `<small>${esc(meta)}</small>` : ""}
    <p>${esc(detail)}</p>
  </div>
  <div class="cg-detail-actions">
    <div><button type="button" class="primary" data-cg-detail-action="source">${esc(actionLabel)} <span>→</span></button></div>
    <span>Enter selects · double-click follows</span>
  </div>`;
  panel.querySelector("[data-cg-detail-action='source']")?.addEventListener(
    "click",
    () => openSource(root, nodeElement)
  );
}

function bindGraph(root) {
  const graph = root.querySelector("[data-reference-claim-graph='true']");
  if (!graph) return;
  const nodes = [...graph.querySelectorAll("[data-cg-node]")];
  nodes.forEach((nodeElement) => {
    const select = () => selectGraphNode(root, nodeElement);
    nodeElement.addEventListener("click", select);
    nodeElement.addEventListener("dblclick", () => openSource(root, nodeElement));
    nodeElement.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        select();
      }
    });
  });
  const preferred = nodes.find((candidate) => candidate.dataset.cgNode === graphState.selectedNodeId)
    || nodes.find((candidate) => candidate.dataset.cgField === "beta")
    || nodes[0];
  if (preferred) selectGraphNode(root, preferred);
}

async function renderGraph(root) {
  if (graphState.rendering) return;
  const auditId = root.dataset.auditId || "";
  const inspector = root.querySelector("#ah-inspector");
  if (!auditId || !inspector) return;
  graphState.rendering = true;
  const token = ++graphState.requestToken;
  inspector.innerHTML = `<div class="cg-loading"><span>◇</span><strong>Loading persisted claim graph…</strong></div>`;
  try {
    const payload = await requestClaimGraph(auditId);
    if (token !== graphState.requestToken || !graphState.active) return;
    const freshRoot = auditRoot();
    const freshInspector = freshRoot?.querySelector("#ah-inspector");
    if (!freshRoot || freshRoot.dataset.auditId !== auditId || !freshInspector) return;
    freshRoot.querySelectorAll(".ah-tabs button").forEach((button) => button.classList.remove("active"));
    freshRoot.querySelector("[data-reference-claim-tab]")?.classList.add("active");
    freshInspector.innerHTML = graphMarkup(payload);
    bindGraph(freshRoot);
  } catch (error) {
    const freshRoot = auditRoot();
    const freshInspector = freshRoot?.querySelector("#ah-inspector");
    if (!freshRoot || freshRoot.dataset.auditId !== auditId || !freshInspector) return;
    freshInspector.innerHTML = `<div class="cg-empty cg-error"><span>!</span><strong>Claim graph unavailable</strong><p>${esc(error.message)}</p><button type="button" data-cg-retry="true">Retry graph</button></div>`;
    freshInspector.querySelector("[data-cg-retry]")?.addEventListener("click", () => {
      graphState.active = true;
      renderGraph(auditRoot() || freshRoot);
    });
  } finally {
    graphState.rendering = false;
  }
}

function ensureTab(root) {
  const auditId = root.dataset.auditId || "";
  if (graphState.auditId && graphState.auditId !== auditId) {
    graphState.active = false;
    graphState.selectedNodeId = "";
    graphState.requestToken += 1;
  }
  graphState.auditId = auditId;
  const tabs = root.querySelector(".ah-tabs");
  if (!tabs) return;
  let tab = tabs.querySelector("[data-reference-claim-tab]");
  if (!tab) {
    tab = document.createElement("button");
    tab.type = "button";
    tab.dataset.referenceClaimTab = "true";
    tab.textContent = "Claim Graph";
    const findingsTab = tabs.querySelector("[data-ah-tab='findings']");
    if (findingsTab?.nextSibling) tabs.insertBefore(tab, findingsTab.nextSibling);
    else tabs.append(tab);
  }
  if (tab.dataset.bound !== "true") {
    tab.dataset.bound = "true";
    tab.addEventListener("click", () => {
      graphState.active = true;
      renderGraph(auditRoot() || root);
    });
  }
  tabs.querySelectorAll("[data-ah-tab]").forEach((nativeTab) => {
    if (nativeTab.dataset.claimGraphBound === "true") return;
    nativeTab.dataset.claimGraphBound = "true";
    nativeTab.addEventListener("click", () => {
      graphState.active = false;
      graphState.requestToken += 1;
    });
  });
  if (
    graphState.active
    && !graphState.rendering
    && !root.querySelector("[data-reference-claim-graph='true']")
  ) {
    renderGraph(root);
  }
}

function enhance() {
  graphState.queued = false;
  const root = auditRoot();
  if (!root) {
    graphState.active = false;
    graphState.auditId = "";
    graphState.selectedNodeId = "";
    graphState.requestToken += 1;
    return;
  }
  ensureTab(root);
}

function queueEnhance() {
  if (graphState.queued) return;
  graphState.queued = true;
  queueMicrotask(enhance);
}

const observer = new MutationObserver(queueEnhance);
if (main) observer.observe(main, { childList: true, subtree: true });
window.addEventListener("hashchange", queueEnhance);
queueEnhance();