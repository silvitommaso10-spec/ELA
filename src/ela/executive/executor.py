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
  then the step is closed. A grant that turns out expired or exhausted at ``consume`` asks
  again; one that vanished fails the step with :data:`GRANT_VANISHED`.

One instant serves ``authorize`` and ``consume``: ``decision.created_at`` (ADR 0012 §6, ADR 0013
§6). A grant born from an approval has a deterministic id per approval, so a retry after a crash
finds it instead of minting a second one, and writes the ``AUTHORIZATION_GRANTED`` a crash may
have skipped (ADR 0013 §3, §8). What never enters the audit trail: the arguments and the tool's
output (§57).
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
    AuditLog,
    AuthorizationNotUsableError,
    AuthorizationStore,
    AuthorizingGuardianPort,
    CapabilityRegistryPort,
    Clock,
    IdGenerator,
    NotAllowedError,
    NotFoundError,
    TaskRepository,
    ToolPort,
    ToolRegistryPort,
)
from ela.tasks.engine import TaskEngine
from ela.tasks.graph import GraphState

__all__ = [
    "AUTHORIZATION_NAMESPACE",
    "CONSUMING_RULES",
    "DEFAULT_APPROVAL_TTL",
    "GRANT_VANISHED",
    "LOCAL_DEVICE",
    "TOOL_EXCEPTION",
    "TOOL_REFUSED",
    "Execution",
    "Executor",
    "approved_targets",
    "select_authorization",
]

AUTHORIZATION_NAMESPACE: Final = UUID("2d9b7f61-8c4a-4e0b-9f3d-6a1e5c7b8d90")
"""The UUID namespace of approval-born grants: ``uuid5(AUTHORIZATION_NAMESPACE, str(approval.id))``.

Arbitrary and fixed forever: one approval gives one grant, however many times the call that
uses it is retried (ADR 0013 §3). Changing it would change the id of every such grant.
"""

DEFAULT_APPROVAL_TTL: Final = timedelta(hours=24)
"""How long a request for approval stays answerable (ADR 0013 §5, decision E).

A setting in M8.1. Who expires a task left WAITING_APPROVAL is not the executor: recovery or the
Proactive Core, later.
"""

CONSUMING_RULES: Final[frozenset[Rule]] = frozenset(
    {Rule.APPROVAL_UNLESS_AUTHORIZED, Rule.AUTHORIZATION_REQUIRED}
)
"""The rules under which an ``ALLOWED`` decision rests on the grant it was given (ADR 0011 §6,
§9): only then is the grant consumed. ``ALLOW`` and ``ALLOW_WITHIN_SCOPE`` ignore the grant."""

LOCAL_DEVICE: Final = "local"
"""Where a tool runs until the Device Orchestrator (§17) exists: in the Core, ``device_id=None``."""

TOOL_EXCEPTION: Final = "tool.exception"
"""Error code of a result synthesised from an exception the tool raised while acting."""
TOOL_REFUSED: Final = "tool.refused"
"""Error code of a step failed because the tool refused the decision (``NotAllowedError``)."""
GRANT_VANISHED: Final = "grant_vanished"
"""Error code of a step failed because the grant vanished between ``authorize`` and ``consume``."""

_CONSUMING_RULE_VALUES: Final[frozenset[str]] = frozenset(rule.value for rule in CONSUMING_RULES)


