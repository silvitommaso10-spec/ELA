"""``/health`` and ``/diagnostics`` (spec §54; ADR 0023 §6).

``/health`` says the database answered, not that a process is listening: it reads through the
port. ``/diagnostics`` says how ELA is composed — and what it must **never** say is a secret or
the user's content, which is the half of it that has a test of its own.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ela.api import create_app
from ela.api.tasks import PLAN_IS_TEMPORARY
from ela.composition import Ela
from ela.domain import TaskState
from ela.ports import TaskRepository
from ela.providers.anthropic import PROVIDER_NAME
from ela.routing import DEFAULT_ROUTES
from tests.api.support import AUTHORIZED, BASE, BrokenRepository, echo_plan, queued
from tests.composition.support import TOKEN


async def test_health_says_the_database_answered(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok" and body["database"] == "ok"
    assert body["now"].endswith("Z") or "+00:00" in body["now"]


async def test_health_is_503_when_the_database_does_not_answer(ela: Ela) -> None:
    """A health check that cannot fail is not a health check."""
    broken = dataclasses.replace(ela, repository=BrokenRepository())  # type: ignore[arg-type]
    app = create_app(broken)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url=BASE, headers=AUTHORIZED
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"


async def test_diagnostics_says_how_ela_is_composed(client: AsyncClient, ela: Ela) -> None:
    body = (await client.get("/diagnostics")).json()

    assert body["providers"] == {PROVIDER_NAME: "UNAVAILABLE"}  # no key on this machine
    assert body["tools"] == [tool.name for tool in ela.tools.tools()]
    assert body["capabilities"] == [spec.id for spec in ela.capabilities.specs()]
    assert body["task_types"] == sorted(DEFAULT_ROUTES)
    assert body["default_profile"] == ela.settings.routing.model_default_route.profile
    assert body["devices"] == {"local": "available"}
    assert body["user_name"] == "user"
    assert body["version"]


async def test_diagnostics_counts_what_ela_is_holding(client: AsyncClient) -> None:
    await queued(client, echo_plan())

    body = (await client.get("/diagnostics")).json()

    assert body["tasks"] == {TaskState.QUEUED.value: 1}
    assert body["pending_approvals"] == 0
    assert body["recovered"] == {"failed": 0, "skipped": 0, "expired": 0}


async def test_diagnostics_counts_without_loading_the_tasks(ela: Ela) -> None:
    """The debt of M8.1, paid (ADR 0025 §2): ``count`` is asked, ``tasks`` is not.

    Asserting on the body alone would not catch a regression here — the body is the same either
    way, and that it is the same is the other half of what this checks.
    """
    spy = _CountingRepository(ela.repository)
    app = create_app(dataclasses.replace(ela, repository=spy))
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url=BASE, headers=AUTHORIZED) as client,
    ):
        await queued(client, echo_plan())
        spy.calls.clear()

        body = (await client.get("/diagnostics")).json()

    assert body["tasks"] == {TaskState.QUEUED.value: 1}
    assert "count" in spy.calls
    assert "tasks" not in spy.calls


class _CountingRepository:
    """Every call goes through to the real repository; the names are written down on the way."""

    def __init__(self, inner: TaskRepository) -> None:
        self._inner = inner
        self.calls: list[str] = []

    def __getattr__(self, name: str) -> Any:
        self.calls.append(name)
        return getattr(self._inner, name)


async def test_a_start_up_recovers_and_says_what_it_found(app: FastAPI) -> None:
    """ADR 0023 §11: the lifespan calls ``recover()`` once, and the result is readable."""
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url=BASE, headers=AUTHORIZED) as client,
    ):
        body = (await client.get("/diagnostics")).json()

    assert body["recovered"] == {"failed": 0, "skipped": 0, "expired": 0}


@pytest.mark.parametrize("route", ["/diagnostics", "/health"])
async def test_no_secret_ever_reaches_a_response(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    """Not the API token, not the provider key. A diagnostics page is read out loud."""
    text = (await client.get(route)).text

    assert TOKEN not in text
    assert "api_key" not in text and "token" not in text


async def test_the_schema_warns_that_the_plan_endpoint_is_temporary(client: AsyncClient) -> None:
    """The limit of ADR 0023 read by whoever *uses* the API, not only by whoever reads the ADR:
    until the Planner exists (§13), the shape of a plan is not something to build on."""
    schema = (await client.get("/openapi.json")).json()

    description = schema["paths"]["/tasks/{task_id}/plan"]["post"]["description"]
    assert description == PLAN_IS_TEMPORARY
    assert "temporary" in description and "without a version bump" in description
    assert "Planner" in description


async def test_the_schema_needs_the_token_too(anonymous: AsyncClient) -> None:
    assert (await anonymous.get("/openapi.json")).status_code == 401
