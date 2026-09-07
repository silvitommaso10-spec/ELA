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

from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Final, NamedTuple
from uuid import UUID

from ela.domain import (
    Approval,
    ApprovalId,
    ApprovalStatus,
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
    PlanId,
    ProviderRequest,
    ProviderResult,
    ProviderResultId,
    ProviderStatus,
    ProviderUsage,
    StepId,
    Task,
    TaskEvent,
    TaskEventId,
    TaskId,
    TaskPlan,
    TaskState,
    TaskStep,
)
from ela.ports import (
    PROVIDER_UNAVAILABLE,
    AlreadyExistsError,
    ApprovalAlreadyAnsweredError,
    ApprovalExpiredError,
    AuthorizationExhaustedError,
    AuthorizationExpiredError,
    Clock,
    IdGenerator,
    ModelProvider,
    NotAllowedError,
    NotFoundError,
    ToolPort,
    VerifierPort,
    check_answer,
    check_limit,
    check_verifiable,
)

__all__ = [
    "DEFAULT_START",
    "FAKE_CONDITION",
    "FakeApprovalStore",
    "FakeAuditLog",
    "FakeAuthorizationStore",
    "FakeCapabilityRegistry",
    "FakeClock",
    "FakeDeviceRegistry",
    "FakeExecutionResultStore",
    "FakeIdGenerator",
    "FakeModelProvider",
    "FakePermissionGuardian",
    "FakeProviderRegistry",
    "FakeTaskRepository",
    "FakeTool",
    "FakeToolRegistry",
    "FakeVerifier",
    "FakeVerifierRegistry",
    "GuardianCall",
    "ToolCall",
    "VerifierCall",
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
        check_limit(limit)
        selected = (
            event
            for event in self._events
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

    async def consume(self, authorization_id: AuthorizationId, *, now: datetime) -> int:
        """Same rules as the SQL store, in the same order: unknown, expired, exhausted, count."""
        grant = await self.get(authorization_id)
        uses = self._uses[authorization_id]
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
        idempotent: bool = True,
        usage: ProviderUsage | None = None,
    ) -> None:
        self._capability_id = capability_id
        self._clock = clock
        self._ids = ids
        self._name = name
        self.idempotent = idempotent
        """Whether twice is once (ADR 0015 §8, ADR 0021 §1): ``False`` is how a test builds a
        tool the executor must run under the STARTED protocol."""
        self._output: JsonMapping = {} if output is None else output
        self._status = status
        self._usage = usage
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
            usage=self._usage,
            duration_ms=0,
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
    ) -> None:
        self._capability_id = capability_id
        self._name = name
        self._conditions = frozenset(conditions)
        self._failures: Mapping[str, ErrorMetadata] = MappingProxyType(
            {} if failures is None else dict(failures)
        )
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


class FakeModelProvider:
    """A provider that answers from a canned reply (port :class:`~ela.ports.ModelProvider`).

    ``reply`` is a string or a function of the request. ``usage`` counts words, deterministically.
    With ``error`` set, every result carries that error and an empty output, which is how a real
    provider reports a failure (a result, not an exception). ``status`` says whether the provider
    is configured at all (ADR 0020 §2); an ``UNAVAILABLE`` fake answers with
    :data:`~ela.ports.PROVIDER_UNAVAILABLE` and records no request, as the real one does.
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
    ) -> None:
        self._clock = clock
        self._ids = ids
        self._name = name
        self._reply = reply
        self._error = error
        self._status = status
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
            usage=ProviderUsage(input_tokens=prompt_words, output_tokens=len(output.split())),
            finish_reason="error" if self._error is not None else "end_turn",
            error=self._error,
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
            usage=ProviderUsage(input_tokens=0, output_tokens=0),
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
