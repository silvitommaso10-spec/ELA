"""In-memory implementations of every port in :mod:`ela.ports`, for the tests (spec §51).

One fake per port, deterministic and without I/O. Each fake honours the contract of its port —
the same contract tests in ``tests/contracts/`` run on the fakes and on every real adapter — and
records what it receives (``calls``, ``requests``) as tuples, so a test can assert on *what* was
asked, not only on what came back.

A fake that builds entities (the Guardian, a tool, a provider) takes a :class:`~ela.ports.Clock`
and an :class:`~ela.ports.IdGenerator`: an adapter owns its own clock and id source, the caller
never passes "now" to a tool.

This package is for tests only. Rule 6 (ADR 0005) forbids any production module of ``ela`` from
importing it, and rule 7 keeps it dependent on nothing but the standard library, the domain and
the ports.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final, NamedTuple, cast
from uuid import UUID

from ela.domain import (
    Admission,
    Approval,
    ApprovalId,
    ApprovalStatus,
    Assignment,
    AssignmentId,
    AssignmentState,
    AuditEvent,
    Authorization,
    AuthorizationId,
    CapabilityId,
    CapabilitySpec,
    DecisionId,
    Device,
    DeviceAvailability,
    DeviceId,
    DeviceRole,
    DeviceStatus,
    Enrollment,
    ErrorMetadata,
    ExecutionId,
    ExecutionResult,
    ExecutionStatus,
    JsonMapping,
    ModelRoute,
    PermissionDecision,
    PermissionOutcome,
    PlanId,
    PowerSource,
    ProbeFamily,
    ProviderRequest,
    ProviderResult,
    ProviderResultId,
    ProviderStatus,
    ProviderUsage,
    RawCapture,
    RawHeardSegment,
    RawObservation,
    RawRecognition,
    RawSpeech,
    RawTranscript,
    Reservation,
    RiskLevel,
    StepId,
    Task,
    TaskEvent,
    TaskEventId,
    TaskId,
    TaskPlan,
    TaskState,
    TaskStep,
    WorstCase,
)
from ela.ports import (
    ANNOUNCED_FIELDS,
    NAVIGATION,
    PROVIDER_UNAVAILABLE,
    STARTED_ID,
    VERIFICATION_NO_CONDITIONS,
    VERIFICATION_NOT_SUCCEEDED,
    VERIFICATION_UNKNOWN_CONDITION,
    VERIFICATION_WRONG_CAPABILITY,
    AlreadyExistsError,
    ApprovalAlreadyAnsweredError,
    ApprovalExpiredError,
    AssignmentExpiredError,
    AssignmentHeldElsewhereError,
    AssignmentNodeBusyError,
    AssignmentStateError,
    AssignmentStillLiveError,
    AuthorizationAlreadyRevokedError,
    AuthorizationExhaustedError,
    AuthorizationExpiredError,
    AuthorizationRevokedError,
    BrowserError,
    BrowserStopped,
    CallRequest,
    Clock,
    Command,
    DeviceRevokedError,
    Ending,
    EnrollmentConsumedError,
    EnrollmentExpiredError,
    EnrollmentRoleError,
    Field,
    Forwarded,
    Glanced,
    IdentityConflictError,
    IdGenerator,
    ModelProvider,
    NotAllowedError,
    NotFoundError,
    Opened,
    PageGone,
    Prospect,
    Ran,
    RoutingError,
    SessionEnd,
    SessionHandle,
    SessionHost,
    SessionPlan,
    StopPoint,
    TaskStop,
    ToolPort,
    ToolStopped,
    VerifierPort,
    check_answer,
    check_limit,
    check_verifiable,
)

__all__ = [
    "DEFAULT_START",
    "FAKE_CALL_WORST",
    "FAKE_CONDITION",
    "FAKE_SESSION_TOOLS",
    "FAKE_CURRENCY",
    "FAKE_WORST_CASE",
    "FakeApprovalStore",
    "FakeAuditLog",
    "FakeAuthorizationStore",
    "FakeBell",
    "FakeBrowser",
    "FakePage",
    "FakeCapabilityRegistry",
    "FakeClock",
    "FakeLauncher",
    "FakeDeviceRegistry",
    "FakeExecutionResultStore",
    "FakeIdGenerator",
    "FakeModelProvider",
    "FakeModelRouter",
    "FakePermissionGuardian",
    "FakeProbe",
    "FakeProviderRegistry",
    "FakeListening",
    "FakeLocalBeat",
    "FakePower",
    "FakeScreenCapture",
    "FakeSpeech",
    "FakeTaskRepository",
    "FakeTextRecognition",
    "FakeTool",
    "FakeToolRegistry",
    "FakeVerifier",
    "FakeVerifierRegistry",
    "GuardianCall",
    "ToolCall",
    "VerifierCall",
    "FakeEnrollmentStore",
    "FakeAssignmentStore",
    "FakeStop",
    "FakeAgentSession",
    "FakeModelGateway",
    "SessionScript",
    "finished",
]

DEFAULT_START: Final = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
"""Where a :class:`FakeClock` starts unless told otherwise."""

FAKE_CONDITION: Final = "fake.ok"
"""The one condition a :class:`FakeVerifier` can check unless told otherwise; it holds."""


# --------------------------------------------------------------------------------------
# Time and identity
# --------------------------------------------------------------------------------------


class FakeClock:
    """A clock that moves only when the test says so (port :class:`~ela.ports.Clock`)."""

    def __init__(self, start: datetime = DEFAULT_START) -> None:
        if start.tzinfo is None or start.tzinfo.utcoffset(start) is None:
            raise ValueError("FakeClock needs a timezone-aware start")
        self._now = start.astimezone(UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        """Move forward by ``delta``; a negative delta is refused, the fake is monotonic."""
        if delta < timedelta(0):
            raise ValueError("FakeClock only moves forward")
        self._now += delta


class FakeIdGenerator:
    """Sequential, readable UUIDs (port :class:`~ela.ports.IdGenerator`).

    ``00000000-0000-4000-8000-000000000001``, ``...002``, and so on: two fresh generators produce
    the same sequence, so a test can predict the id an entity will get.
    """

    def __init__(self) -> None:
        self._next = 1

    def new_uuid(self) -> UUID:
        value = UUID(f"00000000-0000-4000-8000-{self._next:012d}")
        self._next += 1
        return value


# --------------------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------------------


class FakeTaskRepository:
    """Tasks, their events and their plans in dictionaries (port ``TaskRepository``)."""

    def __init__(self) -> None:
        self._tasks: dict[TaskId, Task] = {}
        self._events: dict[TaskId, tuple[TaskEvent, ...]] = {}
        self._event_ids: set[TaskEventId] = set()
        self._plans: dict[TaskId, TaskPlan] = {}
        self._plan_ids: set[PlanId] = set()

    def _require_parent(self, task: Task) -> None:
        if task.parent_id is not None and task.parent_id not in self._tasks:
            raise NotFoundError("task", task.parent_id)

    async def add(self, task: Task) -> None:
        self._require_parent(task)
        if task.id in self._tasks:
            raise AlreadyExistsError("task", task.id)
        self._tasks[task.id] = task
        self._events[task.id] = ()

    async def save(self, task: Task) -> None:
        self._require_parent(task)
        if task.id not in self._tasks:
            raise NotFoundError("task", task.id)
        self._tasks[task.id] = task

    async def get(self, task_id: TaskId) -> Task:
        try:
            return self._tasks[task_id]
        except KeyError:
            raise NotFoundError("task", task_id) from None

    async def tasks(
        self, *, states: frozenset[TaskState] | None = None, limit: int | None = None
    ) -> tuple[Task, ...]:
        check_limit(limit)
        selected = (t for t in self._tasks.values() if states is None or t.state in states)
        return tuple(selected)[:limit]

    async def count(self, *, states: frozenset[TaskState] | None = None) -> Mapping[TaskState, int]:
        counted: dict[TaskState, int] = {}
        for task in self._tasks.values():
            if states is None or task.state in states:
                counted[task.state] = counted.get(task.state, 0) + 1
        return counted

    async def finished(self, *, states: frozenset[TaskState], limit: int) -> tuple[Task, ...]:
        check_limit(limit)
        selected = [
            (index, task) for index, task in enumerate(self._tasks.values()) if task.state in states
        ]
        # Newest hour first, the last inserted first on a tie, and no hour at the end: the order
        # the SQL writes as ``finished_at DESC NULLS LAST, seq DESC``.
        selected.sort(
            key=lambda pair: (
                pair[1].finished_at is not None,
                pair[1].finished_at or datetime.min.replace(tzinfo=UTC),
                pair[0],
            ),
            reverse=True,
        )
        return tuple(task for _, task in selected)[:limit]

    async def due(
        self, *, states: frozenset[TaskState] | None = None, limit: int | None = None
    ) -> tuple[Task, ...]:
        check_limit(limit)
        selected = [
            task
            for task in self._tasks.values()
            if task.deadline is not None and (states is None or task.state in states)
        ]
        # ``sorted`` is stable, so insertion order breaks ties exactly as ``seq`` does in SQL.
        selected.sort(key=lambda task: cast(datetime, task.deadline))
        return tuple(selected)[:limit]

    async def due_count(self, *, states: frozenset[TaskState] | None = None) -> int:
        return sum(
            1
            for task in self._tasks.values()
            if task.deadline is not None and (states is None or task.state in states)
        )

    async def append_event(self, event: TaskEvent) -> None:
        if event.task_id not in self._tasks:
            raise NotFoundError("task", event.task_id)
        if event.id in self._event_ids:
            raise AlreadyExistsError("task event", event.id)
        self._event_ids.add(event.id)
        self._events[event.task_id] = (*self._events[event.task_id], event)

    async def events(self, task_id: TaskId) -> tuple[TaskEvent, ...]:
        try:
            return self._events[task_id]
        except KeyError:
            raise NotFoundError("task", task_id) from None

    async def add_plan(self, plan: TaskPlan) -> None:
        if plan.task_id not in self._tasks:
            raise NotFoundError("task", plan.task_id)
        if plan.task_id in self._plans or plan.id in self._plan_ids:
            raise AlreadyExistsError("task plan", plan.id)
        self._plans[plan.task_id] = plan
        self._plan_ids.add(plan.id)

    async def plan(self, task_id: TaskId) -> TaskPlan:
        if task_id not in self._tasks:
            raise NotFoundError("task", task_id)
        try:
            return self._plans[task_id]
        except KeyError:
            raise NotFoundError("task plan", task_id) from None


class FakeBell:
    """A bell that remembers what it rang and never touches a network (port ``Bell``).

    ``ready`` is a flag and not a deduction: a test that wants the silent case — no topic, or no
    address to open — turns it off, and one that wants the bell to fail turns ``delivers`` off.
    """

    def __init__(self, *, ready: bool = True, delivers: bool = True, name: str = "fake") -> None:
        self.rung: list[RiskLevel] = []
        self.serving: tuple[str, ...] = ()
        self.delivers = delivers
        self._ready = ready
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def ready(self) -> bool:
        return self._ready

    def serving_at(self, addresses: Sequence[str]) -> None:
        """Not a member of the port: the composition hands this over as a callable (ADR 0043 §8),
        and the fake keeps it so a test can wire one the same way production does."""
        self.serving = tuple(addresses)

    async def approval_waiting(self, risk: RiskLevel) -> bool:
        self.rung.append(risk)
        return self.delivers


class FakeAuditLog:
    """An append-only trail kept as a tuple (port :class:`~ela.ports.AuditLog`).

    The state is a tuple rebuilt on every append: not even this class has a list to mutate.
    """

    def __init__(self) -> None:
        self._events: tuple[AuditEvent, ...] = ()

    async def append(self, event: AuditEvent) -> None:
        if any(existing.id == event.id for existing in self._events):
            raise AlreadyExistsError("audit event", event.id)
        self._events = (*self._events, event)

    async def read(
        self,
        *,
        task_id: TaskId | None = None,
        since: datetime | None = None,
        limit: int | None = None,
        newest_first: bool = False,
    ) -> tuple[AuditEvent, ...]:
        check_limit(limit)
        source = reversed(self._events) if newest_first else self._events
        selected = (
            event
            for event in source
            if (task_id is None or event.task_id == task_id)
            and (since is None or event.created_at >= since)
        )
        return tuple(selected)[:limit]


class FakeDeviceRegistry:
    """Nodes by id (port :class:`~ela.ports.DeviceRegistryPort`).

    ``devices`` seeds the registry in the order given, as :class:`FakeCapabilityRegistry` and
    :class:`FakeToolRegistry` do: a test that needs a node to exist should not have to await it.
    """

    def __init__(self, devices: Iterable[Device] = ()) -> None:
        self._devices: dict[DeviceId, Device] = {device.id: device for device in devices}
        self._secret_hashes: dict[DeviceId, str] = {}

    async def register(self, device: Device) -> None:
        if device.id in self._devices:
            raise AlreadyExistsError("device", device.id)
        self._devices[device.id] = device

    async def update(self, device: Device) -> None:
        if device.id not in self._devices:
            raise NotFoundError("device", device.id)
        self._devices[device.id] = device

    async def get(self, device_id: DeviceId) -> Device:
        try:
            return self._devices[device_id]
        except KeyError:
            raise NotFoundError("device", device_id) from None

    async def devices(self) -> tuple[Device, ...]:
        return tuple(self._devices.values())

    async def enroll(self, device: Device, *, secret_hash: str) -> None:
        await self.register(device)
        self._secret_hashes[device.id] = secret_hash

    async def secret_hash(self, device_id: DeviceId) -> str | None:
        await self.get(device_id)
        return self._secret_hashes.get(device_id)

    async def announce(self, device: Device, *, expected_revision: int) -> int:
        current = await self.get(device.id)
        if current.revoked_at is not None:
            raise DeviceRevokedError(device.id, current.revoked_at)
        if current.revision != expected_revision:
            raise IdentityConflictError(device.id, expected_revision, current.revision)
        declared = {field: getattr(device, field) for field in ANNOUNCED_FIELDS}
        revision = expected_revision + 1
        self._devices[device.id] = current.model_copy(update={**declared, "revision": revision})
        return revision

    async def observe(
        self,
        device_id: DeviceId,
        *,
        seen_at: datetime,
        availability: DeviceAvailability,
        status: DeviceStatus | None = None,
        current_workload: float | None = None,
        power_source: PowerSource | None = None,
    ) -> None:
        current = await self.get(device_id)
        observed: dict[str, object] = {"last_seen_at": seen_at, "availability": availability}
        if status is not None:
            observed["status"] = status
        if current_workload is not None:
            observed["current_workload"] = current_workload
        if power_source is not None:
            observed["power_source"] = power_source
        self._devices[device_id] = current.model_copy(update=observed)

    async def revoke(self, device_id: DeviceId, *, at: datetime) -> bool:
        current = await self.get(device_id)
        if current.revoked_at is not None:
            return False
        self._devices[device_id] = current.model_copy(update={"revoked_at": at})
        return True


class FakeEnrollmentStore:
    """One-shot codes by hash (port :class:`~ela.ports.EnrollmentStore`).

    Never a hash in an error: the same discipline as the adapter, so a test that passes on the
    fake is not passing on something the adapter could not do.
    """

    def __init__(self) -> None:
        self._codes: dict[str, Enrollment] = {}

    async def offer(self, enrollment: Enrollment) -> None:
        if self._codes.get(enrollment.code_hash) is not None:
            raise AlreadyExistsError("enrollment", "code")
        self._codes[enrollment.code_hash] = enrollment

    async def consume(
        self, code_hash: str, *, device_id: DeviceId, now: datetime, role: DeviceRole
    ) -> Enrollment:
        """The order of the port: unknown, spent, the wrong role, expired (M12.5 dec. C.5)."""
        enrollment = self._codes.get(code_hash)
        if enrollment is None:
            raise NotFoundError("enrollment", "code")
        if enrollment.device_id is not None:
            raise EnrollmentConsumedError(enrollment.device_id)
        if enrollment.role is not role:
            raise EnrollmentRoleError(enrollment.role, role)
        if enrollment.expires_at <= now:
            raise EnrollmentExpiredError(enrollment.expires_at)
        spent = enrollment.model_copy(update={"consumed_at": now, "device_id": device_id})
        self._codes[code_hash] = spent
        return spent


class FakeAssignmentStore:
    """Work handed to remote nodes, by id, in insertion order (port ``AssignmentStore``).

    Kept as **rows** — the field values of each assignment — and every read rebuilds the entity,
    validated, the way the adapter's mapper does. A move writes fields of the row and never copies
    the entity: ``model_copy`` does not run the validators, which is why architecture rules 5 and
    15 watch it, and a move the entity refuses must fail here as it fails on a real read.

    Every move checks what the adapter's conditional ``UPDATE`` checks, in the port's order, and
    writes only when everything holds: the same refusals for the same reasons, so a test that
    passes on the fake is not passing on something the adapter could not do. The two constraints
    the table holds — one id, one assignment per step that is not ``EXPIRED`` — are checked by
    scanning, like the ``STARTED`` index of :class:`FakeExecutionResultStore`.
    """

    def __init__(self) -> None:
        self._rows: dict[AssignmentId, dict[str, Any]] = {}

    async def add(self, assignment: Assignment) -> None:
        if assignment.id in self._rows:
            raise AlreadyExistsError("assignment", assignment.id)
        if any(
            row["task_id"] == assignment.task_id
            and row["step_id"] == assignment.step_id
            and row["state"] is not AssignmentState.EXPIRED
            for row in self._rows.values()
        ):
            raise AlreadyExistsError("open assignment for step", assignment.step_id)
        self._rows[assignment.id] = assignment.model_dump()

    async def get(self, assignment_id: AssignmentId) -> Assignment:
        return Assignment.model_validate(self._row(assignment_id))

    async def for_step(self, task_id: TaskId, step_id: StepId) -> tuple[Assignment, ...]:
        return tuple(
            Assignment.model_validate(row)
            for row in self._rows.values()
            if row["task_id"] == task_id and row["step_id"] == step_id
        )

    async def offered_to(self, device_id: DeviceId) -> tuple[Assignment, ...]:
        return tuple(
            Assignment.model_validate(row)
            for row in self._rows.values()
            if row["device_id"] == device_id and row["state"] is AssignmentState.OFFERED
        )

    async def claim(
        self,
        assignment_id: AssignmentId,
        *,
        device_id: DeviceId,
        now: datetime,
        expires_at: datetime,
    ) -> Assignment:
        row = self._movable(assignment_id, device_id, AssignmentState.OFFERED, now)
        if any(
            held["device_id"] == device_id
            and held["state"] is AssignmentState.CLAIMED
            and held["expires_at"] > now
            for held in self._rows.values()
        ):
            raise AssignmentNodeBusyError(assignment_id, device_id)
        return self._write(
            assignment_id,
            {**row, "state": AssignmentState.CLAIMED, "claimed_at": now, "expires_at": expires_at},
        )

    async def deliver(
        self, assignment_id: AssignmentId, *, device_id: DeviceId, now: datetime, digest: str
    ) -> Assignment:
        row = self._movable(assignment_id, device_id, AssignmentState.CLAIMED, now)
        return self._write(
            assignment_id,
            {
                **row,
                "state": AssignmentState.DELIVERED,
                "delivered_at": now,
                "delivery_digest": digest,
            },
        )

    async def renew(
        self,
        assignment_id: AssignmentId,
        *,
        device_id: DeviceId,
        now: datetime,
        expires_at: datetime,
    ) -> Assignment:
        row = self._movable(assignment_id, device_id, AssignmentState.CLAIMED, now)
        return self._write(assignment_id, {**row, "expires_at": expires_at})

    async def withdraw(self, assignment_id: AssignmentId, *, now: datetime) -> Assignment:
        row = self._row(assignment_id)
        if row["state"] is not AssignmentState.OFFERED:
            return Assignment.model_validate(row)
        return self._write(assignment_id, {**row, "state": AssignmentState.WITHDRAWN})

    async def expire(self, assignment_id: AssignmentId, *, now: datetime) -> Assignment:
        row = self._row(assignment_id)
        if row["state"] is AssignmentState.EXPIRED:
            return Assignment.model_validate(row)
        if row["state"] is AssignmentState.DELIVERED:
            raise AssignmentStateError(assignment_id, row["state"])
        if row["expires_at"] > now:
            raise AssignmentStillLiveError(assignment_id, row["expires_at"])
        return self._write(assignment_id, {**row, "state": AssignmentState.EXPIRED})

    async def cut_short(self, device_id: DeviceId, *, now: datetime) -> int:
        live = [
            assignment_id
            for assignment_id, row in self._rows.items()
            if row["device_id"] == device_id
            and row["state"] in {AssignmentState.OFFERED, AssignmentState.CLAIMED}
            and row["expires_at"] > now
        ]
        for assignment_id in live:
            self._write(assignment_id, {**self._rows[assignment_id], "expires_at": now})
        return len(live)

    def _row(self, assignment_id: AssignmentId) -> dict[str, Any]:
        try:
            return self._rows[assignment_id]
        except KeyError:
            raise NotFoundError("assignment", assignment_id) from None

    def _movable(
        self,
        assignment_id: AssignmentId,
        device_id: DeviceId,
        state: AssignmentState,
        now: datetime,
    ) -> dict[str, Any]:
        """What a move's ``UPDATE`` asks of the row, in the port's order."""
        row = self._row(assignment_id)
        if row["device_id"] != device_id:
            raise AssignmentHeldElsewhereError(assignment_id, row["device_id"])
        if row["state"] is not state:
            raise AssignmentStateError(assignment_id, row["state"])
        if row["expires_at"] <= now:
            raise AssignmentExpiredError(assignment_id, row["expires_at"])
        return row

    def _write(self, assignment_id: AssignmentId, row: dict[str, Any]) -> Assignment:
        """The row, validated as an entity before it is kept: a move the entity refuses is not."""
        moved = Assignment.model_validate(row)
        self._rows[assignment_id] = row
        return moved


class FakeAuthorizationStore:
    """Grants by id, with a use counter each (port :class:`~ela.ports.AuthorizationStore`).

    **It keeps rows, as the SQL store does, and reads them back** — the shape of the fake of the
    assignments. A revocation writes ``revoked_at`` into the row and the read rebuilds the grant:
    nothing here coins or widens a grant (rule 15), and ``ela.testing`` imports nothing but the
    domain and the ports (contract 6) — so it cannot borrow a function of ``ela.permissions``
    (M13.12, ADR 0062)."""

    def __init__(self) -> None:
        self._rows: dict[AuthorizationId, dict[str, Any]] = {}
        self._uses: dict[AuthorizationId, int] = {}

    async def grant(self, authorization: Authorization) -> None:
        if authorization.id in self._rows:
            raise AlreadyExistsError("authorization", authorization.id)
        self._rows[authorization.id] = authorization.model_dump()
        self._uses[authorization.id] = 0

    async def get(self, authorization_id: AuthorizationId) -> Authorization:
        try:
            return Authorization.model_validate(self._rows[authorization_id])
        except KeyError:
            raise NotFoundError("authorization", authorization_id) from None

    async def for_capability(self, capability_id: CapabilityId) -> tuple[Authorization, ...]:
        return tuple(
            Authorization.model_validate(row)
            for row in self._rows.values()
            if row["capability_id"] == capability_id
        )

    async def uses(self, authorization_id: AuthorizationId) -> int:
        try:
            return self._uses[authorization_id]
        except KeyError:
            raise NotFoundError("authorization", authorization_id) from None

    async def revoke(self, authorization_id: AuthorizationId, *, at: datetime) -> Authorization:
        """Same rules as the SQL store: unknown, already revoked — the first instant stays —, or
        the instant written into the row, once."""
        grant = await self.get(authorization_id)
        if grant.revoked_at is not None:
            raise AuthorizationAlreadyRevokedError(authorization_id, grant.revoked_at)
        self._rows[authorization_id]["revoked_at"] = at
        return await self.get(authorization_id)

    async def consume(self, authorization_id: AuthorizationId, *, now: datetime) -> int:
        """Same rules as the SQL store, in the same order: unknown, revoked, expired, exhausted,
        count."""
        grant = await self.get(authorization_id)
        uses = self._uses[authorization_id]
        if grant.revoked_at is not None:
            raise AuthorizationRevokedError(authorization_id, grant.revoked_at)
        if grant.expires_at is not None and grant.expires_at <= now:
            raise AuthorizationExpiredError(authorization_id, grant.expires_at)
        if grant.max_uses is not None and uses >= grant.max_uses:
            raise AuthorizationExhaustedError(authorization_id, uses, grant.max_uses)
        self._uses[authorization_id] = uses + 1
        return uses + 1


class FakeApprovalStore:
    """Requests for consent by id, answered once (port :class:`~ela.ports.ApprovalStore`)."""

    def __init__(self) -> None:
        self._approvals: dict[ApprovalId, Approval] = {}

    async def add(self, approval: Approval) -> None:
        if approval.status is not ApprovalStatus.PENDING:
            raise ValueError(f"a request is added PENDING, not {approval.status.value}")
        if approval.id in self._approvals:
            raise AlreadyExistsError("approval", approval.id)
        self._approvals[approval.id] = approval

    async def get(self, approval_id: ApprovalId) -> Approval:
        try:
            return self._approvals[approval_id]
        except KeyError:
            raise NotFoundError("approval", approval_id) from None

    async def for_task(self, task_id: TaskId) -> tuple[Approval, ...]:
        return tuple(a for a in self._approvals.values() if a.task_id == task_id)

    async def pending(
        self, *, now: datetime | None = None, limit: int | None = None
    ) -> tuple[Approval, ...]:
        check_limit(limit)
        waiting = [
            approval
            for approval in self._approvals.values()
            if approval.status is ApprovalStatus.PENDING
            and not (
                now is not None and approval.expires_at is not None and approval.expires_at <= now
            )
        ]
        return tuple(waiting if limit is None else waiting[:limit])

    async def respond(
        self,
        approval_id: ApprovalId,
        *,
        status: ApprovalStatus,
        responded_by: str,
        now: datetime,
    ) -> Approval:
        """Same rules as the SQL store, in the same order: bad status, unknown, answered,
        expired, then the write."""
        check_answer(status)
        approval = await self.get(approval_id)
        if approval.status is not ApprovalStatus.PENDING:
            raise ApprovalAlreadyAnsweredError(approval_id, approval.status)
        if approval.expires_at is not None and approval.expires_at <= now:
            raise ApprovalExpiredError(approval_id, approval.expires_at)
        answered = approval.model_copy(
            update={"status": status, "responded_by": responded_by, "responded_at": now}
        )
        self._approvals[approval_id] = answered
        return answered


class FakeExecutionResultStore:
    """Results by id, insert-only (port :class:`~ela.ports.ExecutionResultStore`).

    Two refusals, as the port describes: a repeated id, and a second ``STARTED`` record for a
    step that already has one (ADR 0021 §1-bis).
    """

    def __init__(self) -> None:
        self._results: dict[ExecutionId, ExecutionResult] = {}

    async def add(self, result: ExecutionResult) -> None:
        # What the domain refuses is refused here too, as by the SQL store (M13.1c, ADR 0055): a
        # copy skips the validators, and a fake that kept it would pass what production fails.
        result = ExecutionResult.model_validate(result.model_dump())
        if result.id in self._results:
            raise AlreadyExistsError("execution result", result.id)
        if result.status is ExecutionStatus.STARTED and any(
            held.status is ExecutionStatus.STARTED
            and held.task_id == result.task_id
            and held.step_id == result.step_id
            for held in self._results.values()
        ):
            raise AlreadyExistsError("started record for step", result.step_id)
        self._results[result.id] = result

    async def get(self, result_id: ExecutionId) -> ExecutionResult:
        try:
            return self._results[result_id]
        except KeyError:
            raise NotFoundError("execution result", result_id) from None

    async def for_step(self, task_id: TaskId, step_id: StepId) -> tuple[ExecutionResult, ...]:
        return tuple(
            r for r in self._results.values() if r.task_id == task_id and r.step_id == step_id
        )

    async def for_task(self, task_id: TaskId) -> tuple[ExecutionResult, ...]:
        return tuple(r for r in self._results.values() if r.task_id == task_id)

    async def spending(self, since: datetime, until: datetime) -> tuple[ExecutionResult, ...]:
        """The period's reservations and what closes them, as the SQL store reads them."""
        reservations = [
            r
            for r in self._results.values()
            if r.status is ExecutionStatus.STARTED
            and r.worst_case is not None
            and since <= r.created_at < until
        ]
        ids = {str(r.id) for r in reservations}
        closing = [
            r
            for r in self._results.values()
            if r.status is not ExecutionStatus.STARTED and r.metadata.get(STARTED_ID) in ids
        ]
        return (*reservations, *closing)

    async def reserve(
        self,
        record: ExecutionResult,
        since: datetime,
        until: datetime,
        admits: Callable[[tuple[ExecutionResult, ...]], bool],
    ) -> bool:
        """The read and the insert with nothing between them that yields to the event loop: the
        fake's reads do not suspend, so one call is one step of the loop."""
        if not admits(await self.spending(since, until)):
            return False
        await self.add(record)
        return True


