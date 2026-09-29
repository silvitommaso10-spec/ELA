"""``browser.read`` and ``browser.act`` do not travel, and a test says so (M13.4 form A, ADR 0052
§2).

Their verifier looks at a page that lives in a process of **this** machine — the kind of thing ADR
0038 §14 already counts as the machine —, and no node carries it: the third answer of ADR 0048 §7.
The orchestrator refuses a node that is not ``local`` with ``UNVERIFIABLE`` **even if it declared
the tool**, shown here on a node built to win on points, so that «it went to ``local``» cannot be
the points instead of the filter.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from ela.devices import LOCAL_DEVICE_ID, DeviceOrchestrator, DeviceRegistry, Refusal
from ela.domain import (
    CapabilityId,
    DeviceStatus,
    NetworkKind,
    PerformanceClass,
    PowerSource,
    PrivacyLevel,
)
from ela.permissions import BROWSER_ACT, BROWSER_READ
from ela.testing.fakes import (
    FakeAuditLog,
    FakeBrowser,
    FakeCapabilityRegistry,
    FakeClock,
    FakeDeviceRegistry,
    FakeIdGenerator,
    FakeTool,
    FakeToolRegistry,
    FakeVerifierRegistry,
)
from ela.tools import VERIFIED_ON_THE_NODE
from ela.tools.verifiers import BrowserActVerifier, BrowserReadVerifier
from tests.devices.nodes import node, step
from tests.domain.examples import TASK_ID


@pytest.mark.parametrize(
    ("capability", "tool"), [(BROWSER_READ, "browser-read"), (BROWSER_ACT, "browser-act")]
)
async def test_a_page_is_opened_here_and_the_other_node_is_refused_as_unverifiable(
    capability: CapabilityId, tool: str
) -> None:
    far = node(
        "mac-lontano",
        tools=(tool,),
        privacy=PrivacyLevel.TRUSTED,
        performance=PerformanceClass.HIGH,
        network=NetworkKind.LOCAL,
        power_source=PowerSource.AC,
        status=DeviceStatus.IDLE,
        workload=0.0,
    )
    clock = FakeClock()
    port = FakeDeviceRegistry()
    for device in (node("local", tools=(tool,)), far):
        await port.register(device.model_copy(update={"last_seen_at": clock.now()}))
    audit = FakeAuditLog()
    browser = FakeBrowser()
    orchestrator = DeviceOrchestrator(
        DeviceRegistry(port, clock, audit, FakeIdGenerator(), heartbeat_ttl=timedelta(seconds=60)),
        FakeToolRegistry([FakeTool(capability, clock, FakeIdGenerator(), name=tool)]),
        audit,
        FakeIdGenerator(),
        clock,
        verifiers=FakeVerifierRegistry(
            [BrowserReadVerifier(browser, 30.0), BrowserActVerifier(browser, 30.0)]
        ),
        capabilities=FakeCapabilityRegistry(),
        carried=VERIFIED_ON_THE_NODE,
    )

    placed = await orchestrator.place(
        step(capabilities=(capability,), goal="aprire una pagina"),
        task_id=TASK_ID,
        max_privacy=PrivacyLevel.TRUSTED,
    )

    assert placed.device is not None and placed.device.id == LOCAL_DEVICE_ID
    refused = {judged.device_id: judged.refusals for judged in placed.scores}
    assert refused[far.id] == (Refusal.UNVERIFIABLE,)


def test_no_node_carries_the_browser_s_verifiers() -> None:
    assert {BROWSER_READ, BROWSER_ACT}.isdisjoint(VERIFIED_ON_THE_NODE)
