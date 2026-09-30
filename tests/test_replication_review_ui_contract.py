from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_replication_review_ui_keeps_human_annotation_boundary_explicit() -> None:
    script = (ROOT / "src/veritas/harness/static/reproduction-review.js").read_text(
        encoding="utf-8"
    )
    styles = (ROOT / "src/veritas/harness/static/reproduction-review.css").read_text(
        encoding="utf-8"
    )
    shell = (ROOT / "src/veritas/harness/static/index.html").read_text(encoding="utf-8")

    assert 'value: "supports"' in script
    assert 'value: "contradicts"' in script
    assert 'value: "inconclusive"' in script
    assert "does not resolve the finding" in script
    assert "promote generated output to paper evidence" in script
    assert "/api/v1/runs/${encodeURIComponent(runId)}/review" in script
    assert "dataRepReviewSaved" in script
    assert "dataRepReviewDisposition" in script
    assert "data-rep-review-boundary" in script
    assert ".rep-review-card" in styles
    assert ".rep-review-option.selected" in styles
    assert "/static/reproduction-review.css" in shell
    assert "/static/reproduction-review.js" in shell


def test_finding_handoff_uses_api_canonical_binding_but_restores_detector_focus() -> None:
    navigation = (ROOT / "src/veritas/harness/static/finding-navigation.js").read_text(
        encoding="utf-8"
    )
    browser_smoke = (ROOT / "scripts/smoke_finding_replication_browser.py").read_text(
        encoding="utf-8"
    )

    assert "function replicationBindingId(index)" in navigation
    assert 'return `${findingState.auditId}:finding:${index}`' in navigation
    assert "function displayFindingId(findingId)" in navigation
    assert "fnReplicationFindingId" in navigation
    assert "openReplicationForFinding(finding, bindingId || findingId)" in navigation
    assert 'binding_id = f"{audit_id}:finding:0"' in browser_smoke
    assert 'data-fn-replication-finding-id' in browser_smoke
    assert "restore the exact finding focus" in browser_smoke


def test_real_browser_smoke_persists_review_without_mutating_detector_result() -> None:
    workflow = (ROOT / ".github/workflows/ui-visual-smoke.yml").read_text(encoding="utf-8")
    smoke = (ROOT / "scripts/smoke_replication_review_browser.py").read_text(encoding="utf-8")
    mobile = (ROOT / ".github/workflows/mobile.yml").read_text(encoding="utf-8")

    assert "python scripts/smoke_replication_review_browser.py" in workflow
    assert "--base-url http://127.0.0.1:8766" in workflow
    assert '"replication-review.png"' in smoke
    assert '"replication-review-persisted.png"' in smoke
    assert "_seed_contradiction_audit" in smoke
    assert 'binding_finding_id = f"{audit_id}:finding:0"' in smoke
    assert "detector_finding_id" in smoke
    assert "[data-rep-review-disposition='supports']" in smoke
    assert "generated outputs remain untrusted" in smoke
    assert "latest_result" in smoke
    assert "Operator review mutated the detector result or finding state" in smoke
    assert "node --check ../src/veritas/harness/static/reproduction-review.js" in mobile
