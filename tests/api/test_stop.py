"""The «ferma» through the application: the lock, the close, the node, the outcome (M6.3c).

* **The lock** (proposal 8, decision 16): two runs of a live task are one run and a ``409`` —
  ``test_task_lock.py`` says it —; the run of a **stopped** task that finds the lock taken is its
  outcome, never a ``409``, and closes nothing: whoever holds the lock does.
* **The route of the «ferma»** closes the open step only with the lock free.
* **The node** (proposal 7): an offer of a task that ended is withdrawn, and a node asking for work
  finds none; a claim of one is renewed without signing a life the task no longer has.
* **The outcome** carries ``halt`` in ``RunOut``, ``TaskDetail`` and the finished tasks.

The preconditions are built, not waited for: a power reading that holds the first run, as in
``test_task_lock.py``, and no sleep.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ela.api import create_app
from ela.composition import Ela, Settings, build
from ela.domain import (
    ApprovalId,
    ApprovalStatus,
    AssignmentState,
    Halt,
    StepId,
    StepState,
    TaskEventType,
    TaskId,
)
from ela.ports import AssignmentStateError
from tests.api.support import AUTHORIZED, BASE, echo_plan, note_plan, queued
from tests.api.test_nodes_work import a_node, taken, work_for
from tests.api.test_task_lock import GatedPower
from tests.composition.support import create_schema

STOPPED = "cancel: WAITING_APPROVAL -> CANCELLED (ferma)"


@pytest.fixture
async def gated(settings: Settings) -> AsyncIterator[tuple[AsyncClient, GatedPower, Ela]]:
    power = GatedPower()
    await create_schema(settings.persistence.db_url)
    ela = await build(settings, power=power)
    app: FastAPI = create_app(ela)
    try:
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app), base_url=BASE, headers=AUTHORIZED
            ) as client,
        ):
            yield client, power, ela
    finally:
        await ela.aclose()


async def the_step(ela: Ela, task_id: str) -> tuple[StepId, StepState]:
    graph = await ela.engine.graph(TaskId(uuid.UUID(task_id)))
    ((step, state),) = graph.states.items()
    return step, state


async def asking(client: AsyncClient) -> str:
    task_id = await queued(client, note_plan())
    asked = await client.post(f"/tasks/{task_id}/run")
    assert asked.json()["outcome"] == "waiting_approval", asked.text
    return task_id


# ----------------------------------------------------------------------------------------
# The lock
# ----------------------------------------------------------------------------------------


async def test_the_run_of_a_stopped_task_that_finds_the_lock_taken_is_its_outcome(
    gated: tuple[AsyncClient, GatedPower, Ela],
) -> None:
    """The first run holds the lock, suspended in its walk; the task is stopped; a second run
    arrives. Before M6.3c it was a ``409``. Now it answers as the door would, and writes nothing:
    the first run, which holds the lock, rereads the task as its last act and answers the same."""
    client, power, ela = gated
    task_id = await queued(client, echo_plan())
    power.armed = True
    first = asyncio.create_task(client.post(f"/tasks/{task_id}/run"))
    await power.reached.wait()

    stopped = await client.post(f"/tasks/{task_id}/cancel", json={"reason": "ferma"})
    second = await client.post(f"/tasks/{task_id}/run")
    power.released.set()
    answered = await first

    assert stopped.status_code == 200, stopped.text
    assert second.status_code == 200, second.text
    assert second.json()["outcome"] == "cancelled"
    assert second.json()["reason"] == "cancel: QUEUED -> CANCELLED (ferma)"
    assert second.json()["steps"] == []
    assert answered.status_code == 200, answered.text
    assert answered.json()["outcome"] == "cancelled"
    _, state = await the_step(ela, task_id)
    assert state is StepState.PENDING  # nothing was in progress: decision 11, it stays PENDING


async def test_a_run_of_a_live_task_that_finds_the_lock_taken_is_still_a_409(
    gated: tuple[AsyncClient, GatedPower, Ela],
) -> None:
    """The negative case of the door at a taken lock: a task that has not ended is not answered,
    it is refused — two runs of one live task are one run (ADR 0023 §9)."""
    client, power, _ = gated
    task_id = await queued(client, echo_plan())
    power.armed = True
    first = asyncio.create_task(client.post(f"/tasks/{task_id}/run"))
    await power.reached.wait()

    second = await client.post(f"/tasks/{task_id}/run")
    power.released.set()
    await first

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "already_running"


# ----------------------------------------------------------------------------------------
# The route of the «ferma»: it closes, with the lock free
# ----------------------------------------------------------------------------------------


async def test_the_stop_of_a_task_nobody_runs_closes_its_open_step(
    client: AsyncClient, ela: Ela
) -> None:
    task_id = await asking(client)
    _, before = await the_step(ela, task_id)
    assert before is StepState.RUNNING

    stopped = await client.post(f"/tasks/{task_id}/cancel", json={"reason": "ferma"})

    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["state"] == "CANCELLED"
    _, after = await the_step(ela, task_id)
    assert after is StepState.CANCELLED


async def test_the_stop_of_a_task_whose_lock_is_taken_leaves_the_close_to_its_holder(
    client: AsyncClient, ela: Ela, app: FastAPI
) -> None:
    """The lock taken by somebody else — here put in the set by hand, the way a run holds it: the
    route stops the task and closes nothing. The holder's last act is the close."""
    task_id = await asking(client)
    identifier = TaskId(uuid.UUID(task_id))
    running: set[TaskId] = app.state.running
    running.add(identifier)
    try:
        await client.post(f"/tasks/{task_id}/cancel", json={"reason": "ferma"})
        _, held = await the_step(ela, task_id)
    finally:
        running.discard(identifier)

    assert held is StepState.RUNNING
    run = await client.post(f"/tasks/{task_id}/run")
    assert run.json()["steps"] == [str((await the_step(ela, task_id))[0])]
    assert (await the_step(ela, task_id))[1] is StepState.CANCELLED


