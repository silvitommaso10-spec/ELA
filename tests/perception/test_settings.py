"""``PerceptionSettings``: the two defaults that are decisions, and the three cadences.

ADR 0028 §6 and §7.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from ela.domain import ProbeFamily
from ela.perception import DEFAULT_INTERVALS, PerceptionSettings


def test_perception_is_on_and_the_loop_is_off_by_default() -> None:
    """The pair is the decision: ELA knows its own machine, and does not watch on its own.

    §11 applied one level up — nothing active without a reason — and turning the loop on stays a
    gesture somebody makes.
    """
    settings = PerceptionSettings()

    assert settings.perception_enabled is True
    assert settings.perception_loop_interval_seconds == 0
    assert settings.loop_enabled is False


def test_the_loop_needs_both_the_switch_and_an_interval() -> None:
    assert PerceptionSettings(perception_loop_interval_seconds=5).loop_enabled is True
    assert not PerceptionSettings(
        perception_enabled=False, perception_loop_interval_seconds=5
    ).loop_enabled


@pytest.mark.parametrize("family", list(ProbeFamily))
def test_each_family_has_its_own_interval(family: ProbeFamily) -> None:
    """Three cadences because the three readings differ by two orders of magnitude in cost and
    far more in how often they change (ADR 0028 §6)."""
    assert PerceptionSettings().interval(family) == timedelta(seconds=DEFAULT_INTERVALS[family])


def test_the_defaults_go_from_the_cheapest_and_fastest_to_the_dearest_and_slowest() -> None:
    """Not a coincidence to be preserved by luck: the order is the measurement."""
    intervals = [DEFAULT_INTERVALS[family] for family in ProbeFamily]

    assert intervals == sorted(intervals)


def test_a_negative_interval_is_refused_and_zero_is_not() -> None:
    """Zero means *always due*, which is a legitimate way to run this; below zero means nothing."""
    assert PerceptionSettings(perception_sensors_interval_seconds=0).interval(
        ProbeFamily.SENSORS
    ) == timedelta(0)
    with pytest.raises(ValueError, match="greater than or equal to 0"):
        PerceptionSettings(perception_sensors_interval_seconds=-1)


def test_a_timeout_of_zero_is_refused() -> None:
    """A probe given no time at all would report "not observable" forever, which is a lie about
    the machine rather than a reading of it."""
    with pytest.raises(ValueError, match="greater than 0"):
        PerceptionSettings(perception_probe_timeout_seconds=0)


def test_the_timeout_is_generous_by_two_orders_of_magnitude() -> None:
    """A full reading measured 35 ms. This is not a performance budget: it is the line past which
    a hung ``tccd`` stops being ELA's problem."""
    assert PerceptionSettings().probe_timeout >= timedelta(seconds=1)


def test_a_fractional_cadence_is_allowed() -> None:
    """Half a second is a legitimate way to run this, and ADR 0028 already contemplates faster."""
    assert PerceptionSettings(perception_loop_interval_seconds=0.5).loop_interval == timedelta(
        milliseconds=500
    )
