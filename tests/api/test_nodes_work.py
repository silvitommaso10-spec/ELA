"""The three routes of the work, through the real application (M12.2; ADR 0038 §11, §12).

Every status is **observed**, never declared: a node enrolled through the routes of M12.1 asks
for work, brings it back, asks for more time, and what comes back is read off the response and
out of the audit. The id of the assignment travels in the **body** on purpose (dec. I):
``NODE_ROUTES`` is a set of literal pairs, so with the id in the path a node would have been
refused by the middleware while the Core's token reached the handler.

**What this file does not do yet**: reach the work through ``POST /tasks/{id}/run``. That route
walks the plan at the strictest privacy, so a ``TRUSTED`` node is refused ``PRIVACY`` until the
commit that brings the sensitivity of a task (criterion 32, dec. O) — here the walk is the
runner's, with the privacy a declared task will carry, and the whole turn through HTTP is what
``tests/conformance`` does. The ``409`` of the cap stays where the cap is decided
(``tests/executive``): making it observable here would mean waiting real time.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from ela.api.nodes import work_order
from ela.composition import Ela
from ela.domain import (
    AuditEventType,
    DeviceId,
    ExecutionStatus,
    PrivacyLevel,
    TaskId,
)
from ela.executive import Claimed, RunOutcome, WorkRejection
from tests.api.support import echo_plan, queued
from tests.api.test_nodes import enrolled, written

ENVELOPE: dict[str, Any] = {
    "form": "result",
    "status": "SUCCEEDED",
    "output": {"message": "ciao"},
    "duration_ms": 12,
    "node": {"finished_at": "2026-09-11T08:00:02Z"},
}
"""What a node delivers when its tool answered: its half of the run, and nothing the Core knows."""


async def a_node(client: AsyncClient, ela: Ela) -> tuple[str, dict[str, str]]:
    """A node enrolled, beating and built to win: every tool of this ELA, on power, idle."""
    device_id, headers = await enrolled(
        client, "TRUSTED", available_tools=[tool.name for tool in ela.tools.tools()]
    )
    await client.post(
        "/nodes/heartbeat", json={"status": "IDLE", "power_source": "AC"}, headers=headers
    )
    return device_id, headers


async def work_for(client: AsyncClient, ela: Ela) -> tuple[str, str, dict[str, str]]:
    """A task whose one step is handed to that node: the task id, the node id, its header.

    The walk is the runner's, with the privacy a declared task will carry — the route that walks it
    learns about sensitivity in the next commit.
    """
    device_id, headers = await a_node(client, ela)
    task_id = await queued(client, echo_plan())
    run = await ela.runner.run(TaskId(UUID(task_id)), max_privacy=PrivacyLevel.TRUSTED)
    assert run.outcome is RunOutcome.ASSIGNED, run.outcome
    return task_id, device_id, headers


async def taken(
    client: AsyncClient, ela: Ela
) -> tuple[str, dict[str, Any], dict[str, str], DeviceId]:
    """Work asked for and taken: the task id, the order, the node's header and its id.

    The id comes from the enrollment and not from the order: a decision is about a capability, and
    which node runs it is the assignment's — the order carries the call, and nothing else.
    """
    task_id, device_id, headers = await work_for(client, ela)
    answered = await client.post("/nodes/work", headers=headers)
    assert answered.status_code == 200, answered.text
    return task_id, dict(answered.json()), headers, DeviceId(UUID(device_id))


async def rejections(ela: Ela) -> list[dict[str, Any]]:
    return [dict(event.payload) for event in await written(ela, AuditEventType.DEVICE_REJECTED)]


# ----------------------------------------------------------------------------------------
# Asking for work: the order, and nothing else (criterion 6)
# ----------------------------------------------------------------------------------------


async def test_the_order_carries_the_call_and_nothing_else(client: AsyncClient, ela: Ela) -> None:
    """Criterion 6, a closed world on the keys: an order that carried the success conditions or the
    name of the verifier — the verification, which happens here — is not this set."""
    task_id, order, _, _ = await taken(client, ela)

    assert set(order) == {
        "assignment_id",
        "capability_id",
        "tool_name",
        "decision",
        "arguments",
        "expires_at",
    }
    assert order["capability_id"] == "core.echo"
    assert order["arguments"] == {"message": "ciao"}
    assert order["decision"]["outcome"] == "ALLOWED"
    assert order["decision"]["task_id"] == task_id


async def test_a_node_with_nothing_waiting_is_told_so(client: AsyncClient, ela: Ela) -> None:
    """``204`` and no body: the window is held and then the node asks again, which is what makes
    the long-poll degrade into polling by itself."""
    _, headers = await a_node(client, ela)

    answered = await client.post("/nodes/work", headers=headers)

    assert answered.status_code == 204
    assert answered.content == b""


async def test_a_second_request_while_the_work_is_in_hand_gets_nothing(
    client: AsyncClient, ela: Ela
) -> None:
    """One assignment taken per node (D16): the offer of another task waits until this one is back,
    and the node is told "nothing" rather than handed a second piece of work."""
    _, _, headers, _ = await taken(client, ela)
    second = await queued(client, echo_plan())
    assert (
        await ela.runner.run(TaskId(UUID(second)), max_privacy=PrivacyLevel.TRUSTED)
    ).outcome is RunOutcome.ASSIGNED

    answered = await client.post("/nodes/work", headers=headers)

    assert answered.status_code == 204


async def test_the_work_of_one_node_never_comes_out_for_another(
    client: AsyncClient, ela: Ela
) -> None:
    """The offer is for the node the Core chose, and another node asking gets nothing — not an
    error, because there is nothing to tell it about somebody else's work."""
    await work_for(client, ela)
    _, other = await enrolled(client, "TRUSTED", available_tools=["core-echo"])

    answered = await client.post("/nodes/work", headers=other)

    assert answered.status_code == 204


