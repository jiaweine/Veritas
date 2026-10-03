const main = document.querySelector("#main-content");
const sidebar = document.querySelector("#sidebar");
const AUDIT_PAGE_LIMIT = 50;

const auditFeed = {
  items: [],
  nextCursor: null,
  hasMore: false,
  total: 0,
  statusCounts: {},
  loadingMore: false,
  loadMoreError: "",
  enhancementQueued: false,
};

const esc = (value = "") => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

const pct = (value) => `${Math.round((Number(value) || 0) * 100)}%`;
const num = (value) => new Intl.NumberFormat().format(Number(value) || 0);
const shortDate = (value) => {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "—"
    : date.toLocaleDateString([], { month: "short", day: "numeric" });
};

function statusBadge(status = "ready", label = null) {
  const normalized = String(status || "ready").replaceAll("_", "-");
  const text = label || String(status || "ready").replaceAll("_", " ");
  return `<span class="badge ${esc(normalized)}">${esc(text)}</span>`;
}

function normalizeSnapshot(snapshot) {
  const items = Array.isArray(snapshot?.items) ? snapshot.items.filter((item) => item && item.audit_id) : [];
  return {
    items,
    nextCursor: snapshot?.next_cursor || null,
    hasMore: Boolean(snapshot?.has_more),
    total: Number(snapshot?.total) || items.length,
    statusCounts: snapshot?.status_counts && typeof snapshot.status_counts === "object"
      ? { ...snapshot.status_counts }
      : {},
  };
}

function mergeHead(existing, refreshed) {
  const merged = [];
  const seen = new Set();
  for (const item of [...refreshed, ...existing]) {
    const auditId = String(item?.audit_id || "");
    if (!auditId || seen.has(auditId)) continue;
    seen.add(auditId);
    merged.push(item);
  }
  return merged;
}

function appendTail(existing, incoming) {
  const merged = [...existing];
  const seen = new Set(existing.map((item) => String(item?.audit_id || "")).filter(Boolean));
  for (const item of incoming) {
    const auditId = String(item?.audit_id || "");
    if (!auditId || seen.has(auditId)) continue;
    seen.add(auditId);
    merged.push(item);
  }
  return merged;
}

function adoptSnapshot(snapshot, { reset = false } = {}) {
  const normalized = normalizeSnapshot(snapshot);
  const preserveCursor = !reset && auditFeed.items.length > AUDIT_PAGE_LIMIT;
  if (reset || auditFeed.items.length <= AUDIT_PAGE_LIMIT) {
    auditFeed.items = normalized.items;
  } else {
    // Product refreshes may request the first page again. Put refreshed head
    // rows first without discarding already-loaded older audit history.
    auditFeed.items = mergeHead(auditFeed.items, normalized.items);
  }
  if (!preserveCursor) {
    auditFeed.nextCursor = normalized.nextCursor;
    auditFeed.hasMore = normalized.hasMore;
  }
  auditFeed.total = Math.max(normalized.total, auditFeed.items.length);
  auditFeed.statusCounts = normalized.statusCounts;
  auditFeed.loadMoreError = "";
  queueEnhance();
}

function activeTitle() {
  return main?.querySelector(".page-title")?.textContent?.trim() || "";
}

function renderAuditRow(audit) {
  const result = audit.latest_result || {};
  const summary = audit.paper_summary || {};
  const auditId = esc(audit.audit_id);
  return `<tr class="clickable" data-audit-id="${auditId}" data-audit-page-id="${auditId}">
    <td><div class="row-title">${esc(audit.title || "Untitled audit")}</div><div class="row-sub mono">${auditId}</div></td>
    <td>${statusBadge(audit.status)}</td>
    <td><div style="display:flex;align-items:center;gap:8px"><div class="progress"><i style="width:${Math.max(0, Math.min(100, (Number(result.verification_coverage) || 0) * 100))}%"></i></div><span>${pct(result.verification_coverage)}</span></div></td>
    <td>${num(summary.pages)} pages · ${num(summary.tables_detected)} tables</td>
    <td>${shortDate(audit.updated_at)}</td>
  </tr>`;
}