class Execution(NamedTuple):
    """What one call of :meth:`Executor.execute` did (ADR 0013 §1).

    ``result`` is set only if the tool ran; ``approval`` only if one was requested; ``graph`` is
    the state of the plan as last read or written. ``decision`` is always there: every path
    after the preconditions goes through the Guardian.
    """

    task: Task
    step_id: StepId
    graph: GraphState
    decision: PermissionDecision
    authorization: Authorization | None
    result: ExecutionResult | None
    approval: Approval | None


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

    ``actor`` is who the executor says it is in ``TOOL_EXECUTED`` (ELA acts); the user signs
    ``AUTHORIZATION_GRANTED`` through the approval. ``authorization_ttl`` is the life of a grant
    born here (ADR 0012 §2), ``approval_ttl`` the life of a request for approval.
    """

    def __init__(
        self,
        *,
        registry: CapabilityRegistryPort,
        tools: ToolRegistryPort,
        guardian: AuthorizingGuardianPort,
        engine: TaskEngine,
        repository: TaskRepository,
        authorizations: AuthorizationStore,
        audit: AuditLog,
        clock: Clock,
        ids: IdGenerator,
        actor: Actor,
        authorization_ttl: timedelta = DEFAULT_AUTHORIZATION_TTL,
        approval_ttl: timedelta = DEFAULT_APPROVAL_TTL,
    ) -> None:
        if approval_ttl <= timedelta(0):
            raise ValueError(f"approval_ttl must be positive, not {approval_ttl}")
        self._registry = registry
        self._tools = tools
        self._guardian = guardian
        self._engine = engine
        self._repository = repository
        self._authorizations = authorizations
        self._audit = audit
        self._clock = clock
        self._ids = ids
        self._actor = actor
        self._authorization_ttl = authorization_ttl
        self._approval_ttl = approval_ttl

    async def execute(
        self,
        task_id: TaskId,
        step_id: StepId,
        arguments: JsonMapping,
        *,
        approval: Approval | None = None,
    ) -> Execution:
        """Run the one capability of a RUNNING step of an EXECUTING task (ADR 0013 §1–§9).

        ``approval`` is the user's GRANTED answer to a request this executor made earlier: it
        becomes the grant the call runs under. Preconditions that fail raise before anything is
        written: :class:`~ela.executive.errors.ExecutorError`,
        :class:`~ela.tasks.errors.UnknownStepError`, ``CapabilityNotFound``, ``ToolNotFound``,
        ``ApprovalMismatchError``.
        """
        task = await self._repository.get(task_id)
        if task.state is not TaskState.EXECUTING:
            raise ExecutorError(task_id, f"a tool needs an EXECUTING task, not {task.state.value}")
        graph = await self._engine.graph(task_id)
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
        spec = self._registry.get(step.required_capabilities[0])
        tool = self._tools.get(spec.id)
        targets = targets_of(spec, arguments)

        now = self._clock.now()
        authorization: Authorization | None
        if approval is not None:
            authorization, uses = await self._grant(approval, task, step, spec, now)
        else:
            authorization, uses = await self._find_authorization(spec, targets, task, step, now)

        decision = await self._guardian.authorize(
            spec,
            arguments,
            task=task,
            step=step,
            authorization=authorization,
            authorization_uses=uses,
        )
        if decision.outcome is PermissionOutcome.DENIED:
            task = await self._engine.deny(task_id, decision=decision)
            return Execution(task, step_id, graph, decision, authorization, None, None)
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

        result = await self._run_tool(tool, decision, arguments)
        if result is None:
            refused = ErrorMetadata(
                code=TOOL_REFUSED,
                message=f"{tool.name} refused the decision {decision.id}",
                tool_name=tool.name,
            )
            return await self._fail(task, graph, decision, authorization, refused)
        await self._record_execution(tool, decision, authorization, result, targets, consumed)
        if result.status is ExecutionStatus.SUCCEEDED:
            graph = await self._engine.complete_step(task_id, step_id, result)
        else:
            graph = await self._engine.fail_step(task_id, step_id, _failure_of(result, tool))
        return Execution(task, step_id, graph, decision, authorization, result, None)

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
            id=ApprovalId(self._ids.new_uuid()),
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
        task = await self._engine.request_approval(decision.task_id, approval)
        return Execution(task, step.id, graph, decision, authorization, None, approval)

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
        return Execution(task, decision.step_id, graph, decision, authorization, None, None)

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
        decision: PermissionDecision,
        authorization: Authorization | None,
        result: ExecutionResult,
        targets: Sequence[object],
        consumed: int | None,
    ) -> None:
        """``TOOL_EXECUTED``: the fact, the decision, the grant, the targets — never the
        arguments nor the output (§57)."""
        await self._audit.append(
            AuditEvent(
                id=AuditEventId(self._ids.new_uuid()),
                created_at=result.created_at,
                event_type=AuditEventType.TOOL_EXECUTED,
                actor=self._actor,
                summary=f"execute: {result.status.value} {decision.capability_id} by {tool.name}",
                task_id=decision.task_id,
                step_id=decision.step_id,
                capability_id=decision.capability_id,
                decision_id=decision.id,
                authorization_id=None
                if consumed is None or authorization is None
                else authorization.id,
                tool_name=tool.name,
                error=result.error,
                payload={
                    "status": result.status.value,
                    "result_id": str(result.id),
                    "targets": _json_targets(targets),
                    "duration_ms": result.duration_ms,
                    "device": LOCAL_DEVICE,
                    "uses": consumed,
                },
            )
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
