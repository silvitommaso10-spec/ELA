"""``PlacementDecision``, ``ensure_placed`` and ``confirm``: the placement as data (ADR 0026).

Until M9.1 the executor took a bare ``DeviceId`` and had no way to tell a node the orchestrator
had chosen from a node the caller had invented — the one link in the permission chain with a
single defence, and the link that decides *which node may see this content* (§57).

Three groups of tests, one per piece:

* :func:`ensure_placed` refuses a decision that is not about this call, names nobody, or
  disagrees with itself — the mirror of ``ela.tools.base.check_decision``;
* :meth:`DeviceOrchestrator.place` fills the identity a bare id could not carry;
* :meth:`DeviceOrchestrator.confirm` judges the node of a resumed step without choosing one, and
  without writing a second ``DEVICE_SELECTED``.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta

import pytest

from ela.devices import (
    DeviceOrchestrator,
    DeviceRegistry,
    NotPlacedError,
    PlacementDecision,
    Refusal,
    ensure_placed,
    score,
)
from ela.domain import AuditEventType, CapabilityId, Device, DeviceAvailability, PrivacyLevel
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
from tests.devices.nodes import device_id, needs, node, step
from tests.domain.examples import MUCH_LATER, OTHER_STEP_ID, TASK_ID
from tests.permissions.support import OTHER_TASK_ID

TTL = timedelta(seconds=60)
WRITE_NOTE = CapabilityId("workspace.write_note")
NOTES = "workspace_notes"
STEP = step()


def decision(device: Device | None, **changes: object) -> PlacementDecision:
    """A placement of :data:`STEP` for :data:`TASK_ID` on ``device``, then ``changes`` applied."""
    requirements = needs()
    base = PlacementDecision(
        created_at=MUCH_LATER,
        task_id=TASK_ID,
        step_id=STEP.id,
        requirements=requirements,
        device=device,
        scores=() if device is None else (score(device, requirements),),
        reason="for the test",
    )
    return base._replace(**changes)  # type: ignore[arg-type]


# ----------------------------------------------------------------------------------------
# ensure_placed: the three refusals (ADR 0026 §3)
# ----------------------------------------------------------------------------------------


def test_a_placement_of_this_step_on_an_eligible_node_gives_the_node() -> None:
    eligible = node("local")

    assert ensure_placed(decision(eligible), TASK_ID, STEP.id) is eligible


def test_a_placement_of_another_task_is_refused() -> None:
    with pytest.raises(NotPlacedError, match="the placement is for step"):
        ensure_placed(decision(node("local"), task_id=OTHER_TASK_ID), TASK_ID, STEP.id)


def test_a_placement_of_another_step_is_refused() -> None:
    """A placement is not transferable: one step's node is not another step's permission."""
    with pytest.raises(NotPlacedError, match="the placement is for step"):
        ensure_placed(decision(node("local"), step_id=OTHER_STEP_ID), TASK_ID, STEP.id)


def test_a_placement_that_names_nobody_is_refused_with_its_reason() -> None:
    with pytest.raises(NotPlacedError, match="no node was chosen: for the test"):
        ensure_placed(decision(None), TASK_ID, STEP.id)


@pytest.mark.parametrize(
    ("bad", "refusal"),
    [
        (node("stale", availability=DeviceAvailability.OFFLINE), Refusal.UNAVAILABLE),
        (node("cloud", privacy=PrivacyLevel.CLOUD_ALLOWED), Refusal.PRIVACY),
    ],
)
def test_a_placement_that_disagrees_with_itself_is_refused(bad: Device, refusal: Refusal) -> None:
    """The check that matters: the same pure ``refusals`` the orchestrator ran, run again.

    A forged decision has to be consistent to be useful, and a consistent one is a decision the
    orchestrator could have made. No second read of the registry, no second policy.
    """
    with pytest.raises(NotPlacedError, match=f"refused by its own placement: {refusal.value}"):
        ensure_placed(decision(bad), TASK_ID, STEP.id)


def test_the_error_names_the_task_and_the_step_it_refused() -> None:
    with pytest.raises(NotPlacedError) as raised:
        ensure_placed(decision(None), TASK_ID, STEP.id)

    assert raised.value.task_id == TASK_ID
    assert raised.value.step_id == STEP.id
    assert raised.value.reason.startswith("no node was chosen")
    assert str(TASK_ID) in str(raised.value)


# ----------------------------------------------------------------------------------------
# place and confirm
# ----------------------------------------------------------------------------------------


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(MUCH_LATER)


@pytest.fixture
def port() -> FakeDeviceRegistry:
    return FakeDeviceRegistry()


@pytest.fixture
def audit() -> FakeAuditLog:
    return FakeAuditLog()


@pytest.fixture
def orchestrator(
    port: FakeDeviceRegistry, audit: FakeAuditLog, clock: FakeClock
) -> DeviceOrchestrator:
    tools = FakeToolRegistry([FakeTool(WRITE_NOTE, clock, FakeIdGenerator(), name=NOTES)])
    registry = DeviceRegistry(port, clock, audit, FakeIdGenerator(), heartbeat_ttl=TTL)
    verifiers = FakeVerifierRegistry([FakeVerifier(WRITE_NOTE)])
    return DeviceOrchestrator(registry, tools, audit, FakeIdGenerator(), clock, verifiers=verifiers)


async def register(port: FakeDeviceRegistry, nodes: Iterable[Device], clock: FakeClock) -> None:
    for device in nodes:
        await port.register(device.model_copy(update={"last_seen_at": clock.now()}))


async def test_place_fills_the_identity_a_bare_id_could_not_carry(
    orchestrator: DeviceOrchestrator, port: FakeDeviceRegistry, clock: FakeClock
) -> None:
    await register(port, [node("local")], clock)

    placed = await orchestrator.place(STEP, task_id=TASK_ID)

    assert placed.task_id == TASK_ID
    assert placed.step_id == STEP.id
    assert placed.created_at == clock.now()
    assert placed.requirements == orchestrator.requirements(STEP)
    assert ensure_placed(placed, TASK_ID, STEP.id) is not None


async def test_confirm_keeps_a_node_that_is_still_eligible(
    orchestrator: DeviceOrchestrator,
    port: FakeDeviceRegistry,
    clock: FakeClock,
    audit: FakeAuditLog,
) -> None:
    await register(port, [node("local")], clock)

    confirmed = await orchestrator.confirm(device_id("local"), STEP, task_id=TASK_ID)

    assert confirmed.device is not None
    assert confirmed.device.id == device_id("local")
    assert "confirmed without a new choice" in confirmed.reason
    assert ensure_placed(confirmed, TASK_ID, STEP.id) is not None
    assert await audit.read() == ()  # confirming is not choosing (ADR 0026 §4)


async def test_confirm_refuses_a_node_that_stopped_answering(
    orchestrator: DeviceOrchestrator, port: FakeDeviceRegistry, clock: FakeClock
) -> None:
    await register(port, [node("local")], clock)
    clock.advance(TTL * 2)  # the node says nothing while the user thinks

    confirmed = await orchestrator.confirm(device_id("local"), STEP, task_id=TASK_ID)

    assert confirmed.waits
    assert Refusal.UNAVAILABLE.value in confirmed.reason
    assert confirmed.scores  # why it lost is recorded, as a placement records it
    with pytest.raises(NotPlacedError):
        ensure_placed(confirmed, TASK_ID, STEP.id)


async def test_confirm_names_the_tool_the_node_no_longer_has(
    orchestrator: DeviceOrchestrator, port: FakeDeviceRegistry, clock: FakeClock
) -> None:
    """A step resumed after its node lost a capability: the reason says which one (dec. F).

    Not a second path for the same sentence — the names are computed where the reason is born,
    and ``confirm`` is a second place a reason is born. The node is still there and still
    answering; what it cannot do any more is the thing the step needs.
    """
    await register(port, [node("local")], clock)

    confirmed = await orchestrator.confirm(
        device_id("local"), step(capabilities=(str(WRITE_NOTE),)), task_id=TASK_ID
    )

    assert confirmed.waits
    assert f"{Refusal.MISSING_TOOL.value} ({NOTES})" in confirmed.reason


async def test_confirm_refuses_a_node_that_is_no_longer_registered(
    orchestrator: DeviceOrchestrator,
) -> None:
    """A node can be gone, not only quiet — and the answer is the same: nobody is named."""
    confirmed = await orchestrator.confirm(device_id("vanished"), STEP, task_id=TASK_ID)

    assert confirmed.waits
    assert confirmed.scores == ()
    assert "no longer registered" in confirmed.reason
    assert confirmed.task_id == TASK_ID and confirmed.step_id == STEP.id


async def test_confirm_never_names_a_node_other_than_the_one_it_was_asked_about(
    orchestrator: DeviceOrchestrator, port: FakeDeviceRegistry, clock: FakeClock
) -> None:
    """The reason ``confirm`` exists rather than a second ``place`` (ADR 0019 §4).

    The node it is asked about is refused on privacy — a filter the heartbeat cannot rescue —
    while a perfectly eligible ``other`` sits in the registry. ``place`` would pick ``other``;
    ``confirm`` must not, because a tool may already have run on the first.
    """
    await register(port, [node("gone", privacy=PrivacyLevel.CLOUD_ALLOWED), node("other")], clock)

    confirmed = await orchestrator.confirm(device_id("gone"), STEP, task_id=TASK_ID)

    assert confirmed.waits  # "other" is eligible and is *not* offered as a replacement
    assert Refusal.PRIVACY.value in confirmed.reason
    chosen = await orchestrator.place(STEP, task_id=TASK_ID)
    assert chosen.device is not None and chosen.device.id == device_id("other")


async def test_a_placement_and_a_confirmation_of_the_same_node_agree(
    orchestrator: DeviceOrchestrator,
    port: FakeDeviceRegistry,
    clock: FakeClock,
    audit: FakeAuditLog,
) -> None:
    """One judgement, two callers: the requirements and the verdict are the same either way."""
    await register(port, [node("local")], clock)

    placed = await orchestrator.place(STEP, task_id=TASK_ID)
    assert placed.device is not None
    confirmed = await orchestrator.confirm(placed.device.id, STEP, task_id=TASK_ID)

    assert confirmed.device == placed.device
    assert confirmed.requirements == placed.requirements
    types = [event.event_type for event in await audit.read()]
    assert types == [AuditEventType.DEVICE_SELECTED]  # one event, from ``place`` alone


async def test_confirm_says_a_revoked_node_is_revoked_and_not_gone(
    orchestrator: DeviceOrchestrator, port: FakeDeviceRegistry, clock: FakeClock
) -> None:
    """Criterion 9 (D13): the row of a revoked node stays, so ``confirm`` finds it and judges it —
    "no longer eligible", naming ``REVOKED``, and never "no longer registered", which is false."""
    await register(port, [node("local")], clock)
    await port.revoke(device_id("local"), at=clock.now())

    confirmed = await orchestrator.confirm(device_id("local"), STEP, task_id=TASK_ID)

    assert confirmed.waits
    assert "no longer eligible" in confirmed.reason
    assert Refusal.REVOKED.value in confirmed.reason
    assert "no longer registered" not in confirmed.reason
