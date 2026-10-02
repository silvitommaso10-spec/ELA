"""The reason of ``POST /tasks/{id}/run`` for every end but ``completed`` (M13.1c, ADR 0055).

Decision D of the session: **the reason is the same for the call that closes the task and for a
later call that finds it closed at the door** — and it is the summary of the audit event of the
transition that ended the task, passed and never composed (decision C, ADR 0019 §2). Until M13.1c
the door answered nothing for ``denied``, ``failed`` and ``expired``, and the call that closed the
task answered nothing in the branches where the executor's word carried no error: a failure a node
delivered, a step a crash left interrupted or blocked.

The branches are built in ``tests/api/reasons.py``, one per row of the table of the SPEC.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from ela.domain import TaskId
from ela.executive import RunOutcome
from tests.api.reasons import (
    CASES,
    Builder,
    World,
    ending,
    run,
    said,
)


async def the_two_calls(
    w: World, task: str, *, taken: bool
) -> tuple[dict[str, Any], dict[str, Any]]:
    first = await run(w, task)
    if not taken:
        return first, await run(w, task)
    running: set[TaskId] = w.app.state.running
    running.add(TaskId(UUID(task)))
    try:
        return first, await run(w, task)
    finally:
        running.discard(TaskId(UUID(task)))


@pytest.mark.parametrize("case", CASES, ids=[case.__name__ for case in CASES])
async def test_the_reason_is_the_transition_s_at_the_end_and_at_the_door(
    case: Builder, world: World
) -> None:
    branch = await case(world)

    first, second = await the_two_calls(world, branch.task, taken=branch.taken)

    assert first["outcome"] == second["outcome"] == branch.outcome.value
    assert first["reason"], first
    assert second["reason"] == first["reason"]
    event = await ending(world, branch.task)
    assert first["reason"] == event["summary"]
    assert first["reason"].startswith(f"{event['payload']['operation']}: ")
    assert said(event) in first["reason"]


def test_every_end_that_is_not_completed_has_a_case() -> None:
    """Closed over the outcomes that end a task with a reason: a new one stops the suite here."""
    ends = {RunOutcome.DENIED, RunOutcome.FAILED, RunOutcome.EXPIRED}

    assert {case.__name__.split("_")[0] for case in CASES} == {end.value for end in ends}


async def test_a_no_is_said_with_the_identity_that_answered(world: World) -> None:
    """Decision 1 of the review: the no carries the id the approval records, ``responded_by`` —
    through the CLI's token that is ``local``'s, the person at this machine."""
    branch = await CASES[1](world)

    answer = await run(world, branch.task)

    assert answer["reason"] == (
        "deny_by_approval: WAITING_APPROVAL -> DENIED (rejected by "
        "6c38f1c5-6cda-5680-8a7a-4f061588deed)"
    )


async def test_a_failure_carries_its_code_beside_its_message(world: World) -> None:
    branch = await CASES[2](world)

    answer = await run(world, branch.task)

    assert answer["reason"] == (
        "fail: EXECUTING -> FAILED (fs.overwrite_mismatch: 'ELA/prova.md' was declared as a new "
        "file and something is there now)"
    )


def test_the_schema_says_that_an_end_always_carries_its_why(world: World) -> None:
    """Decision F, on the published schema: the ``description`` of ``RunOut`` is the class's
    docstring — the docstring of a field is not published — and it is what a client of the API
    reads."""
    schema = world.app.openapi()["components"]["schemas"]["RunOut"]
    description = " ".join(schema["description"].split())

    assert (
        "``denied``, ``failed``, ``cancelled`` and ``expired`` always carry their why"
        in description
    )
    assert "when this run received one" not in description
