const FINDING_PAGE_LIMIT = 50;

const findingFeed = {
  items: [],
  nextCursor: null,
  hasMore: false,
  total: 0,
  severityCounts: {},
  loadingMore: false,
  loadMoreError: "",
  ready: false,
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function shortDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric" }).format(date);
}

function statusBadge(value, fallback = "contradiction") {
  const raw = String(value || fallback);
  const normalized = raw.toLowerCase();
  const label = raw.replaceAll("_", " ");
  const cls = ["success", "verified", "ready", "pass"].includes(normalized)
    ? "success"
    : ["running", "review", "warning", "needs_review"].includes(normalized)
      ? "warning"
      : "danger";
  return `<span class="badge ${cls}">${escapeHtml(label)}</span>`;
}

function normalizeSnapshot(value) {
  const items = Array.isArray(value?.items) ? value.items.filter((item) => item && item.finding_id) : [];
  return {
    items,
    nextCursor: value?.next_cursor || null,
    hasMore: Boolean(value?.has_more),
    total: Number(value?.total) || items.length,
    severityCounts: value?.severity_counts && typeof value.severity_counts === "object"
      ? value.severity_counts
      : {},
  };
}

function replaceHead(value) {
  const snapshot = normalizeSnapshot(value);
  // Findings are a mutable projection of each audit's latest result. A refresh
  // must replace the old feed rather than retain findings that disappeared after
  // a rerun. Only explicit "Load more" appends older pages.
  findingFeed.items = snapshot.items;
  findingFeed.nextCursor = snapshot.nextCursor;
  findingFeed.hasMore = snapshot.hasMore;
  findingFeed.total = snapshot.total;
  findingFeed.severityCounts = snapshot.severityCounts;
  findingFeed.loadingMore = false;
  findingFeed.loadMoreError = "";
  findingFeed.ready = true;
  updateGlobalCount();
  enhanceFindingsPage();
}

function appendTail(value) {
  const snapshot = normalizeSnapshot(value);
  const seen = new Set(findingFeed.items.map((item) => item.finding_id));
  for (const item of snapshot.items) {
    if (!seen.has(item.finding_id)) {
      seen.add(item.finding_id);
      findingFeed.items.push(item);
    }
  }
  findingFeed.nextCursor = snapshot.nextCursor;
  findingFeed.hasMore = snapshot.hasMore;
  findingFeed.total = snapshot.total;
  findingFeed.severityCounts = snapshot.severityCounts;
  findingFeed.loadingMore = false;
  findingFeed.loadMoreError = "";
  findingFeed.ready = true;
  updateGlobalCount();
}

function updateGlobalCount() {
  if (!findingFeed.ready) return;
  const node = document.querySelector("#finding-count");
  const authoritative = String(findingFeed.total || findingFeed.items.length);
  if (node && node.textContent !== authoritative) node.textContent = authoritative;
}

function openAudit(auditId) {
  if (!auditId) return;
  const target = new URL(window.location.href);
  target.searchParams.set("audit_open", auditId);
  target.hash = `audit=${encodeURIComponent(auditId)}`;
  if (target.href !== window.location.href) window.location.href = target.href;
}

function findingCard(finding) {
  const source = finding.source && typeof finding.source === "object" ? finding.source : {};
  return `<article class="finding-card finding-page-card" tabindex="0"
      data-audit-id="${escapeHtml(finding.audit_id)}"
      data-finding-id="${escapeHtml(finding.finding_id)}"
      data-finding-page-id="${escapeHtml(finding.finding_id)}">
    <div>
      <h3>${escapeHtml(finding.title || "Finding")}</h3>
      <p>${escapeHtml(finding.explanation || "")}</p>
      <div class="finding-meta">
        ${statusBadge(finding.severity)}
        <span>${escapeHtml(finding.audit_title || "")}</span>
        <span>${shortDate(finding.updated_at)}</span>
      </div>
    </div>
    <div class="finding-source">
      <strong>${escapeHtml(source.table || "Source")}</strong><br>
      ${source.page ? `page ${escapeHtml(source.page)}` : "open paper"}
    </div>
  </article>`;
}

