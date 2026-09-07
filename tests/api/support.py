"""Driving the API in a test: a client over the app, and plans to send it.

The transport is ``ASGITransport``: the request reaches the application in this process and no
socket is opened, which is what keeps ``tests/conftest.py``'s "no test talks to the network"
true for these tests too.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any, cast

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from ela.api import create_app
from ela.composition import Ela
from ela.infrastructure.persistence.orm import APPEND_ONLY_TRIGGERS
from ela.permissions import CORE_ECHO, WORKSPACE_WRITE_NOTE
from ela.tools import ECHO_MESSAGE_MATCHES, NOTE_CONTENT_MATCHES, NOTE_EXISTS
from tests.composition.support import TOKEN

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
    """A plan of one step that needs the user's consent (§30): ``run`` stops and asks."""
    return {
        "goal": "write a note",
        "steps": [
            {
                "id": str(uuid.uuid4()),
                "goal": "write",
                "required_capabilities": [WORKSPACE_WRITE_NOTE],
                "arguments": {"path": path, "body": body},
                "risk": "MEDIUM",
                "expected_result": "a note on disk",
                "success_conditions": [NOTE_EXISTS, NOTE_CONTENT_MATCHES],
                "requires_authorization": True,
            }
        ],
    }


async def queued(client: AsyncClient, plan: dict[str, Any], text: str = "fai una cosa") -> str:
    """A task with that plan attached, ready to run; returns its id."""
    created = await client.post("/tasks", json={"text": text})
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


@pytest.fixture
async def anonymous(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """A client with no credentials at all."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as opened:
        yield opened
