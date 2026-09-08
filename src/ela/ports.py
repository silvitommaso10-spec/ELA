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

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Final, Protocol, runtime_checkable
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
    Device,
    DeviceId,
    ErrorMetadata,
    ExecutionId,
    ExecutionResult,
    ExecutionStatus,
    JsonMapping,
    ModelRoute,
    PermissionDecision,
    ProbeFamily,
    ProviderRequest,
    ProviderResult,
    ProviderStatus,
    RawCapture,
    RawObservation,
    RawRecognition,
    RawSpeech,
    StepId,
    Task,
    TaskEvent,
    TaskId,
    TaskPlan,
    TaskState,
    TaskStep,
)

__all__ = [
    "ANSWERS",
    "AlreadyExistsError",
    "ApprovalAlreadyAnsweredError",
    "ApprovalExpiredError",
    "ApprovalNotAnswerableError",
    "ApprovalStore",
    "AuditLog",
    "AuthorizationExhaustedError",
    "AuthorizationExpiredError",
    "AuthorizationNotUsableError",
    "AuthorizationStore",
    "AuthorizingGuardianPort",
    "CapabilityRegistryPort",
    "Clock",
    "DeviceRegistryPort",
    "ExecutionResultStore",
    "IdGenerator",
    "ModelProvider",
    "ModelRouterPort",
    "NotAllowedError",
    "NotFoundError",
    "PROVIDER_AUTHENTICATION_ERROR",
    "PROVIDER_BAD_REQUEST",
    "PROVIDER_ERROR_CODES",
    "PROVIDER_MALFORMED_RESPONSE",
    "PROVIDER_NO_OUTPUT",
    "PROVIDER_RATE_LIMITED",
    "PROVIDER_REFUSAL",
    "PROVIDER_REJECTED",
    "PROVIDER_SERVER_ERROR",
    "PROVIDER_TIMEOUT",
    "PROVIDER_UNAVAILABLE",
    "PROVIDER_UNKNOWN_MODEL",
    "PROVIDER_UNKNOWN_MODEL_HINT",
    "PROVIDER_UNREACHABLE",
    "PROVIDER_UNSUPPORTED_PARAMETER",
    "PerceptionProbe",
    "PermissionGuardianPort",
    "PortError",
    "ProviderRegistryPort",
    "ROUTING_EMPTY_ROUTES",
    "ROUTING_ERROR_CODES",
    "ROUTING_UNKNOWN_PROVIDER",
    "ROUTING_UNKNOWN_TASK_TYPE",
    "RoutingError",
    "SPEECH_AUTHENTICATION_ERROR",
    "SPEECH_ERROR_CODES",
    "SPEECH_MALFORMED_RESPONSE",
    "SPEECH_NO_KEY",
    "SPEECH_NO_PLAYER",
    "SPEECH_NO_VOICE",
    "SPEECH_PLAYBACK_FAILED",
    "SPEECH_PLAYBACK_TIMEOUT",
    "SPEECH_QUOTA_EXCEEDED",
    "SPEECH_RATE_LIMITED",
    "SPEECH_REJECTED",
    "SPEECH_SERVER_ERROR",
    "SPEECH_TIMEOUT",
    "SPEECH_TOO_MUCH_AUDIO",
    "SPEECH_UNKNOWN_MODEL",
    "SPEECH_UNKNOWN_VOICE",
    "SPEECH_UNREACHABLE",
    "ScreenCapturePort",
    "SpeechPort",
    "TaskRepository",
    "TextRecognitionPort",
    "ToolPort",
    "ToolRegistryPort",
    "VERIFICATION_NOT_SUCCEEDED",
    "VERIFICATION_NO_CONDITIONS",
    "VERIFICATION_UNKNOWN_CONDITION",
    "VERIFICATION_WRONG_CAPABILITY",
    "VerifierPort",
    "VerifierRegistryPort",
    "check_answer",
    "check_limit",
    "check_verifiable",
    "named",
]


# --------------------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------------------


class PortError(Exception):
    """Base class of every error a port may raise, so a caller can catch them in one clause."""


def named(key: object) -> str:
    """A key as the caller wrote it, and can paste back (review of M8.2).

    An identifier is quoted — ``repr`` — because an empty or space-padded key has to stay
    visible in a message. A ``UUID`` is the exception: ``repr`` gives ``UUID('…')``, which is
    Python's syntax for building one and not the identifier anybody typed, and that string
    travels — through the API's error body, into what the CLI prints, into the next command.
    """
    return str(key) if isinstance(key, UUID) else repr(key)


class NotFoundError(PortError):
    """A ``get`` on a key the port does not hold. Never ``None``: a miss is named, not implied."""

    def __init__(self, kind: str, key: object) -> None:
        self.kind = kind
        self.key = key
        super().__init__(f"{kind} {named(key)} not found")


