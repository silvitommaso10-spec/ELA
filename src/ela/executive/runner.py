"""The Task Runner (spec §14, §15, §17): the loop that walks a plan to its end (ADR 0019).

Everything one step needs has existed since M6.2 and nothing put it in a row. The graph says
which steps may run (``GraphState.ready``), the orchestrator says on which node (``place``), the
executor runs one with permission, authorization, verification and resume-after-crash
(``Executor.execute``), the engine closes the task when every step is COMPLETED. This module is
the driver, and it is deliberately thin: **it writes nothing of its own**.

Every fact a run produces is already someone's event — ``place`` writes ``DEVICE_SELECTED`` or
``DEVICE_UNAVAILABLE``, the engine writes ``TASK_*`` and ``STEP_*``, the executor writes
``PERMISSION_DECIDED``, ``TOOL_EXECUTED`` and ``EXECUTION_VERIFIED`` — so a second event from
here would be noise in the chain of §32 (ADR 0017 §6, generalised). No new ``AuditEventType``, no
new port, no new table.

Two properties make the loop re-entrant, which is what lets a crashed run be resumed by simply
calling :meth:`TaskRunner.run` again (ADR 0019 §5):

* **a RUNNING step is picked before any ready one.** ``ready()`` returns PENDING steps only, so a
  runner that looked only there would never pick up a step a crash — or an approval — left
  RUNNING;
* **a RUNNING step is not placed again**: its node is read back from the ``STEP_STARTED`` of the
  audit. The node of a started step is a fact, not a decision to retake, and re-placing could
  name a second node while a tool has already run on the first.

Everything else the loop needs is re-derived from the stores on every iteration, so no state
survives in memory between two of them.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Final, NamedTuple

from ela.devices.orchestrator import DeviceOrchestrator
from ela.domain import (
    AuditEventType,
    DeviceId,
    PrivacyLevel,
    StepId,
    StepState,
    Task,
    TaskId,
    TaskState,
)
from ela.executive.errors import RunnerError
from ela.executive.executor import Execution, Executor
from ela.ports import AuditLog, ExecutionResultStore, TaskRepository
from ela.tasks.engine import TaskEngine
from ela.tasks.graph import GraphState

__all__ = ["OUTCOMES", "RUNNABLE_STATES", "Run", "RunOutcome", "TaskRunner"]


class RunOutcome(StrEnum):
    """Why one call of :meth:`TaskRunner.run` stopped."""

    COMPLETED = "completed"
    """Every step COMPLETED and the task closed."""
    FAILED = "failed"
    """A step failed and the task is FAILED, its pending descendants CANCELLED."""
    DENIED = "denied"
    """The Guardian denied a step; the task is DENIED and nothing ran."""
    WAITING_APPROVAL = "waiting_approval"
    """A step needs the user's consent (§30). The next run resumes it."""
    WAITING_DEVICE = "waiting_device"
    """No node was eligible: the task is QUEUED and does **not** fail (ADR 0017 §6)."""
    CANCELLED = "cancelled"
    """Somebody stopped the task (§65). A decision, and the audit says whose."""
    EXPIRED = "expired"
    """The task ran out of time (§14). Nobody decided anything; a deadline passed."""


OUTCOMES: Final[Mapping[TaskState, RunOutcome]] = MappingProxyType(
    {
        TaskState.COMPLETED: RunOutcome.COMPLETED,
        TaskState.FAILED: RunOutcome.FAILED,
        TaskState.DENIED: RunOutcome.DENIED,
        TaskState.WAITING_APPROVAL: RunOutcome.WAITING_APPROVAL,
        TaskState.CANCELLED: RunOutcome.CANCELLED,
        TaskState.EXPIRED: RunOutcome.EXPIRED,
    }
)
"""The states in which the loop has nothing left to do, and the outcome each one is reported as.

One table for both the check at the door and the check between two iterations: a task already
closed when ``run`` is called is reported exactly as one closed by the call itself, and the empty
``Run.steps`` is what says which of the two happened.

One state, one outcome. A task somebody stopped and a task whose deadline passed are two
different facts — one is a decision with an actor behind it, the other is time running out — and
collapsing them into a single "terminal" would throw away a distinction that cannot be recovered
later (review of M6.3).
"""

RUNNABLE_STATES: Final[frozenset[TaskState]] = frozenset({TaskState.QUEUED, TaskState.EXECUTING})
"""The two states a plan can be walked from (§14): ready to start, or already under way.

CREATED and PLANNING are not here — a task without a plan has no graph to walk, and producing
one is the Planner's job (§13), not this module's.
"""


