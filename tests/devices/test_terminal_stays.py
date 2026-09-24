"""``terminal.run`` does not travel, and a test says so rather than a silence (M13.2 dec. 11).

Its verifier reads the identity of a program **on the Core's disk** — the ``/usr/bin/git`` of the
Core, not of a node — so on another machine it would compare the wrong file: the false positive of
ADR 0038 §14. It declares ``reads_the_machine``, and the orchestrator refuses a node that is not
``local`` with ``UNVERIFIABLE`` — shown here on a node built to win on points, with the tool the
step needs, so that «it went to ``local``» cannot be the points instead of the filter.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from ela.tools.programs import Programs

from ela.devices import LOCAL_DEVICE_ID, DeviceOrchestrator, DeviceRegistry, Refusal
from ela.domain import (
    DeviceStatus,
    NetworkKind,
    PerformanceClass,
    PowerSource,
    PrivacyLevel,
)
from ela.permissions import TERMINAL_RUN
from ela.testing.fakes import (
    FakeAuditLog,
    FakeCapabilityRegistry,
    FakeClock,
    FakeDeviceRegistry,
    FakeIdGenerator,
    FakeTool,
    FakeToolRegistry,
    FakeVerifierRegistry,
)
from ela.tools.verifiers import TerminalRunVerifier
from tests.devices.nodes import node, step
from tests.domain.examples import TASK_ID

TOOL = "terminal-run"
STEP = step(capabilities=(TERMINAL_RUN,), goal="far girare i test")
FAR = node(
    "mac-lontano",
    tools=(TOOL,),
    privacy=PrivacyLevel.TRUSTED,
    performance=PerformanceClass.HIGH,
    network=NetworkKind.LOCAL,
    power_source=PowerSource.AC,
    status=DeviceStatus.IDLE,
    workload=0.0,
)


async def test_a_command_is_placed_here_and_the_other_node_is_refused_as_unverifiable(
    tmp_path: Path,
) -> None:
    clock = FakeClock()
    port = FakeDeviceRegistry()
    for device in (node("local", tools=(TOOL,)), FAR):
        await port.register(device.model_copy(update={"last_seen_at": clock.now()}))
    audit = FakeAuditLog()
    orchestrator = DeviceOrchestrator(
        DeviceRegistry(port, clock, audit, FakeIdGenerator(), heartbeat_ttl=timedelta(seconds=60)),
        FakeToolRegistry([FakeTool(TERMINAL_RUN, clock, FakeIdGenerator(), name=TOOL)]),
        audit,
        FakeIdGenerator(),
        clock,
        verifiers=FakeVerifierRegistry([TerminalRunVerifier(Programs.fixed(()))]),
        capabilities=FakeCapabilityRegistry(),
    )

    placed = await orchestrator.place(STEP, task_id=TASK_ID, max_privacy=PrivacyLevel.TRUSTED)

    assert placed.device is not None and placed.device.id == LOCAL_DEVICE_ID
    refused = {judged.device_id: judged.refusals for judged in placed.scores}
    assert refused[FAR.id] == (Refusal.UNVERIFIABLE,)
