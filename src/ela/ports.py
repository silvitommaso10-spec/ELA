"""Ports of ELA: the interfaces through which the Core talks to the outside world (spec §49).

A port says *what* the Core needs — somewhere to keep tasks, an append-only audit trail, a model
provider, a clock — and nothing about *how*. Implementations live at the edges (``providers/``,
``infrastructure/``, ``api/``) or, for the tests, in :mod:`ela.testing.fakes`; the Core only ever
sees these ``Protocol`` classes. That is what lets an implementation be replaced without rewriting
the Core (§49) and what keeps a provider's API out of the domain (§26, §50).

Two conventions run through every port (ADR 0005):

* **Async where there is I/O, sync where there is only computation.** A port that crosses an I/O
  boundary — persistence, a node, a provider, a wait — is ``async``; a port that computes from its
  arguments is synchronous. The Guardian is synchronous on purpose: it is a pure function from
  (specification, context, authorization) to a decision, with no I/O inside.
* **Reads are immutable, misses are explicit.** A collection comes back as a ``tuple``; a ``get`` on
  a missing key raises :class:`NotFoundError`; an insert on an existing key raises
  :class:`AlreadyExistsError`. Nothing is silently overwritten.
* **Expiry is closed.** Anything with an ``expires_at`` — a decision, an authorization, an
  approval, a heartbeat — is expired when ``expires_at <= now``. An implementation that treats
  the exact instant as still valid violates the contract (§33: when in doubt, do not act).

The module imports only the standard library and :mod:`ela.domain` (ADR 0002, rule 2). The
protocols are ``runtime_checkable`` so that a contract test can ask ``isinstance``; the signature
comparison in ``tests/contracts/test_protocols.py`` covers what ``isinstance`` cannot see.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Final, Protocol, runtime_checkable
from uuid import UUID

from ela.domain import (
    AuditEvent,
    Authorization,
    AuthorizationId,
    CapabilityId,
    CapabilitySpec,
    Device,
    DeviceId,
    ErrorMetadata,
    ExecutionResult,
    ExecutionStatus,
    JsonMapping,
    PermissionDecision,
    ProviderRequest,
    ProviderResult,
    Task,
    TaskEvent,
    TaskId,
    TaskPlan,
    TaskState,
    TaskStep,
)

__all__ = [
    "AlreadyExistsError",
    "AuditLog",
    "AuthorizationExhaustedError",
    "AuthorizationExpiredError",
    "AuthorizationNotUsableError",
    "AuthorizationStore",
    "AuthorizingGuardianPort",
    "CapabilityRegistryPort",
    "Clock",
    "DeviceRegistryPort",
    "IdGenerator",
    "ModelProvider",
    "NotAllowedError",
    "NotFoundError",
    "PermissionGuardianPort",
    "PortError",
    "ProviderRegistry",
    "TaskRepository",
    "ToolPort",
    "ToolRegistryPort",
    "VERIFICATION_NOT_SUCCEEDED",
    "VERIFICATION_NO_CONDITIONS",
    "VERIFICATION_UNKNOWN_CONDITION",
    "VERIFICATION_WRONG_CAPABILITY",
    "VerifierPort",
    "VerifierRegistryPort",
    "check_limit",
    "check_verifiable",
]


# --------------------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------------------


class PortError(Exception):
    """Base class of every error a port may raise, so a caller can catch them in one clause."""


class NotFoundError(PortError):
    """A ``get`` on a key the port does not hold. Never ``None``: a miss is named, not implied."""

    def __init__(self, kind: str, key: object) -> None:
        self.kind = kind
        self.key = key
        super().__init__(f"{kind} {key!r} not found")


class AlreadyExistsError(PortError):
    """An insert on a key the port already holds. Overwriting silently would be a modification."""

    def __init__(self, kind: str, key: object) -> None:
        self.kind = kind
        self.key = key
        super().__init__(f"{kind} {key!r} already exists")


def check_limit(limit: int | None) -> None:
    """The ``limit`` rule of every windowed read: ``None`` or at least 1, else ``ValueError``."""
    if limit is not None and limit < 1:
        raise ValueError(f"limit must be None or >= 1, not {limit}")


VERIFICATION_WRONG_CAPABILITY: Final = "verification.wrong_capability"
"""``verify`` was given a result of another capability (contract of :class:`VerifierPort`)."""
VERIFICATION_NOT_SUCCEEDED: Final = "verification.not_succeeded"
"""``verify`` was given a result whose status is not ``SUCCEEDED``: nothing to verify."""
VERIFICATION_NO_CONDITIONS: Final = "verification.no_conditions"
"""``verify`` was given no condition: the empty truth is a doubt (§33)."""
VERIFICATION_UNKNOWN_CONDITION: Final = "verification.unknown_condition"
"""A condition outside the verifier's vocabulary: it cannot be checked, so it does not hold."""


