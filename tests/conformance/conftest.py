"""One Core, on a real database, with a clock the stories move (M12.2, dec. P; ADR 0038 §18).

Three things are real here and said out loud because the value of the suite depends on them: the
**application** (the same ``create_app`` production serves, middleware included), the **database**
(a SQLite file in ``tmp_path``, migrated, not an in-memory engine that two connections would see as
two databases), and the **protocol** (HTTP over the ASGI transport of ``httpx``).

One thing is deliberately not real: the **clock**. The Core is built with the ``FakeClock`` of
``ela.testing`` — through ``build(settings, clock=…)``, a declared parameter and not a patch —
six of the thirteen stories turn on an expiry, and a suite that waited out a TTL would be measuring
patience. What that costs is written among the limits: the expiry is proved, its tuning is not.

The settings are chosen so that the stories are playable rather than comfortable:

* ``ELA_ASSIGNMENT_TTL_SECONDS=60`` — one minute of silence before the Core decides a node is gone;
* ``ELA_ASSIGNMENT_MAX_SECONDS=120`` — a cap **two renewals** away, so "works longer than the TTL"
  can reach it without an hour of clock;
* ``ELA_NODE_POLL_SECONDS=1`` — the window a request for work is held, so a ``204`` costs a second
  and not twenty-five.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from ela.api import create_app
from ela.composition import Settings, build
from ela.testing.fakes import FakeClock
from tests.api.support import AUTHORIZED, BASE
from tests.composition.support import create_schema, declare
from tests.conformance.driver import Conformance

ASSIGNMENT_TTL = "60"
ASSIGNMENT_CAP = "120"
POLL = "1"


@pytest.fixture
async def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[Conformance]:
    """The Core the stories talk to, and the ``reborn`` that starts it again over the same file."""
    declare(
        monkeypatch,
        tmp_path,
        ELA_ASSIGNMENT_TTL_SECONDS=ASSIGNMENT_TTL,
        ELA_ASSIGNMENT_MAX_SECONDS=ASSIGNMENT_CAP,
        ELA_NODE_POLL_SECONDS=POLL,
    )
    settings = Settings.load()
    await create_schema(settings.persistence.db_url)
    clock = FakeClock()
    async with AsyncExitStack() as outer:
        process = await outer.enter_async_context(AsyncExitStack())
        built = await _started(settings, clock, process)
        world = Conformance(
            app=built[1],
            ela=built[0],
            clock=clock,
            client=built[2],
            base_url=BASE,
            reborn=lambda: _again(settings, clock, world, outer),
        )
        yield world


async def _started(
    settings: Settings, clock: FakeClock, stack: AsyncExitStack
) -> tuple[object, object, AsyncClient]:
    """One process of the Core: built, its lifespan run, a client of the user over it.

    The lifespan matters and is not decoration: ``recover()`` runs there, and "the Core dies
    halfway" is a story about what the **next** start-up does with what the last one left.
    """
    ela = await build(settings, clock=clock)
    stack.push_async_callback(ela.aclose)
    app = create_app(ela)
    await stack.enter_async_context(app.router.lifespan_context(app))
    client = await stack.enter_async_context(
        AsyncClient(transport=ASGITransport(app=app), base_url=BASE, headers=AUTHORIZED)
    )
    return ela, app, client


async def _again(
    settings: Settings, clock: FakeClock, world: Conformance, outer: AsyncExitStack
) -> None:
    """Close this process and start another over the same database, keeping the same clock.

    The old ELA is released — engine included — before the new one opens, so the second process
    finds the file and nothing of the first one's memory. The clock is the same object: a restart
    loses what was in memory, not the hour it is.
    """
    process = AsyncExitStack()
    ela, app, client = await _started(settings, clock, process)
    await world.ela.aclose()
    await world.client.aclose()
    outer.push_async_callback(process.aclose)
    world.ela = ela  # type: ignore[assignment]
    world.app = app  # type: ignore[assignment]
    world.client = client
