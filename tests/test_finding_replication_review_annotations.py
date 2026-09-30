from __future__ import annotations

import pymupdf
from fastapi.testclient import TestClient

from veritas.harness.models import HarnessEvent
from veritas.harness.web import create_app


def _make_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((60, 72), "Finding review projection paper", fontsize=14)
    page.insert_text((60, 112), "Table 4. Main result", fontsize=11)
    page.insert_text((60, 145), "Treatment  -0.021  (0.026)", fontsize=10)
    payload = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return payload


def _seed_linked_terminal_run(
    client: TestClient,
    audit_id: str,
    run_id: str,
    *,
    finding_index: int = 0,
) -> str:
    finding_id = f"{audit_id}:finding:{finding_index}"
    store = client.app.state.harness.store
    store.append_event(
        HarnessEvent(
            audit_id=audit_id,
            kind="replication_context",
            title="Scientific finding linked to replication",
            payload={
                "tool": "replication.acp",
                "run_kind": "replication",
                "run_id": run_id,
                "phase": "context",
                "origin_finding": {
                    "finding_id": finding_id,
                    "title": "Regression reporting contradiction",
                    "severity": "contradiction",
                    "source": {"page": 1, "table": "Table 4", "row": "Treatment"},
                    "binding_only": True,
                },
            },
        )
    )
    store.append_event(
        HarnessEvent(
            audit_id=audit_id,
            kind="tool",
            title="Replication finished",
            status="success",
            payload={
                "tool": "replication.acp",
                "run_kind": "replication",
                "run_id": run_id,
                "phase": "finish",
                "result": {"status": "completed", "verification_coverage": 0.0, "counts": {}},
            },
        )
    )
    return finding_id


def test_audit_review_projection_returns_latest_review_per_linked_run(tmp_path) -> None:
    client = TestClient(create_app(tmp_path))
    created = client.post(
        "/api/v1/audits",
        data={"title": "Finding review projection"},
        files={"file": ("paper.pdf", _make_pdf(), "application/pdf")},
    )
    assert created.status_code == 200
    audit_id = created.json()["audit_id"]

    first_binding = _seed_linked_terminal_run(client, audit_id, "run_projection_first")
    second_binding = _seed_linked_terminal_run(
        client,
        audit_id,
        "run_projection_second",
        finding_index=1,
    )

    first_review = client.post(
        "/api/v1/runs/run_projection_first/review",
        json={"disposition": "supports", "note": "First operator pass."},
    )
    assert first_review.status_code == 200
    second_review = client.post(
        "/api/v1/runs/run_projection_first/review",
        json={"disposition": "inconclusive", "note": "Later operator pass."},
    )
    assert second_review.status_code == 200
    other_review = client.post(
        "/api/v1/runs/run_projection_second/review",
        json={"disposition": "contradicts", "note": "Different linked finding."},
    )
    assert other_review.status_code == 200

    projected = client.get(f"/api/v1/audits/{audit_id}/replication-reviews")
    assert projected.status_code == 200
    payload = projected.json()
    assert payload["audit_id"] == audit_id
    assert payload["review_only"] is True
    assert payload["does_not_resolve_finding"] is True
    assert payload["does_not_promote_evidence"] is True

    by_run = {item["run_id"]: item for item in payload["items"]}
    assert set(by_run) == {"run_projection_first", "run_projection_second"}
    first = by_run["run_projection_first"]
    assert first["origin_finding"]["finding_id"] == first_binding
    assert first["review_count"] == 2
    assert first["review"]["disposition"] == "inconclusive"
    assert first["review"]["note"] == "Later operator pass."
    assert first["does_not_resolve_finding"] is True
    assert first["does_not_promote_evidence"] is True

    second = by_run["run_projection_second"]
    assert second["origin_finding"]["finding_id"] == second_binding
    assert second["review_count"] == 1
    assert second["review"]["disposition"] == "contradicts"


def test_audit_review_projection_fails_closed_for_unlinked_review_history(tmp_path) -> None:
    client = TestClient(create_app(tmp_path))
    created = client.post(
        "/api/v1/audits",
        data={"title": "Malformed review history"},
        files={"file": ("paper.pdf", _make_pdf(), "application/pdf")},
    ).json()
    audit_id = created["audit_id"]
    client.app.state.harness.store.append_event(
        HarnessEvent(
            audit_id=audit_id,
            kind="replication_review",
            title="Malformed review event",
            payload={
                "tool": "replication.review",
                "run_kind": "replication",
                "run_id": "run_orphan_review",
                "phase": "review",
                "review": {
                    "disposition": "supports",
                    "note": "Must not be projected without server-owned finding context.",
                    "finding_id": "fabricated",
                },
            },
        )
    )

    projected = client.get(f"/api/v1/audits/{audit_id}/replication-reviews")
    assert projected.status_code == 200
    assert projected.json()["items"] == []


def test_finding_review_annotation_ui_keeps_review_separate_from_evidence() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    script = (root / "src/veritas/harness/static/finding-replication-review.js").read_text(
        encoding="utf-8"
    )
    styles = (root / "src/veritas/harness/static/finding-replication-review.css").read_text(
        encoding="utf-8"
    )
    shell = (root / "src/veritas/harness/static/index.html").read_text(encoding="utf-8")
    mobile = (root / ".github/workflows/mobile.yml").read_text(encoding="utf-8")

    assert "/api/v1/audits/${encodeURIComponent(auditId)}/replication-reviews" in script
    assert "data-fn-replication-finding-id" in script
    assert '"veritas.replication.run.focus.v1"' in script
    assert "finding unchanged · generated outputs untrusted" in script
    assert "data-finding-replication-review" in script or "findingReplicationReview" in script
    assert "data-open-reviewed-run" in script
    assert ".fn-replication-review" in styles
    assert "/static/finding-replication-review.css" in shell
    assert "/static/finding-replication-review.js" in shell
    assert "node --check ../src/veritas/harness/static/finding-replication-review.js" in mobile
