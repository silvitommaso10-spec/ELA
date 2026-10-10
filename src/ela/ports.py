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

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Final, Protocol, runtime_checkable
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
    JsonValue,
    ModelRoute,
    PermissionDecision,
    PowerSource,
    ProbeFamily,
    ProviderRequest,
    ProviderResult,
    ProviderStatus,
    ProviderUsage,
    RawCapture,
    RawObservation,
    RawRecognition,
    RawSpeech,
    RawTranscript,
    Reservation,
    RiskLevel,
    StepId,
    Task,
    TaskEvent,
    TaskId,
    TaskPlan,
    TaskState,
    TaskStep,
    WorstCase,
)

__all__ = [
    "ANNOUNCED_FIELDS",
    "ANSWERS",
    "AgentSession",
    "AlreadyExistsError",
    "ApprovalAlreadyAnsweredError",
    "ApprovalExpiredError",
    "ApprovalNotAnswerableError",
    "ApprovalOutOfReachError",
    "ApprovalStore",
    "AssignmentExpiredError",
    "AssignmentHeldElsewhereError",
    "AssignmentNodeBusyError",
    "AssignmentNotUsableError",
    "AssignmentStateError",
    "AssignmentStillLiveError",
    "AssignmentStore",
    "AuditLog",
    "AuthorizationAlreadyRevokedError",
    "AuthorizationExhaustedError",
    "AuthorizationExpiredError",
    "AuthorizationNotUsableError",
    "AuthorizationRevokedError",
    "AuthorizationStore",
    "AuthorizingGuardianPort",
    "Bell",
    "Browser",
    "BrowserError",
    "BrowserFailed",
    "BrowserNotInstalled",
    "BrowserStopped",
    "BrowserUnsupported",
    "CallRequest",
    "CapabilityRegistryPort",
    "Captured",
    "Clock",
    "Command",
    "CommandLauncher",
    "DeviceRegistryPort",
    "DeviceRevokedError",
    "ENVELOPE",
    "Ending",
    "EnrollmentConsumedError",
    "EnrollmentExpiredError",
    "EnrollmentNotUsableError",
    "EnrollmentRoleError",
    "EnrollmentStore",
    "ExecutionResultStore",
    "Field",
    "Forwarded",
    "GUIDED_CACHE",
    "GUIDED_CAP_BELOW_ONE_CALL",
    "GUIDED_COST",
    "GUIDED_DURATION",
    "GUIDED_ERROR_CODES",
    "GUIDED_FAILED",
    "GUIDED_FOLDER_CHANGED",
    "GUIDED_LOOKS",
    "GUIDED_MAX_TOKENS",
    "GUIDED_MODEL_CHANGED",
    "GUIDED_NOT_INSTALLED",
    "GUIDED_PERMISSION_ASKED",
    "GUIDED_ROUTE_CHANGED",
    "GUIDED_SESSION_GONE",
    "GUIDED_STOPPED",
    "GUIDED_TOOLS_CHANGED",
    "GUIDED_UNCHECKED",
    "GUIDED_UNRESERVED",
    "Gesture",
    "Gestures",
    "Glanced",
    "Guided",
    "IdGenerator",
    "IdentityConflictError",
    "Invocation",
    "LISTEN_DENIED_BY_SYSTEM",
    "LISTEN_DISABLED",
    "LISTEN_ERROR_CODES",
    "LISTEN_FAILED",
    "LISTEN_LANGUAGE_UNSUPPORTED",
    "LISTEN_NO_INPUT_DEVICE",
    "LISTEN_NO_SIGNAL",
    "LISTEN_PERMISSION_UNREADABLE",
    "LISTEN_TIMEOUT",
    "LISTEN_TRANSCRIPTION_FAILED",
    "LISTEN_TRANSCRIPTION_UNAVAILABLE",
    "LISTEN_UNSUPPORTED",
    "ListeningPort",
    "LocalBeat",
    "ModelGateway",
    "ModelProvider",
    "ModelRouterPort",
    "NAVIGATION",
    "NotAllowedError",
    "NotFoundError",
    "Opened",
    "OpenedSession",
    "PROVIDER_AUTHENTICATION_ERROR",
    "PROVIDER_BAD_REQUEST",
    "PROVIDER_ERROR_CODES",
    "PROVIDER_MALFORMED_RESPONSE",
    "PROVIDER_NO_OUTPUT",
    "PROVIDER_RATE_LIMITED",
    "PROVIDER_REFUSAL",
    "PROVIDER_REJECTED",
    "PROVIDER_SERVER_ERROR",
    "PROVIDER_SPEND_LIMIT",
    "PROVIDER_TIMEOUT",
    "PROVIDER_UNAVAILABLE",
    "PROVIDER_UNKNOWN_MODEL",
    "PROVIDER_UNKNOWN_MODEL_HINT",
    "PROVIDER_UNREACHABLE",
    "PROVIDER_UNSUPPORTED_PARAMETER",
    "PageGone",
    "PerceptionProbe",
    "PermissionGuardianPort",
    "PortError",
    "Prospect",
    "ProviderRegistryPort",
    "ROUTING_EMPTY_ROUTES",
    "ROUTING_ERROR_CODES",
    "ROUTING_UNKNOWN_PROVIDER",
    "ROUTING_UNKNOWN_TASK_TYPE",
    "Ran",
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
    "SPENDING_OVER_RESERVATION",
    "STARTED_ID",
    "ScreenCapturePort",
    "SessionEnd",
    "SessionHandle",
    "SessionHost",
    "SessionPlan",
    "SessionTally",
    "SiteUnreachable",
    "SpeechPort",
    "StopPoint",
    "Target",
    "TaskRepository",
    "TaskStop",
    "TextRecognitionPort",
    "ToolPort",
    "ToolRegistryPort",
    "ToolStopped",
    "VERIFICATION_NOT_SUCCEEDED",
    "VERIFICATION_NO_CONDITIONS",
    "VERIFICATION_UNKNOWN_CONDITION",
    "VERIFICATION_WRONG_CAPABILITY",
    "VerifierPort",
    "VerifierRegistryPort",
    "Visit",
    "WireCode",
    "audited_numbers",
    "check_answer",
    "check_limit",
    "check_verifiable",
    "named",
]


# --------------------------------------------------------------------------------------
# The vocabulary of the wire
# --------------------------------------------------------------------------------------


class WireCode(StrEnum):
    """Every ``error.code`` the API answers with, and nothing else (ADR 0023 §10; M12.4).

    A client branches on the code — a node tells the two ``409`` of a delivery apart by it, because
    the status is the same — so the code is the one part of a refusal both ends must spell the same
    way. Until M12.4 it was a string written wherever it was needed: in the API's table, in a node's
    constants, in a node's tests. Nothing compared them, and the node's tests scripted three codes
    no Core has ever sent (``renewal.capped``, ``too_late``, ``code_reused``).

    **Here because it is the one place both ends may import**: ``ela.api`` and ``ela.node`` both
    reach ``ela.ports``, and ``ela.ports`` reaches nothing but the domain (import contract 2). A
    closed list, held in both directions by ``tests/api/test_wire_codes.py``: every code the API
    emits is a member, and every member is emitted by someone.

    The codes of a **tool** (``provider.*``, ``speech.*``, ``verification.*``) are not these: they
    travel inside a result, as its word, and not as the answer to a request.
    """

    NOT_FOUND = "not_found"
    ALREADY_EXISTS = "already_exists"
    NOT_ANSWERABLE = "not_answerable"
    TAMPERED = "tampered"
    INVALID = "invalid"
    CONFLICT = "conflict"
    ALREADY_RUNNING = "already_running"
    ASSIGNMENT_EXPIRED = "assignment.expired"
    ASSIGNMENT_VOID = "assignment.void"
    NOT_ASSIGNED = "not_assigned"
    ASSIGNMENT_AT_CAP = "assignment.at_cap"
    DELIVERY_CONFLICT = "delivery.conflict"
    IDENTITY_CONFLICT = "identity_conflict"
    NOT_REVOCABLE = "not_revocable"
    REVISION_REQUIRED = "revision_required"
    DATABASE_UNAVAILABLE = "database_unavailable"
    POLICY_REFUSED = "policy.refused"
    """A policy of §59 that cannot be born (M13.12, ADR 0062): the check is the first word of the
    message, the closed vocabulary of the wire is not widened by one code per check."""
    POLICY_WOULD_NOT_START = "policy.would_not_start"
    """«Partirebbe» (decision 7): the tool refused the call at the limits and on the sites of the
    policy; its own code is the first word of the message."""
    POLICY_PREVIEW_CHANGED = "policy.preview_changed"
    """The confirmation named another model than the prospect does now: preview again."""
    POLICY_NOT_LIVE = "policy.not_live"
    """A revocation of a policy already revoked, or already ended."""
    UNAUTHORIZED = "unauthorized"
    """Every refusal of the middleware, whatever the reason was (ADR 0023 §7, ADR 0037 §13)."""


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


class AuthorizationRevokedError(AuthorizationNotUsableError):
    """The grant was revoked at ``revoked_at`` (M13.12, ADR 0062; decision 5): named **before**
    expired, in the order of the predicate, and refused in the same ``UPDATE`` that spends."""

    def __init__(self, authorization_id: AuthorizationId, revoked_at: datetime) -> None:
        self.revoked_at = revoked_at
        super().__init__(authorization_id, f"it was revoked at {revoked_at.isoformat()}")