class AlreadyExistsError(PortError):
    """An insert on a key the port already holds. Overwriting silently would be a modification."""

    def __init__(self, kind: str, key: object) -> None:
        self.kind = kind
        self.key = key
        super().__init__(f"{kind} {named(key)} already exists")


def check_limit(limit: int | None) -> None:
    """The ``limit`` rule of every windowed read: ``None`` or at least 1, else ``ValueError``."""
    if limit is not None and limit < 1:
        raise ValueError(f"limit must be None or >= 1, not {limit}")


ANSWERS: Final[frozenset[ApprovalStatus]] = frozenset(
    {ApprovalStatus.GRANTED, ApprovalStatus.REJECTED}
)
"""The two statuses ``respond`` accepts (contract of :class:`ApprovalStore`): a yes or a no."""


def check_answer(status: ApprovalStatus) -> None:
    """The ``status`` rule of ``respond``: GRANTED or REJECTED, else ``ValueError``.

    Shared by every implementation, like :func:`check_limit`: PENDING is not an answer and
    EXPIRED is not the user's to say (the engine's recovery expires a task, ADR 0015 §6).
    """
    if status not in ANSWERS:
        raise ValueError(f"an answer is GRANTED or REJECTED, not {status.value}")


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


class ApprovalNotAnswerableError(PortError):
    """``respond`` refused to answer a request that exists but cannot be answered now (§30, §62).

    Raised *instead of* writing: nothing changed in the store. The two subclasses say why, so a
    caller can tell "someone already answered" from "too late".
    """

    def __init__(self, approval_id: ApprovalId, reason: str) -> None:
        self.approval_id = approval_id
        self.reason = reason
        super().__init__(f"approval {approval_id!r} cannot be answered: {reason}")


class ApprovalAlreadyAnsweredError(ApprovalNotAnswerableError):
    """The request is no longer PENDING: one answer, ever (§30)."""

    def __init__(self, approval_id: ApprovalId, status: ApprovalStatus) -> None:
        self.status = status
        super().__init__(approval_id, f"it is already {status.value}")


class ApprovalExpiredError(ApprovalNotAnswerableError):
    """The request's ``expires_at`` is at or before the instant given (closed bound, ADR 0005)."""

    def __init__(self, approval_id: ApprovalId, expires_at: datetime) -> None:
        self.expires_at = expires_at
        super().__init__(approval_id, f"it expired at {expires_at.isoformat()}")


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

    async def count(self, *, states: frozenset[TaskState] | None = None) -> Mapping[TaskState, int]:
        """How many tasks there are in each state, without bringing the tasks back (M8.3).

        One entry per state that has **at least one** task, never an entry at zero: the answer
        says what there is, and a state nobody has reached is not a fact worth a row. ``states``
        restricts the question (``None`` asks about all of them), and an **empty** ``frozenset``
        is a question about no state at all — it answers with an empty mapping, which is the one
        case where ``frozenset()`` and ``None`` do not mean the same thing.

        No ``limit``: counting the first N of something is not a count. The reason this exists is
        that ``GET /diagnostics`` used to count ten tasks by loading ten, and would have loaded
        ten thousand (review of M8.1).
        """

    async def due(
        self, *, states: frozenset[TaskState] | None = None, limit: int | None = None
    ) -> tuple[Task, ...]:
        """Stored tasks that **have** a deadline, soonest first, then ``limit`` (M10.4).

        The one question ``tasks()`` cannot answer, and the reason it is a member of its own:
        ``tasks()`` declares that its order is always insertion order, and that sentence is an
        invariant every implementation keeps. A different order is a different question, and a
        different question gets a name.

        Tasks **without** a deadline are not returned at all — not sorted to the end. The
        question is "which deadlines exist", and a task with no deadline is not a late one.

        ``states`` restricts the question as in ``tasks`` (``None`` asks about all of them, an
        empty ``frozenset`` about none). Ties on the same instant fall back to insertion order,
        so the answer is stable. ``limit`` is ``None`` or at least 1, else ``ValueError``, and
        applies after the filter — composing the answer by loading every live task and sorting
        it in the caller is what the review of M8.1 took out of ``/diagnostics``.
        """

    async def due_count(self, *, states: frozenset[TaskState] | None = None) -> int:
        """How many tasks have a deadline, without bringing any of them back (M10.4).

        The companion of ``due`` for the same reason ``count`` is the companion of ``tasks``:
        counting the first N of something is not a count, and a section that shows twenty of a
        hundred and thirty-seven must be able to say the hundred and thirty-seven without loading
        it (ADR 0032 §9-bis). Same ``states`` semantics as ``count``; an empty ``frozenset`` is a
        question about no state at all and answers ``0``.
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
        newest_first: bool = False,
    ) -> tuple[AuditEvent, ...]:
        """Events of one task if ``task_id``, with ``created_at >= since``, ``limit`` of them.

        ``since`` is inclusive, like every time boundary in the system (ADR 0005). All filters
        apply before ``limit``. ``limit`` is ``None`` or at least 1: a non-positive limit raises
        ``ValueError`` in every implementation (review M2.1).

        ``newest_first`` chooses **which end** the reading starts from, and the returned tuple is
        always in the order it was read (M8.3, ADR 0025 §3): appended order by default, so
        ``limit`` keeps the *first* entries; from the end when ``True``, so ``limit`` keeps the
        *last* ones and the tuple runs newest to oldest. A tail is the other end of the log, and
        taking it by reading the whole window and trimming it client-side — which is what
        ``ela audit tail`` did until M8.3 — reads everything the log has (ADR 0024 §6).
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


