const main = document.querySelector("#main-content");
let enhanceTimer = null;
const reviewCache = new Map();

const DISPOSITIONS = [
  {
    value: "supports",
    label: "Supports finding",
    help: "The run is consistent with the detector finding or concern.",
  },
  {
    value: "contradicts",
    label: "Contradicts finding",
    help: "The run conflicts with the detector finding or concern.",
  },
  {
    value: "inconclusive",
    label: "Inconclusive",
    help: "The run does not support a clear operator assessment.",
  },
];

function selectedRunId() {
  return document.querySelector(".rep-run-row.selected[data-run-id]")?.dataset.runId || "";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatSavedAt(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

async function requestReview(runId, options = {}) {
  const response = await fetch(`/api/v1/runs/${encodeURIComponent(runId)}/review`, {
    cache: "no-store",
    headers: { Accept: "application/json", ...(options.headers || {}) },
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `review request failed: ${response.status}`);
  return body;
}

async function loadReview(runId) {
  if (!reviewCache.has(runId)) {
    reviewCache.set(runId, requestReview(runId));
  }
  try {
    return await reviewCache.get(runId);
  } catch (error) {
    reviewCache.delete(runId);
    throw error;
  }
}

function reviewCard(runId, payload) {
  const review = payload.review || null;
  const selected = review?.disposition || "";
  const note = review?.note || "";
  const saved = review?.created_at ? `Saved ${formatSavedAt(review.created_at)}` : "No operator review recorded";
  const findingId = payload.origin_finding?.finding_id || "linked finding";
  const section = document.createElement("section");
  section.className = "rep-review-card";
  section.dataset.repReviewCard = "true";
  section.dataset.repReviewRunId = runId;
  section.innerHTML = `
    <div class="rep-review-kicker">OPERATOR REVIEW</div>
    <strong>Assess reproduction against finding</strong>
    <p class="rep-review-copy">Record how this run relates to the linked detector finding. This is an operator annotation only: it does not resolve the finding, change detector evidence, or promote generated output to paper evidence.</p>
    <code class="rep-review-finding">${escapeHtml(findingId)}</code>
    <div class="rep-review-options" role="radiogroup" aria-label="Replication review disposition">
      ${DISPOSITIONS.map((item) => `<button type="button" class="rep-review-option ${selected === item.value ? "selected" : ""}" data-rep-review-disposition="${item.value}" role="radio" aria-checked="${selected === item.value ? "true" : "false"}"><span>${item.label}</span><small>${item.help}</small></button>`).join("")}
    </div>
    <label class="rep-review-note"><span>Review note <em>optional</em></span><textarea rows="3" maxlength="4000" placeholder="State what in the run output informed this assessment…">${escapeHtml(note)}</textarea></label>
    <div class="rep-review-actions"><small data-rep-review-status>${escapeHtml(saved)}</small><button type="button" class="primary-button" data-rep-review-save ${selected ? "" : "disabled"}>Save review</button></div>
    <div class="rep-review-boundary" data-rep-review-boundary="true">Review-only · finding remains open to independent evidence review · generated outputs remain untrusted</div>`;

  let disposition = selected;
  const save = section.querySelector("[data-rep-review-save]");
  const status = section.querySelector("[data-rep-review-status]");
  section.querySelectorAll("[data-rep-review-disposition]").forEach((button) => {
    button.addEventListener("click", () => {
      disposition = button.dataset.repReviewDisposition || "";
      section.querySelectorAll("[data-rep-review-disposition]").forEach((candidate) => {
        const active = candidate === button;
        candidate.classList.toggle("selected", active);
        candidate.setAttribute("aria-checked", String(active));
      });
      save.disabled = !disposition;
      status.textContent = review ? saved : "Unsaved operator assessment";
    });
  });

  save.addEventListener("click", async () => {
    if (!disposition) return;
    const textarea = section.querySelector("textarea");
    save.disabled = true;
    status.textContent = "Saving review…";
    try {
      const result = await requestReview(runId, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ disposition, note: textarea.value }),
      });
      reviewCache.set(runId, Promise.resolve(result));
      const createdAt = result.review?.created_at;
      status.textContent = createdAt ? `Saved ${formatSavedAt(createdAt)}` : "Review saved";
      section.dataset.repReviewSaved = "true";
      section.dataset.repReviewDisposition = disposition;
    } catch (error) {
      status.textContent = error.message || "Review could not be saved";
      section.dataset.repReviewError = "true";
    } finally {
      save.disabled = !disposition;
    }
  });
  return section;
}

async function enhanceRunInspector() {
  const inspector = document.querySelector(".rep-run-inspector");
  const origin = inspector?.querySelector("[data-rep-run-origin='true']");
  const runId = selectedRunId();
  if (!inspector || !origin || !runId) return;
  const existing = inspector.querySelector("[data-rep-review-card='true']");
  if (existing?.dataset.repReviewRunId === runId) return;
  existing?.remove();

  let payload;
  try {
    payload = await loadReview(runId);
  } catch {
    return;
  }
  if (selectedRunId() !== runId) return;
  const current = document.querySelector(".rep-run-inspector");
  const currentOrigin = current?.querySelector("[data-rep-run-origin='true']");
  if (!current || !currentOrigin) return;
  current.querySelector("[data-rep-review-card='true']")?.remove();
  currentOrigin.insertAdjacentElement("afterend", reviewCard(runId, payload));
}

function scheduleEnhancement() {
  clearTimeout(enhanceTimer);
  enhanceTimer = setTimeout(() => { void enhanceRunInspector(); }, 0);
}

if (main) {
  const observer = new MutationObserver(scheduleEnhancement);
  observer.observe(main, { childList: true, subtree: true });
  document.addEventListener("click", (event) => {
    if (event.target.closest?.("[data-run-id], [data-rep-tab='run'], #rep-refresh-runs")) {
      scheduleEnhancement();
    }
  });
  scheduleEnhancement();
}
