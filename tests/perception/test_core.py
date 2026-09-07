"""``PerceptionCore``: the cadences, the merge, the loop, and the audit that stays empty.

The four properties here are the ones that would be easy to get wrong and hard to notice:

* a tick asks for the families that are **due**, and for nothing else;
* a family that was not re-read keeps what it had, instead of appearing to have vanished;
* a tick writes **zero** audit events;
* a probe that breaks its contract does not take the loop down with it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import timedelta

import pytest

from ela.domain import ProbeFamily, RawObservation, SensorCause, SensorState, SystemPermission
from ela.perception import PerceptionCore, PerceptionSettings
from ela.testing.fakes import FakeAuditLog, FakeClock, FakeProbe

MAC = RawObservation(
    camera_count=1,
    microphone_count=1,
    microphone_in_use=False,
    display_count=1,
    display_asleep=False,
    screen_locked=False,
    on_console=True,
    idle_seconds=0.5,
    camera_permission=3,
    microphone_permission=3,
    screen_recording_permission=False,
)


def core(
    probe: FakeProbe, clock: FakeClock | None = None, **settings: object
) -> tuple[PerceptionCore, FakeClock]:
    ticking = clock or FakeClock()
    return PerceptionCore(probe, ticking, PerceptionSettings(**settings)), ticking  # type: ignore[arg-type]


# ----------------------------------------------------------------------------------------
# Before the first look
# ----------------------------------------------------------------------------------------


async def test_a_freshly_built_core_believes_nothing_and_says_so() -> None:
    """ "OFF by default" reconciled with ``ACTIVE`` meaning "in use by anyone": before the first
    tick ELA has not looked, and ``NOT_LOOKING`` is literally what happened."""
    watcher, _ = core(FakeProbe())

    assert watcher.view.observation.microphone.state == SensorState.OFF
    assert watcher.view.observation.microphone.cause == SensorCause.NOT_LOOKING
    assert watcher.view.changes == ()


async def test_the_first_tick_asks_for_every_family() -> None:
    probe = FakeProbe([MAC])
    watcher, _ = core(probe)

    await watcher.tick()

    assert probe.calls == (frozenset(ProbeFamily),)
    assert watcher.view.observation.microphone.cause == SensorCause.OBSERVED


# ----------------------------------------------------------------------------------------
# The cadences
# ----------------------------------------------------------------------------------------


async def test_a_second_tick_inside_every_interval_asks_for_nothing_and_spawns_nothing() -> None:
    """The cadence *is* the freshness contract: a read inside the interval answers what it saw."""
    probe = FakeProbe([MAC])
    watcher, clock = core(probe)
    await watcher.tick()
    seen = watcher.view.observation.observed_at

    assert await watcher.tick() == ()
    assert probe.calls == (frozenset(ProbeFamily),)
    assert watcher.view.observation.observed_at == seen


async def test_a_tick_asks_only_for_the_families_that_are_due() -> None:
    probe = FakeProbe([MAC])
    watcher, clock = core(probe)
    await watcher.tick()

    clock.advance(timedelta(seconds=2))
    await watcher.tick()

    assert probe.calls[1] == frozenset({ProbeFamily.SENSORS})


async def test_a_refresh_of_one_family_does_not_erase_the_others() -> None:
    """The easiest way to get differentiated cadences wrong: a permission read thirty seconds ago
    must not look like it became unreadable because this tick only asked about the microphone.

    Without ``merge`` the second tick would report three permissions "changing" to
    ``NOT_OBSERVABLE`` — a phantom change, and one that would repeat forever.
    """
    # The second answer carries only the SENSORS fields, because only SENSORS was asked.
    sensors_only = RawObservation(camera_count=1, microphone_count=1, microphone_in_use=False)
    probe = FakeProbe([MAC, sensors_only])
    watcher, clock = core(probe)
    await watcher.tick()

    clock.advance(timedelta(seconds=2))
    changes = await watcher.tick()

    assert changes == ()
    assert watcher.view.observation.permissions[SystemPermission.CAMERA].value == "GRANTED"
    assert watcher.view.observation.display_count == 1


async def test_an_interval_of_zero_means_always_due() -> None:
    probe = FakeProbe([MAC])
    watcher, _ = core(probe, perception_sensors_interval_seconds=0)
    await watcher.tick()

    await watcher.tick()

    assert probe.calls[1] == frozenset({ProbeFamily.SENSORS})


# ----------------------------------------------------------------------------------------
# Not looking at all
# ----------------------------------------------------------------------------------------


async def test_perception_disabled_never_spawns_anything() -> None:
    """``ELA_PERCEPTION_ENABLED=false``: ELA does not look, and does not pretend the world is off.

    The state is ``OFF`` because there is nothing else it could be, and the cause is what stops
    that from being read as an observation.
    """
    probe = FakeProbe([MAC])
    watcher, _ = core(probe, perception_enabled=False)

    await watcher.tick()
    await watcher.tick()

    assert probe.calls == ()
    assert watcher.view.observation.camera.cause == SensorCause.NOT_LOOKING


# ----------------------------------------------------------------------------------------
# The audit stays empty (ADR 0028 §10)
# ----------------------------------------------------------------------------------------


async def test_a_full_tick_writes_nothing_to_the_audit_log() -> None:
    """An observed change is not a decision of ELA's, and the audit records what ELA decides.

    Asserted through the port rather than by reading the source: the day ELA *causes* a state to
    change, this test is the one that has to be rewritten on purpose.
    """
    audit = FakeAuditLog()
    probe = FakeProbe([MAC, MAC.model_copy(update={"microphone_in_use": True})])
    watcher, clock = core(probe, perception_sensors_interval_seconds=0)

    await watcher.tick()
    clock.advance(timedelta(seconds=1))
    changes = await watcher.tick()

    assert [change.field for change in changes] == ["microphone"]
    assert await audit.read() == ()


def test_the_core_has_no_way_to_reach_an_audit_log() -> None:
    """Structural half of the same property: it is not wired to one, so it cannot start writing."""
    watcher, _ = core(FakeProbe())

    assert "audit" not in "".join(PerceptionCore.__slots__)
    assert not hasattr(watcher, "_audit")


# ----------------------------------------------------------------------------------------
# The loop
# ----------------------------------------------------------------------------------------


async def test_the_loop_returns_at_once_when_it_is_off() -> None:
    """The default: ELA answers when asked and does not watch on its own (ADR 0028 §7)."""
    probe = FakeProbe([MAC])
    watcher, _ = core(probe)

    await watcher.run()

    assert probe.calls == ()


async def test_the_loop_is_off_when_perception_is_off_whatever_the_interval_says() -> None:
    watcher, _ = core(FakeProbe(), perception_enabled=False, perception_loop_interval_seconds=0.01)

    await watcher.run()

    assert watcher.view.observation.camera.cause == SensorCause.NOT_LOOKING


async def test_a_tick_lets_a_broken_probe_speak_because_the_contract_is_the_contract() -> None:
    """``tick`` does not swallow it: an implementation that raises is a bug in that adapter, and
    hiding it here would make the port's promise unfalsifiable."""
    watcher, _ = core(FakeProbe(fails=True))

    with pytest.raises(RuntimeError):
        await watcher.tick()


