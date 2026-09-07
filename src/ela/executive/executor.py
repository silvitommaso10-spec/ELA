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
EXECUTING is failed now (ADR 0015 §7). What a retry cannot repair — the instant between the
tool's effect and the insert of its result — is declared, not hidden.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Final, NamedTuple
from uuid import UUID, uuid5

from ela.domain import (
    Actor,
    ActorKind,
    Approval,
    ApprovalId,
    ApprovalStatus,
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
    StepId,
    StepState,
    Task,
    TaskId,
    TaskState,
    TaskStep,
)
from ela.executive.errors import ExecutorError
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
    "GRANT_VANISHED",
    "MAX_APPROVAL_TTL",
    "RECOVERED",
    "TOOL_EXCEPTION",
    "TOOL_REFUSED",
    "VERIFICATION_EXCEPTION",
    "VERIFICATION_FAILED",
    "Execution",
    "Executor",
    "Verification",
    "approved_targets",
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
VERIFICATION_FAILED: Final = "verification.failed"
"""Error code of a step, and its task, failed because a success condition did not hold (ADR
0014 §4): the tool said SUCCEEDED and the world said otherwise."""
VERIFICATION_EXCEPTION: Final = "verification.exception"
"""Error code of a step, and its task, failed because the verifier raised: a verifier that
could not answer has not verified, and a doubt is a failure (§33)."""

_CONSUMING_RULE_VALUES: Final[frozenset[str]] = frozenset(rule.value for rule in CONSUMING_RULES)


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
        self._authorization_ttl = authorization_ttl
        self._approval_ttl = approval_ttl

    async def execute(self, task_id: TaskId, step_id: StepId, *, device_id: DeviceId) -> Execution:
        """Run and verify the one capability of a RUNNING step of an EXECUTING task (ADR 0013
        §1–§9, ADR 0014 §3–§4), or resume what an earlier call left unfinished (ADR 0015 §5–§7).

        The arguments are the step's (``TaskStep.arguments``, ADR 0018), not the caller's: a
        retry is the *same* call and must run on the *same* arguments, or the targets an audit
        event records would not be the targets the tool acted on. ``device_id`` is the node the
        orchestrator chose (ADR 0019 §4); it is mandatory because an execution without a node is
        not a thing this system should be able to express.

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
        step = graph.graph.step(step_id)
        state = graph.states[step_id]
        if state is StepState.FAILED:
            unfinished = await self._unfinished_verification_failure(task_id, step_id)
            if unfinished is not None:  # ADR 0015 §7: the task was to be failed with it
                task = await self._engine.fail(task_id, unfinished)
                return Execution(task, step_id, graph, None, None, None, None, None)
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
        arguments = step.arguments
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
        targets = targets_of(spec, arguments)

        stored = await self._results.for_step(task_id, step_id)
        if len(stored) > 1:
            raise ExecutorError(
                task_id, f"step {step_id} has {len(stored)} results; a step runs once"
            )
        if stored:  # the tool ran in an earlier call: resume from the first missing write
            return await self._resume(
                task, graph, step, tool, verifier, arguments, targets, stored[0]
            )

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
            return await self._ask(graph, step, spec, decision, authorization, decision.reason)

        consumed: int | None = None
        if authorization is not None and decision.metadata.get("rule") in _CONSUMING_RULE_VALUES:
            try:
                consumed = await self._authorizations.consume(
                    authorization.id, now=decision.created_at
                )
            except AuthorizationNotUsableError as unusable:
                return await self._ask(graph, step, spec, decision, authorization, unusable.reason)
            except NotFoundError:
                vanished = ErrorMetadata(
                    code=GRANT_VANISHED,
                    message=f"authorization {authorization.id} vanished before it was consumed",
                    tool_name=tool.name,
                )
                return await self._fail(task, graph, decision, authorization, vanished)

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
                "authorization_id": None
                if consumed is None or authorization is None
                else authorization.id,
            }
        )
        await self._results.add(result)
        await self._record_execution(tool, result, targets, consumed)
        if result.status is not ExecutionStatus.SUCCEEDED:
            graph = await self._engine.fail_step(task_id, step_id, _failure_of(result, tool))
            return Execution(task, step_id, graph, decision, authorization, result, None, None)

        verification = await self._verify(verifier, tool, step, arguments, result)
        await self._record_verification(tool, verifier, result, verification)
        return await self._close(task, graph, step, decision, authorization, result, verification)

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
            prompt=f"{spec.id}{where} for step {step.id} ({step.goal}): {reason}",
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
    ) -> None:
        """``TOOL_EXECUTED``: the fact, the decision and the grant the result carries, the
        targets — never the arguments nor the output (§57). ``created_at`` is the result's when
        written with the run, the clock's on a resume, which also marks the payload."""
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
                error=result.error,
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