@runtime_checkable
class ApprovalStore(Protocol):
    """Where the requests for the user's consent and their answers are kept (§30, §62; ADR 0015).

    A request is born PENDING, in the executor (M5), and is answered **once**, GRANTED or
    REJECTED, by the user through ``respond``: a "yes" enters the store by no other door — ``add``
    refuses anything but PENDING — and the Core never answers its own requests (rule 19). What
    was asked is never rewritten: ``respond`` fills ``status``, ``responded_by`` and
    ``responded_at`` and nothing else. An expired request stays PENDING as stored; the store
    writes no ``EXPIRED``, the engine's recovery expires the task (ADR 0015 §6).
    """

    async def add(self, approval: Approval) -> None:
        """Store a new PENDING request; :class:`AlreadyExistsError` if its id is held.

        A request that is not PENDING is a caller's bug and raises ``ValueError`` in every
        implementation, before anything is written: an answer is given through ``respond``.
        """

    async def get(self, approval_id: ApprovalId) -> Approval:
        """The request with this id; :class:`NotFoundError` if there is none."""

    async def for_task(self, task_id: TaskId) -> tuple[Approval, ...]:
        """Every request of this task, whatever its status, in insertion order."""

    async def pending(
        self, *, now: datetime | None = None, limit: int | None = None
    ) -> tuple[Approval, ...]:
        """Every PENDING request across tasks, in insertion order, the first ``limit``: what
        waits for an answer (M8.1, the iPhone).

        With ``now``, a request that has expired at that instant (``expires_at <= now``, closed
        bound) is left out: it can no longer be answered (``respond`` refuses it), so showing it
        would be asking for something that cannot be given (§33). Without ``now`` every PENDING
        request comes back, expired or not: the store keeps no clock of its own, and the caller
        that has one passes it. Requests without an ``expires_at`` never expire. ``limit`` is
        ``None`` or at least 1, else ``ValueError``, and applies after the filter.
        """

    async def respond(
        self,
        approval_id: ApprovalId,
        *,
        status: ApprovalStatus,
        responded_by: str,
        now: datetime,
    ) -> Approval:
        """Answer the request and return it as stored — only if ``status`` is GRANTED or REJECTED
        (else ``ValueError``, a caller's bug), the request exists, is still PENDING and has not
        expired at ``now`` (``expires_at <= now`` is expired, closed bound). Otherwise nothing is
        written and, in this order, :class:`NotFoundError`, :class:`ApprovalAlreadyAnsweredError`
        or :class:`ApprovalExpiredError` is raised. ``responded_at`` is ``now``: the caller's
        fact, as for ``consume``. The check and the write are one atomic step: of two concurrent
        answers exactly one is recorded."""


@runtime_checkable
class ExecutionResultStore(Protocol):
    """Where what a tool produced is kept (§63; ADR 0015).

    A result is stored **before** ``TOOL_EXECUTED`` names it, so the audit never points at an
    entity that does not exist, and so a retry after a crash finds what the tool did instead of
    running it again (ADR 0015 §5). It holds the tool's ``output`` — the user's content (§57) —
    which the audit trail never does. Insert-only: a result is a fact.

    One rule beyond the id (M7.2, ADR 0021 §1-bis): **a step holds at most one ``STARTED``
    record**. That record means a tool that cannot be run twice was about to run, so a second one
    for the same step would be the very thing the protocol exists to prevent, written down as if
    it were normal. The store refuses it, and refusing it is the store's job and not only the
    executor's: the executor checks before it writes, and a check that lives only in the caller
    protects nothing against a second caller. A second *outcome* is not refused here — the
    executor already rejects one, and a UNIQUE on ``(task_id, step_id)`` was deliberately deferred
    (ADR 0015, alternatives) — so the asymmetry is on purpose.
    """

    async def add(self, result: ExecutionResult) -> None:
        """Store a new result; :class:`AlreadyExistsError` if its id is held, or if it is a
        ``STARTED`` record for a step that already has one."""

    async def get(self, result_id: ExecutionId) -> ExecutionResult:
        """The result with this id; :class:`NotFoundError` if there is none."""

    async def for_step(self, task_id: TaskId, step_id: StepId) -> tuple[ExecutionResult, ...]:
        """The results of this step of this task, in insertion order; empty if none.

        A step runs once (ADR 0013 §1), so at most two rows: the outcome, and — only for a tool
        that cannot be run twice — the ``STARTED`` record written before it acted (ADR 0021 §1).
        The outcome names the record it settles in ``metadata["started_id"]``; a ``STARTED`` with
        no outcome is a run that was interrupted, never one to repeat.
        """

    async def for_task(self, task_id: TaskId) -> tuple[ExecutionResult, ...]:
        """Every result of this task, in insertion order; empty if there is none (M8.3).

        The question ``GET /tasks/{id}/results`` asks, and the reason it is a member rather than
        a loop over ``for_step``: reading what a task produced would otherwise be one query per
        step of its plan. A task that does not exist is not this store's business — it holds
        results, not tasks — so an unknown id is an empty answer and not
        :class:`NotFoundError`.
        """


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
        device_id: DeviceId | None = None,
    ) -> PermissionDecision:
        """Decide about one call and append ``PERMISSION_DECIDED`` before returning.

        ``device_id`` is the node the call is about (M6.3, ADR 0019 §4). It is **stamped on the
        audit event and read by no rule**: a Guardian that decided by node would be a second,
        weaker permission axis beside the one it exists to be.
        """


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

    @property
    def idempotent(self) -> bool:
        """Whether running this tool twice with the same arguments leaves the world as once does.

        Declared, never defaulted: the answer belongs to the tool, and forgetting it must not
        read as a yes (§33). The executor reads it to decide whether a run needs the STARTED
        record of ADR 0021 §1 — a tool that can be repeated is repaired by repeating it
        (ADR 0015 §8), one that cannot is never started twice for the same step.
        """

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


