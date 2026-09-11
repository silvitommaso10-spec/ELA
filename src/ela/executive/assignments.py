"""The assignments (§15, §16; M12.2, ADR 0038 §6): the one door to the work handed to a node.

The port keeps a row as written — an offer an hour past its expiry is still ``OFFERED`` there —
and this service says what it is *now*, the way :class:`~ela.devices.DeviceRegistry` says whether
a node is available: derived on read, and no sweeper (ADR 0016 §3). Every write passes from here,
and this is the one module that may name the port (architecture rule 48): handing work out, a node
taking it, bringing it back, renewing it, letting an expiry act, cutting short the work of a node
the user revoked, and writing down a refusal on the way of the work.

**Every write that sets an expiry writes a heartbeat of the task first.** ``assign``, ``claim``
and ``renew`` read ``now``, compute the expiry, write a ``HEARTBEAT`` (ADR 0008 §5) and only then
the row. So for an assignment alive at an instant ``n``, ``n - last_seen < ttl``; and the start-up
refuses a TTL that is not below ``orphan_after``. ``recover()`` therefore cannot fail a task whose
work is still out, and it holds by construction rather than by coordination (ADR 0038 §9).

Nothing here calls the executor — the executor calls :meth:`Assignments.assign` — and when an
expiry left something in the store, :meth:`Assignments.lapse` says so and the runner calls
``Executor.finish``: a cycle between the two would be a module nobody knows where it begins.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum, auto
from typing import Final, NamedTuple

from ela.devices import LOCAL_DEVICE_ID, DeviceRegistry, PlacementDecision, ensure_placed
from ela.domain import (
    Actor,
    ActorKind,
    Assignment,
    AssignmentId,
    AssignmentState,
    AuditEvent,
    AuditEventId,
    AuditEventType,
    AuthorizationId,
    DeviceId,
    ExecutionStatus,
    JsonValue,
    PermissionDecision,
    PermissionOutcome,
    StepId,
    TaskEventType,
    TaskId,
)
from ela.executive.errors import AssignmentAtCapError, AssignmentRefusedError
from ela.ports import (
    AssignmentExpiredError,
    AssignmentHeldElsewhereError,
    AssignmentStateError,
    AssignmentStore,
    AuditLog,
    Clock,
    ExecutionResultStore,
    IdGenerator,
    TaskRepository,
)
from ela.tasks.engine import TaskEngine

__all__ = [
    "DEFAULT_ASSIGNMENT_CAP",
    "DEFAULT_ASSIGNMENT_TTL",
    "MAX_ASSIGNMENT_CAP",
    "WORK_ACTOR",
    "Assignments",
    "Lapse",
    "Stand",
    "Standing",
    "WorkRejection",
]

DEFAULT_ASSIGNMENT_TTL: Final = timedelta(seconds=120)
"""How long the Core waits before deciding a node is gone (ADR 0038 §5).

