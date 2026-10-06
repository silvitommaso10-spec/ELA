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

from ela.devices.orchestrator import DeviceOrchestrator, PlacementDecision
from ela.domain import (
    AuditEventType,
    DeviceId,
    ExecutionStatus,
    Halt,
    PrivacyLevel,
    StepId,
    StepState,
    Task,
    TaskEventType,
    TaskId,
    TaskState,
)
from ela.executive.assignments import Assignments, Lapse, Stand, Standing
from ela.executive.errors import RunnerError
from ela.executive.executor import Execution, Executor
from ela.ports import AuditLog, ExecutionResultStore, LocalBeat, TaskRepository
from ela.tasks.engine import TERMINAL_STATES, TaskEngine
from ela.tasks.errors import TaskError
from ela.tasks.graph import GraphState

__all__ = ["OUTCOMES", "RUNNABLE_STATES", "Run", "RunOutcome", "TaskRunner"]


class RunOutcome(StrEnum):
    """Why one call of :meth:`TaskRunner.run` stopped."""

    COMPLETED = "completed"
    """Every step COMPLETED and the task closed."""
    FAILED = "failed"
    """A step failed and the task is FAILED, its pending descendants CANCELLED."""
    DENIED = "denied"
    """The task is DENIED — the Guardian denied a step, or the user said no to a question — and the
    denied step did not run. Steps before it may have (M6.3b, ADR 0051). The reason says which:
    ``deny_by_decision`` or ``deny_by_approval`` (M13.1c, ADR 0055)."""
    WAITING_APPROVAL = "waiting_approval"
    """A step needs the user's consent (§30). The next run resumes it."""
    WAITING_DEVICE = "waiting_device"
    """No node was eligible: the task is QUEUED and does **not** fail (ADR 0017 §6)."""
    CANCELLED = "cancelled"
    """Somebody stopped the task (§65). A decision, and the audit says whose. Said at the door and,
    since M6.3c, from inside the walk too — a stop under a running step is an outcome, never a 409
    (ADR 0054 §6) —, with the words of the stop and what the step in progress had done."""
    EXPIRED = "expired"
    """The task ran out of time (§14). Nobody decided anything; a deadline passed — and the reason
    says which: the question nobody answered, in the words of its transition (M13.1c, ADR 0055)."""
    ASSIGNED = "assigned"
    """A step was handed to a remote node and has not come back (M12.2, ADR 0038 §10).

    The task stays EXECUTING and the step RUNNING: the work is under way somewhere else. A later
    run finds it still out, or closed by the node's delivery, or — once the assignment has expired
    — applies the answer of M12.1, D14. Not a state: §14 fixes the ten, and this is the outcome of
    **one call**, as ``WAITING_DEVICE`` is, which is why :data:`OUTCOMES` does not grow.
    """


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
closed when ``run`` is called is reported exactly as one closed by the call itself. The empty
``Run.steps`` does **not** tell the two apart: it says that the call handled no step, and a retry
that closes a task whose last step an earlier call finished — windows R5 and R6 — handles none
either (M6.3b, ADR 0051 §2). Who closed the task is in the audit.

One state, one outcome. A task somebody stopped and a task whose deadline passed are two
different facts — one is a decision with an actor behind it, the other is time running out — and
collapsing them into a single "terminal" would throw away a distinction that cannot be recovered
later (review of M6.3).
"""

_REASONED: Final[frozenset[TaskState]] = frozenset(TERMINAL_STATES - {TaskState.COMPLETED})
"""The ends whose run says why: every one but ``COMPLETED`` (M13.1c, ADR 0055)."""

RUNNABLE_STATES: Final[frozenset[TaskState]] = frozenset({TaskState.QUEUED, TaskState.EXECUTING})
"""The two states a plan can be walked from (§14): ready to start, or already under way.

