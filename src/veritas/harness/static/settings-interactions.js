const main = document.querySelector("#main-content");

const providerLabel = (card) => card.querySelector(".provider-node-name strong")?.textContent?.trim() || card.dataset.modelProvider || "Provider";
const providerFamily = (card) => card.querySelector(".provider-node-name span")?.textContent?.trim() || "Model family";
const providerMeta = (card) => [...card.querySelectorAll(".provider-node-meta span")].map((node) => {
  const label = node.querySelector("b")?.textContent?.trim() || "DETAIL";
  const value = [...node.childNodes]
    .filter((child) => child.nodeType === Node.TEXT_NODE)
    .map((child) => child.textContent?.trim() || "")
    .filter(Boolean)
    .join(" ");
  return { label, value: value || "—" };
});
const finePointer = window.matchMedia("(pointer: fine)");
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
const HOVER_PREVIEW_DELAY_MS = 150;
const HOVER_RELEASE_GRACE_MS = 90;
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
  const kicker = mode === "pinned" ? "PINNED NODE" : mode === "focus" ? "FOCUS LINK" : "POINTER LINK";
  inspector.innerHTML = `<div><span class="router-inspector-kicker">${kicker}</span><strong>${providerLabel(card)}</strong><small>${providerFamily(card)} · ${selected ? "active route" : "standby route"}</small></div><div class="router-inspector-meta"><span><b>STATE</b>${state}</span>${meta.slice(0, 3).map((item) => `<span><b>${escapeHtml(item.label)}</b>${escapeHtml(item.value)}</span>`).join("")}</div><div class="router-inspector-orbit" aria-hidden="true"><i></i><i></i><i></i></div>`;
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