def check_verifiable(
    capability_id: CapabilityId,
    vocabulary: frozenset[str],
    conditions: Sequence[str],
    result: ExecutionResult,
) -> tuple[ErrorMetadata, ...]:
    """The preconditions every ``verify`` shares (contract of :class:`VerifierPort`): the
    failures that stop a verification before any condition is looked at, or nothing.

    A result of another capability, a result that did not succeed and an empty list of
    conditions are each one failure; a condition outside ``vocabulary`` is one failure per
    condition. The verifier then checks nothing else: a call that could not be verified is
    reported as such, never as a pass (§33, §63).
    """
    if result.capability_id != capability_id:
        return (
            ErrorMetadata(
                code=VERIFICATION_WRONG_CAPABILITY,
                message=f"the result is about {result.capability_id}, not {capability_id}",
                tool_name=result.tool_name,
                details={"condition": None},
            ),
        )
    if result.status is not ExecutionStatus.SUCCEEDED:
        return (
            ErrorMetadata(
                code=VERIFICATION_NOT_SUCCEEDED,
                message=f"the result is {result.status.value}, not SUCCEEDED: nothing to verify",
                tool_name=result.tool_name,
                details={"condition": None},
            ),
        )
    if not conditions:
        return (
            ErrorMetadata(
                code=VERIFICATION_NO_CONDITIONS,
                message="no success condition to check: an unverifiable result is not a success",
                tool_name=result.tool_name,
                details={"condition": None},
            ),
        )
    return tuple(
        ErrorMetadata(
            code=VERIFICATION_UNKNOWN_CONDITION,
            message=f"{condition!r} is not a condition the verifier of {capability_id} can check",
            tool_name=result.tool_name,
            details={"condition": condition},
        )
        for condition in conditions
        if condition not in vocabulary
    )


class AuthorizationNotUsableError(PortError):
    """``consume`` refused to spend a grant that exists but cannot be used now (§30, §33).

    Raised *instead of* counting: nothing changed in the store. The two subclasses say why, so a
    caller can tell "ask again" (expired) from "someone else got there first" (exhausted).
    """

    def __init__(self, authorization_id: AuthorizationId, reason: str) -> None:
        self.authorization_id = authorization_id
        self.reason = reason
        super().__init__(f"authorization {authorization_id!r} cannot be used: {reason}")


class AuthorizationExpiredError(AuthorizationNotUsableError):
    """The grant's ``expires_at`` is at or before the instant given (closed bound, ADR 0005)."""

    def __init__(self, authorization_id: AuthorizationId, expires_at: datetime) -> None:
        self.expires_at = expires_at
        super().__init__(authorization_id, f"it expired at {expires_at.isoformat()}")


class AuthorizationExhaustedError(AuthorizationNotUsableError):
    """The grant was already used ``max_uses`` times: a single-use grant spent twice (§30)."""

    def __init__(self, authorization_id: AuthorizationId, uses: int, max_uses: int) -> None:
        self.uses = uses
        self.max_uses = max_uses
        super().__init__(authorization_id, f"it was used {uses} of {max_uses} times")


