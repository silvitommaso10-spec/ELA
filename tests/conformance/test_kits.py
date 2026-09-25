"""What a kit of the real node declares, read where the Core keeps it (M12.4 dec. G, criterion 2).

The stories of the contract do not look at what a node declares about itself beyond the tools a
step needs, so a kit could recite every one while building another system's composition. This
reads the row the Core wrote at enrollment: the operating system and the tools, **as literals**,
because a list derived from the composition would agree with whatever the composition built.
"""

from __future__ import annotations

import os
from uuid import UUID

import pytest

from ela.domain import DeviceId
from ela.testing.fakes import FakeClock
from ela.tools import VOICE_ONLINE_TOOL_NAME
from tests.conformance.driver import Conformance
from tests.conformance.fake_node import ONE_HOUR_BEHIND
from tests.conformance.real_node import MACOS, WINDOWS, RealNode


async def test_the_windows_kit_declares_windows_and_the_three_tools_of_a_pc(
    world: Conformance,
) -> None:
    """``WINDOWS``, and ``voice-speak`` without ``voice-speak-online``: a PC has a local voice and
    no player for the online one (dec. E, F). *Fails* if the kit built the Darwin composition — the
    system would be ``MACOS`` — or faked a player the system does not have."""
    node = await WINDOWS.node(world)

    row = await world.ela.devices.get(DeviceId(UUID(node.device_id)))

    assert row.os.value == "WINDOWS"
    assert list(row.available_tools) == ["core-echo", "model-complete", "voice-speak"]


async def test_the_darwin_kit_fakes_the_player_its_composition_would_choose(
    world: Conformance,
) -> None:
    """The other half of the derivation (review of 2026-09-17): the kit asks the composition whether
    Darwin has a player, and fakes it. Without the fake, the declaration would read this runner —
    ``afplay`` is on a Mac and not on the Ubuntu job — and on a Mac nothing would notice: the tools
    declared would be the same four, from the machine. So this asserts what the online voice **is**,
    on any runner. Built and not enrolled, so a Windows runner can build it too."""
    node = RealNode(
        world,
        system=MACOS.system,
        directory=world.ela.settings.captures.capture_dir.parent / "darwin-kit",
        clock=FakeClock(ONE_HOUR_BEHIND),
    )

    assert node.speech_online is not None
    assert node._built.voices[VOICE_ONLINE_TOOL_NAME] is node.speech_online  # noqa: SLF001
    await node.aclose()


async def test_the_windows_kit_enrols_with_the_mode_of_its_world(
    world: Conformance, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The kit enrols by a road of its own, and writes the identity with its world's mode as
    ``join_or_read`` does (dec. G). ``os.fchmod`` taken away, which is what Windows on 3.12 is.

    **The one monkeypatch of dec. H, and why here.** The absence of a function of the standard
    library is what Windows *is*, and it cannot be declared by parameter without handing the writer
    a fake ``os`` module — which would prove the fake. ``raising=False`` because on Windows there is
    nothing to take away.

    *Fails* on any runner if the kit wrote with ``BITS``: on this Mac that line would otherwise
    pass, and only a PC would see it."""
    monkeypatch.delattr(os, "fchmod", raising=False)

    node = await WINDOWS.node(world)

    assert node.device_id