One measure for the two silences — the claim of work offered, and a sign of the work taken —
because the question is one, and two variables would make of D6 two facts with two settings.
Twice the heartbeat's TTL, so a node available when it was chosen had a whole interval to show up;
below the decision's five minutes, so the shortest offer leaves the node time to start. A reason,
not a measurement: M12.3 measures it on a real node."""

DEFAULT_ASSIGNMENT_CAP: Final = timedelta(hours=1)
"""The longest life of work a node took, however often it renews (ADR 0038 §13)."""

MAX_ASSIGNMENT_CAP: Final = timedelta(days=1)
"""No TTL without a cap, and the cap has one too: a node stuck renewing for ever would hold a
step for ever."""

WORK_ACTOR: Final = Actor(kind=ActorKind.SYSTEM, id="assignments")
"""Who signs a refusal on the way of the work: ``SYSTEM``, as M12.1 fixed for ``DEVICE_REJECTED``
(ADR 0037 §13) — the Core decided it — under a name of its own, because the registry is not the
one refusing."""


class WorkRejection(StrEnum):
    """Why a request of an authenticated node on the way of the work was refused (ADR 0038 §12).

    The four reasons of the work, beside the four of identity the registry writes
    (:class:`~ela.devices.Rejection`): one type of event, ``DEVICE_REJECTED``, two writers. Each is
    valued as its name in lower case, the way ADR 0037 §13 writes the reasons.
    """

    LATE = auto()
    """A delivery after the work expired. Refused, and what the node reports stays in the audit
    as its word — never the output."""
    TASK_CLOSED = auto()
    """A delivery for a task that closed while the node was working on it."""
    NOT_ASSIGNED = auto()
    """A delivery or a renewal of an assignment the node does not hold: unknown, or another's —
    the node gets the same ``404`` for both, and the audit tells them apart."""
    DELIVERY_CONFLICT = auto()
    """A second delivery with another envelope than the one accepted."""


class Standing(StrEnum):
    """What the latest assignment of a RUNNING step is *now* (ADR 0038 §10)."""

    NONE = "none"
    """No assignment, or one already released: the step goes the way it always went."""
    LIVE = "live"
    """Offered or taken, and not expired: the work is out, and the run returns ``ASSIGNED``."""
    LAPSED = "lapsed"
    """Its expiry passed, marked or not, and nobody released the step yet: :meth:`lapse`."""
    DELIVERED = "delivered"
    """The node's envelope was accepted and the step did not close: ``Executor.finish``."""


class Stand(NamedTuple):
    """The standing of a step, and the assignment it is about."""

    standing: Standing
    assignment: Assignment | None


class Lapse(StrEnum):
    """What letting an expiry act did (ADR 0038 §8)."""

    RELEASED = "released"
    """Nothing in the store: nobody can have acted, and the step is back in play."""
    LEFT_BEHIND = "left_behind"
    """A STARTED record or an outcome is in the store: ``Executor.finish`` closes the step."""


