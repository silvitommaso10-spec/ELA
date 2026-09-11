"""A capability whose verifier reads this machine stays on this machine (M12.2, D15; ADR 0038 §14).

Filter F7: a node that is not ``local`` is refused with ``UNVERIFIABLE`` for a step whose required
capability is verified by reading this machine's disk. The requirement is derived through the
verifier registry — a port, as the tool registry is (ADR 0017 §3) — and the node that would have
won is built to win, and shown winning when the verifier reads nothing: without that twin, "it
went to ``local``" could be the points and not the filter.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta
from pathlib import Path

import pytest

from ela.devices import LOCAL_DEVICE_ID, DeviceOrchestrator, DeviceRegistry, Refusal, score
from ela.domain import (
    CapabilityId,
    Device,
    DeviceStatus,
    NetworkKind,
    PerformanceClass,
    PowerSource,
    PrivacyLevel,
)
from ela.ports import VerifierRegistryPort
from ela.testing.fakes import (
    FakeAuditLog,
    FakeClock,
    FakeDeviceRegistry,
    FakeIdGenerator,
    FakeTool,
    FakeToolRegistry,
    FakeVerifier,
    FakeVerifierRegistry,
)
from ela.tools import WriteNoteVerifier
from tests.devices.nodes import node, step
from tests.domain.examples import TASK_ID

TTL = timedelta(seconds=60)
WRITE_NOTE = CapabilityId("workspace.write_note")
NOTES = "workspace_notes"
STEP = step(capabilities=(WRITE_NOTE,), goal="scrivere il verbale")
REASON = "UNVERIFIABLE (workspace.write_note: its verifier reads this machine)"
MAC = node(
    "mac",
    tools=(NOTES,),
    privacy=PrivacyLevel.TRUSTED,
    performance=PerformanceClass.HIGH,
    network=NetworkKind.LOCAL,
    power_source=PowerSource.AC,
    status=DeviceStatus.IDLE,
    workload=0.0,
)
"""A remote ``TRUSTED`` node built to win on points against a bare ``local``."""


def local(*, tools: tuple[str, ...] = (NOTES,)) -> Device:
    return node("local", tools=tools)


@pytest.fixture
def port() -> FakeDeviceRegistry:
    return FakeDeviceRegistry()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


async def orchestrator_over(
    port: FakeDeviceRegistry,
    clock: FakeClock,
    nodes: Iterable[Device],
    verifiers: VerifierRegistryPort,
) -> DeviceOrchestrator:
    for device in nodes:
        await port.register(device.model_copy(update={"last_seen_at": clock.now()}))
    audit = FakeAuditLog()
    registry = DeviceRegistry(port, clock, audit, FakeIdGenerator(), heartbeat_ttl=TTL)
    tools = FakeToolRegistry([FakeTool(WRITE_NOTE, clock, FakeIdGenerator(), name=NOTES)])
    return DeviceOrchestrator(registry, tools, audit, FakeIdGenerator(), clock, verifiers=verifiers)


def test_the_nodes_are_the_ones_the_tests_below_need() -> None:
    """The precondition, asserted once: ``local`` is the Core's node and ``mac`` is not."""
    assert local().id == LOCAL_DEVICE_ID
    assert MAC.id != LOCAL_DEVICE_ID


async def test_a_capability_whose_verifier_reads_the_machine_stays_here(
    port: FakeDeviceRegistry, clock: FakeClock, tmp_path: Path
) -> None:
    """Criterion 20: ``workspace.write_note``, verified by the real ``WriteNoteVerifier``, goes to
    ``local`` although the remote node would win it — and the reason names the capability."""
    verifiers = FakeVerifierRegistry([WriteNoteVerifier(tmp_path)])
    orchestrator = await orchestrator_over(port, clock, [local(), MAC], verifiers)
    requirements = orchestrator.requirements(STEP, max_privacy=PrivacyLevel.TRUSTED)

    placed = await orchestrator.place(STEP, task_id=TASK_ID, max_privacy=PrivacyLevel.TRUSTED)

    assert requirements.verified_here == (WRITE_NOTE,)
    assert score(MAC, requirements).points > score(local(), requirements).points
    assert placed.device is not None
    assert placed.device.id == LOCAL_DEVICE_ID
    assert "1 of 2 node(s) eligible" in placed.reason
    refused = {judged.device_id: judged.refusals for judged in placed.scores}
    assert refused[MAC.id] == (Refusal.UNVERIFIABLE,)


async def test_with_local_unable_the_step_waits_and_says_why(
    port: FakeDeviceRegistry, clock: FakeClock, tmp_path: Path
) -> None:
    """``local`` without the tool: nobody is eligible, and whoever waits reads both reasons."""
    verifiers = FakeVerifierRegistry([WriteNoteVerifier(tmp_path)])
    orchestrator = await orchestrator_over(port, clock, [local(tools=()), MAC], verifiers)

    placed = await orchestrator.place(STEP, task_id=TASK_ID, max_privacy=PrivacyLevel.TRUSTED)

    assert placed.waits
    assert REASON in placed.reason
    assert f"MISSING_TOOL ({NOTES})" in placed.reason


async def test_a_verifier_that_reads_nothing_lets_the_capability_travel(
    port: FakeDeviceRegistry, clock: FakeClock
) -> None:
    """The twin: the same nodes, the same step, a verifier that declares ``False`` — and the node
    built to win wins. What kept the step on ``local`` above was the filter, not the points."""
    verifiers = FakeVerifierRegistry([FakeVerifier(WRITE_NOTE, reads_the_machine=False)])
    orchestrator = await orchestrator_over(port, clock, [local(), MAC], verifiers)

    placed = await orchestrator.place(STEP, task_id=TASK_ID, max_privacy=PrivacyLevel.TRUSTED)

    assert orchestrator.requirements(STEP, max_privacy=PrivacyLevel.TRUSTED).verified_here == ()
    assert placed.device is not None
    assert placed.device.id == MAC.id


async def test_a_capability_with_no_verifier_stays_here_too(
    port: FakeDeviceRegistry, clock: FakeClock
) -> None:
    """A doubt keeps it here (§33): with no verifier, whether it may be verified elsewhere is
    unknown — and on ``local`` the executor refuses it for its own reason."""
    orchestrator = await orchestrator_over(port, clock, [local(), MAC], FakeVerifierRegistry())

    placed = await orchestrator.place(STEP, task_id=TASK_ID, max_privacy=PrivacyLevel.TRUSTED)

    assert placed.requirements.verified_here == (WRITE_NOTE,)
    assert placed.device is not None
    assert placed.device.id == LOCAL_DEVICE_ID


async def test_a_capability_no_tool_implements_is_unresolved_not_verified_here(
    port: FakeDeviceRegistry, clock: FakeClock
) -> None:
    """Nobody runs it anywhere, so where it would be verified is not the question: one reason
    per requirement, not two for the same capability."""
    orchestrator = await orchestrator_over(port, clock, [local()], FakeVerifierRegistry())
    unknown = step(capabilities=("core.rm_rf",), goal="cancellare tutto")

    requirements = orchestrator.requirements(unknown)

    assert requirements.unresolved == (CapabilityId("core.rm_rf"),)
    assert requirements.verified_here == ()
