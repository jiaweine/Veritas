const main = document.querySelector("#main-content");
let activePremiumCleanup = null;

const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
const finePointer = window.matchMedia("(pointer: fine)");

function providerCards(router) {
  return [...router.querySelectorAll("[data-model-provider]")];
}

function centerOf(node) {
  const rect = node.getBoundingClientRect();
  return {
    x: rect.left + rect.width / 2,
    y: rect.top + rect.height / 2,
  };
}

function nearestDirectionalCard(cards, current, key) {
  const origin = centerOf(current);
  const horizontal = key === "ArrowLeft" || key === "ArrowRight";
  const sign = key === "ArrowLeft" || key === "ArrowUp" ? -1 : 1;
  const candidates = cards
    .filter((card) => card !== current)
    .map((card) => {
      const point = centerOf(card);
      const dx = point.x - origin.x;
      const dy = point.y - origin.y;
      const primary = horizontal ? dx : dy;
      const cross = horizontal ? dy : dx;
      if (primary * sign <= 4) return null;
      const score = Math.abs(primary) + Math.abs(cross) * 0.42;
      return { card, score, primary: Math.abs(primary), cross: Math.abs(cross) };
    })
    .filter(Boolean)
    .sort((a, b) => a.score - b.score || a.primary - b.primary || a.cross - b.cross);
  return candidates[0]?.card || null;
}

function syncLegacyRoving(card, cards) {
  cards.forEach((item) => {
    const active = item === card;
    item.tabIndex = active ? 0 : -1;
    item.dataset.rovingFocus = String(active);
  });
  card.focus({ preventScroll: true });
  try {
    card.dispatchEvent(new PointerEvent("pointerdown", {
      bubbles: false,
      cancelable: false,
      pointerType: "touch",
      isPrimary: true,
    }));
  } catch {
    // Focus and tabindex remain authoritative if PointerEvent is unavailable.
  }
}

function edgeDirection(key) {
  if (key === "ArrowLeft") return "left";
  if (key === "ArrowRight") return "right";
  if (key === "ArrowUp") return "up";
  return "down";
}

function nudgeEdge(card, key) {
  card.dataset.navEdge = edgeDirection(key);
  window.clearTimeout(Number(card.dataset.navEdgeTimer || 0));
  const timer = window.setTimeout(() => {
    delete card.dataset.navEdge;
    delete card.dataset.navEdgeTimer;
  }, reducedMotion.matches ? 40 : 190);
  card.dataset.navEdgeTimer = String(timer);
}

function pulseActivation(card, event) {
  if (!finePointer.matches || reducedMotion.matches) return;
  const rect = card.getBoundingClientRect();
  const x = Math.max(0, Math.min(rect.width, event.clientX - rect.left));
  const y = Math.max(0, Math.min(rect.height, event.clientY - rect.top));
  const wave = document.createElement("span");
  wave.className = "provider-activation-wave";
  wave.setAttribute("aria-hidden", "true");
  wave.style.setProperty("--wave-x", `${x}px`);
  wave.style.setProperty("--wave-y", `${y}px`);
  card.append(wave);
  wave.addEventListener("animationend", () => wave.remove(), { once: true });
  window.setTimeout(() => wave.remove(), 650);
}

function bindPremiumNavigation(router) {
  if (!router || router.dataset.premiumNavigation === "true") return;
  const cards = providerCards(router);
  if (!cards.length) return;

  activePremiumCleanup?.();
  router.dataset.premiumNavigation = "true";
  const controller = new AbortController();
  const signal = controller.signal;
  let lifecycleObserver = null;
  let pressedCard = null;

  const selected = cards.find((card) => card.dataset.providerSelected === "true") || cards[0];
  cards.forEach((card) => {
    card.setAttribute(
      "aria-keyshortcuts",
      "ArrowLeft ArrowRight ArrowUp ArrowDown Home End Enter Space Escape Shift+F10"
    );
    card.dataset.premiumNavigation = "true";
  });
  syncLegacyRoving(selected, cards);

  const releasePress = () => {
    if (!pressedCard) return;
    pressedCard.dataset.pressed = "false";
    pressedCard = null;
  };

  cards.forEach((card) => {
    card.addEventListener("pointerdown", (event) => {
      if (!event.isTrusted || event.pointerType === "touch" || event.button !== 0) return;
      releasePress();
      pressedCard = card;
      card.dataset.pressed = "true";
      const rect = card.getBoundingClientRect();
      card.style.setProperty("--press-x", `${event.clientX - rect.left}px`);
      card.style.setProperty("--press-y", `${event.clientY - rect.top}px`);
    }, { signal });
    card.addEventListener("pointerup", releasePress, { signal });
    card.addEventListener("pointercancel", releasePress, { signal });
    card.addEventListener("lostpointercapture", releasePress, { signal });
    card.addEventListener("click", (event) => {
      if (event.detail > 0) pulseActivation(card, event);
    }, { signal });
  });

  document.addEventListener("keydown", (event) => {
    const card = event.target?.closest?.("[data-model-provider]");
    if (!card || !router.contains(card)) return;

    if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) {
      event.preventDefault();
      event.stopImmediatePropagation();
      const next = nearestDirectionalCard(cards, card, event.key);
      if (next) {
        router.dataset.navigationMode = "spatial";
        router.dataset.navigationVector = edgeDirection(event.key);
        syncLegacyRoving(next, cards);
      } else {
        router.dataset.navigationMode = "edge";
        router.dataset.navigationVector = edgeDirection(event.key);
        nudgeEdge(card, event.key);
      }
      return;
    }

    if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      event.stopImmediatePropagation();
      router.dataset.navigationMode = "jump";
      router.dataset.navigationVector = event.key.toLowerCase();
      syncLegacyRoving(event.key === "Home" ? cards[0] : cards[cards.length - 1], cards);
    }
  }, { capture: true, signal });

  document.addEventListener("pointerdown", () => {
    router.dataset.navigationMode = "pointer";
    router.dataset.navigationVector = "";
  }, { signal });

  const cleanup = () => {
    controller.abort();
    lifecycleObserver?.disconnect();
    releasePress();
    cards.forEach((card) => {
      delete card.dataset.premiumNavigation;
      delete card.dataset.navEdge;
      delete card.dataset.navEdgeTimer;
      delete card.dataset.pressed;
      card.removeAttribute("aria-keyshortcuts");
      card.querySelectorAll(".provider-activation-wave").forEach((wave) => wave.remove());
    });
    if (activePremiumCleanup === cleanup) activePremiumCleanup = null;
  };
  activePremiumCleanup = cleanup;

  lifecycleObserver = new MutationObserver(() => {
    if (!router.isConnected) cleanup();
  });
  lifecycleObserver.observe(main || document.body, { childList: true, subtree: true });
}

function enhance() {
  const router = main?.querySelector("[data-model-provider-matrix='true']");
  if (router) bindPremiumNavigation(router);
  else activePremiumCleanup?.();
}

new MutationObserver(enhance).observe(main || document.body, { childList: true, subtree: true });
enhance();
