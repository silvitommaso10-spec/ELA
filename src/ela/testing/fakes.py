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

from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Final, NamedTuple
from uuid import UUID

from ela.domain import (
    AuditEvent,
    Authorization,
    AuthorizationId,
    CapabilityId,
    CapabilitySpec,
    DecisionId,
    Device,
    DeviceId,
    ErrorMetadata,
    ExecutionId,
    ExecutionResult,
    ExecutionStatus,
    JsonMapping,
    PermissionDecision,
    PermissionOutcome,
    ProviderRequest,
    ProviderResult,
    ProviderResultId,
    ProviderUsage,
    Task,
    TaskEvent,
    TaskEventId,
    TaskId,
    TaskState,
    TaskStep,
)
from ela.ports import (
    AlreadyExistsError,
    Clock,
    IdGenerator,
    ModelProvider,
    NotAllowedError,
    NotFoundError,
)

__all__ = [
    "DEFAULT_START",
    "FakeAuditLog",
    "FakeAuthorizationStore",
    "FakeCapabilityRegistry",
    "FakeClock",
    "FakeDeviceRegistry",
    "FakeIdGenerator",
    "FakeModelProvider",
    "FakePermissionGuardian",
    "FakeProviderRegistry",
    "FakeTaskRepository",
    "FakeTool",
    "GuardianCall",
    "ToolCall",
]

DEFAULT_START: Final = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
"""Where a :class:`FakeClock` starts unless told otherwise."""


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
    """Tasks and their events in two dictionaries (port :class:`~ela.ports.TaskRepository`)."""

    def __init__(self) -> None:
        self._tasks: dict[TaskId, Task] = {}
        self._events: dict[TaskId, tuple[TaskEvent, ...]] = {}
        self._event_ids: set[TaskEventId] = set()

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
        selected = (t for t in self._tasks.values() if states is None or t.state in states)
        return tuple(selected)[:limit]

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
    ) -> tuple[AuditEvent, ...]:
        selected = (
            event
            for event in self._events
            if (task_id is None or event.task_id == task_id)
            and (since is None or event.created_at >= since)
        )
        return tuple(selected)[:limit]


class FakeDeviceRegistry:
    """Nodes by id (port :class:`~ela.ports.DeviceRegistryPort`)."""

    def __init__(self) -> None:
        self._devices: dict[DeviceId, Device] = {}

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


class FakeAuthorizationStore:
    """Grants by id, with a use counter each (port :class:`~ela.ports.AuthorizationStore`)."""

    def __init__(self) -> None:
        self._grants: dict[AuthorizationId, Authorization] = {}
        self._uses: dict[AuthorizationId, int] = {}

    async def grant(self, authorization: Authorization) -> None:
        if authorization.id in self._grants:
            raise AlreadyExistsError("authorization", authorization.id)
        self._grants[authorization.id] = authorization
        self._uses[authorization.id] = 0

    async def get(self, authorization_id: AuthorizationId) -> Authorization:
        try:
            return self._grants[authorization_id]
        except KeyError:
            raise NotFoundError("authorization", authorization_id) from None

    async def for_capability(self, capability_id: CapabilityId) -> tuple[Authorization, ...]:
        return tuple(a for a in self._grants.values() if a.capability_id == capability_id)

    async def uses(self, authorization_id: AuthorizationId) -> int:
        try:
            return self._uses[authorization_id]
        except KeyError:
            raise NotFoundError("authorization", authorization_id) from None

    async def record_use(self, authorization_id: AuthorizationId) -> int:
        if authorization_id not in self._uses:
            raise NotFoundError("authorization", authorization_id)
        self._uses[authorization_id] += 1
        return self._uses[authorization_id]


# --------------------------------------------------------------------------------------
# Capabilities, decisions and tools
# --------------------------------------------------------------------------------------


class FakeCapabilityRegistry:
    """Specifications by id (port :class:`~ela.ports.CapabilityRegistryPort`)."""

    def __init__(self) -> None:
        self._specs: dict[CapabilityId, CapabilitySpec] = {}

    def register(self, spec: CapabilitySpec) -> None:
        if spec.id in self._specs:
            raise AlreadyExistsError("capability", spec.id)
        self._specs[spec.id] = spec

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
    ) -> PermissionDecision:
        self.calls = (*self.calls, GuardianCall(capability, arguments, task, step, authorization))
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


class ToolCall(NamedTuple):
    """One execution a :class:`FakeTool` accepted."""

    decision: PermissionDecision
    arguments: JsonMapping


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
    ) -> None:
        self._capability_id = capability_id
        self._clock = clock
        self._ids = ids
        self._name = name
        self._output: JsonMapping = {} if output is None else output
        self._status = status
        self.calls: tuple[ToolCall, ...] = ()

    @property
    def capability_id(self) -> CapabilityId:
        return self._capability_id

    @property
    def name(self) -> str:
        return self._name

    async def execute(
        self, decision: PermissionDecision, arguments: JsonMapping
    ) -> ExecutionResult:
        if decision.capability_id != self._capability_id:
            raise NotAllowedError(
                self._capability_id, f"the decision is about {decision.capability_id}"
            )
        if decision.outcome is not PermissionOutcome.ALLOWED:
            raise NotAllowedError(self._capability_id, f"outcome is {decision.outcome.value}")
        if decision.expires_at is not None and decision.expires_at <= self._clock.now():
            raise NotAllowedError(self._capability_id, f"decision expired at {decision.expires_at}")
        self.calls = (*self.calls, ToolCall(decision, arguments))
        return ExecutionResult(
            id=ExecutionId(self._ids.new_uuid()),
            created_at=self._clock.now(),
            capability_id=self._capability_id,
            status=self._status,
            task_id=decision.task_id,
            step_id=decision.step_id,
            tool_name=self._name,
            output=self._output,
            duration_ms=0,
        )


# --------------------------------------------------------------------------------------
# Model providers
# --------------------------------------------------------------------------------------


class FakeModelProvider:
    """A provider that answers from a canned reply (port :class:`~ela.ports.ModelProvider`).

    ``reply`` is a string or a function of the request. ``usage`` counts words, deterministically.
    With ``error`` set, every result carries that error and an empty output, which is how a real
    provider reports a failure (a result, not an exception).
    """

    def __init__(
        self,
        clock: Clock,
        ids: IdGenerator,
        *,
        name: str = "fake",
        reply: str | Callable[[ProviderRequest], str] = "ok",
        error: ErrorMetadata | None = None,
    ) -> None:
        self._clock = clock
        self._ids = ids
        self._name = name
        self._reply = reply
        self._error = error
        self.requests: tuple[ProviderRequest, ...] = ()

    @property
    def name(self) -> str:
        return self._name

    async def complete(self, request: ProviderRequest) -> ProviderResult:
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
            usage=ProviderUsage(input_tokens=prompt_words, output_tokens=len(output.split())),
            finish_reason="error" if self._error is not None else "end_turn",
            error=self._error,
        )


class FakeProviderRegistry:
    """Providers by name (port :class:`~ela.ports.ProviderRegistry`)."""

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
