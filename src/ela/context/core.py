"""The Context Core: compose the answer to §44, and name what cannot be answered (ADR 0032).

Three things this module is not, and each one is a decision rather than an omission:

* **It is not a service that answers questions.** §44's operating principle — *do not ask what
  ELA can reasonably obtain by itself* — needs to know **which** questions get asked, and today
  nobody asks any. So this composes a value; the query interface is born with whoever asks
  (§13's Planner, §45's Decision Engine).
* **It is not memory.** The test is ADR 0032 §4: *if the fact can be recomputed it is context; if
  losing it loses information it is memory.* Nothing here is stored, so there is no importance,
  no confidence, no expiry and no privacy level — the four fields of §21 govern something that is
  kept, and this keeps nothing.
* **It does not act.** Architecture rule 38: *if answering a context question requires a
  capability, that answer is not context — it is an action*, and it goes through the Executor.
  Which is why the perception view arrives as an **argument**: taking it by calling ``tick``
  would spawn a helper, and a composer that spawns something causes something.

What it adds over four routes a caller could join by hand — the reason it exists at all — is one
instant instead of four, an age on every fact, the deadlines nobody else answers, and the
absences of §44 named out loud.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from ela.context.settings import ContextSettings
from ela.devices import DeviceRegistry
from ela.domain import (
    QUESTION_SOURCES,
    SOURCE_FIELDS,
    Approval,
    ContextActivity,
    ContextApproval,
    ContextDeadline,
    ContextDeadlines,
    ContextDevice,
    ContextEvent,
    ContextQuestion,
    ContextQuestionStatus,
    ContextRecent,
    ContextSnapshot,
    ContextSource,
    ContextTask,
    ContextWork,
    Device,
    DeviceId,
    Observation,
    StepId,
    Task,
    TaskEvent,
    TaskEventType,
    TaskState,
)
from ela.perception import PerceptionView
from ela.ports import ApprovalStore, Clock, NotFoundError, TaskRepository

__all__ = ["ContextCore", "held", "questions", "snapshot_fields"]


def snapshot_fields() -> frozenset[str]:
    """The fields :class:`~ela.domain.ContextSnapshot` actually has, right now."""
    return frozenset(ContextSnapshot.model_fields)


def held(
    sources: Iterable[ContextSource], fields: frozenset[str]
) -> tuple[tuple[ContextSource, ...], tuple[ContextSource, ...]]:
    """Split ``sources`` into the ones ``fields`` carries and the ones it does not.

    A pure function of two arguments, and deliberately so: the whole mechanism of ADR 0032 §3
    rests on it, so every one of its outcomes is exercised instead of waited for — including the
    one that matters, *a source whose field arrives stops being missing*, which is asserted by
    calling this with the field added rather than by trusting a comment.

    The direction is the fail-safe one: a source whose declared field is absent is **missing**,
    never quietly counted as answered. There is no second list anywhere; the absences of a
    snapshot are computed here or they do not exist.
    """
    answered: list[ContextSource] = []
    missing: list[ContextSource] = []
    for source in sources:
        (answered if SOURCE_FIELDS[source] in fields else missing).append(source)
    return tuple(answered), tuple(missing)


def questions(fields: frozenset[str]) -> tuple[ContextQuestionStatus, ...]:
    """All seven questions of §44 — including the ones this ELA cannot answer.

    Order is §44's, because the enum's order is §44's and ``tests/docs/test_spec_context.py``
    holds it to that.
    """
    answers: list[ContextQuestionStatus] = []
    for question in ContextQuestion:
        answered, missing = held(QUESTION_SOURCES[question], fields)
        answers.append(
            ContextQuestionStatus(question=question, answered_by=answered, missing=missing)
        )
    return tuple(answers)


def _activity(observation: Observation) -> ContextActivity:
    """The observation, narrowed to what §44's first line asks — state, never content."""
    return ContextActivity(
        observed_at=observation.observed_at,
        microphone=observation.microphone,
        camera=observation.camera,
        permissions=observation.permissions,
        display_count=observation.display_count,
        display_asleep=observation.display_asleep,
        screen_locked=observation.screen_locked,
        on_console=observation.on_console,
        idle_seconds=observation.idle_seconds,
        running_bundle_ids=observation.running_bundle_ids,
        frontmost_bundle_id=observation.frontmost_bundle_id,
        window_count=observation.window_count,
    )


def _device(device: Device, *, available: bool, local_id: DeviceId) -> ContextDevice:
    """One node as the snapshot carries it.

    ``available`` is passed in because it is the registry's answer and not a field anybody may
    read: deriving availability is ``ela.devices``' business (architecture rule 20).
    """
    return ContextDevice(
        device_id=device.id,
        name=device.name,
        os=device.os,
        available=available,
        status=device.status,
        is_local=device.id == local_id,
        last_seen_at=device.last_seen_at,
    )


def _approval(approval: Approval) -> ContextApproval:
    return ContextApproval(
        approval_id=approval.id,
        task_id=approval.task_id,
        capability_id=approval.capability_id,
        expires_at=approval.expires_at,
    )


def _deadline(task: Task) -> ContextDeadline:
    # ``due`` never returns a task without a deadline, so this narrowing is the contract of the
    # port and not a check that could fail quietly.
    assert task.deadline is not None
    return ContextDeadline(
        task_id=task.id, goal=task.goal, state=task.state, deadline=task.deadline
    )


