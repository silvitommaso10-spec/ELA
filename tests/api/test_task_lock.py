"""The lock of a task, taken with nothing in between (M13.3, C10 and R1; ADR 0023 §9).

``running_of`` promises that the check and the insert happen with no ``await`` between them, and
``run_task`` broke the promise: between ``identifier in running`` and ``running.add`` it wrote the
heartbeat of ``local`` and read the power source, which on a Mac is a ``pmset`` process. Two runs of
one task arriving together — the phone's "yes" and ``ela task run`` at the Mac — both passed the
check, and that is the race of M13.1b's risks (P4) in a configuration ELA declares.

The precondition is built, not waited for: a power reading that suspends until the test lets it go,
so the first run is **inside** whatever it does after the check at the instant the second arrives.
The assertion does not depend on where that is — today before the insert, after the repair inside
the walk —, only on what the lock promises: one run at a time, and a second one refused.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ela.api import create_app
from ela.composition import Settings, build
from ela.domain import PowerSource
from tests.api.support import AUTHORIZED, BASE, echo_plan, queued
from tests.composition.support import create_schema


class GatedPower:
    """A power reading that, once armed, holds its first caller until the test lets it go."""

    def __init__(self) -> None:
        self.armed = False
        self.reached = asyncio.Event()
        self.released = asyncio.Event()

    async def __call__(self) -> PowerSource:
        if self.armed:
            self.armed = False
            self.reached.set()
            await self.released.wait()
        return PowerSource.AC


@pytest.fixture
async def gated(settings: Settings) -> AsyncIterator[tuple[AsyncClient, GatedPower]]:
    power = GatedPower()
    await create_schema(settings.persistence.db_url)
    ela = await build(settings, power=power)
    app: FastAPI = create_app(ela)
    try:
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app), base_url=BASE, headers=AUTHORIZED
            ) as client,
        ):
            yield client, power
    finally:
        await ela.aclose()


async def test_two_runs_of_one_task_at_the_same_instant_are_one_run(
    gated: tuple[AsyncClient, GatedPower],
) -> None:
    client, power = gated
    task_id = await queued(client, echo_plan())

    power.armed = True
    first = asyncio.create_task(client.post(f"/tasks/{task_id}/run"))
    await power.reached.wait()  # the first run is suspended past its check of the lock
    second = await client.post(f"/tasks/{task_id}/run")
    power.released.set()
    answered = await first

    assert sorted([answered.status_code, second.status_code]) == [200, 409], (
        answered.text,
        second.text,
    )
    assert second.json()["error"]["code"] == "already_running"
