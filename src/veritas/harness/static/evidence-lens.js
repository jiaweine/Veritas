const main = document.querySelector("#main-content");

const FIELD_LABELS = {
  beta: "Estimate",
  se: "Std. Error",
  t_stat: "Test statistic",
  p_value: "p-value",
};

function fieldLabel(field = "") {
  return FIELD_LABELS[field] || field.replaceAll("_", " ") || "Evidence field";
}

function activePreview() {
  return main?.querySelector("[data-reference-evidence-preview='true']") || null;
}

function fieldNode(preview, field) {
  return field ? preview.querySelector(`[data-ref-field="${CSS.escape(field)}"]`) : null;
}

function renderHud(preview, field = "", mode = "idle") {
  const hud = preview.querySelector("[data-evidence-lens-hud='true']");
  if (!hud) return;
  if (!field) {
    hud.dataset.mode = "idle";
    hud.innerHTML = `<div class="evidence-lens-hud-copy"><span>POINTER EVIDENCE LENS</span><strong>Inspect a reported value</strong><small>Hover a detector-backed field to inspect it. Click to pin; open Claim Graph to follow the same persisted value through the evidence chain.</small></div><div class="evidence-lens-radar" aria-hidden="true"><i></i><i></i><i></i></div>`;
    return;
  }

  const node = fieldNode(preview, field);
  const value = node?.textContent?.trim() || "—";
  hud.dataset.mode = mode;
  hud.innerHTML = `<div class="evidence-lens-hud-copy"><span>${mode === "pinned" ? "FIELD LOCK" : mode === "linked" ? "GRAPH LINK" : "POINTER TRACE"}</span><strong>${fieldLabel(field)}</strong><small>${value} · persisted detector consensus</small></div><div class="evidence-lens-hud-actions"><button type="button" data-evidence-open-graph="${field}">Open Claim Graph ↗</button>${mode === "pinned" || mode === "linked" ? `<button type="button" data-evidence-release="true">Release</button>` : ""}</div><div class="evidence-lens-radar active" aria-hidden="true"><i></i><i></i><i></i></div>`;

  hud.querySelector("[data-evidence-open-graph]")?.addEventListener("click", () => openClaimGraph(preview, field));
  hud.querySelector("[data-evidence-release]")?.addEventListener("click", () => setPinned(preview, "", "lens"));
}

function setPinned(preview, field = "", source = "lens") {
  const next = field || "";
  preview.dataset.evidenceLensPinned = next;
  preview.dataset.evidenceLensState = next ? (source === "graph" ? "linked" : "pinned") : "idle";
  preview.querySelectorAll("[data-ref-field]").forEach((node) => {
    const active = Boolean(next) && node.dataset.refField === next;
    node.dataset.lensPinned = String(active);
    node.setAttribute("aria-pressed", String(active));
  });
  renderHud(preview, next, next ? (source === "graph" ? "linked" : "pinned") : "idle");
  if (source === "lens") {
    window.dispatchEvent(new CustomEvent("veritas:evidence-field", { detail: { field: next, source: "evidence-lens" } }));
  }
}

function openClaimGraph(preview, field) {
  const root = preview.closest("[data-audit-harness='true']");
  if (!root || !field) return;
  preview.dataset.evidenceLensState = "graph";
  const tab = root.querySelector("[data-reference-claim-tab]") || root.querySelector(".ah-tabs [data-ah-tab='claim-graph']");
  tab?.click();
  window.setTimeout(() => {
    const node = root.querySelector(`[data-cg-field="${CSS.escape(field)}"]`);
    if (!node) return;
    node.focus({ preventScroll: true });
    node.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
    node.scrollIntoView({ block: "center", inline: "center", behavior: "smooth" });
  }, 120);
}