# --------------------------------------------------------------------------------------
# Capabilities, decisions and tools
# --------------------------------------------------------------------------------------


class FakeCapabilityRegistry:
    """Specifications by id, fixed at construction (:class:`~ela.ports.CapabilityRegistryPort`).

    Read-only like the port (ADR 0010): the specifications are given to the constructor, a
    duplicate id is an :class:`~ela.ports.AlreadyExistsError`, and nothing can be added later.
    Unlike the real registry it validates nothing else: a test may register a HIGH capability to
    see it denied.
    """

    def __init__(self, specs: Iterable[CapabilitySpec] = ()) -> None:
        catalogue: dict[CapabilityId, CapabilitySpec] = {}
        for spec in specs:
            if spec.id in catalogue:
                raise AlreadyExistsError("capability", spec.id)
            catalogue[spec.id] = spec
        self._specs: Mapping[CapabilityId, CapabilitySpec] = MappingProxyType(catalogue)

    def get(self, capability_id: CapabilityId) -> CapabilitySpec:
        try:
            return self._specs[capability_id]
        except KeyError:
            raise NotFoundError("capability", capability_id) from None

    def specs(self) -> tuple[CapabilitySpec, ...]:
        return tuple(self._specs.values())


class GuardianCall(NamedTuple):
    """What a :class:`FakePermissionGuardian` was asked, verbatim."""

    capability: CapabilitySpec
    arguments: JsonMapping
    task: Task | None
    step: TaskStep | None
    authorization: Authorization | None
    authorization_uses: int


