"""A browser step stopped halfway: **the behaviour ELA wants**, since M6.3c (ADR 0054 §11).

A step of the browser lasts as long as the site, so the case of M6.3c happens for real: the user
presses «ferma» — on the phone, in the console, with ``ela task cancel`` — while the browser works.
Until M6.3c the click went out after the «ferma», ``run`` answered ``409`` and the step stayed
``RUNNING`` in a ``CANCELLED`` task: the dated debt of ADR 0052 §15, owed by M6.3c, whose smallest
defence this file was. **Turned**, it says the three sides of the point of no return of
``browser.act`` — the first gesture:

* stopped while the browser starts, **before the navigation**: the site sees nothing, no gesture;
* stopped after the navigation, **before the first gesture**: the visit happened, no gesture;
* stopped while the click is under way, **after the point**: the step closes as a normal one, and
  the outcome says it had acted and its verification passed.

The precondition is built, not waited for: the browser is the fake of ``ela.testing``, injected in
``build()``, and it holds the instant the test needs until the test has stopped the task.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response

from ela.api import create_app
from ela.composition import Ela, Settings, build
from ela.domain import AuditEventType, ExecutionStatus, Halt, StepId, StepState, TaskId
from ela.executive import EXECUTION_STOPPED
from ela.testing.fakes import FakeBrowser
from tests.api.support import AUTHORIZED, BASE, queued
from tests.composition.support import create_schema, database_url, declare

STEP = "b4c2d7e1-5a3f-4b69-8d20-000000000005"
PLAN: dict[str, Any] = {
    "goal": "compilare e inviare un modulo",
    "steps": [
        {
            "id": STEP,
            "goal": "compilare il nome nel modulo di prova e inviarlo",
            "required_capabilities": ["browser.act"],
            "arguments": {
                "site": "httpbin.org",
                "path": "/forms/post",
                "fill": [["input[name=custname]", "ELA prova 7431"]],
                "click": "form button",
                "expect_text": "ELA prova 7431",
                "purpose": "la prova del ferma",
            },
            "risk": "HIGH",
            "expected_result": "la pagina dopo l'invio mostra il nome scritto",
            "success_conditions": ["browser.expect_visible"],
            "requires_authorization": True,
        }
    ],
}


@pytest.fixture
async def held(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> AsyncIterator[tuple[AsyncClient, Ela, FakeBrowser]]:
    declare(monkeypatch, tmp_path, ELA_BROWSER_SITES=json.dumps(["httpbin.org"]))
    await create_schema(database_url(tmp_path))
    browser = FakeBrowser()
    ela = await build(Settings.load(), browser=browser)
    app: FastAPI = create_app(ela)
    try:
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app), base_url=BASE, headers=AUTHORIZED
            ) as client,
        ):
            yield client, ela, browser
    finally:
        await ela.aclose()


async def asked_and_approved(client: AsyncClient) -> str:
    task_id = await queued(client, PLAN)
    asked = await client.post(f"/tasks/{task_id}/run")
    assert asked.json()["outcome"] == "waiting_approval", asked.text
    (approval,) = (await client.get("/approvals")).json()
    yes = await client.post(f"/tasks/{task_id}/approve", json={"approval_id": approval["id"]})
    assert yes.status_code == 200, yes.text
    return task_id


async def stopped_while(
    client: AsyncClient, task_id: str, reached: asyncio.Event, released: asyncio.Event
) -> tuple[Response, Response]:
    """``run`` in flight, the «ferma» when the fake browser is at the instant, then let it go."""
    running = asyncio.create_task(client.post(f"/tasks/{task_id}/run"))
    await reached.wait()
    stopped = await client.post(f"/tasks/{task_id}/cancel", json={"reason": "ferma"})
    released.set()
    return stopped, await running


async def kinds_after_the_stop(ela: Ela, task_id: str) -> list[AuditEventType]:
    kinds = [event.event_type for event in await ela.audit.read(task_id=TaskId(uuid.UUID(task_id)))]
    return kinds[kinds.index(AuditEventType.TASK_CANCELLED) :]


async def test_a_browser_step_stopped_after_its_first_gesture_closes_as_a_normal_one(
    held: tuple[AsyncClient, Ela, FakeBrowser],
) -> None:
    """The debt's own case, turned: the click is under way when the «ferma» arrives — past the
    point —, so it goes out, the verifier looks, and the step is COMPLETED. ``run`` says
    ``cancelled``, with the stop's words and what the step in progress had done."""
    client, ela, browser = held
    task_id = await asked_and_approved(client)
    browser.click_reached, browser.click_released = asyncio.Event(), asyncio.Event()

    stopped, answered = await stopped_while(
        client, task_id, browser.click_reached, browser.click_released
    )

    assert stopped.status_code == 200, stopped.text
    assert browser.clicks == ["form button"]
    assert answered.status_code == 200, answered.text
    body = answered.json()
    assert body["outcome"] == "cancelled"
    assert body["reason"] == "cancel: EXECUTING -> CANCELLED (ferma)"
    assert body["halt"] == Halt.ACTED_VERIFIED.value
    assert body["steps"] == [STEP]
    task = TaskId(uuid.UUID(task_id))
    graph = await ela.engine.graph(task)
    assert graph.states[StepId(uuid.UUID(STEP))] is StepState.COMPLETED
    written = await ela.results.for_step(task, StepId(uuid.UUID(STEP)))
    assert [result.status for result in written] == [
        ExecutionStatus.STARTED,
        ExecutionStatus.SUCCEEDED,
    ]
    after = await kinds_after_the_stop(ela, task_id)
    assert AuditEventType.TOOL_EXECUTED in after
    assert AuditEventType.EXECUTION_VERIFIED in after
    assert AuditEventType.STEP_COMPLETED in after


