const main = document.querySelector("#main-content");

const escapeHtml = (value = "") => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

function cardLabel(card) {
  return card.querySelector(".provider-node-name strong")?.textContent?.trim()
    || card.dataset.modelProvider
    || "Provider";
}

function cardFamily(card) {
  return card.querySelector(".provider-node-name span")?.textContent?.trim() || "Model family";
}

function cardMeta(card) {
  return [...card.querySelectorAll(".provider-node-meta span")].map((node) => {
    const label = node.querySelector("b")?.textContent?.trim() || "DETAIL";
    const value = [...node.childNodes]
      .filter((child) => child.nodeType === Node.TEXT_NODE)
      .map((child) => child.textContent?.trim() || "")
      .filter(Boolean)
      .join(" ");
    return { label, value: value || "—" };
  });
}

function activeModel(router) {
  const rows = [...router.querySelectorAll(".router-telemetry > div")];
  const row = rows.find((item) => item.querySelector("span")?.textContent?.trim() === "MODEL ID");
  return row?.querySelector("strong")?.textContent?.trim() || "MODEL NOT PINNED";
}

function positionFloating(node, anchor, preferred = "below") {
  if (!node || !anchor) return;
  const rect = anchor.getBoundingClientRect();
  const nodeRect = node.getBoundingClientRect();
  const margin = 12;
  const width = Math.min(nodeRect.width || 360, window.innerWidth - margin * 2);
  let left = rect.left + rect.width / 2 - width / 2;
  left = Math.max(margin, Math.min(window.innerWidth - width - margin, left));
  let top = preferred === "above" ? rect.top - nodeRect.height - 10 : rect.bottom + 10;
  if (top + nodeRect.height > window.innerHeight - margin) top = rect.top - nodeRect.height - 10;
  if (top < margin) top = margin;
  node.style.left = `${Math.round(left)}px`;
  node.style.top = `${Math.round(top)}px`;
}

async function copyText(value, statusNode) {
  try {
    await navigator.clipboard.writeText(value);
    statusNode.textContent = "Copied";
  } catch {
    statusNode.textContent = "Clipboard unavailable";
  }
  window.setTimeout(() => { statusNode.textContent = ""; }, 1600);
}

