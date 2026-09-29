from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ui_visual_smoke_workflow_captures_product_surfaces() -> None:
    workflow = (ROOT / ".github/workflows/ui-visual-smoke.yml").read_text(encoding="utf-8")
    script = (ROOT / "scripts/smoke_harness_browser.py").read_text(encoding="utf-8")

    assert "python -m playwright install --with-deps chromium" in workflow
    assert "python scripts/smoke_harness_browser.py" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "veritas-ui-screenshots" in workflow

    assert '"audit-workspace.png"' in script
    assert '"audit-notes.png"' in script
    assert '"replication-workspace.png"' in script
    assert '"audit-mobile.png"' in script
    assert "[data-audit-harness='true']" in script
    assert "[data-reproduction-surface='true']" in script
    assert "Notes did not persist through the real browser save path" in script


def test_mobile_workflow_syntax_checks_all_workbench_modules() -> None:
    workflow = (ROOT / ".github/workflows/mobile.yml").read_text(encoding="utf-8")
    expected_modules = {
        "app.js",
        "audit-harness.js",
        "audit-harness-product.js",
        "audit-notes.js",
        "reproduction.js",
        "runs.js",
        "settings.js",
        "benchmarks.js",
    }

    for module in expected_modules:
        assert f"node --check ../src/veritas/harness/static/{module}" in workflow
