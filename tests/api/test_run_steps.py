"""What ``POST /tasks/{id}/run`` says of the steps of a run, on every branch (M6.3b, ADR 0051).

``steps`` holds the steps the call **handled**: those the executor gave its answer about in this
call — it ran, failed, was denied, or stopped on to ask for consent. A step handed to a node is not
among them, because the node will answer and ``reason`` names it; nor is a step waiting for a node,
which the executor did not see in this call. The field used to be described as the steps the call
*executed*, and in ``waiting_approval`` it carried the step that had not run (the proof by hand of
M17.2b).

Every case builds its branch the way production reaches it, then reads, for each step in the answer,
what happened to it: its state, and whether a ``TOOL_EXECUTED`` names it. The data passes before the
repair as after it — the field did not change, the word did —, and these tests are the precondition
of decision (a): what the word says is what the field holds. The cases are closed over
:class:`~ela.executive.RunOutcome`, so an outcome a future milestone adds stops the suite until it
has its own.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response

from ela.composition import Ela, Settings, build
from ela.domain import StepState
from ela.executive import RunOutcome
from ela.testing.fakes import FakeBrowser, FakeClock, FakePage, FakePower
from tests.api.support import EXAMPLES, echo_plan, note_plan, queued
from tests.api.test_nodes_work import ENVELOPE, a_node
from tests.composition.support import create_schema, declare


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    """The composition's world with the guide's sites (M14.1): the step that runs and fails is a
    gesture on a field the page does not have, since a call to the model that cannot be bounded is
    denied before its question (ADR 0057)."""
    declare(monkeypatch, tmp_path, ELA_BROWSER_SITES=json.dumps(["example.com", "httpbin.org"]))
    return Settings.load()


@pytest.fixture
async def ela(settings: Settings) -> AsyncIterator[Ela]:
    """ELA as ``build`` makes it, with a browser that opens nothing and a page with no
    ``#non-esiste`` — the story of ``browser-act-missing.json``."""
    await create_schema(settings.persistence.db_url)
    built = await build(
        settings, power=FakePower(), browser=FakeBrowser(FakePage(counts={"#non-esiste": 0}))
    )
    try:
        yield built
    finally:
        await built.aclose()


DEFINITION = "A step is handled when the executor gave its answer about it in this call"
"""The sentence the schema carries, written here and not read from the code: a test that read it
from ``RunOut`` would compare the schema with itself."""

FIRST_TASK_ECHO = "9c5b8f26-1a2b-4c3d-8e4f-000000000001"
FIRST_TASK_NOTE = "9c5b8f26-1a2b-4c3d-8e4f-000000000002"
"""The two steps of ``docs/examples/first-task.json``, the example of the guide's §6."""


@dataclass(frozen=True)
class Handled:
    """A step the answer must list, and what happened to it."""

    step: str
    state: StepState
    ran: bool
    """Whether a ``TOOL_EXECUTED`` names the step: its tool acted, here or on a node."""


@dataclass(frozen=True)
class Branch:
    """The answer of the run under test, and what it must say."""

    task: str
    answer: Response
    handled: tuple[Handled, ...]
    waiting: str | None = None
    """The step the run stopped before without handling it: handed to a node, or waiting for one."""


Case = Callable[[AsyncClient, Ela], Awaitable[Branch]]


def example(name: str) -> dict[str, Any]:
    plan: dict[str, Any] = json.loads((EXAMPLES / name).read_text(encoding="utf-8"))
    return plan


async def run(client: AsyncClient, task: str) -> Response:
    answer = await client.post(f"/tasks/{task}/run")
    assert answer.status_code == 200, answer.text
    return answer


async def answer_the_question(client: AsyncClient, task: str, verb: str) -> None:
    approval = (await client.get("/approvals")).json()[0]["id"]
    answered = await client.post(f"/tasks/{task}/{verb}", json={"approval_id": approval})
    assert answered.status_code == 200, answered.text


def echo_then(capability: str) -> tuple[dict[str, Any], str, str]:
    """A plan of an echo and a second step on ``capability`` after it; the plan and the two ids."""
    plan = echo_plan()
    first = plan["steps"][0]
    second = {**first, "id": "00000000-0000-4000-8000-0000000000b2"}
    second["required_capabilities"] = [capability]
    second["dependencies"] = [first["id"]]
    plan["steps"].append(second)
    return plan, first["id"], second["id"]


# ----------------------------------------------------------------------------------------
# The branches
# ----------------------------------------------------------------------------------------


