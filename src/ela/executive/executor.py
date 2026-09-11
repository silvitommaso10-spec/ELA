"""The executor (spec §27): the pipeline Capability → Guardian → Authorization → Tool → Audit.

One call of :meth:`Executor.execute` runs **one step** of a plan (ADR 0013 §1): the step declares
exactly one capability, the executor asks the Guardian about it with the arguments and the
grant that would cover it, and — only with an ``ALLOWED`` decision in hand — spends the grant,
calls the tool and records ``TOOL_EXECUTED``. This module is the only caller of ``Tool.execute``
in the Core (rule 16), and the step never stays RUNNING after a call that ran: the executor
closes it with ``complete_step`` or ``fail_step``. Which step runs next is the orchestrator's
question (M6.2), not this module's.

The outcomes of the Guardian are moves of the engine (ADR 0013 §5):

* ``DENIED`` → ``engine.deny``: the task is DENIED, nothing ran.
* ``REQUIRES_APPROVAL`` → an :class:`~ela.domain.Approval` built from the decision (its targets
  are the decision's, ADR 0012 §6) and ``engine.request_approval``: the task waits.
* ``ALLOWED`` → ``consume`` if the decision rests on the grant, then the tool, then the audit,
  then the **verifier**, then the step is closed. A grant that turns out expired or exhausted
  at ``consume`` asks again; one that vanished fails the step with :data:`GRANT_VANISHED`.

Execution is not proof of success (§63, ADR 0014): a SUCCEEDED result is what the tool *says*;
the verifier of the capability checks the world against the step's ``success_conditions`` and
only its pass completes the step (``complete_step`` has one caller, this module: rule 17). A
failed verification is a contradiction between the tool's claim and reality — a doubt (§33) —
so the step **and the task** are FAILED with one :class:`~ela.domain.ErrorMetadata` that says
what, why, which tool, which device (§64). A tool that reports its own failure is a different
fact: the step fails, the task stays EXECUTING, and who decides about the task is the
orchestrator (ADR 0013 §5). An action that cannot be verified — no verifier, no condition, a
condition outside the verifier's vocabulary — is not executed at all.

One instant serves ``authorize`` and ``consume``: ``decision.created_at`` (ADR 0012 §6, ADR 0013
§6). A grant born from an approval has a deterministic id per approval, so a retry after a crash
finds it instead of minting a second one, and writes the ``AUTHORIZATION_GRANTED`` a crash may
have skipped (ADR 0013 §3, §8). What never enters the audit trail: the arguments, the tool's
output, and the content the verifier compared (§57).

Nothing the executor needs lives only in memory (M5.3, ADR 0015). The request for approval is
stored in the :class:`~ela.ports.ApprovalStore` before the task waits on it, and the user's
answer is read from there: a retry finds the GRANTED request of the step and turns it into the
grant. The tool's result is stored in the :class:`~ela.ports.ExecutionResultStore` before
``TOOL_EXECUTED`` names it. So a retry after a crash **resumes** instead of restarting: a stored
result of a RUNNING step means the tool ran, and the call continues from the first write that is
missing — the audit, the verification, the closing of the step — without asking the Guardian,
spending a grant or running the tool again. A step FAILED by a verification whose task is still
EXECUTING is failed now (ADR 0015 §7).

Since M12.2 a step may run on a node that is not this process (ADR 0038 §2). The pipeline is the
same up to the ``consume``; there the path **divides by id** — ``local`` runs here as it always
did, and for any other node ``execute`` writes an assignment and returns, with the work out and
the step still RUNNING. The rest arrives in two later calls, each inside a request of the node:
:meth:`Executor.begin` when it takes the work (the claim, the STARTED record of a tool that cannot
be repeated, the sensor event) and :meth:`Executor.deliver` when it brings back an
:class:`Envelope` (the gate, the result the Core mints from it, and the second half).
:meth:`Executor.finish` is the second half alone, for a step whose work expired leaving something
behind or whose delivery was written while the process died.

**The second half has one implementation** (:meth:`Executor._settled`): the local path reaches it
after the tool, the delivery after rebuilding the result, and neither has a branch of its own.
Two paths that should say the same thing and drift in silence is the failure ADR 0031 was written
about; here the defence is that there is one path, plus a parity test that runs the same plan here
and on a node and compares the two trails.

The instant between the tool's effect and the insert of its result — crash window 7a — was
declared unrepairable while every tool was idempotent, because the repair was to run the tool
again. Since M7.2 a tool may say it cannot be (``ToolPort.idempotent``), and for such a tool the
executor writes an :class:`~ela.domain.ExecutionResult` with status ``STARTED`` **before** the
call (ADR 0021 §1). A retry that finds that record with no outcome does not call the tool: the
step is failed with :data:`EXECUTION_INTERRUPTED`, and nobody pays twice for a completion nobody
read. The audit trail of a run carries what the call consumed, ``AuditEvent.usage`` from
``ExecutionResult.usage`` (§32).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime, timedelta
from enum import StrEnum
from types import MappingProxyType
from typing import Final, NamedTuple
from uuid import UUID, uuid5

from ela.devices import LOCAL_DEVICE_ID, PlacementDecision, ensure_placed
from ela.domain import (
    Actor,
    ActorKind,
    Approval,
    ApprovalId,
    ApprovalStatus,
    Assignment,
    AssignmentId,
    AssignmentState,
    AuditEvent,
    AuditEventId,
    AuditEventType,
    Authorization,
    AuthorizationId,
    CapabilitySpec,
    DeviceId,
    ErrorMetadata,
    ExecutionId,
    ExecutionResult,
    ExecutionStatus,
    JsonMapping,
    JsonValue,
    PermissionDecision,
    PermissionOutcome,
    ProviderUsage,
    StepId,
    StepState,
    Task,
    TaskId,
    TaskState,
    TaskStep,
)
from ela.executive.assignments import Assignments, WorkRejection
from ela.executive.errors import (
    AssignmentVoidError,
    DeliveryConflictError,
    ExecutorError,
    WorkNotYoursError,
)
from ela.permissions import (
    DEFAULT_AUTHORIZATION_TTL,
    Rule,
    authorization_from_approval,
    scope_covers,
    targets_of,
)
from ela.ports import (
    AlreadyExistsError,
    ApprovalStore,
    AssignmentExpiredError,
    AuditLog,
    AuthorizationNotUsableError,
    AuthorizationStore,
    AuthorizingGuardianPort,
    CapabilityRegistryPort,
    Clock,
    ExecutionResultStore,
    IdGenerator,
    NotAllowedError,
    NotFoundError,
    TaskRepository,
    ToolPort,
    ToolRegistryPort,
    VerifierPort,
    VerifierRegistryPort,
)
from ela.tasks.engine import TaskEngine
from ela.tasks.graph import GraphState

__all__ = [
    "APPROVAL_NAMESPACE",
    "AUTHORIZATION_NAMESPACE",
    "CONSUMING_RULES",
    "DEFAULT_APPROVAL_TTL",
    "DELIVERY_NAMESPACE",
    "EXECUTION_INTERRUPTED",
    "GRANT_VANISHED",
    "MAX_APPROVAL_TTL",
    "RECOVERED",
    "REPORTABLE",
    "STARTED_ID",
    "TOOL_EXCEPTION",
    "TOOL_REFUSED",
    "VERIFICATION_EXCEPTION",
    "VERIFICATION_FAILED",
    "Claimed",
    "Delivered",
    "Delivery",
    "Envelope",
    "Execution",
    "Executor",
    "Verification",
    "approved_targets",
    "check_envelope",
    "select_authorization",
]

AUTHORIZATION_NAMESPACE: Final = UUID("2d9b7f61-8c4a-4e0b-9f3d-6a1e5c7b8d90")
"""The UUID namespace of approval-born grants: ``uuid5(AUTHORIZATION_NAMESPACE, str(approval.id))``.

Arbitrary and fixed forever: one approval gives one grant, however many times the call that
uses it is retried (ADR 0013 §3). Changing it would change the id of every such grant.
"""

APPROVAL_NAMESPACE: Final = UUID("7c3e1a58-2f6b-4d90-a1c4-9e8b5d2f6a71")
"""The UUID namespace of requests for approval: ``uuid5(APPROVAL_NAMESPACE, str(decision.id))``.