def test_the_composer_refuses_an_order_for_another_node() -> None:
    """Criterion 21, the half an AST cannot see: the composer compares the identity that asked with
    the one the assignment names, and raises instead of composing."""

    class _Assignment:
        id = uuid4()
        device_id = DeviceId(uuid4())

    claimed = Claimed(_Assignment(), "core-echo", {})  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="belongs to another node"):
        work_order(claimed, DeviceId(uuid4()))


# ----------------------------------------------------------------------------------------
# Bringing it back: the seven cases (criterion 16)
# ----------------------------------------------------------------------------------------


async def test_a_delivery_closes_the_step_and_says_where_everything_stands(
    client: AsyncClient, ela: Ela
) -> None:
    task_id, order, headers, device_id = await taken(client, ela)

    delivered = await client.post(
        "/nodes/work/result",
        json={"assignment_id": order["assignment_id"], **ENVELOPE},
        headers=headers,
    )

    assert delivered.status_code == 200, delivered.text
    assert delivered.json() == {
        "assignment_id": order["assignment_id"],
        "state": "DELIVERED",
        "step": "COMPLETED",
    }
    assert (await client.post(f"/tasks/{task_id}/run")).json()["outcome"] == "completed"


async def test_the_same_delivery_twice_is_the_same_answer_and_nothing_new(
    client: AsyncClient, ela: Ela
) -> None:
    """A network that retries is not an action (ADR 0016 §6): one stored result, no new event."""
    task_id, order, headers, device_id = await taken(client, ela)
    body = {"assignment_id": order["assignment_id"], **ENVELOPE}
    first = await client.post("/nodes/work/result", json=body, headers=headers)
    events = len(await ela.audit.read())

    again = await client.post("/nodes/work/result", json=body, headers=headers)

    assert again.status_code == 200
    assert again.json() == first.json()
    assert len(await ela.audit.read()) == events
    stored = (await client.get(f"/tasks/{task_id}/results")).json()
    assert len([one for one in stored if one["status"] != "STARTED"]) == 1


async def test_a_second_envelope_is_a_conflict_and_the_first_one_stands(
    client: AsyncClient, ela: Ela
) -> None:
    _, order, headers, device_id = await taken(client, ela)
    await client.post(
        "/nodes/work/result",
        json={"assignment_id": order["assignment_id"], **ENVELOPE},
        headers=headers,
    )

    other = await client.post(
        "/nodes/work/result",
        json={"assignment_id": order["assignment_id"], **ENVELOPE, "output": {"message": "altro"}},
        headers=headers,
    )

    assert other.status_code == 409
    assert other.json()["error"]["code"] == "delivery.conflict"
    assert (await rejections(ela))[-1]["reason"] == WorkRejection.DELIVERY_CONFLICT.value