async def completed(client: AsyncClient, ela: Ela) -> Branch:
    """An echo, walked to the end: the step ran in this call."""
    plan = echo_plan()
    task = await queued(client, plan)
    step = plan["steps"][0]["id"]
    return Branch(task, await run(client, task), (Handled(step, StepState.COMPLETED, True),))


async def completed_after_a_yes(client: AsyncClient, ela: Ela) -> Branch:
    """The guide's §7: after the yes, the second run handles only what was left."""
    task = await queued(client, example("first-task.json"))
    await run(client, task)
    await answer_the_question(client, task, "approve")
    return Branch(
        task, await run(client, task), (Handled(FIRST_TASK_NOTE, StepState.COMPLETED, True),)
    )


async def completed_with_nothing_to_handle(client: AsyncClient, ela: Ela) -> Branch:
    """A node's delivery closed the step through its route: the next run only closes the task, and
    has handled no step — the empty list does not say who closed it (ADR 0051 §2)."""
    _, headers = await a_node(client, ela)
    task = await queued(client, echo_plan(), privacy="TRUSTED")
    await run(client, task)
    order = (await client.post("/nodes/work", headers=headers)).json()
    delivered = await client.post(
        "/nodes/work/result",
        json={"assignment_id": order["assignment_id"], **ENVELOPE},
        headers=headers,
    )
    assert delivered.status_code == 200, delivered.text
    return Branch(task, await run(client, task), ())


async def waiting_approval(client: AsyncClient, ela: Ela) -> Branch:
    """The guide's §6: the echo ran; on the note ELA stopped to ask, and its tool did not run."""
    task = await queued(client, example("first-task.json"))
    return Branch(
        task,
        await run(client, task),
        (
            Handled(FIRST_TASK_ECHO, StepState.COMPLETED, True),
            Handled(FIRST_TASK_NOTE, StepState.RUNNING, False),
        ),
    )


async def denied_by_the_guardian(client: AsyncClient, ela: Ela) -> Branch:
    """The guide's §15, step 5: the Guardian denies a write outside the scope; nothing ran."""
    plan = example("fs-outside-the-scope.json")
    task = await queued(client, plan)
    step = plan["steps"][0]["id"]
    # The denied step did not act, and closes CANCELLED (M6.3c, ADR 0054 §4).
    return Branch(task, await run(client, task), (Handled(step, StepState.CANCELLED, False),))


async def denied_at_the_door(client: AsyncClient, ela: Ela) -> Branch:
    """The user's no closes the task; the run finds it closed and handles no step."""
    task = await queued(client, note_plan())
    await run(client, task)
    await answer_the_question(client, task, "deny")
    return Branch(task, await run(client, task), ())


async def failed_before_the_act(client: AsyncClient, ela: Ela) -> Branch:
    """The guide's §15, step 3: the same new file a second time is refused before the tool."""
    plan = example("fs-write.json")
    first = await queued(client, plan)
    await run(client, first)
    await answer_the_question(client, first, "approve")
    await run(client, first)
    again = await queued(client, plan)
    step = plan["steps"][0]["id"]
    return Branch(again, await run(client, again), (Handled(step, StepState.FAILED, False),))


async def failed_after_the_act(client: AsyncClient, ela: Ela) -> Branch:
    """A gesture on a field the page does not have: the tool ran, and failed (since M14.1; until
    then the model asked on a machine without a key, which is now denied before the question)."""
    plan = example("browser-act-missing.json")
    task = await queued(client, plan)
    await run(client, task)
    await answer_the_question(client, task, "approve")
    step = plan["steps"][0]["id"]
    return Branch(task, await run(client, task), (Handled(step, StepState.FAILED, True),))


async def waiting_device(client: AsyncClient, ela: Ela) -> Branch:
    """An echo, then a capability no node has: the echo was handled, the second step never was."""
    plan, echo, missing = echo_then("core.rm_rf")
    task = await queued(client, plan)
    return Branch(
        task, await run(client, task), (Handled(echo, StepState.COMPLETED, True),), waiting=missing
    )


async def cancelled_at_the_door(client: AsyncClient, ela: Ela) -> Branch:
    """A task the user stopped before any run."""
    task = await queued(client, echo_plan())
    stopped = await client.post(f"/tasks/{task}/cancel", json={"reason": "fermato"})
    assert stopped.status_code == 200, stopped.text
    return Branch(task, await run(client, task), ())