class FakePermissionGuardian:
    """A Guardian driven by a table (port :class:`~ela.ports.PermissionGuardianPort`).

    ``outcomes`` maps a capability id to the outcome to return. Anything not in the table is
    ``DENIED`` with an explicit reason: the fail-safe of §33 holds in the fake as well, so a test
    that forgets to configure a capability sees a denial, never a silent permission.
    """

    def __init__(
        self,
        clock: Clock,
        ids: IdGenerator,
        *,
        outcomes: Mapping[CapabilityId, PermissionOutcome] | None = None,
    ) -> None:
        self._clock = clock
        self._ids = ids
        self._outcomes: dict[CapabilityId, PermissionOutcome] = dict(outcomes or {})
        self.calls: tuple[GuardianCall, ...] = ()

    def decide(
        self,
        capability: CapabilitySpec,
        arguments: JsonMapping,
        *,
        task: Task | None = None,
        step: TaskStep | None = None,
        authorization: Authorization | None = None,
        authorization_uses: int = 0,
    ) -> PermissionDecision:
        self.calls = (
            *self.calls,
            GuardianCall(capability, arguments, task, step, authorization, authorization_uses),
        )
        outcome = self._outcomes.get(capability.id)
        if outcome is None:
            outcome = PermissionOutcome.DENIED
            reason = f"no rule for {capability.id}: denied by default (§33)"
        else:
            reason = f"configured outcome for {capability.id}"
        return PermissionDecision(
            id=DecisionId(self._ids.new_uuid()),
            created_at=self._clock.now(),
            capability_id=capability.id,
            outcome=outcome,
            risk=capability.risk,
            reason=reason,
            task_id=None if task is None else task.id,
            step_id=None if step is None else step.id,
            authorization_id=None if authorization is None else authorization.id,
        )