PROVIDER_UNAVAILABLE: Final = "provider.unavailable"
"""The provider has no usable configuration — no credentials, typically. Nothing was sent."""
PROVIDER_UNKNOWN_MODEL_HINT: Final = "provider.unknown_model_hint"
"""``ProviderRequest.model_hint`` names no profile this provider offers. Nothing was sent."""
PROVIDER_UNSUPPORTED_PARAMETER: Final = "provider.unsupported_parameter"
"""``ProviderRequest.parameters`` holds a key or a value this provider cannot honour."""
PROVIDER_AUTHENTICATION_ERROR: Final = "provider.authentication_error"
"""The credentials were refused (or lack the right). Never retried: retrying cannot fix it."""
PROVIDER_BAD_REQUEST: Final = "provider.bad_request"
"""The provider rejected the request as malformed."""
PROVIDER_UNKNOWN_MODEL: Final = "provider.unknown_model"
"""The provider does not know the model that was asked for."""
PROVIDER_REJECTED: Final = "provider.rejected"
"""Any other refusal on the provider's side that retrying cannot fix — a conflict with the state
of a resource, a payload that failed validation. The request arrived and was turned down."""
PROVIDER_MALFORMED_RESPONSE: Final = "provider.malformed_response"
"""The provider answered something that is not an answer. Not a refusal: the request may well have
been fine and the channel is what broke — a serialisation bug reads as a broken channel, which is
what it is, instead of hiding behind "your request was rejected"."""
PROVIDER_RATE_LIMITED: Final = "provider.rate_limited"
"""Too many requests. Retryable: the same call can succeed later."""
PROVIDER_SERVER_ERROR: Final = "provider.server_error"
"""The provider failed on its side. Retryable."""
PROVIDER_UNREACHABLE: Final = "provider.unreachable"
"""The provider could not be reached at all. Retryable."""
PROVIDER_TIMEOUT: Final = "provider.timeout"
"""The call did not answer within the configured time. Retryable."""
PROVIDER_REFUSAL: Final = "provider.refusal"
"""The model declined to answer. Not a fault: a fact about the request, worth remembering
separately from a breakdown (§64) — hence a code of its own, and ``retryable`` false."""
PROVIDER_NO_OUTPUT: Final = "provider.no_output"
"""The call succeeded and carries no text. Nothing was refused and nothing broke: an answer
arrived and there is nothing in it (M7.2, ADR 0021 §5).

The odd one out of the vocabulary, and deliberately in it. The other thirteen name a failure the
provider *reported*; this one names a result a caller cannot use, and it exists so that an empty
answer is refused where it is seen rather than passed on as a success with nothing inside — which
would reach a verifier as a contradiction, and fail one layer later with less to say about why.
Whoever notices first says it: today that is the tool of ``model.complete``, and any adapter that
can tell an empty body from an answer may say it too."""

