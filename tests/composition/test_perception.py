"""Which probe ELA is wired to, and the fact that nothing consumes it yet (ADR 0028 §1).

The choice of adapter lives in the composition root and nowhere else (architecture rule 27): it is
not a capability of the local node and not a branch inside the adapter, because "ELA on Linux
perceives nothing" should be an object with a name and a test rather than a gap.
"""

from __future__ import annotations

import dataclasses
import platform
from pathlib import Path

import pytest

from ela.composition import Ela, Settings, build
from ela.infrastructure.perception import DarwinProbe, UnsupportedProbe
from ela.perception import PerceptionCore
from ela.ports import PerceptionProbe
from tests.composition.support import create_schema, declare


async def test_ela_is_built_with_a_perception_core(ela: Ela) -> None:
    assert isinstance(ela.perception, PerceptionCore)


async def test_the_probe_is_the_one_this_operating_system_can_answer(ela: Ela) -> None:
    probe = ela.perception._probe  # noqa: SLF001 — the wiring is what is under test
    expected = DarwinProbe if platform.system() == "Darwin" else UnsupportedProbe

    assert isinstance(probe, expected)
    assert isinstance(probe, PerceptionProbe)


async def test_a_machine_that_is_not_a_mac_gets_the_probe_that_reads_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Asserted by naming the system rather than by running on one: the branch exists for the
    runners, and a runner that is a Mac would otherwise never exercise it."""
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    declare(monkeypatch, tmp_path)
    settings = Settings.load()
    await create_schema(settings.persistence.db_url)
    built = await build(settings)
    try:
        assert isinstance(built.perception._probe, UnsupportedProbe)  # noqa: SLF001
    finally:
        await built.aclose()


async def test_nothing_else_in_ela_holds_the_perception_core(ela: Ela) -> None:
    """v0.1 has no consumer: no task reads perception and no decision depends on it.

    It is the shape of the milestone rather than an omission, and it is also why the continuous
    loop is off by default — an observer nobody reads should not be watching (ADR 0028 §7).
    """
    holders = [
        field.name
        for field in dataclasses.fields(ela)
        if isinstance(getattr(ela, field.name), PerceptionCore)
    ]

    assert holders == ["perception"]
