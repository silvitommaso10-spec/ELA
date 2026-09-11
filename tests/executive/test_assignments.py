"""The service of the assignments (M12.2, ADR 0038 §6): every write of the work handed to a node.

On the fakes. The store's statements are under contract in
``tests/contracts/test_assignment_store.py``; what is here is what the service adds: the checks
before anything is written, the heartbeat in front of every expiry it sets, what a row is *now*,
and the answer of M12.1, D14 when time decides.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

import pytest

from ela.devices import LOCAL_DEVICE_ID, DeviceRegistry, PlacementDecision
from ela.devices.errors import NotPlacedError
from ela.devices.orchestrator import Requirements
from ela.domain import (
    Assignment,
    AssignmentState,
    AuditEventType,
    CapabilityId,
    DecisionId,
    Device,
    DeviceAvailability,
    DeviceId,
    DeviceStatus,
    ExecutionStatus,
    NetworkKind,
    OperatingSystem,
    PermissionDecision,
    PermissionOutcome,
    PrivacyLevel,
    RiskLevel,
    StepId,
    StepState,
    TaskEventType,
    TaskId,
)
from ela.executive import (
    MAX_ASSIGNMENT_CAP,
    WORK_ACTOR,
    AssignmentAtCapError,
    AssignmentRefusedError,
    Assignments,
    Lapse,
    Standing,
    WorkRejection,
)
from ela.ports import AssignmentExpiredError, AssignmentHeldElsewhereError, AssignmentStateError
from ela.testing.fakes import (
    DEFAULT_START,
    FakeAssignmentStore,
    FakeDeviceRegistry,
    FakeExecutionResultStore,
)
from tests.tasks.graphs import chain, sid
from tests.tasks.support import Harness, executing_with, make_harness, step_result_for

TTL = timedelta(seconds=120)
CAP = timedelta(minutes=10)
INSTANT = timedelta(microseconds=1)
DIGEST = "ab" * 32
NODE = Device(
    id=DeviceId(UUID("00000000-0000-4000-8000-000000000501")),
    created_at=DEFAULT_START,
    name="pc-windows",
    os=OperatingSystem.WINDOWS,
    availability=DeviceAvailability.ONLINE,
    status=DeviceStatus.IDLE,
    available_tools=("core-echo",),
    network=NetworkKind.REMOTE,
    privacy=PrivacyLevel.TRUSTED,
)
OTHER_NODE = NODE.model_copy(
    update={"id": DeviceId(UUID("00000000-0000-4000-8000-000000000502")), "name": "phone"}
)
HERE = NODE.model_copy(
    update={"id": LOCAL_DEVICE_ID, "name": "local", "privacy": PrivacyLevel.LOCAL_ONLY}
)


@dataclass
class World:
    h: Harness
    store: FakeAssignmentStore
    results: FakeExecutionResultStore
    service: Assignments
    task_id: TaskId
    step_id: StepId

    async def written(self) -> tuple[int, int, int]:
        """Trail events, audit events, assignments of the step: what "nothing written" counts."""
        return (
            len(await self.h.repository.events(self.task_id)),
            len(await self.h.audit.read()),
            len(await self.store.for_step(self.task_id, self.step_id)),
        )

    async def last_trail_event(self) -> TaskEventType:
        return (await self.h.repository.events(self.task_id))[-1].event_type


def build(
    h: Harness,
    store: FakeAssignmentStore,
    results: FakeExecutionResultStore,
    *,
    ttl: timedelta = TTL,
    cap: timedelta = CAP,
) -> Assignments:
    devices = DeviceRegistry(
        FakeDeviceRegistry([NODE, OTHER_NODE]),
        h.clock,
        h.audit,
        h.ids,
        heartbeat_ttl=timedelta(seconds=60),
    )
    return Assignments(
        store,
        engine=h.engine,
        repository=h.repository,
        results=results,
        devices=devices,
        audit=h.audit,
        clock=h.clock,
        ids=h.ids,
        ttl=ttl,
        cap=cap,
    )


@pytest.fixture
async def w() -> World:
    """An EXECUTING task whose one step runs on :data:`NODE`, and nothing assigned yet."""
    h = make_harness()
    task = await executing_with(h, chain(1))
    await h.engine.start_step(task.id, sid(0), device_id=NODE.id)
    store, results = FakeAssignmentStore(), FakeExecutionResultStore()
    return World(h, store, results, build(h, store, results), task.id, sid(0))


def decision(w: World, **update: object) -> PermissionDecision:
    """ALLOWED, about the step, alive for five minutes."""
    now = w.h.clock.now()
    return PermissionDecision(
        id=DecisionId(UUID(int=1)),
        created_at=now,
        capability_id=CapabilityId("core.echo"),
        outcome=PermissionOutcome.ALLOWED,
        risk=RiskLevel.LOW,
        reason="allowed",
        task_id=w.task_id,
        step_id=w.step_id,
        expires_at=now + timedelta(minutes=5),
    ).model_copy(update=update)


def placement(
    w: World, *, device: Device | None = NODE, step_id: StepId | None = None
) -> PlacementDecision:
    """The orchestrator's choice of ``device`` for the step, judged under ``TRUSTED``."""
    return PlacementDecision(
        created_at=w.h.clock.now(),
        task_id=w.task_id,
        step_id=w.step_id if step_id is None else step_id,
        requirements=Requirements(
            tools=frozenset({"core-echo"}),
            traits=(),
            risk=RiskLevel.LOW,
            max_privacy=PrivacyLevel.TRUSTED,
        ),
        device=device,
        scores=(),
        reason="chosen",
    )