class AuthorizationAlreadyRevokedError(PortError):
    """``revoke`` of a grant already revoked: the revocation is written once (decision 5), and the
    first instant stays."""

    def __init__(self, authorization_id: AuthorizationId, revoked_at: datetime) -> None:
        self.authorization_id = authorization_id
        self.revoked_at = revoked_at
        super().__init__(
            f"authorization {authorization_id!r} was already revoked at {revoked_at.isoformat()}"
        )


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


class ApprovalOutOfReachError(ApprovalNotAnswerableError):
    """The identity answering may not be shown what it would be approving (M12.5 dec. F.2).

    The third way a request that exists cannot be answered *now*, beside "already answered" and
    "too late": the content of the task is above what the user allowed this identity to receive,
    so the page did not show it — and one does not approve what one cannot see (§30). The answer
    is not refused to the **user**, who has it at the Mac: it is refused to this bearer.
    """

    def __init__(self, approval_id: ApprovalId) -> None:
        super().__init__(approval_id, "its content stays on the Mac: answer it from there")


class IdentityConflictError(PortError):
    """Two processes claim to be the same node: the row is not at the revision the caller saw.

    Not a race resolved by order of arrival — a **conflict of identity** (ADR 0035 §5): the second
    announcement believed something false about the row, and is told so instead of overwriting the
    first. Detected, named and refused (M12.1 dec. H; ADR 0037 §9).
    """

    def __init__(self, device_id: DeviceId, expected: int, actual: int) -> None:
        self.device_id = device_id
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"device {device_id} is at revision {actual}, not {expected}: "
            "two processes claim to be it"
        )


class DeviceRevokedError(PortError):
    """The node was revoked: its row stays, and nothing it declares is written any more."""

    def __init__(self, device_id: DeviceId, revoked_at: datetime) -> None:
        self.device_id = device_id
        self.revoked_at = revoked_at
        super().__init__(f"device {device_id} was revoked at {revoked_at.isoformat()}")


class EnrollmentNotUsableError(PortError):
    """An enrollment code exists and cannot be spent; the subclasses say why (ADR 0037 §5).

    The message never carries the code nor its hash: an error can reach a response body, and the
    only response that carries a secret of the enrollment is the one that hands it out.
    """


class EnrollmentConsumedError(EnrollmentNotUsableError):
    """The code was already spent — by the node it names, which is what ``code_reused`` reports."""

    def __init__(self, device_id: DeviceId) -> None:
        self.device_id = device_id
        super().__init__(f"the enrollment code was already consumed by device {device_id}")


class EnrollmentExpiredError(EnrollmentNotUsableError):
    """The code's ``expires_at`` is at or before the instant given (closed bound, ADR 0005)."""

    def __init__(self, expires_at: datetime) -> None:
        self.expires_at = expires_at
        super().__init__(f"the enrollment code expired at {expires_at.isoformat()}")


class EnrollmentRoleError(EnrollmentNotUsableError):
    """The code was minted for one role and presented on the enrolment route of another (M12.5).

    Nothing is written: the role is a condition **of the statement** that spends the code, so a
    code refused here is still spendable where it belongs (dec. C.5). The message names the two
    roles and never the code — an error reaches a response body, and a companion's is a page.
    """

    def __init__(self, carried: DeviceRole, expected: DeviceRole) -> None:
        self.carried = carried
        self.expected = expected
        super().__init__(
            f"the enrollment code was issued for a {carried.value} "
            f"and this route enrolls a {expected.value}"
        )


class AssignmentNotUsableError(PortError):
    """An assignment exists and a move asked of it did not happen; the subclasses say why.

    Raised only after the conditional ``UPDATE`` of the move touched no row: the safety is in the
    statement, and the read that follows it only names the reason (ADR 0012 §5; M12.2, ADR 0038).
    No message names another node: an error can reach a response body, and a node is not told
    which assignments exist for the others.
    """

    def __init__(self, assignment_id: AssignmentId, reason: str) -> None:
        self.assignment_id = assignment_id
        self.reason = reason
        super().__init__(f"assignment {assignment_id} cannot be moved: {reason}")


class AssignmentHeldElsewhereError(AssignmentNotUsableError):
    """The assignment is another node's: whoever asked was never its assignee.

    ``held_by`` is kept for the audit, which tells "unknown" from "another's"; the message does
    not carry it.
    """

    def __init__(self, assignment_id: AssignmentId, held_by: DeviceId) -> None:
        self.held_by = held_by
        super().__init__(assignment_id, "it is assigned to another node")


class AssignmentStateError(AssignmentNotUsableError):
    """The assignment is not in the state the move starts from."""

    def __init__(self, assignment_id: AssignmentId, state: AssignmentState) -> None:
        self.state = state
        super().__init__(assignment_id, f"it is {state.value}")


class AssignmentExpiredError(AssignmentNotUsableError):
    """Its ``expires_at`` is at or before the instant given (closed bound, ADR 0005 §2-bis)."""

    def __init__(self, assignment_id: AssignmentId, expires_at: datetime) -> None:
        self.expires_at = expires_at
        super().__init__(assignment_id, f"it expired at {expires_at.isoformat()}")


class AssignmentStillLiveError(AssignmentNotUsableError):
    """An expiry asked of an assignment whose ``expires_at`` is ahead: time has not decided yet."""

    def __init__(self, assignment_id: AssignmentId, expires_at: datetime) -> None:
        self.expires_at = expires_at
        super().__init__(assignment_id, f"it expires only at {expires_at.isoformat()}")


class AssignmentNodeBusyError(AssignmentNotUsableError):
    """A claim by a node that holds a claim not yet expired: one at a time (M12.1, D16)."""

    def __init__(self, assignment_id: AssignmentId, device_id: DeviceId) -> None:
        self.device_id = device_id
        super().__init__(assignment_id, f"node {device_id} holds work that has not expired")


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


class ToolStopped(PortError):
    """The task of a running tool was stopped before the tool passed its point of no return
    (M6.3c, ADR 0054 §3).

    Raised by :meth:`TaskStop.listen`, at the point or before it, and only there: nothing has
    happened that the call was approved to do, and the executor records the call as ``CANCELLED``.
    A tool stopped **after** its point does not raise this — it reports what it did, in its own
    words, because then it has acted.
    """

    def __init__(self, where: str) -> None:
        self.where = where
        super().__init__(f"the task was stopped before {where}")


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

    async def finished(self, *, states: frozenset[TaskState], limit: int) -> tuple[Task, ...]:
        """Stored tasks in ``states``, the last to finish first, ``limit`` of them (M17.2b).

        The question the homes ask — «the last N outcomes» — and a member of its own for the reason
        :meth:`due` gives: ``tasks()`` keeps insertion order, and a different order is a different
        question. The order is ``finished_at``, newest first, with insertion order newest first on
        a tie so the answer is stable; a task **without** a ``finished_at`` — one that finished
        before the hour was written, and whose final event was lost (ADR 0015 §8) — comes **last**,
        never left out: it finished, and a list of outcomes that dropped it would be the defect
        this member repairs.

        ``states`` is the caller's (``TERMINAL_STATES``): the port does not import the state
        machine. An empty ``frozenset`` is a question about no state at all and answers ``()``, as
        for ``tasks`` and ``count``. ``limit`` is required and at least 1, else ``ValueError``: its
        only caller always passes one, and ``None`` would be a branch nobody produces. How many
        there are in all is :meth:`count` — the question a list that cuts must be able to answer
        without loading what it cut.
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


ANNOUNCED_FIELDS: Final[tuple[str, ...]] = (
    "name",
    "os",
    "capabilities",
    "available_tools",
    "performance",
)
"""The half of a node's row the node declares about itself, and all an announcement writes.

ADR 0037 §10: ``privacy`` is imposed by the user at enrollment, ``network`` is the registry's,
what a heartbeat carries is observed, and ``revision`` and ``revoked_at`` are the state of the
identity. :meth:`DeviceRegistryPort.announce` writes these fields and no other, in every
implementation; ``tests/docs/test_adr_nodes.py`` keeps them equal to the ADR's table.
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

    async def enroll(self, device: Device, *, secret_hash: str) -> None:
        """Add a node that proves itself from the network, with the SHA-256 of its secret.

        :class:`AlreadyExistsError` if the id is taken. The hash is kept on the row and never on
        the entity (M12.1 dec. G; architecture rule 46).
        """

    async def secret_hash(self, device_id: DeviceId) -> str | None:
        """The hash a node proves itself against; ``None`` for a node that does not authenticate
        from the network (``local``); :class:`NotFoundError` if the id is unknown."""

    async def announce(self, device: Device, *, expected_revision: int) -> int:
        """Write the node's declared half and return the new revision — only if the row is still at
        ``expected_revision`` and not revoked (M12.1 dec. H).

        The declared half is :data:`ANNOUNCED_FIELDS` (ADR 0037 §10): nothing observed,
        nothing imposed. Otherwise nothing is
        written and, in this order, :class:`NotFoundError`, :class:`DeviceRevokedError` or
        :class:`IdentityConflictError` is raised. The check and the write are one atomic step: of
        two announcements at the same revision exactly one is written.
        """

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
        """Write the observed half of a node — ``last_seen_at``, ``availability``, and what the
        heartbeat reports — and nothing else; :class:`NotFoundError` if unknown.

        ``status``, ``current_workload`` and ``power_source`` are written only when given: a
        heartbeat that says nothing about them must not erase what was known. Its own statement,
        so that no announcement can be lost to a heartbeat that read the row before it (ADR 0016
        §5; M12.1 dec. H).
        """

    async def revoke(self, device_id: DeviceId, *, at: datetime) -> bool:
        """Mark the node revoked at ``at``, once: ``True`` if this call revoked it, ``False`` if it
        already was; :class:`NotFoundError` if unknown. The row stays (ADR 0016 §6)."""