async def test_a_browser_step_stopped_before_the_navigation_visits_nothing(
    held: tuple[AsyncClient, Ela, FakeBrowser],
) -> None:
    """The stop while the browser starts: the navigation is listened to first, the site sees
    nothing, no gesture is made, and the step did not act."""
    client, ela, browser = held
    task_id = await asked_and_approved(client)
    browser.launch_reached, browser.launch_released = asyncio.Event(), asyncio.Event()

    _, answered = await stopped_while(
        client, task_id, browser.launch_reached, browser.launch_released
    )

    assert answered.status_code == 200, answered.text
    assert answered.json()["outcome"] == "cancelled"
    assert answered.json()["halt"] == Halt.NOT_ACTED.value
    assert browser.opened == []
    assert browser.fills == [] and browser.clicks == []
    task = TaskId(uuid.UUID(task_id))
    assert (await ela.engine.graph(task)).states[StepId(uuid.UUID(STEP))] is StepState.CANCELLED
    written = await ela.results.for_step(task, StepId(uuid.UUID(STEP)))
    assert [result.status for result in written] == [
        ExecutionStatus.STARTED,
        ExecutionStatus.CANCELLED,
    ]
    assert written[-1].error is not None
    assert written[-1].error.code == EXECUTION_STOPPED


async def test_a_browser_step_stopped_before_its_first_gesture_fills_nothing_and_closes_the_page(
    held: tuple[AsyncClient, Ela, FakeBrowser],
) -> None:
    """The point of decision 2: the page is open, the elements are being looked at, and the stop
    arrives — no field is filled, no click is sent, and the page is closed (B-R10 of the
    re-read)."""
    client, ela, browser = held
    task_id = await asked_and_approved(client)
    reached, released = asyncio.Event(), asyncio.Event()
    counting = browser.count

    async def held_count(page: str, selector: str) -> int:
        reached.set()
        await released.wait()
        return await counting(page, selector)

    browser.count = held_count  # type: ignore[method-assign]

    _, answered = await stopped_while(client, task_id, reached, released)

    assert answered.status_code == 200, answered.text
    assert answered.json()["halt"] == Halt.NOT_ACTED.value
    assert browser.opened == ["https://httpbin.org/forms/post"]
    assert browser.fills == [] and browser.clicks == []
    assert browser.closed == ["page-1"]
