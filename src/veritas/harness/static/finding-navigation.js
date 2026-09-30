const main = document.querySelector("#main-content");

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

function selectFindingCard(findingId = findingState.pendingFindingId) {
  if (!findingId) return false;
  const root = auditRoot();
  if (!root) return false;
  const rows = [...root.querySelectorAll(".fn-finding-row[data-fn-finding-id]")];
  let selected = null;
  rows.forEach((row) => {
    const active = row.dataset.fnFindingId === findingId;
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
        <button type="button" class="primary" data-fn-graph="true">Claim Graph <b>→</b></button>
      </div>`;
    wrapper.append(actions);

    actions.querySelector("[data-fn-evidence]")?.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      card.click();
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