async def test_work_this_node_does_not_hold_is_the_same_404_for_both_reasons(
    client: AsyncClient, ela: Ela
) -> None:
    """One answer for an id the Core never minted and for another node's work — a node is told
    nothing about work that is not its own — and two reasons in the audit, which criterion 16 asks
    for because the two facts are different."""
    _, order, headers, device_id = await taken(client, ela)
    _, other = await enrolled(client, "TRUSTED", available_tools=["core-echo"])

    unknown = await client.post(
        "/nodes/work/result", json={"assignment_id": str(uuid4()), **ENVELOPE}, headers=headers
    )
    not_mine = await client.post(
        "/nodes/work/result",
        json={"assignment_id": order["assignment_id"], **ENVELOPE},
        headers=other,
    )

    assert unknown.status_code == not_mine.status_code == 404
    assert unknown.json() == not_mine.json()  # the same sentence, or the difference is the answer
    assert order["assignment_id"] not in str(unknown.json())
    reasons = [one for one in await rejections(ela) if one["reason"] == "not_assigned"]
    assert [one["assignment_known"] for one in reasons] == [False, True]


async def test_a_late_delivery_is_refused_and_the_audit_keeps_what_it_reported(
    client: AsyncClient, ela: Ela
) -> None:
    """The revocation brings the expiry to ``now`` (D17), which is how a late delivery is built here
    without waiting: the work is over, the node does not know it yet, and what it reports is kept as
    its word — the status, never the output."""
    task_id, order, headers, device_id = await taken(client, ela)
    await ela.assignments.cut_short(device_id)

    late = await client.post(
        "/nodes/work/result",
        json={"assignment_id": order["assignment_id"], **ENVELOPE},
        headers=headers,
    )

    assert late.status_code == 410
    assert late.json()["error"]["code"] == "assignment.expired"
    refusal = (await rejections(ela))[-1]
    assert refusal["reason"] == WorkRejection.LATE.value
    assert refusal["reported_status"] == ExecutionStatus.SUCCEEDED.value
    assert "ciao" not in str(refusal)


async def test_a_delivery_for_a_task_the_user_stopped_is_void(
    client: AsyncClient, ela: Ela
) -> None:
    task_id, order, headers, device_id = await taken(client, ela)
    await client.post(f"/tasks/{task_id}/cancel", json={"reason": "non mi serve più"})

    void = await client.post(
        "/nodes/work/result",
        json={"assignment_id": order["assignment_id"], **ENVELOPE},
        headers=headers,
    )

    assert void.status_code == 410
    assert void.json()["error"]["code"] == "assignment.void"
    assert (await rejections(ela))[-1]["reason"] == WorkRejection.TASK_CLOSED.value


async def test_a_delivery_while_the_task_is_being_walked_is_not_now(
    client: AsyncClient, ela: Ela, app: Any
) -> None:
    """The lock of the task, the ``set`` of ``app.state.running``: a claim, a delivery and a ``run``
    are three callers of the executor on one step, and it has no lock of its own. The answer is the
    ``409`` of a refused ``run`` and **nothing is written** — a "not now", which is why the node
    keeps the envelope (D7)."""
    task_id, order, headers, device_id = await taken(client, ela)
    app.state.running.add(TaskId(UUID(task_id)))
    events = len(await ela.audit.read())

    busy = await client.post(
        "/nodes/work/result",
        json={"assignment_id": order["assignment_id"], **ENVELOPE},
        headers=headers,
    )

    assert busy.status_code == 409
    assert busy.json()["error"]["code"] == "already_running"
    assert len(await ela.audit.read()) == events


