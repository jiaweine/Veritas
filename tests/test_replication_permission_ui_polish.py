from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_permission_review_surface_is_one_shot_accessible_and_browser_gated() -> None:
    review_js = (
        ROOT / "src/veritas/harness/static/reproduction-review.js"
    ).read_text(encoding="utf-8")
    review_css = (
        ROOT / "src/veritas/harness/static/reproduction-review.css"
    ).read_text(encoding="utf-8")
    browser = (
        ROOT / "scripts/smoke_replication_permission_polish_browser.py"
    ).read_text(encoding="utf-8")
    workflow = (
        ROOT / ".github/workflows/replication-permission-ui-smoke.yml"
    ).read_text(encoding="utf-8")

    assert "data-permission-enhanced" in browser
    assert "data-permission-submitting" in browser
    assert "Never remembered" in review_js
    assert "One operation" in review_js
    assert "Sensitive operation approval" in review_js
    assert "historical request cannot be approved again" in review_js
    assert "permissionSubmitting" in review_js
    assert 'actions.setAttribute("aria-busy", "true")' in review_js
    assert "buttons.forEach((candidate) => { candidate.disabled = true; })" in review_js
    assert "allow_always" not in review_js

    assert ".rep-permission.rep-permission-surface" in review_css
    assert "--permission-x" in review_css
    assert "rep-permission-energy" in review_css
    assert "prefers-reduced-motion" in review_css
    assert "min-height: 32px" in review_css

    assert "smoke_replication_permission_browser.py" in workflow
    assert "smoke_replication_permission_polish_browser.py" in workflow
    assert "actions/upload-artifact@v7" in workflow
