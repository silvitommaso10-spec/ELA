"""Which reader of the power source a machine gets, and the two producers that read it (M12.3c).

Chosen by **naming** the system (ADR 0031 §3), in the composition and nowhere else; read by both
things that write a heartbeat — a node, on every sign of life, and ``local``, on each of its own.
"""

from __future__ import annotations

import platform
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from ela.composition import Settings, build, build_node
from ela.composition.system import (
    power_nobody_reads,
    power_of_a_mac,
    power_of_a_pc,
    power_reading,
)
from ela.devices.local import LOCAL_DEVICE_ID
from ela.domain import PowerSource
from ela.testing.fakes import FakePower, FakeSpeech
from tests.composition.support import create_schema
from tests.node.support import config


class Child:
    """A fake ``spawn`` that answers what it was told to."""

    def __init__(self, output: str) -> None:
        self.output = output

    async def __call__(self, argv: Sequence[str], timeout: float) -> tuple[int, str]:
        return 0, self.output


SYSTEMS: list[tuple[str, Callable[..., object]]] = [
    ("Darwin", power_of_a_mac),
    ("Windows", power_of_a_pc),
    ("Linux", power_nobody_reads),
]


@pytest.mark.parametrize(("system", "reader"), [*SYSTEMS, ("Plan 9", power_nobody_reads)])
def test_the_reader_is_the_named_system_s(system: str, reader: Callable[..., object]) -> None:
    """An ``if`` per system and never a ternary (architecture rule 37): each arm is asked for by
    name, so the system this suite is *not* running on is proved too."""
    assert power_reading(system) is reader


async def test_a_system_nobody_reads_says_unknown() -> None:
    """Declared, and worth zero points: a fact nobody observed is never mistaken for a good one."""
    assert await power_nobody_reads() is PowerSource.UNKNOWN


async def test_a_mac_s_reading_is_pmset_s_words_through_the_mac_s_map() -> None:
    child = Child("Now drawing from 'Battery Power'\n")

    assert await power_of_a_mac(child, binary=sys.executable) is PowerSource.BATTERY


async def test_a_pc_s_reading_is_power_status_through_the_pc_s_map() -> None:
    child = Child("Online\r\n0\r\n")

    assert await power_of_a_pc(child, binary=sys.executable) is PowerSource.AC


@pytest.mark.parametrize(("system", "reader"), SYSTEMS)
def test_a_node_reads_the_power_of_the_system_it_was_built_for(
    tmp_path: Path, system: str, reader: Callable[..., object]
) -> None:
    built = build_node(config(tmp_path), speech=FakeSpeech(), system=system)

    assert built.power is reader


def test_the_node_s_power_is_a_declared_parameter(tmp_path: Path) -> None:
    """The same shape as ``speech``: a test names the machine instead of being it."""
    power = FakePower()

    assert build_node(config(tmp_path), speech=FakeSpeech(), power=power).power is power


async def test_local_says_what_this_machine_runs_on_when_the_core_starts(
    settings: Settings,
) -> None:
    """The heartbeat ``build`` writes for ``local`` carries the reading, and it is read once."""
    await create_schema(settings.persistence.db_url)
    power = FakePower(PowerSource.BATTERY)

    ela = await build(settings, power=power)
    try:
        assert ela.power is power
        assert power.asked == 1
        assert (await ela.devices.get(LOCAL_DEVICE_ID)).power_source is PowerSource.BATTERY
    finally:
        await ela.aclose()


async def test_without_the_seam_the_core_reads_the_system_it_runs_on(settings: Settings) -> None:
    """The default, asserted against what this machine's system gets and never against a value:
    whether this Mac is plugged in is not a property of the code."""
    await create_schema(settings.persistence.db_url)

    ela = await build(settings)
    try:
        assert ela.power is power_reading(platform.system())
    finally:
        await ela.aclose()