PROVIDER_ERROR_CODES: Final = frozenset(
    {
        PROVIDER_UNAVAILABLE,
        PROVIDER_UNKNOWN_MODEL_HINT,
        PROVIDER_UNSUPPORTED_PARAMETER,
        PROVIDER_AUTHENTICATION_ERROR,
        PROVIDER_BAD_REQUEST,
        PROVIDER_UNKNOWN_MODEL,
        PROVIDER_REJECTED,
        PROVIDER_MALFORMED_RESPONSE,
        PROVIDER_RATE_LIMITED,
        PROVIDER_SERVER_ERROR,
        PROVIDER_UNREACHABLE,
        PROVIDER_TIMEOUT,
        PROVIDER_REFUSAL,
        PROVIDER_NO_OUTPUT,
    }
)
"""The closed vocabulary of ``ProviderResult.error.code`` (ADR 0020 §7).

It lives here, with the port, and not inside an adapter, for the reason §26 exists: a caller must
be able to tell an authentication failure from an overload without importing — or even knowing —
the provider that produced it. A second provider reports the same fourteen codes or it is not
interchangeable with the first.

Closed means closed: a caller that needs a name for a failure the vocabulary does not have adds
it *here*, with an ADR, and never coins one of its own next to the code that raises it. A code
outside the vocabulary is exactly what the vocabulary exists to forbid (review of M7.2, which
brought :data:`PROVIDER_NO_OUTPUT` in from ``ela.tools.model``).
"""


@runtime_checkable
class ModelProvider(Protocol):
    """One model provider, in vendor-independent terms (§26, §50).

    Claude can be one; a local model can be another. The Core sees a request in, a result out,
    and what the call cost.

    ``complete`` never raises for a provider failure: the failure *is* the result, with ``error``
    set and its ``code`` taken from :data:`PROVIDER_ERROR_CODES`. That is what lets a caller
    record a failed call as it records a successful one (§32, §64).
    """

    @property
    def name(self) -> str:
        """The name the :class:`ProviderRegistryPort` knows this provider by."""

    @property
    def status(self) -> ProviderStatus:
        """Whether the provider is configured well enough to be called at all (§25).

        A provider that answers ``UNAVAILABLE`` is still registered and still answers
        ``complete`` — with :data:`PROVIDER_UNAVAILABLE` and without touching the network. It is
        how a missing credential becomes a fact ELA can read instead of a crash at start-up.
        """

    async def complete(self, request: ProviderRequest) -> ProviderResult:
        """Answer ``request``; a failure is a result with ``error`` set, not an exception."""


@runtime_checkable
class ProviderRegistryPort(Protocol):
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


# --------------------------------------------------------------------------------------
# Model routing (§25)
# --------------------------------------------------------------------------------------


ROUTING_UNKNOWN_TASK_TYPE: Final = "routing.unknown_task_type"
"""The policy has no route for that ``task_type``. Nothing was sent (ADR 0022 §5).

The vocabulary of task types is **closed**, like the vocabulary of hints (ADR 0020 §5): a type
nobody has mapped is a bug in whoever planned the step, not a case to cover with a default. A
default route exists for a step that names **no** type at all, which is a different thing from a
step that names the wrong one.
"""

ROUTING_UNKNOWN_PROVIDER: Final = "routing.unknown_provider"
"""A route names a provider the registry does not have. Raised **when the router is built**, not
when a step runs (ADR 0022 §7).

Distinct from :data:`PROVIDER_UNAVAILABLE`, and the distinction is the point: a provider that is
registered without credentials is *known* and gets skipped, which is the fallback §25 asks for; a
provider that is not registered at all is a typo in ``ELA_MODEL_ROUTES``, and a typo must stop ELA
before it works rather than divert a call in silence or fail a step hours later.
"""

ROUTING_EMPTY_ROUTES: Final = "routing.empty_routes"
"""The routing table has no route at all. Raised **when the policy is built** (ADR 0022 §8).

An empty table is not a policy that routes nothing on purpose: it is a policy that can answer
only calls naming no ``task_type``, and every step that names one fails — one at a time, at run
time, for a reason nobody would connect back to a configuration file. ELA ships a default table
precisely so that a machine where nobody configured anything still routes (§25), so the empty
table is refused at start-up and the failure says how to get that default back.
"""

ROUTING_ERROR_CODES: Final = frozenset(
    {
        ROUTING_UNKNOWN_TASK_TYPE,
        ROUTING_UNKNOWN_PROVIDER,
        ROUTING_EMPTY_ROUTES,
        PROVIDER_UNAVAILABLE,
    }
)
"""What a :class:`RoutingError` may carry (ADR 0022 §5).

Four codes and one of them is borrowed: a route whose providers are all unusable ends in
:data:`PROVIDER_UNAVAILABLE`, the code ADR 0020 §7 already gave to "this provider cannot be
called". Coining ``routing.no_provider_available`` beside it would give one fact two names, and
whoever reads a failure would have to know both to recognise the same wall.
"""