async def offered(w: World) -> Assignment:
    return await w.service.assign(decision(w), placement(w), authorization_id=None)


# ----------------------------------------------------------------------------------------
# Handing the work out
# ----------------------------------------------------------------------------------------


async def test_an_offer_is_born_after_a_heartbeat_of_its_task(w: World) -> None:
    grant = UUID("00000000-0000-4000-8000-000000000601")
    assignment = await w.service.assign(decision(w), placement(w), authorization_id=grant)

    assert assignment.state is AssignmentState.OFFERED
    assert assignment.device_id == NODE.id
    assert assignment.authorization_id == grant
    assert assignment.expires_at == w.h.clock.now() + TTL
    assert await w.store.get(assignment.id) == assignment
    assert await w.last_trail_event() is TaskEventType.HEARTBEAT


async def test_the_heartbeat_comes_before_the_row(w: World) -> None:
    """ADR 0038 §9: with the row first, a death between the two would leave work out with no sign
    of life in front of it. Here the row cannot be written, and the heartbeat already is."""

    class Refusing(FakeAssignmentStore):
        async def add(self, assignment: Assignment) -> None:
            raise RuntimeError("the row could not be written")

    service = build(w.h, Refusing(), w.results)
    with pytest.raises(RuntimeError):
        await service.assign(decision(w), placement(w), authorization_id=None)
    assert await w.last_trail_event() is TaskEventType.HEARTBEAT


async def test_an_offer_never_outlives_its_decision(w: World) -> None:
    short = decision(w, expires_at=w.h.clock.now() + timedelta(seconds=30))
    assignment = await w.service.assign(short, placement(w), authorization_id=None)

    assert assignment.expires_at == short.expires_at


@pytest.mark.parametrize(
    "update",
    [
        {"outcome": PermissionOutcome.DENIED},
        {"outcome": PermissionOutcome.REQUIRES_APPROVAL},
        {"expires_at": DEFAULT_START},
        {"expires_at": None},
        {"step_id": None},
    ],
    ids=["denied", "requires-approval", "expired", "never-expires", "about-no-step"],
)
async def test_a_decision_that_does_not_allow_the_call_writes_nothing(
    w: World, update: dict[str, object]
) -> None:
    """Criterion 25: refused before anything is written — no row and no heartbeat, counted."""
    before = await w.written()
    with pytest.raises(AssignmentRefusedError):
        await w.service.assign(decision(w, **update), placement(w), authorization_id=None)
    assert await w.written() == before