class FakeStop:
    """The stop of a task as a tool sees it, scripted by the test (port ``TaskStop``, M6.3c).

    The two sides of a tool's point, built and never waited for: ``stopped=True`` is a task stopped
    **before** the point — :meth:`listen` raises ``ToolStopped`` and the port sees no effect —;
    ``after=<point>`` is a task stopped **right after** the tool passed it — the listening there
    goes through, and the stop is raised the instant after. ``listened`` is every place the tool
    listened at, in order: what a test reads to know the tool listened where it declared.
    """

    def __init__(self, *, stopped: bool = False, after: str | None = None) -> None:
        self.event = asyncio.Event()
        if stopped:
            self.event.set()
        self.after = after
        self.listened: list[str] = []

    def listen(self, where: str) -> None:
        self.listened.append(where)
        if self.event.is_set():
            raise ToolStopped(where)
        if where == self.after:
            self.event.set()

    def is_set(self) -> bool:
        return self.event.is_set()

    def stopped(self) -> Awaitable[object]:
        return self.event.wait()


class ToolCall(NamedTuple):
    """One execution a :class:`FakeTool` accepted."""

    decision: PermissionDecision
    arguments: JsonMapping


class FakeLauncher:
    """A launcher that launches nothing and remembers what it was handed (port ``CommandLauncher``).

    What a real child receives is asserted on real children
    (``tests/infrastructure/machine/test_launcher.py``); this is for the tests of the tool and of
    the executor, which need to know **what the tool decided** and **how many times it launched**.
    """

    def __init__(self, ran: Ran | None = None) -> None:
        self.ran = Ran(Ending.EXITED, code=0) if ran is None else ran
        self.commands: tuple[Command, ...] = ()

    async def run(self, command: Command, stop: TaskStop) -> Ran:
        """The command «starts» — it is remembered — and a stop of its task already raised ends it
        as the real launcher would, with the group stopped (M6.3c)."""
        self.commands = (*self.commands, command)
        if stop.is_set():
            return Ran(Ending.HALTED, signal=15)
        return self.ran