CREATED and PLANNING are not here — a task without a plan has no graph to walk, and producing
one is the Planner's job (§13), not this module's.
"""


class Run(NamedTuple):
    """What one call of :meth:`TaskRunner.run` did.

    ``steps`` are the steps this call **handled**, in the order it handled them: the ones the
    executor gave its answer about in this call — it ran, it was closed from what a node delivered
    or a crash left, it failed, it was denied, or ELA stopped on it to ask for consent (M6.3b,
    ADR 0051 §1). A step handed to a node is not among them, because the node will answer and
    ``reason`` names it; nor is a step waiting for a node, which the executor did not see in this
    call. ``executions`` is the executor's word about each, in the same order. Both are empty for a
    call that handled no step, which says nothing about who closed the task (ADR 0051 §2). Nothing
    here is persisted: the trail, the results and the audit are.
    """

    task: Task
    outcome: RunOutcome
    steps: tuple[StepId, ...]
    executions: tuple[Execution, ...]
    reason: str | None = None
    """Why the run stopped, when the answer alone does not say (M6.1b dec. F).

    ``WAITING_DEVICE`` used to travel as a bare word while the orchestrator had already written a
    precise sentence in the audit — every candidate, every refusal, and for a missing tool its
    name — which the person waiting never saw. This is that sentence, carried out with the result
    instead of left behind in the log.

    ``ASSIGNED`` carries one too, and it is the assignment's: the node, the work and the deadline
    by which it is due (M12.2, ADR 0038 §10). What a person deciding whether to wait has to read.

    **Every end but ``COMPLETED`` carries one, always** — ``DENIED``, ``FAILED``, ``CANCELLED`` and
    ``EXPIRED`` —: the words of the transition that ended the task, the summary of its audit event
    (M13.1c, ADR 0055; the form of ADR 0054 §7). The same for the call that ended the task and for
    every call after it, which finds it at the door: until M13.1c the door said nothing for a denial
    or a failure, and the call that closed a task said nothing when the executor's word carried no
    error — a failure a node delivered, a step a crash left. The name of the operation says who
    ended it: ``deny_by_decision`` the Guardian, ``deny_by_approval`` the user, ``recover`` the
    start-up. **A diagnosis that lives where nobody looks is not a diagnosis** (M13.1).

    ``None`` for every other outcome: those say what happened. The runner still writes nothing of
    its own (ADR 0019) — every reason is the placement's, the assignment's or the transition's,
    passed on rather than composed here.
    """
    halt: Halt | None = None
    """What the step in progress had done when the task was stopped (M6.3c, ADR 0054 §7); ``None``
    for every outcome but ``CANCELLED``, and for a stop that found no step in progress."""


class TaskRunner:
    """Walks the graph of one task: choose a step, choose a node, execute, close (ADR 0019).

    ``run`` returns as soon as it cannot go on — the task closed, the user's answer is needed, no
    node is eligible. It never sleeps and never polls: who calls it again when the world has
    changed (a node comes back, the user answers) is the API of M8.1 or the Proactive Core, not
    this class.
    """

    __slots__ = (
        "_assignments",
        "_audit",
        "_beat",
        "_engine",
        "_executor",
        "_orchestrator",
        "_repository",
        "_results",
    )

    def __init__(
        self,
        *,
        engine: TaskEngine,
        orchestrator: DeviceOrchestrator,
        executor: Executor,
        repository: TaskRepository,
        results: ExecutionResultStore,
        audit: AuditLog,
        assignments: Assignments,
        beat: LocalBeat,
    ) -> None:
        self._beat = beat
        self._engine = engine
        self._orchestrator = orchestrator
        self._executor = executor
        self._repository = repository
        self._results = results
        self._audit = audit
        self._assignments = assignments

    async def run(self, task_id: TaskId) -> Run:
        """Walk the plan of ``task_id`` as far as it goes, one step at a time (ADR 0019 §3).

        **How far the content may travel is the task's** (M12.2, D18, D20): ``task.max_privacy``,
        declared at creation and immutable, read here and handed to every placement of this walk.
        It used to be an argument of this method, defaulting to the strictest level — which was the
        safe default and the reason no remote node ever received work: the only caller that exists,
        ``POST /tasks/{id}/run``, had nothing to pass and nobody *could* declare it. An argument
        would also let two runs judge one task at two levels, and a step placed under ``TRUSTED``
        would be confirmed under ``LOCAL_ONLY`` by a later call that passed nothing.

        :class:`~ela.executive.errors.RunnerError` before anything is written for a task that
        cannot be walked: one still CREATED or PLANNING, or one whose plan has no steps.

        The loop terminates without a counter, and the reason is worth stating: every iteration
        that does not return closes a step **or releases one**, and a release happens at most once
        per step per call (M12.2, dec. F). ``execute`` refuses a step that is not RUNNING, and each
        of its paths either moves the step out of RUNNING, hands it to a node — which returns
        ``ASSIGNED`` — or leaves the task in a state of :data:`OUTCOMES`, which the next iteration
        returns on. A released step is PENDING and is placed again at once: on a remote node the
        new assignment returns the call, on ``local`` the iteration closes it. So at most two
        iterations per step of the plan — asserted for real by
        ``test_a_run_handles_each_step_at_most_once`` for the half that closes, and by
        ``test_a_plan_of_many_steps_releases_each_step_at_most_once_per_call`` for the half that
        releases.
        """
        walked = await self._walk(task_id)
        if walked.task.state in TERMINAL_STATES:
            return walked
        # The last act under the lock of ``run`` (M6.3c, ADR 0054 §5): a stop that landed after the
        # walk's last write is seen here, and nobody else would close its step — the route of the
        # stop leaves the closing to whoever holds the lock. After this read, nothing awaits until
        # the route releases the lock.
        task = await self._repository.get(task_id)
        if task.state in TERMINAL_STATES:
            return await self._ended(task, list(walked.steps), list(walked.executions))
        return walked

    async def answer(self, task_id: TaskId) -> Run:
        """What ``run`` would answer at the door for a task that has ended, **without closing
        anything** (M6.3c, decision 16 of the review): for a ``run`` that finds the lock taken by
        somebody else, who closes what is open. Never a ``409`` for a task that was stopped."""
        task = await self._repository.get(task_id)
        return Run(
            task,
            OUTCOMES[task.state],
            (),
            (),
            await self._reason(task),
            await self._executor.halt(task_id),
        )

    async def _walk(self, task_id: TaskId) -> Run:
        task = await self._repository.get(task_id)
        max_privacy = task.max_privacy
        if task.state in OUTCOMES:
            return await self._at_the_door(task)
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
        try:
            return await self._loop(task, graph, max_privacy, steps, executions)
        except TaskError:
            # A write of this walk found the task ended under it (M6.3c, ADR 0054 §6): a stop is an
            # outcome, never a 409. Anything else that raises is what it was.
            task = await self._repository.get(task_id)
            if task.state not in TERMINAL_STATES:
                raise
            return await self._ended(task, steps, executions)

    async def _loop(
        self,
        task: Task,
        graph: GraphState,
        max_privacy: PrivacyLevel,
        steps: list[StepId],
        executions: list[Execution],
    ) -> Run:
        task_id = task.id
        while True:
            if graph.is_blocked:
                task = await self._fail(task_id)
                # The plan cannot go on because a step failed — here, on a node that delivered it,
                # or in a call a crash cut short — and the reason is the transition's, which carries
                # that step's error: the same whoever failed the step (M13.1c, ADR 0055).
                return Run(
                    task,
                    RunOutcome.FAILED,
                    tuple(steps),
                    tuple(executions),
                    await self._reason(task),
                )
            if graph.is_complete:
                task = await self._complete(task_id, graph)
                return Run(task, RunOutcome.COMPLETED, tuple(steps), tuple(executions))

            step_id = self._next(task_id, graph)
            stand = await self._stand(task_id, step_id, graph)
            if stand.standing is Standing.LIVE:
                assert stand.assignment is not None
                return Run(
                    task,
                    RunOutcome.ASSIGNED,
                    tuple(steps),
                    tuple(executions),
                    await self._assignments.describe(stand.assignment),
                )
            if stand.standing is not Standing.NONE:
                execution = await self._left_behind(task_id, step_id, stand)
                if execution is not None:
                    steps.append(step_id)
                    executions.append(execution)
                    task = await self._repository.get(task_id)
                    if task.state in OUTCOMES:
                        return await self._closing(task, execution, steps, executions)
                graph = await self._engine.graph(task_id)
                continue
            placement = await self._node(task_id, step_id, graph, max_privacy)
            if placement.device is None:
                task = await self._wait(task)
                return Run(
                    task,
                    RunOutcome.WAITING_DEVICE,
                    tuple(steps),
                    tuple(executions),
                    placement.reason,
                )
            device_id = placement.device.id
            if task.state is TaskState.QUEUED:
                task = await self._engine.start(task_id, device_id=device_id)
            if graph.states[step_id] is StepState.PENDING:
                await self._engine.start_step(task_id, step_id, device_id=device_id)

            execution = await self._executor.execute(task_id, step_id, placement=placement)
            if execution.assignment is not None:
                # The call handed the step to a node instead of running it (ADR 0038 §10). It is
                # not among the steps this run handled: the answer about it is the node's to give,
                # and the reason names it (M6.3b, ADR 0051 §1).
                return Run(
                    execution.task,
                    RunOutcome.ASSIGNED,
                    tuple(steps),
                    tuple(executions),
                    await self._assignments.describe(execution.assignment),
                )
            steps.append(step_id)
            executions.append(execution)
            # Read again, never believed (M6.3c, ADR 0054 §6): ``execution.task`` is the task as
            # the executor read it before the tool, and a stop since then is only in the store.
            task = await self._repository.get(task_id)
            if task.state in OUTCOMES:
                return await self._closing(task, execution, steps, executions)
            graph = await self._engine.graph(task_id)

    # ----------------------------------------------------------------------------------
    # A task that ended: by this walk, or under it (M6.3c, ADR 0054 §5–§7)
    # ----------------------------------------------------------------------------------

    async def _closing(
        self, task: Task, execution: Execution, steps: list[StepId], executions: list[Execution]
    ) -> Run:
        """The walk stops on a task in a state of :data:`OUTCOMES`. A stop, or an end somebody else
        wrote, is :meth:`_ended`; one the walk itself reached is reported with the words of its
        transition — the one source of a reason since M13.1c, whoever wrote the end."""
        if task.state is TaskState.CANCELLED or (
            task.state in TERMINAL_STATES and execution.task.state is not task.state
        ):
            return await self._ended(task, steps, executions)
        return Run(
            task, OUTCOMES[task.state], tuple(steps), tuple(executions), await self._reason(task)
        )

    async def _ended(self, task: Task, steps: list[StepId], executions: list[Execution]) -> Run:
        """A task that ended under the walk: its open step closed, its reason passed, its halt.

        The reason is **never empty** for an end that has one (decision 4 of the session of M6.3c):
        the words of the transition that ended the task, which the engine always writes.
        """
        closed = await self._executor.close_open_step(task.id)
        if closed is not None and closed.step_id not in steps:
            steps.append(closed.step_id)
            executions.append(closed)
        return Run(
            task,
            OUTCOMES[task.state],
            tuple(steps),
            tuple(executions),
            await self._reason(task),
            await self._executor.halt(task.id),
        )

    async def _at_the_door(self, task: Task) -> Run:
        """A task already in a state of :data:`OUTCOMES` when ``run`` is called (ADR 0019 §10).

        An ended task whose step is still RUNNING has it closed here (M6.3c): the door is one of
        the places a stop's open step is closed, under the lock of ``run``.
        """
        if task.state not in TERMINAL_STATES:
            return Run(task, OUTCOMES[task.state], (), ())
        closed = await self._executor.close_open_step(task.id)
        handled = () if closed is None else (closed.step_id,)
        done = () if closed is None else (closed,)
        return Run(
            task,
            OUTCOMES[task.state],
            handled,
            done,
            await self._reason(task),
            await self._executor.halt(task.id),
        )

    async def _reason(self, task: Task) -> str | None:
        """The reason of a run whose task has ended, **the one source of it** (M13.1c, ADR 0055):
        the words of the transition that ended the task for every end but ``COMPLETED``, which
        explains itself — at the door, under a taken lock, at the end the walk reached, at a blocked
        plan, and for an end written under the walk. The same for the call that ended the task and
        for every call after it (decision D of the session). ``None`` for a task that has not
        ended."""
        if task.state not in _REASONED:
            return None
        return await self._transition_reason(task)

    async def _transition_reason(self, task: Task) -> str:
        """The words of the transition that put the task in its state, passed and not composed
        (ADR 0019 §2): the summary of its audit event; without one — a crash between the row and
        the audit —, the message of the trail's ``STATE_CHANGED`` with its operation."""
        for event in reversed(await self._audit.read(task_id=task.id)):
            if event.payload.get("new_state") == task.state.value:
                return event.summary
        for change in reversed(await self._repository.events(task.id)):
            if change.event_type is TaskEventType.STATE_CHANGED and change.new_state is task.state:
                operation = str(change.metadata.get("operation", ""))
                return f"{operation}: {change.message}" if change.message else operation
        return task.state.value

    # ----------------------------------------------------------------------------------
    # A step that was handed to a node (M12.2, ADR 0038 §10)
    # ----------------------------------------------------------------------------------

    async def _stand(self, task_id: TaskId, step_id: StepId, graph: GraphState) -> Stand:
        """Where the work of a RUNNING step stands now; nothing at all for a PENDING one.

        A step with an assignment is **not** confirmed with ``confirm``, which judges the node by
        the availability derived from its heartbeat: a node rendering for ten minutes without
        reporting would read as unreachable, the run would return ``WAITING_DEVICE`` and the task
        would go back to QUEUED **with live work in somebody's hands**. For D6 the instant a node
        is gone is the expiry of the assignment, not a belief about the node — so the assignment is
        read rather than the node judged (ADR 0038 §10).
        """
        if graph.states[step_id] is not StepState.RUNNING:
            return Stand(Standing.NONE, None)
        return await self._assignments.standing(task_id, step_id)

    async def _left_behind(
        self, task_id: TaskId, step_id: StepId, stand: Stand
    ) -> Execution | None:
        """What to do with work that expired or was delivered (dec. F): release it, or close it.

        ``None`` when the expiry released the step: nothing can have acted, the step is PENDING
        again, and the loop places it — which is the ordinary branch reached again, not a new one.
        Otherwise the store holds a STARTED record or an outcome, and ``Executor.finish`` closes the
        step from the first write that is missing. The service never calls the executor; this is
        where the two meet (ADR 0038 §6).
        """
        assert stand.assignment is not None
        if (
            stand.standing is Standing.LAPSED
            and await self._assignments.lapse(stand.assignment) is Lapse.RELEASED
        ):
            return None
        return await self._executor.finish(task_id, step_id)

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
    ) -> PlacementDecision:
        """The decision ``step_id`` runs under; it names no node when none is eligible (§4).

        A PENDING step is placed; a RUNNING one is **not placed again** — its node is read back
        from the audit, because a step that was started has already been given a node and asking
        a second time could name another one while a tool ran on the first.

        **Before either, a heartbeat of ``local``** (M13.3, ADR 0048 §2): this process is about to
        choose where a step runs, and ``local`` is this process. Without it a local step longer than
        the heartbeat's TTL left ``local`` expired for the step after it, in the same walk; and the
        power source a placement weighs is read here, at this instant, and not remembered from a
        beat twenty seconds old — a periodic belief never decides an action (ADR 0029 §7).

        Reading it back is not the same as trusting it (ADR 0026 §4). The id comes out of an
        audit event, and ``confirm`` turns it into a decision only if that node is *still*
        eligible: it judges, it does not choose, so it writes no second ``DEVICE_SELECTED``. A
        node that has gone means the run waits — the answer ADR 0017 §6 already gives — instead
        of resuming somewhere nobody would place it now.
        """
        step = graph.graph.step(step_id)
        await self._beat.beat()
        if graph.states[step_id] is StepState.RUNNING:
            return await self._orchestrator.confirm(
                await self._started_on(task_id, step_id),
                step,
                task_id=task_id,
                max_privacy=max_privacy,
            )
        return await self._orchestrator.place(step, task_id=task_id, max_privacy=max_privacy)

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

        A step run by a tool that cannot be repeated has **two** stored rows: the ``STARTED``
        record written before the call and the outcome that settles it (ADR 0021 §1). Only the
        outcome closes a task — a record of an intention is not a result — so the STARTED rows
        are dropped before counting, and "missing or ambiguous" keeps meaning what it meant.
        """
        last = graph.graph.order[-1]
        stored = [
            result
            for result in await self._results.for_step(task_id, last)
            if result.status is not ExecutionStatus.STARTED
        ]
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