async def test_a_decision_is_expired_at_the_instant_of_its_expiry(w: World) -> None:
    """Closed bound: at ``expires_at`` the decision cannot be handed out."""
    now = w.h.clock.now()
    with pytest.raises(AssignmentRefusedError, match="expired"):
        await w.service.assign(decision(w, expires_at=now), placement(w), authorization_id=None)


@pytest.mark.parametrize(
    ("device", "step"),
    [
        (None, None),
        (NODE, StepId(UUID(int=99))),
        (NODE.model_copy(update={"privacy": "CLOUD_ALLOWED"}), None),
    ],
    ids=["waits", "another-step", "refused-by-its-own-placement"],
)
async def test_a_placement_that_allows_no_node_writes_nothing(
    w: World, device: Device | None, step: StepId | None
) -> None:
    """``ensure_placed``, the same pure function the executor calls (ADR 0026 §3)."""
    before = await w.written()
    with pytest.raises(NotPlacedError):
        await w.service.assign(
            decision(w), placement(w, device=device, step_id=step), authorization_id=None
        )
    assert await w.written() == before


async def test_local_is_executed_never_assigned(w: World) -> None:
    """ADR 0038 §3: ``local`` runs in this process, and handing it an offer is a caller's bug."""
    before = await w.written()
    with pytest.raises(AssignmentRefusedError, match="local"):
        await w.service.assign(decision(w), placement(w, device=HERE), authorization_id=None)
    assert await w.written() == before


# ----------------------------------------------------------------------------------------
# What a row is now
# ----------------------------------------------------------------------------------------


async def test_a_step_with_no_assignment_stands_as_ever(w: World) -> None:
    assert await w.service.standing(w.task_id, w.step_id) == (Standing.NONE, None)


async def test_work_out_is_live_until_the_instant_of_its_expiry(w: World) -> None:
    """Criterion 13, on the service: an instant before, live; at ``expires_at``, lapsed — and the
    row is still ``OFFERED`` in the store, because nothing was written by reading it."""
    assignment = await offered(w)
    w.h.clock.advance(TTL - INSTANT)
    assert (await w.service.standing(w.task_id, w.step_id)).standing is Standing.LIVE

    w.h.clock.advance(INSTANT)
    assert await w.service.standing(w.task_id, w.step_id) == (Standing.LAPSED, assignment)
    assert (await w.store.get(assignment.id)).state is AssignmentState.OFFERED


async def test_delivered_work_stands_delivered(w: World) -> None:
    assignment = await offered(w)
    await w.service.claim(assignment.id, NODE.id)
    await w.service.deliver(assignment.id, NODE.id, digest=DIGEST, now=w.h.clock.now())

    assert (await w.service.standing(w.task_id, w.step_id)).standing is Standing.DELIVERED


async def test_an_expiry_marked_and_not_yet_acted_on_stands_lapsed(w: World) -> None:
    """Window A11: ``EXPIRED`` written, the release not — the next run finds it and acts."""
    assignment = await offered(w)
    w.h.clock.advance(TTL)
    await w.store.expire(assignment.id, now=w.h.clock.now())

    assert (await w.service.standing(w.task_id, w.step_id)).standing is Standing.LAPSED


async def test_a_released_assignment_is_no_longer_the_steps(w: World) -> None:
    """Criterion 27's service half: a ``STEP_RELEASED`` carries its id, so the step goes the way it
    always went — even when it is RUNNING again, elsewhere, after the release."""
    assignment = await offered(w)
    w.h.clock.advance(TTL)
    await w.service.lapse(assignment)
    await w.h.engine.start_step(w.task_id, w.step_id)

    assert await w.service.standing(w.task_id, w.step_id) == (Standing.NONE, None)


