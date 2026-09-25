"""The heartbeat of ``local``, written by the Core (M13.3, ADR 0048 §2; ADR 0044 §8).

The loop is driven by the test and not by time: its wait is injected, and each wait is an event the
test sets — a duration waited for is how a suite starts measuring the machine it runs on (ADR 0006
§13).
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest

from ela.devices import (
    BEATS_PER_TTL,
    LOCAL_DEVICE_ID,
    DeviceRegistry,
    LocalHeartbeat,
    is_available,
    period_of,
)
from ela.domain import DeviceStatus, PowerSource
from ela.ports import LocalBeat
from ela.testing.fakes import FakeClock, FakePower
from tests.devices.conftest import TTL


class Steps:
    """A wait the test opens one step at a time, and that says when the loop is waiting."""

    def __init__(self) -> None:
        self.waiting = asyncio.Event()
        self.go = asyncio.Event()
        self.asked: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.asked.append(seconds)
        self.waiting.set()
        await self.go.wait()
        self.go.clear()

    async def next(self) -> None:
        """Let one wait end, and come back when the loop is waiting again."""
        self.waiting.clear()
        self.go.set()
        await self.waiting.wait()


class Failing:
    """A power reading that fails once, then answers: the database busy for one beat, say."""

    def __init__(self) -> None:
        self.failed = False

    async def __call__(self) -> PowerSource:
        if not self.failed:
            self.failed = True
            raise OSError("busy")
        return PowerSource.AC


async def nothing_runs() -> bool:
    """No step runs on ``local``: the status the beat writes is ``IDLE``."""
    return False


async def local(registry: DeviceRegistry) -> DeviceRegistry:
    await registry.ensure_local()
    return registry


def test_the_period_is_a_third_of_the_ttl_and_not_a_setting_of_its_own() -> None:
    assert BEATS_PER_TTL == 3
    assert period_of(TTL) == timedelta(seconds=20)


def test_a_heartbeat_with_no_period_is_refused(registry: DeviceRegistry) -> None:
    for period in (timedelta(0), timedelta(seconds=-1)):
        with pytest.raises(ValueError, match="positive period"):
            LocalHeartbeat(registry, FakePower(), busy=nothing_runs, period=period)


def test_the_service_is_the_port_the_runner_is_given(registry: DeviceRegistry) -> None:
    heartbeat = LocalHeartbeat(registry, FakePower(), busy=nothing_runs, period=period_of(TTL))

    assert isinstance(heartbeat, LocalBeat)
    assert heartbeat.period == period_of(TTL)


async def test_a_beat_makes_local_alive_with_the_power_read_now(
    registry: DeviceRegistry, clock: FakeClock
) -> None:
    power = FakePower(PowerSource.BATTERY)
    heartbeat = LocalHeartbeat(
        await local(registry), power, busy=nothing_runs, period=period_of(TTL)
    )

    await heartbeat.beat()

    device = await registry.get(LOCAL_DEVICE_ID)
    assert is_available(device, clock.now(), TTL)
    assert device.power_source is PowerSource.BATTERY
    assert power.asked == 1


@pytest.mark.parametrize(
    ("running", "status"), [(True, DeviceStatus.BUSY), (False, DeviceStatus.IDLE)]
)
async def test_a_beat_says_what_the_core_observes_of_local(
    registry: DeviceRegistry, running: bool, status: DeviceStatus
) -> None:
    """M13.3, decision 2: the status of ``local`` is the Core's observation — ``BUSY`` while a step
    runs here — and the beat is handed the question, as it is handed the power reading."""

    async def busy() -> bool:
        return running

    heartbeat = LocalHeartbeat(await local(registry), FakePower(), busy=busy, period=period_of(TTL))

    await heartbeat.beat()

    assert (await registry.get(LOCAL_DEVICE_ID)).status is status


async def test_the_loop_beats_once_a_period_and_keeps_going_after_a_failed_beat(
    registry: DeviceRegistry, clock: FakeClock
) -> None:
    steps = Steps()
    heartbeat = LocalHeartbeat(
        await local(registry), Failing(), busy=nothing_runs, period=period_of(TTL), wait=steps
    )
    loop = asyncio.create_task(heartbeat.run())
    await steps.waiting.wait()
    assert steps.asked == [20.0]  # it waits first: start-up has just beaten

    await steps.next()  # the first beat fails, and the loop waits again
    assert (await registry.get(LOCAL_DEVICE_ID)).power_source is not PowerSource.AC

    clock.advance(TTL * 2)
    await steps.next()  # the second beat lands
    device = await registry.get(LOCAL_DEVICE_ID)
    assert is_available(device, clock.now(), TTL)
    assert device.power_source is PowerSource.AC

    loop.cancel()
    with pytest.raises(asyncio.CancelledError):
        await loop
