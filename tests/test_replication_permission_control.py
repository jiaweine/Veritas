from __future__ import annotations

import asyncio

import pytest

from veritas.replication.acp import _InteractiveControlPlane

_OPTIONS = (
    {"kind": "allow_always", "optionId": "forever", "name": "Always allow"},
    {"kind": "allow_once", "optionId": "once", "name": "Allow once"},
    {"kind": "reject_once", "optionId": "reject", "name": "Reject"},
)


def test_valid_permission_decision_is_consumed_exactly_once() -> None:
    async def scenario() -> None:
        control = _InteractiveControlPlane()
        run_id = "run_atomic1"
        request_id = "perm_atomic1"
        control.activate(run_id, interactive_permissions=True)

        pending = asyncio.create_task(
            control.request(run_id, request_id, _OPTIONS, timeout_seconds=1.0)
        )
        await asyncio.sleep(0)
        assert [item["request_id"] for item in control.state(run_id)["pending_permissions"]] == [
            request_id
        ]

        first = control.resolve(
            run_id,
            request_id,
            decision="allow_once",
            option_id="once",
        )
        assert first["selected_option_id"] == "once"
        assert control.state(run_id)["pending_permissions"] == []

        with pytest.raises(KeyError, match="not pending"):
            control.resolve(run_id, request_id, decision="reject")

        assert await pending == "once"
        control.deactivate(run_id)

    asyncio.run(scenario())


def test_invalid_allow_once_does_not_consume_pending_request() -> None:
    async def scenario() -> None:
        control = _InteractiveControlPlane()
        run_id = "run_atomic2"
        request_id = "perm_atomic2"
        control.activate(run_id, interactive_permissions=True)

        pending = asyncio.create_task(
            control.request(run_id, request_id, _OPTIONS, timeout_seconds=1.0)
        )
        await asyncio.sleep(0)

        with pytest.raises(ValueError, match="not an offered allow_once"):
            control.resolve(
                run_id,
                request_id,
                decision="allow_once",
                option_id="forever",
            )
        assert len(control.state(run_id)["pending_permissions"]) == 1

        rejected = control.resolve(run_id, request_id, decision="reject")
        assert rejected["selected_option_id"] is None
        assert await pending is None
        control.deactivate(run_id)

    asyncio.run(scenario())


def test_cancel_atomically_revokes_all_pending_approvals() -> None:
    async def scenario() -> None:
        control = _InteractiveControlPlane()
        run_id = "run_atomic3"
        request_id = "perm_atomic3"
        control.activate(run_id, interactive_permissions=True)

        pending = asyncio.create_task(
            control.request(run_id, request_id, _OPTIONS, timeout_seconds=1.0)
        )
        await asyncio.sleep(0)
        assert len(control.state(run_id)["pending_permissions"]) == 1

        assert control.cancel(run_id) is True
        state = control.state(run_id)
        assert state["cancel_requested"] is True
        assert state["pending_permissions"] == []

        with pytest.raises(KeyError, match="cancellation already requested"):
            control.resolve(
                run_id,
                request_id,
                decision="allow_once",
                option_id="once",
            )

        assert await pending is None
        control.deactivate(run_id)

    asyncio.run(scenario())
