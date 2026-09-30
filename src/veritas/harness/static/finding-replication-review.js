const main = document.querySelector("#main-content");
const RUN_FOCUS_KEY = "veritas.replication.run.focus.v1";

const reviewState = {
  auditId: "",
  items: [],
  loading: false,
  queued: false,
  requestToken: 0,
  focusingRunId: "",
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

function readRunFocus() {
  try {
    const raw = sessionStorage.getItem(RUN_FOCUS_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw);
    const auditId = String(value?.auditId || "").trim();
    const runId = String(value?.runId || "").trim();
    if (!auditId || !runId) return null;
    return { auditId, runId };
  } catch {
    return null;
  }
}

function clearRunFocus() {
  try { sessionStorage.removeItem(RUN_FOCUS_KEY); } catch {}
  reviewState.focusingRunId = "";
}

function openReviewedRun(item) {
  const auditId = String(item?.audit_id || "");
  const runId = String(item?.run_id || "");
  if (!auditId || !runId) return;
  try {
    sessionStorage.setItem(RUN_FOCUS_KEY, JSON.stringify({ auditId, runId }));
  } catch {}
  const reproductionNav = document.querySelector('[data-view="reproduction"]');
  if (reproductionNav instanceof HTMLElement) {
    reproductionNav.click();
    return;
  }
  location.hash = "#reproduction";
  location.reload();
}

function reviewForBinding(bindingId) {
  return reviewState.items.find((item) => (
    String(item?.origin_finding?.finding_id || "") === String(bindingId || "")
  )) || null;
}

function formatReviewTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function decorateFindingRows(root) {
  root.querySelectorAll(".fn-finding-row").forEach((row) => {
    const reproduce = row.querySelector("[data-fn-replication-finding-id]");
    const bindingId = reproduce?.dataset.fnReplicationFindingId || "";
    const item = reviewForBinding(bindingId);
    const existing = row.querySelector("[data-finding-replication-review='true']");
    if (!item) {
      existing?.remove();
      return;
    }

    const review = item.review || {};
    const disposition = String(review.disposition || "inconclusive");
    const note = String(review.note || "").trim();
    const when = formatReviewTime(review.created_at);
    const count = Number(item.review_count || 1);
    const fingerprint = [item.run_id, disposition, review.event_id, count].join(":");
    if (existing?.dataset.reviewFingerprint === fingerprint) return;

    const annotation = document.createElement("section");
    annotation.className = `fn-replication-review ${disposition}`;
    annotation.dataset.findingReplicationReview = "true";
    annotation.dataset.reviewFingerprint = fingerprint;
    annotation.dataset.reviewRunId = String(item.run_id || "");
    annotation.dataset.reviewDisposition = disposition;
    annotation.innerHTML = `
      <div class="fn-review-mark">↻</div>
      <div class="fn-review-copy">
        <div class="fn-review-title"><strong>Replication review</strong><span>${esc(disposition)}</span></div>
        ${note ? `<p>${esc(note)}</p>` : `<p>No operator note recorded.</p>`}
        <small>${when ? `${esc(when)} · ` : ""}${count} review event${count === 1 ? "" : "s"} · finding unchanged · generated outputs untrusted</small>
      </div>
      <button type="button" data-open-reviewed-run="true">Open run →</button>`;
    annotation.querySelector("[data-open-reviewed-run]")?.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      openReviewedRun(item);
    });
    if (existing) existing.replaceWith(annotation);
    else row.append(annotation);
  });
}

async function hydrateFindingReviews(root) {
  const auditId = String(root?.dataset.auditId || "");
  if (!auditId || reviewState.loading) return;
  if (reviewState.auditId === auditId) {
    decorateFindingRows(root);
    return;
  }
  const token = ++reviewState.requestToken;
  reviewState.loading = true;
  try {
    const response = await fetch(`/api/v1/audits/${encodeURIComponent(auditId)}/replication-reviews`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    const payload = await response.json();
    if (token !== reviewState.requestToken) return;
    reviewState.auditId = auditId;
    reviewState.items = Array.isArray(payload.items) ? payload.items : [];
    const freshRoot = auditRoot();
    if (freshRoot?.dataset.auditId === auditId) decorateFindingRows(freshRoot);
  } catch (error) {
    console.error("Unable to load replication reviews for findings", error);
  } finally {
    if (token === reviewState.requestToken) reviewState.loading = false;
  }
}

function focusReviewedRun() {
  const focus = readRunFocus();
  const surface = main?.querySelector("[data-reproduction-surface='true']");
  if (!focus || !surface) return false;

  const auditSelect = surface.querySelector("#rep-audit-select");
  if (auditSelect && auditSelect.value !== focus.auditId) {
    if (![...auditSelect.options].some((option) => option.value === focus.auditId)) {
      clearRunFocus();
      return true;
    }
    auditSelect.value = focus.auditId;
    auditSelect.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }

  const row = surface.querySelector(`.rep-run-row[data-run-id="${CSS.escape(focus.runId)}"]`);
  if (!row) return true;
  if (!row.classList.contains("selected")) {
    if (reviewState.focusingRunId !== focus.runId) {
      reviewState.focusingRunId = focus.runId;
      row.click();
    }
    return true;
  }

  const runTab = surface.querySelector("[data-rep-tab='run']");
  if (runTab && !runTab.classList.contains("active")) {
    runTab.click();
    return true;
  }
  clearRunFocus();
  return true;
}

function enhance() {
  reviewState.queued = false;
  if (!main) return;
  if (focusReviewedRun()) return;
  const root = auditRoot();
  if (!root) {
    reviewState.auditId = "";
    reviewState.items = [];
    reviewState.loading = false;
    return;
  }
  void hydrateFindingReviews(root);
}

function queueEnhance() {
  if (reviewState.queued) return;
  reviewState.queued = true;
  queueMicrotask(enhance);
}

const observer = new MutationObserver(queueEnhance);
if (main) observer.observe(main, { childList: true, subtree: true });
window.addEventListener("hashchange", queueEnhance);
queueEnhance();
