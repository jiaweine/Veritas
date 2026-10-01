from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_provider_power_interactions_are_wired_and_accessible() -> None:
    script = (ROOT / "src/veritas/harness/static/settings-power-interactions.js").read_text(
        encoding="utf-8"
    )
    styles = (ROOT / "src/veritas/harness/static/settings-power-interactions.css").read_text(
        encoding="utf-8"
    )
    shell = (ROOT / "src/veritas/harness/static/index.html").read_text(encoding="utf-8")
    service_worker = (ROOT / "src/veritas/harness/static/sw.js").read_text(encoding="utf-8")
    browser = (ROOT / "scripts/smoke_provider_power_interactions_browser.py").read_text(
        encoding="utf-8"
    )
    workflow = (ROOT / ".github/workflows/ui-visual-smoke.yml").read_text(encoding="utf-8")
    mobile = (ROOT / ".github/workflows/mobile.yml").read_text(encoding="utf-8")

    # Source uses DOMStringMap camelCase assignments. The browser acceptance below
    # verifies that these materialize as the expected data-* attributes at runtime.
    assert 'quicklook.dataset.providerQuicklook = "true"' in script
    assert 'actions.dataset.providerActionPanel = "true"' in script
    assert 'data-roving-focus' not in script  # DOM dataset uses camelCase assignment
    assert "rovingFocus" in script
    assert 'event.key === " "' in script
    assert 'event.key === "F10"' in script
    assert 'event.key === "ContextMenu"' in script
    assert '["ArrowRight", "ArrowDown", "j", "J"].includes(event.key)' in script
    assert '["ArrowLeft", "ArrowUp", "k", "K"].includes(event.key)' in script
    assert 'event.key === "Escape"' in script
    assert "closeTopContextLayer" in script
    assert 'event.stopPropagation();' in script
    assert 'item.dataset.quicklook = String(item === card)' in script
    assert 'else activePowerCleanup?.();' in script
    assert 'controller.abort();' in script
    assert 'role", "menu"' in script
    assert 'role="menuitem"' in script
    assert "navigator.clipboard.writeText" in script
    assert 'successLabel: "Copied provider ID ✓"' in script
    assert ".provider-quicklook" in styles
    assert ".provider-action-panel" in styles
    assert ".provider-node[data-roving-focus=\"true\"]" in styles
    assert "(pointer: coarse)" in styles
    assert "prefers-reduced-motion" in styles
    assert '/static/settings-power-interactions.css' in shell
    assert '/static/settings-power-interactions.js' in shell
    assert '/static/settings-power-interactions.css' in service_worker
    assert '/static/settings-power-interactions.js' in service_worker
    assert 'const CACHE = "veritas-shell-v28"' in service_worker
    assert '"settings-provider-quicklook.png"' in browser
    assert '"settings-provider-actions.png"' in browser
    assert '"settings-provider-action-feedback.png"' in browser
    assert "page.keyboard.down(\"Space\")" in browser
    assert "page.keyboard.press(\"j\")" in browser
    assert "click(button=\"right\"" in browser
    assert 'data-quicklook=\'true\'' in browser
    assert "Provider ID copied" in browser
    assert "First Escape" in browser
    assert "Second Escape" in browser
    assert "Third Escape" not in browser  # final unpin is asserted by state, not prose only
    assert "python scripts/smoke_provider_power_interactions_browser.py" in workflow
    assert "settings-power-interactions.js" in mobile