@runtime_checkable
class EnrollmentStore(Protocol):
    """Where the one-shot enrollment codes wait for a node to present them (§16; M12.1 dec. D, G).

    The twenty-fourth port. A code is not a device — until it is consumed no node exists — so it
    has a store of its own (ADR 0037 §8). What is kept is the hash of the code, never the code.
    """

    async def offer(self, enrollment: Enrollment) -> None:
        """Keep a new code; :class:`AlreadyExistsError` if a code with this hash is already kept."""

    async def consume(
        self, code_hash: str, *, device_id: DeviceId, now: datetime, role: DeviceRole
    ) -> Enrollment:
        """Spend the code for ``device_id`` and return it as stored — only if it exists, has not
        been consumed, has not expired at ``now`` (``expires_at <= now`` is expired, closed bound)
        and carries ``role``, the role of the enrolment route presenting it (M12.5 dec. C.5).
        Otherwise nothing is written and, in this order, :class:`NotFoundError`,
        :class:`EnrollmentConsumedError`, :class:`EnrollmentRoleError` or
        :class:`EnrollmentExpiredError` is raised. The check and the write are one atomic step: of
        two nodes presenting the same code exactly one is born (ADR 0012 §5, the shape of
        ``consume``)."""


@runtime_checkable
class LocalBeat(Protocol):
    """A sign of life of this machine, with what it runs on read **now** (§16; M13.3, ADR 0048 §2).

    The runner asks for one before **every** placement — ``place`` for a pending step, ``confirm``
    for a running one — so that ``local`` is alive for the registry whenever it is about to be
    chosen, and the power source the placement weighs was read at that instant and not remembered
    from an earlier beat: a periodic belief never decides an action (ADR 0029 §7). A port and not
    the service, because the runner lives in ``ela.executive`` and the service in ``ela.devices``,
    and a test fakes a beat without building a registry.

    Only the Core writes it (ADR 0044 §8): never a page, never a route that happens to be
    answering.
    """

    async def beat(self) -> None:
        """Write the heartbeat of ``local``, with the power source read at this instant."""
        ...


@runtime_checkable
class Bell(Protocol):
    """How ELA gets the user's attention when it needs them and they are not here (M12.5 dec. E).

    The twenty-sixth port, and the only one whose effect is **on a phone**: everything else ELA
    does lands where somebody has to go and look. A bell is not a letter — it says that something
    waits, never what it is — and the vocabulary is closed **by the shape of this port**: one
    method per thing that can ring, and today one method. An enum with a single member would
    invite a second voice with no writer; a method obliges every future event to arrive with its
    own caller and its own decision (the review of 2026-09-19).

    **No parameter is a string**, and that is the guarantee rather than a promise: ``risk`` comes
    from the catalogue, so nothing of the user's content can be passed in, and ``mypy --strict``
    refuses a sentence where the method wants a :class:`~ela.domain.RiskLevel`. What the user is
    shown is composed by the adapter, from a table of its own.

    **It does not fail — it reports.** A bell that does not ring must not fail a run: the question
    waits on the page and in the CLI all the same, and the outcome is written either way. Whoever
    calls it writes ``BELL_RUNG`` with what came back (§57: which provider, which data, why).
    """

    @property
    def name(self) -> str:
        """Which provider would ring: what the audit records, never the topic or the URL."""
        ...

    @property
    def ready(self) -> bool:
        """Whether a bell can ring at all: a topic configured, and an address to open."""
        ...

    async def approval_waiting(self, risk: RiskLevel) -> bool:
        """Ring for a request for consent that is waiting; ``True`` if it was delivered.

        Never raises: a network that is not there, a provider that says no and a timeout all come
        back as ``False``.
        """


@runtime_checkable
class AssignmentStore(Protocol):
    """Where the work handed to remote nodes waits, is taken and comes back (§15; M12.2, ADR 0038).

    The twenty-fifth port. It returns every row **as written** — ``OFFERED`` even when its expiry
    passed an hour ago — and what a row is *now* is derived on read by the service that decides,
    :mod:`ela.executive.assignments`, the one module that may name this port (architecture rule
    48): ADR 0016 §3, applied to a second deadline. No sweeper writes ``EXPIRED``; whoever acts on
    an expiry writes it, in the statement that checks it.

    Every move is one conditional ``UPDATE`` whose predicate asks "has it expired?" of the one
    ``expires_at``, with one meaning and closed (``expires_at <= now`` is expired). When it touches
    no row nothing is written, and one read in the same transaction names the reason, in this
    order: :class:`NotFoundError`, :class:`AssignmentHeldElsewhereError`,
    :class:`AssignmentStateError`, then the expiry (ADR 0012 §5). ``now`` is always the caller's.
    """

    async def add(self, assignment: Assignment) -> None:
        """Keep a new assignment. :class:`AlreadyExistsError` if its id is kept, or if its step
        already has an assignment that is not ``EXPIRED`` — one per step, a partial unique index
        (ADR 0038)."""

    async def get(self, assignment_id: AssignmentId) -> Assignment:
        """The assignment as written; :class:`NotFoundError` if unknown."""

    async def for_step(self, task_id: TaskId, step_id: StepId) -> tuple[Assignment, ...]:
        """Every assignment of one step, in insertion order: the last is the standing one."""

    async def offered_to(self, device_id: DeviceId) -> tuple[Assignment, ...]:
        """Every ``OFFERED`` assignment of one node, in insertion order, whatever its expiry."""

    async def claim(
        self,
        assignment_id: AssignmentId,
        *,
        device_id: DeviceId,
        now: datetime,
        expires_at: datetime,
    ) -> Assignment:
        """``OFFERED → CLAIMED`` at ``now``, the expiry moved to ``expires_at`` — only if the offer
        is ``device_id``'s, not expired at ``now``, **and the node holds no claim that is not
        expired at ``now``** (M12.1, D16): a ``NOT EXISTS`` in the same statement, not an index,
        because an index does not know the time. Its atomicity rests on SQLite's single writer,
        declared (ADR 0038). The refusals are the port's, then :class:`AssignmentNodeBusyError`."""

    async def deliver(
        self, assignment_id: AssignmentId, *, device_id: DeviceId, now: datetime, digest: str
    ) -> Assignment:
        """``CLAIMED → DELIVERED`` at ``now`` with the SHA-256 of the envelope — only if the claim
        is ``device_id``'s and not expired at ``now``."""

    async def renew(
        self,
        assignment_id: AssignmentId,
        *,
        device_id: DeviceId,
        now: datetime,
        expires_at: datetime,
    ) -> Assignment:
        """The claim's expiry moved to ``expires_at`` — only if it is ``device_id``'s, ``CLAIMED``
        and not expired at ``now``. The cap is the caller's to apply (ADR 0038)."""

    async def expire(self, assignment_id: AssignmentId, *, now: datetime) -> Assignment:
        """``OFFERED`` or ``CLAIMED`` → ``EXPIRED``, only if expired at ``now``. One already
        ``EXPIRED`` is returned as it is: two callers acting on one expiry agree, and the second
        writes nothing. :class:`AssignmentStateError` for a ``DELIVERED`` one,
        :class:`AssignmentStillLiveError` for one whose expiry is still ahead."""

    async def withdraw(self, assignment_id: AssignmentId, *, now: datetime) -> Assignment:
        """``OFFERED → WITHDRAWN`` at ``now``, **only if it is still ``OFFERED``** (M6.3c, ADR
        0054 §9): its task ended before any node took it. A claim that came first wins, and the row
        comes back as it is — ``CLAIMED`` —, as does one already ``WITHDRAWN``: the caller reads
        which. Not :meth:`expire`, which writes only where time has decided. :class:`NotFoundError`
        if unknown.
        """

    async def cut_short(self, device_id: DeviceId, *, now: datetime) -> int:
        """The expiry of every assignment of the node that is ``OFFERED`` or ``CLAIMED`` and not
        expired at ``now`` becomes ``now`` (M12.1, D17): how many were cut. No state changes —
        the revocation makes an expiry, and whoever acts on it writes ``EXPIRED``."""


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

    async def revoke(self, authorization_id: AuthorizationId, *, at: datetime) -> Authorization:
        """Write ``revoked_at`` once and return the revoked grant (M13.12, ADR 0062; decision 5).

        :class:`NotFoundError` for an unknown id; :class:`AuthorizationAlreadyRevokedError` the
        second time, with the first instant, which stays. One conditional ``UPDATE``. ``at`` is the
        caller's fact: the store has no clock."""

    async def consume(self, authorization_id: AuthorizationId, *, now: datetime) -> int:
        """Spend one use and return the new total — only if the grant exists, is not revoked, has
        not expired at ``now`` (``expires_at <= now`` is expired, closed bound) and is not exhausted
        (``uses < max_uses``). Otherwise nothing is counted and, in this order,
        :class:`NotFoundError`, :class:`AuthorizationRevokedError`,
        :class:`AuthorizationExpiredError` or :class:`AuthorizationExhaustedError` is raised (the
        revocation since M13.12, in the same conditional ``UPDATE``). The check and the count are
        one atomic step: of two concurrent calls on a single-use grant exactly one returns.
        ``now`` is the caller's fact, as ``authorization_uses`` is for the Guardian (ADR 0011 §5).
        """


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


