"""The ends of a task that ``run`` reports with a reason, built as production reaches them (M13.1c).

One builder per row of the table of ``docs/milestones/M13.1c.md``, shared by the API test
(``tests/api/test_run_reasons.py``) and the CLI test (``tests/cli/test_run_reasons.py``): a builder
leaves the task **one call before the end** when a ``run`` closes it, and **closed** when something
else does — the route of the no, the route of a node's delivery, the start-up. The test then makes
the two calls through its own surface and compares them (ADR 0055, decision D of the session: the
reason is the same for the call that closes the task and for a later call that finds it closed at
the door).

The ends that only a crash leaves are prepared through ELA's own ports, as ``tamper_with_the_trail``
prepares a tampered log: the engine's write path, the store of the results — the state a crash
leaves, written by the code that would have written it, never by a route invented for a test.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ela.api import create_app
from ela.cli import client as cli_client
from ela.composition import Ela, Settings, build
from ela.devices import LOCAL_DEVICE_ID
from ela.domain import (
    CapabilityId,
    ErrorMetadata,
    ExecutionId,
    ExecutionResult,
    ExecutionStatus,
    StepId,
    TaskId,
)
from ela.executive import RunOutcome
from ela.testing.fakes import FakeBrowser, FakeClock, FakePage, FakePower
from tests.api.support import AUTHORIZED, BASE, EXAMPLES, echo_plan, note_plan, queued
from tests.api.test_nodes_work import ENVELOPE, a_node
from tests.cli.support import Cli, LoopTransport
from tests.composition.support import create_schema, declare

SITES = ["example.com", "httpbin.org"]
"""The sites the guide's §20 tells the reader to declare, for the plans of the browser."""

PARAGRAPH = "body > p:first-of-type"


@dataclass(frozen=True)
class World:
    """One ELA with a browser the test scripts, its application, a client and the CLI over it."""

    ela: Ela
    app: FastAPI
    client: AsyncClient
    cli: Cli
    browser: FakeBrowser
    settings: Settings


@dataclass(frozen=True)
class Branch:
    """A task one call before its end, or already ended, and what the two calls must answer."""

    task: str
    outcome: RunOutcome
    closes: bool
    """``True``: the next ``run`` closes the task. ``False``: something else closed it, and both
    calls are at the door."""
    taken: bool = False
    """The second call finds the lock of ``run`` taken (``TaskRunner.answer``, M6.3c)."""


Builder = Callable[[World], Awaitable[Branch]]


@pytest.fixture
async def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[World]:
    """ELA as ``build`` makes it, with the browser of ``ela.testing`` and the guide's sites."""
    async with opened(monkeypatch, tmp_path) as built:
        yield built


@asynccontextmanager
async def opened(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **declared: str
) -> AsyncIterator[World]:
    """The world of :func:`world`, with whatever else the test declares — a configured voice for
    the dry run of the guide's §22 (``tests/cli/test_section_22_on_the_cli.py``)."""
    declare(monkeypatch, tmp_path, ELA_BROWSER_SITES=json.dumps(SITES), **declared)
    settings = Settings.load()
    await create_schema(settings.persistence.db_url)
    browser = FakeBrowser()
    ela = await build(settings, power=FakePower(), browser=browser)
    app = create_app(ela)
    transport = LoopTransport(app, asyncio.get_running_loop())
    monkeypatch.setattr(
        cli_client, "connect", lambda: cli_client.open_client(ela.settings.api, transport=transport)
    )
    try:
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app), base_url=BASE, headers=AUTHORIZED
            ) as client,
        ):
            yield World(ela, app, client, Cli(transport), browser, settings)
    finally:
        await ela.aclose()


def example(name: str) -> dict[str, Any]:
    plan: dict[str, Any] = json.loads((EXAMPLES / name).read_text(encoding="utf-8"))
    return plan


async def run(w: World, task: str) -> dict[str, Any]:
    answer = await w.client.post(f"/tasks/{task}/run")
    assert answer.status_code == 200, answer.text
    body: dict[str, Any] = answer.json()
    return body


async def answer_the_question(w: World, task: str, verb: str) -> None:
    pending = [one for one in (await w.client.get("/approvals")).json() if one["task_id"] == task]
    answered = await w.client.post(f"/tasks/{task}/{verb}", json={"approval_id": pending[0]["id"]})
    assert answered.status_code == 200, answered.text