function renderEvidenceRow(audit) {
  const result = audit.latest_result || {};
  const source = result.source || {};
  const auditId = esc(audit.audit_id);
  return `<tr class="clickable" data-audit-id="${auditId}" data-audit-page-id="${auditId}">
    <td><div class="row-title">${esc(audit.title || "Untitled audit")}</div></td>
    <td>${esc(source.page || "—")}</td>
    <td>${esc(source.table || "—")}</td>
    <td>${esc(source.row || "—")}</td>
    <td>${pct(result.verification_coverage)}</td>
  </tr>`;
}

function openPagedAudit(auditId) {
  if (!auditId) return;
  // app.js intentionally owns audit detail state and only resolves audit hashes
  // during boot. A paged row can name an audit outside the first-page state, so
  // use a document navigation to re-enter that existing server-backed open path.
  const target = new URL(window.location.href);
  target.searchParams.set("audit_open", auditId);
  target.hash = `audit=${encodeURIComponent(auditId)}`;
  window.location.assign(target.toString());
}

function bindAuditRows(root) {
  root.querySelectorAll("[data-audit-page-id]:not([data-audit-page-bound])").forEach((row) => {
    row.dataset.auditPageBound = "true";
    row.addEventListener("click", () => openPagedAudit(row.dataset.auditPageId));
  });
}

function statusCount(status) {
  return Number(auditFeed.statusCounts?.[status]) || 0;
}

function updateGlobalCounts() {
  const total = String(auditFeed.total || auditFeed.items.length);
  const auditCount = document.querySelector("#audit-count");
  if (auditCount && auditCount.textContent !== total) auditCount.textContent = total;
  const referenceCount = sidebar?.querySelector('[data-ref-view="audits"] em');
  if (referenceCount && referenceCount.textContent !== total) referenceCount.textContent = total;
}

function footerMarkup(kind) {
  const noun = kind === "evidence" ? "audits scanned" : "audits loaded";
  const loaded = auditFeed.items.length;
  const terminal = !auditFeed.hasMore && !auditFeed.nextCursor;
  const status = terminal
    ? `${loaded} ${noun} · End of validated audit history`
    : `${loaded} of ${auditFeed.total || "?"} ${noun}`;
  const error = auditFeed.loadMoreError
    ? `<span class="audit-page-error">${esc(auditFeed.loadMoreError)}</span>`
    : "";
  const button = terminal
    ? ""
    : `<button class="secondary-button" type="button" data-audit-load-more="${kind}" ${auditFeed.loadingMore ? "disabled" : ""}>${auditFeed.loadingMore ? "Loading…" : `Load ${AUDIT_PAGE_LIMIT} more`}</button>`;
  return `<div class="audit-page-footer" data-audit-page-footer="${kind}"><span>${esc(status)}</span>${error}${button}</div>`;
}

function enhanceAudits() {
  if (activeTitle() !== "Audits") return;
  const page = main.querySelector(".page");
  const panel = page?.querySelector(".panel");
  if (!page || !panel) return;

  const signature = [
    auditFeed.items.map((item) => item.audit_id).join(","),
    auditFeed.nextCursor || "",
    auditFeed.hasMore ? "1" : "0",
    auditFeed.total,
    auditFeed.loadingMore ? "1" : "0",
    auditFeed.loadMoreError,
  ].join("|");
  if (page.dataset.auditPageSignature === signature) return;

  const pills = page.querySelectorAll(".filter-pill");
  if (pills[0]) pills[0].textContent = `All ${auditFeed.total || auditFeed.items.length}`;
  if (pills[1]) pills[1].textContent = `Ready ${statusCount("ready")}`;
  if (pills[2]) pills[2].textContent = `Running ${statusCount("running")}`;
  if (pills[3]) pills[3].textContent = `Error ${statusCount("error")}`;

  if (auditFeed.items.length) {
    let tableWrap = panel.querySelector(".table-wrap");
    if (!tableWrap) {
      panel.innerHTML = `<div class="table-wrap"><table class="data-table"><thead><tr><th>Paper</th><th>Status</th><th>Evidence</th><th>Structure</th><th>Updated</th></tr></thead><tbody></tbody></table></div>`;
      tableWrap = panel.querySelector(".table-wrap");
    }
    const tbody = tableWrap?.querySelector("tbody");
    if (tbody) tbody.innerHTML = auditFeed.items.map(renderAuditRow).join("");
    bindAuditRows(panel);
  }

  panel.querySelector("[data-audit-page-footer='audits']")?.remove();
  panel.insertAdjacentHTML("beforeend", footerMarkup("audits"));
  bindFooter(panel);
  page.dataset.auditPageSignature = signature;
}

