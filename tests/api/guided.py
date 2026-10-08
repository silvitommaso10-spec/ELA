"""An ELA with a guided session the test scripts (M14.3, ADR 0060): the whole road, nothing paid.

ELA as ``build`` makes it — the cap, the key and the sites declared, the browser of ``ela.testing``
— with three factories replaced, here and nowhere else, as ``tests/api/planning.py`` replaces one:

* the model's provider is **the real Anthropic adapter** over the client double of
  ``tests/providers``: the worst case of a session's call is the price list's;
* the gateway is **the real** :class:`~ela.providers.anthropic.AnthropicGateway` over a transport
  that answers as Anthropic streams (:class:`Anthropic`): the key goes on, the events come back;
* the session of Claude Code is a :class:`~ela.testing.fakes.FakeAgentSession` running a
  :class:`Script`, which calls the gateway **over HTTP**, from loopback, with its token — the route,
  the middleware, the room and the budget are the production ones — and asks for its gestures
  through the host, as the in-process tools do.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, cast

import httpx
import pytest
from anthropic import AsyncAnthropic
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ela.api import create_app
from ela.composition import Ela, Settings, build, root
from ela.ports import Clock, IdGenerator, SessionEnd, SessionHost, SessionPlan
from ela.providers.anthropic import AnthropicGateway, AnthropicProvider, AnthropicSettings
from ela.providers.anthropic.models import HAIKU_5_5
from ela.testing.fakes import FAKE_SESSION_TOOLS, FakeAgentSession, FakeBrowser, FakePower, finished
from tests.api.support import AUTHORIZED, BASE
from tests.composition.support import create_schema, declare
from tests.providers.support import SECRET, FakeAnthropic

SITES: Final = ["www.youtube.com", "example.com", "httpbin.org"]
"""The sites of the guide's section 26: YouTube for the sentence, section 20's two beside it."""

LOOPBACK: Final = "http://127.0.0.1:8765"
"""Where a session reaches ELA's gateway: both ends of the socket on loopback."""

MAX_COST: Final = "0.60"
"""The most a session of the proof may spend: one call of Haiku 5.5 at its worst, 0,516384 $."""

GOAL: Final = "Apri YouTube e cerca il canale di MrBeast."


def plan_of(**update: Any) -> dict[str, Any]:
    """A plan of one ``browser.guided`` step, as the guide's example writes it."""
    arguments: dict[str, Any] = {
        "goal": GOAL,
        "sites": ["www.youtube.com"],
        "max_cost_usd": MAX_COST,
        "looks": 8,
        "seconds": 600,
        **update,
    }
    return {
        "goal": "guidare il browser",
        "steps": [
            {
                "id": "3f0d1a44-5b6c-4d7e-8f90-000000000026",
                "goal": "cercare il canale",
                "required_capabilities": ["browser.guided"],
                "arguments": arguments,
                "risk": "MEDIUM",
                "expected_result": "il nome del canale",
                "success_conditions": [
                    "guided.closed",
                    "guided.gestures_audited",
                    "guided.reservations_closed",
                ],
            }
        ],
    }


def events(*, model: str = HAIKU_5_5, input_tokens: int = 1_200, output_tokens: int = 40) -> bytes:
    """One call as Anthropic streams it: the start with the input, the delta with the output, the
    stop."""
    start = {
        "type": "message_start",
        "message": {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": [],
            "usage": {"input_tokens": input_tokens, "output_tokens": 1},
        },
    }
    delta = {
        "type": "message_delta",
        "delta": {"stop_reason": "end_turn"},
        "usage": {"output_tokens": output_tokens},
    }
    return (
        f"event: message_start\ndata: {json.dumps(start)}\n\n"
        f"event: message_delta\ndata: {json.dumps(delta)}\n\n"
        'event: message_stop\ndata: {"type": "message_stop"}\n\n'
    ).encode()


@dataclass
class Anthropic:
    """The provider behind the gateway: what it received, and what it streams back."""

    received: list[httpx.Request] = field(default_factory=list)
    answer: bytes = field(default_factory=events)
    status: int = 200

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.received.append(request)
        return httpx.Response(
            self.status, headers={"content-type": "text/event-stream"}, content=self.answer
        )


def body_of(plan: SessionPlan, **update: Any) -> dict[str, Any]:
    """A call of the session as Claude Code sends it: its model, its ``max_tokens``, its tools."""
    return {
        "model": plan.model,
        "max_tokens": plan.max_tokens,
        "stream": True,
        "system": [{"type": "text", "text": plan.instructions}],
        "tools": [{"name": name, "input_schema": {}} for name in sorted(FAKE_SESSION_TOOLS)],
        "messages": [{"role": "user", "content": plan.goal}],
        **update,
    }


Step = Callable[["Script", SessionPlan, SessionHost], Awaitable[None]]


def call(**update: Any) -> Step:
    """A call to the gateway, over HTTP, with the session's token."""

    async def step(script: Script, plan: SessionPlan, host: SessionHost) -> None:
        response = await script.http(plan).post(
            "/v1/messages?beta=true",
            content=json.dumps(body_of(plan, **update)).encode(),
            headers={"x-api-key": plan.token, "anthropic-beta": "fine-grained-tool-streaming"},
        )
        script.answered.append((response.status_code, response.content))

    return step


