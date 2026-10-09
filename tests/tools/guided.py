"""The guided session of a test (M14.3, ADR 0060): a room over fakes, a session that runs no model.

``production_tools`` and ``production_verifiers`` build ``browser.guided`` and its verifier like
every other tool, so whoever calls them names the room, the session and the gateway they hold —
most tests want :func:`a_room` and :func:`a_session`. The tests of the tool itself want more: a
world (:func:`guided_world`) with the reservation the cap would have written in the ``STARTED``
record of the step, a fake provider whose worst case names ``fake-model``, and a fake gateway that
prices it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Any, Final

from ela.domain import (
    Actor,
    ActorKind,
    ExecutionId,
    ExecutionResult,
    ExecutionStatus,
    PermissionDecision,
    WorstCase,
)
from ela.executive.sessions import SessionRoom
from ela.executive.spending import SpendingGate
from ela.permissions import BROWSER_GUIDED, production_catalogue
from ela.tasks.engine import TaskEngine
from ela.testing.fakes import (
    FakeAgentSession,
    FakeApprovalStore,
    FakeAuditLog,
    FakeClock,
    FakeExecutionResultStore,
    FakeIdGenerator,
    FakeModelGateway,
    FakeModelProvider,
    FakeTaskRepository,
    SessionScript,
)
from ela.tools.guided import BrowserGuidedTool
from tests.domain.examples import NOW, STEP_ID, TASK_ID
from tests.routing.support import routing_for
from tests.tools.support import allowed

GATEWAY: Final = "http://127.0.0.1:8765"
"""Where the gateway of a test's ELA would answer."""

MODEL: Final = "fake-model"
"""The model the fake provider's worst case names, and the fake gateway prices."""

ARGUMENTS: Final[dict[str, Any]] = {
    "goal": "Apri YouTube e cerca il canale di MrBeast.",
    "sites": ["www.youtube.com"],
    "max_cost_usd": "0.05",
    "looks": 8,
    "seconds": 120,
}
"""The sentence of the registration, on its site, with a budget of five cents."""


def a_room() -> SessionRoom:
    """A room of the sessions over fakes, with no runner: a test that walks a gesture builds a
    world with one (``tests/executive/guided_world.py``)."""
    repository, results = FakeTaskRepository(), FakeExecutionResultStore()
    return SessionRoom(
        engine=_engine(repository),
        repository=repository,
        results=results,
        capabilities=production_catalogue(),
        spending=SpendingGate(results, None),
        gateway=FakeModelGateway(),
        running=set(),
    )


def a_session() -> FakeAgentSession:
    return FakeAgentSession()


def _engine(repository: FakeTaskRepository) -> TaskEngine:
    return TaskEngine(
        repository,
        FakeAuditLog(),
        FakeClock(),
        FakeIdGenerator(),
        approvals=FakeApprovalStore(),
        actor=Actor(kind=ActorKind.ELA, id="ela"),
        orphan_after=timedelta(minutes=15),
    )


async def no_wait(seconds: float) -> None:
    """The sleep of a session's duration that never ends by itself: the test ends the session."""
    await asyncio.Event().wait()


@dataclass
class GuidedWorld:
    """The tool of ``browser.guided`` on its fakes, and what a test reads afterwards."""

    tool: BrowserGuidedTool
    room: SessionRoom
    session: FakeAgentSession
    gateway: FakeModelGateway
    results: FakeExecutionResultStore
    provider: FakeModelProvider
    decision: PermissionDecision = field(default_factory=lambda: allowed(BROWSER_GUIDED))
    arguments: dict[str, Any] = field(default_factory=lambda: dict(ARGUMENTS))


def guided_world(
    script: SessionScript | None = None,
    *,
    session: FakeAgentSession | None = None,
    reserved: Decimal | None = Decimal("0.05"),
    sleep: Callable[[float], Awaitable[None]] = no_wait,
    worst: WorstCase | None = None,
) -> GuidedWorld:
    """The tool with a room whose results hold the ``STARTED`` record the cap would have written
    for the step — ``reserved`` dollars, one call of ``fake-model`` at a time —, unless
    ``reserved`` is ``None``."""
    repository, results = FakeTaskRepository(), FakeExecutionResultStore()
    gateway = FakeModelGateway()
    room = SessionRoom(
        engine=_engine(repository),
        repository=repository,
        results=results,
        capabilities=production_catalogue(),
        spending=SpendingGate(results, Decimal("30")),
        gateway=gateway,
        running=set(),
    )
    provider = FakeModelProvider(FakeClock(), FakeIdGenerator(), worst=worst)
    router, providers = routing_for(provider)
    agents = (
        session
        if session is not None
        else (FakeAgentSession() if script is None else FakeAgentSession(script))
    )
    tool = BrowserGuidedTool(
        room,
        agents,
        router,
        providers,
        FakeClock(),
        FakeIdGenerator(),
        gateway=GATEWAY,
        sleep=sleep,
    )
    if reserved is not None:
        record = started(reserved)
        # Written as the cap writes it, before the tool runs: the fake's store, synchronously.
        results._results[record.id] = record  # noqa: SLF001
    return GuidedWorld(tool, room, agents, gateway, results, provider)


def started(amount: Decimal) -> ExecutionResult:
    """The ``STARTED`` record the cap writes for the step of the example decision: the
    reservation of the session."""
    return ExecutionResult(
        id=ExecutionId(STEP_ID),
        created_at=NOW,
        capability_id=BROWSER_GUIDED,
        status=ExecutionStatus.STARTED,
        task_id=TASK_ID,
        step_id=STEP_ID,
        tool_name="browser-guided",
        worst_case=WorstCase(
            amount=amount,
            currency="USD",
            model=MODEL,
            input_tokens=1_000,
            output_tokens=100,
            per_call=True,
        ),
    )