async def expired_at_the_door(client: AsyncClient, ela: Ela) -> Branch:
    """A question nobody answered, expired by ``recover()`` on a clock past its life — the one
    producer of ``EXPIRED`` in production (ADR 0015 §6)."""
    task = await queued(client, note_plan())
    await run(client, task)
    after = datetime.now(UTC) + ela.settings.core.approval_ttl + timedelta(minutes=1)
    later = await build(ela.settings, clock=FakeClock(after), power=FakePower())
    try:
        # What the start-up does: recover(), then the close of the steps it left open (M6.3c).
        await later.engine.recover()
        await later.executor.close_every_open_step()
    finally:
        await later.aclose()
    return Branch(task, await run(client, task), ())


async def assigned(client: AsyncClient, ela: Ela) -> Branch:
    """An echo a node wins: handed away, not handled — and the reason names it."""
    await a_node(client, ela)
    plan = echo_plan()
    task = await queued(client, plan, privacy="TRUSTED")
    return Branch(task, await run(client, task), (), waiting=plan["steps"][0]["id"])


async def assigned_after_a_handled_step(client: AsyncClient, ela: Ela) -> Branch:
    """A note written here, then an echo a node wins: the note is handled, the echo is not."""
    await a_node(client, ela)
    plan = note_plan()
    note = plan["steps"][0]
    note["requires_authorization"] = False
    echo = echo_plan()["steps"][0]
    echo["dependencies"] = [note["id"]]
    plan["steps"].append(echo)
    task = await queued(client, plan, privacy="TRUSTED")
    return Branch(
        task,
        await run(client, task),
        (Handled(note["id"], StepState.COMPLETED, True),),
        waiting=echo["id"],
    )


CASES: tuple[tuple[RunOutcome, Case], ...] = (
    (RunOutcome.COMPLETED, completed),
    (RunOutcome.COMPLETED, completed_after_a_yes),
    (RunOutcome.COMPLETED, completed_with_nothing_to_handle),
    (RunOutcome.WAITING_APPROVAL, waiting_approval),
    (RunOutcome.DENIED, denied_by_the_guardian),
    (RunOutcome.DENIED, denied_at_the_door),
    (RunOutcome.FAILED, failed_before_the_act),
    (RunOutcome.FAILED, failed_after_the_act),
    (RunOutcome.WAITING_DEVICE, waiting_device),
    (RunOutcome.CANCELLED, cancelled_at_the_door),
    (RunOutcome.EXPIRED, expired_at_the_door),
    (RunOutcome.ASSIGNED, assigned),
    (RunOutcome.ASSIGNED, assigned_after_a_handled_step),
)
"""One row per branch of a run that the API reaches without a fault. The branches it does not reach
— a resume after a crash, a step closed by ``finish`` — are asserted on the runner
(``tests/executive/test_assignment_recovery.py``, ``test_assignment_expiry.py``,
``test_runner_recovery.py``)."""


def test_every_outcome_of_a_run_has_a_case() -> None:
    """Closed over the outcomes: a new one without a case stops the suite here."""
    assert {outcome for outcome, _ in CASES} == set(RunOutcome)


@pytest.mark.parametrize(("outcome", "case"), CASES, ids=[case.__name__ for _, case in CASES])
async def test_the_steps_of_a_run_are_the_steps_it_handled(
    outcome: RunOutcome, case: Case, client: AsyncClient, ela: Ela
) -> None:
    branch = await case(client, ela)
    body = branch.answer.json()

    assert body["outcome"] == outcome.value
    assert body["steps"] == [handled.step for handled in branch.handled]
    detail = (await client.get(f"/tasks/{branch.task}")).json()
    states = {step["id"]: step["state"] for step in detail["steps"]}
    audit = (await client.get("/audit", params={"task_id": branch.task})).json()
    executed = {event["step_id"] for event in audit if event["event_type"] == "TOOL_EXECUTED"}
    for handled in branch.handled:
        assert states[handled.step] == handled.state.value, handled.step
        assert (handled.step in executed) is handled.ran, handled.step
    if branch.waiting is not None:
        assert branch.waiting not in body["steps"]
        assert branch.waiting not in executed
    if outcome is RunOutcome.ASSIGNED:
        assert branch.waiting is not None and branch.waiting in body["reason"]


def test_the_schema_says_what_a_handled_step_is(app: FastAPI) -> None:
    """One sentence for every outcome, read from the published schema (decision 7): the
    ``description`` of ``RunOut`` is the class's docstring, and it is what a client of the API reads
    about ``steps``."""
    description = " ".join(app.openapi()["components"]["schemas"]["RunOut"]["description"].split())

    assert DEFINITION in description
    assert "steps executed" not in description
    assert "steps it executed" not in description