function bindPowerInteractions(router) {
  if (!router || router.dataset.providerPower === "true") return;
  const cards = [...router.querySelectorAll("[data-model-provider]")];
  if (!cards.length) return;
  router.dataset.providerPower = "true";

  const quicklook = document.createElement("aside");
  quicklook.className = "provider-quicklook";
  quicklook.dataset.providerQuicklook = "true";
  quicklook.hidden = true;
  quicklook.setAttribute("role", "region");
  quicklook.setAttribute("aria-live", "polite");
  document.body.append(quicklook);

  const actions = document.createElement("div");
  actions.className = "provider-action-panel";
  actions.dataset.providerActionPanel = "true";
  actions.hidden = true;
  actions.setAttribute("role", "menu");
  actions.setAttribute("aria-label", "Provider actions");
  document.body.append(actions);

  let current = cards.find((card) => card.dataset.providerSelected === "true") || cards[0];
  let quicklookCard = null;
  let quicklookHeld = false;
  let quicklookSticky = false;
  let actionCard = null;

  const setRovingCard = (card, { focus = false } = {}) => {
    current = card;
    cards.forEach((item) => {
      item.tabIndex = item === card ? 0 : -1;
      item.dataset.rovingFocus = String(item === card);
    });
    if (focus) card.focus({ preventScroll: true });
    if (!quicklook.hidden && quicklookCard) showQuicklook(card, quicklookSticky ? "pinned" : "peek");
  };

  const quicklookMarkup = (card, mode) => {
    const meta = cardMeta(card);
    const selected = card.dataset.providerSelected === "true";
    const state = String(card.dataset.providerState || "available").replaceAll("_", " ").toUpperCase();
    const model = selected ? activeModel(router) : "Standby route";
    return `<div class="provider-quicklook-head"><div><span>${mode === "pinned" ? "QUICK LOOK // PINNED" : "QUICK LOOK // HOLD SPACE"}</span><strong>${escapeHtml(cardLabel(card))}</strong><small>${escapeHtml(cardFamily(card))}</small></div><kbd>SPACE</kbd></div>
      <div class="provider-quicklook-grid">
        <span><b>STATE</b>${escapeHtml(state)}</span>
        <span><b>ROUTE</b>${selected ? "ACTIVE" : "STANDBY"}</span>
        <span><b>MODEL</b>${escapeHtml(model)}</span>
        ${meta.slice(0, 3).map((item) => `<span><b>${escapeHtml(item.label)}</b>${escapeHtml(item.value)}</span>`).join("")}
      </div>
      <div class="provider-quicklook-foot"><span>← → / J K navigate</span><span>Enter pin</span><span>Shift+F10 actions</span><span>Esc close</span></div>`;
  };

  function showQuicklook(card, mode = "peek") {
    quicklookCard = card;
    quicklook.hidden = false;
    quicklook.dataset.mode = mode;
    quicklook.dataset.provider = card.dataset.modelProvider || "";
    quicklook.innerHTML = quicklookMarkup(card, mode);
    positionFloating(quicklook, card);
    card.dataset.quicklook = "true";
  }

  const hideQuicklook = () => {
    if (quicklookCard) quicklookCard.dataset.quicklook = "false";
    quicklookCard = null;
    quicklook.hidden = true;
    quicklook.dataset.mode = "idle";
    quicklook.dataset.provider = "";
  };

  const closeActions = ({ restoreFocus = false } = {}) => {
    actions.hidden = true;
    actions.dataset.provider = "";
    const card = actionCard;
    actionCard = null;
    if (restoreFocus && card) card.focus({ preventScroll: true });
  };

  const openActions = (card, point = null) => {
    actionCard = card;
    setRovingCard(card);
    const selected = card.dataset.providerSelected === "true";
    const pinned = card.dataset.pinned === "true";
    const probeButton = router.querySelector(".router-probe-button");
    const canProbe = selected && probeButton && !probeButton.disabled;
    const model = selected ? activeModel(router) : "";
    actions.innerHTML = `<div class="provider-action-head"><span>ACTION PANEL</span><strong>${escapeHtml(cardLabel(card))}</strong><small>Context actions never change provider configuration.</small></div>
      <div class="provider-action-list">
        <button type="button" role="menuitem" data-provider-action="pin"><span>${pinned ? "Unpin details" : "Pin details"}</span><kbd>Enter</kbd></button>
        <button type="button" role="menuitem" data-provider-action="quicklook"><span>${quicklookSticky ? "Close Quick Look" : "Keep Quick Look open"}</span><kbd>Space</kbd></button>
        <button type="button" role="menuitem" data-provider-action="copy-provider"><span>Copy provider ID</span><kbd>⌘C</kbd></button>
        ${model ? `<button type="button" role="menuitem" data-provider-action="copy-model"><span>Copy model ID</span><kbd>⌥C</kbd></button>` : ""}
        ${canProbe ? `<button type="button" role="menuitem" data-provider-action="probe"><span>Test active link</span><kbd>T</kbd></button>` : ""}
      </div>
      <div class="provider-action-status" aria-live="polite"></div>`;
    actions.hidden = false;
    actions.dataset.provider = card.dataset.modelProvider || "";
    if (point) {
      const width = 286;
      const height = Math.min(actions.getBoundingClientRect().height || 260, window.innerHeight - 24);
      actions.style.left = `${Math.max(12, Math.min(window.innerWidth - width - 12, point.x))}px`;
      actions.style.top = `${Math.max(12, Math.min(window.innerHeight - height - 12, point.y))}px`;
    } else {
      positionFloating(actions, card);
    }

    const statusNode = actions.querySelector(".provider-action-status");
    actions.querySelectorAll("[data-provider-action]").forEach((button) => {
      button.addEventListener("click", async () => {
        const action = button.dataset.providerAction;
        if (action === "pin") card.click();
        if (action === "quicklook") {
          quicklookSticky = !quicklookSticky;
          quicklookHeld = false;
          if (quicklookSticky) showQuicklook(card, "pinned");
          else hideQuicklook();
        }
        if (action === "copy-provider") await copyText(card.dataset.modelProvider || "", statusNode);
        if (action === "copy-model" && model) await copyText(model, statusNode);
        if (action === "probe" && canProbe) probeButton.click();
        if (!["copy-provider", "copy-model"].includes(action)) closeActions({ restoreFocus: true });
      });
    });

    requestAnimationFrame(() => actions.querySelector("[data-provider-action]")?.focus());
  };

  const move = (delta) => {
    const index = Math.max(0, cards.indexOf(current));
    const next = cards[(index + delta + cards.length) % cards.length];
    setRovingCard(next, { focus: true });
  };

  setRovingCard(current);

  cards.forEach((card) => {
    card.addEventListener("pointerdown", () => setRovingCard(card));
    card.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      openActions(card, { x: event.clientX, y: event.clientY });
    });
  });

  router.addEventListener("keydown", (event) => {
    const card = event.target.closest?.("[data-model-provider]");
    if (!card) return;
    setRovingCard(card);

    if (["ArrowRight", "ArrowDown", "j", "J"].includes(event.key)) {
      event.preventDefault();
      event.stopPropagation();
      move(1);
      return;
    }
    if (["ArrowLeft", "ArrowUp", "k", "K"].includes(event.key)) {
      event.preventDefault();
      event.stopPropagation();
      move(-1);
      return;
    }
    if (event.key === "Home") {
      event.preventDefault();
      setRovingCard(cards[0], { focus: true });
      return;
    }
    if (event.key === "End") {
      event.preventDefault();
      setRovingCard(cards[cards.length - 1], { focus: true });
      return;
    }
    if (event.key === " ") {
      event.preventDefault();
      event.stopPropagation();
      if (!event.repeat) {
        quicklookHeld = true;
        quicklookSticky = false;
        showQuicklook(card, "peek");
      }
      return;
    }
    if ((event.key === "F10" && event.shiftKey) || event.key === "ContextMenu") {
      event.preventDefault();
      event.stopPropagation();
      openActions(card);
      return;
    }
    if (event.key === "Escape") {
      closeActions();
      quicklookHeld = false;
      quicklookSticky = false;
      hideQuicklook();
    }
  }, true);

  router.addEventListener("keyup", (event) => {
    if (event.key !== " ") return;
    event.preventDefault();
    event.stopPropagation();
    quicklookHeld = false;
    if (!quicklookSticky) hideQuicklook();
  }, true);

  actions.addEventListener("keydown", (event) => {
    const items = [...actions.querySelectorAll("[role='menuitem']")];
    if (!items.length) return;
    const index = Math.max(0, items.indexOf(document.activeElement));
    if (event.key === "ArrowDown") {
      event.preventDefault();
      items[(index + 1) % items.length].focus();
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      items[(index - 1 + items.length) % items.length].focus();
    }
    if (event.key === "Escape") {
      event.preventDefault();
      closeActions({ restoreFocus: true });
    }
  });

  document.addEventListener("pointerdown", (event) => {
    if (actions.hidden) return;
    if (actions.contains(event.target) || actionCard?.contains(event.target)) return;
    closeActions();
  });

  window.addEventListener("resize", () => {
    if (!quicklook.hidden && quicklookCard) positionFloating(quicklook, quicklookCard);
    if (!actions.hidden && actionCard) positionFloating(actions, actionCard);
  });
}

function enhance() {
  const router = main?.querySelector("[data-model-provider-matrix='true']");
  if (router) bindPowerInteractions(router);
}

new MutationObserver(enhance).observe(main || document.body, { childList: true, subtree: true });
enhance();