async def ending(w: World, task: str) -> dict[str, Any]:
    """The audit event of the transition that put the task in its state: chosen by the state it
    wrote (``payload.new_state``), not by its type — the no is an ``APPROVAL_RESOLVED``."""
    state = (await w.client.get(f"/tasks/{task}")).json()["state"]
    audit = (await w.client.get("/audit", params={"task_id": task})).json()
    found = [event for event in audit if event["payload"].get("new_state") == state]
    assert found, f"no audit event put {task} in {state}"
    event: dict[str, Any] = found[-1]
    return event


def ids(task: str, plan: dict[str, Any]) -> tuple[TaskId, StepId]:
    return TaskId(UUID(task)), StepId(UUID(plan["steps"][0]["id"]))


async def later(w: World, minutes: float) -> None:
    """What the start-up does on a clock past the deadline of the task's silence or question:
    ``recover()``, then the close of the steps it left open (M6.3c)."""
    after = datetime.now(UTC) + timedelta(minutes=minutes)
    built = await build(w.settings, clock=FakeClock(after), power=FakePower())
    try:
        await built.engine.recover()
        await built.executor.close_every_open_step()
    finally:
        await built.aclose()


async def node_took(w: World) -> tuple[str, dict[str, Any], dict[str, str]]:
    """An echo a node won and took: the task, the order, the node's header."""
    _, headers = await a_node(w.client, w.ela)
    task = await queued(w.client, echo_plan(), privacy="TRUSTED")
    assert (await run(w, task))["outcome"] == RunOutcome.ASSIGNED.value
    order = await w.client.post("/nodes/work", headers=headers)
    assert order.status_code == 200, order.text
    return task, order.json(), headers


async def deliver(
    w: World, order: dict[str, Any], headers: dict[str, str], **envelope: Any
) -> None:
    delivered = await w.client.post(
        "/nodes/work/result",
        json={"assignment_id": order["assignment_id"], **envelope},
        headers=headers,
    )
    assert delivered.status_code == 200, delivered.text


# ----------------------------------------------------------------------------------------
# The rows of the table
# ----------------------------------------------------------------------------------------


async def denied_by_the_guardian(w: World) -> Branch:
    """Row 1: a write outside the scope, the guide's §15 step 5."""
    task = await queued(w.client, example("fs-outside-the-scope.json"))
    return Branch(task, RunOutcome.DENIED, closes=True)


async def denied_by_the_user(w: World) -> Branch:
    """Row 2: the no, through its route — which closes the task and the step that asked."""
    task = await queued(w.client, note_plan())
    await run(w, task)
    await answer_the_question(w, task, "deny")
    return Branch(task, RunOutcome.DENIED, closes=False)


async def failed_before_the_act(w: World) -> Branch:
    """Row 3: the same new file a second time, refused before the tool (§15 step 3)."""
    plan = example("fs-write.json")
    first = await queued(w.client, plan)
    await run(w, first)
    await answer_the_question(w, first, "approve")
    await run(w, first)
    return Branch(await queued(w.client, plan), RunOutcome.FAILED, closes=True)


async def failed_after_the_act(w: World) -> Branch:
    """Row 4: a gesture on a field the page does not have — the tool ran, and failed.

    Until M14.1 this row was the model asked on a machine without a key; since the spending cap a
    call that spends is denied before its question when it cannot be bounded (ADR 0057), and the
    row needs a tool that does run. The page has no ``#non-esiste``: the example's own story."""
    w.browser.page = FakePage(counts={"#non-esiste": 0})
    task = await queued(w.client, example("browser-act-missing.json"))
    await run(w, task)
    await answer_the_question(w, task, "approve")
    return Branch(task, RunOutcome.FAILED, closes=True)


async def failed_by_the_verification(w: World) -> Branch:
    """Row 5: the page answers the verifier's look with another text than the one the tool read —
    the world that changed between the tool and the verifier, not a fault."""
    w.browser.page = FakePage(
        title="Example Domain",
        texts={PARAGRAPH: "This domain is for use in documentation examples"},
        changes_to={PARAGRAPH: "Something else entirely"},
    )
    task = await queued(w.client, example("browser-read.json"))
    return Branch(task, RunOutcome.FAILED, closes=True)