SPENDING_OVER_RESERVATION: Final = "spending.over_reservation"
"""A node did not make a call that spends because its own worst case was more than the Core
reserved (M14.1, ADR 0057): another output budget, another route, another price list — another
commit. Not a cap of the node's: the node does not spend beyond what the Core decided. The call
was not sent, and the result says so (``usage.sent`` false)."""

STARTED_ID: Final = "started_id"
"""Key of ``ExecutionResult.metadata`` on an outcome that settles a STARTED record (ADR 0021 §1):
the id of that record, so the two rows of one run are one run and not two. Here since M14.1, with
the port, because three packages read it — the executor that writes it, the store that finds what
closes a reservation, and the month's ledger (ADR 0057)."""


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

    async def spending(self, since: datetime, until: datetime) -> tuple[ExecutionResult, ...]:
        """The reservations of a period and what closed them (M14.1, ADR 0057).

        Every ``STARTED`` record with a ``worst_case`` created in ``[since, until)``, and every
        result that names one of them in ``metadata["started_id"]``, wherever its own date falls:
        the rows the month's ledger is derived from, and nothing else.
        """

    async def reserve(
        self,
        record: ExecutionResult,
        since: datetime,
        until: datetime,
        admits: Callable[[tuple[ExecutionResult, ...]], bool],
    ) -> bool:
        """Add ``record`` only if ``admits`` says yes to the period's rows, as one operation.

        Under the write lock from the read to the insert (M14.1, ADR 0057): the rows are those of
        :meth:`spending`, read inside the same transaction, so two reservations that would each fit
        alone cannot both be written on the same margin. ``False``, and nothing written, when
        ``admits`` says no. The other refusals of :meth:`add` hold.
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


@dataclass(frozen=True, slots=True)
class Target:
    """Where a path really points, and what a "yes" would do to it (M13.1 dec. G).

    ``resolved`` is the absolute path the call will touch, ``exists`` says whether a regular file
    is there **now**, and ``does`` is the sentence the user reads before answering. All three are
    read from the machine with the classification the tool and the verifier share (ADR 0014 §2),
    never from what the caller declared.

    **``does`` belongs to the capability, not to the fact.** «Overwrites a file that is already
    there» is true of a write and false of a read, and a warning that says the wrong thing
    teaches the reader to stop reading it. The tool writes its own sentence, and no surface owns
    a phrase it could lend to a capability that never asked for one.

    **And so does ``label``, what the target is called** (M13.2 dec. 12): a surface that wrote
    «Il file» beside every target was right about a file and misleading about a program — true to
    the letter, since a program is a file, and wrong about what is being approved. The tool that
    knows what it touches says what to call it.
    """

    resolved: str
    exists: bool
    does: str
    label: str


@dataclass(frozen=True, slots=True)
class Invocation:
    """What a command would receive, read by the tool that will launch it (M13.2 dec. 12).

    ``program`` is the declared path in full and ``runs`` the file it leads to, read from the disk
    now — two facts, because ELA runs the first and the identity it fixed is the second's.
    ``arguments`` exactly as the process will receive them, ``folder`` the resolved folder it
    starts from, and the two numbers of the question: how long ELA waits, and which code the plan
    expects. None of them is the plan's word: each is what the tool would do with it.
    """

    program: str
    runs: str
    arguments: tuple[str, ...]
    folder: str
    timeout_seconds: int
    expect_exit: int


@dataclass(frozen=True, slots=True)
class Guided:
    """What a guided session of the browser would be, as the question names it (M14.3, ADR 0060).

    The sentence the model starts from, the sites that are the boundary of every gesture, the model
    the router chose — the one that will run, or the step fails —, the most the session may spend,
    in dollars as a string of ``Decimal``, the looks and the seconds, and ``sends``, the tool's
    sentence that the text of the pages goes to the model's provider (§57). The worst case and what
    is left of the month are the question's own, as for every call that spends.
    """

    phrase: str
    sites: tuple[str, ...]
    model: str
    max_cost: str
    looks: int
    timeout_seconds: int
    sends: str
    one_call: str
    """The worst case of one call of the session, in dollars, or ``"no price"`` (M13.12, decision
    9): what the preview of a policy names beside the most a session may spend — the limit is on
    the reservation, and one call reserves this much. The question of a session does not show it:
    it shows the worst case line, which already says «per call»."""


@dataclass(frozen=True, slots=True)
class Prospect:
    """What a call would meet on the machine **now**, read without running anything.

    The whole of M13.1's rule in one answer: *a question is composed only for something that,
    approved now, would succeed on the disk as it is now* (ADR 0045 §6-bis). ``refusal`` is what
    this call would fail with if it ran this instant; ``target`` is what the question would say
    about the file. A refusal means **there is no question to ask** — the step fails where the
    question would have been composed, and nobody is woken to approve what is already lost.

    Both come from the same code the tool refuses with when it really runs: one fact, one
    definition, one place.
    """

    target: Target | None = None
    refusal: ErrorMetadata | None = None
    invocation: Invocation | None = None
    """What a command would receive, when the call is a command (M13.2); ``None`` otherwise."""
    visit: Visit | None = None
    """What a browser call would do, when the call is one (M13.4, ADR 0052); ``None`` otherwise.
    It carries the site, what the tool calls it and the tool's sentence itself, because a site is
    not a :class:`Target`: nobody resolved it."""
    guided: Guided | None = None
    """What a guided session of the browser would be, when the call is one (M14.3, ADR 0060);
    ``None`` otherwise."""


def audited_numbers(declared: frozenset[str], output: JsonMapping) -> dict[str, JsonValue]:
    """The numbers of a result that enter ``TOOL_EXECUTED``: integers, by type, and nothing else.

    ``declared`` are the tool's :attr:`ToolPort.audit_numbers`, each a path into ``output``
    (``"stdout.total"``); a key that is not there is ``None``. A value that is not an ``int`` — a
    string, a float, a boolean, a list — is a :class:`ValueError` that names the key and the type,
    **never the value**, which may be the user's content (§57). A boolean is refused although Python
    counts it as an integer: ``True`` in an audit is a word, not a count.

    **The one definition** (M13.2, ADR 0047): the executor calls it where a result is born — the
    tool of this machine, and a node's delivery, where a ``ValueError`` is a ``422`` — and where
    ``TOOL_EXECUTED`` is written, and ``tests/architecture/test_terminal_rules.py`` refuses a
    payload whose numbers come from anywhere else.
    """
    numbers: dict[str, JsonValue] = {}
    for key in sorted(declared):
        value: object = output
        for part in key.split("."):
            if value is None:
                break
            if not isinstance(value, Mapping):
                raise ValueError(
                    f"{key!r} passes through a {type(value).__name__}, not an object: only "
                    "integers enter the audit"
                )
            value = value.get(part)
        if value is not None and type(value) is not int:
            raise ValueError(
                f"{key!r} is a {type(value).__name__} and not an integer: only integers enter "
                "the audit"
            )
        numbers[key] = value
    return numbers


ENVELOPE: Final = "the envelope"
"""The point of no return of a step placed on a node (M6.3c, ADR 0054 §3): the order goes out as the
answer to the node's own request, and the stop of a task does not reach the node."""


@dataclass(frozen=True, slots=True)
class StopPoint:
    """Where a tool listens for the stop of its task, in two halves (M6.3c, ADR 0054 §3).

    ``here`` names the point of no return where the tool listens **on this machine** — the instant
    after which an effect of the call has happened or can no longer be taken back —, or is ``None``
    for a tool whose point is **the call itself**: it has no wait inside before its effect, and the
    one listening is the executor's, before the grant. ``on_a_node`` is :data:`ENVELOPE` for a tool
    that travels and ``None`` for one that does not: never a promise to listen on a node, because
    the stop does not reach one — for a step on a node, the point is the order sent.
    """

    here: str | None
    on_a_node: str | None


