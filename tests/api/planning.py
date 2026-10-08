"""An ELA whose model answers what the test writes, for the routes of the Planner (M14.2, ADR 0058).

ELA as ``build`` makes it — the cap and the key declared, as on the Mac of the proof — with **the
real Anthropic adapter over the client double** of ``tests/providers``: the request the Planner
makes is built, sent and read by the code that will send it for real, and no socket is opened
(``tests/conftest.py``). The one thing replaced is the factory that would give the adapter the SDK's
client, as ``tests/api/test_server.py`` replaces uvicorn — **here and nowhere else**, and with the
default ``raising=True``: a factory renamed tomorrow fails the patch instead of letting the real one
through. A parameter of ``build`` would have been a door in the product opened for the tests (review
of the summary of M14.2, question 1).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

import pytest
from anthropic import AsyncAnthropic
from httpx import AsyncClient

from ela.composition import root
from ela.ports import Clock, IdGenerator
from ela.providers.anthropic import AnthropicProvider, AnthropicSettings
from ela.providers.anthropic.models import OPUS_5_5
from tests.api.reasons import World, opened
from tests.executive.planning import GOAL, NO_PLAN, NOTE_PLAN
from tests.providers.support import SECRET, FakeAnthropic, answer

__all__ = ["GOAL", "NO_PLAN", "NOTE_PLAN", "asked", "created", "said", "with_a_model"]


def said(text: str) -> Any:
    """What the model answers, as the SDK would have parsed it: the model of the planning route."""
    return answer(text, model=OPUS_5_5, input_tokens=4_000, output_tokens=600)


@asynccontextmanager
async def with_a_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *answers: Any, **declared: str
) -> AsyncIterator[tuple[World, FakeAnthropic]]:
    """The world of ``tests/api/reasons.py`` with a cap, a key, and a model that answers."""
    client = FakeAnthropic(*answers)

    def provider(
        clock: Clock, ids: IdGenerator, *, settings: AnthropicSettings | None = None
    ) -> AnthropicProvider:
        assert settings is not None
        return AnthropicProvider(
            cast(AsyncAnthropic, client), clock=clock, ids=ids, settings=settings
        )

    monkeypatch.setattr(root, "anthropic_provider", provider)
    values = {"ELA_SPENDING_CAP_USD": "30", "ELA_ANTHROPIC_API_KEY": SECRET, **declared}
    async with opened(monkeypatch, tmp_path, **values) as world:
        yield world, client


async def created(client: AsyncClient, goal: str = GOAL) -> str:
    return str((await client.post("/tasks", json={"text": goal})).json()["id"])


async def asked(client: AsyncClient, task_id: str) -> dict[str, Any]:
    """The first ``/planning`` of a task: its planning task, waiting for the yes to its call."""
    response = await client.post(f"/tasks/{task_id}/planning")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    assert body["outcome"] == "waiting_approval", body
    return body