class RoutingError(PortError):
    """The router cannot choose (§25, §33). Raised **before** any provider is called.

    A failure of the router is an exception and not a result, unlike a failure of
    :meth:`ModelProvider.complete`: there the callee is across a network, where breaking down is
    ordinary and a result is what lets a caller record it; here the callee is a table in this
    process, and ELA already says "the caller was wrong" with a :class:`PortError` — see
    :class:`NotFoundError` and :class:`AuthorizationNotUsableError`. The tool of
    ``model.complete`` turns it into a failed outcome carrying ``code``, so what reaches the
    audit trail is the same either way.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@runtime_checkable
class ModelRouterPort(Protocol):
    """Which provider and which profile answer a call (§25, "tipo di task" and "disponibilità").

    Synchronous, like :class:`ProviderRegistryPort`: choosing reads a table and a declared
    status, and reading a declared status is not I/O — that is the whole point of
    :class:`~ela.domain.ProviderStatus` being a property of the configuration (ADR 0020 §2).

    The router **never calls a provider**: it answers with a :class:`~ela.domain.ModelRoute`, and
    a route that cannot be built is a :class:`RoutingError`. So the criterion §25 calls
    "disponibilità" costs nothing, and a provider that is down never receives the user's content
    only to hand it back (§57).
    """

    def route(self, task_type: str | None, model_hint: str | None) -> ModelRoute:
        """The route for this ``task_type``, with ``model_hint`` winning over its profile.

        :raises RoutingError: with :data:`ROUTING_UNKNOWN_TASK_TYPE` if the policy has no route
            for ``task_type``, or :data:`PROVIDER_UNAVAILABLE` if no provider of the route is
            usable. In both cases nothing has been sent anywhere.
        """


# --------------------------------------------------------------------------------------
# Perception (async: an I/O boundary, and the only one that touches the hardware)
# --------------------------------------------------------------------------------------


@runtime_checkable
class PerceptionProbe(Protocol):
    """Where ELA reads the state of the machine it runs on (§10, §11, §33, §57).

    The narrowest port in ELA, and narrow on purpose: it answers with primitives
    (:class:`~ela.domain.RawObservation`) and never with domain vocabulary. Whether an integer
    means ``DENIED`` and whether a missing camera means ``OFF`` are decisions, and decisions live
    in :mod:`ela.perception`, which the coverage gate covers — the adapter cannot be covered,
    because no CI runner has a webcam, so it must not be allowed to decide anything (M10.1,
    ADR 0028 §1; architecture rule 34).

    What this port must **not** do is as much of the contract as what it must:

    * **It reads state, never content.** No screen pixels, no audio samples, no window titles.
      Whether the microphone is in use is a fact about the machine, of the same kind as whether
      the display is asleep; a second of audio is not, and the milestone that first reads content
      is born with its own ``MEDIUM`` capability (§57, ADR 0028 §9).
    * **It never turns anything on.** Reading a permission is not requesting it, and no
      implementation may raise a system prompt (§11: nothing active without a reason).
    * **It does not fail — it reports.** A timeout, a dead helper process, an operating system
      with no such notion: all of them come back as a :class:`~ela.domain.RawObservation` whose
      fields are ``None``, never as an exception. The fail-safe of §33 is a *value* here, because
      "not observable" is already a fact this domain can express, and a perception read must never
      be able to take ELA down with it.
    """

    async def read(self, families: frozenset[ProbeFamily]) -> RawObservation:
        """Read the requested families; every field outside them is ``None``.

        ``families`` empty is a legal call that reads nothing and answers with an empty
        observation: the scheduler asks for what is due, and nothing being due is normal.
        """


@runtime_checkable
class TextRecognitionPort(Protocol):
    """Where ELA reads the text out of an image it already has (§10, §44, §57; M10.3, ADR 0030).

    The shape of :class:`ScreenCapturePort`, and the same three refusals, but the reason it is a
    port at all is different and worth naming: **this one needs no permission.** Measured from a
    process that was its own TCC responsible process, macOS's Vision recognises text with no grant
    of any kind, and with the network denied it answers in the same time — so nothing here reads a
    permission, preflights one, or can cause one to be recorded as denied. The permission was
    spent when the capture was taken, by the capability that took it.

    * **It does not choose what it reads.** The caller hands over a path inside a store it owns.
    * **It does not choose where the answer goes.** The lines come back; the file is the caller's
      to write, at the caller's mode, under the caller's expiry.
    * **It does not fail — it reports.** A timeout, a helper killed by a signal, an operating
      system with no such framework: all come back as a :class:`~ela.domain.RawRecognition` that
      says how it ended.
    * **It decides nothing** (architecture rule 34). It carries lines, confidences and the
      languages it could not use; what "no lines" *means* is the caller's to work out, and it
      cannot be worked out without those languages.
    """

    async def available(self) -> bool:
        """Whether this machine can recognise text at all — no permission, no side effect.

        Its own member for the reason ADR 0028 gave ``UnsupportedProbe`` and ADR 0029 gave
        ``available``: "ELA on Linux reads nothing" deserves to be an answer with a name and a
        test rather than a gap somebody discovers.
        """

    async def recognise(
        self, source: str, *, languages: tuple[str, ...], region: tuple[float, ...] | None
    ) -> RawRecognition:
        """Read the text in the image at ``source``, and answer with how it ended.

        ``source`` is an absolute path in a directory the caller owns. ``region``, when given, is
        ``(x, y, width, height)`` normalised to the image **with the origin at the bottom left**,
        which is the framework's convention: the caller converts, in code a runner can cover,
        because a flipped rectangle is the kind of mistake that returns a plausible answer instead
        of an error (ADR 0030 §12).
        """


@runtime_checkable
class SpeechPort(Protocol):
    """Where ELA says something out loud (§8, §9; M11.1, ADR 0033).

    The first port whose effect is **outside the screen**. Everything ELA did until now landed in
    a database, a file that expires, or an HTTP response — things you read if you go and look. A
    spoken sentence is heard, by whoever is in the room, and it leaves nothing behind to inspect.

    Three things it must not do, and each is half the contract:

    * **It writes nothing.** Not a file, not a buffer, not a return value carrying the sentence.
      ``say`` takes ``-o`` and would render to disk instead of speaking; architecture rule 40
      makes "it does not" checkable rather than promised (M11.1 dec. 7).
    * **It does not choose the voice.** Which voice ELA has is configuration of this machine, and
      a caller that could pick one could change who appears to be speaking.
    * **It does not fail — it reports.** A timeout, a helper killed by a signal, an operating
      system with no such notion: all come back as a :class:`~ela.domain.RawSpeech` that says how
      it ended, never as an exception.

    And one it **must** do, which no other port here needs: **a cancelled call stops the sound.**
    Awaiting :meth:`speak` to the end is what the caller does; cancelling that await is what a
    caller does when it has changed its mind, and the sentence has to stop. It is not the barge-in
    of §9 — that arrives with the listening, and needs a listener — but it is the primitive the
    barge-in will stand on, and a port that leaked an orphaned child here could not grow one.
    """

    async def available(self) -> bool:
        """Whether this machine can speak at all — no permission, no side effect.

        Its own member for the reason ADR 0028 gave ``UnsupportedProbe`` and ADR 0029 gave
        ``available``: "ELA on Linux says nothing" deserves to be an answer with a name and a
        test rather than a gap somebody discovers.
        """

    async def speak(self, text: str) -> RawSpeech:
        """Say ``text`` out loud, and answer with how it ended.

        Returns when the speaking is over: the duration of the call *is* the duration of the
        sentence, which is why the caller's timeout has to allow for a whole one.
        """


SPEECH_NO_KEY: Final = "speech.no_key"
"""No API key was configured for the online voice: ``ELA_ELEVENLABS_API_KEY`` is not set.