@runtime_checkable
class TaskStop(Protocol):
    """The stop of one task, as one call of a tool sees it (M6.3c, ADR 0054 §2–§3).

    The mechanism of ``Ela.stopping`` (ADR 0047 §7) narrowed to a task, and handed **per call**,
    never at construction: an adapter built with the stop of one task would stop the next one.
    """

    def listen(self, where: str) -> None:
        """Raise :class:`ToolStopped` if the task is stopped; otherwise, when ``where`` is the
        tool's own point (:attr:`StopPoint.here`), record that the tool has passed it.

        Called **with no ``await`` of ELA's between it and the call that produces the effect**.
        Named, because the same stop serves a listening that is not the tool's point:
        ``browser.act`` opens its page through the same navigation ``browser.read`` acts with."""

    def is_set(self) -> bool:
        """Whether the task is stopped, for a tool past its point that can still spare an effect."""

    def stopped(self) -> Awaitable[object]:
        """What completes when the task is stopped: what a launcher races a running program
        against. A sync member that hands out the awaitable, so the port has one mode — a sync
        one, because :meth:`listen` must not yield the loop (ADR 0005 §1)."""


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

    @property
    def relocatable(self) -> bool:
        """Whether the work of this tool, taken by a node that then goes silent, may be done again
        on **another machine** without changing what it means and without doubling its effect
        (M13.3, ADR 0048).

        Declared, never defaulted — the form of :attr:`idempotent` — and **not a synonym of it**:
        ``fs.read`` can be repeated on its machine, and on another one the same path is another
        file. The executor reads it at the claim of a node: the STARTED record is written there for
        a tool that is not relocatable, so an expired claim is closed ``interrupted`` instead of
        being placed again (the second predicate of ADR 0038 §8). A tool that cannot be repeated
        here cannot be repeated elsewhere: :class:`~ela.tools.registry.ToolRegistry` refuses
        ``True`` beside ``idempotent`` ``False``, and silence.
        """

    @property
    def audit_numbers(self) -> frozenset[str]:
        """The keys of this tool's result whose **integers** enter ``TOOL_EXECUTED`` (M13.2).

        Declared, never defaulted — the form of :attr:`idempotent` — and closed: a key is a path
        into the result (``stdout.total``) whose first segment is one of the tool's output keys,
        and :class:`~ela.tools.registry.ToolRegistry` refuses a tool that declares nothing or a key
        outside its result. The values pass through :func:`audited_numbers`, which lets through an
        integer or ``None`` and nothing else: the first door through which a tool writes facts of
        its own into a log that is never redacted, built narrow (ADR 0047).
        """

    async def prospect(self, arguments: JsonMapping) -> Prospect:
        """What this call would meet now: what to show, and whether to ask at all.

        Read-only and **not an execution**: it is how a question learns the facts it must name
        before anybody answers it, and how the executor learns that there is nothing to ask
        (M13.1 dec. G, and the rule of ADR 0045 §6-bis). Asked of the component that holds the
        root and the shared classification, so that no second definition of «what would happen»
        can drift from the one that really refuses.

        A tool that works on no path answers an empty :class:`Prospect`: nothing to show, and
        nothing to refuse in advance.

        ``async`` because it reads the filesystem, which is the criterion of ADR 0005 §1 — and
        because a port has one mode: a sync member on an async port would be the first place
        somebody stopped being able to say what this one is.
        """

    async def asserted(self, arguments: JsonMapping) -> Prospect:
        """What this call **asserts**, answered without looking at any machine (M13.3, ADR 0048).

        Beside :meth:`prospect`, which looks: for a step placed on a node whose verifier reads the
        machine, the Core's disk is the wrong one to look at, so the question names what the plan
        asserts — the path as written, and for ``fs.write`` whether it creates or overwrites, in
        the tool's words — and the node's tool, which is this code, compares that with its own disk
        before acting. Only what needs no disk may refuse here: the shape of the arguments and the
        grammar of the path. A tool that works on no path answers an empty :class:`Prospect`.
        """

    @property
    def stop_point(self) -> StopPoint:
        """Where this tool listens for the stop of its task (M6.3c, ADR 0054 §3).

        Declared, never defaulted — the form of :attr:`relocatable` —: a tool that says nothing is
        refused by :class:`~ela.tools.registry.ToolRegistry`, and one with no wait before its effect
        says ``here=None`` in so many words."""

    async def worst_case(self, arguments: JsonMapping) -> WorstCase | ErrorMetadata | None:
        """The most this call can cost, before it is made (§30; M14.1, ADR 0057).

        ``None`` for a tool that spends nothing, which is every tool but the ones that call a paid
        provider. A tool that spends answers with the same steps its run takes up to the network —
        the arguments, the route, the provider — and an error when one of them refuses: a call
        that cannot be bounded is a call that is not made. The executor asks it where the
        ``STARTED`` record is born, on the Core; a node asks its own copy before running an order,
        and does not spend beyond what the Core reserved.
        """

    async def execute(
        self, decision: PermissionDecision, arguments: JsonMapping, stop: TaskStop
    ) -> ExecutionResult:
        """Run the capability under ``decision``; :class:`NotAllowedError` if it does not allow.

        ``stop`` is the stop of the task (M6.3c): the tool calls :meth:`TaskStop.listen` at its
        point, and :class:`ToolStopped` leaves the call there, before any effect."""


@runtime_checkable
class ToolRegistryPort(Protocol):
    """The tools ELA can execute, one per capability (§28; ADR 0013).

    Synchronous and read-only, like :class:`CapabilityRegistryPort`: a table of tools already
    built, fixed when the registry is. The key of every entry is the tool's own ``capability_id``
    — a tool cannot be registered under another capability — and two tools for one capability at
    construction are an :class:`AlreadyExistsError`. Its callers are the executor, the
    orchestrator, the planner, the readiness of a plan, and since M13.12 the route of the policies,
    which asks a tool its ``prospect`` before a policy is born (ADR 0062; decision 7).
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

    @property
    def failure_codes(self) -> frozenset[str]:
        """The codes this verifier can report: the vocabulary of its failures (ADR 0014 §2).

        A member of the port since M13.3 (ADR 0048): a node verifies ``fs.*`` on its own machine
        and sends the codes back, and the Core accepts a verdict only in this vocabulary — a code
        outside it is a doubt, and the step fails ``verification.missing``.
        """

    @property
    def reads_the_machine(self) -> bool:
        """Whether this verifier reads the disk of the machine it runs on (M12.2, ADR 0038 §14) —
        or anything else that lives there: the Core's stores (ADR 0038 §14), a page open in a
        process of this machine (M13.4, ADR 0052 §2).

        Declared, never defaulted — the form of ``ToolPort.idempotent``: forgetting it must not
        read as a no. A verifier that reads the Core's disk proves an effect only if the effect
        happened on the Core's disk, so its capability does not travel to a node that is not this
        one (M12.1, D15), and the orchestrator refuses such a node with ``UNVERIFIABLE``.
        """

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
PROVIDER_SPEND_LIMIT: Final = "provider.spend_limit"
"""The provider refused the request because one of its monthly spend limits is reached — the one
the organization set in the console, which is the **second cap**, a workspace's, or the usage
tier's cap (M14.1, ADR 0057). Never retried: it holds until the provider's month turns or somebody
raises the limit. It does **not** say that ELA's count is wrong: the provider's month need not be
ELA's, so the limit can be reached with ELA in order with its own cap. The reason names the limit,
the Core adds what ELA counted of its cap, and the guide lists the causes (review of ``be7f131``).
A name of its own instead of :data:`PROVIDER_BAD_REQUEST` and :data:`PROVIDER_RATE_LIMITED`, which
is what it was until M14.1: named ``provider.workspace_limit`` until the console of 2026-10-07
showed that the limit that holds is the organization's."""
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
        PROVIDER_SPEND_LIMIT,
    }
)
"""The closed vocabulary of ``ProviderResult.error.code`` (ADR 0020 §7).

It lives here, with the port, and not inside an adapter, for the reason §26 exists: a caller must
be able to tell an authentication failure from an overload without importing — or even knowing —
the provider that produced it. A second provider reports the same fifteen codes or it is not
interchangeable with the first — fifteen since M14.1, which added :data:`PROVIDER_SPEND_LIMIT`
(ADR 0057).

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

    async def worst_case(self, request: ProviderRequest) -> WorstCase | ErrorMetadata:
        """The most ``request`` can cost, worked out without the network (§30; M14.1, ADR 0057).

        Computed with the functions that build the call — the model ``complete`` would choose and
        the output budget the payload would carry —, never with a second estimate. An error when
        the request could not be made at all, with the code ``complete`` would answer; never an
        exception, like ``complete``. A model with no price is a :class:`~ela.domain.WorstCase`
        with no amount.
        """


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
"""Too many requests, or too many at once — ten concurrent on the plan ADR 0034 §1.4 measured."""
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
class ListeningPort(Protocol):
    """Where ELA opens the microphone of the machine it runs on (§9, §10, §11; M11.2, ADR 0036).

    The first port through which something comes **in from the room**. Everything ELA received
    until now was digital — a database, a screen, an HTTP response — and everything it sent out
    was words of its own. A microphone is of another kind:

    **it is the first of ELA's data that contains people who are not the user.** A screen capture
    photographs what the user chose to have in front of them; a recording takes whoever was in the
    room, including somebody who never agreed and does not know.

    Which is why the port hands back a transcript and never audio. The raw material is not kept
    (M11.2 dec. E): recording and transcribing happen behind this one interface, the samples live
    on an anonymous inode inside the adapter, and **no byte of audio crosses into the Core**. One
    port rather than two is not economy — it is that decision made structural, the same shape
    ADR 0034 §6 used when synthesis arrived as a typed callable instead of a port of its own.

    Four clauses, and the last is the one no other port here needs:

    * **It does not choose what to listen to.** The caller says *for how long*, and nothing else.
    * **It decides nothing** (architecture rule 34): it carries segments, probabilities, the peak
      of the signal and how it ended. What "no words" *means* is the caller's to work out, and it
      cannot be worked out without the peak.
    * **It does not fail — it reports.** A denied permission, a machine with no input device, an
      operating system with no such notion: all come back as a
      :class:`~ela.domain.RawTranscript` that says how it ended, never as an exception.
    * **A cancelled call closes the microphone.** ADR 0033 §4's promise with the sign reversed,
      and graver: an orphaned ``say`` is ELA still talking, an orphaned recorder is **ELA still
      listening after being told to stop**. A child outlives its parent — ``launchd`` adopts it —
      so the child carries its own deadline too, and that is why the longest an orphaned
      microphone can live is the ceiling plus its margin rather than "until somebody notices".
    """

    async def available(self) -> bool:
        """Whether this machine can listen at all — no permission asked, no side effect.

        Its own member for the reason ADR 0028 gave ``UnsupportedProbe``: "ELA on Linux hears
        nothing" deserves to be an answer with a name and a test rather than a gap somebody finds.
        """

    async def listen(self, seconds: int) -> RawTranscript:
        """Open the microphone for ``seconds``, and answer with what was heard.

        Returns when the recording and its transcription are both over. The duration of the call
        is therefore longer than ``seconds``, and the caller's timeout has to allow for both.
        """


LISTEN_DISABLED: Final = "listen.disabled"
"""The user switched listening off: ``ELA_LISTEN_ENABLED`` is false.