function footerHtml() {
  if (findingFeed.loadMoreError) {
    return `<div class="finding-page-footer finding-page-error">
      <span>${escapeHtml(findingFeed.loadMoreError)}</span>
      <button class="secondary-button" data-finding-page-retry>Retry</button>
    </div>`;
  }
  if (findingFeed.hasMore) {
    return `<div class="finding-page-footer">
      <span>Loaded ${findingFeed.items.length} of ${findingFeed.total} findings</span>
      <button class="secondary-button" data-finding-page-more ${findingFeed.loadingMore ? "disabled" : ""}>
        ${findingFeed.loadingMore ? "Loading…" : `Load ${FINDING_PAGE_LIMIT} more`}
      </button>
    </div>`;
  }
  return `<div class="finding-page-footer finding-page-terminal">
    <span>${findingFeed.items.length
      ? `Loaded all ${findingFeed.items.length} findings`
      : "No contradiction findings"}</span>
  </div>`;
}

function bindFindingCards(root) {
  root.querySelectorAll("[data-finding-page-id]").forEach((node) => {
    const activate = () => openAudit(node.dataset.auditId);
    node.addEventListener("click", activate);
    node.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        activate();
      }
    });
  });
  root.querySelector("[data-finding-page-more]")?.addEventListener("click", loadMore);
  root.querySelector("[data-finding-page-retry]")?.addEventListener("click", loadMore);
}

function enhanceFindingsPage() {
  const title = document.querySelector(".page-title")?.textContent?.trim();
  if (title !== "Findings") return;
  const page = document.querySelector("#main-content .page");
  if (!page) return;

  const previousScrollTop = document.querySelector("#main-content")?.scrollTop || 0;
  let list = page.querySelector(".finding-list");
  const panel = page.querySelector(".panel");

  if (findingFeed.items.length) {
    if (!list) {
      panel?.remove();
      list = document.createElement("div");
      list.className = "finding-list";
      page.append(list);
    }
    list.innerHTML = findingFeed.items.map(findingCard).join("");
  } else if (list) {
    list.remove();
  }

  page.querySelector(".finding-page-footer")?.remove();
  page.insertAdjacentHTML("beforeend", footerHtml());
  bindFindingCards(page);
  page.dataset.findingPaginationEnhanced = "1";
  updateGlobalCount();

  const main = document.querySelector("#main-content");
  if (main) main.scrollTop = previousScrollTop;
}

async function loadMore() {
  if (findingFeed.loadingMore || !findingFeed.hasMore || !findingFeed.nextCursor) return;
  findingFeed.loadingMore = true;
  findingFeed.loadMoreError = "";
  enhanceFindingsPage();

  const url = new URL("/api/v1/finding-pages", window.location.origin);
  url.searchParams.set("limit", String(FINDING_PAGE_LIMIT));
  url.searchParams.set("cursor", findingFeed.nextCursor);
  try {
    const response = await fetch(url.toString(), { cache: "no-store" });
    if (!response.ok) throw new Error(`Finding history request failed (${response.status})`);
    appendTail(await response.json());
  } catch (error) {
    findingFeed.loadingMore = false;
    findingFeed.loadMoreError = error instanceof Error ? error.message : "Finding history request failed";
  }
  enhanceFindingsPage();
}

function adoptInitialSnapshot() {
  if (window.__veritasFindingPageFeed) replaceHead(window.__veritasFindingPageFeed);
}

window.addEventListener("veritas:finding-page-reset", (event) => replaceHead(event.detail));

const globalCountNode = document.querySelector("#finding-count");
const globalCountObserver = new MutationObserver(() => updateGlobalCount());
if (globalCountNode) {
  // app.js still writes the size of its compatibility array after product boot.
  // Once the bounded page snapshot is authoritative, keep the sidebar count on
  // the server-reported total instead of allowing that later write to regress it.
  globalCountObserver.observe(globalCountNode, { childList: true, characterData: true, subtree: true });
}

const observer = new MutationObserver(() => {
  const title = document.querySelector(".page-title")?.textContent?.trim();
  const page = document.querySelector("#main-content .page");
  if (title !== "Findings" || !page) return;
  if (page.dataset.findingPaginationEnhanced === "1") return;
  enhanceFindingsPage();
});
observer.observe(document.querySelector("#main-content") || document.body, { childList: true, subtree: true });

adoptInitialSnapshot();