@dataclass
class FakePage:
    """What a :class:`FakeBrowser` page answers (M13.4): a script, not a browser.

    ``texts`` maps a selector to the text of its element, and ``None`` to the whole page's;
    ``counts`` how many elements a selector finds — one when it is not listed —; ``fields`` what an
    element declares; ``left`` a navigation the boundary refused at the opening,
    ``left_after_click`` one the click started; ``shown`` whether an awaited text appears, and
    ``changes_to`` the text the page shows once the tool is done with it, for the verifier's look.
    """

    status: int | None = 200
    address: str | None = None
    title: str = "a page"
    texts: dict[str | None, str] = field(default_factory=lambda: {None: "the text of the page"})
    counts: dict[str, int] = field(default_factory=dict)
    fields: dict[str, Field] = field(default_factory=dict)
    left: str | None = None
    left_after_click: str | None = None
    shown: bool = True
    changes_to: dict[str | None, str] | None = None


class FakeBrowser:
    """A browser that opens nothing and remembers what it was asked (port ``Browser``, M13.4).

    What a real browser does is asserted on a real browser
    (``tests/infrastructure/machine/test_browser.py``); this is for the tool, the verifiers, the
    executor and the API, which need to know **what the tool decided** — the address, the boundary,
    each gesture — and to answer **when the test decides**. ``raising`` makes one member raise the
    given error; ``click_reached`` and ``click_released``, when set, hold the click until the test
    lets it go — the precondition of a stop given halfway, built instead of waited for.
    """

    def __init__(self, page: FakePage | None = None, *, installed: bool = True) -> None:
        self.page = FakePage() if page is None else page
        self.installed_answer = installed
        self.raising: dict[str, BrowserError] = {}
        self.opened: list[str] = []
        self.allowed: list[Callable[[str], bool]] = []
        self.fills: list[tuple[str, str]] = []
        self.clicks: list[str] = []
        self.kept: list[str] = []
        self.closed: list[str] = []
        self.glances: list[tuple[str, str | None, str | None, float]] = []
        self.click_reached: asyncio.Event | None = None
        self.click_released: asyncio.Event | None = None
        self.launch_reached: asyncio.Event | None = None
        self.launch_released: asyncio.Event | None = None
        """Held, when set, while «the browser starts» — before the navigation and its listening
        (M6.3c): the window where a stop finds the site not yet visited."""
        self._open: dict[str, bool] = {}
        self._clicked = False

    def _raise(self, member: str) -> None:
        error = self.raising.get(member)
        if error is not None:
            raise error

    def _on(self, page: str) -> None:
        if page not in self._open:
            raise PageGone(page)

    async def installed(self) -> bool:
        self._raise("installed")
        return self.installed_answer

    async def open(self, address: str, allowed: Callable[[str], bool], stop: TaskStop) -> Opened:
        self._raise("open")
        if self.launch_reached is not None and self.launch_released is not None:
            self.launch_reached.set()
            await self.launch_released.wait()
        stop.listen(NAVIGATION)
        self.opened.append(address)
        self.allowed.append(allowed)
        page = f"page-{len(self.opened)}"
        self._open[page] = False
        return Opened(
            page=page,
            status=self.page.status,
            address=address if self.page.address is None else self.page.address,
            left=self.page.left,
        )

    async def count(self, page: str, selector: str) -> int:
        self._on(page)
        self._raise("count")
        return self.page.counts.get(selector, 1)

    async def field(self, page: str, selector: str) -> Field:
        self._on(page)
        return self.page.fields.get(selector, Field(type="text", autocomplete=""))

    async def fill(self, page: str, selector: str, value: str) -> None:
        self._on(page)
        self._raise("fill")
        self.fills.append((selector, value))

    async def click(self, page: str, selector: str) -> None:
        self._on(page)
        if self.click_reached is not None and self.click_released is not None:
            self.click_reached.set()
            await self.click_released.wait()
        self._raise("click")
        self.clicks.append(selector)
        self._clicked = True

    async def text(self, page: str, selector: str | None) -> str:
        self._on(page)
        self._raise("text")
        return self.page.texts.get(selector, "")

    async def title(self, page: str) -> str:
        self._on(page)
        return self.page.title

    async def left(self, page: str) -> str | None:
        self._on(page)
        return self.page.left_after_click if self._clicked else self.page.left

    async def keep(self, page: str) -> None:
        if page in self._open:
            self._open[page] = True
            self.kept.append(page)

    async def glance(
        self, page: str, *, selector: str | None, expect: str | None, seconds: float
    ) -> Glanced:
        self.glances.append((page, selector, expect, seconds))
        self._raise("glance")
        if not self._open.get(page, False):
            raise PageGone(page)
        del self._open[page]
        texts = self.page.texts if self.page.changes_to is None else self.page.changes_to
        return Glanced(
            text=texts.get(selector) if selector in texts else None,
            shown=None if expect is None else self.page.shown,
            left=self.page.left_after_click if self._clicked else self.page.left,
        )

    async def close(self, page: str) -> None:
        self.closed.append(page)
        self._open.pop(page, None)

    def stop(self) -> None:
        """What the stop signal does to a real one: every page closed, and what runs is stopped."""
        self._open.clear()
        for member in ("open", "count", "fill", "click", "text", "glance", "installed"):
            self.raising[member] = BrowserStopped("ELA is stopping")


class FakeTool:
    """A tool that returns a fixed result once the decision allows it (port :class:`ToolPort`).

    The check comes first and is the contract of every tool: a decision that is not ``ALLOWED``,
    is for another capability or has expired raises :class:`~ela.ports.NotAllowedError` and leaves
    ``calls`` untouched. A decision expiring at this very instant is already expired.
    """

    def __init__(
        self,
        capability_id: CapabilityId,
        clock: Clock,
        ids: IdGenerator,
        *,
        name: str = "fake-tool",
        output: JsonMapping | None = None,
        status: ExecutionStatus = ExecutionStatus.SUCCEEDED,
        idempotent: bool = True,
        relocatable: bool | None = None,
        prospect: Prospect | None = None,
        usage: ProviderUsage | None = None,
        audit_numbers: frozenset[str] = frozenset(),
        stop_point: StopPoint | None = None,
        error: ErrorMetadata | None = None,
    ) -> None:
        self._capability_id = capability_id
        self._clock = clock
        self._ids = ids
        self._name = name
        self.stop_point = StopPoint(here=None, on_a_node=None) if stop_point is None else stop_point
        """Where it listens for the stop of its task (M6.3c): nowhere — its point is the call —,
        unless a test gives it a point, and then it listens there before it «acts»."""
        self.idempotent = idempotent
        """Whether twice is once (ADR 0015 §8, ADR 0021 §1): ``False`` is how a test builds a
        tool the executor must run under the STARTED protocol."""
        self._relocatable = relocatable
        self.audit_numbers = audit_numbers
        """What of its result enters ``TOOL_EXECUTED`` (M13.2): nothing, unless a test says so."""
        self.output: JsonMapping = {} if output is None else output
        """What the tool answers with, settable so a test can put a number or a string in it."""
        self._status = status
        self._error = error
        """What it reports with a status that did not succeed (M13.1c): the test's, or one of its
        own — a result that did not succeed says why, or the domain does not build it (§64)."""
        self._usage = usage
        self.calls: tuple[ToolCall, ...] = ()
        self.prospects = Prospect() if prospect is None else prospect
        self.assertions = Prospect()
        self.bound: WorstCase | ErrorMetadata | None = None

    @property
    def capability_id(self) -> CapabilityId:
        return self._capability_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def relocatable(self) -> bool:
        """Whether a node's expired claim is placed again (M13.3, ADR 0048): what the test says,
        or else what :attr:`idempotent` says **now** — the one predicate the claim read before
        M13.3, so a test that turns ``idempotent`` off after building the world keeps meaning
        what it meant. A test that wants the two apart sets this."""
        return self.idempotent if self._relocatable is None else self._relocatable

    @relocatable.setter
    def relocatable(self, value: bool) -> None:
        self._relocatable = value

    async def prospect(self, arguments: JsonMapping) -> Prospect:
        """Whatever the test set: nothing to show and nothing to refuse, by default."""
        return self.prospects

    async def asserted(self, arguments: JsonMapping) -> Prospect:
        """What the call asserts without looking (M13.3): whatever the test set, empty by
        default — and never what :attr:`prospects` says, so a test sees which one was asked."""
        return self.assertions

    async def worst_case(self, arguments: JsonMapping) -> WorstCase | ErrorMetadata | None:
        """What the test set in :attr:`bound`: ``None`` — a tool that spends nothing — by default
        (M14.1)."""
        return self.bound

    async def execute(
        self, decision: PermissionDecision, arguments: JsonMapping, stop: TaskStop
    ) -> ExecutionResult:
        if decision.capability_id != self._capability_id:
            raise NotAllowedError(
                self._capability_id, f"the decision is about {decision.capability_id}"
            )
        if decision.outcome is not PermissionOutcome.ALLOWED:
            raise NotAllowedError(self._capability_id, f"outcome is {decision.outcome.value}")
        if decision.expires_at is not None and decision.expires_at <= self._clock.now():
            raise NotAllowedError(self._capability_id, f"decision expired at {decision.expires_at}")
        if self.stop_point.here is not None:
            stop.listen(self.stop_point.here)
        self.calls = (*self.calls, ToolCall(decision, arguments))
        return ExecutionResult(
            id=ExecutionId(self._ids.new_uuid()),
            created_at=self._clock.now(),
            capability_id=self._capability_id,
            status=self._status,
            task_id=decision.task_id,
            step_id=decision.step_id,
            tool_name=self._name,
            output=self.output,
            error=self._failure(),
            usage=self._usage,
            duration_ms=0,
        )

    def _failure(self) -> ErrorMetadata | None:
        if self._status in (ExecutionStatus.SUCCEEDED, ExecutionStatus.STARTED):
            return None
        if self._error is not None:
            return self._error
        return ErrorMetadata(
            code=f"fake.{self._status.value.lower()}",
            message=f"{self._name} reported {self._status.value}",
            tool_name=self._name,
        )