# ----------------------------------------------------------------------------------------
# The outcome, on every route that carries a task's state
# ----------------------------------------------------------------------------------------


async def test_the_run_the_detail_and_the_finished_list_say_what_the_step_had_done(
    client: AsyncClient, ela: Ela
) -> None:
    task_id = await asking(client)
    await client.post(f"/tasks/{task_id}/cancel", json={"reason": "ferma"})

    run = (await client.post(f"/tasks/{task_id}/run")).json()
    detail = (await client.get(f"/tasks/{task_id}")).json()
    finished = (await client.get("/tasks/finished", params={"limit": 5})).json()

    assert run["outcome"] == "cancelled"
    assert run["reason"] == STOPPED
    assert run["halt"] == Halt.NOT_ACTED.value
    assert detail["halt"] == Halt.NOT_ACTED.value
    (row,) = [one for one in finished["tasks"] if one["id"] == task_id]
    assert row["halt"] == Halt.NOT_ACTED.value


async def test_a_task_ended_otherwise_has_no_halt_anywhere(client: AsyncClient) -> None:
    task_id = await queued(client, echo_plan())
    run = (await client.post(f"/tasks/{task_id}/run")).json()
    detail = (await client.get(f"/tasks/{task_id}")).json()

    assert run["outcome"] == "completed"
    assert run["halt"] is None
    assert detail["halt"] is None


# ----------------------------------------------------------------------------------------
# The node: the offer withdrawn, the claim of one, and the renewal
# ----------------------------------------------------------------------------------------


async def test_the_offer_of_a_stopped_task_is_withdrawn_and_the_node_finds_no_work(
    client: AsyncClient, ela: Ela
) -> None:
    task_id, _, headers = await work_for(client, ela)

    await client.post(f"/tasks/{task_id}/cancel", json={"reason": "ferma"})
    asked = await client.post("/nodes/work", headers=headers)

    assert asked.status_code == 204
    step, state = await the_step(ela, task_id)
    assert state is StepState.CANCELLED
    (offer,) = await ela.assignments._store.for_step(TaskId(uuid.UUID(task_id)), step)  # noqa: SLF001
    assert offer.state is AssignmentState.WITHDRAWN