def gesture(name: str, **arguments: Any) -> Step:
    """A gesture the model asks for, through the host as the in-process tools do."""

    async def step(script: Script, plan: SessionPlan, host: SessionHost) -> None:
        script.read.append(await host.gesture(name, arguments))

    return step


def obeying(name: str, **arguments: Any) -> Step:
    """A gesture a page told the model to make: made only if a page read in the session asked."""

    async def step(script: Script, plan: SessionPlan, host: SessionHost) -> None:
        if any("ignore your instructions" in page for page in script.read):
            script.read.append(await host.gesture(name, arguments))

    return step


def asked() -> Step:
    """A request for a permission, which the session denies by itself."""

    async def step(script: Script, plan: SessionPlan, host: SessionHost) -> None:
        await host.asked()

    return step


@dataclass
class Script:
    """A fake session's turn: the tools of its start, then its steps, then its last text."""

    steps: list[Step]
    tools: tuple[str, ...] = tuple(sorted(FAKE_SESSION_TOOLS))
    answer: str = "Il canale è @MrBeast: https://www.youtube.com/results?search_query=MrBeast"
    app: FastAPI | None = None
    plans: list[SessionPlan] = field(default_factory=list)
    answered: list[tuple[int, bytes]] = field(default_factory=list)
    read: list[str] = field(default_factory=list)

    def http(self, plan: SessionPlan) -> AsyncClient:
        assert self.app is not None
        return AsyncClient(transport=ASGITransport(app=self.app), base_url=plan.gateway)

    async def __call__(self, plan: SessionPlan, host: SessionHost) -> SessionEnd:
        self.plans.append(plan)
        if await host.started(self.tools) is not None:
            await asyncio.Event().wait()  # halted: ELA interrupts the session
        for step in self.steps:
            await step(self, plan, host)
        return finished(self.answer)


@dataclass(frozen=True)
class Guided:
    """One ELA, its application, a client with the Core's token, and the session's three ends."""

    ela: Ela
    app: FastAPI
    client: AsyncClient
    browser: FakeBrowser
    anthropic: Anthropic
    sessions: FakeAgentSession
    script: Script


@asynccontextmanager
async def guided(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    script: Script,
    *,
    session: FakeAgentSession | None = None,
    **declared: str,
) -> AsyncIterator[Guided]:
    anthropic = Anthropic()
    client = FakeAnthropic()
    agents = FakeAgentSession(script) if session is None else session

    def provider(
        clock: Clock, ids: IdGenerator, *, settings: AnthropicSettings | None = None
    ) -> AnthropicProvider:
        assert settings is not None
        return AnthropicProvider(
            cast(AsyncAnthropic, client), clock=clock, ids=ids, settings=settings
        )

    def gateway(*, settings: AnthropicSettings | None = None) -> AnthropicGateway:
        return AnthropicGateway(
            SECRET, timeout=5.0, transport=httpx.MockTransport(anthropic.handler)
        )

    monkeypatch.setattr(root, "anthropic_provider", provider)
    monkeypatch.setattr(root, "anthropic_gateway", gateway)
    monkeypatch.setattr(root, "ClaudeAgentSession", lambda folder: agents)
    values = {
        "ELA_SPENDING_CAP_USD": "30",
        "ELA_ANTHROPIC_API_KEY": SECRET,
        "ELA_BROWSER_SITES": json.dumps(SITES),
        **declared,
    }
    declare(monkeypatch, tmp_path, **values)
    settings = Settings.load()
    await create_schema(settings.persistence.db_url)
    browser = FakeBrowser()
    ela = await build(settings, power=FakePower(), browser=browser)
    app = create_app(ela)
    script.app = app
    try:
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app), base_url=BASE, headers=AUTHORIZED
            ) as http,
        ):
            yield Guided(ela, app, http, browser, anthropic, agents, script)
    finally:
        await ela.aclose()


async def planned(g: Guided, **update: Any) -> str:
    """A task with the plan of one session, queued: its id."""
    task = str((await g.client.post("/tasks", json={"text": GOAL})).json()["id"])
    response = await g.client.post(f"/tasks/{task}/plan", json=plan_of(**update))
    assert response.status_code == 200, response.text
    return task


async def run(g: Guided, task: str) -> dict[str, Any]:
    response = await g.client.post(f"/tasks/{task}/run")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def question(g: Guided, task: str) -> dict[str, Any]:
    (found,) = [one for one in (await g.client.get("/approvals")).json() if one["task_id"] == task]
    return cast(dict[str, Any], found)


async def approve(g: Guided, task: str) -> None:
    asked_ = await question(g, task)
    response = await g.client.post(f"/tasks/{task}/approve", json={"approval_id": asked_["id"]})
    assert response.status_code == 200, response.text


async def approved_and_run(g: Guided, task: str) -> dict[str, Any]:
    """The session's question, the yes, and the run that launches the session."""
    first = await run(g, task)
    assert first["outcome"] == "waiting_approval", first
    await approve(g, task)
    return await run(g, task)