async def test_a_decision_the_node_made_up_has_nowhere_to_go(client: AsyncClient, ela: Ela) -> None:
    """Criterion 17. A node can run a tool on its own machine whenever it likes — the machine is
    its own. What it cannot do is have the Core record an effect the Core did not assign: the
    envelope carries no decision, and a body that brings one is refused rather than trimmed."""
    _, order, headers, device_id = await taken(client, ela)

    forged = await client.post(
        "/nodes/work/result",
        json={
            "assignment_id": order["assignment_id"],
            **ENVELOPE,
            "decision": {"outcome": "ALLOWED"},
        },
        headers=headers,
    )

    assert forged.status_code == 422
    assert forged.json()["error"]["code"] == "invalid"


@pytest.mark.parametrize(
    "envelope",
    [
        {"form": "result"},
        {"form": "result", "status": "STARTED"},
        {"form": "refused", "status": "SUCCEEDED"},
        {"form": "exception"},
        {"form": "exception", "exception": "not an identifier"},
        {"form": "nonsense"},
    ],
    ids=[
        "no-status",
        "started",
        "a-refusal-with-a-status",
        "no-name",
        "not-a-name",
        "no-such-form",
    ],
)
async def test_an_envelope_that_tells_two_stories_is_refused(
    client: AsyncClient, ela: Ela, envelope: dict[str, Any]
) -> None:
    _, order, headers, device_id = await taken(client, ela)

    answered = await client.post(
        "/nodes/work/result",
        json={"assignment_id": order["assignment_id"], **envelope},
        headers=headers,
    )

    assert answered.status_code == 422


async def test_a_tool_that_refused_on_the_node_fails_the_step(
    client: AsyncClient, ela: Ela
) -> None:
    _, order, headers, device_id = await taken(client, ela)

    refused = await client.post(
        "/nodes/work/result",
        json={"assignment_id": order["assignment_id"], "form": "refused"},
        headers=headers,
    )

    assert refused.status_code == 200
    assert refused.json()["step"] == "FAILED"


# ----------------------------------------------------------------------------------------
# Asking for more time (ADR 0038 §13)
# ----------------------------------------------------------------------------------------


async def test_a_renewal_moves_the_deadline_and_writes_no_event(
    client: AsyncClient, ela: Ela
) -> None:
    """A sign of life is not an action (ADR 0016 §6): the deadline moves, the audit does not grow,
    and the task's own trail keeps the ``HEARTBEAT`` that makes ``recover()`` safe."""
    _, order, headers, device_id = await taken(client, ela)
    events = len(await ela.audit.read())

    renewed = await client.post(
        "/nodes/work/renew", json={"assignment_id": order["assignment_id"]}, headers=headers
    )

    assert renewed.status_code == 200, renewed.text
    assert renewed.json()["assignment_id"] == order["assignment_id"]
    assert renewed.json()["expires_at"] > order["expires_at"]
    assert len(await ela.audit.read()) == events


async def test_renewing_work_that_is_not_yours_is_the_same_404(
    client: AsyncClient, ela: Ela
) -> None:
    _, order, headers, device_id = await taken(client, ela)
    _, other = await enrolled(client, "TRUSTED", available_tools=["core-echo"])

    unknown = await client.post(
        "/nodes/work/renew", json={"assignment_id": str(uuid4())}, headers=headers
    )
    not_mine = await client.post(
        "/nodes/work/renew", json={"assignment_id": order["assignment_id"]}, headers=other
    )

    assert unknown.status_code == not_mine.status_code == 404


async def test_renewing_work_that_is_over_is_gone(client: AsyncClient, ela: Ela) -> None:
    _, order, headers, device_id = await taken(client, ela)
    await ela.assignments.cut_short(device_id)

    renewed = await client.post(
        "/nodes/work/renew", json={"assignment_id": order["assignment_id"]}, headers=headers
    )

    assert renewed.status_code == 410
    assert renewed.json()["error"]["code"] == "assignment.expired"


# ----------------------------------------------------------------------------------------
# The three routes are a node's, and only a node's (criterion 23)
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path", ["/nodes/work", "/nodes/work/result", "/nodes/work/renew"], ids=lambda p: p
)
async def test_the_core_is_not_a_node_on_the_work_routes(client: AsyncClient, path: str) -> None:
    """The Core's token is refused here exactly as nothing is: it is not a node, and there is no
    work for it to take. The matrix of every identity against every route is in test_security.py."""
    assert (await client.post(path, json={})).status_code == 401
