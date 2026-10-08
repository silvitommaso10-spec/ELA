"""One case for every operation of the engine that ends a task with a reason (M13.1e, decision 1).

The cases are **closed on ``OPERATIONS``**: every operation whose target is in
:data:`~ela.tasks.ending.REASONED` is produced here the way ELA produces it, and ``end`` is read
through ``GET /tasks/{id}``. An operation added to the engine that ends a task, without its case,
fails :func:`test_every_operation_that_ends_a_task_has_its_case` — the alarm that keeps a new end
from reaching the surfaces without its why.

``end.code`` is the payload's own, wherever the payload carries one: the failure's code, the
orphan's, the cap's ``spending.*`` — never a list of operations that have one.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from types import MappingProxyType
from typing import Any

import pytest

from ela.tasks.ending import REASONED
from ela.tasks.engine import OPERATIONS
from ela.testing.fakes import FakePage
from tests.api.ends import MISSING_BUTTON
from tests.api.reasons import (
    World,
    denied_by_the_guardian,
    denied_by_the_user,
    ending,
    example,
    expired,
    failed_as_an_orphan,
    run,
)
from tests.api.support import echo_plan, queued


async def by_approval(w: World) -> str:
    return (await denied_by_the_user(w)).task


async def by_decision(w: World) -> str:
    task = (await denied_by_the_guardian(w)).task
    assert (await run(w, task))["outcome"] == "denied"
    return task


async def by_cap(w: World) -> str:
    """A call to the model on a machine with no cap: denied before its question (ADR 0057)."""
    task = await queued(w.client, example("ask-model.json"))
    assert (await run(w, task))["outcome"] == "denied"
    return task


async def by_planning(w: World) -> str:
    """The planning of a task, on a machine with no cap: the planning task denied by the cap, and
    the task it plans denied by its planning (ADR 0058)."""
    task = str((await w.client.post("/tasks", json={"text": "una nota"})).json()["id"])
    planned = await w.client.post(f"/tasks/{task}/planning")
    assert planned.json()["outcome"] == "denied", planned.text
    return task


async def by_failure(w: World) -> str:
    w.browser.page = FakePage(counts={"#non-esiste": 0})
    task = await queued(w.client, example(MISSING_BUTTON))
    await run(w, task)
    pending = [one for one in (await w.client.get("/approvals")).json() if one["task_id"] == task]
    await w.client.post(f"/tasks/{task}/approve", json={"approval_id": pending[0]["id"]})
    assert (await run(w, task))["outcome"] == "failed"
    return task


async def by_recovery(w: World) -> str:
    return (await failed_as_an_orphan(w)).task


async def by_stop(w: World) -> str:
    task = await queued(w.client, echo_plan())
    await w.client.post(f"/tasks/{task}/cancel", json={"reason": "fermato"})
    return task


async def by_expiry(w: World) -> str:
    return (await expired(w)).task


CASES: Mapping[str, Callable[[World], Awaitable[str]]] = MappingProxyType(
    {
        "deny_by_approval": by_approval,
        "deny_by_decision": by_decision,
        "deny_by_cap": by_cap,
        "deny_by_planning": by_planning,
        "fail": by_failure,
        "recover": by_recovery,
        "cancel": by_stop,
        "expire": by_expiry,
    }
)
"""The operation each case produces, as ELA produces it."""

CODES: Mapping[str, str | None] = MappingProxyType(
    {
        "deny_by_approval": None,
        "deny_by_decision": None,
        "deny_by_cap": "spending.",
        "deny_by_planning": None,
        "fail": "browser.element_missing",
        "recover": "orphaned",
        "cancel": None,
        "expire": None,
    }
)
"""What the code begins with, or ``None`` for a payload that carries no code."""


def test_every_operation_that_ends_a_task_has_its_case() -> None:
    ends = {op.name for op in OPERATIONS.values() if op.target in REASONED}

    assert set(CASES) == ends, "an operation that ends a task without its case, or the other way"
    assert set(CODES) == ends


@pytest.mark.parametrize("operation", sorted(CASES))
async def test_the_end_of_every_operation_is_read_through_the_route(
    world: World, operation: str
) -> None:
    task = await CASES[operation](world)
    event = await ending(world, task)

    end: dict[str, Any] | None = (await world.client.get(f"/tasks/{task}")).json()["end"]

    assert end is not None
    assert end["reason"] == event["summary"]
    assert end["operation"] == event["payload"]["operation"] == operation
    assert end["code"] == event["payload"].get("code")
    assert (end["code"] is None) == (CODES[operation] is None)
    assert str(end["code"] or "").startswith(CODES[operation] or "")