async def failed_interrupted(w: World) -> Branch:
    """Row 6: a tool that cannot run twice, started under its STARTED record, never reported — the
    state a crash between the tool and its outcome leaves, written by the engine and the store."""
    plan = example("ask-model.json")
    task = await queued(w.client, plan)
    task_id, step_id = ids(task, plan)
    await w.ela.engine.start(task_id, device_id=LOCAL_DEVICE_ID)
    await w.ela.engine.start_step(task_id, step_id, device_id=LOCAL_DEVICE_ID)
    tool = w.ela.tools.get(CapabilityId(plan["steps"][0]["required_capabilities"][0]))
    await w.ela.results.add(
        ExecutionResult(
            id=ExecutionId(uuid4()),
            created_at=w.ela.clock.now(),
            capability_id=tool.capability_id,
            status=ExecutionStatus.STARTED,
            task_id=task_id,
            step_id=step_id,
            tool_name=tool.name,
            device_id=LOCAL_DEVICE_ID,
        )
    )
    return Branch(task, RunOutcome.FAILED, closes=True)


async def failed_on_a_node(w: World) -> Branch:
    """Row 7, as production reaches it: a node delivers a failure with its error. The delivery
    closes the step and leaves the task EXECUTING; the next run fails the task."""
    task, order, headers = await node_took(w)
    await deliver(
        w,
        order,
        headers,
        form="result",
        status="FAILED",
        error={"code": "terminal.exit_code", "message": "the program exited with 3"},
        duration_ms=12,
        node={"finished_at": "2026-10-02T08:00:02Z"},
    )
    return Branch(task, RunOutcome.FAILED, closes=True)


async def failed_after_a_crash(w: World) -> Branch:
    """Row 7, the other way: a crash between ``fail_step`` and ``fail`` (window R6)."""
    plan = echo_plan()
    task = await queued(w.client, plan)
    task_id, step_id = ids(task, plan)
    await w.ela.engine.start(task_id, device_id=LOCAL_DEVICE_ID)
    await w.ela.engine.start_step(task_id, step_id, device_id=LOCAL_DEVICE_ID)
    await w.ela.engine.fail_step(
        task_id,
        step_id,
        ErrorMetadata(code="tool.exception", message="RuntimeError: the tool raised"),
    )
    return Branch(task, RunOutcome.FAILED, closes=True)


async def failed_as_an_orphan(w: World) -> Branch:
    """Row 10: a task EXECUTING and silent past ``orphan_after``, failed by the start-up."""
    plan = echo_plan()
    task = await queued(w.client, plan)
    task_id, _ = ids(task, plan)
    await w.ela.engine.start(task_id, device_id=LOCAL_DEVICE_ID)
    await later(w, w.settings.core.orphan_after.total_seconds() / 60 + 1)
    return Branch(task, RunOutcome.FAILED, closes=False)


async def denied_with_the_lock_taken(w: World) -> Branch:
    """Row 11: the second call finds the lock of ``run`` held by another holder."""
    branch = await denied_by_the_guardian(w)
    return Branch(branch.task, branch.outcome, closes=True, taken=True)


async def failed_by_a_delivery_not_verified(w: World) -> Branch:
    """Row 12: a node says the echo answered something else; the Core's verifier disagrees, and the
    route of the delivery fails the task."""
    task, order, headers = await node_took(w)
    await deliver(w, order, headers, **{**ENVELOPE, "output": {"message": "addio"}})
    return Branch(task, RunOutcome.FAILED, closes=False)


async def expired(w: World) -> Branch:
    """``expired`` (decision 2 of the review): a question nobody answered, expired at start-up."""
    task = await queued(w.client, note_plan())
    await run(w, task)
    await later(w, w.settings.core.approval_ttl.total_seconds() / 60 + 1)
    return Branch(task, RunOutcome.EXPIRED, closes=False)


CASES: tuple[Builder, ...] = (
    denied_by_the_guardian,
    denied_by_the_user,
    failed_before_the_act,
    failed_after_the_act,
    failed_by_the_verification,
    failed_interrupted,
    failed_on_a_node,
    failed_after_a_crash,
    failed_as_an_orphan,
    denied_with_the_lock_taken,
    failed_by_a_delivery_not_verified,
    expired,
)
"""The rows of the table with a case of their own (criterion 1). Row 8 is row 7 seen from ``run``;
row 9 the validator removes (criterion 3); row 13 is asserted on the runner, because ``recover()``
runs only at start-up."""


def said(event: dict[str, Any]) -> str:
    """What the reason must contain beyond the summary's form: the error as ``code: message``."""
    error = event.get("error")
    if not error:
        return ""
    return f"{error['code']}: {error['message']}" if error["message"] else str(error["code"])
