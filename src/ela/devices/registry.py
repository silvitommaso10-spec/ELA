"""The Device Registry: which nodes exist, and which of them answered recently (§16, ADR 0016).

:class:`~ela.ports.DeviceRegistryPort` is storage — add a node, replace a node, read nodes. What
it cannot answer is the question §16 actually asks, "posso usarlo *adesso*": a stored
``availability`` says what was true when someone last wrote it, and keeps saying it after the node
has gone quiet. :class:`DeviceRegistry` puts the missing half on top of the port: a ``heartbeat``
that records a sign of life, and a deadline that turns silence into ``UNAVAILABLE`` **as the node
is read**, so no reader can be told a stale node is reachable because no sweeper has run yet
(ADR 0016 §3; §33: in doubt, no).

The vocabulary of §16 is AVAILABLE/UNAVAILABLE; the domain's is
:class:`~ela.domain.DeviceAvailability`. :data:`AVAILABLE` and :data:`UNAVAILABLE` are the mapping,
in one place: a fresh heartbeat is evidence the node answers (``ONLINE``), silence past the TTL is
evidence of nothing (``UNREACHABLE``) — not of ``OFFLINE``, which would claim the node is down
when all we know is that it stopped talking to us.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any, Final

from ela.devices.local import LOCAL_DEVICE_ID, local_device
from ela.domain import Device, DeviceAvailability, DeviceId, DeviceStatus
from ela.ports import AlreadyExistsError, Clock, DeviceRegistryPort, NotFoundError

__all__ = ["AVAILABLE", "UNAVAILABLE", "DeviceRegistry", "is_available"]

AVAILABLE: Final = DeviceAvailability.ONLINE
"""§16 "disponibile": the node answered within the TTL."""

UNAVAILABLE: Final = DeviceAvailability.UNREACHABLE
"""§16 "non disponibile": no sign of life within the TTL. Not ``OFFLINE`` — see the module doc."""


def is_available(device: Device, now: datetime, ttl: timedelta) -> bool:
    """Whether ``device`` answered recently enough to be used at ``now``.

    A node never seen (``last_seen_at is None``) is **not** available: registering a node is a
    statement that it exists, not that it answers (§33). The deadline is closed, like every
    deadline in the system (ADR 0005 §2-bis): at exactly ``last_seen_at + ttl`` it has passed.
    """
    return device.last_seen_at is not None and now < device.last_seen_at + ttl


def _with(device: Device, changes: Mapping[str, Any]) -> Device:
    """``device`` with ``changes`` applied, **revalidated**.

    ``model_copy(update=...)`` skips validation, so it alone would let a caller's
    ``current_workload=7.5`` into the registry past the domain's ``0.0..1.0``.
    """
    return Device.model_validate({**device.model_dump(), **changes})


class DeviceRegistry:
    """The nodes ELA can use, with the heartbeat deadline applied on every read.

    Not an implementation of :class:`~ela.ports.DeviceRegistryPort` and not usable as one: it
    *holds* a port and answers a different question. The port returns the row as stored; this
    returns the node as it is now.
    """

    __slots__ = ("_clock", "_devices", "_ttl")

    def __init__(
        self, devices: DeviceRegistryPort, clock: Clock, *, heartbeat_ttl: timedelta
    ) -> None:
        if heartbeat_ttl <= timedelta(0):
            raise ValueError(f"the heartbeat TTL must be positive, not {heartbeat_ttl}")
        self._devices = devices
        self._clock = clock
        self._ttl = heartbeat_ttl

    @property
    def heartbeat_ttl(self) -> timedelta:
        """How long a heartbeat keeps a node available."""
        return self._ttl

    def seen(self, device: Device, now: datetime) -> Device:
        """``device`` with ``availability`` answered from its last heartbeat, not from the row."""
        availability = AVAILABLE if is_available(device, now, self._ttl) else UNAVAILABLE
        return device.model_copy(update={"availability": availability})

    async def register(self, device: Device) -> Device:
        """Add a node and return it as it reads; :class:`AlreadyExistsError` if the id is taken.

        A node is registered ``UNAVAILABLE``, whatever the caller declared: nothing has been
        heard from it yet.
        """
        await self._devices.register(device)
        return self.seen(device, self._clock.now())

    async def update(self, device: Device) -> Device:
        """Replace a registered node — a configuration change; :class:`NotFoundError` if unknown.

        Not the way to report a sign of life: that is ``heartbeat``.
        """
        await self._devices.update(device)
        return self.seen(device, self._clock.now())

    async def get(self, device_id: DeviceId) -> Device:
        """The node with this id, as it is now; :class:`NotFoundError` if there is none."""
        return self.seen(await self._devices.get(device_id), self._clock.now())

    async def devices(self) -> tuple[Device, ...]:
        """Every node, in registration order, all judged against the same instant."""
        now = self._clock.now()
        return tuple(self.seen(device, now) for device in await self._devices.devices())

    async def available(self) -> tuple[Device, ...]:
        """The nodes whose last heartbeat is still worth something, in registration order.

        The question "which nodes can ELA use right now" belongs here, where availability is
        derived (ADR 0016 §3): a caller that filtered on the field itself would be reading a
        column that keeps saying ``AVAILABLE`` after a node went quiet — which is what
        architecture rule 20 exists to prevent.
        """
        return tuple(device for device in await self.devices() if device.availability is AVAILABLE)

    async def heartbeat(
        self,
        device_id: DeviceId,
        *,
        status: DeviceStatus | None = None,
        current_workload: float | None = None,
    ) -> Device:
        """Record a sign of life from a node, optionally with what it is doing (§16).

        ``status`` and ``current_workload`` are the node's own report and are written only when
        given: a heartbeat that says nothing about them must not erase what was known.

        Read-modify-write, not one atomic statement (ADR 0016 §5). Two heartbeats racing on the
        same node can only lose one ``last_seen_at``, leaving the older of two recent instants —
        the node stays available, and no other field is at stake because a heartbeat writes no
        other field on its own.

        :raises NotFoundError: if the node is not registered. A heartbeat never registers one:
            an unknown node announcing itself is M7's business, and it goes through the Guardian.
        """
        now = self._clock.now()
        device = await self._devices.get(device_id)
        changes: dict[str, Any] = {"last_seen_at": now, "availability": AVAILABLE}
        if status is not None:
            changes["status"] = status
        if current_workload is not None:
            changes["current_workload"] = current_workload
        seen = _with(device, changes)
        await self._devices.update(seen)
        return seen

    async def ensure_local(
        self, *, system: str | None = None, available_tools: tuple[str, ...] = ()
    ) -> Device:
        """The ``local`` node, registered the first time and returned every time (§54).

        Idempotent by construction: the id is deterministic, so the second call finds the node
        the first one wrote — in this process or in the next one. The ``AlreadyExistsError``
        branch is the same answer for two callers racing between the read and the insert.
        """
        try:
            return await self.get(LOCAL_DEVICE_ID)
        except NotFoundError:
            pass
        device = local_device(self._clock.now(), system=system, available_tools=available_tools)
        try:
            return await self.register(device)
        except AlreadyExistsError:
            return await self.get(LOCAL_DEVICE_ID)