class FakeToolRegistry:
    """Tools by capability id, fixed at construction (port :class:`~ela.ports.ToolRegistryPort`).

    The key is the tool's own ``capability_id``; a second tool for the same capability is an
    :class:`~ela.ports.AlreadyExistsError`, and nothing can be added later.
    """

    def __init__(self, tools: Iterable[ToolPort] = ()) -> None:
        table: dict[CapabilityId, ToolPort] = {}
        for tool in tools:
            if tool.capability_id in table:
                raise AlreadyExistsError("tool", tool.capability_id)
            table[tool.capability_id] = tool
        self._tools: Mapping[CapabilityId, ToolPort] = MappingProxyType(table)

    def get(self, capability_id: CapabilityId) -> ToolPort:
        try:
            return self._tools[capability_id]
        except KeyError:
            raise NotFoundError("tool", capability_id) from None

    def tools(self) -> tuple[ToolPort, ...]:
        return tuple(self._tools.values())


# --------------------------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------------------------


class VerifierCall(NamedTuple):
    """One verification a :class:`FakeVerifier` was asked, verbatim."""

    conditions: tuple[str, ...]
    arguments: JsonMapping
    result: ExecutionResult


class FakeVerifier:
    """A verifier that answers from a table of failures (port :class:`~ela.ports.VerifierPort`).

    ``conditions`` is its vocabulary; ``failures`` maps a condition to the failure it reports
    (any other known condition holds). The preconditions of the contract come first, as for
    every verifier: another capability, a result that did not succeed, no condition or an
    unknown one are failures with the codes of :func:`~ela.ports.check_verifiable`. Every call
    is recorded in ``calls``, whatever it answered; nothing is ever written anywhere.
    """

    def __init__(
        self,
        capability_id: CapabilityId,
        *,
        name: str = "fake-verifier",
        conditions: Iterable[str] = (FAKE_CONDITION,),
        failures: Mapping[str, ErrorMetadata] | None = None,
        reads_the_machine: bool = False,
    ) -> None:
        self._capability_id = capability_id
        self._name = name
        self._conditions = frozenset(conditions)
        self.reads_the_machine = reads_the_machine
        """Declared like every verifier's (ADR 0038 §14); a fake reads nothing, unless told."""
        self._failures: Mapping[str, ErrorMetadata] = MappingProxyType(
            {} if failures is None else dict(failures)
        )
        self.failure_codes: frozenset[str] = frozenset(
            {
                VERIFICATION_WRONG_CAPABILITY,
                VERIFICATION_NOT_SUCCEEDED,
                VERIFICATION_NO_CONDITIONS,
                VERIFICATION_UNKNOWN_CONDITION,
            }
        ) | {failure.code for failure in self._failures.values()}
        """Its vocabulary of failures (ADR 0014 §2): the contract's codes and its table's."""
        unknown = set(self._failures) - self._conditions
        if unknown:
            raise ValueError(f"failures for conditions outside the vocabulary: {sorted(unknown)}")
        self.calls: tuple[VerifierCall, ...] = ()

    @property
    def capability_id(self) -> CapabilityId:
        return self._capability_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def conditions(self) -> frozenset[str]:
        return self._conditions

    async def verify(
        self, conditions: Sequence[str], arguments: JsonMapping, result: ExecutionResult
    ) -> tuple[ErrorMetadata, ...]:
        self.calls = (*self.calls, VerifierCall(tuple(conditions), arguments, result))
        refused = check_verifiable(self._capability_id, self._conditions, conditions, result)
        if refused:
            return refused
        return tuple(
            self._failures[condition].model_copy(
                update={"details": {**self._failures[condition].details, "condition": condition}}
            )
            for condition in conditions
            if condition in self._failures
        )


class FakeVerifierRegistry:
    """Verifiers by capability id, fixed at construction (port
    :class:`~ela.ports.VerifierRegistryPort`), keyed like :class:`FakeToolRegistry`."""

    def __init__(self, verifiers: Iterable[VerifierPort] = ()) -> None:
        table: dict[CapabilityId, VerifierPort] = {}
        for verifier in verifiers:
            if verifier.capability_id in table:
                raise AlreadyExistsError("verifier", verifier.capability_id)
            table[verifier.capability_id] = verifier
        self._verifiers: Mapping[CapabilityId, VerifierPort] = MappingProxyType(table)

    def get(self, capability_id: CapabilityId) -> VerifierPort:
        try:
            return self._verifiers[capability_id]
        except KeyError:
            raise NotFoundError("verifier", capability_id) from None

    def verifiers(self) -> tuple[VerifierPort, ...]:
        return tuple(self._verifiers.values())


# --------------------------------------------------------------------------------------
# Model providers
# --------------------------------------------------------------------------------------


FAKE_CURRENCY: Final = "USD"
FAKE_WORST_CASE: Final = Decimal("0.01")
"""What a :class:`FakeModelProvider` reserves for a call unless a test says otherwise: one cent."""


class FakeModelProvider:
    """A provider that answers from a canned reply (port :class:`~ela.ports.ModelProvider`).

    ``reply`` is a string or a function of the request. ``usage`` counts words, deterministically.
    With ``error`` set, every result carries that error and an empty output, which is how a real
    provider reports a failure (a result, not an exception). ``status`` says whether the provider
    is configured at all (ADR 0020 §2); an ``UNAVAILABLE`` fake answers with
    :data:`~ela.ports.PROVIDER_UNAVAILABLE`, says it sent nothing, and records no request, as the
    real one does.

    ``cost`` is what every answered call reports it cost, ``None`` by default — a model with no
    price. ``finish_reason`` is what an answer that did not fail reports, ``end_turn`` by default:
    ``max_tokens`` is how a test says the answer was cut (M14.2). ``worst`` is what
    :meth:`worst_case` answers (M14.1): a bound of one cent by default, or the error a test wants;
    it is asked without the network, so it records nothing.
    """

    def __init__(
        self,
        clock: Clock,
        ids: IdGenerator,
        *,
        name: str = "fake",
        reply: str | Callable[[ProviderRequest], str] = "ok",
        error: ErrorMetadata | None = None,
        status: ProviderStatus = ProviderStatus.AVAILABLE,
        cost: Decimal | None = None,
        worst: WorstCase | ErrorMetadata | None = None,
        finish_reason: str = "end_turn",
    ) -> None:
        self._clock = clock
        self._ids = ids
        self._name = name
        self._reply = reply
        self._finish_reason = finish_reason
        self._error = error
        self._status = status
        self._cost = cost
        self._worst = worst
        self.requests: tuple[ProviderRequest, ...] = ()

    @property
    def name(self) -> str:
        return self._name

    @property
    def status(self) -> ProviderStatus:
        return self._status

    async def complete(self, request: ProviderRequest) -> ProviderResult:
        if self._status is ProviderStatus.UNAVAILABLE:
            return self._unusable(request)
        self.requests = (*self.requests, request)
        if self._error is not None:
            output = ""
        elif callable(self._reply):
            output = self._reply(request)
        else:
            output = self._reply
        prompt_words = len(request.input.split()) + len((request.instructions or "").split())
        return ProviderResult(
            id=ProviderResultId(self._ids.new_uuid()),
            created_at=self._clock.now(),
            request_id=request.id,
            provider=self._name,
            model=f"{self._name}-model",
            output=output,
            usage=ProviderUsage(
                input_tokens=prompt_words,
                output_tokens=len(output.split()),
                cost=self._cost,
                currency=None if self._cost is None else FAKE_CURRENCY,
            ),
            finish_reason="error" if self._error is not None else self._finish_reason,
            error=self._error,
        )

    async def worst_case(self, request: ProviderRequest) -> WorstCase | ErrorMetadata:
        """What the test set, or one cent on this fake's model: never the network."""
        if self._worst is not None:
            return self._worst
        return WorstCase(
            amount=FAKE_WORST_CASE,
            currency=FAKE_CURRENCY,
            model=f"{self._name}-model",
            input_tokens=1_000,
            output_tokens=100,
        )

    def _unusable(self, request: ProviderRequest) -> ProviderResult:
        """What every provider answers when it is not configured (ADR 0020 §2): no work done."""
        return ProviderResult(
            id=ProviderResultId(self._ids.new_uuid()),
            created_at=self._clock.now(),
            request_id=request.id,
            provider=self._name,
            model="",
            output="",
            usage=ProviderUsage(input_tokens=0, output_tokens=0, sent=False),
            error=ErrorMetadata(
                code=PROVIDER_UNAVAILABLE,
                message=f"provider {self._name} is not configured",
                retryable=False,
            ),
        )