async def test_the_reason_names_the_node_the_assignment_and_when_it_is_due(w: World) -> None:
    assignment = await offered(w)
    reason = await w.service.describe(assignment)

    assert "pc-windows" in reason and str(NODE.id) in reason
    assert str(assignment.id) in reason and assignment.expires_at.isoformat() in reason


async def test_a_node_is_offered_its_oldest_live_work(w: World) -> None:
    assert await w.service.next_for(NODE.id) is None
    assignment = await offered(w)

    assert await w.service.next_for(NODE.id) == assignment
    assert await w.service.next_for(OTHER_NODE.id) is None
    w.h.clock.advance(TTL)
    assert await w.service.next_for(NODE.id) is None


# ----------------------------------------------------------------------------------------
# The node's moves
# ----------------------------------------------------------------------------------------


async def test_a_claim_writes_a_heartbeat_and_gives_the_work_a_ttl(w: World) -> None:
    assignment = await offered(w)
    w.h.clock.advance(timedelta(seconds=5))
    taken = await w.service.claim(assignment.id, NODE.id)

    assert taken.state is AssignmentState.CLAIMED
    assert taken.expires_at == w.h.clock.now() + TTL
    assert await w.last_trail_event() is TaskEventType.HEARTBEAT


async def test_a_claim_that_cannot_happen_writes_no_heartbeat(w: World) -> None:
    """Another node's offer, work already taken, an offer past its expiry: each refused by the
    port's own error, with nothing written."""
    assignment = await offered(w)
    before = await w.written()
    with pytest.raises(AssignmentHeldElsewhereError):
        await w.service.claim(assignment.id, OTHER_NODE.id)
    assert await w.written() == before

    await w.service.claim(assignment.id, NODE.id)
    before = await w.written()
    with pytest.raises(AssignmentStateError):
        await w.service.claim(assignment.id, NODE.id)
    assert await w.written() == before


async def test_a_claim_of_an_expired_offer_writes_no_heartbeat(w: World) -> None:
    assignment = await offered(w)
    w.h.clock.advance(TTL)
    before = await w.written()
    with pytest.raises(AssignmentExpiredError):
        await w.service.claim(assignment.id, NODE.id)
    assert await w.written() == before


async def test_a_renewal_moves_the_expiry_up_to_the_cap(w: World) -> None:
    """``min(now + ttl, claimed_at + cap)``, with a heartbeat each time; at the cap, a refusal
    that writes nothing and says when the work expires (ADR 0038 §13)."""
    assignment = await offered(w)
    taken = await w.service.claim(assignment.id, NODE.id)
    assert taken.claimed_at is not None

    w.h.clock.advance(timedelta(seconds=60))
    renewed = await w.service.renew(assignment.id, NODE.id)
    assert renewed.expires_at == w.h.clock.now() + TTL
    assert await w.last_trail_event() is TaskEventType.HEARTBEAT

    while renewed.expires_at < taken.claimed_at + CAP:
        w.h.clock.advance(timedelta(seconds=100))
        renewed = await w.service.renew(assignment.id, NODE.id)
    assert renewed.expires_at == taken.claimed_at + CAP

    before = await w.written()
    with pytest.raises(AssignmentAtCapError) as caught:
        await w.service.renew(assignment.id, NODE.id)
    assert caught.value.expires_at == taken.claimed_at + CAP
    assert await w.written() == before


async def test_an_offer_is_not_renewed(w: World) -> None:
    assignment = await offered(w)
    with pytest.raises(AssignmentStateError):
        await w.service.renew(assignment.id, NODE.id)


# ----------------------------------------------------------------------------------------
# When time decides
# ----------------------------------------------------------------------------------------