Its own code and not one shared with the missing device, for the reason ADR 0033 §9 gives the
voice: "you turned it off" must not arrive wearing the face of "this machine cannot hear". The
switch is a convenience and **not the defence** (M11.2 dec. K) — the defence is the capability,
the Guardian and the ceiling on how long the device stays open."""
LISTEN_UNSUPPORTED: Final = "listen.unsupported"
"""This operating system has no listening ELA knows about."""
LISTEN_DENIED_BY_SYSTEM: Final = "listen.denied_by_system"
"""macOS refuses the microphone to whoever is running ELA.

Read **in the instant**, never from the periodic belief: a belief on a cadence is for telling, and
when something must *happen* the fact is read again (ADR 0029 §7). And from a denied state ELA
does not open the device at all — measured on 2026-09-09, opening it succeeds and delivers
silence, which a transcriber turns into words nobody said.

Not a :class:`~ela.domain.SensorCause`: with the permission denied the probe still sees the device
and still reads whether anyone is using it, so no state of §11 changes and a cause for it could
never fire (ADR 0028 §4, and M11.2 dec. I, which measured it)."""
LISTEN_PERMISSION_UNREADABLE: Final = "listen.permission_unreadable"
"""The microphone permission could not be read at all — the probe timed out, died, or spoke
nonsense.

**A doubt, and a doubt is not a yes** (§33). Its own code and not
:data:`LISTEN_DENIED_BY_SYSTEM`, because "the system refuses me" and "I could not find out" are
different facts with different answers, and collapsing them is the exact mistake this milestone
exists to avoid — one step further back. The sibling of ``screen.not_observable`` (M10.2)."""
LISTEN_NO_INPUT_DEVICE: Final = "listen.no_input_device"
"""There is no input device at all — the case of every CI runner."""
LISTEN_NO_SIGNAL: Final = "listen.no_signal"
"""Every sample was silence, so nothing was handed to the transcriber.

**Not a threshold: the peak was zero**, which is the fact that no sample differed from silence. It
catches what the preflight cannot — a granted permission with a muted device, a hardware switch, a
dead input — and it exists because a transcriber has no way to say "I heard nothing": the absence
of signal reaches it as signal and it answers with language.

The limit it does **not** cover, declared rather than solved: a quiet room has a small true
signal, not a zero one, and there the transcriber can still invent. What stands there is the
structural answer — an approval that names what ELA understood before acting — and it belongs to
the milestone that first turns a transcript into a command (ADR 0018 §6)."""
LISTEN_TIMEOUT: Final = "listen.timeout"
"""A helper outstayed its deadline and was stopped."""
LISTEN_FAILED: Final = "listen.failed"
"""A helper ended badly. What it *means* is not ELA's to guess (ADR 0033 §9)."""
LISTEN_TRANSCRIPTION_UNAVAILABLE: Final = "listen.transcription_unavailable"
"""The transcriber or its model is missing, or its digest is not the one ELA was told to expect.

Nothing is heard when ELA cannot check what would be doing the hearing: what decides what ELA
believes was said is a file whose fingerprint is declared, never a name resolved through
``PATH`` (ADR 0029 §3)."""
LISTEN_TRANSCRIPTION_FAILED: Final = "listen.transcription_failed"
"""The transcriber ran and ended badly."""
LISTEN_LANGUAGE_UNSUPPORTED: Final = "listen.language_unsupported"
"""The configured language is not one the transcriber has.

ADR 0030 §8 literally: without this code, "you were configured wrongly" would arrive as "you said
nothing", and the two send whoever is investigating in opposite directions."""

LISTEN_ERROR_CODES: Final = frozenset(
    {
        LISTEN_DISABLED,
        LISTEN_UNSUPPORTED,
        LISTEN_DENIED_BY_SYSTEM,
        LISTEN_NO_INPUT_DEVICE,
        LISTEN_NO_SIGNAL,
        LISTEN_PERMISSION_UNREADABLE,
        LISTEN_TIMEOUT,
        LISTEN_FAILED,
        LISTEN_TRANSCRIPTION_UNAVAILABLE,
        LISTEN_TRANSCRIPTION_FAILED,
        LISTEN_LANGUAGE_UNSUPPORTED,
    }
)
"""The closed vocabulary of :attr:`~ela.domain.RawTranscript.error` (M11.2 dec. J).

Here and not in the adapter, for the reason ADR 0020 §7 put the model provider's codes here: a
caller must tell "the microphone is refused" from "there is no microphone" **without knowing who
produced the answer**.

Eleven of them, and three exist only because the measurement of 2026-09-09 said a refusal is
silent:
:data:`LISTEN_DENIED_BY_SYSTEM`, :data:`LISTEN_NO_SIGNAL` and :data:`LISTEN_NO_INPUT_DEVICE` are
what keep "you said nothing", "I was refused" and "there is nothing here to hear with" from
arriving as the same empty answer.
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


# --------------------------------------------------------------------------------------
# The terminal (§18; M13.2, ADR 0047)
# --------------------------------------------------------------------------------------


class Ending(StrEnum):
    """How a command ended, as the launcher saw it (M13.2 dec. 5, 7, 9; M6.3c).

    More than the tool's ``ended`` — ``exited``, ``signalled``, ``stopped_by_ela``,
    ``stopped_with_the_task`` —, because ELA stops a group for two reasons that must not be read as
    one another, and a run that never started is not a run that ended.
    """

    EXITED = "exited"
    """The program ended by itself with a code."""
    SIGNALLED = "signalled"
    """The program was ended by a signal nobody in ELA sent."""
    TIMED_OUT = "timed_out"
    """ELA stopped the group: the timeout came first."""
    STOPPED = "stopped"
    """ELA stopped the group: ELA itself was stopping (ADR 0038 §11)."""
    HALTED = "halted"
    """ELA stopped the group: the task of the command was stopped (M6.3c, ADR 0054 §3)."""
    NOT_STARTED = "not_started"
    """The kernel refused the ``exec`` — a format it does not know, a missing interpreter."""


@dataclass(frozen=True, slots=True)
class Command:
    """What a program receives, **decided by the tool and executed to the letter** (M13.2 dec. 15).

    The decisions stay in the gate: ``argv`` with the declared path first, the closed environment,
    the folder, the timeout, the breath between ``SIGTERM`` and ``SIGKILL``, and how much of the
    head and of the tail of each stream to keep. The launcher adds nothing of its own — no ``PATH``
    search, no shell, no inherited variable, no stdin.
    """

    argv: tuple[str, ...]
    environment: tuple[tuple[str, str], ...]
    folder: str
    timeout: float
    grace: float
    head: int
    tail: int


@dataclass(frozen=True, slots=True)
class Captured:
    """One stream as the launcher kept it while reading: raw bytes, and how many there were.

    ``head`` is the first bytes, up to the command's ``head``; ``tail`` the last ones of what came
    after, up to its ``tail``; ``total`` every byte read. When everything fits, ``head + tail`` is
    all of it. Decoding, and cutting on a character, are the tool's (M13.2 dec. 8).
    """

    head: bytes = b""
    tail: bytes = b""
    total: int = 0


@dataclass(frozen=True, slots=True)
class Ran:
    """What happened to a command: how it ended, its code or its signal, and its two streams.

    ``failure`` is set only for :attr:`Ending.NOT_STARTED`, with the operating system's words —
    the error's type and message, never an argument.
    """

    ending: Ending
    code: int | None = None
    signal: int | None = None
    stdout: Captured = Captured()
    stderr: Captured = Captured()
    failure: str | None = None


@runtime_checkable
class CommandLauncher(Protocol):
    """How ``terminal.run`` starts a program on this machine (§18; M13.2 dec. 15, ADR 0047).

    A port because a tool may not reach ``ela.infrastructure`` (import contract 12), and because the
    whole of what a program receives is decided in the gate and handed over as a :class:`Command`.
    The contract every implementation keeps:

    * the child gets exactly ``argv``, exactly ``environment``, starts in ``folder``, and reads the
      end of a file on stdin — never ELA's TTY;
    * it lives in **a process group of its own**, and whichever way ELA stops waiting — the
      timeout, the stop signal of ADR 0038 §11, a cancellation — the group is stopped with
      ``SIGTERM``, then after ``grace`` with ``SIGKILL``, and **is empty when this returns**;
    * the streams are capped **while they are read**, and a grandchild that holds a pipe does not
      hold the launcher;
    * it does not fail, it reports: a refused ``exec`` is :attr:`Ending.NOT_STARTED`. Only a
      cancellation propagates, after the group is stopped.
    """

    async def run(self, command: Command, stop: TaskStop) -> Ran:
        """Start ``command``, wait for it within its timeout, and say how it ended.

        ``stop`` is the stop of the command's task (M6.3c): raised while the program runs, the
        group is stopped as for the timeout, and the ending is :attr:`Ending.HALTED`."""


# --------------------------------------------------------------------------------------
# The browser (§19; M13.4, ADR 0052)
# --------------------------------------------------------------------------------------


NAVIGATION: Final = "the navigation"
"""Where :meth:`Browser.open` listens for the stop of its task: the request of the page leaves after
it (M6.3c, ADR 0054 §3). ``browser.read``'s point, and only a listening for ``browser.act``."""


