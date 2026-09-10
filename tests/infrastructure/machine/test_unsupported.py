"""Perception on an operating system that has none of this (ADR 0028, declared constraint).

Written as a test of an object with a name, and not as a note somewhere, for the reason the class
exists at all: "ELA on Linux perceives nothing" should be a fact somebody can look up, not a gap
they discover.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ela.domain import ProbeFamily, RawObservation, SensorCause
from ela.infrastructure.machine import UnsupportedProbe
from ela.perception import interpret, unobserved

AT = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "families", [frozenset(), frozenset({ProbeFamily.SENSORS}), frozenset(ProbeFamily)]
)
async def test_it_reads_nothing_whatever_it_is_asked_for(families: frozenset[ProbeFamily]) -> None:
    assert await UnsupportedProbe().read(families) == RawObservation()


async def test_what_ela_believes_on_linux_is_not_observable_and_not_off() -> None:
    """The distinction is the milestone's: ELA does not claim the microphone is off, it says it
    cannot see. The two render differently everywhere a sensor is shown."""
    seen = interpret(await UnsupportedProbe().read(frozenset(ProbeFamily)), at=AT)

    assert seen == unobserved(SensorCause.NOT_OBSERVABLE, at=AT)
