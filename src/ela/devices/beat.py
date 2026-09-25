"""The heartbeat of ``local``, written by the Core (§16; M13.3, ADR 0048 §2; ADR 0044 §8).

Until M13.3 ``local`` beat at start-up and at the start of every ``POST /tasks/{id}/run``, and
nothing else: past ``ELA_DEVICE_HEARTBEAT_TTL_SECONDS`` the registry said — rightly, by ADR 0016 §3
— that no sign of life came from this machine, while the process was alive and serving the page
that said so. And inside one run a local step longer than the TTL left ``local`` expired for the
step after it, which then waited for a device, or went to another machine.

:class:`LocalHeartbeat` is the one writer of that heartbeat, and it writes it two ways:

* **on request, before every placement** (:meth:`beat`, the :class:`~ela.ports.LocalBeat` the
  runner is given): ``local`` is alive whenever the runner is about to choose it, and the power
  source the placement weighs was read at that instant — a periodic belief never decides an action
  (ADR 0029 §7);
* **on a period** (:meth:`run`, started by the application's lifespan): a third of the TTL, so two
  beats can be lost before the Mac reads as silent. This one decides nothing — no placement reads
  it that has not just asked for a fresh one —; it keeps true what the Device Center shows between
  one run and the next.

**And what ``local`` is doing, observed by the Core** (M13.3, decision 2 of the review of the
implementation; ADR 0048 §13): ``BUSY`` while a step runs on this machine, ``IDLE`` otherwise — the
two words a node says of itself. Until then ``local`` said nothing and scored 0 where an idle node
scored 10, and a PC won a race because nobody looked at the Mac. The fact is the Task Engine's, and
the beat is handed the question, as it is handed the power reading.

Not the perception's tick: it is off by default, and a heartbeat that needed perception on would
make the Mac disappear from the registry the day the user turned perception off. And not the wall
of the resident process (ADR 0029 §16, ADR 0039 §6): the loop lives inside ``ela serve``, which the
user already started in the foreground, and dies with it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Final

from ela.devices.local import LOCAL_DEVICE_ID
from ela.devices.registry import DeviceRegistry
from ela.domain import DeviceStatus, PowerSource

__all__ = ["BEATS_PER_TTL", "Busy", "LocalHeartbeat", "Wait", "period_of"]

BEATS_PER_TTL: Final = 3
"""How many periodic beats fit in one heartbeat TTL: two may be lost before ``local`` expires."""

Wait = Callable[[float], Awaitable[None]]
"""How the loop waits between two beats: ``asyncio.sleep``, or a test's own event."""

Busy = Callable[[], Awaitable[bool]]
"""Whether a step runs on ``local`` now: the Task Engine's answer, handed in by the composition."""


def period_of(ttl: timedelta) -> timedelta:
    """The period of the loop for a heartbeat TTL: a value derived, not a setting of its own."""
    return ttl / BEATS_PER_TTL


class LocalHeartbeat:
    """The heartbeat of ``local``: before every placement, and on a period (the module docstring).

    ``power`` is the reading of what this machine runs on — a function the composition hands over,
    because ``ela.devices`` does not import ``ela.composition`` — and ``busy`` the question whether
    a step runs here, the Task Engine's, because ``ela.devices`` does not import ``ela.tasks``. A
    beat that fails in the loop — the database busy, say — does not stop the loop; if the loop stops
    beating, ``local`` expires, and that is the right diagnosis, in the place where somebody looks.
    """

    __slots__ = ("_busy", "_period", "_power", "_registry", "_wait")

    def __init__(
        self,
        registry: DeviceRegistry,
        power: Callable[[], Awaitable[PowerSource]],
        *,
        busy: Busy,
        period: timedelta,
        wait: Wait = asyncio.sleep,
    ) -> None:
        if period <= timedelta(0):
            raise ValueError(f"a heartbeat needs a positive period, not {period}")
        self._registry = registry
        self._power = power
        self._busy = busy
        self._period = period
        self._wait = wait

    @property
    def period(self) -> timedelta:
        return self._period

    async def beat(self) -> None:
        """Write the heartbeat of ``local``, with the power source read now and the status
        observed now: ``BUSY`` while a step runs here, ``IDLE`` otherwise."""
        status = DeviceStatus.IDLE
        if await self._busy():
            status = DeviceStatus.BUSY
        await self._registry.heartbeat(
            LOCAL_DEVICE_ID, power_source=await self._power(), status=status
        )

    async def run(self) -> None:
        """Beat every :attr:`period` until cancelled; a failed beat is followed by the next one."""
        while True:
            await self._wait(self._period.total_seconds())
            try:
                await self.beat()
            except Exception:  # noqa: BLE001 — a missed beat is what expiry is for (ADR 0016 §3)
                continue