function setPointer(preview, event) {
  const rect = preview.getBoundingClientRect();
  const x = Math.max(0, Math.min(rect.width, event.clientX - rect.left));
  const y = Math.max(0, Math.min(rect.height, event.clientY - rect.top));
  preview.style.setProperty("--lens-x", `${x}px`);
  preview.style.setProperty("--lens-y", `${y}px`);
  const nx = rect.width ? x / rect.width - 0.5 : 0;
  const ny = rect.height ? y / rect.height - 0.5 : 0;
  preview.style.setProperty("--lens-tilt-x", `${(-ny * 1.8).toFixed(2)}deg`);
  preview.style.setProperty("--lens-tilt-y", `${(nx * 2.4).toFixed(2)}deg`);
  preview.dataset.evidenceLensPointer = "active";
}

function resetPointer(preview) {
  preview.dataset.evidenceLensPointer = "idle";
  preview.style.setProperty("--lens-tilt-x", "0deg");
  preview.style.setProperty("--lens-tilt-y", "0deg");
}

function bindPreview(preview) {
  if (!preview || preview.dataset.evidenceLensBound === "true") return;
  preview.dataset.evidenceLensBound = "true";
  preview.dataset.evidenceLensState = "idle";
  preview.dataset.evidenceLensPointer = "idle";
  preview.dataset.evidenceLensPinned = "";

  const hud = document.createElement("aside");
  hud.className = "evidence-lens-hud";
  hud.dataset.evidenceLensHud = "true";
  hud.id = "evidence-lens-hud";
  hud.setAttribute("aria-live", "polite");
  preview.append(hud);
  renderHud(preview);

  const finePointer = window.matchMedia("(pointer: fine)").matches;
  let frame = 0;
  let latestPointer = null;
  if (finePointer) {
    preview.addEventListener("pointermove", (event) => {
      if (event.pointerType === "touch") return;
      latestPointer = event;
      if (!frame) {
        frame = requestAnimationFrame(() => {
          frame = 0;
          if (latestPointer) setPointer(preview, latestPointer);
        });
      }
    });
    preview.addEventListener("pointerleave", () => {
      latestPointer = null;
      resetPointer(preview);
      if (!preview.dataset.evidenceLensPinned) renderHud(preview);
    });
  }

  preview.querySelectorAll("[data-ref-field]").forEach((node) => {
    const field = node.dataset.refField || "";
    node.tabIndex = 0;
    node.setAttribute("role", "button");
    node.setAttribute("aria-controls", "evidence-lens-hud");
    node.setAttribute("aria-pressed", "false");
    node.setAttribute("aria-label", `${fieldLabel(field)} evidence value ${node.textContent?.trim() || ""}`);

    node.addEventListener("pointerenter", () => {
      node.dataset.lensHover = "true";
      if (!preview.dataset.evidenceLensPinned) {
        preview.dataset.evidenceLensState = "hover";
        renderHud(preview, field, "hover");
      }
    });
    node.addEventListener("pointerleave", () => {
      node.dataset.lensHover = "false";
      if (!preview.dataset.evidenceLensPinned) {
        preview.dataset.evidenceLensState = "idle";
        renderHud(preview);
      }
    });

    const toggle = () => {
      const next = preview.dataset.evidenceLensPinned === field ? "" : field;
      setPinned(preview, next, "lens");
    };
    node.addEventListener("click", toggle);
    node.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        toggle();
      } else if (event.key === "Escape") {
        event.preventDefault();
        setPinned(preview, "", "lens");
      }
    });
  });
}

function enhance() {
  const preview = activePreview();
  if (preview) bindPreview(preview);
}

window.addEventListener("veritas:evidence-field", (event) => {
  if (event.detail?.source === "evidence-lens") return;
  const preview = activePreview();
  if (!preview) return;
  const field = String(event.detail?.field || "");
  setPinned(preview, field, "graph");
});

new MutationObserver(enhance).observe(main || document.body, { childList: true, subtree: true });
window.addEventListener("hashchange", () => {
  const preview = activePreview();
  if (preview) setPinned(preview, "", "graph");
});
enhance();