class BrowserError(PortError):
    """Something a browser of ELA's could not do (M13.4). The tool turns each kind into a code;
    the message is a type's name or a sentence of the adapter's, never a page, an address or an
    argument, which a failure carries into the audit (§57)."""


class BrowserNotInstalled(BrowserError):
    """The browser the lock names is not on this machine: nobody ran the command that installs
    it."""


class SiteUnreachable(BrowserError):
    """The page did not answer: a name that does not resolve, a refused connection, a certificate
    the browser does not accept. What went wrong is the engine's type name, never its message."""


class BrowserUnsupported(BrowserError):
    """ELA does not know where the browser would be on this system, so it cannot say whether it is
    there: not «not installed», which a command could fix, but «not looked» (M13.4; review of the
    summary, 2026-09-30)."""


class BrowserStopped(BrowserError):
    """ELA was stopping, and its browsers were closed: the stop signal of ADR 0038 §11."""


class PageGone(BrowserError):
    """No page under this identifier: closed, never opened, or opened by a process that is gone."""


class BrowserFailed(BrowserError):
    """Anything else the engine raised, named by its type (ADR 0052): a poor diagnosis, and said."""


@dataclass(frozen=True, slots=True)
class Opened:
    """A page the browser opened, and what the opening met (M13.4).

    ``page`` is the identifier every later call names; ``status`` the HTTP status of the main
    document, ``None`` when no response came back; ``address`` where the main frame is now;
    ``left`` the address of a navigation of the main frame that the boundary refused — the request
    was never sent —, ``None`` when there was none. An address and not an origin: what an origin is,
    the tool says, once (``ela.tools.browser.origin_of``).
    """

    page: str
    status: int | None
    address: str
    left: str | None


@dataclass(frozen=True, slots=True)
class Field:
    """What an element declares of itself, lower-cased: its ``type`` and its ``autocomplete``
    attributes, empty when absent. The tool decides what they mean (M13.4, ADR 0052)."""

    type: str
    autocomplete: str


@dataclass(frozen=True, slots=True)
class Glanced:
    """What the verifier saw in its one look at a page (M13.4).

    ``text`` is the text under the selector it asked about — ``None`` when that selector does not
    find exactly one element —; ``shown`` whether the text it waited for appeared, ``None`` when it
    waited for none; ``left`` the address of the last navigation the boundary refused since the
    opening.
    """

    text: str | None
    shown: bool | None
    left: str | None


@dataclass(frozen=True, slots=True)
class Visit:
    """What a browser call would do, as the question names it (M13.4 dec. G, ADR 0052).

    Beside :class:`Invocation`, which is a command's: ``site`` is the target and ``label`` what the
    tool calls it, ``does`` the tool's sentence — that the browser is empty, and for an action that
    what it sends is not taken back —, ``address`` in full, ``gestures`` one line each in the tool's
    words, ``expect`` the text an action waits for (empty for a read), and ``timeout_seconds``.
    **Not a** :class:`Target`: its ``exists`` would be a fact about a site nobody visited, and a
    field filled with a fact nobody looked at is the false diagnosis of ADR 0045 §5.
    """

    site: str
    label: str
    does: str
    address: str
    gestures: tuple[str, ...]
    expect: str
    timeout_seconds: int


@runtime_checkable
class Browser(Protocol):
    """A browser of ELA's own, with an empty profile for every page (§19; M13.4, ADR 0052).

    **A mechanism, not a policy.** Every decision is the tool's and reaches the adapter as data: the
    address, which navigations of the main frame may happen (``allowed``, a function of the tool),
    which element, which value. What an implementation keeps:

    * each :meth:`open` starts a browser of its own, with an empty profile, and **closes it** when
      the page is closed, looked at, or refused — nothing passes from one page to the next;
    * a navigation of the main frame that ``allowed`` refuses **is not sent**, and
    :attr:`Opened.left`
      names it;
    * the browser is started so that a signal to ELA's process group does not close it: the stop is
      ELA's, through the stop signal of ADR 0038 §11, which raises :class:`BrowserStopped` in what
      was running — and **from the moment it is raised no navigation and no gesture leaves**,
      whenever that moment is: :meth:`open` and every use of a page raise
      :class:`BrowserStopped`, and a page that was being opened is closed by its opening (M13.4c);
    * a page kept with :meth:`keep` waits for :meth:`glance`, and an implementation closes it
      itself if nobody looks before its deadline;
    * when :meth:`close` returns, the kernel knows no process of that page's browser any more.
    """

    async def installed(self) -> bool:
        """Whether the browser the lock names is on this machine. No page, no network."""

    async def open(self, address: str, allowed: Callable[[str], bool], stop: TaskStop) -> Opened:
        """Open ``address`` in a new, empty browser; a navigation ``allowed`` refuses is not sent.

        ``stop`` is listened to **right before the navigation**, as :data:`NAVIGATION` (M6.3c): a
        stopped task leaves the page unopened and the site unvisited.

        :raises BrowserNotInstalled, SiteUnreachable, BrowserStopped, BrowserFailed, ToolStopped:
            and nothing stays open behind the exception.
        """

    async def count(self, page: str, selector: str) -> int:
        """How many elements ``selector`` finds on the page."""

    async def field(self, page: str, selector: str) -> Field:
        """What the one element ``selector`` finds declares of itself."""

    async def fill(self, page: str, selector: str, value: str) -> None:
        """Write ``value`` in the one element ``selector`` finds."""

    async def click(self, page: str, selector: str) -> None:
        """Click the one element ``selector`` finds."""

    async def text(self, page: str, selector: str | None) -> str:
        """The text of the one element ``selector`` finds, or of the whole page when ``None``."""

    async def title(self, page: str) -> str:
        """The title of the page."""

    async def left(self, page: str) -> str | None:
        """The address of the last navigation the boundary refused since the opening, or
        ``None``."""

    async def keep(self, page: str) -> None:
        """Hand the page over to the verifier: it stays open until :meth:`glance`, or its deadline.

        Never raises: a page that is not there any more — ELA was stopping — is found gone by the
        verifier, which says so (``browser.page_gone``)."""

    async def glance(
        self, page: str, *, selector: str | None, expect: str | None, seconds: float
    ) -> Glanced:
        """The verifier's one look, and the page is released with it.

        The text under ``selector`` when one is asked (or of the page, when ``selector`` is ``None``
        and ``expect`` is too), and whether ``expect`` appeared within ``seconds``.
        """

    async def close(self, page: str) -> None:
        """Close the page and its browser; nothing of it runs when this returns. Idempotent, and
        never raises: what cannot be closed any more is closed already. **The closing runs to its
        end whoever waits for it** (M13.4b): a caller cancelled while it waits gets its
        cancellation, and the page's processes still go."""


# --------------------------------------------------------------------------------------
# The guided session of the browser (M14.3, ADR 0060)
# --------------------------------------------------------------------------------------


GUIDED_LOOKS: Final = "guided.looks"
"""ELA stopped the session: its model asked for one gesture more than the looks the yes allowed."""
GUIDED_DURATION: Final = "guided.duration"
"""ELA stopped the session at the end of the seconds the yes allowed, the wait for a yes included.
"""
GUIDED_COST: Final = "guided.cost"
"""ELA stopped the session: a call did not fit in what is left of its reservation, or had no
price."""
GUIDED_TOOLS_CHANGED: Final = "guided.tools_changed"
"""The tools of a call, or of the session's start, were not exactly the session's two (decision 22).
"""
GUIDED_MODEL_CHANGED: Final = "guided.model_changed"
"""A call asked for another model than the one the router chose and the question named."""
GUIDED_MAX_TOKENS: Final = "guided.max_tokens"
"""A call with no ``max_tokens``, or more than the session declared."""
GUIDED_CACHE: Final = "guided.cache"
"""A call that asked for the cache, whose writes the worst case of ADR 0057 §2 does not price."""
GUIDED_UNCHECKED: Final = "guided.unchecked"
"""A call before the tools of the session's start were checked (decision 22)."""
GUIDED_PERMISSION_ASKED: Final = "guided.permission_asked"
"""The session asked for a permission — an anomaly, denied by the session —, and ELA stopped it."""
GUIDED_NOT_INSTALLED: Final = "guided.not_installed"
"""The binary of the session is not on this machine."""
GUIDED_CAP_BELOW_ONE_CALL: Final = "guided.cap_below_one_call"
"""The most the session may spend is below the worst case of one call: no call could go out."""
GUIDED_FOLDER_CHANGED: Final = "guided.folder_changed"
"""The session's folder does not hold exactly what ELA wrote, or cannot be prepared."""
GUIDED_ROUTE_CHANGED: Final = "guided.route_changed"
"""At the yes the router chose another model than the one the question named: never an effect
other than the one approved."""
GUIDED_STOPPED: Final = "guided.stopped"
"""The task was stopped while the session ran, and ELA interrupted it: its calls are counted."""
GUIDED_FAILED: Final = "guided.failed"
"""The session ended with an error of its own, not one of ELA's limits."""
GUIDED_UNRESERVED: Final = "guided.unreserved"
"""The step has no reservation of the cap: a session spends, and nothing was set aside for it."""
GUIDED_SESSION_GONE: Final = "guided.session_gone"
"""A call or a gesture for a session that is not open."""
GUIDED_ERROR_CODES: Final = frozenset(
    {
        GUIDED_LOOKS,
        GUIDED_DURATION,
        GUIDED_COST,
        GUIDED_TOOLS_CHANGED,
        GUIDED_MODEL_CHANGED,
        GUIDED_MAX_TOKENS,
        GUIDED_CACHE,
        GUIDED_UNCHECKED,
        GUIDED_PERMISSION_ASKED,
        GUIDED_NOT_INSTALLED,
        GUIDED_CAP_BELOW_ONE_CALL,
        GUIDED_FOLDER_CHANGED,
        GUIDED_ROUTE_CHANGED,
        GUIDED_STOPPED,
        GUIDED_FAILED,
        GUIDED_UNRESERVED,
        GUIDED_SESSION_GONE,
    }
)
"""Every code a guided session can end with (M14.3, ADR 0060): the tool's ``error_codes``."""


