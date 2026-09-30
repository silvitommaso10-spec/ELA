"""A browser step stopped halfway: **the defect as it is, not the behaviour ELA wants** (M13.4 form
M).

A step of the browser lasts as long as the site, so the case of M6.3c happens for real: the user
presses «ferma» — on the phone, in the console, with ``ela task cancel`` — while the browser clicks.
``POST /tasks/{id}/cancel`` does not take the lock of ``run`` (census C7), so it lands between two
writes of the executor: **the click goes out after the «ferma»**, the result is written, the
verifier looks at the page, ``TOOL_EXECUTED`` and ``EXECUTION_VERIFIED`` follow ``TASK_CANCELLED``,
``run`` answers ``409``, and the step stays ``RUNNING`` in a ``CANCELLED`` task, where ``recover()``
does not look.

**It is a dated debt of ADR 0052 (§15), owed by M6.3c** — the first milestone after M13.4 —, which
will make ``run`` answer a clean ``cancelled`` and bring the stop to a tool before its point of no
return: for ``browser.act``, before the first gesture. **This test is the smallest defence of that
debt**: the day it fails, the debt is being paid — write the payment in an ADR, and turn the test.

The precondition is built, not waited for: the browser is the fake of ``ela.testing``, injected in
``build()`` (C8), and it holds the click until the test has stopped the task.
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
from httpx import ASGITransport, AsyncClient

from ela.api import create_app
from ela.composition import Ela, Settings, build
from ela.domain import AuditEventType, ExecutionStatus, StepId, StepState, TaskId
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


async def test_a_browser_step_stopped_midway_is_the_defect_of_m6_3c(
    held: tuple[AsyncClient, Ela, FakeBrowser],
) -> None:
    client, ela, browser = held
    task_id = await queued(client, PLAN)
    asked = await client.post(f"/tasks/{task_id}/run")
    assert asked.json()["outcome"] == "waiting_approval", asked.text
    (approval,) = (await client.get("/approvals")).json()
    yes = await client.post(f"/tasks/{task_id}/approve", json={"approval_id": approval["id"]})
    assert yes.status_code == 200, yes.text

    browser.click_reached, browser.click_released = asyncio.Event(), asyncio.Event()
    running = asyncio.create_task(client.post(f"/tasks/{task_id}/run"))
    await browser.click_reached.wait()  # the fields are filled, and the click is under way
    stopped = await client.post(f"/tasks/{task_id}/cancel", json={"reason": "ferma"})
    browser.click_released.set()
    answered = await running

    # The «ferma» answers — and did not stop the browser: the click went out after it.
    assert stopped.status_code == 200, stopped.text
    assert browser.clicks == ["form button"]
    # ``run`` does not say «cancelled»: the engine's sentence, as a 409.
    assert answered.status_code == 409, answered.text
    assert "complete_step needs an EXECUTING task, not CANCELLED" in answered.text
    # The task is stopped, and its step is still running, where nothing will close it.
    task = TaskId(uuid.UUID(task_id))
    assert (await client.get(f"/tasks/{task_id}")).json()["state"] == "CANCELLED"
    graph = await ela.engine.graph(task)
    assert graph.states[StepId(uuid.UUID(STEP))] is StepState.RUNNING
    # The effect is written: the STARTED record, then the result.
    written = await ela.results.for_step(task, StepId(uuid.UUID(STEP)))
    assert [result.status for result in written] == [
        ExecutionStatus.STARTED,
        ExecutionStatus.SUCCEEDED,
    ]
    # And the audit says so after the «ferma»: the tool ran, and the page was looked at.
    kinds = [event.event_type for event in await ela.audit.read(task_id=task)]
    cancelled = kinds.index(AuditEventType.TASK_CANCELLED)
    assert AuditEventType.TOOL_EXECUTED in kinds[cancelled:]
    assert AuditEventType.EXECUTION_VERIFIED in kinds[cancelled:]
