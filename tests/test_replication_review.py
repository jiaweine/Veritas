from __future__ import annotations

import pymupdf
from fastapi.testclient import TestClient

from veritas.harness.models import HarnessEvent
from veritas.harness.web import create_app


def _make_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((60, 72), "Synthetic replication review paper", fontsize=14)
    page.insert_text((60, 112), "Table 4. Main result", fontsize=11)
    page.insert_text((60, 145), "Treatment  -0.021  (0.026)", fontsize=10)
    payload = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return payload


def _seed_linked_run(client: TestClient, audit_id: str, run_id: str) -> dict[str, object]:
    origin = {
        "finding_id": f"{audit_id}:finding:0",
        "title": "Regression reporting contradiction",
        "severity": "needs_review",
        "source": {
            "page": 1,
            "table": "Table 4",
            "row": "Treatment",
            "column": "(1)",
        },
        "binding_only": True,
    }
    store = client.app.state.harness.store
    store.append_event(
        HarnessEvent(
            audit_id=audit_id,
            kind="tool",
            title="Replication started",
            status="running",
            payload={
                "tool": "replication.acp",
                "run_kind": "replication",
                "run_id": run_id,
                "phase": "start",
            },
        )
    )
    store.append_event(
        HarnessEvent(
            audit_id=audit_id,
            kind="replication_context",
            title="Scientific finding linked to replication",
            detail="Context binding only; agent completion does not resolve the finding.",
            payload={
                "tool": "replication.acp",
                "run_kind": "replication",
                "run_id": run_id,
                "phase": "context",
                "origin_finding": origin,
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
                "evidence": False,
            },
        )
    )
    return origin


def test_operator_review_is_append_only_and_does_not_resolve_finding(tmp_path) -> None:
    client = TestClient(create_app(tmp_path))
    created = client.post(
        "/api/v1/audits",
        data={"title": "Replication review paper"},
        files={"file": ("paper.pdf", _make_pdf(), "application/pdf")},
    )
    assert created.status_code == 200
    audit_id = created.json()["audit_id"]
    run_id = "run_review_boundary"
    origin = _seed_linked_run(client, audit_id, run_id)

    before = client.get(f"/api/v1/audits/{audit_id}").json()
    empty = client.get(f"/api/v1/runs/{run_id}/review")
    assert empty.status_code == 200
    assert empty.json()["review"] is None
    assert empty.json()["origin_finding"] == origin
    assert empty.json()["does_not_resolve_finding"] is True
    assert empty.json()["does_not_promote_evidence"] is True

    recorded = client.post(
        f"/api/v1/runs/{run_id}/review",
        json={
            "disposition": "supports",
            "note": "  The reproduced output is consistent with the detector concern.  ",
            "finding_id": "client-spoofed-finding",
        },
    )
    assert recorded.status_code == 200
    payload = recorded.json()
    assert payload["review"]["disposition"] == "supports"
    assert payload["review"]["note"] == "The reproduced output is consistent with the detector concern."
    assert payload["review"]["finding_id"] == origin["finding_id"]
    assert payload["review"]["review_only"] is True
    assert payload["review"]["does_not_resolve_finding"] is True
    assert payload["review"]["does_not_promote_evidence"] is True

    second = client.post(
        f"/api/v1/runs/{run_id}/review",
        json={"disposition": "inconclusive", "note": "Needs an independent evidence check."},
    )
    assert second.status_code == 200
    latest = client.get(f"/api/v1/runs/{run_id}/review").json()["review"]
    assert latest["disposition"] == "inconclusive"
    assert latest["note"] == "Needs an independent evidence check."

    run = client.get(f"/api/v1/runs/{run_id}").json()
    assert run["phase"] == "finish"
    assert run["origin_finding"] == origin
    reviews = [event for event in run["events"] if event["kind"] == "replication_review"]
    assert len(reviews) == 2
    assert all(event["status"] == "info" for event in reviews)
    assert reviews[-1]["payload"]["phase"] == "review"

    after = client.get(f"/api/v1/audits/{audit_id}").json()
    assert after["latest_result"] == before["latest_result"]
    assert after["paper_summary"] == before["paper_summary"]
    assert after["artifact_sha256"] == before["artifact_sha256"]


def test_replication_review_input_is_bounded_and_enumerated(tmp_path) -> None:
    client = TestClient(create_app(tmp_path))
    created = client.post(
        "/api/v1/audits",
        data={"title": "Review validation paper"},
        files={"file": ("paper.pdf", _make_pdf(), "application/pdf")},
    )
    assert created.status_code == 200
    audit_id = created.json()["audit_id"]
    run_id = "run_review_validation"
    _seed_linked_run(client, audit_id, run_id)

    invalid_disposition = client.post(
        f"/api/v1/runs/{run_id}/review",
        json={"disposition": "verified", "note": "Must not invent a stronger review state."},
    )
    assert invalid_disposition.status_code == 422

    oversized_note = client.post(
        f"/api/v1/runs/{run_id}/review",
        json={"disposition": "supports", "note": "x" * 4_001},
    )
    assert oversized_note.status_code == 422

    detail = client.get(f"/api/v1/runs/{run_id}").json()
    assert not [event for event in detail["events"] if event["kind"] == "replication_review"]


def test_replication_review_requires_linked_terminal_replication_run(tmp_path) -> None:
    client = TestClient(create_app(tmp_path))
    created = client.post(
        "/api/v1/audits",
        data={"title": "Review guard paper"},
        files={"file": ("paper.pdf", _make_pdf(), "application/pdf")},
    ).json()
    audit_id = created["audit_id"]
    store = client.app.state.harness.store

    store.append_event(
        HarnessEvent(
            audit_id=audit_id,
            kind="tool",
            title="Unlinked replication finished",
            payload={
                "tool": "replication.acp",
                "run_kind": "replication",
                "run_id": "run_unlinked",
                "phase": "finish",
            },
        )
    )
    unlinked = client.post(
        "/api/v1/runs/run_unlinked/review",
        json={"disposition": "inconclusive"},
    )
    assert unlinked.status_code == 409
    assert unlinked.json()["detail"] == "replication run is not linked to a finding"

    origin = {
        "finding_id": f"{audit_id}:finding:0",
        "title": "Linked finding",
        "severity": "needs_review",
        "source": {},
        "binding_only": True,
    }
    store.append_event(
        HarnessEvent(
            audit_id=audit_id,
            kind="replication_context",
            title="Linked running replication",
            payload={
                "tool": "replication.acp",
                "run_kind": "replication",
                "run_id": "run_running",
                "phase": "context",
                "origin_finding": origin,
            },
        )
    )
    running = client.post(
        "/api/v1/runs/run_running/review",
        json={"disposition": "supports"},
    )
    assert running.status_code == 409
    assert running.json()["detail"] == "replication run is not terminal"