class Run(NamedTuple):
    """What one call of :meth:`TaskRunner.run` did.

    ``steps`` are the steps this call executed, in the order it executed them; ``executions`` is
    the executor's word about each, in the same order. Both are empty for a call that found
    nothing to do. Nothing here is persisted: the trail, the results and the audit are.
    """

    task: Task
    outcome: RunOutcome
    steps: tuple[StepId, ...]
    executions: tuple[Execution, ...]


class TaskRunner:
    """Walks the graph of one task: choose a step, choose a node, execute, close (ADR 0019).

    ``run`` returns as soon as it cannot go on — the task closed, the user's answer is needed, no
    node is eligible. It never sleeps and never polls: who calls it again when the world has
    changed (a node comes back, the user answers) is the API of M8.1 or the Proactive Core, not
    this class.
    """

    __slots__ = ("_audit", "_engine", "_executor", "_orchestrator", "_repository", "_results")

    def __init__(
        self,
        *,
        engine: TaskEngine,
        orchestrator: DeviceOrchestrator,
        executor: Executor,
        repository: TaskRepository,
        results: ExecutionResultStore,
        audit: AuditLog,
    ) -> None:
        self._engine = engine
        self._orchestrator = orchestrator
        self._executor = executor
        self._repository = repository
        self._results = results
        self._audit = audit

    async def run(
        self, task_id: TaskId, *, max_privacy: PrivacyLevel = PrivacyLevel.LOCAL_ONLY
    ) -> Run:
        """Walk the plan of ``task_id`` as far as it goes, one step at a time (ADR 0019 §3).

        ``max_privacy`` is the most permissive node the caller tolerates and defaults to the most
        restrictive level, as ``place`` does: a privacy nobody declared is not a permission (§33,
        §57; ADR 0017 §8).

        :class:`~ela.executive.errors.RunnerError` before anything is written for a task that
        cannot be walked: one still CREATED or PLANNING, or one whose plan has no steps.

        The loop terminates without a counter, and the reason is worth stating: every iteration
        that does not return closes a step. ``execute`` refuses a step that is not RUNNING, and
        each of its paths either moves the step out of RUNNING or leaves the task in a state of
        :data:`OUTCOMES`, which the next iteration returns on. So at most one iteration per step
        of the plan — asserted for real by ``test_a_run_executes_each_step_at_most_once``.
        """
        task = await self._repository.get(task_id)
        if task.state in OUTCOMES:
            return Run(task, OUTCOMES[task.state], (), ())
        if task.state not in RUNNABLE_STATES:
            raise RunnerError(
                task_id, f"a plan is walked from QUEUED or EXECUTING, not from {task.state.value}"
            )
        graph = await self._engine.graph(task_id)
        if not len(graph.graph):
            raise RunnerError(
                task_id,
                "the plan has no steps: there is nothing to walk, and no result to close the "
                "task with",
            )

        steps: list[StepId] = []
        executions: list[Execution] = []
        while True:
            if graph.is_blocked:
                task = await self._fail(task_id)
                return Run(task, RunOutcome.FAILED, tuple(steps), tuple(executions))
            if graph.is_complete:
                task = await self._complete(task_id, graph)
                return Run(task, RunOutcome.COMPLETED, tuple(steps), tuple(executions))

            step_id = self._next(task_id, graph)
            device_id = await self._node(task_id, step_id, graph, max_privacy)
            if device_id is None:
                task = await self._wait(task)
                return Run(task, RunOutcome.WAITING_DEVICE, tuple(steps), tuple(executions))
            if task.state is TaskState.QUEUED:
                task = await self._engine.start(task_id, device_id=device_id)
            if graph.states[step_id] is StepState.PENDING:
                await self._engine.start_step(task_id, step_id, device_id=device_id)

            execution = await self._executor.execute(task_id, step_id, device_id=device_id)
            steps.append(step_id)
            executions.append(execution)
            task = execution.task
            if task.state in OUTCOMES:
                return Run(task, OUTCOMES[task.state], tuple(steps), tuple(executions))
            graph = await self._engine.graph(task_id)

    # ----------------------------------------------------------------------------------
    # Which step, and on which node
    # ----------------------------------------------------------------------------------

    def _next(self, task_id: TaskId, graph: GraphState) -> StepId:
        """The step this iteration works on: a RUNNING one if there is one, else the first ready.

        A RUNNING step comes first because ``ready()`` never names one: a step left RUNNING by a
        crash (window R3) or by an approval (window R8) would otherwise be invisible and the plan
        would stall with a step nobody finishes. The runner is sequential, so there is at most
        one; two is an incoherence in the trail and a doubt is a failure (§33).
        """
        running = [step for step, state in graph.states.items() if state is StepState.RUNNING]
        if len(running) > 1:
            raise RunnerError(
                task_id,
                f"{len(running)} steps are RUNNING ({', '.join(str(s) for s in running)}); "
                "a sequential runner leaves at most one",
            )
        return running[0] if running else graph.ready()[0]

    async def _node(
        self, task_id: TaskId, step_id: StepId, graph: GraphState, max_privacy: PrivacyLevel
    ) -> DeviceId | None:
        """The node ``step_id`` runs on, or ``None`` when no node is eligible (ADR 0019 §4).

        A PENDING step is placed; a RUNNING one is **not placed again** — its node is read back
        from the audit, because a step that was started has already been given a node and asking
        a second time could name another one while a tool ran on the first.
        """
        if graph.states[step_id] is StepState.RUNNING:
            return await self._started_on(task_id, step_id)
        placement = await self._orchestrator.place(
            graph.graph.step(step_id), task_id=task_id, max_privacy=max_privacy
        )
        return None if placement.device is None else placement.device.id

    async def _started_on(self, task_id: TaskId, step_id: StepId) -> DeviceId:
        """The node the last ``STEP_STARTED`` of this step names; a doubt is a failure (§33)."""
        for event in reversed(await self._audit.read(task_id=task_id)):
            if event.event_type is AuditEventType.STEP_STARTED and event.step_id == step_id:
                if event.device_id is None:
                    break
                return event.device_id
        raise RunnerError(
            task_id,
            f"step {step_id} is RUNNING but no STEP_STARTED names the node it runs on; "
            "it cannot be resumed without inventing one",
        )

    # ----------------------------------------------------------------------------------
    # The three ways a run ends on its own
    # ----------------------------------------------------------------------------------

    async def _wait(self, task: Task) -> Task:
        """No node was eligible: the task **waits** as QUEUED (ADR 0017 §6), and nothing else.

        No ``fail``, no ``fail_step``, no ``ErrorMetadata`` — a missing node is not an error of
        the action — and no audit event: ``place`` has already written ``DEVICE_UNAVAILABLE``
        with every candidate and its refusals, and a second event for the same fact is noise.
        Retrying is the caller's next ``run``, not a spin here.
        """
        if task.state is TaskState.EXECUTING:
            return await self._engine.queue(task.id, reason="no eligible device")
        return task

    async def _complete(self, task_id: TaskId, graph: GraphState) -> Task:
        """Close a plan whose every step is COMPLETED (ADR 0019 §6).

        The closing result is the one of the **last step in topological order**, read back from
        the store — not whichever result this call happens to hold. ``complete`` keys idempotency
        on ``result_id``: a rule that depended on what is in memory would pick a different result
        after a crash, and the second call would be refused instead of being a no-op.
        """
        last = graph.graph.order[-1]
        stored = await self._results.for_step(task_id, last)
        if len(stored) != 1:
            raise RunnerError(
                task_id,
                f"step {last} is COMPLETED with {len(stored)} stored results; the task cannot be "
                "closed on a result that is missing or ambiguous",
            )
        return await self._engine.complete(task_id, stored[0])

    async def _fail(self, task_id: TaskId) -> Task:
        """Close a blocked plan with the error its failed step carries (ADR 0014 §4).

        A step failed by the tool leaves the task EXECUTING on purpose: deciding about the task
        belongs to whoever orchestrates, and that is this class. The error is the one already in
        the ``STEP_FAILED`` of the audit, not a new one — a second description of the same
        failure would be a second story about it. The cascade over pending descendants was
        applied by ``fail_step``; ``fail`` has no idempotency key, so a retry after a crash
        between the two is a silent no-op.
        """
        for event in reversed(await self._audit.read(task_id=task_id)):
            if event.event_type is AuditEventType.STEP_FAILED and event.error is not None:
                return await self._engine.fail(task_id, event.error)
        raise RunnerError(
            task_id,
            "the plan is blocked but no STEP_FAILED in the audit carries the error it failed "
            "with; the task cannot be closed on an error nobody recorded",
        )
