from __future__ import annotations

from veritas.harness.replication_workspace_product import (
    normalize_replication_event,
    normalize_replication_run,
)


def test_persisted_pending_permission_is_historical_not_actionable() -> None:
    value = {
        "run_id": "run_0123456789ab",
        "run_kind": "replication",
        "status": "success",
        "events": [
            {
                "event_id": "evt_permission",
                "kind": "replication",
                "payload": {
                    "agent_event": {
                        "kind": "permission",
                        "status": "review",
                        "detail": "Waiting for approval",
                        "payload": {
                            "request_id": "perm_0123456789ab",
                            "decision": "pending",
                            "options": [
                                {
                                    "kind": "allow_once",
                                    "optionId": "once",
                                    "name": "Allow once",
                                }
                            ],
                        },
                    }
                },
            }
        ],
    }

    normalized = normalize_replication_run(value)

    agent_event = normalized["events"][0]["payload"]["agent_event"]
    assert agent_event["payload"]["decision"] == "historical_pending"
    assert agent_event["status"] == "review"
    assert "no longer actionable" in agent_event["detail"]
    assert value["events"][0]["payload"]["agent_event"]["payload"]["decision"] == "pending"


def test_cancelled_replication_is_not_projected_as_failure() -> None:
    terminal = {
        "event_id": "evt_cancelled",
        "kind": "tool",
        "title": "Replication run failed",
        "detail": "ReplicationCancelledError: replication run cancelled by user",
        "status": "danger",
        "payload": {
            "tool": "replication.acp",
            "run_kind": "replication",
            "run_id": "run_0123456789ab",
            "phase": "error",
            "error_type": "ReplicationCancelledError",
            "result": {
                "status": "error",
                "verification_coverage": 0.0,
                "counts": {},
            },
        },
    }
    value = {
        "run_id": "run_0123456789ab",
        "run_kind": "replication",
        "task": "Replication run failed",
        "phase": "error",
        "status": "danger",
        "error_type": "ReplicationCancelledError",
        "events": [terminal],
    }

    live = normalize_replication_event(terminal)
    assert live["title"] == "Replication run cancelled"
    assert live["status"] == "review"
    assert live["payload"]["phase"] == "cancelled"
    assert live["payload"]["error_type"] is None
    assert live["payload"]["result"]["status"] == "cancelled"

    normalized = normalize_replication_run(value)
    assert normalized["task"] == "Replication run cancelled"
    assert normalized["phase"] == "cancelled"
    assert normalized["status"] == "review"
    assert normalized["error_type"] is None
    assert normalized["events"][0] == live

    assert terminal["title"] == "Replication run failed"
    assert terminal["status"] == "danger"
    assert terminal["payload"]["phase"] == "error"
