const main = document.querySelector("#main-content");

const graphState = {
  auditId: "",
  active: false,
  queued: false,
  rendering: false,
  requestToken: 0,
};

const GRAPH_WIDTH = 640;
const GRAPH_HEIGHT = 650;
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

function tone(status = "") {
  const value = String(status).toLowerCase();
  if (["verified", "success", "pass", "ready"].some((item) => value.includes(item))) return "good";
  if (["contradiction", "danger", "error", "fail"].some((item) => value.includes(item))) return "bad";
  if (["review", "warning", "unverifiable"].some((item) => value.includes(item))) return "warn";
  return "neutral";
}

function truncate(value, length = 24) {
  const text = String(value ?? "");
  return text.length > length ? `${text.slice(0, Math.max(1, length - 1))}…` : text;
}

function statusValue(check = {}) {
  return typeof check.status === "object" ? check.status?.value : check.status;
}

async function requestAudit(auditId) {
  const response = await fetch(`/api/v1/audits/${encodeURIComponent(auditId)}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

function node({ id, x, y, title, value = "", kind = "neutral", field = "", action = "" }) {
  const attrs = [
    `data-cg-node="${esc(id)}"`,
    field ? `data-cg-field="${esc(field)}"` : "",
    action ? `data-cg-action="${esc(action)}"` : "",
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

function edge(x1, y1, x2, y2, label = "") {
  const midY = (y1 + y2) / 2;
  return `<g class="cg-edge"><path d="M ${x1} ${y1} C ${x1} ${midY}, ${x2} ${midY}, ${x2} ${y2}" marker-end="url(#cg-arrow)"></path>${label ? `<text x="${(x1 + x2) / 2}" y="${midY - 7}">${esc(label)}</text>` : ""}</g>`;
}

function graphMarkup(audit) {
  const result = audit?.latest_result || null;
  if (!result) {
    return `<div class="cg-empty" data-reference-claim-graph="true"><span>◇</span><strong>No claim graph yet</strong><p>Run an evidence-linked audit. Veritas will project the persisted result, source, checks, and findings into a claim graph.</p></div>`;
  }

  const consensus = result.consensus || {};
  const source = result.source || {};
  const checks = Array.isArray(result.checks) ? result.checks : [];
  const findings = Array.isArray(result.findings) ? result.findings : [];
  const page = Number(source.page || result.locator?.expected_page || 1);
  const row = result.row_label || source.row || "Reported result";
  const table = String(source.table || result.locator?.table_label || "Located table").replace(/\s*\[native-table:[^\]]+\]\s*/gi, " ").replace(/\s+/g, " ").trim();
  const parserFamilies = new Set(
    Object.values(result.fields || {})
      .flatMap((candidates) => Array.isArray(candidates) ? candidates : [])
      .map((candidate) => candidate?.parser_family)
      .filter(Boolean)
  );

  const values = [
    ["beta", "Estimate", consensus.beta],
    ["se", "Std. Error", consensus.se],
    ["t_stat", "Test statistic", consensus.t_stat],
    ["p_value", "p-value", consensus.p_value],
  ].filter(([, , value]) => value !== null && value !== undefined && value !== "");

  const sourcePosition = { x: 225, y: 24 };
  const claimPosition = { x: 225, y: 126 };
  const metricPositions = [
    { x: 38, y: 252 },
    { x: 412, y: 252 },
    { x: 38, y: 350 },
    { x: 412, y: 350 },
  ];
  const checkPositions = [
    { x: 38, y: 476 },
    { x: 412, y: 476 },
    { x: 38, y: 560 },
    { x: 412, y: 560 },
  ];
  const sourceValue = `${truncate(table || "Paper source", 20)} · p.${page}`;
  const status = String(result.status || "review_required");
  const checkItems = checks.slice(0, 4);

  const sourceCenter = sourcePosition.x + NODE_WIDTH / 2;
  const claimCenter = claimPosition.x + NODE_WIDTH / 2;
  const edges = [
    edge(sourceCenter, sourcePosition.y + NODE_HEIGHT, claimCenter, claimPosition.y, "supports"),
  ];
  values.forEach(([, label], index) => {
    const position = metricPositions[index];
    edges.push(edge(
      claimCenter,
      claimPosition.y + NODE_HEIGHT,
      position.x + NODE_WIDTH / 2,
      position.y,
      label === "Estimate" ? "reports" : "tests"
    ));
  });
  checkItems.forEach((check, index) => {
    const position = checkPositions[index];
    const metric = values.length ? metricPositions[Math.min(index, values.length - 1)] : claimPosition;
    edges.push(edge(
      metric.x + NODE_WIDTH / 2,
      metric.y + NODE_HEIGHT,
      position.x + NODE_WIDTH / 2,
      position.y,
      "checked by"
    ));
  });

  const nodes = [
    node({ id: "source", ...sourcePosition, title: "Evidence source", value: sourceValue, kind: "source", action: "source" }),
    node({ id: "claim", ...claimPosition, title: row, value: `${Math.round((Number(result.verification_coverage) || 0) * 100)}% verified`, kind: tone(status), action: "source" }),
    ...values.map(([field, label, value], index) => node({ id: field, ...metricPositions[index], title: label, value, kind: "metric", field, action: "source" })),
    ...checkItems.map((check, index) => node({
      id: `check-${index}`,
      ...checkPositions[index],
      title: check.title || check.name || check.kind || check.check || `Check ${index + 1}`,
      value: String(statusValue(check) || "recorded").replaceAll("_", " "),
      kind: tone(statusValue(check)),
      action: statusValue(check) === "fail" ? "findings" : "source",
    })),
  ];

  if (!checkItems.length) {
    const fallback = { x: 225, y: 500 };
    edges.push(edge(claimCenter, claimPosition.y + NODE_HEIGHT, fallback.x + NODE_WIDTH / 2, fallback.y, "reviewed by"));
    nodes.push(node({
      id: "checks",
      ...fallback,
      title: findings.length ? `${findings.length} finding${findings.length === 1 ? "" : "s"}` : "Audit checks",
      value: findings.length ? "Open linked findings" : "No persisted checks",
      kind: findings.length ? "bad" : "neutral",
      action: findings.length ? "findings" : "source",
    }));
  }

  return `<section class="claim-graph" data-reference-claim-graph="true">
    <div class="cg-toolbar"><div><strong>Claim Graph</strong><small>Derived from the latest persisted audit result</small></div><div class="cg-legend"><span><i class="source"></i>evidence</span><span><i class="metric"></i>reported value</span><span><i class="check"></i>verification</span></div></div>
    <div class="cg-canvas" role="region" aria-label="Evidence claim graph">
      <svg viewBox="0 0 ${GRAPH_WIDTH} ${GRAPH_HEIGHT}" role="img" aria-label="Claim graph for ${esc(row)}">
        <defs><marker id="cg-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z"></path></marker></defs>
        ${edges.join("")}
        ${nodes.join("")}
      </svg>
    </div>
    <div class="cg-foot"><span>${esc(parserFamilies.size)} independent parser families represented · select a value to open evidence</span><span>${esc(checks.length)} checks · ${esc(findings.length)} findings</span></div>
  </section>`;
}

function openSource(root, page, field = "") {
  graphState.active = false;
  const pageButton = [...root.querySelectorAll("[data-ah-page]")].find((node) => String(node.dataset.ahPage) === String(page));
  if (pageButton) pageButton.click();
  else root.querySelector("[data-ah-tab='source']")?.click();
  if (field) {
    window.setTimeout(() => {
      window.dispatchEvent(new CustomEvent("veritas:evidence-field", { detail: { field } }));
    }, 80);
  }
}

function bindGraph(root, audit) {
  const graph = root.querySelector("[data-reference-claim-graph='true']");
  if (!graph) return;
  const page = Number(audit?.latest_result?.source?.page || audit?.latest_result?.locator?.expected_page || 1);
  graph.querySelectorAll("[data-cg-node]").forEach((nodeElement) => {
    const activate = () => {
      const action = nodeElement.dataset.cgAction || "source";
      if (action === "findings") {
        graphState.active = false;
        root.querySelector("[data-ah-tab='findings']")?.click();
        return;
      }
      openSource(root, page, nodeElement.dataset.cgField || "");
    };
    nodeElement.addEventListener("click", activate);
    nodeElement.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        activate();
      }
    });
  });
}

async function renderGraph(root) {
  if (graphState.rendering) return;
  const auditId = root.dataset.auditId || "";
  const inspector = root.querySelector("#ah-inspector");
  if (!auditId || !inspector) return;
  graphState.rendering = true;
  const token = ++graphState.requestToken;
  inspector.innerHTML = `<div class="cg-loading"><span>◇</span><strong>Building evidence graph…</strong></div>`;
  try {
    const audit = await requestAudit(auditId);
    if (token !== graphState.requestToken || !graphState.active) return;
    const freshRoot = auditRoot();
    const freshInspector = freshRoot?.querySelector("#ah-inspector");
    if (!freshRoot || freshRoot.dataset.auditId !== auditId || !freshInspector) return;
    freshRoot.querySelectorAll(".ah-tabs button").forEach((button) => button.classList.remove("active"));
    freshRoot.querySelector("[data-reference-claim-tab]")?.classList.add("active");
    freshInspector.innerHTML = graphMarkup(audit);
    bindGraph(freshRoot, audit);
  } catch (error) {
    inspector.innerHTML = `<div class="cg-empty"><span>!</span><strong>Claim graph unavailable</strong><p>${esc(error.message)}</p></div>`;
  } finally {
    graphState.rendering = false;
  }
}

function ensureTab(root) {
  const auditId = root.dataset.auditId || "";
  if (graphState.auditId && graphState.auditId !== auditId) graphState.active = false;
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
    nativeTab.addEventListener("click", () => { graphState.active = false; });
  });
  if (graphState.active && !graphState.rendering && !root.querySelector("[data-reference-claim-graph='true']")) renderGraph(root);
}

function enhance() {
  graphState.queued = false;
  const root = auditRoot();
  if (!root) {
    graphState.active = false;
    graphState.auditId = "";
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
