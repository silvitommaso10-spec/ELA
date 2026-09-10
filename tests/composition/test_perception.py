"""Which adapters ELA is wired to, and the fact that nothing consumes the probe yet (ADR 0028 §1).

The choice of adapter lives in the composition root and nowhere else (architecture rule 27): it is
not a capability of the local node and not a branch inside the adapter, because "ELA on Linux
perceives nothing" should be an object with a name and a test rather than a gap.

**Both directions are asserted by naming the system, never by being on one** (ADR 0031). A test
that reads ``platform.system()`` to decide what to expect verifies half of the wiring on each
machine and fails on neither: the Mac never checks the Linux arm, the runner never checks the
Darwin arm, and the branch nobody proves is the one that breaks. Here each direction is a case
with a name, and every runner runs both.
"""

from __future__ import annotations

import dataclasses
import platform
from pathlib import Path

import pytest

from ela.composition import Ela, Settings, build
from ela.infrastructure.machine import (
    DarwinProbe,
    ScreenCaptureCommand,
    UnsupportedProbe,
    UnsupportedScreenCapture,
    UnsupportedTextRecognition,
    VisionTextRecognition,
)
from ela.perception import PerceptionCore
from ela.permissions import PERCEPTION_CAPTURE_SCREEN
from ela.ports import PerceptionProbe
from ela.tools import PERCEPTION_READ_SCREEN_TEXT
from tests.composition.support import create_schema, declare


async def test_ela_is_built_with_a_perception_core(ela: Ela) -> None:
    assert isinstance(ela.perception, PerceptionCore)


async def test_the_probe_satisfies_the_port_whatever_this_machine_is(ela: Ela) -> None:
    """What holds on every runner, stated without asking which one this is."""
    assert isinstance(ela.perception._probe, PerceptionProbe)  # noqa: SLF001


@pytest.mark.parametrize(
    ("system", "expected"),
    [
        ("Darwin", (DarwinProbe, ScreenCaptureCommand, VisionTextRecognition)),
        ("Linux", (UnsupportedProbe, UnsupportedScreenCapture, UnsupportedTextRecognition)),
    ],
)
async def test_the_adapters_are_the_ones_the_named_system_can_answer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    system: str,
    expected: tuple[type, type, type],
) -> None:
    """Both arms of the one ``if`` in the composition root, on any runner (ADR 0031).

    Nothing here touches the hardware: the three Darwin adapters only store a timeout and a spawn
    at construction, and no child starts until somebody calls them — which is what makes the
    Darwin case runnable on a machine that is not a Mac, and the whole point of asserting it by
    name. Before this test the Darwin arm was proved only by being on a Mac, and ``ocr_timeout``
    was covered by that arm alone: on a Linux runner the gate failed on a line whose own package
    had never called it.
    """
    monkeypatch.setattr(platform, "system", lambda: system)
    declare(monkeypatch, tmp_path)
    settings = Settings.load()
    await create_schema(settings.persistence.db_url)
    built = await build(settings)
    probe_type, screen_type, recognition_type = expected
    try:
        capture_tool = built.tools.get(PERCEPTION_CAPTURE_SCREEN)
        reading_tool = built.tools.get(PERCEPTION_READ_SCREEN_TEXT)

        assert isinstance(built.perception._probe, probe_type)  # noqa: SLF001
        assert isinstance(capture_tool._capture, screen_type)  # noqa: SLF001
        assert isinstance(reading_tool._recognition, recognition_type)  # noqa: SLF001
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
