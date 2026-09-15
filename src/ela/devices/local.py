"""The one node of v0.1: ``local``, the machine the Core runs on (§16, §54; ADR 0016 §4).

Its :class:`~ela.domain.DeviceId` is a UUIDv5 over a fixed namespace and the name ``local``, so
it is the same id in every process and on every run: a registry that invented a new id at each
start would collect a node per boot. What ``local`` declares is only what can be known without
probing the hardware — the operating system, that the node is on the local network — and, where
nothing can be known, ``UNKNOWN``. ``privacy`` has no ``UNKNOWN`` and is set to the most
restrictive level: an undeclared privacy must never be read as permission to send data out
(§33, §57).

What a machine says of its **power** is mapped here too (M12.3c), beside what it says of its system
and for the same reason: a node reads the same words and needs the same map, and the readers in
``ela.infrastructure.machine`` hand over words and decide nothing (ADR 0028 §1). The power source is
not a fact of the registration — ``local`` is born ``UNKNOWN`` — but of every heartbeat.
"""

from __future__ import annotations

import platform
from collections.abc import Mapping
from datetime import datetime
from types import MappingProxyType
from typing import Final
from uuid import NAMESPACE_DNS, uuid5

from ela.devices.errors import UnsupportedOperatingSystemError
from ela.domain import (
    Actor,
    ActorKind,
    Device,
    DeviceAvailability,
    DeviceId,
    DeviceStatus,
    NetworkKind,
    OperatingSystem,
    PerformanceClass,
    PowerSource,
    PrivacyLevel,
)

__all__ = [
    "DEVICE_NAMESPACE",
    "DRAWING_FROM",
    "LOCAL_DEVICE_ID",
    "LOCAL_DEVICE_NAME",
    "LOCAL_USER",
    "POWER_LINE",
    "SYSTEMS",
    "local_device",
    "operating_system",
    "power_drawn_from",
    "power_on_the_line",
]

DEVICE_NAMESPACE: Final = uuid5(NAMESPACE_DNS, "devices.ela")
"""The namespace every deterministic device id is derived from."""

LOCAL_DEVICE_NAME: Final = "local"

LOCAL_DEVICE_ID: Final = DeviceId(uuid5(DEVICE_NAMESPACE, LOCAL_DEVICE_NAME))
"""Deterministic: the same id in every process, so ``ensure_local`` registers one node ever."""

LOCAL_USER: Final = Actor(kind=ActorKind.USER, id=str(LOCAL_DEVICE_ID))
"""The user at this machine: who the Core's token is, since M12.1 (D12; ADR 0037 §15).

The id is ``local``'s because what the audit gains is *where* an act came from, resolved and not
declared; the kind is ``USER`` because who approves, issues a code or revokes a node is a person,
not a device. In M12.1 it is the only identity that can issue a code or revoke (ADR 0037 §4).
"""

SYSTEMS: Final[Mapping[str, OperatingSystem]] = MappingProxyType(
    {
        "Darwin": OperatingSystem.MACOS,
        "Windows": OperatingSystem.WINDOWS,
        "Linux": OperatingSystem.LINUX,
    }
)
"""What ``platform.system()`` returns, mapped to the domain. ``IOS`` is not here: no Core runs on
an iPhone — that node will register itself over the network (M7), it is not detected locally."""


def operating_system(system: str) -> OperatingSystem:
    """The domain value for a ``platform.system()`` string.

    :raises UnsupportedOperatingSystemError: for anything else, before a node is built.
    """
    try:
        return SYSTEMS[system]
    except KeyError:
        raise UnsupportedOperatingSystemError(system) from None


DRAWING_FROM: Final[Mapping[str, PowerSource]] = MappingProxyType(
    {"AC Power": PowerSource.AC, "Battery Power": PowerSource.BATTERY}
)
"""What ``pmset -g batt`` names on its first line, mapped to the domain (M12.3c).

The two words P6 measured on this Mac on 2026-09-15, plugged in and unplugged, and no others: a
word nobody measured — ``UPS Power`` exists — is worth what a fact nobody observed is worth.
"""

POWER_LINE: Final[Mapping[str, PowerSource]] = MappingProxyType(
    {"Online": PowerSource.AC, "Offline": PowerSource.BATTERY}
)
"""What ``SystemInformation.PowerStatus.PowerLineStatus`` answers, mapped to the domain (M12.3c).

Its third value, ``Unknown``, is not here, for the same reason."""


def power_drawn_from(source: str | None) -> PowerSource:
    """The domain value for what a Mac says it draws from; ``UNKNOWN`` if it said nothing readable.

    ``UNKNOWN`` scores zero, as ``BATTERY`` does (``POWER_POINTS``): a reading that failed can cost
    a machine its points and never earn it any.
    """
    if source is None:
        return PowerSource.UNKNOWN
    return DRAWING_FROM.get(source, PowerSource.UNKNOWN)


def power_on_the_line(status: tuple[str, int] | None) -> PowerSource:
    """The domain value for what a PC says of its power line and of how many batteries it has.

    **A machine with no battery is on AC** (decisione del 2026-09-15), whatever its line says: there
    is nothing else it could be drawing from. The PC of P6 is that case — ``Online``, ``0``,
    ``NoSystemBattery``.
    """
    if status is None:
        return PowerSource.UNKNOWN
    line, batteries = status
    if batteries == 0:
        return PowerSource.AC
    return POWER_LINE.get(line, PowerSource.UNKNOWN)


def local_device(
    created_at: datetime,
    *,
    system: str | None = None,
    available_tools: tuple[str, ...] = (),
) -> Device:
    """The ``local`` node as it is first registered: nothing claimed that was not observed.

    ``system`` defaults to ``platform.system()``; the tests pass it instead of patching the
    interpreter. ``availability`` and ``status`` start ``UNKNOWN`` and ``last_seen_at`` ``None``
    because no heartbeat has arrived yet — and a node never seen is not available (ADR 0016 §3).
    ``available_tools`` is given by the caller: which tools exist depends on a workspace root the
    registry has no business knowing (ADR 0016 §4).
    """
    return Device(
        id=LOCAL_DEVICE_ID,
        created_at=created_at,
        name=LOCAL_DEVICE_NAME,
        os=operating_system(platform.system() if system is None else system),
        availability=DeviceAvailability.UNKNOWN,
        status=DeviceStatus.UNKNOWN,
        capabilities=(),
        available_tools=available_tools,
        performance=PerformanceClass.UNKNOWN,
        network=NetworkKind.LOCAL,
        power_source=PowerSource.UNKNOWN,
        privacy=PrivacyLevel.LOCAL_ONLY,
        current_workload=None,
        last_seen_at=None,
    )