class Assignments:
    """The work handed to remote nodes, as it is now, and every write of it (ADR 0038 §6)."""

    __slots__ = (
        "_audit",
        "_cap",
        "_clock",
        "_devices",
        "_engine",
        "_ids",
        "_repository",
        "_results",
        "_store",
        "_ttl",
    )

    def __init__(
        self,
        store: AssignmentStore,
        *,
        engine: TaskEngine,
        repository: TaskRepository,
        results: ExecutionResultStore,
        devices: DeviceRegistry,
        audit: AuditLog,
        clock: Clock,
        ids: IdGenerator,
        ttl: timedelta = DEFAULT_ASSIGNMENT_TTL,
        cap: timedelta = DEFAULT_ASSIGNMENT_CAP,
    ) -> None:
        if not timedelta(0) < ttl <= cap <= MAX_ASSIGNMENT_CAP:
            raise ValueError(
                f"an assignment needs 0 < ttl <= cap <= {MAX_ASSIGNMENT_CAP}, not ttl {ttl} "
                f"and cap {cap}"
            )
        self._store = store
        self._engine = engine
        self._repository = repository
        self._results = results
        self._devices = devices
        self._audit = audit
        self._clock = clock
        self._ids = ids
        self._ttl = ttl
        self._cap = cap

    # ----------------------------------------------------------------------------------
    # Handing work out, and reading where it stands
    # ----------------------------------------------------------------------------------

    async def assign(
        self,
        decision: PermissionDecision,
        placement: PlacementDecision,
        *,
        authorization_id: AuthorizationId | None,
    ) -> Assignment:
        """Hand the call of ``decision`` to the node ``placement`` chose, as an offer.

        Refused before anything is written: a placement that allows no node for this very step
        (:func:`~ela.devices.ensure_placed`, the same pure function ADR 0026 §3 gave the
        executor), ``local`` — which runs in this process —, a decision that is not ``ALLOWED`` or
        that has expired at ``now``. The offer lives until ``min(now + ttl,
        decision.expires_at)``: nobody may take work whose decision will have lapsed.
        ``authorization_id`` is the grant ``consume`` spent, named by what comes back.
        """
        task_id, step_id = decision.task_id, decision.step_id
        if task_id is None or step_id is None:
            raise AssignmentRefusedError(decision.id, "the decision is about no step")
        device = ensure_placed(placement, task_id, step_id)
        if device.id == LOCAL_DEVICE_ID:
            raise AssignmentRefusedError(
                decision.id, "local runs in this process: it is executed, never assigned"
            )
        if decision.outcome is not PermissionOutcome.ALLOWED:
            raise AssignmentRefusedError(
                decision.id, f"only an ALLOWED decision leaves the Core, not {decision.outcome}"
            )
        now = self._clock.now()
        if decision.expires_at is None or decision.expires_at <= now:
            raise AssignmentRefusedError(decision.id, "the decision has expired")
        expires_at = min(now + self._ttl, decision.expires_at)
        await self._engine.heartbeat(task_id)
        assignment = Assignment(
            id=AssignmentId(self._ids.new_uuid()),
            created_at=now,
            task_id=task_id,
            step_id=step_id,
            device_id=device.id,
            decision=decision,
            authorization_id=authorization_id,
            state=AssignmentState.OFFERED,
            expires_at=expires_at,
        )
        await self._store.add(assignment)
        return assignment

    async def standing(self, task_id: TaskId, step_id: StepId) -> Stand:
        """The latest assignment of a step, as it is now — read, never written."""
        held = await self._store.for_step(task_id, step_id)
        if not held or await self._released(held[-1]):
            return Stand(Standing.NONE, None)
        last = held[-1]
        if last.state is AssignmentState.DELIVERED:
            return Stand(Standing.DELIVERED, last)
        if last.state is not AssignmentState.EXPIRED and last.expires_at > self._clock.now():
            return Stand(Standing.LIVE, last)
        return Stand(Standing.LAPSED, last)

    async def describe(self, assignment: Assignment) -> str:
        """Why a run returned ``ASSIGNED``: what a person deciding whether to wait needs to read.

        The assignment's words, passed on by the runner and never composed there (ADR 0038 §10).
        """
        device = await self._devices.get(assignment.device_id)
        return (
            f"step {assignment.step_id} assigned to node {device.name} ({assignment.device_id}) "
            f"as assignment {assignment.id}, due by {assignment.expires_at.isoformat()}"
        )

    async def next_for(self, device_id: DeviceId) -> Assignment | None:
        """The oldest offer to ``device_id`` that has not expired; ``None`` if there is none."""
        now = self._clock.now()
        offers = await self._store.offered_to(device_id)
        return next((offer for offer in offers if offer.expires_at > now), None)

    # ----------------------------------------------------------------------------------
    # The node's moves: take, bring back, renew
    # ----------------------------------------------------------------------------------

    async def claim(self, assignment_id: AssignmentId, device_id: DeviceId) -> Assignment:
        """The node takes the offer: a heartbeat of the task, then ``OFFERED → CLAIMED``.

        Read first, so that a claim that cannot happen writes no heartbeat; the conditional
        ``UPDATE`` of the store is still what decides, a node's busy hands included (M12.1, D16).
        """
        now = self._clock.now()
        offer = await self._store.get(assignment_id)
        _movable(offer, device_id, AssignmentState.OFFERED, now)
        await self._engine.heartbeat(offer.task_id)
        return await self._store.claim(
            assignment_id, device_id=device_id, now=now, expires_at=now + self._ttl
        )

    async def deliver(
        self, assignment_id: AssignmentId, device_id: DeviceId, *, digest: str, now: datetime
    ) -> Assignment:
        """``CLAIMED → DELIVERED`` with the digest of the envelope, at the instant of the gate:
        one instant serves the check and the writes (ADR 0013 §6)."""
        return await self._store.deliver(assignment_id, device_id=device_id, now=now, digest=digest)

    async def renew(self, assignment_id: AssignmentId, device_id: DeviceId) -> Assignment:
        """The work in hand lives a TTL more, up to its cap: a heartbeat, then the new expiry.

        No audit: a sign of life is not an action (ADR 0016 §6). At the cap nothing is written,
        and :class:`~ela.executive.errors.AssignmentAtCapError` says when the work expires.
        """
        now = self._clock.now()
        work = await self._store.get(assignment_id)
        _movable(work, device_id, AssignmentState.CLAIMED, now)
        assert work.claimed_at is not None  # the entity's own invariant for work in hand
        expires_at = min(now + self._ttl, work.claimed_at + self._cap)
        if expires_at <= work.expires_at:
            raise AssignmentAtCapError(assignment_id, work.expires_at)
        await self._engine.heartbeat(work.task_id)
        return await self._store.renew(
            assignment_id, device_id=device_id, now=now, expires_at=expires_at
        )

    # ----------------------------------------------------------------------------------
    # When time decides: the expiry acts, the revocation makes one
    # ----------------------------------------------------------------------------------

    async def lapse(self, assignment: Assignment) -> Lapse:
        """Let an expiry act: ``EXPIRED``, then the answer of M12.1, D14 (ADR 0038 §8).

        Nothing in the store for the step: nobody can have acted, so the step is released — the
        one caller of ``release_step`` (architecture rule 50), and the only one who can see the
        store. A STARTED record or an outcome: ``Executor.finish`` closes it, and the runner calls
        it — this service never calls the executor.
        """
        await self._store.expire(assignment.id, now=self._clock.now())
        if await self._results.for_step(assignment.task_id, assignment.step_id):
            return Lapse.LEFT_BEHIND
        await self._engine.release_step(
            assignment.task_id,
            assignment.step_id,
            key=assignment.id,
            device_id=assignment.device_id,
        )
        return Lapse.RELEASED

    async def cut_short(self, device_id: DeviceId) -> int:
        """The revocation is an expiry (M12.1, D17): every live assignment of the node expires now,
        the offers it can no longer take as well as the work it took. How many were cut."""
        return await self._store.cut_short(device_id, now=self._clock.now())

    # ----------------------------------------------------------------------------------
    # A refusal on the way of the work
    # ----------------------------------------------------------------------------------

    async def reject(
        self,
        device_id: DeviceId,
        reason: WorkRejection,
        *,
        assignment_id: AssignmentId,
        task_id: TaskId | None = None,
        known: bool = True,
        reported: ExecutionStatus | None = None,
    ) -> None:
        """``DEVICE_REJECTED`` with a reason of the work (ADR 0038 §12).

        ``task_id`` only for an assignment the node held; ``known`` tells, for ``not_assigned``,
        an unknown id from another node's; ``reported`` is the status a late or orphaned delivery
        carried — the node's word, recorded as a word. Never the output, never the digest.
        """
        device = await self._devices.get(device_id)
        payload: dict[str, JsonValue] = {
            "reason": reason.value,
            "named_device_id": str(device_id),
            "assignment_id": str(assignment_id),
        }
        if reason is WorkRejection.NOT_ASSIGNED:
            payload["assignment_known"] = known
        if reported is not None:
            payload["reported_status"] = reported.value
        await self._audit.append(
            AuditEvent(
                id=AuditEventId(self._ids.new_uuid()),
                created_at=self._clock.now(),
                event_type=AuditEventType.DEVICE_REJECTED,
                actor=WORK_ACTOR,
                summary=(
                    f"a request of node {device.name} ({device_id}) on the way of the work was "
                    f"refused: {reason.value}"
                ),
                task_id=task_id,
                payload=payload,
            )
        )

    async def _released(self, assignment: Assignment) -> bool:
        """Whether a ``STEP_RELEASED`` of its step carries this assignment's id (ADR 0038 §8)."""
        return any(
            event.event_type is TaskEventType.STEP_RELEASED
            and event.step_id == assignment.step_id
            and event.metadata.get("assignment_id") == str(assignment.id)
            for event in await self._repository.events(assignment.task_id)
        )


def _movable(
    assignment: Assignment, device_id: DeviceId, state: AssignmentState, now: datetime
) -> None:
    """What the store's ``UPDATE`` will ask, asked first so that a move that cannot happen writes
    no heartbeat; the store's statement stays the one that decides."""
    if assignment.device_id != device_id:
        raise AssignmentHeldElsewhereError(assignment.id, assignment.device_id)
    if assignment.state is not state:
        raise AssignmentStateError(assignment.id, assignment.state)
    if assignment.expires_at <= now:
        raise AssignmentExpiredError(assignment.id, assignment.expires_at)