def _started_step(trail: Sequence[TaskEvent]) -> StepId | None:
    """The step of the last ``STEP_STARTED`` that no later event of that step closed."""
    started: StepId | None = None
    for event in trail:
        if event.step_id is None:
            continue
        if event.event_type is TaskEventType.STEP_STARTED:
            started = event.step_id
        elif event.step_id == started:
            started = None
    return started


def _event(event: TaskEvent) -> ContextEvent:
    return ContextEvent(
        task_id=event.task_id,
        event_type=event.event_type,
        at=event.created_at,
        previous_state=event.previous_state,
        new_state=event.new_state,
    )


class ContextCore:
    """Composes a :class:`~ela.domain.ContextSnapshot` from what ELA already holds.

    ``live_states`` is given rather than derived, and that is the point: which states are still
    alive is the state machine's knowledge (ADR 0004), the composer is not allowed to import it
    (import-linter contract 7), and inventing a second copy of the list here is how two lists
    drift apart. It arrives from the composition root as data — the shape of ADR 0026.
    """

    def __init__(
        self,
        *,
        repository: TaskRepository,
        approvals: ApprovalStore,
        devices: DeviceRegistry,
        clock: Clock,
        settings: ContextSettings,
        live_states: frozenset[TaskState],
        local_device_id: DeviceId,
    ) -> None:
        self._repository = repository
        self._approvals = approvals
        self._devices = devices
        self._clock = clock
        self._settings = settings
        self._live = live_states
        self._local_device_id = local_device_id

    async def assemble(self, view: PerceptionView) -> ContextSnapshot:
        """The snapshot of now: reads, and never writes, executes or observes by itself.

        The perception view is an argument and not something taken by calling ``tick``: see the
        module docstring. Everything else is a read through a port, and every list that a limit
        can cut carries how much of how much it is showing (ADR 0032 §9-bis).
        """
        at = self._clock.now()
        live = self._live

        counted = await self._repository.count(states=live)
        tasks = await self._repository.tasks(states=live, limit=self._settings.context_tasks_limit)
        pending = await self._approvals.pending(now=at)
        due = await self._repository.due(states=live, limit=self._settings.context_deadlines_limit)
        due_total = await self._repository.due_count(states=live)

        # One read of the trail per task, used by both the step under way and the recent events:
        # measured, the second read was half the cost of the whole snapshot (ADR 0032 §9-bis).
        trails = {task.id: await self._repository.events(task.id) for task in tasks}

        return ContextSnapshot(
            at=at,
            activity=_activity(view.observation),
            device=await self._local_device(),
            work=ContextWork(
                tasks=tuple([await self._task(task, trails[task.id]) for task in tasks]),
                shown=len(tasks),
                total=sum(counted.values()),
                states=dict(counted),
                pending_approvals=tuple(_approval(approval) for approval in pending),
            ),
            deadlines=ContextDeadlines(
                deadlines=tuple(_deadline(task) for task in due),
                shown=len(due),
                total=due_total,
            ),
            recent=ContextRecent(
                since=view.since,
                changes=tuple(view.changes),
                events=self._events(trails.values()),
            ),
            questions=questions(snapshot_fields()),
        )

    async def _local_device(self) -> ContextDevice | None:
        """The node ELA runs on, or ``None`` when the registry does not hold it.

        ``None`` is a composition ELA can really be in — a registry that has not been seeded —
        and it is visible rather than papered over with a fabricated row, which would be a fact
        about the world that nobody observed (ADR 0028 §3).

        Two reads and not one: the registry is asked which nodes it has and which of them are
        available, because availability is derived and only the registry may derive it
        (architecture rule 20). It is the shape ``/diagnostics`` already uses.
        """
        local = next(
            (
                device
                for device in await self._devices.devices()
                if device.id == self._local_device_id
            ),
            None,
        )
        if local is None:
            return None
        reachable = {device.id for device in await self._devices.available()}
        return _device(local, available=local.id in reachable, local_id=self._local_device_id)

    async def _task(self, task: Task, trail: Sequence[TaskEvent]) -> ContextTask:
        """One live task, with the step under way if its trail says one is.

        The plan is fetched **only** for a task that has actually started a step: a task waiting
        in QUEUED has nothing under way, so asking for its plan would be one query per task for
        an answer that is always empty.
        """
        step_id = _started_step(trail)
        return ContextTask(
            task_id=task.id,
            goal=task.goal,
            state=task.state,
            deadline=task.deadline,
            current_step_id=step_id,
            current_step_goal=None if step_id is None else await self._step_goal(task, step_id),
        )

    async def _step_goal(self, task: Task, step_id: StepId) -> str | None:
        """What the running step is for, named by the plan; ``None`` if the plan cannot say."""
        try:
            plan = await self._repository.plan(task.id)
        except NotFoundError:
            return None
        for step in plan.steps:
            if step.id == step_id:
                return step.goal
        return None

    def _events(self, trails: Iterable[Sequence[TaskEvent]]) -> tuple[ContextEvent, ...]:
        """The most recent events of the tasks being shown, newest first.

        Task events and never audit events: the audit is the trail of what **ELA decided** (§32),
        and reading it back into a composed picture is a second use of the log that deserves its
        own decision. Rule 39 makes that structural rather than a habit.
        """
        collected = [event for trail in trails for event in trail]
        collected.sort(key=lambda event: event.created_at, reverse=True)
        return tuple(_event(event) for event in collected[: self._settings.context_events_limit])
