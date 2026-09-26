"""Where a job goes between this Mac and a PC: the four cases of ADR 0048 §13 (M13.3, decision 2).

The status of ``local`` is observed since M13.3 — ``IDLE``, or ``BUSY`` while a step of its runs —
so the two machines are weighed on the same facts, and the choice of decision 2 is a rate of
exchange: **a Mac on battery gives a job to a PC on the mains; a Mac on the mains keeps it** —
while it is idle. ``POWER_POINTS`` of ``AC`` is 20 for that, and nothing else of ADR 0017 changes:
with 10, the gap of the network (15) was wider than the gap of the power, and the reading of the
power source that M12.3c brought could never move a job from the Mac to the PC.

The PC is the one of §12 of the guide: on the tailnet, on the mains, idle, performance unknown.
"""

from __future__ import annotations

import pytest

from ela.devices import NETWORK_POINTS, POWER_POINTS, choose, score
from ela.domain import Device, DeviceStatus, NetworkKind, PowerSource
from tests.devices.nodes import needs, node

PC = node(
    "pc",
    network=NetworkKind.REMOTE,
    power_source=PowerSource.AC,
    status=DeviceStatus.IDLE,
)


def mac(power: PowerSource, status: DeviceStatus) -> Device:
    return node("local", network=NetworkKind.LOCAL, power_source=power, status=status)


@pytest.mark.parametrize(
    ("power", "status", "mac_points", "winner"),
    [
        (PowerSource.AC, DeviceStatus.IDLE, 50, "local"),
        (PowerSource.AC, DeviceStatus.BUSY, 30, "pc"),
        (PowerSource.BATTERY, DeviceStatus.IDLE, 30, "pc"),
        (PowerSource.BATTERY, DeviceStatus.BUSY, 10, "pc"),
    ],
    ids=["mains-idle", "mains-busy", "battery-idle", "battery-busy"],
)
def test_the_four_cases_against_a_pc_on_the_mains_and_idle(
    power: PowerSource, status: DeviceStatus, mac_points: int, winner: str
) -> None:
    here = mac(power, status)

    placed = choose([here, PC], needs())

    assert score(here, needs()).points == mac_points
    assert score(PC, needs()).points == 35
    assert placed.device is not None and placed.device.name == winner


def test_the_gap_of_the_power_is_wider_than_the_gap_of_the_network() -> None:
    """The reason of the choice, as arithmetic: the power can move a job from an idle Mac to a PC
    only if it weighs more than the distance does."""
    network_gap = NETWORK_POINTS[NetworkKind.LOCAL] - NETWORK_POINTS[NetworkKind.REMOTE]
    power_gap = POWER_POINTS[PowerSource.AC] - POWER_POINTS[PowerSource.BATTERY]

    assert (network_gap, power_gap) == (15, 20)