Arbitrary and fixed forever: one ``REQUIRES_APPROVAL`` decision gives one request, and a second
request for the same step is born only from a second decision of the Guardian (ADR 0015 §6).
"""

DELIVERY_NAMESPACE: Final = UUID("5f1c7e34-9a02-4b6d-8e17-3c5a2d4f6b98")
"""The UUID namespace of a delivered outcome: ``uuid5(DELIVERY_NAMESPACE, str(assignment.id))``.

Arbitrary and fixed forever, the form of :data:`AUTHORIZATION_NAMESPACE` (M12.2, dec. B). One
assignment gives one outcome however many times the node delivers it, so a network that retries
writes the same row instead of a second one — which is what makes a redelivery idempotent without
a second key, and what repairs crash window ``A8`` by itself. An id the node chose could collide,
or be chosen to collide.
"""

RECOVERED: Final = "recovered"
"""The payload key an audit event written on a resumed run carries, set to ``True`` (ADR 0015 §5,
decision E): the numbers it holds were read at the retry, not at the run. Absent otherwise."""

DEFAULT_APPROVAL_TTL: Final = timedelta(hours=24)
"""How long a request for approval stays answerable (ADR 0013 §5, decision E).

A setting in M8.1, within :data:`MAX_APPROVAL_TTL`. Who expires a task left WAITING_APPROVAL is
not the executor: recovery or the Proactive Core, later.
"""
MAX_APPROVAL_TTL: Final = timedelta(days=7)
"""The longest ``approval_ttl`` the executor accepts (review of M5.1): no TTL without a cap, the
rule of M4.2 and M4.3. Above it is a configuration error, ``ValueError`` at construction."""

CONSUMING_RULES: Final[frozenset[Rule]] = frozenset(
    {Rule.APPROVAL_UNLESS_AUTHORIZED, Rule.AUTHORIZATION_REQUIRED}
)
"""The rules under which an ``ALLOWED`` decision rests on the grant it was given (ADR 0011 §6,
§9): only then is the grant consumed. ``ALLOW`` and ``ALLOW_WITHIN_SCOPE`` ignore the grant."""

TOOL_EXCEPTION: Final = "tool.exception"
"""Error code of a result synthesised from an exception the tool raised while acting."""
TOOL_REFUSED: Final = "tool.refused"
"""Error code of a step failed because the tool refused the decision (``NotAllowedError``)."""
GRANT_VANISHED: Final = "grant_vanished"
"""Error code of a step failed because the grant vanished between ``authorize`` and ``consume``."""
EXECUTION_INTERRUPTED: Final = "execution.interrupted"
"""Error code of a step whose non-idempotent tool was started and never reported (ADR 0021 §2).

The STARTED record says the tool was about to act; nothing says whether it did. Running it again
is the one thing ELA must not do — it is why the record exists — so the step fails with this, and
``retryable`` is ``True``: what failed is the crash, not the request, and a *new* step may ask
again (a failed step never restarts, ADR 0009). Whether the money was spent is unknown, and the
audit says so rather than guessing.
"""
STARTED_ID: Final = "started_id"
"""Key of ``ExecutionResult.metadata`` on an outcome that settles a STARTED record (ADR 0021 §1):
the id of that record, so the two rows of one run are one run and not two."""
VERIFICATION_FAILED: Final = "verification.failed"
"""Error code of a step, and its task, failed because a success condition did not hold (ADR
0014 §4): the tool said SUCCEEDED and the world said otherwise."""
VERIFICATION_EXCEPTION: Final = "verification.exception"
"""Error code of a step, and its task, failed because the verifier raised: a verifier that
could not answer has not verified, and a doubt is a failure (§33)."""

_CONSUMING_RULE_VALUES: Final[frozenset[str]] = frozenset(rule.value for rule in CONSUMING_RULES)

REPORTABLE: Final[frozenset[ExecutionStatus]] = frozenset(
    {ExecutionStatus.SUCCEEDED, ExecutionStatus.FAILED}
)
"""The two statuses a node may report: the only ones ``Tool.execute`` produces (ADR 0038 §4).

``STARTED`` is the Core's own — it writes it at the claim — and the others belong to nobody's
tool, so a node that reported one would be reporting about a run that did not happen here.
"""

_NOTHING: Final[JsonMapping] = MappingProxyType({})


class Delivery(StrEnum):
    """The three forms of what a node brings back (ADR 0038 §4).

    Three because ``_run_tool`` has three outcomes, and a protocol with two would confuse them:
    a tool that answered, a tool that refused the decision before acting, and a tool that fell
    over. What the Core does with each is the same thing it does here, in this process.
    """

    RESULT = "result"
    """The tool answered, ``SUCCEEDED`` or ``FAILED``: the Core rebuilds the result."""
    REFUSED = "refused"
    """The tool refused the decision — expired at the node's clock, for one — and nothing ran."""
    EXCEPTION = "exception"
    """The tool raised: the type's name, never the message (§57)."""


