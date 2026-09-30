const main = document.querySelector("#main-content");
const REPLICATION_CONTEXT_KEY = "veritas.replication.context.v1";
const FINDING_FOCUS_KEY = "veritas.finding.focus.v1";

const findingState = {
  auditId: "",
  findings: [],
  queued: false,
  requestToken: 0,
  pendingFindingId: "",
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

function inspectorFindingsTab(root) {
  return root?.querySelector(".ah-tabs [data-ah-tab='findings']") || null;
}

async function requestAudit(auditId) {
  const response = await fetch(`/api/v1/audits/${encodeURIComponent(auditId)}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

function sourceSummary(finding = {}) {
  const source = finding.source || {};
  return [
    source.table,
    source.row,
    source.column,
    source.page ? `p.${source.page}` : "",
  ].filter(Boolean).join(" · ");
}

function replicationBindingId(index) {
  if (!findingState.auditId || !Number.isInteger(index) || index < 0) return "";
  return `${findingState.auditId}:finding:${index}`;
}

function displayFindingId(findingId) {
  const value = String(findingId || "");
  const prefix = `${findingState.auditId}:finding:`;
  if (!value.startsWith(prefix)) return value;
  const index = Number(value.slice(prefix.length));
  if (!Number.isInteger(index) || index < 0) return value;
  return String(findingState.findings[index]?.finding_id || value);
}

function persistReplicationContext(finding, findingId) {
  const context = {
    auditId: findingState.auditId,
    findingId,
    title: String(finding.title || "Finding"),
    explanation: String(finding.explanation || ""),
    severity: String(finding.severity || "review"),
    source: finding.source && typeof finding.source === "object" ? finding.source : {},
  };
  try {
    sessionStorage.setItem(REPLICATION_CONTEXT_KEY, JSON.stringify(context));
  } catch {}
  return context;
}

function consumeReturnFocus(root) {
  let focus = null;
  try {
    const raw = sessionStorage.getItem(FINDING_FOCUS_KEY);
    if (raw) focus = JSON.parse(raw);
  } catch {}
  if (!focus || String(focus.auditId || "") !== String(root?.dataset.auditId || "")) return;
  const findingId = String(focus.findingId || "");
  if (!findingId) return;
  findingState.pendingFindingId = findingId;
  try { sessionStorage.removeItem(FINDING_FOCUS_KEY); } catch {}
}

function openReplicationForFinding(finding, findingId) {
  persistReplicationContext(finding, findingId);
  const reproductionNav = document.querySelector('[data-view="reproduction"]');
  if (reproductionNav instanceof HTMLElement) {
    reproductionNav.click();
    return;
  }
  location.hash = "#reproduction";
  location.reload();
}

function selectFindingCard(findingId = findingState.pendingFindingId) {
  if (!findingId) return false;
  const root = auditRoot();
  if (!root) return false;
  const displayId = displayFindingId(findingId);
  const rows = [...root.querySelectorAll(".fn-finding-row[data-fn-finding-id]")];
  let selected = null;
  rows.forEach((row) => {
    const active = row.dataset.fnFindingId === displayId;
    row.classList.toggle("is-linked-finding", active);
    const card = row.querySelector(".ah-finding-card[data-fn-finding-id]");
    if (active) {
      row.setAttribute("aria-current", "true");
      card?.setAttribute("aria-current", "true");
      selected = row;
    } else {
      row.removeAttribute("aria-current");
      card?.removeAttribute("aria-current");
    }
  });
  if (!selected) return false;
  selected.scrollIntoView({ block: "center", inline: "nearest", behavior: "smooth" });
  findingState.pendingFindingId = findingId;
  return true;
}

function enhanceCards(root) {
  const cards = [...root.querySelectorAll(".ah-finding-card[data-ah-finding]")];
  cards.forEach((card) => {
    const index = Number(card.dataset.ahFinding);
    const finding = Number.isInteger(index) ? findingState.findings[index] : null;
    if (!finding) return;
    const findingId = String(finding.finding_id || `${findingState.auditId}:finding:${index}`);
    const bindingId = replicationBindingId(index);
    card.dataset.fnFindingId = findingId;
    card.setAttribute("aria-label", `${finding.title || "Finding"}. Open linked evidence.`);

    if (card.parentElement?.classList.contains("fn-finding-row")) return;
    const wrapper = document.createElement("div");
    wrapper.className = "fn-finding-row";
    wrapper.dataset.fnFindingId = findingId;
    card.parentNode?.insertBefore(wrapper, card);
    wrapper.append(card);

    const source = sourceSummary(finding);
    const actions = document.createElement("div");
    actions.className = "fn-finding-actions";
    actions.innerHTML = `${source ? `<span>${esc(source)}</span>` : `<span>Evidence-linked detector finding</span>`}
      <div>
        <button type="button" data-fn-evidence="true">Evidence</button>
        <button type="button" data-fn-reproduce="true">Reproduce</button>
        <button type="button" class="primary" data-fn-graph="true">Claim Graph <b>→</b></button>
      </div>`;
    wrapper.append(actions);

    actions.querySelector("[data-fn-evidence]")?.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      card.click();
    });
    const reproduce = actions.querySelector("[data-fn-reproduce]");
    if (reproduce && bindingId) reproduce.dataset.fnReplicationFindingId = bindingId;
    reproduce?.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      findingState.pendingFindingId = findingId;
      openReplicationForFinding(finding, bindingId || findingId);
    });
    actions.querySelector("[data-fn-graph]")?.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      findingState.pendingFindingId = findingId;
      window.dispatchEvent(new CustomEvent("veritas:claim-finding", {
        detail: {
          auditId: findingState.auditId,
          findingId,
          findingIndex: index,
        },
      }));
    });
  });
  selectFindingCard();
}

async function hydrateFindings(root) {
  const auditId = root.dataset.auditId || "";
  if (!auditId || !root.querySelector(".ah-finding-stack")) return;
  if (findingState.auditId === auditId && findingState.findings.length) {
    enhanceCards(root);
    return;
  }
  const token = ++findingState.requestToken;
  try {
    const audit = await requestAudit(auditId);
    if (token !== findingState.requestToken) return;
    const freshRoot = auditRoot();
    if (!freshRoot || freshRoot.dataset.auditId !== auditId) return;
    findingState.auditId = auditId;
    findingState.findings = Array.isArray(audit?.latest_result?.findings)
      ? audit.latest_result.findings
      : [];
    consumeReturnFocus(freshRoot);
    enhanceCards(freshRoot);
  } catch (error) {
    console.error("Unable to hydrate finding navigation", error);
  }
}

function enhance() {
  findingState.queued = false;
  const root = auditRoot();
  if (!root) {
    findingState.auditId = "";
    findingState.findings = [];
    findingState.pendingFindingId = "";
    return;
  }
  const auditId = root.dataset.auditId || "";
  if (findingState.auditId && findingState.auditId !== auditId) {
    findingState.findings = [];
    findingState.pendingFindingId = "";
  }
  consumeReturnFocus(root);
  hydrateFindings(root);
}

function queueEnhance() {
  if (findingState.queued) return;
  findingState.queued = true;
  queueMicrotask(enhance);
}

window.addEventListener("veritas:finding-select", (event) => {
  const findingId = String(event.detail?.findingId || "");
  if (!findingId) return;
  findingState.pendingFindingId = findingId;
  const root = auditRoot();
  inspectorFindingsTab(root)?.click();
  window.setTimeout(queueEnhance, 0);
  window.setTimeout(() => selectFindingCard(findingId), 140);
});

const observer = new MutationObserver(queueEnhance);
if (main) observer.observe(main, { childList: true, subtree: true });
window.addEventListener("hashchange", queueEnhance);
queueEnhance();