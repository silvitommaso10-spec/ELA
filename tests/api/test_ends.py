"""The why of an end on every route that carries a task's state, and who said no (M13.1e, ADR 0059).

**One source** (decision A): ``end.reason`` is the summary of the audit event of the transition that
ended the task, read from ``GET /audit`` — the event whose ``payload.new_state`` is the task's
state —, passed and never composed; the same in ``RunOut.reason`` and ``PlanningOut.reason``, which
read it from the same function. The routes are read from ``docs/outcomes.txt``.

**Who said no** (decision D, with the four facts of the census and decision 2 of the review): the
route resolves the identity the approval recorded — ``LOCAL_USER`` first, with its fixed name and
the role ``LOCAL``; then the device registry, revoked rows included, with the row's name and role;
otherwise the id alone, with no name and no role. For a task denied by its planning, who answered
its planning task.

**The reads** (decision 4): one read of the audit more for every listed task with a reason, and one
more for a task denied by its planning — counted, not timed (ADR 0052 §16).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from ela.devices import LOCAL_USER
from ela.domain import ApprovalId, ApprovalStatus, TaskId, TaskState
from ela.tasks.ending import REASONED
from tests.api.ends import (
    CONSOLE_NAME,
    PHONE_NAME,
    Surfaces,
    asking,
    closing,
    device_of,
    ended,
    no_from_the_command_line,
    no_from_the_console,
    no_from_the_phone,
    question_of,
    task_of,
)
from tests.api.planning import created
from tests.api.reasons import run
from tests.api.support import echo_plan, queued
from tests.docs.test_outcomes import written

LOCAL_NAME = "the command line on the Core"
NOBODY = "0b7c2f4e-9a1d-4c3e-8f6a-2d5b8e1c7a90"
"""An id no row of the registry has: one fixed value, so every worker of the suite collects the
same case."""

COVERED = frozenset(
    {
        ("GET", "/tasks"),
        ("GET", "/tasks/finished"),
        ("GET", "/tasks/{task_id}"),
        ("POST", "/tasks/{task_id}/approve"),
        ("POST", "/tasks/{task_id}/cancel"),
        ("POST", "/tasks/{task_id}/deny"),
        ("POST", "/tasks/{task_id}/planning"),
        ("POST", "/tasks/{task_id}/run"),
    }
)
"""The routes of ``docs/outcomes.txt`` that can answer with a task that ended, each with its case
here."""

NEVER = frozenset({("POST", "/tasks"), ("POST", "/tasks/{task_id}/plan")})
"""The routes that cannot: a task just created is ``CREATED``, and a plan written by hand enters a
``CREATED`` or ``PLANNING`` task and leaves it ``QUEUED``. They carry ``end`` like every other —
empty."""


def outcome_routes() -> set[tuple[str, str]]:
    return {
        (line.split(" ")[1], line.split(" ")[2])
        for line in written().splitlines()
        if line.startswith("route ")
    }


def test_every_route_that_carries_a_state_is_covered_or_cannot_carry_an_end() -> None:
    assert outcome_routes() == COVERED | NEVER
    assert COVERED.isdisjoint(NEVER)


# ----------------------------------------------------------------------------------------
# One source, on every route
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("state", sorted(REASONED))
async def test_every_reading_route_carries_the_summary_of_the_transition(
    surfaces: Surfaces, state: TaskState
) -> None:
    s = surfaces
    task = await ended(s, state)
    summary = (await closing(s, task))["summary"]

    listed = [one for one in (await s.world.client.get("/tasks")).json() if one["id"] == task]
    finished = (await s.world.client.get("/tasks/finished", params={"limit": 10})).json()
    row = [one for one in finished["tasks"] if one["id"] == task]
    detail = await task_of(s, task)
    ran = (await s.world.client.post(f"/tasks/{task}/run")).json()

    assert [one["end"]["reason"] for one in (*listed, *row, detail, ran["task"])] == [summary] * 4
    assert ran["reason"] == summary


async def test_a_task_that_did_not_end_with_a_reason_carries_no_end(surfaces: Surfaces) -> None:
    s = surfaces
    waiting = await asking(s, "una domanda")
    created_task = (await s.world.client.post("/tasks", json={"text": "appena creato"})).json()

    assert created_task["end"] is None
    assert (await task_of(s, waiting))["end"] is None


async def test_the_answers_of_the_no_the_stop_and_a_repeated_yes_carry_the_end(
    surfaces: Surfaces,
) -> None:
    s = surfaces
    asked = await asking(s, "un no")
    question = await question_of(s, asked)
    denied = (
        await s.world.client.post(f"/tasks/{asked}/deny", json={"approval_id": question})
    ).json()
    later = await asking(s, "un sì, poi fermato")
    yes = await question_of(s, later)
    await s.world.client.post(f"/tasks/{later}/approve", json={"approval_id": yes})
    stopped = (await s.world.client.post(f"/tasks/{later}/cancel", json={})).json()
    again = (await s.world.client.post(f"/tasks/{later}/approve", json={"approval_id": yes})).json()

    assert denied["end"]["reason"] == (await closing(s, asked))["summary"]
    assert stopped["state"] == again["state"] == TaskState.CANCELLED.value
    assert stopped["end"] == again["end"]
    assert again["end"]["reason"] == (await closing(s, later))["summary"]


async def test_the_planning_route_says_the_end_of_the_task_and_of_its_planning_task(
    surfaces: Surfaces,
) -> None:
    s = surfaces
    task = await created(s.world.client)
    body = (await s.world.client.post(f"/tasks/{task}/planning")).json()
    await s.world.client.post(
        f"/tasks/{body['planning_task']['id']}/deny", json={"approval_id": body["approval"]["id"]}
    )

    planned = (await s.world.client.post(f"/tasks/{task}/planning")).json()

    assert planned["task"]["end"]["reason"] == planned["reason"]
    assert planned["reason"] == (await closing(s, task))["summary"]
    assert (
        planned["planning_task"]["end"]["reason"]
        == (await closing(s, planned["planning_task"]["id"]))["summary"]
    )


# ----------------------------------------------------------------------------------------
# Who said no
# ----------------------------------------------------------------------------------------


async def answered_by(s: Surfaces, task: str) -> dict[str, Any]:
    end = (await task_of(s, task))["end"]
    assert end is not None
    found: dict[str, Any] = end["answered_by"]
    return found


async def test_the_no_of_the_command_line_has_the_fixed_name_and_the_local_role(
    surfaces: Surfaces,
) -> None:
    """Fact 1 of the census: the id of ``LOCAL_USER`` is the id of the row ``local``, which the
    registry would name «local» — the fixed name comes first."""
    task = await no_from_the_command_line(surfaces)

    assert await answered_by(surfaces, task) == {
        "identity": LOCAL_USER.id,
        "name": LOCAL_NAME,
        "role": "LOCAL",
    }


async def test_the_no_of_the_console_has_its_name_and_its_role(surfaces: Surfaces) -> None:
    task = await no_from_the_console(surfaces)

    assert await answered_by(surfaces, task) == {
        "identity": await device_of(surfaces, CONSOLE_NAME),
        "name": CONSOLE_NAME,
        "role": "CONSOLE",
    }


async def test_the_no_of_the_phone_has_its_name_and_its_role(surfaces: Surfaces) -> None:
    task = await no_from_the_phone(surfaces)

    assert await answered_by(surfaces, task) == {
        "identity": await device_of(surfaces, PHONE_NAME),
        "name": PHONE_NAME,
        "role": "COMPANION",
    }


async def test_a_device_revoked_after_its_no_keeps_its_name(surfaces: Surfaces) -> None:
    """The row stays (ADR 0037): the name is the one it had when it answered."""
    task = await no_from_the_phone(surfaces)
    phone = await device_of(surfaces, PHONE_NAME)
    revoked = await surfaces.world.client.post(f"/nodes/{phone}/revoke")
    assert revoked.status_code == 200, revoked.text

    assert await answered_by(surfaces, task) == {
        "identity": phone,
        "name": PHONE_NAME,
        "role": "COMPANION",
    }


@pytest.mark.parametrize("recorded", ["user", NOBODY])
async def test_an_identity_the_registry_does_not_know_is_the_id_alone(
    surfaces: Surfaces, recorded: str
) -> None:
    """Fact 3: before M12.1 ``responded_by`` was ``ELA_USER_NAME``, «user» by default (ADR 0037
    §15); and an id with no row is an id. Written as the route wrote it then: the store, then the
    engine."""
    s = surfaces
    task = await asking(s, "una risposta di prima")
    answered = await s.world.ela.approvals.respond(
        ApprovalId(UUID(await question_of(s, task))),
        status=ApprovalStatus.REJECTED,
        responded_by=recorded,
        now=s.world.ela.clock.now(),
    )
    await s.world.ela.engine.deny(TaskId(UUID(task)), approval=answered)

    assert await answered_by(s, task) == {"identity": recorded, "name": None, "role": None}


async def test_a_task_denied_by_its_planning_says_who_answered_its_planning_task(
    surfaces: Surfaces,
) -> None:
    """Fact 2: followed through the child the parent names, never read out of the words."""
    s = surfaces
    task = await created(s.world.client)
    body = (await s.world.client.post(f"/tasks/{task}/planning")).json()
    answered = await s.console.post(
        "/console/answer",
        data={"id": body["approval"]["id"], "answer": "no"},
        headers={"Origin": "http://127.0.0.1"},
    )
    assert answered.status_code == 303, answered.text
    await s.world.client.post(f"/tasks/{task}/planning")

    assert (await task_of(s, task))["state"] == TaskState.DENIED.value
    assert await answered_by(s, task) == {
        "identity": await device_of(s, CONSOLE_NAME),
        "name": CONSOLE_NAME,
        "role": "CONSOLE",
    }
    assert s.model.messages.calls == []


async def test_an_end_nobody_answered_has_nobody(surfaces: Surfaces) -> None:
    task = await ended(surfaces, TaskState.FAILED)

    assert (await task_of(surfaces, task))["end"]["answered_by"] is None


# ----------------------------------------------------------------------------------------
# What a list costs
# ----------------------------------------------------------------------------------------


async def test_a_list_reads_the_audit_once_more_per_task_with_a_reason(
    surfaces: Surfaces, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Decision 4: counted, not timed. A task in every end of ``REASONED``, one ``COMPLETED`` that
    needs nothing, and a task denied by its planning that needs its child too."""
    s = surfaces
    for state in sorted(REASONED):
        await ended(s, state)
    task = await created(s.world.client)
    body = (await s.world.client.post(f"/tasks/{task}/planning")).json()
    await s.world.client.post(
        f"/tasks/{body['planning_task']['id']}/deny", json={"approval_id": body["approval"]["id"]}
    )
    await s.world.client.post(f"/tasks/{task}/planning")
    completed = await queued(s.world.client, echo_plan(), "un saluto")
    assert (await run(s.world, completed))["outcome"] == "completed"
    reads: list[object] = []
    inner = s.world.ela.audit.read

    async def counted(**filters: Any) -> Any:
        reads.append(filters.get("task_id"))
        return await inner(**filters)

    every = (await s.world.client.get("/tasks")).json()
    reasoned = [one for one in every if one["state"] in {state.value for state in REASONED}]
    monkeypatch.setattr(s.world.ela.audit, "read", counted)

    await s.world.client.get("/tasks")

    assert len(reads) == len(reasoned) + 1
    assert sorted(map(str, reads)) == sorted(
        [*(one["id"] for one in reasoned), body["planning_task"]["id"]]
    )