class NotAllowedError(PortError):
    """A :class:`ToolPort` refused to execute: the decision does not allow it (§27, §33).

    Raised *before* anything happens, whatever the reason — the outcome is not ``ALLOWED``, the
    decision is for another capability, or it has expired. A tool that runs on a doubtful decision
    is the bypass §28 exists to prevent.
    """

    def __init__(self, capability_id: CapabilityId, reason: str) -> None:
        self.capability_id = capability_id
        self.reason = reason
        super().__init__(f"tool for {capability_id} refused to execute: {reason}")


# --------------------------------------------------------------------------------------
# Time and identity (synchronous: no I/O boundary)
# --------------------------------------------------------------------------------------


@runtime_checkable
class Clock(Protocol):
    """Where the Core reads the time (§51; ADR 0003 §4).

    The domain never reads the clock, so whoever builds an entity asks this port for "now".
    Contract: the instant is timezone-aware and in UTC. Monotonicity is *not* promised here — a
    system clock can step backwards — and stays a concern of the Task Engine (M1.2, deferred).
    """

    def now(self) -> datetime:
        """The current instant, timezone-aware, in UTC."""


@runtime_checkable
class IdGenerator(Protocol):
    """Where the Core gets a fresh identifier (§49; ADR 0003 §2).

    One method for every kind of id: the typed ids are ``NewType`` aliases that do not exist at
    runtime, so the caller wraps the result — ``TaskId(ids.new_uuid())``.
    """

    def new_uuid(self) -> UUID:
        """A UUID never returned before by this generator."""


# --------------------------------------------------------------------------------------
# Persistence (async: an I/O boundary)
# --------------------------------------------------------------------------------------


@runtime_checkable
class TaskRepository(Protocol):
    """Where tasks and their events are kept (§14, §15).

    The task is the aggregate and its :class:`~ela.domain.TaskEvent` trail belongs to it: "capire
    cosa è successo" and "riprendere attività interrotte" (§14) need both from one place. The
    repository stores and nothing else — which transitions are legal is the state machine's
    business (ADR 0004), and ``save`` does not check them.

    The :class:`~ela.domain.TaskPlan` of a task lives here too (M3.1, ADR 0008): the Task Graph
    and the orchestrator read it by id, and an entity with an id is not something to rebuild by
    scanning events. One plan per task, stored once; replanning is not a thing in v0.1 (ADR 0004).
    """

    async def add(self, task: Task) -> None:
        """Store a new task; :class:`AlreadyExistsError` if its id is already held.

        A ``parent_id`` must name a stored task, else :class:`NotFoundError` for the parent
        (M2.1): the Task Graph (§15) relies on that integrity, so every implementation keeps it.
        """

    async def save(self, task: Task) -> None:
        """Replace a stored task with this version; :class:`NotFoundError` if it is unknown.

        Same rule as ``add`` for ``parent_id``: an unknown parent is :class:`NotFoundError`.
        """

    async def get(self, task_id: TaskId) -> Task:
        """The task with this id; :class:`NotFoundError` if there is none."""

    async def tasks(
        self, *, states: frozenset[TaskState] | None = None, limit: int | None = None
    ) -> tuple[Task, ...]:
        """Stored tasks in insertion order: those in ``states`` (all if ``None``), then ``limit``.

        Recovery (M3.1) asks for the EXECUTING tasks without loading everything: the filter is
        the repository's, the order is always insertion order, ``limit`` applies after the filter.
        ``limit`` is ``None`` or at least 1: a non-positive limit is a caller's bug and raises
        ``ValueError`` in every implementation (review M2.1), never an empty result.
        """

    async def append_event(self, event: TaskEvent) -> None:
        """Record an event of a stored task.

        :class:`NotFoundError` if the task is unknown, :class:`AlreadyExistsError` if the event id
        was recorded before.
        """

    async def events(self, task_id: TaskId) -> tuple[TaskEvent, ...]:
        """The events of a stored task in insertion order; :class:`NotFoundError` if unknown."""

    async def add_plan(self, plan: TaskPlan) -> None:
        """Store the plan of a stored task.

        :class:`NotFoundError` if ``plan.task_id`` is unknown; :class:`AlreadyExistsError` if
        the task already has a plan or the plan id is already held.
        """

    async def plan(self, task_id: TaskId) -> TaskPlan:
        """The plan of a stored task; :class:`NotFoundError` if the task is unknown or has none."""