function createNetworkField(router) {
  const noop = {
    setPointer() {},
    clearPointer() {},
    focus() {},
  };
  if (!finePointer.matches || reducedMotion.matches) return noop;

  const canvas = document.createElement("canvas");
  canvas.className = "router-network-field";
  canvas.setAttribute("data-router-network-field", "true");
  canvas.setAttribute("aria-hidden", "true");
  router.prepend(canvas);

  const ctx = canvas.getContext("2d", { alpha: true });
  if (!ctx) return noop;

  const seeds = [
    [.06, .18, 0.2], [.17, .09, 1.4], [.29, .19, 2.6], [.41, .10, 3.2],
    [.53, .20, 4.5], [.66, .08, 5.3], [.78, .20, 6.1], [.91, .12, 7.4],
    [.10, .48, 8.1], [.24, .39, 9.2], [.38, .52, 10.4], [.51, .40, 11.1],
    [.63, .55, 12.3], [.76, .42, 13.7], [.89, .51, 14.4],
    [.08, .78, 15.2], [.21, .68, 16.1], [.35, .82, 17.3], [.49, .70, 18.2],
    [.62, .84, 19.1], [.75, .70, 20.4], [.91, .80, 21.3],
  ];
  const pointer = { x: 0, y: 0, active: false };
  let focusCard = null;
  let focusMode = "idle";
  let width = 0;
  let height = 0;
  let dpr = 1;
  let frame = 0;
  let lastPaint = 0;

  const localPoint = (element) => {
    if (!element?.isConnected) return null;
    const routerRect = router.getBoundingClientRect();
    const rect = element.getBoundingClientRect();
    return {
      x: rect.left - routerRect.left + rect.width / 2,
      y: rect.top - routerRect.top + rect.height / 2,
    };
  };

  const nodePositions = (time) => seeds.map(([nx, ny, phase]) => ({
    x: nx * width + Math.sin(time / 2200 + phase) * 4.5,
    y: ny * height + Math.cos(time / 2600 + phase * .73) * 3.5,
    phase,
  }));

  const paint = (time = performance.now()) => {
    if (!canvas.isConnected) return;
    frame = requestAnimationFrame(paint);
    const interactive = pointer.active || Boolean(focusCard);
    const cadence = interactive ? 32 : 90;
    canvas.dataset.networkCadence = interactive ? "active" : "idle";
    if (time - lastPaint < cadence) return;
    lastPaint = time;
    if (!width || !height) return;

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    const nodes = nodePositions(time);
    let links = 0;

    ctx.lineWidth = .65;
    for (let i = 0; i < nodes.length; i += 1) {
      for (let j = i + 1; j < nodes.length; j += 1) {
        const a = nodes[i];
        const b = nodes[j];
        const distance = Math.hypot(a.x - b.x, a.y - b.y);
        if (distance > 145) continue;
        const alpha = Math.max(0, (145 - distance) / 145) * .17;
        ctx.strokeStyle = `rgba(96, 224, 214, ${alpha.toFixed(3)})`;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
        links += 1;
      }
    }

    nodes.forEach((node) => {
      const pulse = .52 + Math.sin(time / 820 + node.phase) * .2;
      ctx.fillStyle = `rgba(111, 232, 222, ${Math.max(.12, pulse * .42).toFixed(3)})`;
      ctx.beginPath();
      ctx.arc(node.x, node.y, 1.15, 0, Math.PI * 2);
      ctx.fill();
    });

    if (pointer.active) {
      const nearest = [...nodes]
        .map((node) => ({ node, distance: Math.hypot(node.x - pointer.x, node.y - pointer.y) }))
        .sort((a, b) => a.distance - b.distance)
        .slice(0, 3);
      nearest.forEach(({ node, distance }, index) => {
        const alpha = Math.max(.08, .38 - distance / 700) * (1 - index * .17);
        const gradient = ctx.createLinearGradient(pointer.x, pointer.y, node.x, node.y);
        gradient.addColorStop(0, `rgba(139, 255, 243, ${alpha.toFixed(3)})`);
        gradient.addColorStop(1, "rgba(91, 211, 204, .04)");
        ctx.strokeStyle = gradient;
        ctx.lineWidth = index === 0 ? 1 : .65;
        ctx.beginPath();
        ctx.moveTo(pointer.x, pointer.y);
        ctx.lineTo(node.x, node.y);
        ctx.stroke();
      });
      ctx.strokeStyle = "rgba(140, 255, 244, .48)";
      ctx.lineWidth = .75;
      ctx.beginPath();
      ctx.arc(pointer.x, pointer.y, 8 + Math.sin(time / 360) * 1.5, 0, Math.PI * 2);
      ctx.stroke();
    }

    const flowSource = localPoint(router.querySelector(".router-flow-node.provider"));
    const target = localPoint(focusCard);
    if (flowSource && target) {
      const gradient = ctx.createLinearGradient(flowSource.x, flowSource.y, target.x, target.y);
      gradient.addColorStop(0, "rgba(104, 233, 222, .72)");
      gradient.addColorStop(.5, focusMode === "pinned" ? "rgba(124, 255, 235, .52)" : "rgba(91, 214, 206, .31)");
      gradient.addColorStop(1, "rgba(85, 189, 187, .07)");
      ctx.strokeStyle = gradient;
      ctx.lineWidth = focusMode === "pinned" ? 1.35 : .85;
      ctx.setLineDash([4, 7]);
      ctx.lineDashOffset = -(time / 75) % 11;
      ctx.beginPath();
      ctx.moveTo(flowSource.x, flowSource.y);
      const midY = Math.min(flowSource.y, target.y) - 18;
      ctx.bezierCurveTo(flowSource.x, midY, target.x, midY, target.x, target.y);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = focusMode === "pinned" ? "rgba(143, 255, 239, .92)" : "rgba(111, 226, 217, .68)";
      ctx.beginPath();
      ctx.arc(target.x, target.y, focusMode === "pinned" ? 2.8 : 2, 0, Math.PI * 2);
      ctx.fill();
    }

    canvas.dataset.networkLinks = String(links);
  };

  const resize = () => {
    const rect = router.getBoundingClientRect();
    width = Math.max(1, Math.round(rect.width));
    height = Math.max(1, Math.round(rect.height));
    dpr = Math.min(window.devicePixelRatio || 1, 1.75);
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    canvas.dataset.networkReady = "true";
  };

  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(router);
  resize();
  frame = requestAnimationFrame(paint);

  return {
    setPointer(x, y) {
      pointer.x = x;
      pointer.y = y;
      pointer.active = true;
      canvas.dataset.networkPointer = "active";
    },
    clearPointer() {
      pointer.active = false;
      canvas.dataset.networkPointer = "idle";
    },
    focus(card, mode = "hover") {
      focusCard = card || null;
      focusMode = card ? mode : "idle";
      canvas.dataset.networkFocus = card?.dataset.modelProvider || "";
      canvas.dataset.networkFocusMode = focusMode;
    },
  };
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
  inspector.id = "router-pointer-inspector";
  inspector.setAttribute("data-router-pointer-inspector", "true");
  inspector.setAttribute("aria-live", "polite");
  grid.insertAdjacentElement("afterend", inspector);
  renderInspector(inspector, null);

  const network = createNetworkField(router);
  let pinned = null;
  let hovered = null;
  let focused = null;
  let frame = 0;
  let lastPointer = null;
  let hoverTimer = 0;
  let releaseTimer = 0;

  const clearHoverTimer = () => {
    if (!hoverTimer) return;
    window.clearTimeout(hoverTimer);
    hoverTimer = 0;
  };
  const clearReleaseTimer = () => {
    if (!releaseTimer) return;
    window.clearTimeout(releaseTimer);
    releaseTimer = 0;
  };
  const clearPreview = () => {
    renderInspector(inspector, null);
    network.focus(null);
    router.dataset.previewMode = "idle";
    router.dataset.previewProvider = "";
  };
  const showPreview = (card, mode) => {
    if (!card?.isConnected || pinned) return;
    renderInspector(inspector, card, mode);
    network.focus(card, mode);
    router.dataset.previewMode = mode;
    router.dataset.previewProvider = card.dataset.modelProvider || "";
  };
  const schedulePointerPreview = (card) => {
    hovered = card;
    card.dataset.hovered = "true";
    card.dataset.hoverIntent = "pending";
    clearHoverTimer();
    clearReleaseTimer();
    hoverTimer = window.setTimeout(() => {
      hoverTimer = 0;
      if (pinned || hovered !== card || !card.isConnected) return;
      card.dataset.hoverIntent = "active";
      showPreview(card, "hover");
    }, HOVER_PREVIEW_DELAY_MS);
  };
  const releasePointerPreview = (card) => {
    if (hovered === card) hovered = null;
    card.dataset.hovered = "false";
    card.dataset.hoverIntent = "idle";
    resetCardPointer(card);
    clearHoverTimer();
    clearReleaseTimer();
    releaseTimer = window.setTimeout(() => {
      releaseTimer = 0;
      if (pinned) return;
      if (focused?.isConnected) showPreview(focused, "focus");
      else clearPreview();
    }, HOVER_RELEASE_GRACE_MS);
  };
  const focusPreview = (card) => {
    focused = card;
    card.dataset.focused = "true";
    clearReleaseTimer();
    showPreview(card, "focus");
  };
  const blurPreview = (card) => {
    if (focused === card) focused = null;
    card.dataset.focused = "false";
    if (pinned) return;
    clearReleaseTimer();
    releaseTimer = window.setTimeout(() => {
      releaseTimer = 0;
      if (hovered?.isConnected && hovered.dataset.hoverIntent === "active") showPreview(hovered, "hover");
      else clearPreview();
    }, HOVER_RELEASE_GRACE_MS);
  };

  const applyRouterPointer = () => {
    frame = 0;
    if (!lastPointer) return;
    const rect = router.getBoundingClientRect();
    const x = Math.max(0, Math.min(rect.width, lastPointer.clientX - rect.left));
    const y = Math.max(0, Math.min(rect.height, lastPointer.clientY - rect.top));
    router.style.setProperty("--router-x", `${x}px`);
    router.style.setProperty("--router-y", `${y}px`);
    router.dataset.cursorActive = "true";
    network.setPointer(x, y);
  };

  router.addEventListener("pointermove", (event) => {
    if (event.pointerType === "touch") return;
    lastPointer = { clientX: event.clientX, clientY: event.clientY };
    if (!frame) frame = requestAnimationFrame(applyRouterPointer);
  });
  router.addEventListener("pointerleave", () => {
    router.dataset.cursorActive = "false";
    lastPointer = null;
    network.clearPointer();
  });
  router.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || !pinned) return;
    pinned.dataset.pinned = "false";
    pinned.setAttribute("aria-pressed", "false");
    pinned = null;
    clearPreview();
  });

  cards.forEach((card) => {
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    card.setAttribute("aria-pressed", "false");
    card.setAttribute("aria-controls", inspector.id);
    card.setAttribute("aria-label", `${providerLabel(card)} provider configuration`);
    card.dataset.hoverIntent = "idle";
    card.dataset.focused = "false";

    card.addEventListener("pointerenter", () => schedulePointerPreview(card));
    card.addEventListener("focus", () => focusPreview(card));
    card.addEventListener("pointermove", (event) => {
      if (event.pointerType !== "touch") setCardPointer(card, event);
    });
    card.addEventListener("pointerleave", () => releasePointerPreview(card));
    card.addEventListener("blur", () => blurPreview(card));

    const togglePin = () => {
      const next = pinned === card ? null : card;
      cards.forEach((item) => {
        const active = item === next;
        item.dataset.pinned = String(active);
        item.setAttribute("aria-pressed", String(active));
      });
      pinned = next;
      clearHoverTimer();
      clearReleaseTimer();
      if (pinned) {
        renderInspector(inspector, pinned, "pinned");
        network.focus(pinned, "pinned");
        router.dataset.previewMode = "pinned";
        router.dataset.previewProvider = pinned.dataset.modelProvider || "";
      } else if (focused?.isConnected) {
        showPreview(focused, "focus");
      } else if (hovered?.isConnected && hovered.dataset.hoverIntent === "active") {
        showPreview(hovered, "hover");
      } else {
        clearPreview();
      }
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