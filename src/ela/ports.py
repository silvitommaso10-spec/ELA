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

The module imports only the standard library and :mod:`ela.domain` (ADR 0002, rule 2). The
protocols are ``runtime_checkable`` so that a contract test can ask ``isinstance``; the signature
comparison in ``tests/contracts/test_protocols.py`` covers what ``isinstance`` cannot see.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from ela.domain import (
    AuditEvent,
    Authorization,
    AuthorizationId,
    CapabilityId,
    CapabilitySpec,
    Device,
    DeviceId,
    ExecutionResult,
    JsonMapping,
    PermissionDecision,
    ProviderRequest,
    ProviderResult,
    Task,
    TaskEvent,
    TaskId,
    TaskState,
    TaskStep,
)

__all__ = [
    "AlreadyExistsError",
    "AuditLog",
    "AuthorizationStore",
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
    """

    async def add(self, task: Task) -> None:
        """Store a new task; :class:`AlreadyExistsError` if its id is already held."""

    async def save(self, task: Task) -> None:
        """Replace a stored task with this version; :class:`NotFoundError` if it is unknown."""

    async def get(self, task_id: TaskId) -> Task:
        """The task with this id; :class:`NotFoundError` if there is none."""

    async def tasks(self, *, state: TaskState | None = None) -> tuple[Task, ...]:
        """Every stored task, or only those in ``state``, in insertion order."""

    async def append_event(self, event: TaskEvent) -> None:
        """Record an event of a stored task.

        :class:`NotFoundError` if the task is unknown, :class:`AlreadyExistsError` if the event id
        was recorded before.
        """

    async def events(self, task_id: TaskId) -> tuple[TaskEvent, ...]:
        """The events of a stored task in insertion order; :class:`NotFoundError` if unknown."""


@runtime_checkable
class AuditLog(Protocol):
    """The append-only trail of what ELA did, why, under which authorization (§32).

    Two members and no more: ``append`` and ``read``. There is no update, no delete, no clear, and
    an architecture test keeps it that way. Appending an event whose id is already in the log is
    refused with :class:`AlreadyExistsError` — overwriting is modifying.
    """

    async def append(self, event: AuditEvent) -> None:
        """Add an event at the end of the log; :class:`AlreadyExistsError` if its id is there."""

    async def read(self, *, task_id: TaskId | None = None) -> tuple[AuditEvent, ...]:
        """The whole log, or only the events of one task, in append order."""


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
    the uses on its behalf. It only counts: whether ``uses < max_uses`` still holds is the
    Guardian's judgement, and the Guardian receives the authorization as an argument — it never
    holds this store (ADR 0005).
    """

    async def grant(self, authorization: Authorization) -> None:
        """Store a new grant with zero uses; :class:`AlreadyExistsError` if its id is held."""

    async def get(self, authorization_id: AuthorizationId) -> Authorization:
        """The grant with this id; :class:`NotFoundError` if there is none."""

    async def for_capability(self, capability_id: CapabilityId) -> tuple[Authorization, ...]:
        """Every grant for this capability, expired or not, in grant order."""

    async def uses(self, authorization_id: AuthorizationId) -> int:
        """How many times the grant was used; :class:`NotFoundError` if unknown."""

    async def record_use(self, authorization_id: AuthorizationId) -> int:
        """Count one more use and return the new total; :class:`NotFoundError` if unknown."""


# --------------------------------------------------------------------------------------
# Capabilities, decisions and tools (§27–§29)
# --------------------------------------------------------------------------------------


@runtime_checkable
class CapabilityRegistryPort(Protocol):
    """The catalogue of what ELA may do, as specifications (§28, §29).

    Synchronous: the catalogue is declared, not fetched. A specification is registered once;
    registering the same id again is an error, not a replacement.
    """

    def register(self, spec: CapabilitySpec) -> None:
        """Add a specification; :class:`AlreadyExistsError` if its id is already there."""

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
    """

    def decide(
        self,
        capability: CapabilitySpec,
        arguments: JsonMapping,
        *,
        task: Task | None = None,
        step: TaskStep | None = None,
        authorization: Authorization | None = None,
    ) -> PermissionDecision:
        """Decide about one call of ``capability`` with ``arguments`` in this context."""


@runtime_checkable
class ToolPort(Protocol):
    """The implementation of one capability (§27, §28).

    A tool cannot run without a :class:`~ela.domain.PermissionDecision`: it is the first,
    mandatory argument of ``execute``. Contract for every implementation — before doing anything,
    the tool raises :class:`NotAllowedError` if the outcome is not ``ALLOWED``, if the decision is
    for another capability, or if it has expired. A tool receives the decision as data and never
    the Guardian or the store that produced it.
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
