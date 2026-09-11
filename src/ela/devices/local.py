"""The one node of v0.1: ``local``, the machine the Core runs on (§16, §54; ADR 0016 §4).

Its :class:`~ela.domain.DeviceId` is a UUIDv5 over a fixed namespace and the name ``local``, so
it is the same id in every process and on every run: a registry that invented a new id at each
start would collect a node per boot. What ``local`` declares is only what can be known without
probing the hardware — the operating system, that the node is on the local network — and, where
nothing can be known, ``UNKNOWN``. ``privacy`` has no ``UNKNOWN`` and is set to the most
restrictive level: an undeclared privacy must never be read as permission to send data out
(§33, §57).
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
    "LOCAL_DEVICE_ID",
    "LOCAL_DEVICE_NAME",
    "LOCAL_USER",
    "SYSTEMS",
    "local_device",
    "operating_system",
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
