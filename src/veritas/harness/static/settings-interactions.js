const main = document.querySelector("#main-content");

const providerLabel = (card) => card.querySelector(".provider-node-name strong")?.textContent?.trim() || card.dataset.modelProvider || "Provider";
const providerFamily = (card) => card.querySelector(".provider-node-name span")?.textContent?.trim() || "Model family";
const providerMeta = (card) => [...card.querySelectorAll(".provider-node-meta span")].map((node) => node.textContent.trim()).filter(Boolean);
const escapeHtml = (value = "") => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

function setCardPointer(card, event) {
  const rect = card.getBoundingClientRect();
  const x = Math.max(0, Math.min(rect.width, event.clientX - rect.left));
  const y = Math.max(0, Math.min(rect.height, event.clientY - rect.top));
  const nx = rect.width ? x / rect.width - 0.5 : 0;
  const ny = rect.height ? y / rect.height - 0.5 : 0;
  card.style.setProperty("--card-x", `${x}px`);
  card.style.setProperty("--card-y", `${y}px`);
  card.style.setProperty("--tilt-x", `${(-ny * 4.5).toFixed(2)}deg`);
  card.style.setProperty("--tilt-y", `${(nx * 5.5).toFixed(2)}deg`);
  card.dataset.pointerActive = "true";
}

function resetCardPointer(card) {
  card.style.setProperty("--tilt-x", "0deg");
  card.style.setProperty("--tilt-y", "0deg");
  card.dataset.pointerActive = "false";
}

function renderInspector(inspector, card, mode = "hover") {
  if (!card) {
    inspector.innerHTML = `<div><span class="router-inspector-kicker">POINTER LINK</span><strong>Hover a provider</strong><small>Move the pointer across a provider node to inspect its live configuration surface. Click to pin the card locally; no server configuration is changed.</small></div><div class="router-inspector-orbit" aria-hidden="true"><i></i><i></i><i></i></div>`;
    inspector.dataset.provider = "";
    inspector.dataset.mode = "idle";
    return;
  }
  const state = String(card.dataset.providerState || "available").replaceAll("_", " ").toUpperCase();
  const selected = card.dataset.providerSelected === "true";
  const meta = providerMeta(card);
  inspector.innerHTML = `<div><span class="router-inspector-kicker">${mode === "pinned" ? "PINNED NODE" : "POINTER LINK"}</span><strong>${providerLabel(card)}</strong><small>${providerFamily(card)} · ${selected ? "active route" : "standby route"}</small></div><div class="router-inspector-meta"><span><b>STATE</b>${state}</span>${meta.slice(0, 3).map((item) => `<span>${item}</span>`).join("")}</div><div class="router-inspector-orbit" aria-hidden="true"><i></i><i></i><i></i></div>`;
  inspector.dataset.provider = card.dataset.modelProvider || "";
  inspector.dataset.mode = mode;
}

function renderProbeStatus(status, payload = null) {
  if (!payload) {
    status.dataset.probeState = "idle";
    status.innerHTML = `<span class="router-probe-signal"><i></i></span><div><b>LIVE DIAGNOSTIC</b><strong>Provider link not tested</strong><small>No network request has been made. The test is non-generative and cannot change detector evidence.</small></div>`;
    return;
  }
  const latency = Number.isFinite(Number(payload.latency_ms)) ? `${Math.round(Number(payload.latency_ms))} ms` : "—";
  const statusCode = payload.status_code == null ? "—" : String(payload.status_code);
  const label = payload.ok ? "Provider link verified" : String(payload.detail || "Provider diagnostic failed");
  status.dataset.probeState = payload.ok ? "ready" : String(payload.state || "error");
  status.innerHTML = `<span class="router-probe-signal"><i></i></span><div><b>LIVE DIAGNOSTIC</b><strong>${escapeHtml(label)}</strong><small>${escapeHtml(payload.provider || "provider")} · ${escapeHtml(payload.model || "model")} · HTTP ${escapeHtml(statusCode)} · ${escapeHtml(latency)} · response body discarded</small></div>`;
}

