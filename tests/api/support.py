"""Driving the API in a test: a client over the app, and plans to send it.

The transport is ``ASGITransport``: the request reaches the application in this process and no
socket is opened, which is what keeps ``tests/conftest.py``'s "no test talks to the network"
true for these tests too.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from ela.api import create_app
from ela.composition import Ela, Settings, build
from ela.domain import Task, TaskState
from ela.infrastructure.persistence.orm import APPEND_ONLY_TRIGGERS
from ela.permissions import CORE_ECHO, WORKSPACE_WRITE_NOTE
from ela.testing.fakes import FakeClock, FakePower
from ela.tools import ECHO_MESSAGE_MATCHES, NOTE_CONTENT_MATCHES, NOTE_EXISTS
from tests.composition.support import TOKEN, create_schema

BASE = "http://ela"
AUTHORIZED = {"Authorization": f"Bearer {TOKEN}"}
NOTE_PATH = "workspace/notes/briefing.md"
NOTE_BODY = "quello che l'utente ha scritto"
ECHO_MESSAGE = "ciao"


def echo_plan() -> dict[str, Any]:
    """A plan of one SAFE step: no approval, so a single ``run`` walks it to the end."""
    return {
        "goal": "say something",
        "steps": [
            {
                "id": str(uuid.uuid4()),
                "goal": "echo",
                "required_capabilities": [CORE_ECHO],
                "arguments": {"message": ECHO_MESSAGE},
                "risk": "SAFE",
                "expected_result": "the message back",
                "success_conditions": [ECHO_MESSAGE_MATCHES],
                "requires_authorization": False,
            }
        ],
    }


def note_plan(path: str = NOTE_PATH, body: str = NOTE_BODY) -> dict[str, Any]:
    """A plan of one step that needs the user's consent (§30): ``run`` stops and asks.

    The risk is the catalogue's — ``workspace.write_note`` is LOW, protected by its scope — and
    what makes the step ask is ``requires_authorization`` on the step itself (ADR 0025 §8.2).
    """
    return {
        "goal": "write a note",
        "steps": [
            {
                "id": str(uuid.uuid4()),
                "goal": "write",
                "required_capabilities": [WORKSPACE_WRITE_NOTE],
                "arguments": {"path": path, "body": body},
                "risk": "LOW",
                "expected_result": "a note on disk",
                "success_conditions": [NOTE_EXISTS, NOTE_CONTENT_MATCHES],
                "requires_authorization": True,
            }
        ],
    }


async def queued(
    client: AsyncClient,
    plan: dict[str, Any],
    text: str = "fai una cosa",
    *,
    privacy: str | None = None,
) -> str:
    """A task with that plan attached, ready to run; returns its id.

    ``privacy`` is how far the task may travel (M12.2, D18): left out, the task stays on this
    machine, which is both the default and what every task of this suite did before. A test that
    wants a node to receive work declares it here, because declaring it at creation is the only way
    there is — the level is the task's and immutable (D20).
    """
    body: dict[str, Any] = {"text": text}
    if privacy is not None:
        body["max_privacy"] = privacy
    created = await client.post("/tasks", json=body)
    assert created.status_code == 201, created.text
    task_id: str = created.json()["id"]
    planned = await client.post(f"/tasks/{task_id}/plan", json=plan)
    assert planned.status_code == 200, planned.text
    return task_id


async def tamper_with_the_trail(ela: Ela) -> None:
    """Rewrite one entry of the log, the way only somebody with the file could.

    The triggers refuse an ``UPDATE`` (ADR 0007, level 3), so they go first: what is being
    simulated is an attacker who has the database itself, which is exactly the case the chain
    exists for — the trail cannot stop them, it can only make them visible.
    """
    engine = cast(AsyncEngine, ela.database)
    async with engine.begin() as connection:
        for trigger in APPEND_ONLY_TRIGGERS:
            await connection.execute(text(f"DROP TRIGGER {trigger}"))
        await connection.execute(
            text("UPDATE audit_events SET summary = 'rewritten' WHERE seq = 1")
        )


class BrokenRepository:
    """A repository whose disk is gone. Only ``tasks`` is needed: it is what health reads."""

    async def tasks(self, **kwargs: Any) -> tuple[Task, ...]:
        raise OSError("disk I/O error")


def outside_the_block(page: str) -> str:
    """A page without its ``<style>`` block (M17.2c, D8): 81 KB of sheet in the text would let a
    «contains» pass on the CSS — ``components.css`` says «ELA» too — and turn a «does not contain»
    red for a comment."""
    return re.sub(r"<style>.*?</style>", "", page, flags=re.DOTALL)


class NoListOfEveryTask:
    """A repository that refuses the one question a page must not ask: every task (M17.2b, C6).

    The finished tasks grow for ever, and a home that loaded them all to show eight would be the
    shape the review of M8.1 took out of ``/diagnostics`` (ADR 0025 §2). Everything else is the
    real repository's.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def tasks(
        self, *, states: frozenset[TaskState] | None = None, limit: int | None = None
    ) -> tuple[Task, ...]:
        if states is None:
            raise AssertionError("a page asked for every task (M17.2b, C6)")
        result: tuple[Task, ...] = await self._inner.tasks(states=states, limit=limit)
        return result


# ----------------------------------------------------------------------------------------
# A task in each final state, reached the way production reaches it (M17.2b, correction A)
# ----------------------------------------------------------------------------------------

EXAMPLES = Path(__file__).resolve().parents[2] / "docs" / "examples"

Ending = Callable[[AsyncClient, Ela, str, str | None], Awaitable[str]]