@dataclass(frozen=True, slots=True)
class CallRequest:
    """What one call of a guided session asks for, read from its body by the gateway's adapter:
    numbers and names, never the text (§57). ``None`` where the body does not say — a doubt the
    budget refuses (§33)."""

    model: str | None
    max_tokens: int | None
    tools: tuple[str, ...] | None
    cached: bool
    request_bytes: int


@dataclass(frozen=True, slots=True)
class Forwarded:
    """A call on its way back from the provider: the status, the type of the body, the body
    **event by event**, and what the call consumed once the body is over — ``None`` when the end
    never came, an outcome nobody knows (ADR 0057 §10)."""

    status: int
    content_type: str
    chunks: AsyncIterator[bytes]
    usage: Callable[[], ProviderUsage | None]


@runtime_checkable
class ModelGateway(Protocol):
    """Where a call of a guided session leaves the machine (§26, §30, §57; M14.3, ADR 0060): the
    adapter that holds the key, beside the one :class:`ModelProvider` is.

    The session never sees the key: it sends its calls to ELA's gateway with a token of its own,
    and this port puts the key on a call **only with an** :class:`~ela.domain.Admission` — what the
    budget of the session minted for it (architecture rule 65).
    """

    async def read(self, body: bytes) -> CallRequest:
        """What the call in ``body`` asks for: its model, ``max_tokens``, the names of its tools,
        whether it asks for the cache, and its bytes. A body that is not a call says nothing."""

    async def worst(self, model: str, max_tokens: int) -> Decimal | None:
        """The worst case of one call to ``model`` with ``max_tokens``, with the function of ADR
        0057 §2 — the price list's —, or ``None`` for a model with no price."""

    async def forward(self, admission: Admission, body: bytes, beta: str | None) -> Forwarded:
        """Send ``body`` as it is to the provider with the key, and hand its answer back event by
        event. Never raises: a call that could not leave answers with a status of its own and a
        usage that says it was not sent."""


@dataclass(frozen=True, slots=True)
class OpenedSession:
    """A guided session the room of ELA opened for a step (M14.3, ADR 0060): its id, the token the
    session presents to the gateway — 32 random bytes, valid for this session only, from this
    machine only, while it lives —, the reservation it spends, and the path of its gateway."""

    session: StepId
    token: str
    reservation: Reservation
    path: str


@dataclass(frozen=True, slots=True)
class Gesture:
    """One gesture of a guided session, as it ended: the text the session reads — the result of
    the child task, or the reason of its end —, how its task ended, and whether it was a
    ``browser.act`` that acted."""

    text: str
    state: TaskState
    acted: bool


@dataclass(frozen=True, slots=True)
class SessionTally:
    """A guided session, closed: what it consumed — the usage that closes its reservation — and its
    numbers. Only numbers: the calls one by one as (model, input tokens, output tokens, bytes)."""

    usage: ProviderUsage
    calls: int
    unknown: int
    input_minus_bytes_max: int | None
    looks: int
    refused: int
    acts: int
    per_call: tuple[tuple[str, int, int, int], ...]


@runtime_checkable
class Gestures(Protocol):
    """The room of the guided sessions (§19, §27; M14.3, ADR 0060): what ``browser.guided`` asks.

    **Every gesture of a session is a child task** of the session's task, walked by the runner
    with the Guardian, the grant, the tool, the verifier and the audit of every task: one door, and
    no second one. The room also holds each session's budget and token, which the gateway reads.
    """

    async def open(
        self, task_id: TaskId, step_id: StepId, *, sites: tuple[str, ...], tools: frozenset[str]
    ) -> OpenedSession | ErrorMetadata:
        """Open the session of this step on the reservation the cap holds for it, or say why not."""

    async def start(self, session: StepId, tools: Sequence[str]) -> ErrorMetadata | None:
        """The tools the session's start lists: exactly its two, or the session is halted
        (decision 22). No call is admitted before this answered."""

    async def gesture(
        self, session: StepId, capability: CapabilityId, arguments: JsonMapping
    ) -> Gesture:
        """One gesture the model asked for: a child task, planned, walked, and waited for."""

    async def halt(self, session: StepId, error: ErrorMetadata) -> None:
        """Stop the session for ``error``: what the tool reads in :meth:`halted`."""

    async def halted(self, session: StepId) -> ErrorMetadata:
        """What ELA stopped the session for, once it does: awaited by the tool beside the end of
        the session, the stop of its task and its duration."""

    async def close(self, session: StepId, *, reason: str) -> SessionTally:
        """Close the session: its live gestures stopped, its calls closed, its token gone."""

    async def is_open(self, session: StepId) -> bool:
        """Whether the session is still open in this room: a call of it can still be admitted."""

    async def gesture_ids(self, task_id: TaskId, session: StepId, count: int) -> tuple[TaskId, ...]:
        """The ids of the first ``count`` gestures of ``session``: derived, never stored."""


@dataclass(frozen=True, slots=True)
class SessionPlan:
    """What a guided session is launched with, all of it written by ELA (M14.3, ADR 0060): the
    sentence, ELA's instructions and what the two tools are — the grammar of a selector among it
    (decision 44 of the review of the second round) —, the model and ``max_tokens`` the gateway
    holds it to, the address of the gateway and the token, and how long it may last."""

    session: StepId
    goal: str
    instructions: str
    read_description: str
    act_description: str
    model: str
    max_tokens: int
    gateway: str
    token: str
    seconds: int


@dataclass(frozen=True, slots=True)
class SessionHost:
    """What the session calls back into, while it runs: the tools of its start, each gesture its
    model asks for, and a request for a permission — an anomaly, denied by the session (§33)."""

    started: Callable[[tuple[str, ...]], Awaitable[ErrorMetadata | None]]
    gesture: Callable[[str, JsonMapping], Awaitable[str]]
    asked: Callable[[], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class SessionEnd:
    """How a guided session ended, as the session wrote it: its last text — content from outside
    (ADR 0059) —, the subtype of its end, the cost Claude Code estimated beside ELA's (never in its
    place), its version, the permissions it denied, and whether no process of it is left."""

    text: str
    subtype: str
    reported_cost: str | None
    version: str | None
    denials: int
    closed: bool


@dataclass(frozen=True, slots=True)
class SessionHandle:
    """A session that was launched: what ends with it, and how to stop it — the interrupt first,
    then the end of its input, then ``SIGKILL`` after a grace (decision 11)."""

    ended: Awaitable[SessionEnd]
    interrupt: Callable[[], Awaitable[None]]


@runtime_checkable
class AgentSession(Protocol):
    """A session of Claude Code launched by ELA as a program (§19, §24; M14.3, ADR 0060).

    It has **no tools of its own** — no shell, no file, no network —, only the two gestures of ELA,
    in-process; its folder is ELA's, empty but for what ELA writes and checks before every launch;
    its environment is closed, and its only way to a model is ELA's gateway, with a token.
    """

    @property
    def tools(self) -> frozenset[str]:
        """The names of the two tools every session offers its model: the budget holds every call
        to exactly these."""

    async def ready(self) -> ErrorMetadata | None:
        """Whether a session could be launched now: the binary there, the folder preparable."""

    async def running(self, session: StepId) -> bool:
        """Whether a process of ``session`` is still running on this machine: read from the
        kernel, never from what the session said."""

    async def launch(
        self, reservation: Reservation, plan: SessionPlan, host: SessionHost
    ) -> SessionHandle | ErrorMetadata:
        """Launch the session on money already set aside. An :class:`~ela.domain.ErrorMetadata`
        when it could not start — its folder changed, its binary gone —, and nothing ran."""

    async def sweep(self) -> int:
        """At start-up, what a crash left: every session's folder deleted, and a session's process
        still running killed first. No session has a right to live then — its gateway went with
        the process that is starting again. Answers how many folders it deleted."""
