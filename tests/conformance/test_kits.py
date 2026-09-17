"""What a kit of the real node declares, read where the Core keeps it (M12.4 dec. G, criterion 2).

The stories of the contract do not look at what a node declares about itself beyond the tools a
step needs, so a kit could recite all thirteen while building another system's composition. This
reads the row the Core wrote at enrollment: the operating system and the tools, **as literals**,
because a list derived from the composition would agree with whatever the composition built.
"""

from __future__ import annotations

import os
from uuid import UUID

import pytest

from ela.domain import DeviceId
from tests.conformance.driver import Conformance
from tests.conformance.real_node import WINDOWS


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


async def test_the_windows_kit_enrols_with_the_mode_of_its_world(
    world: Conformance, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The kit enrols by a road of its own, and writes the identity with its world's mode as
    ``join_or_read`` does (dec. G). ``os.fchmod`` taken away, which is what Windows on 3.12 is — the
    one monkeypatch of dec. H, and ``tests/node/test_state.py`` says why. *Fails* on any runner if
    the kit wrote with ``BITS``: on this Mac that line would otherwise pass, and only a PC would see
    it."""
    monkeypatch.delattr(os, "fchmod", raising=False)

    node = await WINDOWS.node(world)

    assert node.device_id
