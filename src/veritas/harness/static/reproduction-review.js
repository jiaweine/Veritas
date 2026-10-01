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

function permissionToolData(card) {
  const raw = card.querySelector(".rep-permission-copy .rep-json")?.textContent || "";
  if (!raw.trim()) return {};
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function permissionRawInput(tool) {
  const raw = tool.rawInput || tool.raw_input || {};
  return raw && typeof raw === "object" ? raw : {};
}

function permissionCapability(tool) {
  const value = String(tool.kind || "operation").trim().toLowerCase();
  return value || "operation";
}

function enhancePermissionCard(card) {
  if (card.dataset.permissionEnhanced === "true") return;
  card.dataset.permissionEnhanced = "true";
  card.classList.add("rep-permission-surface");

  const pending = card.classList.contains("pending");
  card.setAttribute("role", "group");
  card.setAttribute("aria-label", pending ? "Sensitive operation approval" : "Permission audit record");

  const copy = card.querySelector(".rep-permission-copy");
  const actions = card.querySelector(".rep-permission-actions");
  const tool = permissionToolData(card);
  const rawInput = permissionRawInput(tool);
  const capability = permissionCapability(tool);
  card.dataset.permissionCapability = capability;

  if (copy) {
    const payload = copy.querySelector(".rep-json");
    const meta = document.createElement("div");
    meta.className = "rep-permission-meta";
    meta.dataset.permissionMeta = "true";
    meta.innerHTML = `<span><b>Capability</b>${escapeHtml(capability)}</span><span><b>Scope</b>One operation</span><span><b>Persistence</b>Never remembered</span>`;
    copy.insertBefore(meta, payload || null);

    const command = typeof rawInput.command === "string" ? rawInput.command.trim() : "";
    if (command) {
      const code = document.createElement("code");
      code.className = "rep-permission-command";
      code.dataset.permissionCommand = "true";
      code.textContent = command;
      code.title = command;
      copy.insertBefore(code, payload || null);
    }

    const boundary = document.createElement("div");
    boundary.className = "rep-permission-boundary";
    boundary.dataset.permissionBoundary = "true";
    boundary.textContent = pending
      ? "Your decision applies only to this request. Veritas never turns this into permanent approval."
      : "Audit record only. This historical request cannot be approved again.";
    copy.insertBefore(boundary, payload || null);
  }

  if (pending && actions) {
    actions.setAttribute("aria-label", "Permission decision");
    actions.setAttribute("aria-live", "polite");
    const reject = actions.querySelector("[data-permission-decision='reject']");
    const allow = actions.querySelector("[data-permission-decision='allow_once']");
    if (reject) {
      reject.setAttribute("type", "button");
      reject.setAttribute("title", "Do not run this operation");
      reject.setAttribute("aria-label", "Reject this operation");
    }
    if (allow) {
      allow.setAttribute("type", "button");
      allow.setAttribute("title", "Approve this operation once; the choice is not remembered");
      allow.setAttribute("aria-label", "Allow this operation once");
    }
  }

  card.addEventListener("pointermove", (event) => {
    if (!card.classList.contains("pending")) return;
    const rect = card.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    card.style.setProperty("--permission-x", `${Math.max(0, Math.min(rect.width, event.clientX - rect.left))}px`);
    card.style.setProperty("--permission-y", `${Math.max(0, Math.min(rect.height, event.clientY - rect.top))}px`);
  });
  card.addEventListener("pointerleave", () => {
    card.style.setProperty("--permission-x", "50%");
    card.style.setProperty("--permission-y", "50%");
  });

  bindPermissionDecisionLock(card);
}

function bindPermissionDecisionLock(card) {
  const actions = card.querySelector(".rep-permission-actions");
  if (!actions) return;
  actions.querySelectorAll("[data-permission-decision]").forEach((button) => {
    if (button.dataset.permissionPolishBound === "true") return;
    button.dataset.permissionPolishBound = "true";
    button.addEventListener("click", () => {
      if (card.dataset.permissionSubmitting === "true") return;
      card.dataset.permissionSubmitting = "true";
      card.classList.add("submitting");
      actions.setAttribute("aria-busy", "true");
      const buttons = [...actions.querySelectorAll("[data-permission-decision]")];
      buttons.forEach((candidate) => { candidate.disabled = true; });

      const observer = new MutationObserver(() => {
        const remaining = [...actions.querySelectorAll("[data-permission-decision]")];
        if (!remaining.length) {
          card.classList.remove("submitting");
          card.classList.add("decision-dispatched");
          card.dataset.permissionSubmitting = "false";
          actions.removeAttribute("aria-busy");
          observer.disconnect();
          return;
        }
        if (!button.disabled) {
          remaining.forEach((candidate) => { candidate.disabled = false; });
          card.classList.remove("submitting");
          card.dataset.permissionSubmitting = "false";
          actions.removeAttribute("aria-busy");
          observer.disconnect();
        }
      });
      observer.observe(actions, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ["disabled"],
      });
    });
  });
}

function enhancePermissionCards(root = document) {
  root.querySelectorAll(".rep-permission").forEach(enhancePermissionCard);
}

function scheduleEnhancement() {
  clearTimeout(enhanceTimer);
  enhanceTimer = setTimeout(() => {
    enhancePermissionCards();
    void enhanceRunInspector();
  }, 0);
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
