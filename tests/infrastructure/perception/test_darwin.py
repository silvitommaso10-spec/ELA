"""The macOS adapter, tested without a Mac (ADR 0028 §1).

The port's hardest promise is **it does not fail, it reports**, and every way of failing is
something a test can produce with a fake spawn: a child that timed out, one killed by a signal,
one that printed nonsense, one that printed a key this version does not know. None of them needs
hardware, which is the point of pushing the decisions up and leaving primitives down here.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from datetime import timedelta

import pytest

from ela.domain import ProbeFamily, RawObservation
from ela.infrastructure.perception import PROBE_MODULE, TIMED_OUT, DarwinProbe

ALL = frozenset(ProbeFamily)


def answering(code: int, output: str) -> tuple[DarwinProbe, list[Sequence[str]]]:
    """A probe whose helper answers exactly this, and the argv it was asked to run."""
    seen: list[Sequence[str]] = []

    async def spawn(argv: Sequence[str], timeout: float) -> tuple[int, str]:
        del timeout
        seen.append(argv)
        return code, output

    return DarwinProbe(timeout=timedelta(seconds=1), runner=spawn), seen


async def test_a_good_answer_becomes_the_primitives_it_carries() -> None:
    probe, _ = answering(0, '{"camera_count": 2, "microphone_in_use": true, "idle_seconds": 0.5}')

    seen = await probe.read(ALL)

    assert (seen.camera_count, seen.microphone_in_use, seen.idle_seconds) == (2, True, 0.5)
    assert seen.display_count is None


async def test_the_helper_is_started_with_this_interpreter_and_the_families_asked_for() -> None:
    """``sys.executable`` and not ``python``: the child must inherit the virtual environment."""
    probe, seen = answering(0, "{}")

    await probe.read(frozenset({ProbeFamily.SENSORS, ProbeFamily.PERMISSIONS}))

    assert seen == [[sys.executable, "-m", PROBE_MODULE, "PERMISSIONS,SENSORS"]]


async def test_asking_for_nothing_starts_nothing() -> None:
    """The scheduler asks for what is due, and nothing being due is the normal case."""
    probe, seen = answering(0, "{}")

    assert await probe.read(frozenset()) == RawObservation()
    assert seen == []


@pytest.mark.parametrize(
    ("code", "output", "why"),
    [
        (TIMED_OUT, "", "the helper was killed for overstaying"),
        (-6, "", "the helper died of an Objective-C exception"),
        (1, "", "the helper could not start"),
        (0, "not json at all", "the helper printed nonsense"),
        (0, "[1, 2, 3]", "the helper printed the wrong shape"),
        (0, '{"camera_count": "two"}', "the helper printed the wrong type"),
        (0, '{"screen_brightness": 4}', "the helper printed a key this version does not know"),
        (0, '{"camera_count": -1}', "the helper printed a value the domain refuses"),
    ],
)
async def test_every_way_the_helper_can_let_us_down_reads_as_nothing_observed(
    code: int, output: str, why: str
) -> None:
    """One value for all of them, and it is a value the domain already has (ADR 0028 §2).

    Nothing here raises: a perception read must never be able to take ELA down with it (§33).
    """
    probe, _ = answering(code, output)

    assert await probe.read(ALL) == RawObservation(), why


async def test_a_spawn_that_cannot_start_at_all_is_not_an_exception_either() -> None:
    """No interpreter, no permission to execute: still an answer, still not a crash."""

    async def broken(argv: Sequence[str], timeout: float) -> tuple[int, str]:
        del argv, timeout
        raise OSError("no such file")

    probe = DarwinProbe(timeout=timedelta(seconds=1), runner=broken)

    assert await probe.read(ALL) == RawObservation()


async def test_the_timeout_reaches_the_spawn_in_seconds() -> None:
    seen: list[float] = []

    async def spawn(argv: Sequence[str], timeout: float) -> tuple[int, str]:
        del argv
        seen.append(timeout)
        return 0, "{}"

    await DarwinProbe(timeout=timedelta(milliseconds=250), runner=spawn).read(ALL)

    assert seen == [0.25]