async def test_a_probe_that_breaks_its_contract_does_not_stop_the_loop() -> None:
    """The loop is the place that must survive it. The belief becomes ``NOT_OBSERVABLE`` — where
    somebody will see it — and the next tick tries again.

    A log line would have been the other option, and it would have gone where nobody reads.
    """
    watcher, _ = core(FakeProbe(fails=True), perception_loop_interval_seconds=0.01)
    running = asyncio.create_task(watcher.run())
    await _until(lambda: watcher.view.observation.camera.cause == SensorCause.NOT_OBSERVABLE)

    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running

    assert watcher.view.observation.camera.state == SensorState.OFF


async def test_the_loop_keeps_ticking_until_it_is_cancelled() -> None:
    probe = FakeProbe([MAC])
    watcher, _ = core(
        probe, perception_sensors_interval_seconds=0, perception_loop_interval_seconds=1
    )
    running = asyncio.create_task(watcher.run())
    await _until(lambda: len(probe.calls) >= 2)

    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running

    assert watcher.view.observation.microphone.cause == SensorCause.OBSERVED


POLL = 0.001
"""How long ``_until`` parks between two looks. Not a budget: the loop's own cadence has to
elapse in real time, so the poll has to let real time pass — it exits on the event, never on a
deadline (ADR 0006 §13)."""


async def _until(done: Callable[[], bool], tries: int = 10_000) -> None:
    """Yield to the loop until ``done`` holds, then return immediately.

    The lesson of ADR 0006 §13: wait for the event, never for a duration. There is no budget to
    exhaust here — a slow machine takes more turns, not a failure — and the count is only a
    backstop so a genuinely stuck loop fails instead of hanging the suite.
    """
    for _ in range(tries):
        if done():
            return
        await asyncio.sleep(POLL)
    raise AssertionError("the loop never got there")
