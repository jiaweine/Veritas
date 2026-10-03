from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_benchmarks_chromium_smoke_is_wired_into_visual_workflow() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ui-visual-smoke.yml").read_text(encoding="utf-8")
    script = (ROOT / "scripts" / "smoke_benchmarks_browser.py").read_text(encoding="utf-8")

    assert '"scripts/smoke_benchmarks_browser.py"' in workflow
    assert "python scripts/smoke_benchmarks_browser.py" in workflow
    assert '"benchmarks-workspace.png"' in script
    assert "[data-benchmark-surface='true']" in script
    assert 'wait_until="domcontentloaded"' in script
    assert 'wait_until="networkidle"' not in script
    assert 'page.locator(".sidebar [data-view=\'benchmarks\']")' in script
    assert "benchmarks_nav.click()" in script
    assert '"navigation": "sidebar-click"' in script
    assert '"auditbench-v1"' in script
    assert '"auditbench-v02-pack"' in script
    assert 'catalog.get("gating_count") != 5' in script
    assert 'catalog.get("non_gating_count") != 4' in script
    assert "No result envelope has been ingested locally yet." in script
    assert '"suite_count": 9' in script
    assert '"status": "success"' in script