class Envelope(NamedTuple):
    """What a node delivers: what the tool said, and nothing the Core knows already (ADR 0038 §4).

    Not an :class:`~ela.domain.ExecutionResult`: ``id``, ``created_at`` and the whole stamp of the
    chain are the Core's (D7), and a result arriving from outside would put the order of §32 in the
    hands of another machine's clock. ``node`` is where the node's own instants live — reported
    data, not an instant of the chain — and ``duration_ms`` is reported too: the Core cannot
    measure the run, only the network.
    """

    form: Delivery
    status: ExecutionStatus | None = None
    output: JsonMapping = _NOTHING
    error: ErrorMetadata | None = None
    usage: ProviderUsage | None = None
    duration_ms: int | None = None
    exception: str | None = None
    node: JsonMapping = _NOTHING

    @property
    def digest(self) -> str:
        """The fingerprint of this envelope: what tells a retry from a second claim (ADR 0038 §12).

        Canonical — sorted keys, no spacing — so that the same envelope gives the same digest
        whatever order a node's JSON arrived in. It lives in the assignment's row and nowhere else:
        never in an audit event, never in an error message (§57).
        """
        return hashlib.sha256(
            json.dumps(
                {
                    "form": self.form.value,
                    "status": None if self.status is None else self.status.value,
                    "output": dict(self.output),
                    "error": None if self.error is None else self.error.model_dump(mode="json"),
                    "usage": None if self.usage is None else self.usage.model_dump(mode="json"),
                    "duration_ms": self.duration_ms,
                    "exception": self.exception,
                    "node": dict(self.node),
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
        ).hexdigest()


def check_envelope(envelope: Envelope) -> None:
    """What a coherent envelope looks like (ADR 0038 §4); a ``ValueError`` is a ``422``.

    The form says which fields mean anything, and a field the form has no room for is refused
    rather than ignored: "the tool refused" plus an output is two different stories in one
    message, and ELA does not choose between them (§33).
    """
    if envelope.form is Delivery.RESULT:
        if envelope.status not in REPORTABLE:
            raise ValueError(
                f"a delivered result reports {', '.join(sorted(s.value for s in REPORTABLE))}, "
                f"not {None if envelope.status is None else envelope.status.value}"
            )
    elif envelope.status is not None:
        raise ValueError(f"an envelope of form {envelope.form.value} carries no status")
    if envelope.form is Delivery.EXCEPTION:
        if envelope.exception is None or not envelope.exception.isidentifier():
            raise ValueError(
                "an envelope of form exception carries the name of the exception's type, and a "
                "name is an identifier"
            )
    elif envelope.exception is not None:
        raise ValueError(f"an envelope of form {envelope.form.value} carries no exception")
    if envelope.form is Delivery.REFUSED and (
        envelope.output or envelope.error is not None or envelope.usage is not None
    ):
        raise ValueError("a tool that refused the decision produced nothing: the envelope is empty")


class Verification(NamedTuple):
    """What the verifier said about one SUCCEEDED result (ADR 0014 §4, §8).

    ``failures`` are the verifier's, one per condition that did not hold (or the one synthesised
    from an exception); ``error`` is the :class:`~ela.domain.ErrorMetadata` the step and the task
    are failed with, ``None`` when every condition held. Not persisted: ``EXECUTION_VERIFIED`` is
    its trace.
    """

    conditions: tuple[str, ...]
    failures: tuple[ErrorMetadata, ...]
    error: ErrorMetadata | None

    @property
    def passed(self) -> bool:
        return self.error is None


class Execution(NamedTuple):
    """What one call of :meth:`Executor.execute` did (ADR 0013 §1, ADR 0014 §8, ADR 0015 §4).

    ``result`` is set if the tool ran — in this call or, on a resumed run, in the one the crash
    cut short; ``approval`` only if a request was made or completed by this call;
    ``verification`` only if the verifier's word entered this call (consulted now, or read back
    from ``EXECUTION_VERIFIED`` on a resume, with ``failures`` empty and the error carrying them
    in ``details``); ``graph`` is the state of the plan as last read or written. ``decision`` is
    ``None`` only when the call resumed a run, completed a request or failed a task the Guardian
    had already decided about in an earlier call: its id is in ``result.decision_id`` or
    ``approval.decision_id``, and the decision itself in ``PERMISSION_DECIDED``.
    """

    task: Task
    step_id: StepId
    graph: GraphState
    decision: PermissionDecision | None
    authorization: Authorization | None
    result: ExecutionResult | None
    approval: Approval | None
    verification: Verification | None
    assignment: Assignment | None = None
    """The work this call handed to a node instead of running (M12.2, ADR 0038 §2).

    Set only by the remote branch, and it is what tells the runner that the call assigned: the
    tool did not run here, the step stays RUNNING, and the run returns ``ASSIGNED``. ``None`` for
    every call that ran something, which is every call of a plan that runs on this machine.
    """


class Prepared(NamedTuple):
    """A step that can be acted on, and everything one call needs to act (ADR 0013 §2).

    The rows before the node: the step, the registries' answers about its one capability, the
    arguments of the plan and the targets they name. Built by :meth:`Executor._prepared`, which
    both ``execute`` and ``finish`` go through — the second half of a remote call must ask exactly
    what the first half asked, or the two paths would drift in silence (ADR 0031's lesson).
    """

    step: TaskStep
    spec: CapabilitySpec
    tool: ToolPort
    verifier: VerifierPort
    arguments: JsonMapping
    targets: tuple[object, ...]


class Claimed(NamedTuple):
    """What a node's claim produced: the work, and the call it is about (ADR 0038 §11).

    ``tool_name`` and ``arguments`` are read here and composed into the order elsewhere — the one
    module that composes one (architecture rule 51) — because an executor that wrote the message
    would be the transport.
    """

    assignment: Assignment
    tool_name: str
    arguments: JsonMapping


class Delivered(NamedTuple):
    """What a delivery did: the work as it stands, the step's state, and the call it closed.

    ``execution`` is ``None`` for a replica that had nothing left to complete: a network that
    retries is not an action (ADR 0016 §6), and the answer is the same as the first one.
    """

    assignment: Assignment
    step_state: StepState
    execution: Execution | None


Candidate = tuple[Authorization, int]
"""A grant and how many times it was used, as read from the store."""


def select_authorization(
    candidates: Sequence[Candidate],
    *,
    task: Task,
    step: TaskStep,
    targets: Sequence[object],
    now: datetime,
) -> Candidate | None:
    """The grant to hand the Guardian for this call, or ``None`` (ADR 0013 §3). Pure.

    A candidate **covers** the call if it is not bound to another task or step and its scope
    covers the targets; it is **usable** if not expired at ``now`` (closed bound) and not
    exhausted. Grants bound to this step come first, then the rest, in store order. The first
    covering and usable candidate wins; failing that, the first covering one (so the Guardian's
    reason — and the request for approval — names why it could not be used); failing that,
    nothing. A grant that does not cover is never handed over: the Guardian would read it as the
    caller's incoherence and deny (ADR 0011 §6).
    """
    covering = [candidate for candidate in candidates if _covers(candidate[0], task, step, targets)]
    covering.sort(key=lambda candidate: 0 if candidate[0].step_id == step.id else 1)
    for candidate in covering:
        if _usable(candidate, now):
            return candidate
    return covering[0] if covering else None


def _covers(grant: Authorization, task: Task, step: TaskStep, targets: Sequence[object]) -> bool:
    if grant.task_id is not None and grant.task_id != task.id:
        return False
    if grant.step_id is not None and grant.step_id != step.id:
        return False
    return scope_covers(grant.scope, targets)


def _usable(candidate: Candidate, now: datetime) -> bool:
    grant, uses = candidate
    if grant.expires_at is not None and grant.expires_at <= now:
        return False
    return grant.max_uses is None or uses < grant.max_uses


def _json_targets(targets: Sequence[object]) -> list[JsonValue]:
    return [target if isinstance(target, str) else None for target in targets]


def _stated(spec: CapabilitySpec, arguments: JsonMapping) -> str:
    """The declared arguments of ``spec``, rendered into the question the user reads (§30).

    Empty unless the capability declares ``prompt_arguments``, and none of v0.1's three does — so
    for them the prompt is byte for byte what it was. The declaration is the whole defence: a
    prompt that rendered *every* argument would put ``model.complete``'s ``input`` — the user's
    content — into a stored :class:`~ela.domain.Approval` (§57, ADR 0029 §6).

    Why the values are there at all is the other half of §30: "un semplice 'Sì' fuori contesto non
    deve automaticamente autorizzare". A yes is only worth something if the question was complete,
    and "ELA wants to photograph your screen" is not a question anybody can answer.

    A declared argument that is missing renders nothing rather than ``None``: the Guardian has
    already refused the call for it (the catalogue requires every prompt argument to be required),
    so this cannot happen through the executor — and if it ever did, a question with a hole in it
    must not read as a question with the word "None" in it.

    Not filtered by type since M11.2 (dec. G2): the catalogue decides what may be named here, and
    it admits an integer because *how long the microphone stays open* is half of what is being
    approved. Filtering on ``str`` here as well would have been a second, silent rule — a
    capability could declare ``seconds`` legally and the question would simply not mention it.
    """
    stated = [
        f"{name}: {value}"
        for name in spec.prompt_arguments
        if (value := arguments.get(name)) is not None
    ]
    return f" — {'; '.join(stated)}" if stated else ""


def approved_targets(decision: PermissionDecision) -> tuple[str, ...]:
    """The targets of a decision as an approval carries them: the strings of
    ``metadata["targets"]`` (ADR 0011 §10), nothing if the decision has none."""
    recorded = decision.metadata.get("targets")
    if not isinstance(recorded, list | tuple):
        return ()
    return tuple(target for target in recorded if isinstance(target, str))


class Executor:
    """The unit of work across the ports for one step (ADR 0013).

    ``actor`` is who the executor says it is in ``TOOL_EXECUTED`` and ``EXECUTION_VERIFIED``
    (ELA acts); the user signs ``AUTHORIZATION_GRANTED`` through the approval.
    ``authorization_ttl`` is the life of a grant born here (ADR 0012 §2), ``approval_ttl`` the
    life of a request for approval (at most :data:`MAX_APPROVAL_TTL`). ``verifiers`` is
    mandatory: an executor that cannot verify does not exist (§63). ``approvals`` and ``results``
    are mandatory too (ADR 0015): an executor that kept them in memory could not be retried.
    """

    def __init__(
        self,
        *,
        registry: CapabilityRegistryPort,
        tools: ToolRegistryPort,
        verifiers: VerifierRegistryPort,
        guardian: AuthorizingGuardianPort,
        engine: TaskEngine,
        repository: TaskRepository,
        authorizations: AuthorizationStore,
        approvals: ApprovalStore,
        results: ExecutionResultStore,
        audit: AuditLog,
        clock: Clock,
        ids: IdGenerator,
        actor: Actor,
        assignments: Assignments,
        authorization_ttl: timedelta = DEFAULT_AUTHORIZATION_TTL,
        approval_ttl: timedelta = DEFAULT_APPROVAL_TTL,
    ) -> None:
        if not timedelta(0) < approval_ttl <= MAX_APPROVAL_TTL:
            raise ValueError(
                f"approval_ttl must be positive and at most {MAX_APPROVAL_TTL}, not {approval_ttl}"
            )
        self._registry = registry
        self._tools = tools
        self._verifiers = verifiers
        self._guardian = guardian
        self._engine = engine
        self._repository = repository
        self._authorizations = authorizations
        self._approvals = approvals
        self._results = results
        self._audit = audit
        self._clock = clock
        self._ids = ids
        self._actor = actor
        self._assignments = assignments
        self._authorization_ttl = authorization_ttl
        self._approval_ttl = approval_ttl

    async def execute(
        self, task_id: TaskId, step_id: StepId, *, placement: PlacementDecision
    ) -> Execution:
        """Run and verify the one capability of a RUNNING step of an EXECUTING task (ADR 0013
        §1–§9, ADR 0014 §3–§4), or resume what an earlier call left unfinished (ADR 0015 §5–§7).

        The arguments are the step's (``TaskStep.arguments``, ADR 0018), not the caller's: a
        retry is the *same* call and must run on the *same* arguments, or the targets an audit
        event records would not be the targets the tool acted on.

        ``placement`` is the orchestrator's decision about *this* step, and it is checked —
        once the step is known executable, before anything runs — rather than believed
        (:func:`~ela.devices.orchestrator.ensure_placed`,
        :class:`~ela.devices.errors.NotPlacedError`), ADR 0026 §2. Until M9.1 this was a bare
        ``device_id``, which said "here" without saying "for what": the executor had no way to
        tell a node the orchestrator chose from a node the caller invented, and *which node may
        see this content* (§57) was the one link in the permission chain guarded in a single
        place. The node the audit and the results record is now the one the decision names, so
        naming a node nobody chose has stopped being expressible.

        A retry is this same call again. The user's answer to a request this executor made is
        read from the :class:`~ela.ports.ApprovalStore`: the last GRANTED request of the step
        becomes the grant the call runs under. Preconditions that fail raise before anything is
        written: :class:`~ela.executive.errors.ExecutorError` (also for a request of this step
        that expired unanswered: it is never asked again, ADR 0015 §6),
        :class:`~ela.tasks.errors.UnknownStepError`, ``CapabilityNotFound``, ``ToolNotFound``,
        ``VerifierNotFound``, ``ApprovalMismatchError``.
        """
        task = await self._repository.get(task_id)
        if task.state is not TaskState.EXECUTING:
            raise ExecutorError(task_id, f"a tool needs an EXECUTING task, not {task.state.value}")
        graph = await self._engine.graph(task_id)
        closed = await self._closed_by_unfinished_verification(task, graph, step_id)
        if closed is not None:
            return closed
        step, spec, tool, verifier, arguments, targets = self._prepared(task_id, graph, step_id)
        # Where, once it is settled that there is something to run and before anything runs.
        # After the lookups, so a step with no tool still says so with its own error rather than
        # as a node that cannot host it; before the first read of the results, so a caller with
        # somebody else's placement leaves no trace (ADR 0026 §3).
        device_id = ensure_placed(placement, task_id, step_id).id

        started, settled = await self._stored(task_id, step_id)
        if settled:  # the tool ran in an earlier call: resume from the first missing write
            return await self._resume(
                task, graph, step, tool, verifier, arguments, targets, settled[0]
            )
        if started:  # ADR 0021 §2: it was started and never reported. It is not started again.
            return await self._interrupted(task, graph, step, tool, targets, started[0])

        now = self._clock.now()
        requests = [a for a in await self._approvals.for_task(task_id) if a.step_id == step_id]
        pending = [a for a in requests if a.status is ApprovalStatus.PENDING]
        if pending:  # asked in an earlier call, the task never waited on it (ADR 0015 §6)
            request = pending[-1]
            if request.expires_at is not None and request.expires_at <= now:
                raise ExecutorError(
                    task_id,
                    f"approval {request.id} for step {step_id} expired at "
                    f"{request.expires_at.isoformat()} unanswered; it is not asked again",
                )
            task = await self._engine.request_approval(task_id, request)
            return Execution(task, step_id, graph, None, None, None, request, None)
        granted = [a for a in requests if a.status is ApprovalStatus.GRANTED]
        authorization: Authorization | None
        if granted:
            authorization, uses = await self._grant(granted[-1], task, step, spec, now)
        else:
            authorization, uses = await self._find_authorization(spec, targets, task, step, now)

        decision = await self._guardian.authorize(
            spec,
            arguments,
            task=task,
            step=step,
            authorization=authorization,
            authorization_uses=uses,
            device_id=device_id,
        )
        if decision.outcome is PermissionOutcome.DENIED:
            task = await self._engine.deny(task_id, decision=decision)
            return Execution(task, step_id, graph, decision, authorization, None, None, None)
        if decision.outcome is PermissionOutcome.REQUIRES_APPROVAL:
            return await self._ask(
                graph, step, spec, arguments, decision, authorization, decision.reason
            )

        consumed: int | None = None
        if authorization is not None and decision.metadata.get("rule") in _CONSUMING_RULE_VALUES:
            try:
                consumed = await self._authorizations.consume(
                    authorization.id, now=decision.created_at
                )
            except AuthorizationNotUsableError as unusable:
                return await self._ask(
                    graph, step, spec, arguments, decision, authorization, unusable.reason
                )
            except NotFoundError:
                vanished = ErrorMetadata(
                    code=GRANT_VANISHED,
                    message=f"authorization {authorization.id} vanished before it was consumed",
                    tool_name=tool.name,
                )
                return await self._fail(task, graph, decision, authorization, vanished)

        spent = None if consumed is None or authorization is None else authorization.id
        if device_id != LOCAL_DEVICE_ID:
            # The line of D1: everything after this happens on another machine (ADR 0038 §2). The
            # criterion is the id and not the network: ``local``'s is the one id of the system that
            # is deterministic *because it is this machine*, and every other one the Core minted.
            assignment = await self._assignments.assign(decision, placement, authorization_id=spent)
            return Execution(
                task, step_id, graph, decision, authorization, None, None, None, assignment
            )
        record = (
            None if tool.idempotent else await self._start_record(tool, decision, device_id, spent)
        )
        await self._sensor_activated(spec, decision, device_id)
        produced = await self._run_tool(tool, decision, arguments)
        if produced is None:
            refused = ErrorMetadata(
                code=TOOL_REFUSED,
                message=f"{tool.name} refused the decision {decision.id}",
                tool_name=tool.name,
            )
            return await self._fail(task, graph, decision, authorization, refused)
        result = produced.model_copy(
            update={
                "device_id": device_id,
                "decision_id": decision.id,
                "authorization_id": spent,
                "metadata": produced.metadata
                if record is None
                else {**produced.metadata, STARTED_ID: str(record.id)},
            }
        )
        await self._results.add(result)
        return await self._settled(
            task,
            graph,
            Prepared(step, spec, tool, verifier, arguments, targets),
            decision,
            authorization,
            result,
            consumed,
        )

    # ----------------------------------------------------------------------------------
    # The three instants of a call that runs elsewhere (ADR 0038 §2)
    # ----------------------------------------------------------------------------------

    async def begin(self, assignment_id: AssignmentId, device_id: DeviceId) -> Claimed:
        """The node takes the work: the claim, then the two writes of the claim (ADR 0038 §11).

        The order is the claim **first**: a death between the two leaves work taken with no
        STARTED record — an order that never went out — and the expiry releases the step (window
        ``A4``). The other way round would leave a STARTED record with no claim, and the next claim
        would write the step's second one, against the index of migration ``0007``.

        The STARTED record is born **here and not in** ``run`` (M12.1, D14): until a node takes the
        work nothing can have acted, so a step whose offer nobody claimed is placed again whatever
        its tool. ``SENSOR_ACTIVATED`` is written for a capability that turns one on — none that
        travels does today (D15), and the call is here so that the day one does, it is written
        where the sensor is turned on.

        Raises what the service raises for work that cannot be taken: unknown
        (``NotFoundError``), another node's, not offered any more, expired, or a node whose hands
        are already full (``AssignmentNodeBusyError``).
        """
        assignment = await self._assignments.claim(assignment_id, device_id)
        decision = assignment.decision
        graph = await self._engine.graph(assignment.task_id)
        step, spec, tool, _, arguments, _ = self._prepared(
            assignment.task_id, graph, assignment.step_id
        )
        if not tool.idempotent:
            await self._start_record(tool, decision, device_id, assignment.authorization_id)
        await self._sensor_activated(spec, decision, device_id)
        return Claimed(assignment, tool.name, arguments)

    async def deliver(
        self, assignment_id: AssignmentId, device_id: DeviceId, envelope: Envelope
    ) -> Delivered:
        """The node brings the work back: the gate, the result the Core mints, the second half.

        One instant serves the gate and the writes (ADR 0013 §6): ``now`` is read once, so a
        delivery that passes is a delivery that was in time at the instant it was judged.

        The gate refuses, writes a ``DEVICE_REJECTED`` of the work with its reason, and raises —
        an unknown id or another node's (``not_assigned``, and the payload tells the two apart
        while the node gets one answer for both), work no longer taken, a delivery after the expiry
        (``late``), a task that closed while the node worked (``task_closed``), a second envelope
        where one was accepted (``delivery_conflict``). A *repeated* envelope is none of those: it
        is the same answer again, and what a death left unwritten is completed (window ``A9``).

        The order of the writes is the one that makes ``DELIVERED`` mean something: the outcome
        goes in the store first and the assignment is marked after, so *delivered implies the
        outcome is stored, or the step is already closed*; for a refusal the step is failed first
        and then marked. The reverse would leave a refusal a resume could not tell from an
        interruption.
        """
        check_envelope(envelope)
        now = self._clock.now()
        assignment = await self._gate(assignment_id, device_id, envelope, now)
        digest = envelope.digest
        if assignment.state is AssignmentState.DELIVERED:
            if assignment.delivery_digest != digest:
                await self._refuse(assignment, device_id, WorkRejection.DELIVERY_CONFLICT)
                raise DeliveryConflictError(assignment_id)
            return await self._again(assignment)
        task = await self._repository.get(assignment.task_id)
        graph = await self._engine.graph(assignment.task_id)
        if (
            task.state is not TaskState.EXECUTING
            or graph.states[assignment.step_id] is not StepState.RUNNING
        ):
            await self._refuse(
                assignment, device_id, WorkRejection.TASK_CLOSED, reported=envelope.status
            )
            raise AssignmentVoidError(assignment_id, task.state.value)
        ready = self._prepared(assignment.task_id, graph, assignment.step_id)
        if envelope.form is Delivery.REFUSED:
            return await self._refused_there(task, graph, ready, assignment, digest, now)
        started, _ = await self._stored(assignment.task_id, assignment.step_id)
        result = self._minted(
            assignment, ready.tool, envelope, now, started[0] if started else None
        )
        fresh = await self._stored_once(result)
        marked = await self._assignments.deliver(assignment_id, device_id, digest=digest, now=now)
        if not fresh:  # window A8: the row was already there, so the writes after it may be missing
            return await self._again(marked)
        uses = (
            None
            if assignment.authorization_id is None
            else await self._authorizations.uses(assignment.authorization_id)
        )
        execution = await self._settled(task, graph, ready, None, None, result, uses)
        return Delivered(marked, execution.graph.states[assignment.step_id], execution)

    async def finish(self, task_id: TaskId, step_id: StepId) -> Execution:
        """The second half alone, for a step whose node left something behind (ADR 0038 §2).

        The rows of ``execute`` up to the targets, and the resume — **without**
        :func:`~ela.devices.ensure_placed`: that function guards *where a tool runs*, and here no
        tool runs. Called by the runner when an expiry left a STARTED record or an outcome in the
        store, and by a repeated delivery that has writes to complete.

        Neither an outcome nor a STARTED record is an :class:`ExecutorError`: the step was to be
        released, not finished, and a doubt is a failure (§33).
        """
        task = await self._repository.get(task_id)
        if task.state is not TaskState.EXECUTING:
            raise ExecutorError(
                task_id, f"finishing a step needs an EXECUTING task, not {task.state.value}"
            )
        graph = await self._engine.graph(task_id)
        closed = await self._closed_by_unfinished_verification(task, graph, step_id)
        if closed is not None:
            return closed
        ready = self._prepared(task_id, graph, step_id)
        started, settled = await self._stored(task_id, step_id)
        if settled:
            return await self._resume(
                task,
                graph,
                ready.step,
                ready.tool,
                ready.verifier,
                ready.arguments,
                ready.targets,
                settled[0],
            )
        if started:
            return await self._interrupted(
                task, graph, ready.step, ready.tool, ready.targets, started[0]
            )
        raise ExecutorError(
            task_id,
            f"step {step_id} has neither an outcome nor a started record: nothing ran on it, so "
            "it was to be released and not finished",
        )

    # ----------------------------------------------------------------------------------
    # The gate of a delivery, and what it refuses
    # ----------------------------------------------------------------------------------

    async def _gate(
        self,
        assignment_id: AssignmentId,
        device_id: DeviceId,
        envelope: Envelope,
        now: datetime,
    ) -> Assignment:
        """The work this delivery is about, or the refusal that says why it is not (ADR 0038 §12).

        A ``DELIVERED`` row comes back: whether it is the same envelope or another one is the
        caller's question, and the digest is the only thing that can answer it.

        The three ways work is "not this node's" raise **one** error with one message — unknown,
        another's, not taken any more — because a node told them apart could map which assignments
        exist for the others. The audit keeps the difference (``assignment_known``).
        """
        try:
            assignment = await self._assignments.held(assignment_id)
        except NotFoundError:
            await self._assignments.reject(
                device_id,
                WorkRejection.NOT_ASSIGNED,
                assignment_id=assignment_id,
                known=False,
            )
            raise WorkNotYoursError(assignment_id) from None
        if assignment.device_id != device_id:
            await self._assignments.reject(
                device_id, WorkRejection.NOT_ASSIGNED, assignment_id=assignment_id, known=True
            )
            raise WorkNotYoursError(assignment_id)
        if assignment.state is AssignmentState.DELIVERED:
            return assignment
        if assignment.state is not AssignmentState.CLAIMED:
            await self._refuse(assignment, device_id, WorkRejection.NOT_ASSIGNED)
            raise WorkNotYoursError(assignment_id)
        if assignment.expires_at <= now:
            await self._refuse(assignment, device_id, WorkRejection.LATE, reported=envelope.status)
            raise AssignmentExpiredError(assignment_id, assignment.expires_at)
        return assignment

    async def _refuse(
        self,
        assignment: Assignment,
        device_id: DeviceId,
        reason: WorkRejection,
        *,
        reported: ExecutionStatus | None = None,
    ) -> None:
        """A refusal on the way of the work, about an assignment the Core knows (ADR 0038 §12)."""
        await self._assignments.reject(
            device_id,
            reason,
            assignment_id=assignment.id,
            task_id=assignment.task_id,
            reported=reported,
        )

    async def _refused_there(
        self,
        task: Task,
        graph: GraphState,
        ready: Prepared,
        assignment: Assignment,
        digest: str,
        now: datetime,
    ) -> Delivered:
        """The tool refused the decision on the node: the step fails as it fails here (row 16)."""
        refused = ErrorMetadata(
            code=TOOL_REFUSED,
            message=f"{ready.tool.name} refused the decision {assignment.decision.id}",
            tool_name=ready.tool.name,
            device_id=assignment.device_id,
        )
        moved = await self._engine.fail_step(task.id, assignment.step_id, refused)
        marked = await self._assignments.deliver(
            assignment.id, assignment.device_id, digest=digest, now=now
        )
        return Delivered(
            marked,
            moved.states[assignment.step_id],
            Execution(task, assignment.step_id, moved, None, None, None, None, None, marked),
        )

    async def _again(self, assignment: Assignment) -> Delivered:
        """The same envelope a second time: the same answer, and nothing written twice.

        A network that retries is not an action (ADR 0016 §6). What it may be is a first delivery
        whose later writes a death swallowed (windows ``A8``, ``A9``): if the step is still RUNNING
        there is something to complete, and :meth:`finish` completes it from the first write that is
        missing. Otherwise nothing happens at all.
        """
        graph = await self._engine.graph(assignment.task_id)
        state = graph.states[assignment.step_id]
        if state is not StepState.RUNNING:
            return Delivered(assignment, state, None)
        execution = await self.finish(assignment.task_id, assignment.step_id)
        return Delivered(assignment, execution.graph.states[assignment.step_id], execution)

    def _minted(
        self,
        assignment: Assignment,
        tool: ToolPort,
        envelope: Envelope,
        now: datetime,
        record: ExecutionResult | None,
    ) -> ExecutionResult:
        """The result the Core builds from what a node said (ADR 0038 §4; dec. B).

        The node's half is what its tool produced — the status, the output, the error, the usage,
        and a duration it reports because the Core could only measure the network. Everything that
        places the run in the chain of §32 is the Core's: a deterministic ``id`` per assignment,
        ``created_at`` at the gate's instant, and the stamp of the call from the assignment itself.
        The node's own instants travel in ``metadata["node"]``, as reported data and not as an
        instant of the chain.
        """
        error = envelope.error
        status = envelope.status
        if envelope.form is Delivery.EXCEPTION:
            # The form ``_run_tool`` gives an exception here, built here for the same reason: the
            # type's name is information, its message is the user's content (§57).
            error = ErrorMetadata(
                code=TOOL_EXCEPTION, message=str(envelope.exception), tool_name=tool.name
            )
            status = ExecutionStatus.FAILED
        assert status is not None  # check_envelope: a result reports one, an exception is FAILED
        metadata: dict[str, JsonValue] = {"node": dict(envelope.node)}
        if record is not None:
            metadata[STARTED_ID] = str(record.id)
        return ExecutionResult(
            id=ExecutionId(uuid5(DELIVERY_NAMESPACE, str(assignment.id))),
            created_at=now,
            capability_id=assignment.decision.capability_id,
            status=status,
            task_id=assignment.task_id,
            step_id=assignment.step_id,
            tool_name=tool.name,
            device_id=assignment.device_id,
            decision_id=assignment.decision.id,
            authorization_id=assignment.authorization_id,
            output=envelope.output,
            error=error,
            usage=envelope.usage,
            duration_ms=envelope.duration_ms,
            metadata=metadata,
        )

    async def _stored_once(self, result: ExecutionResult) -> bool:
        """Store ``result``; ``False`` if its deterministic id was already there (window ``A8``)."""
        try:
            await self._results.add(result)
        except AlreadyExistsError:
            return False
        return True

    # ----------------------------------------------------------------------------------
    # What both halves share
    # ----------------------------------------------------------------------------------

    def _prepared(self, task_id: TaskId, graph: GraphState, step_id: StepId) -> Prepared:
        """The step and what one call needs to act on it (rows 3–5 of the pipeline).

        One implementation for the local path, the claim, the delivery and ``finish``: the half
        that runs elsewhere must ask exactly what the half that runs here asked, and a second copy
        of these checks is how the two would stop agreeing.
        """
        step = graph.graph.step(step_id)
        state = graph.states[step_id]
        if state is not StepState.RUNNING:
            raise ExecutorError(
                task_id, f"step {step_id} is {state.value}, not RUNNING: start the step first"
            )
        if len(step.required_capabilities) != 1:
            raise ExecutorError(
                task_id,
                f"step {step_id} declares {len(step.required_capabilities)} capabilities; an "
                "executable step declares exactly one",
            )
        if not step.success_conditions:
            raise ExecutorError(
                task_id,
                f"step {step_id} declares no success condition; an action that cannot be "
                "verified is not executed",
            )
        spec = self._registry.get(step.required_capabilities[0])
        tool = self._tools.get(spec.id)
        verifier = self._verifiers.get(spec.id)
        unknown = [c for c in step.success_conditions if c not in verifier.conditions]
        if unknown:
            raise ExecutorError(
                task_id,
                f"step {step_id} names success conditions {verifier.name} cannot check: "
                f"{', '.join(unknown)}; an action that cannot be verified is not executed",
            )
        return Prepared(
            step, spec, tool, verifier, step.arguments, tuple(targets_of(spec, step.arguments))
        )

    async def _stored(
        self, task_id: TaskId, step_id: StepId
    ) -> tuple[tuple[ExecutionResult, ...], tuple[ExecutionResult, ...]]:
        """The STARTED records and the outcomes of the step; more than one of either is a doubt."""
        started, settled = _split(await self._results.for_step(task_id, step_id))
        if len(settled) > 1 or len(started) > 1:
            raise ExecutorError(
                task_id,
                f"step {step_id} has {len(settled)} results and {len(started)} started records; "
                "a step runs once",
            )
        return started, settled

    async def _closed_by_unfinished_verification(
        self, task: Task, graph: GraphState, step_id: StepId
    ) -> Execution | None:
        """ADR 0015 §7: a step FAILED by a verification whose task was never failed with it."""
        if graph.states[step_id] is not StepState.FAILED:
            return None
        unfinished = await self._unfinished_verification_failure(task.id, step_id)
        if unfinished is None:
            return None
        return Execution(
            await self._engine.fail(task.id, unfinished),
            step_id,
            graph,
            None,
            None,
            None,
            None,
            None,
        )

    async def _settled(
        self,
        task: Task,
        graph: GraphState,
        ready: Prepared,
        decision: PermissionDecision | None,
        authorization: Authorization | None,
        result: ExecutionResult,
        uses: int | None,
    ) -> Execution:
        """The second half, once the outcome is in the store: audit, verify, close (rows 19–22).

        The **one** implementation of what happens after a tool ran, wherever it ran (ADR 0038 §2).
        The insert of the result is the caller's and not this method's, because a delivery has to
        mark the assignment between the two writes: *delivered* must imply *the outcome is stored*,
        and a method that did both could not be asked to stop in the middle.
        """
        await self._record_execution(ready.tool, result, ready.targets, uses)
        if result.status is not ExecutionStatus.SUCCEEDED:
            moved = await self._engine.fail_step(
                task.id, ready.step.id, _failure_of(result, ready.tool)
            )
            return Execution(
                task, ready.step.id, moved, decision, authorization, result, None, None
            )
        verification = await self._verify(
            ready.verifier, ready.tool, ready.step, ready.arguments, result
        )
        await self._record_verification(ready.tool, ready.verifier, result, verification)
        return await self._close(
            task, graph, ready.step, decision, authorization, result, verification
        )

    # ----------------------------------------------------------------------------------
    # Resuming what an earlier call left unfinished (ADR 0015 §5, §7)
    # ----------------------------------------------------------------------------------

    async def _resume(
        self,
        task: Task,
        graph: GraphState,
        step: TaskStep,
        tool: ToolPort,
        verifier: VerifierPort,
        arguments: JsonMapping,
        targets: Sequence[object],
        result: ExecutionResult,
    ) -> Execution:
        """Continue from the first write the crash skipped: the audit of the run, the
        verification, the closing of the step. No Guardian, no grant, no tool."""
        events = await self._audit.read(task_id=task.id)
        if _event_about(events, AuditEventType.TOOL_EXECUTED, result.id) is None:
            uses = (
                None
                if result.authorization_id is None
                else await self._authorizations.uses(result.authorization_id)
            )
            await self._record_execution(tool, result, targets, uses, recovered=True)
        if result.status is not ExecutionStatus.SUCCEEDED:
            graph = await self._engine.fail_step(task.id, step.id, _failure_of(result, tool))
            return Execution(task, step.id, graph, None, None, result, None, None)
        verified = _event_about(events, AuditEventType.EXECUTION_VERIFIED, result.id)
        if verified is None:  # re-verify: the verifier only reads (rule 18)
            verification = await self._verify(verifier, tool, step, arguments, result)
            await self._record_verification(tool, verifier, result, verification, recovered=True)
        else:
            verification = Verification(step.success_conditions, (), verified.error)
        return await self._close(task, graph, step, None, None, result, verification)

    async def _interrupted(
        self,
        task: Task,
        graph: GraphState,
        step: TaskStep,
        tool: ToolPort,
        targets: Sequence[object],
        record: ExecutionResult,
    ) -> Execution:
        """A non-idempotent tool was started and never reported: the step fails (ADR 0021 §2).

        The tool is **not** run again — that is the whole reason the STARTED record was written
        — and no outcome is invented: a second row claiming FAILED would say the tool ran and
        failed, when what is known is only that it was about to run. So the record stays as it
        is, ``TOOL_EXECUTED`` names it with :data:`EXECUTION_INTERRUPTED` and a payload whose
        status is STARTED, and the step is failed with the same error. The task stays EXECUTING:
        a tool's failure is the orchestrator's question, not this module's (ADR 0013 §5).

        The audit is guarded the way a resume guards it: a crash between this event and
        ``fail_step`` brings the call back here, and the event is written once.
        """
        error = ErrorMetadata(
            code=EXECUTION_INTERRUPTED,
            message=(
                f"{tool.name} was started for step {step.id} and never reported; it cannot be "
                "repeated, so whether it acted is unknown"
            ),
            tool_name=tool.name,
            device_id=record.device_id,
            retryable=True,
        )
        events = await self._audit.read(task_id=task.id)
        if _event_about(events, AuditEventType.TOOL_EXECUTED, record.id) is None:
            uses = (
                None
                if record.authorization_id is None
                else await self._authorizations.uses(record.authorization_id)
            )
            await self._record_execution(tool, record, targets, uses, recovered=True, error=error)
        graph = await self._engine.fail_step(task.id, step.id, error)
        return Execution(task, step.id, graph, None, None, record, None, None)

    async def _close(
        self,
        task: Task,
        graph: GraphState,
        step: TaskStep,
        decision: PermissionDecision | None,
        authorization: Authorization | None,
        result: ExecutionResult,
        verification: Verification,
    ) -> Execution:
        """The step is COMPLETED on a passed verification; on a failed one the step and the task
        are FAILED with the same error (ADR 0014 §4)."""
        if verification.error is None:
            graph = await self._engine.complete_step(task.id, step.id, result)
        else:
            graph = await self._engine.fail_step(task.id, step.id, verification.error)
            task = await self._engine.fail(task.id, verification.error)
        return Execution(task, step.id, graph, decision, authorization, result, None, verification)

    async def _unfinished_verification_failure(
        self, task_id: TaskId, step_id: StepId
    ) -> ErrorMetadata | None:
        """The error a FAILED step's task was to be failed with, if the crash came between
        ``fail_step`` and ``fail`` (ADR 0015 §7): the ``STEP_FAILED`` of a verification."""
        for event in reversed(await self._audit.read(task_id=task_id)):
            if event.event_type is AuditEventType.STEP_FAILED and event.step_id == step_id:
                if event.error is not None and event.error.code == VERIFICATION_FAILED:
                    return event.error
                return None
        return None

    # ----------------------------------------------------------------------------------
    # Authorization: from an approval, or from the store
    # ----------------------------------------------------------------------------------

    async def _grant(
        self, approval: Approval, task: Task, step: TaskStep, spec: CapabilitySpec, now: datetime
    ) -> Candidate:
        """The grant ``approval`` authorises, stored and recorded once (ADR 0013 §3)."""
        grant = authorization_from_approval(
            approval,
            task=task,
            step=step,
            capability=spec,
            now=now,
            authorization_id=AuthorizationId(uuid5(AUTHORIZATION_NAMESPACE, str(approval.id))),
            ttl=self._authorization_ttl,
        )
        try:
            await self._authorizations.grant(grant)
        except AlreadyExistsError:
            stored = await self._authorizations.get(grant.id)
            if stored.approval_id != approval.id:
                raise ExecutorError(
                    task.id, f"authorization {grant.id} exists for another approval"
                ) from None
            if not await self._grant_recorded(task.id, grant.id):
                await self._record_grant(stored, approval)
            return stored, await self._authorizations.uses(grant.id)
        await self._record_grant(grant, approval)
        return grant, 0

    async def _grant_recorded(self, task_id: TaskId, authorization_id: AuthorizationId) -> bool:
        return any(
            event.event_type is AuditEventType.AUTHORIZATION_GRANTED
            and event.authorization_id == authorization_id
            for event in await self._audit.read(task_id=task_id)
        )

    async def _record_grant(self, grant: Authorization, approval: Approval) -> None:
        await self._audit.append(
            AuditEvent(
                id=AuditEventId(self._ids.new_uuid()),
                created_at=grant.created_at,
                event_type=AuditEventType.AUTHORIZATION_GRANTED,
                actor=Actor(kind=ActorKind.USER, id=grant.granted_by),
                summary=(
                    f"grant: authorization {grant.id} for {grant.capability_id} "
                    f"from approval {approval.id}"
                ),
                task_id=grant.task_id,
                step_id=grant.step_id,
                capability_id=grant.capability_id,
                decision_id=approval.decision_id,
                authorization_id=grant.id,
                payload={
                    "origin": "approval",
                    "approval_id": str(approval.id),
                    "expires_at": None
                    if grant.expires_at is None
                    else grant.expires_at.isoformat(),
                    "max_uses": grant.max_uses,
                    "targets": list(approval.targets),
                    "scope": list(grant.scope),
                },
            )
        )

    async def _find_authorization(
        self,
        spec: CapabilitySpec,
        targets: Sequence[object],
        task: Task,
        step: TaskStep,
        now: datetime,
    ) -> tuple[Authorization | None, int]:
        candidates = [
            (grant, await self._authorizations.uses(grant.id))
            for grant in await self._authorizations.for_capability(spec.id)
        ]
        selected = select_authorization(candidates, task=task, step=step, targets=targets, now=now)
        return (None, 0) if selected is None else selected

    # ----------------------------------------------------------------------------------
    # The outcomes that stop the call: ask, fail
    # ----------------------------------------------------------------------------------

    async def _ask(
        self,
        graph: GraphState,
        step: TaskStep,
        spec: CapabilitySpec,
        arguments: JsonMapping,
        decision: PermissionDecision,
        authorization: Authorization | None,
        reason: str,
    ) -> Execution:
        """Build the request for approval from the decision and let the task wait (ADR 0013 §5)."""
        assert decision.task_id is not None and decision.step_id is not None
        targets = approved_targets(decision)
        where = f" on {', '.join(targets)}" if targets else ""
        approval = Approval(
            id=ApprovalId(uuid5(APPROVAL_NAMESPACE, str(decision.id))),
            created_at=decision.created_at,
            task_id=decision.task_id,
            step_id=decision.step_id,
            capability_id=spec.id,
            targets=targets,
            prompt=f"{spec.id}{where} for step {step.id} ({step.goal}){_stated(spec, arguments)}"
            f": {reason}",
            status=ApprovalStatus.PENDING,
            decision_id=decision.id,
            expires_at=decision.created_at + self._approval_ttl,
        )
        await self._approvals.add(approval)  # stored before the task waits on it (ADR 0015 §6)
        task = await self._engine.request_approval(decision.task_id, approval)
        return Execution(task, step.id, graph, decision, authorization, None, approval, None)

    async def _fail(
        self,
        task: Task,
        graph: GraphState,
        decision: PermissionDecision,
        authorization: Authorization | None,
        error: ErrorMetadata,
    ) -> Execution:
        """Nothing ran: the step is FAILED with the reason, so the task does not hang (§33)."""
        assert decision.step_id is not None
        graph = await self._engine.fail_step(task.id, decision.step_id, error)
        return Execution(task, decision.step_id, graph, decision, authorization, None, None, None)

    # ----------------------------------------------------------------------------------
    # The tool and its audit
    # ----------------------------------------------------------------------------------

    async def _start_record(
        self,
        tool: ToolPort,
        decision: PermissionDecision,
        device_id: DeviceId,
        authorization_id: AuthorizationId | None,
    ) -> ExecutionResult:
        """The STARTED record of a tool that cannot be run twice (ADR 0021 §1).

        Written **before** the tool acts and stored before it is called, so that the instant
        between the action and the insert of its outcome — crash window 7a, declared unrepairable
        in ADR 0015 §8 — leaves something behind. It carries everything the outcome will carry
        except the outcome: whose decision, whose grant, which node. No audit event: nothing has
        happened yet, and ``TOOL_EXECUTED`` is written at the outcome, interrupted or not.
        """
        record = ExecutionResult(
            id=ExecutionId(self._ids.new_uuid()),
            created_at=self._clock.now(),
            capability_id=tool.capability_id,
            status=ExecutionStatus.STARTED,
            task_id=decision.task_id,
            step_id=decision.step_id,
            tool_name=tool.name,
            device_id=device_id,
            decision_id=decision.id,
            authorization_id=authorization_id,
        )
        await self._results.add(record)
        return record

    async def _sensor_activated(
        self, spec: CapabilitySpec, decision: PermissionDecision, device_id: DeviceId
    ) -> None:
        """``SENSOR_ACTIVATED``, when the capability about to run turns on a sensor of §11.

        **Written before the tool, and that is the decision** (M11.2 dec. L, ADR 0036 §11). An
        event written afterwards would describe better — it would know how long the device was
        really open — and would be missing in exactly the worst case: ELA opens the microphone,
        something dies, and nothing says it was ever opened. The duration is not lost; it is in
        the result, which is where a measurement belongs.

        The summary names the sensor and never the arguments — how long is an argument, and
        architecture rule 23 keeps those out of the audit.
        """
        if spec.activates_sensor is None:
            return
        await self._audit.append(
            AuditEvent(
                id=AuditEventId(self._ids.new_uuid()),
                created_at=self._clock.now(),
                event_type=AuditEventType.SENSOR_ACTIVATED,
                actor=self._actor,
                summary=f"activate: {spec.activates_sensor.value} for {spec.id}",
                task_id=decision.task_id,
                step_id=decision.step_id,
                capability_id=spec.id,
                device_id=device_id,
                decision_id=decision.id,
            )
        )

    async def _run_tool(
        self, tool: ToolPort, decision: PermissionDecision, arguments: JsonMapping
    ) -> ExecutionResult | None:
        """The only call of a tool in the Core (rule 16), with an ALLOWED decision in hand.

        ``None`` if the tool refused the decision before acting; a FAILED result if it raised
        while acting, so that the run is recorded whatever happened (§32).
        """
        assert decision.outcome is PermissionOutcome.ALLOWED
        assert decision.capability_id == tool.capability_id
        try:
            return await tool.execute(decision, arguments)
        except NotAllowedError:
            return None
        except Exception as error:  # a tool that fell over halfway: recorded, never hidden
            return ExecutionResult(
                id=ExecutionId(self._ids.new_uuid()),
                created_at=self._clock.now(),
                capability_id=tool.capability_id,
                status=ExecutionStatus.FAILED,
                task_id=decision.task_id,
                step_id=decision.step_id,
                tool_name=tool.name,
                error=ErrorMetadata(
                    code=TOOL_EXCEPTION, message=type(error).__name__, tool_name=tool.name
                ),
            )

    async def _record_execution(
        self,
        tool: ToolPort,
        result: ExecutionResult,
        targets: Sequence[object],
        uses: int | None,
        *,
        recovered: bool = False,
        error: ErrorMetadata | None = None,
    ) -> None:
        """``TOOL_EXECUTED``: the fact, the decision and the grant the result carries, the
        targets — never the arguments nor the output (§57). ``created_at`` is the result's when
        written with the run, the clock's on a resume, which also marks the payload.

        ``usage`` is the result's, and this is the only place ELA writes it: "provider usage
        metadata" is one of the things §32 asks the audit log to hold, and until M7.2 the field
        existed on :class:`~ela.domain.AuditEvent` with nothing to put in it. It is ``None`` for
        a tool that calls no provider — which is not zero, and must not read as free.

        ``error`` overrides the result's, and only one caller passes it: an interrupted run,
        whose STARTED record carries no error of its own but whose audit entry must say why the
        step is being failed (ADR 0021 §2).
        """
        await self._audit.append(
            AuditEvent(
                id=AuditEventId(self._ids.new_uuid()),
                created_at=self._clock.now() if recovered else result.created_at,
                event_type=AuditEventType.TOOL_EXECUTED,
                actor=self._actor,
                summary=f"execute: {result.status.value} {result.capability_id} by {tool.name}",
                task_id=result.task_id,
                step_id=result.step_id,
                capability_id=result.capability_id,
                device_id=result.device_id,
                decision_id=result.decision_id,
                authorization_id=result.authorization_id,
                tool_name=tool.name,
                usage=result.usage,
                error=result.error if error is None else error,
                payload={
                    "status": result.status.value,
                    "result_id": str(result.id),
                    "targets": _json_targets(targets),
                    "duration_ms": result.duration_ms,
                    "device": _device(result),
                    "uses": uses,
                    **({RECOVERED: True} if recovered else {}),
                },
            )
        )

    # ----------------------------------------------------------------------------------
    # The verifier and its audit
    # ----------------------------------------------------------------------------------

    async def _verify(
        self,
        verifier: VerifierPort,
        tool: ToolPort,
        step: TaskStep,
        arguments: JsonMapping,
        result: ExecutionResult,
    ) -> Verification:
        """The verifier's word on a SUCCEEDED result (ADR 0014 §4).

        A verifier that raises has not verified: its exception becomes one failure named after
        the exception's type — never its message (§57) — and the verification fails.
        """
        conditions = step.success_conditions
        try:
            failures = tuple(await verifier.verify(conditions, arguments, result))
        except Exception as error:  # a verifier that could not answer: a doubt, recorded
            failures = (
                ErrorMetadata(
                    code=VERIFICATION_EXCEPTION,
                    message=type(error).__name__,
                    tool_name=tool.name,
                    details={"condition": None},
                ),
            )
        if not failures:
            return Verification(conditions, (), None)
        return Verification(
            conditions,
            failures,
            _verification_failure(result, tool, verifier, conditions, failures),
        )

    async def _record_verification(
        self,
        tool: ToolPort,
        verifier: VerifierPort,
        result: ExecutionResult,
        verification: Verification,
        *,
        recovered: bool = False,
    ) -> None:
        """``EXECUTION_VERIFIED``: passed or failed, which conditions, which failed — never the
        content that was compared (§57). On a resume the payload says so."""
        outcome = "passed" if verification.error is None else "failed"
        await self._audit.append(
            AuditEvent(
                id=AuditEventId(self._ids.new_uuid()),
                created_at=self._clock.now(),
                event_type=AuditEventType.EXECUTION_VERIFIED,
                actor=self._actor,
                summary=f"verify: {outcome} {result.capability_id} by {verifier.name}",
                task_id=result.task_id,
                step_id=result.step_id,
                capability_id=result.capability_id,
                device_id=result.device_id,
                decision_id=result.decision_id,
                authorization_id=result.authorization_id,
                tool_name=tool.name,
                error=verification.error,
                payload={
                    "passed": verification.error is None,
                    "result_id": str(result.id),
                    "verifier": verifier.name,
                    "conditions": list(verification.conditions),
                    "failed": [_condition_of(failure) for failure in verification.failures],
                    "device": _device(result),
                    **({RECOVERED: True} if recovered else {}),
                },
            )
        )


def _split(
    stored: Sequence[ExecutionResult],
) -> tuple[tuple[ExecutionResult, ...], tuple[ExecutionResult, ...]]:
    """The stored results of a step as (STARTED records, outcomes) — ADR 0021 §1.

    A step runs once, so at most one of each: the split is what lets "the tool ran and its
    outcome is here" be told apart from "the tool was started and never came back", which are
    the two facts the resume path and the interrupted path rest on.
    """
    started = tuple(r for r in stored if r.status is ExecutionStatus.STARTED)
    return started, tuple(r for r in stored if r.status is not ExecutionStatus.STARTED)


def _event_about(
    events: Sequence[AuditEvent], event_type: AuditEventType, result_id: ExecutionId
) -> AuditEvent | None:
    """The last event of this type whose payload names this result, or ``None``."""
    for event in reversed(events):
        if event.event_type is event_type and event.payload.get("result_id") == str(result_id):
            return event
    return None


def _device(result: ExecutionResult) -> JsonValue:
    """The node a result ran on, as an audit payload carries it (ADR 0019 §4).

    The result is the authority, not the ``device_id`` of the call: on a resumed run the tool ran
    in an earlier call, on the node that call chose, and reporting the node of the retry would
    attribute the effect to whoever happens to pick the step up.
    """
    return None if result.device_id is None else str(result.device_id)


def _condition_of(failure: ErrorMetadata) -> str:
    """The condition a failure is about, or its code when it is about no condition."""
    condition = failure.details.get("condition")
    return condition if isinstance(condition, str) else failure.code


def _verification_failure(
    result: ExecutionResult,
    tool: ToolPort,
    verifier: VerifierPort,
    conditions: Sequence[str],
    failures: Sequence[ErrorMetadata],
) -> ErrorMetadata:
    """The one error a failed verification becomes (§64; ADR 0014 §7): what (``code``,
    ``message``), why (``cause``), which tool, which device; no fix attempted, retryable only
    if every failure is."""
    named = ", ".join(f"{_condition_of(f)} ({f.code})" for f in failures)
    reported = [f.model_dump(mode="json") for f in failures]
    return ErrorMetadata(
        code=VERIFICATION_FAILED,
        message=(
            f"{len(failures)} of {len(conditions)} success conditions failed for "
            f"{result.capability_id}: {named}"
        ),
        cause="; ".join(f.message for f in failures),
        tool_name=tool.name,
        device_id=result.device_id,
        retryable=all(f.retryable for f in failures),
        details={
            "conditions": list(conditions),
            "failures": [
                {
                    "condition": _condition_of(f),
                    "code": f.code,
                    "message": f.message,
                    "retryable": f.retryable,
                    "details": {k: v for k, v in r["details"].items() if k != "condition"},
                }
                for f, r in zip(failures, reported, strict=True)
            ],
            "result_id": str(result.id),
            "verifier": verifier.name,
            "device": _device(result),
        },
    )


def _failure_of(result: ExecutionResult, tool: ToolPort) -> ErrorMetadata:
    """The error a step is failed with: the tool's, or one named after the status."""
    if result.error is not None:
        return result.error
    return ErrorMetadata(
        code=f"tool.{result.status.value.lower()}",
        message=f"{tool.name} ended with status {result.status.value}",
        tool_name=tool.name,
    )
