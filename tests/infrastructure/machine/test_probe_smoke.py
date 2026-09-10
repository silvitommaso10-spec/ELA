"""The one test that touches the hardware, and it asserts nothing about the hardware.

``probe.py`` is the single module no runner can cover — no CI machine has a webcam — so what CI
can still prove is the part that does not depend on what is there: that the helper **runs**, that
its ``ctypes`` signatures are right, that it does not die of an Objective-C exception, and that
what it prints is the shape the adapter expects.

The line between this and the rest is deliberate. A test that asserted "there is a camera" would
pass on the machine that wrote it and fail on the runner, which is the mistake M9.1 spent its
first commit undoing (ADR 0006 §13). So: exit 0, valid JSON, known keys, and the values are
whatever this machine happens to be.
"""

from __future__ import annotations

import json
import platform
import subprocess  # noqa: S404 — this test *is* the one that starts the helper for real
import sys

import pytest

from ela.domain import FAMILY_FIELDS, ProbeFamily, RawObservation
from ela.infrastructure.machine import PROBE_MODULE

pytestmark = pytest.mark.skipif(
    platform.system() != "Darwin", reason="the helper reads macOS frameworks"
)


def run(families: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", PROBE_MODULE, families],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


@pytest.mark.parametrize("family", list(ProbeFamily))
def test_each_family_alone_answers_the_contract(family: ProbeFamily) -> None:
    """One family at a time, so a framework that fails to load is attributed to its family."""
    finished = run(family.value)

    assert finished.returncode == 0, finished.stderr
    readings = json.loads(finished.stdout)
    assert set(readings) == set(FAMILY_FIELDS[family])


def test_the_whole_reading_is_a_valid_raw_observation() -> None:
    """What the adapter does with the output, done here for real: if this validates, the two
    sides agree on the JSON object that is their entire contract."""
    finished = run(",".join(sorted(family.value for family in ProbeFamily)))

    assert finished.returncode == 0, finished.stderr
    seen = RawObservation.model_validate(json.loads(finished.stdout))

    assert set(seen.model_dump()) == set(RawObservation.model_fields)


def test_asking_for_nothing_answers_an_empty_object() -> None:
    finished = run("")

    assert (finished.returncode, finished.stdout) == (0, "{}")


def test_an_unreadable_fact_costs_only_its_own_key() -> None:
    """The child's own fail-safe: a Mac with no camera is an answer, not a non-zero exit.

    Cannot be produced by unplugging anything, so it is produced by asking for a family under a
    name that means nothing — every reading is skipped and the exit code is still 0.
    """
    finished = run("SENSORS,NONSENSE")

    assert finished.returncode == 0, finished.stderr
    assert set(json.loads(finished.stdout)) == set(FAMILY_FIELDS[ProbeFamily.SENSORS])