**Its own code, and not one shared with the missing voice**, because the two are different facts
with different answers — one is a credential nobody supplied, the other a choice nobody has made
— and the user's own words settled it: *«non hai messo la chiave» e «la chiave non è valida» sono
due fatti diversi con due azioni diverse.* It is ADR 0030 §8 applied to an error instead of to a
reading, and it is the third refusal in a row (``voice.disabled`` / ``voice.unsupported``,
ADR 0033 §9) that exists because collapsing refusals loses the only part that is actionable.

No network is touched: the failure is known before there is anything to send (ADR 0020 §2)."""
SPEECH_NO_VOICE: Final = "speech.no_voice"
"""No voice was chosen: ``ELA_ELEVENLABS_VOICE_ID`` is not set. Nothing is sent, and the answer
is an audition away — which is a different sentence from "your key was refused"."""
SPEECH_AUTHENTICATION_ERROR: Final = "speech.authentication_error"
"""The credential was refused. **Arrives as a 400 and not a 401** on this provider (measured,
ADR 0034 §1.3), which is why the vocabulary is mapped on the body's ``type`` and not on the
status code."""
SPEECH_UNKNOWN_VOICE: Final = "speech.unknown_voice"
"""The provider does not know that voice — for this account, or at all."""
SPEECH_UNKNOWN_MODEL: Final = "speech.unknown_model"
"""The provider does not know that model. Not reachable through configuration, which is checked
at start-up against the models ELA has measured; reachable by a provider retiring one."""
SPEECH_QUOTA_EXCEEDED: Final = "speech.quota_exceeded"
"""The account is out of credits. Not retryable by ELA: what fixes it is a human, next month or
on a different plan."""
SPEECH_RATE_LIMITED: Final = "speech.rate_limited"
"""Too many requests, or too many at once — the measured ceiling of this plan is ten concurrent."""
SPEECH_SERVER_ERROR: Final = "speech.server_error"
"""The provider failed on its own side."""
SPEECH_UNREACHABLE: Final = "speech.unreachable"
"""The provider could not be reached: no network, no DNS, no route."""
SPEECH_TIMEOUT: Final = "speech.timeout"
"""The audio did not arrive in time. **Nothing was said** — which is the difference from
``voice.timeout`` of ADR 0033 §9, where the sentence had already started."""
SPEECH_REJECTED: Final = "speech.rejected"
"""The request was turned down for a reason that is not one of the above."""
SPEECH_MALFORMED_RESPONSE: Final = "speech.malformed_response"
"""An answer arrived and is unusable: no audio, or not the audio that was asked for. Kept apart
from :data:`SPEECH_REJECTED` for the reason of ADR 0020 §7 — a broken channel and a refused
request send whoever is investigating in opposite directions."""
SPEECH_TOO_MUCH_AUDIO: Final = "speech.too_much_audio"
"""The answer went past the ceiling **while it was being read**, and reading stopped there. A
body that does not end is not a sentence, and it is not ELA's to hold in memory (§33)."""
SPEECH_NO_PLAYER: Final = "speech.no_player"
"""This operating system has no audio player ELA knows about.

Distinct from ``voice.unsupported`` (ADR 0033 §9) and not a duplicate of it: that one is "there
is no **voice** here", this one is "there is nothing here that can play a file somebody else
synthesised". On Linux both are true and they are still two different missing things, and ELA
says which one it looked for."""
SPEECH_PLAYBACK_FAILED: Final = "speech.playback_failed"
"""The audio arrived and the player ended badly: no output device, a format it refused, a signal.
What it *means* is not ELA's to guess (ADR 0033 §9)."""
SPEECH_PLAYBACK_TIMEOUT: Final = "speech.playback_timeout"
"""The player outstayed the length of its own audio and was stopped. Like ``voice.timeout``, this
does **not** mean nothing happened: it means ELA stopped mid-word, and for whoever heard it those
are two different things."""