class FakeProviderRegistry:
    """Providers by name (port :class:`~ela.ports.ProviderRegistryPort`)."""

    def __init__(self) -> None:
        self._providers: dict[str, ModelProvider] = {}

    def register(self, provider: ModelProvider) -> None:
        if provider.name in self._providers:
            raise AlreadyExistsError("provider", provider.name)
        self._providers[provider.name] = provider

    def get(self, name: str) -> ModelProvider:
        try:
            return self._providers[name]
        except KeyError:
            raise NotFoundError("provider", name) from None

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))


class FakeModelRouter:
    """A router that always chooses the same provider (port ``ModelRouterPort``).

    Honours ``model_hint`` over ``profile`` the way the real one does (ADR 0022 §3), so a test of
    the tool can prove the hint wins without building a policy. With ``error`` set every call
    raises it, which is how a test reaches the branches where nothing is sent: an unknown task
    type, a route with no usable provider.

    ``calls`` records ``(task_type, model_hint)`` per call, so a test can assert that the tool
    asked what the arguments said and not what it preferred.
    """

    def __init__(
        self,
        *,
        provider: str = "fake",
        profile: str = "balanced",
        skipped: tuple[str, ...] = (),
        error: RoutingError | None = None,
    ) -> None:
        self._provider = provider
        self._profile = profile
        self._skipped = skipped
        self._error = error
        self.calls: tuple[tuple[str | None, str | None], ...] = ()

    def route(self, task_type: str | None, model_hint: str | None) -> ModelRoute:
        self.calls = (*self.calls, (task_type, model_hint))
        if self._error is not None:
            raise self._error
        return ModelRoute(
            task_type=task_type,
            provider=self._provider,
            profile=model_hint if model_hint else self._profile,
            skipped=self._skipped,
        )


class FakeProbe:
    """A :class:`~ela.ports.PerceptionProbe` that answers whatever the test wrote down.

    ``answers`` is consumed one reading at a time and the last one repeats, so a test can say
    "first the microphone is idle, then it is in use" without driving a clock. ``calls`` records
    the families each read asked for — the question the cadence scheduler gets right or wrong.

    Honours the port's promise not to raise: a test that wants a broken probe uses
    :attr:`fails`, and even then the failure is the caller's to see, not this fake's to invent.
    """

    __slots__ = ("_answers", "calls", "fails")

    def __init__(
        self, answers: Sequence[RawObservation] | None = None, *, fails: bool = False
    ) -> None:
        self._answers = list(answers or [RawObservation()])
        self.calls: tuple[frozenset[ProbeFamily], ...] = ()
        self.fails = fails

    async def read(self, families: frozenset[ProbeFamily]) -> RawObservation:
        """The next answer; the last one repeats once the list runs out."""
        self.calls = (*self.calls, families)
        if self.fails:
            raise RuntimeError("the probe broke its contract")
        return self._answers.pop(0) if len(self._answers) > 1 else self._answers[0]


class FakeSpeech:
    """A :class:`~ela.ports.SpeechPort` that says nothing and reports what the test wrote down.

    ``report`` is how the helper ended; ``there`` is whether this machine has a voice at all.

    ``said`` records every sentence it was asked for, and it is what proves the two properties
    the milestone rests on: **when the voice is switched off, this is never called**, and when it
    is called it is called with the text that was asked for and nothing else. A test asserts an
    empty ``said``, not the absence of a sound — no runner has ears, so not attempting to speak
    is the behaviour, and behaviour is only tested by watching for it.

    ``spoken_seconds`` defaults to a duration long enough for any text a test uses, because the
    verifier's floor is a real check and a fake that reported zero would fail it for the wrong
    reason. A test that wants that failure passes its own ``report``.

    Honours the port's promise not to raise: a helper that dies reports how, it does not throw.
    """

    __slots__ = ("_report", "said", "there")

    def __init__(self, *, report: RawSpeech | None = None, there: bool = True) -> None:
        self._report = report if report is not None else RawSpeech(exit_code=0, spoken_seconds=60.0)
        self.there = there
        self.said: tuple[str, ...] = ()

    async def available(self) -> bool:
        return self.there

    async def speak(self, text: str) -> RawSpeech:
        """Record what was asked, make no sound, and report."""
        self.said = (*self.said, text)
        return self._report


class FakePower:
    """What this machine runs on, as the test wrote it down (a ``PowerReading`` of the composition).

    ``source`` is the answer, and a test changes it between two calls to unplug the machine;
    ``asked`` counts the readings, which is what proves the property M12.3c rests on: the power
    source is read at every heartbeat and never kept from an earlier one. ``UNKNOWN`` unless told
    otherwise, which is what every node and ``local`` were before M12.3c.
    """

    __slots__ = ("asked", "source")

    def __init__(self, source: PowerSource = PowerSource.UNKNOWN) -> None:
        self.source = source
        self.asked = 0

    async def __call__(self) -> PowerSource:
        self.asked += 1
        return self.source


class FakeLocalBeat:
    """A heartbeat of ``local`` that is counted and lands nowhere (:class:`~ela.ports.LocalBeat`).

    Since M13.3 the runner asks for a beat before every placement, so ``local`` is alive whenever
    it is about to be chosen. A test about what the runner does when **no node is eligible** —
    which stays reachable for a node that is not this machine, or for a capability no node has —
    declares this beat to build the precondition with the one node of its world; ``beats`` counts
    what was asked, which is what proves the runner asks before every ``place`` and ``confirm``.
    """

    __slots__ = ("beats",)

    def __init__(self) -> None:
        self.beats = 0

    async def beat(self) -> None:
        self.beats += 1


class FakeListening:
    """A :class:`~ela.ports.ListeningPort` that hears whatever the test wrote down.

    ``report`` is the transcript it hands back; ``there`` is whether this machine can listen at
    all.

    ``asked`` records every duration it was called with, and that is what proves the property the
    milestone rests on: **when the permission is denied, this is never called.** A test asserts an
    empty ``asked``, not the absence of a recording — attempting from a denied state is how a
    permanent refusal gets recorded in the operating system (ADR 0029 §7), and worse here, since
    opening a refused microphone succeeds and hands back silence that a transcriber turns into
    words nobody said. Not attempting is the behaviour, and behaviour is only tested by watching
    for it.

    The default report carries a peak above zero: a fake that reported silence would send every
    test down the ``listen.no_signal`` path for the wrong reason. A test that wants that path
    passes its own ``report``.

    Honours the port's promise not to raise: a helper that dies reports how, it does not throw.
    """

    __slots__ = ("_report", "asked", "there")

    def __init__(self, *, report: RawTranscript | None = None, there: bool = True) -> None:
        self._report = (
            report
            if report is not None
            else RawTranscript(
                exit_code=0,
                recorded_seconds=3.0,
                peak=3330,
                language="it",
                segments=(
                    RawHeardSegment(
                        text=" Ela, sposta la call di domani.", start_ms=0, end_ms=1840
                    ),
                ),
            )
        )
        self.there = there
        self.asked: tuple[int, ...] = ()

    async def available(self) -> bool:
        return self.there

    async def listen(self, seconds: int) -> RawTranscript:
        """Record what was asked, open nothing, and report."""
        self.asked = (*self.asked, seconds)
        return self._report