async def test_a_node_that_asks_for_the_offer_of_a_task_ended_under_it_finds_no_work(
    client: AsyncClient, ela: Ela
) -> None:
    """The stop written by the engine alone — nobody closed the step yet —: the node's request
    finds the offer, sees the task ended, withdraws it, closes the step, and gets nothing."""
    task_id, _, headers = await work_for(client, ela)
    identifier = TaskId(uuid.UUID(task_id))
    await ela.engine.cancel(identifier, reason="ferma")

    asked = await client.post("/nodes/work", headers=headers)

    assert asked.status_code == 204
    step, state = await the_step(ela, task_id)
    assert state is StepState.CANCELLED
    (offer,) = await ela.assignments._store.for_step(identifier, step)  # noqa: SLF001
    assert offer.state is AssignmentState.WITHDRAWN


async def test_a_node_working_for_a_stopped_task_renews_without_a_sign_of_life(
    client: AsyncClient, ela: Ela
) -> None:
    task_id, order, headers, _ = await taken(client, ela)
    await client.post(f"/tasks/{task_id}/cancel", json={"reason": "ferma"})
    identifier = TaskId(uuid.UUID(task_id))
    trail = len(await ela.repository.events(identifier))

    renewed = await client.post(
        "/nodes/work/renew", json={"assignment_id": order["assignment_id"]}, headers=headers
    )

    assert renewed.status_code == 200, renewed.text
    assert renewed.json()["expires_at"] > order["expires_at"]
    events = await ela.repository.events(identifier)
    assert TaskEventType.HEARTBEAT not in [event.event_type for event in events[trail:]]
    detail: dict[str, Any] = (await client.get(f"/tasks/{task_id}")).json()
    assert detail["halt"] == Halt.FINISHING.value


async def test_a_node_with_no_work_left_after_a_stop_is_still_a_node(
    client: AsyncClient, ela: Ela
) -> None:
    """The negative case of the withdrawal: a node with nothing offered is told 204 all the same."""
    _, headers = await a_node(client, ela)
    assert (await client.post("/nodes/work", headers=headers)).status_code == 204


async def test_a_no_recorded_and_never_applied_answers_the_task_the_stop_left(
    client: AsyncClient, ela: Ela
) -> None:
    """Window 5c of ADR 0015 §8, met by a stop: the no is in the store, the engine never heard
    it, and the task was stopped meanwhile. The retry of the no answers the stopped task as it
    stands — the stop closed its step —, and closes nothing more."""
    task_id = await asking(client)
    (pending,) = (await client.get("/approvals")).json()
    await ela.approvals.respond(
        ApprovalId(uuid.UUID(pending["id"])),
        status=ApprovalStatus.REJECTED,
        responded_by="you",
        now=ela.clock.now(),
    )
    await client.post(f"/tasks/{task_id}/cancel", json={"reason": "ferma"})

    answered = await client.post(f"/tasks/{task_id}/deny", json={"approval_id": pending["id"]})

    assert answered.status_code == 200, answered.text
    assert answered.json()["state"] == "CANCELLED"
    assert (await the_step(ela, task_id))[1] is StepState.CANCELLED


async def test_an_offer_taken_by_another_request_first_is_no_work_for_this_one(
    client: AsyncClient, ela: Ela, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The race two requests of one node can lose honestly: between the read of the offer and its
    claim, the offer stopped being takeable — and not because its task ended."""
    _, _, headers = await work_for(client, ela)

    async def taken_first(assignment_id: Any, device_id: Any) -> Any:
        raise AssignmentStateError(assignment_id, AssignmentState.CLAIMED)

    monkeypatch.setattr(ela.executor, "begin", taken_first)

    assert (await client.post("/nodes/work", headers=headers)).status_code == 204