async def test_an_expiry_with_nothing_in_the_store_releases_the_step(w: World) -> None:
    """M12.1, D14: without a STARTED record nothing ran — back in play, the assignment as key."""
    assignment = await offered(w)
    w.h.clock.advance(TTL)

    assert await w.service.lapse(assignment) is Lapse.RELEASED
    assert (await w.store.get(assignment.id)).state is AssignmentState.EXPIRED
    graph = await w.h.engine.graph(w.task_id)
    assert graph.states[w.step_id] is StepState.PENDING
    released = (await w.h.repository.events(w.task_id))[-1]
    assert released.event_type is TaskEventType.STEP_RELEASED
    assert released.metadata["assignment_id"] == str(assignment.id)


@pytest.mark.parametrize(
    "status", [ExecutionStatus.STARTED, ExecutionStatus.SUCCEEDED], ids=["started", "outcome"]
)
async def test_an_expiry_that_left_something_behind_is_not_a_release(
    w: World, status: ExecutionStatus
) -> None:
    """A STARTED record — somebody may have acted — or an outcome: ``Executor.finish`` closes
    the step, and the runner calls it; the step stays RUNNING here."""
    assignment = await offered(w)
    await w.results.add(step_result_for(w.task_id, w.step_id, status))
    w.h.clock.advance(TTL)

    assert await w.service.lapse(assignment) is Lapse.LEFT_BEHIND
    graph = await w.h.engine.graph(w.task_id)
    assert graph.states[w.step_id] is StepState.RUNNING


async def test_a_revocation_cuts_the_nodes_work_short(w: World) -> None:
    await offered(w)

    assert await w.service.cut_short(NODE.id) == 1
    assert (await w.service.standing(w.task_id, w.step_id)).standing is Standing.LAPSED


# ----------------------------------------------------------------------------------------
# A refusal on the way of the work
# ----------------------------------------------------------------------------------------


async def test_a_late_delivery_is_written_with_the_status_the_node_reports(w: World) -> None:
    assignment = await offered(w)
    await w.service.reject(
        NODE.id,
        WorkRejection.LATE,
        assignment_id=assignment.id,
        task_id=w.task_id,
        reported=ExecutionStatus.SUCCEEDED,
    )
    event = (await w.h.audit.read())[-1]

    assert event.event_type is AuditEventType.DEVICE_REJECTED
    assert event.actor == WORK_ACTOR
    assert event.task_id == w.task_id
    assert event.payload == {
        "reason": "late",
        "named_device_id": str(NODE.id),
        "assignment_id": str(assignment.id),
        "reported_status": "SUCCEEDED",
    }
    assert "pc-windows" in event.summary


async def test_an_assignment_not_held_says_whether_it_was_known(w: World) -> None:
    unknown = UUID("00000000-0000-4000-8000-000000000999")
    await w.service.reject(
        OTHER_NODE.id, WorkRejection.NOT_ASSIGNED, assignment_id=unknown, known=False
    )
    event = (await w.h.audit.read())[-1]

    assert event.task_id is None
    assert event.payload["reason"] == "not_assigned"
    assert event.payload["assignment_known"] is False


@pytest.mark.parametrize(
    ("ttl", "cap"),
    [
        (timedelta(0), CAP),
        (CAP + INSTANT, CAP),
        (TTL, MAX_ASSIGNMENT_CAP + INSTANT),
    ],
    ids=["no-ttl", "ttl-beyond-the-cap", "cap-beyond-its-cap"],
)
def test_the_service_refuses_durations_that_do_not_fit(ttl: timedelta, cap: timedelta) -> None:
    h = make_harness()
    with pytest.raises(ValueError, match="0 < ttl <= cap"):
        Assignments(
            FakeAssignmentStore(),
            engine=h.engine,
            repository=h.repository,
            results=FakeExecutionResultStore(),
            devices=DeviceRegistry(
                FakeDeviceRegistry(), h.clock, h.audit, h.ids, heartbeat_ttl=timedelta(seconds=60)
            ),
            audit=h.audit,
            clock=h.clock,
            ids=h.ids,
            ttl=ttl,
            cap=cap,
        )