class FakeScreenCapture:
    """A :class:`~ela.ports.ScreenCapturePort` that writes whatever the test wrote down.

    ``payload`` is the bytes the helper "captures" — a valid PNG header for a success, junk or
    ``None`` for the failures a real helper produces: exited zero and wrote nothing, exited zero
    and wrote something that is not an image. ``report`` is how it ended.

    ``calls`` records every ``(destination, display)`` it was asked for, and that is what proves
    the property the milestone rests on: **when the permission is missing, this is never called.**
    A test asserts an empty ``calls``, not the absence of a file — attempting the capture is what
    records a permanent denial in the operating system, so not attempting it is the behaviour, and
    behaviour is only tested by watching for it.

    Honours the port's promise not to raise: a helper that dies reports how, it does not throw.
    """

    __slots__ = ("_payload", "_report", "calls", "there")

    def __init__(
        self,
        *,
        payload: bytes | None = None,
        report: RawCapture | None = None,
        there: bool = True,
    ) -> None:
        self._payload = payload
        self._report = report if report is not None else RawCapture(exit_code=0)
        self.there = there
        self.calls: tuple[tuple[str, int], ...] = ()

    async def available(self) -> bool:
        return self.there

    async def capture(self, destination: str, display: int) -> RawCapture:
        """Record the call, write ``payload`` if there is one, and report."""
        self.calls = (*self.calls, (destination, display))
        if self._payload is not None:
            Path(destination).write_bytes(self._payload)
        return self._report


class FakeTextRecognition:
    """A :class:`~ela.ports.TextRecognitionPort` that reports whatever the test wrote down.

    ``calls`` records every ``(source, languages, region)``, and it is what proves the two
    properties this tool rests on: that **nothing is recognised when the image is not whole** — a
    truncated PNG makes the real framework answer successfully with zero lines, so refusing before
    the call is the behaviour, and a behaviour is only tested by watching for it — and that the
    region reaching the framework is the *flipped* one, since a rectangle that is upside down does
    not raise, it reads the wrong half of the screen.

    Honours the port's promise not to raise: a helper that dies reports how, it does not throw.
    """

    __slots__ = ("_report", "calls", "there")

    def __init__(self, *, report: RawRecognition | None = None, there: bool = True) -> None:
        self._report = report if report is not None else RawRecognition(exit_code=0)
        self.there = there
        self.calls: tuple[tuple[str, tuple[str, ...], tuple[float, ...] | None], ...] = ()

    async def available(self) -> bool:
        return self.there

    async def recognise(
        self, source: str, *, languages: tuple[str, ...], region: tuple[float, ...] | None
    ) -> RawRecognition:
        """Record the call and report."""
        self.calls = (*self.calls, (source, languages, region))
        return self._report


# --------------------------------------------------------------------------------------
# The guided session of the browser (M14.3, ADR 0060)
# --------------------------------------------------------------------------------------

FAKE_CALL_WORST: Final = Decimal("0.01")
"""The worst case of one call of a session to the fake model, whatever its ``max_tokens``."""

FAKE_SESSION_TOOLS: Final = frozenset({"mcp__ela__act", "mcp__ela__read"})
"""The two tools a session offers, by the names Claude Code gives them."""


def _cost_of(body: bytes) -> ProviderUsage:
    return ProviderUsage(
        input_tokens=len(body) // 4,
        output_tokens=10,
        cost=Decimal("0.0001"),
        currency=FAKE_CURRENCY,
        request_bytes=len(body),
    )


class FakeModelGateway:
    """Implements :class:`~ela.ports.ModelGateway` with nothing leaving the machine: every call it
    is handed answers a scripted stream, and is counted in :attr:`forwarded` — the fake provider
    that «counts zero» when a session is refused before the network."""

    def __init__(
        self,
        *,
        prices: Mapping[str, Decimal] | None = None,
        status: int = 200,
        chunks: Sequence[bytes] = (b"event: message_stop\ndata: {}\n\n",),
        usage: Callable[[bytes], ProviderUsage | None] = _cost_of,
    ) -> None:
        self.forwarded: list[tuple[Admission, bytes, str | None]] = []
        self._prices = {"fake-model": FAKE_CALL_WORST} if prices is None else dict(prices)
        self._status = status
        self._chunks = tuple(chunks)
        self._usage = usage

    async def read(self, body: bytes) -> CallRequest:
        try:
            data = json.loads(body)
        except ValueError:
            data = None
        if not isinstance(data, dict):
            return CallRequest(None, None, None, cached=False, request_bytes=len(body))
        tools = data.get("tools")
        model, max_tokens = data.get("model"), data.get("max_tokens")
        return CallRequest(
            model=model if isinstance(model, str) else None,
            max_tokens=max_tokens if type(max_tokens) is int else None,
            tools=(
                tuple(str(one.get("name")) for one in tools if isinstance(one, dict))
                if isinstance(tools, list)
                else None
            ),
            cached="cache_control" in body.decode(errors="replace"),
            request_bytes=len(body),
        )

    async def worst(self, model: str, max_tokens: int) -> Decimal | None:
        return self._prices.get(model)

    async def forward(self, admission: Admission, body: bytes, beta: str | None) -> Forwarded:
        self.forwarded.append((admission, body, beta))
        chunks = self._chunks
        usage = self._usage(body)

        async def answer() -> AsyncIterator[bytes]:
            for chunk in chunks:
                yield chunk

        return Forwarded(
            status=self._status,
            content_type="text/event-stream",
            chunks=answer(),
            usage=lambda: usage,
        )


SessionScript = Callable[[SessionPlan, SessionHost], Awaitable[SessionEnd]]
"""What a fake session does instead of a model: given the plan and the host, it calls back —
``started``, ``gesture``, ``asked`` — and says how it ended."""


def finished(text: str = "done", subtype: str = "success") -> SessionEnd:
    """How a fake session ends: its last text, and the subtype of its end."""
    return SessionEnd(
        text=text, subtype=subtype, reported_cost="0", version="fake", denials=0, closed=True
    )


async def _starts_and_ends(plan: SessionPlan, host: SessionHost) -> SessionEnd:
    """The default script: the two tools at the start, and the turn ended."""
    refused = await host.started(tuple(sorted(FAKE_SESSION_TOOLS)))
    if refused is not None:
        return finished("", "error_during_execution")
    return finished()


class FakeAgentSession:
    """Implements :class:`~ela.ports.AgentSession` with a script instead of Claude Code.

    It records every launch and every interrupt; an interrupt cancels the script and ends the
    session ``error_during_execution``, as Claude Code ends a turn it was interrupted in."""

    def __init__(
        self,
        script: SessionScript = _starts_and_ends,
        *,
        unready: ErrorMetadata | None = None,
        refused: ErrorMetadata | None = None,
        left_running: bool = False,
        held: asyncio.Event | None = None,
    ) -> None:
        self.launched: list[tuple[Reservation, SessionPlan]] = []
        self.held = held
        """When set, an interrupt waits for it before it reaches the script: the session stays
        open in the room for as long as the test holds it."""
        self.interrupted: list[StepId] = []
        self.swept = 0
        """How many times the start-up swept the folders of the sessions."""
        self._script = script
        self._unready = unready
        self._refused = refused
        self._left_running = left_running
        self._alive: set[StepId] = set()

    @property
    def tools(self) -> frozenset[str]:
        return FAKE_SESSION_TOOLS

    async def ready(self) -> ErrorMetadata | None:
        return self._unready

    async def running(self, session: StepId) -> bool:
        return session in self._alive

    async def sweep(self) -> int:
        self.swept += 1
        return 0

    async def launch(
        self, reservation: Reservation, plan: SessionPlan, host: SessionHost
    ) -> SessionHandle | ErrorMetadata:
        if self._refused is not None:
            return self._refused
        self.launched.append((reservation, plan))
        self._alive.add(plan.session)
        interrupted = asyncio.Event()

        async def run() -> SessionEnd:
            work = asyncio.ensure_future(self._script(plan, host))
            stop = asyncio.ensure_future(interrupted.wait())
            try:
                await asyncio.wait((work, stop), return_when=asyncio.FIRST_COMPLETED)
                if work.done():
                    return work.result()
                work.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await work
                return finished("", "error_during_execution")
            finally:
                stop.cancel()
                if not self._left_running:
                    self._alive.discard(plan.session)

        async def interrupt() -> None:
            self.interrupted.append(plan.session)
            if self.held is not None:
                await self.held.wait()
            interrupted.set()

        return SessionHandle(ended=asyncio.ensure_future(run()), interrupt=interrupt)