SPEECH_ERROR_CODES: Final = frozenset(
    {
        SPEECH_NO_KEY,
        SPEECH_NO_PLAYER,
        SPEECH_NO_VOICE,
        SPEECH_AUTHENTICATION_ERROR,
        SPEECH_UNKNOWN_VOICE,
        SPEECH_UNKNOWN_MODEL,
        SPEECH_QUOTA_EXCEEDED,
        SPEECH_RATE_LIMITED,
        SPEECH_SERVER_ERROR,
        SPEECH_UNREACHABLE,
        SPEECH_TIMEOUT,
        SPEECH_REJECTED,
        SPEECH_MALFORMED_RESPONSE,
        SPEECH_TOO_MUCH_AUDIO,
        SPEECH_PLAYBACK_FAILED,
        SPEECH_PLAYBACK_TIMEOUT,
    }
)
"""The closed vocabulary of :attr:`~ela.domain.RawSpeech.error` (ADR 0034 §5).

Here and not in the adapter, for the reason ADR 0020 §7 put the model provider's codes here: a
caller must be able to tell "the network is gone" from "the key was refused" **without importing
— or knowing — who produced it**. A second speech provider reports these sixteen or it is not
interchangeable with the first.

Which of them are worth trying again is not written into the name: it travels with the failure,
because ``retryable`` describes the nature of a failure and not the attempts left (ADR 0020 §7).
"""


@runtime_checkable
class ScreenCapturePort(Protocol):
    """Where ELA photographs the screen it runs in front of (§10, §20, §57; M10.2, ADR 0029).

    A separate port from :class:`PerceptionProbe`, and separate because the probe's contract says
    three things a capture breaks two of: it answers with primitives *and takes none*; it does not
    fail, it reports; and it **reads state, never content**. A screen capture needs a destination,
    it produces the user's content, and "the permission is missing" is not "not observable" here —
    it is a refusal the user has to be told about, with what to do.

    What this port must **not** do is again half the contract:

    * **It does not choose where the image lands.** The caller creates and owns the destination,
      its mode and its lifetime, and hands it over (ADR 0029 §4). A port that picked the path
      would be a port that decides where the user's screen is kept.
    * **It carries no pixels.** The image goes to ``destination`` and nowhere else — never through
      a pipe, never through a return value, never through this process's memory.
    * **It never asks for the permission.** Preflighting is the caller's, and a caller that knows
      the permission is missing must not call this at all: attempting a capture from a denied
      state is how a *permanent* denial gets recorded (ADR 0029 §7).
    * **It does not fail — it reports.** A timeout, a helper killed by a signal, an operating
      system with no such notion: all of them come back as a :class:`~ela.domain.RawCapture` that
      says how it ended, never as an exception.
    """

    async def available(self) -> bool:
        """Whether this machine has a capture helper at all — no permission, no side effect.

        Its own member rather than a failure of :meth:`capture`, for the reason ADR 0028 gave
        ``UnsupportedProbe``: "ELA on Linux captures nothing" is worth being a named answer with
        a test instead of a gap somebody discovers. It also lets the caller settle the question
        **before** the permission, so a machine that could never capture never reads a
        permission it has no use for.
        """

    async def capture(self, destination: str, display: int) -> RawCapture:
        """Write a PNG of ``display`` to ``destination``, and answer with how it ended.

        ``destination`` is an absolute path in a directory the caller already owns; ``display`` is
        1-based. Whether anything was actually written is the caller's to check — an implementation
        that reported success without looking would be the assumption §20 forbids.
        """