async def _completed(client: AsyncClient, ela: Ela, text: str, privacy: str | None) -> str:
    """A run that walks a SAFE plan to its end."""
    task = await queued(client, echo_plan(), text, privacy=privacy)
    await client.post(f"/tasks/{task}/run")
    return task


async def _failed(client: AsyncClient, ela: Ela, text: str, privacy: str | None) -> str:
    """A step that fails: the example that asks a model, on a machine without a key."""
    plan = json.loads((EXAMPLES / "ask-model.json").read_text(encoding="utf-8"))
    task = await queued(client, plan, text, privacy=privacy)
    await client.post(f"/tasks/{task}/run")
    approval = (await client.get("/approvals")).json()[0]["id"]
    await client.post(f"/tasks/{task}/approve", json={"approval_id": approval})
    await client.post(f"/tasks/{task}/run")
    return task


async def _denied(client: AsyncClient, ela: Ela, text: str, privacy: str | None) -> str:
    """A question the user answered no."""
    task = await queued(client, note_plan(), text, privacy=privacy)
    await client.post(f"/tasks/{task}/run")
    approval = (await client.get("/approvals")).json()[0]["id"]
    await client.post(f"/tasks/{task}/deny", json={"approval_id": approval})
    return task


async def _cancelled(client: AsyncClient, ela: Ela, text: str, privacy: str | None) -> str:
    """A live task the user stopped."""
    task = await queued(client, echo_plan(), text, privacy=privacy)
    await client.post(f"/tasks/{task}/cancel", json={"reason": "fermato"})
    return task


async def _expired(client: AsyncClient, ela: Ela, text: str, privacy: str | None) -> str:
    """A question nobody answered in time, expired by ``recover()`` — the one producer of
    ``EXPIRED`` in production (ADR 0015 §6) — on a clock past the question's life.

    Not ``engine.expire``: it has no caller in production (M17.2b, C1), and a precondition built
    by a producer that does not exist says nothing about the product.
    """
    task = await queued(client, note_plan(), text, privacy=privacy)
    await client.post(f"/tasks/{task}/run")
    after = datetime.now(UTC) + ela.settings.core.approval_ttl + timedelta(minutes=1)
    later = await build(ela.settings, clock=FakeClock(after), power=FakePower())
    try:
        await later.engine.recover()
    finally:
        await later.aclose()
    return task


ENDINGS: Mapping[TaskState, Ending] = MappingProxyType(
    {
        TaskState.COMPLETED: _completed,
        TaskState.FAILED: _failed,
        TaskState.DENIED: _denied,
        TaskState.CANCELLED: _cancelled,
        TaskState.EXPIRED: _expired,
    }
)
"""How each final state is reached. Its keys are held equal to ``TERMINAL_STATES`` by a test, so
a sixth final state without a way to get there stops the suite instead of skipping a case."""


async def ended(
    state: TaskState, client: AsyncClient, ela: Ela, *, text: str, privacy: str | None = None
) -> str:
    """A task in ``state``, reached as production reaches it; returns its id."""
    task = await ENDINGS[state](client, ela, text, privacy)
    reached = (await client.get(f"/tasks/{task}")).json()["state"]
    assert reached == state.value, f"{state.value} was not reached: {reached}"
    return task


def served_paths(app: FastAPI) -> list[tuple[str, str]]:
    """Every (method, path) the application serves, read off the application itself.

    FastAPI wraps an included router in an object of its own instead of flattening its routes,
    so the walk follows ``original_router`` where there is one and takes the route where there is
    not: what is being asserted is what the app serves, not how this version stores it.
    """
    found: list[tuple[str, str]] = []
    for entry in app.routes:
        router = getattr(entry, "original_router", None)
        for route in getattr(router, "routes", [entry]):
            for method in sorted(getattr(route, "methods", None) or {"GET"}):
                if method not in {"HEAD", "OPTIONS"}:
                    found.append((method, route.path))
    return found


@pytest.fixture
def app(ela: Ela) -> FastAPI:
    return create_app(ela)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """A client that carries the token, with the application's lifespan run around it."""
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url=BASE, headers=AUTHORIZED) as opened,
    ):
        yield opened


@dataclass(frozen=True)
class Clocked:
    """An ELA whose clock the test moves, its application, and a client carrying the token."""

    clock: FakeClock
    app: FastAPI
    client: AsyncClient


@pytest.fixture
async def clocked(settings: Settings) -> AsyncIterator[Clocked]:
    """An ELA built on a :class:`~ela.testing.fakes.FakeClock` the test moves (M17.2b).

    For the tests that assert the order of outcomes: two runs on the real clock may end in the same
    instant — on Windows the clock ticks every fifteen milliseconds or so —, and a tie is broken by
    insertion, which gives the opposite order. A test asserts only what it built the preconditions
    of, so the instants are the test's: the clock moves between one run and the next. Built with
    ``build(settings, clock=…)`` and not by replacing ``Ela.clock``: ``transition`` reads the
    engine's clock, which ``build`` hands it.
    """
    await create_schema(settings.persistence.db_url)
    clock = FakeClock(datetime.now(UTC))
    built = await build(settings, clock=clock, power=FakePower())
    try:
        application = create_app(built)
        async with (
            application.router.lifespan_context(application),
            AsyncClient(
                transport=ASGITransport(app=application), base_url=BASE, headers=AUTHORIZED
            ) as opened,
        ):
            yield Clocked(clock, application, opened)
    finally:
        await built.aclose()


@pytest.fixture
async def anonymous(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """A client with no credentials at all."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as opened:
        yield opened