function enhanceEvidence() {
  if (activeTitle() !== "Evidence") return;
  const page = main.querySelector(".page");
  const panel = page?.querySelector(".panel");
  if (!page || !panel) return;
  const evidenceAudits = auditFeed.items.filter((audit) => audit.latest_result?.source);
  const signature = [
    evidenceAudits.map((item) => item.audit_id).join(","),
    auditFeed.nextCursor || "",
    auditFeed.hasMore ? "1" : "0",
    auditFeed.loadingMore ? "1" : "0",
    auditFeed.loadMoreError,
  ].join("|");
  if (page.dataset.auditEvidencePageSignature === signature) return;

  if (evidenceAudits.length) {
    panel.innerHTML = `<div class="table-wrap"><table class="data-table"><thead><tr><th>Paper</th><th>Page</th><th>Table</th><th>Row</th><th>Coverage</th></tr></thead><tbody>${evidenceAudits.map(renderEvidenceRow).join("")}</tbody></table></div>${footerMarkup("evidence")}`;
    bindAuditRows(panel);
  } else {
    panel.querySelector("[data-audit-page-footer='evidence']")?.remove();
    panel.insertAdjacentHTML("beforeend", footerMarkup("evidence"));
  }
  bindFooter(panel);
  page.dataset.auditEvidencePageSignature = signature;
}

function bindFooter(root) {
  root.querySelectorAll("[data-audit-load-more]:not([data-audit-load-bound])").forEach((button) => {
    button.dataset.auditLoadBound = "true";
    button.addEventListener("click", loadMoreAudits);
  });
}

async function loadMoreAudits() {
  if (auditFeed.loadingMore || !auditFeed.hasMore || !auditFeed.nextCursor) return;
  auditFeed.loadingMore = true;
  auditFeed.loadMoreError = "";
  const scrollTop = document.scrollingElement?.scrollTop || 0;
  queueEnhance();
  try {
    const url = new URL("/api/v1/audit-pages", window.location.origin);
    url.searchParams.set("limit", String(AUDIT_PAGE_LIMIT));
    url.searchParams.set("cursor", auditFeed.nextCursor);
    const response = await fetch(url.toString(), {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    const page = normalizeSnapshot(await response.json());
    auditFeed.items = appendTail(auditFeed.items, page.items);
    auditFeed.nextCursor = page.nextCursor;
    auditFeed.hasMore = page.hasMore;
    auditFeed.total = Math.max(page.total, auditFeed.items.length);
    auditFeed.statusCounts = page.statusCounts;
  } catch (error) {
    auditFeed.loadMoreError = `Unable to load the next audit page: ${error.message}`;
  } finally {
    auditFeed.loadingMore = false;
    queueEnhance();
    requestAnimationFrame(() => window.scrollTo({ top: scrollTop }));
  }
}

function enhance() {
  auditFeed.enhancementQueued = false;
  updateGlobalCounts();
  enhanceAudits();
  enhanceEvidence();
}

function queueEnhance() {
  if (auditFeed.enhancementQueued) return;
  auditFeed.enhancementQueued = true;
  queueMicrotask(enhance);
}

window.addEventListener("veritas:audit-page-reset", (event) => {
  adoptSnapshot(event.detail || {}, { reset: auditFeed.items.length <= AUDIT_PAGE_LIMIT });
});

if (window.__veritasAuditPageFeed) adoptSnapshot(window.__veritasAuditPageFeed, { reset: true });

const observer = new MutationObserver(queueEnhance);
if (main) observer.observe(main, { childList: true, subtree: true });
if (sidebar) observer.observe(sidebar, { childList: true, subtree: true });
window.addEventListener("hashchange", queueEnhance);
queueEnhance();