async function runProviderProbe(button, status) {
  if (button.disabled || button.dataset.probing === "true") return;
  button.dataset.probing = "true";
  button.textContent = "PROBING…";
  status.dataset.probeState = "probing";
  status.innerHTML = `<span class="router-probe-signal"><i></i></span><div><b>LIVE DIAGNOSTIC</b><strong>Testing server-side provider route…</strong><small>Credential stays on the server. No prompt or research evidence is sent.</small></div>`;
  try {
    const response = await fetch("/api/v1/model-providers/probe", {
      method: "POST",
      headers: { Accept: "application/json" },
    });
    const payload = await response.json().catch(() => ({
      ok: false,
      state: "invalid_response",
      detail: `${response.status} ${response.statusText}`,
    }));
    renderProbeStatus(status, payload);
  } catch (error) {
    renderProbeStatus(status, {
      ok: false,
      state: "client_error",
      detail: error instanceof Error ? error.message : "Provider diagnostic failed",
    });
  } finally {
    button.dataset.probing = "false";
    button.textContent = "TEST LINK";
  }
}

function bindRouter(router) {
  if (!router || router.dataset.pointerInteractions === "true") return;
  router.dataset.pointerInteractions = "true";

  const grid = router.querySelector(".provider-grid");
  const cards = [...router.querySelectorAll("[data-model-provider]")];
  if (!grid || !cards.length) return;

  const probeStrip = document.createElement("div");
  probeStrip.className = "router-probe-strip";
  probeStrip.setAttribute("data-router-provider-probe", "true");
  probeStrip.setAttribute("aria-live", "polite");
  const probeStatus = document.createElement("div");
  probeStatus.className = "router-probe-status";
  renderProbeStatus(probeStatus);
  const probeButton = document.createElement("button");
  probeButton.type = "button";
  probeButton.className = "router-probe-button";
  probeButton.textContent = "TEST LINK";
  probeButton.disabled = router.dataset.modelRouterState !== "configured";
  probeButton.title = probeButton.disabled
    ? "Complete the server-side provider configuration before testing"
    : "Run a bounded, non-generative server-side provider diagnostic";
  probeStrip.append(probeStatus, probeButton);
  const telemetry = router.querySelector(".router-telemetry");
  if (telemetry) telemetry.insertAdjacentElement("afterend", probeStrip);
  else grid.insertAdjacentElement("beforebegin", probeStrip);
  probeButton.addEventListener("click", () => runProviderProbe(probeButton, probeStatus));

  const inspector = document.createElement("aside");
  inspector.className = "router-pointer-inspector";
  inspector.setAttribute("data-router-pointer-inspector", "true");
  inspector.setAttribute("aria-live", "polite");
  grid.insertAdjacentElement("afterend", inspector);
  renderInspector(inspector, null);

  let pinned = null;
  let frame = 0;
  let lastPointer = null;

  const applyRouterPointer = () => {
    frame = 0;
    if (!lastPointer) return;
    const rect = router.getBoundingClientRect();
    const x = Math.max(0, Math.min(rect.width, lastPointer.clientX - rect.left));
    const y = Math.max(0, Math.min(rect.height, lastPointer.clientY - rect.top));
    router.style.setProperty("--router-x", `${x}px`);
    router.style.setProperty("--router-y", `${y}px`);
    router.dataset.cursorActive = "true";
  };

  router.addEventListener("pointermove", (event) => {
    if (event.pointerType === "touch") return;
    lastPointer = event;
    if (!frame) frame = requestAnimationFrame(applyRouterPointer);
  });
  router.addEventListener("pointerleave", () => {
    router.dataset.cursorActive = "false";
    lastPointer = null;
  });

  cards.forEach((card) => {
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    card.setAttribute("aria-pressed", "false");
    card.setAttribute("aria-label", `${providerLabel(card)} provider configuration`);

    card.addEventListener("pointerenter", () => {
      card.dataset.hovered = "true";
      if (!pinned) renderInspector(inspector, card, "hover");
    });
    card.addEventListener("pointermove", (event) => {
      if (event.pointerType !== "touch") setCardPointer(card, event);
    });
    card.addEventListener("pointerleave", () => {
      card.dataset.hovered = "false";
      resetCardPointer(card);
      if (!pinned) renderInspector(inspector, null);
    });

    const togglePin = () => {
      const next = pinned === card ? null : card;
      cards.forEach((item) => {
        const active = item === next;
        item.dataset.pinned = String(active);
        item.setAttribute("aria-pressed", String(active));
      });
      pinned = next;
      renderInspector(inspector, pinned, pinned ? "pinned" : "idle");
    };

    card.addEventListener("click", togglePin);
    card.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        togglePin();
      }
    });
  });
}

function enhance() {
  const router = main?.querySelector("[data-model-provider-matrix='true']");
  if (router) bindRouter(router);
}

new MutationObserver(enhance).observe(main || document.body, { childList: true, subtree: true });
enhance();