@runtime_checkable
class AuditLog(Protocol):
    """The append-only trail of what ELA did, why, under which authorization (§32).

    Two members and no more: ``append`` and ``read``. There is no update, no delete, no clear, and
    an architecture test keeps it that way. Appending an event whose id is already in the log is
    refused with :class:`AlreadyExistsError` — overwriting is modifying.
    """

    async def append(self, event: AuditEvent) -> None:
        """Add an event at the end of the log; :class:`AlreadyExistsError` if its id is there."""

    async def read(
        self,
        *,
        task_id: TaskId | None = None,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> tuple[AuditEvent, ...]:
        """Events in append order: of one task if ``task_id``, with ``created_at >= since``, the
        first ``limit``.

        ``since`` is inclusive, like every time boundary in the system (ADR 0005). All filters
        apply before ``limit``. ``limit`` is ``None`` or at least 1: a non-positive limit raises
        ``ValueError`` in every implementation (review M2.1).
        """


@runtime_checkable
class DeviceRegistryPort(Protocol):
    """The registry of the nodes ELA can operate through (§16).

    ``register`` and ``update`` are distinct because they say different things: a node that
    appears twice is a bug, and so is an update for a node nobody registered.
    """

    async def register(self, device: Device) -> None:
        """Add a node; :class:`AlreadyExistsError` if its id is already registered."""

    async def update(self, device: Device) -> None:
        """Replace a registered node with this version; :class:`NotFoundError` if unknown."""

    async def get(self, device_id: DeviceId) -> Device:
        """The node with this id; :class:`NotFoundError` if there is none."""

    async def devices(self) -> tuple[Device, ...]:
        """Every registered node, in registration order."""


@runtime_checkable
class AuthorizationStore(Protocol):
    """Where the grants the Guardian consumes are kept (§30, §59).

    An :class:`~ela.domain.Authorization` is frozen and may carry ``max_uses``, so the store counts
    the uses on its behalf. The Guardian judges whether a grant covers a call and is usable, from
    the count the caller reads here (``uses``, ADR 0011); ``consume`` then spends one use
    atomically, so that two executors holding the same single-use grant cannot both act (ADR 0012).
    The Guardian receives the authorization as an argument — it never holds this store (ADR 0005).
    """

    async def grant(self, authorization: Authorization) -> None:
        """Store a new grant with zero uses; :class:`AlreadyExistsError` if its id is held."""

    async def get(self, authorization_id: AuthorizationId) -> Authorization:
        """The grant with this id; :class:`NotFoundError` if there is none."""

    async def for_capability(self, capability_id: CapabilityId) -> tuple[Authorization, ...]:
        """Every grant for this capability, expired or not, in grant order."""

    async def uses(self, authorization_id: AuthorizationId) -> int:
        """How many times the grant was used; :class:`NotFoundError` if unknown."""

    async def consume(self, authorization_id: AuthorizationId, *, now: datetime) -> int:
        """Spend one use and return the new total — only if the grant exists, has not expired at
        ``now`` (``expires_at <= now`` is expired, closed bound) and is not exhausted
        (``uses < max_uses``). Otherwise nothing is counted and, in this order,
        :class:`NotFoundError`, :class:`AuthorizationExpiredError` or
        :class:`AuthorizationExhaustedError` is raised. The check and the count are one atomic
        step: of two concurrent calls on a single-use grant exactly one returns. ``now`` is the
        caller's fact, as ``authorization_uses`` is for the Guardian (ADR 0011 §5)."""


# --------------------------------------------------------------------------------------
# Capabilities, decisions and tools (§27–§29)
# --------------------------------------------------------------------------------------


@runtime_checkable
class CapabilityRegistryPort(Protocol):
    """The catalogue of what ELA may do, as specifications (§28, §29).

    Synchronous: the catalogue is declared, not fetched. Read-only (ADR 0010, M4.1): a registry
    is populated once, when it is built, and has no way to change afterwards — a capability that
    could be added at runtime could be added by whatever wants to run it. Two specifications
    with the same id at construction are an :class:`AlreadyExistsError`, not a replacement.
    """

    def get(self, capability_id: CapabilityId) -> CapabilitySpec:
        """The specification with this id; :class:`NotFoundError` if there is none."""

    def specs(self) -> tuple[CapabilitySpec, ...]:
        """Every registered specification, in registration order."""


@runtime_checkable
class PermissionGuardianPort(Protocol):
    """The component that decides whether a capability call may happen (§27, §33).

    Synchronous and pure: a function from the specification, the call's context and the
    authorization that would cover it to a :class:`~ela.domain.PermissionDecision`. The Guardian
    owns no tool and no store: the caller fetches the authorization and passes it in.

    Contract for every implementation: a capability for which the Guardian has no rule is
    ``DENIED`` (§33, "nel dubbio non agire"). Doubt is never ``ALLOWED``.

    ``authorization_uses`` is how many times ``authorization`` has already been used, read by the
    caller from the :class:`AuthorizationStore` (ADR 0011, M4.2): the caller supplies facts, the
    Guardian judges whether the grant is exhausted. Without an authorization the count is
    meaningless and left at zero.
    """

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
        """Decide about one call of ``capability`` with ``arguments`` in this context."""


@runtime_checkable
class AuthorizingGuardianPort(Protocol):
    """The audited entry of the Guardian: decide *and* record the decision (§27, §32; ADR 0013).

    ``decide`` (:class:`PermissionGuardianPort`) is pure and synchronous; a decision the audit log
    never saw does not exist (ADR 0011 §8), so whoever wants one — the executor, M5 — calls this
    port instead. Async because it writes the log; a separate port because one port has one mode
    (ADR 0005 §1). Same arguments as ``decide``; if the log refuses the event the exception
    escapes and no decision is returned. No fake: the real Guardian is pure and runs on the fake
    log, and it is the only implementation registered for the contract tests.
    """

    async def authorize(
        self,
        capability: CapabilitySpec,
        arguments: JsonMapping,
        *,
        task: Task | None = None,
        step: TaskStep | None = None,
        authorization: Authorization | None = None,
        authorization_uses: int = 0,
    ) -> PermissionDecision:
        """Decide about one call and append ``PERMISSION_DECIDED`` before returning."""


@runtime_checkable
class ToolPort(Protocol):
    """The implementation of one capability (§27, §28).

    A tool cannot run without a :class:`~ela.domain.PermissionDecision`: it is the first,
    mandatory argument of ``execute``. Contract for every implementation — before doing anything,
    the tool raises :class:`NotAllowedError` if the outcome is not ``ALLOWED``, if the decision is
    for another capability, or if it has expired (``expires_at <= now``: a decision expiring at
    this very instant is already expired). A tool receives the decision as data and never the
    Guardian or the store that produced it.
    """

    @property
    def capability_id(self) -> CapabilityId:
        """The capability this tool implements."""

    @property
    def name(self) -> str:
        """How the tool is named in audit events and execution results."""

    async def execute(
        self, decision: PermissionDecision, arguments: JsonMapping
    ) -> ExecutionResult:
        """Run the capability under ``decision``; :class:`NotAllowedError` if it does not allow."""


@runtime_checkable
class ToolRegistryPort(Protocol):
    """The tools ELA can execute, one per capability (§28; ADR 0013).

    Synchronous and read-only, like :class:`CapabilityRegistryPort`: a table of tools already
    built, fixed when the registry is. The key of every entry is the tool's own ``capability_id``
    — a tool cannot be registered under another capability — and two tools for one capability at
    construction are an :class:`AlreadyExistsError`. The executor (M5) is the only caller.
    """

    def get(self, capability_id: CapabilityId) -> ToolPort:
        """The tool implementing this capability; :class:`NotFoundError` if there is none."""

    def tools(self) -> tuple[ToolPort, ...]:
        """Every registered tool, in registration order."""


# --------------------------------------------------------------------------------------
# Verification (§20, §63)
# --------------------------------------------------------------------------------------


@runtime_checkable
class VerifierPort(Protocol):
    """Checks the world against the success conditions of a step (§20, §63; ADR 0014).

    Execution is not proof of success: after the tool ran, the executor (M5) asks the verifier
    of the capability whether each of the step's ``success_conditions`` holds, and only then
    completes the step. A verifier is a separate object from the tool on purpose — a tool that
    verified itself would be certifying its own claim — and it is **read-only**: it looks at the
    filesystem, at the tool's output, at whatever the capability touched, and changes nothing.
    Async because it reads.

    ``conditions`` is the closed vocabulary this verifier can check: a plan (§13) names its
    success conditions from it, as it names its arguments from the capability's schema.

    Contract for every implementation of ``verify``, fail-safe on its own (§33): a result about
    another capability, a result whose status is not ``SUCCEEDED``, an empty ``conditions`` (the
    empty truth is a doubt) and a condition outside the vocabulary are each a failure with a
    named code, never a pass and never an exception; a condition that holds produces nothing;
    every failure carries ``details["condition"]``. An empty tuple means verified.
    """

    @property
    def capability_id(self) -> CapabilityId:
        """The capability whose results this verifier checks."""

    @property
    def name(self) -> str:
        """How the verifier is named in audit events."""

    @property
    def conditions(self) -> frozenset[str]:
        """The success conditions this verifier can check: the vocabulary a plan may use."""

    async def verify(
        self, conditions: Sequence[str], arguments: JsonMapping, result: ExecutionResult
    ) -> tuple[ErrorMetadata, ...]:
        """One failure per condition that does not hold, in the order given; empty if all hold."""


@runtime_checkable
class VerifierRegistryPort(Protocol):
    """The verifiers ELA can consult, one per capability (§63; ADR 0014).

    Synchronous and read-only, like :class:`ToolRegistryPort`, and keyed the same way: by the
    verifier's own ``capability_id``; two verifiers for one capability at construction are an
    :class:`AlreadyExistsError`. A capability with a tool but no verifier is not executable: the
    executor refuses it before asking the Guardian (§63: what cannot be verified is not done).
    """

    def get(self, capability_id: CapabilityId) -> VerifierPort:
        """The verifier of this capability; :class:`NotFoundError` if there is none."""

    def verifiers(self) -> tuple[VerifierPort, ...]:
        """Every registered verifier, in registration order."""


# --------------------------------------------------------------------------------------
# Model providers (§26, §50)
# --------------------------------------------------------------------------------------


@runtime_checkable
class ModelProvider(Protocol):
    """One model provider, in vendor-independent terms (§26, §50).

    Claude can be one; a local model can be another. The Core sees a request in, a result out,
    and what the call cost.
    """

    @property
    def name(self) -> str:
        """The name the :class:`ProviderRegistry` knows this provider by."""

    async def complete(self, request: ProviderRequest) -> ProviderResult:
        """Answer ``request``; a failure is a result with ``error`` set, not an exception."""


@runtime_checkable
class ProviderRegistry(Protocol):
    """The providers the Core can route to, by name (§50).

    Synchronous: an in-memory table of already-built providers. Should it ever discover providers
    remotely, it changes side with an ADR (ADR 0005).
    """

    def register(self, provider: ModelProvider) -> None:
        """Add a provider; :class:`AlreadyExistsError` if its name is taken."""

    def get(self, name: str) -> ModelProvider:
        """The provider with this name; :class:`NotFoundError` if there is none."""

    def names(self) -> tuple[str, ...]:
        """The registered names, sorted."""
