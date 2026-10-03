from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_premium_provider_navigation_is_wired_and_accessible() -> None:
    script = (
        ROOT / "src/veritas/harness/static/settings-premium-navigation.js"
    ).read_text(encoding="utf-8")
    styles = (
        ROOT / "src/veritas/harness/static/settings-premium-navigation.css"
    ).read_text(encoding="utf-8")
    shell = (ROOT / "src/veritas/harness/static/index.html").read_text(encoding="utf-8")
    service_worker = (ROOT / "src/veritas/harness/static/sw.js").read_text(encoding="utf-8")
    mobile_workflow = (ROOT / ".github/workflows/mobile.yml").read_text(encoding="utf-8")
    ui_workflow = (ROOT / ".github/workflows/ui-visual-smoke.yml").read_text(encoding="utf-8")
    browser = (
        ROOT / "scripts/smoke_provider_premium_navigation_browser.py"
    ).read_text(encoding="utf-8")

    assert "nearestDirectionalCard" in script
    assert "getBoundingClientRect" in script
    assert "stopImmediatePropagation" in script
    assert "aria-keyshortcuts" in script
    assert "data.pressed" not in script
    assert 'card.dataset.pressed = "true"' in script
    assert "provider-activation-wave" in script
    assert "prefers-reduced-motion: reduce" in styles
    assert "provider-edge-left" in styles
    assert "provider-edge-right" in styles
    assert "provider-edge-up" in styles
    assert "provider-edge-down" in styles
    assert "settings-premium-navigation.css" in shell
    assert "settings-premium-navigation.js" in shell
    assert "settings-premium-navigation.css" in service_worker
    assert "settings-premium-navigation.js" in service_worker
    assert "node --check ../src/veritas/harness/static/settings-premium-navigation.js" in mobile_workflow
    assert "smoke_provider_premium_navigation_browser.py" in ui_workflow
    assert "settings-provider-spatial-navigation.png" in browser
    assert "settings-provider-press-feedback.png" in browser
    assert "openai_compatible" in browser
