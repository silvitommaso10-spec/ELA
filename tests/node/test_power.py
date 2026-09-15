"""What a node says it runs on, with every sign of life (M12.3c).

``power_source`` is weighed by the orchestrator — ``AC`` is worth 10 points (``POWER_POINTS``),
and a node on the other side of a network needs them to beat ``local`` — and until M12.3c no node
sent it. The first version of the cycle sent ``"AC"`` without looking; the correction sent
nothing; and the value the Core weighed was ``UNKNOWN`` from the enrollment on. A field that is
weighed and that nobody can produce is a stub, not a debt (ADR 0026 §7).

What is asserted is the **body that goes over the wire**, not a method of the node: what the Core
weighs is what arrived.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest

from ela.domain import PowerSource
from ela.testing.fakes import FakePower
from tests.node.support import node_of, replies, world


def beats(bodies: list[dict[str, Any]]) -> Callable[[httpx.Request], httpx.Response]:
    """A Core that answers a heartbeat and keeps what it was sent."""

    def beat(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={})

    return beat


async def test_a_heartbeat_says_what_the_machine_runs_on(tmp_path: Path) -> None:
    """The defect, seen red before the repair: the body carried ``status`` and nothing else."""
    bodies: list[dict[str, Any]] = []
    node, _ = node_of(world(tmp_path), replies(beats(bodies)))

    await node.report()

    (sent,) = bodies
    assert sent.get("power_source") in {member.value for member in PowerSource}


@pytest.mark.parametrize("source", list(PowerSource))
async def test_it_sends_what_its_machine_answered(tmp_path: Path, source: PowerSource) -> None:
    """``UNKNOWN`` too, and deliberately: a reading that failed is an observation of not knowing,
    and leaving the field out would leave standing an ``AC`` nobody has seen since — the registry
    writes only what a heartbeat gives."""
    bodies: list[dict[str, Any]] = []
    built = replace(world(tmp_path), power=FakePower(source))
    node, _ = node_of(built, replies(beats(bodies)))

    await node.report()

    assert bodies == [{"status": "IDLE", "power_source": source.value}]


async def test_it_asks_the_machine_again_on_every_beat(tmp_path: Path) -> None:
    """A laptop is unplugged in the middle of a session: a reading kept from the first beat would be
    a fact nobody observed by the second."""
    bodies: list[dict[str, Any]] = []
    power = FakePower(PowerSource.AC)
    node, _ = node_of(replace(world(tmp_path), power=power), replies(beats(bodies), beats(bodies)))

    await node.report()
    power.source = PowerSource.BATTERY
    await node.report("BUSY")

    assert [body["power_source"] for body in bodies] == ["AC", "BATTERY"]
    assert power.asked == 2
