"""The composer: one instant, one read per fact, and nothing caused (M10.4, ADR 0032).

Three properties carry the milestone and each is asserted rather than described: the snapshot has
**one** ``at`` and every age is relative to it; a truncated list says how many of how many; and
``assemble`` neither ticks, nor writes, nor names anything that costs a capability.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from ela.context import ContextCore
from ela.devices.local import LOCAL_DEVICE_ID, local_device
from ela.domain import (
    Approval,
    ApprovalId,
    ApprovalStatus,
    CapabilityId,
    ContextSnapshot,
    Device,
    DeviceAvailability,
    DeviceId,
    DeviceStatus,
    OperatingSystem,
    PlanId,
    PrivacyLevel,
    RiskLevel,
    StepId,
    Task,
    TaskEvent,
    TaskEventId,
    TaskEventType,
    TaskId,
    TaskPlan,
    TaskState,
    TaskStep,
)
from ela.perception import PerceptionView
from ela.testing.fakes import FakeApprovalStore, FakeDeviceRegistry, FakeTaskRepository
from tests.unit.context.conftest import EARLIER, NOW


def task(
    index: int,
    *,
    state: TaskState = TaskState.QUEUED,
    deadline: object = None,
    goal: str = "leggere la posta",
) -> Task:
    return Task(
        id=TaskId(UUID(f"00000000-0000-4000-8000-00000000030{index}")),
        created_at=NOW - timedelta(minutes=index),
        goal=goal,
        state=state,
        deadline=deadline,  # type: ignore[arg-type]
    )


def step(goal: str = "aprire Mail") -> TaskStep:
    return TaskStep(
        id=StepId(uuid4()),
        created_at=NOW,
        goal=goal,
        risk=RiskLevel.LOW,
        expected_result="aperto",
        requires_authorization=False,
    )


def event(
    task_id: TaskId,
    kind: TaskEventType,
    *,
    step_id: StepId | None = None,
    at: object = None,
) -> TaskEvent:
    return TaskEvent(
        id=TaskEventId(uuid4()),
        created_at=at or NOW,  # type: ignore[arg-type]
        task_id=task_id,
        event_type=kind,
        step_id=step_id,
    )


# ----------------------------------------------------------------------------------------
# One instant, and the one age that differs from it
# ----------------------------------------------------------------------------------------


async def test_the_snapshot_has_one_instant(core: ContextCore, view: PerceptionView) -> None:
    snapshot = await core.assemble(view)

    assert snapshot.at == NOW
    assert snapshot.activity.observed_at == view.observation.observed_at


async def test_the_observation_may_be_older_than_the_snapshot(
    core: ContextCore, view: PerceptionView
) -> None:
    """The cadence's doing: a family inside its interval answers with what it last saw."""
    stale = view.observation.model_copy(update={"observed_at": NOW - timedelta(seconds=25)})

    snapshot = await core.assemble(PerceptionView(stale, view.changes, view.since))

    assert snapshot.activity.observed_at < snapshot.at


async def test_recent_says_how_far_back_it_can_see(core: ContextCore, view: PerceptionView) -> None:
    """``since`` is the horizon, and without it "nothing changed" has two meanings (ADR 0030 §8)."""
    snapshot = await core.assemble(view)

    assert snapshot.recent.since == EARLIER
    assert snapshot.recent.changes == view.changes


async def test_the_first_belief_has_a_horizon_of_zero_and_no_changes(
    core: ContextCore, view: PerceptionView
) -> None:
    """A true answer, not a missing one: ELA has only just started looking."""
    first = PerceptionView(view.observation, (), view.observation.observed_at)

    snapshot = await core.assemble(first)

    assert snapshot.recent.since == snapshot.activity.observed_at
    assert snapshot.recent.changes == ()


# ----------------------------------------------------------------------------------------
# The composer causes nothing
# ----------------------------------------------------------------------------------------


async def test_the_perception_view_is_an_argument_and_nothing_is_observed(
    core: ContextCore, view: PerceptionView
) -> None:
    """``assemble`` takes the view; whoever decided to look is whoever looked (ADR 0032 §8)."""
    snapshot = await core.assemble(view)

    assert snapshot.activity.microphone == view.observation.microphone
    assert snapshot.activity.camera.cause == view.observation.camera.cause


async def test_assembling_writes_nothing(
    core: ContextCore, repository: FakeTaskRepository, view: PerceptionView
) -> None:
    await repository.add(task(1))
    before = await repository.tasks()

    await core.assemble(view)

    assert await repository.tasks() == before


# ----------------------------------------------------------------------------------------
# What is under way
# ----------------------------------------------------------------------------------------


async def test_the_live_tasks_carry_their_goal_and_state(
    core: ContextCore, repository: FakeTaskRepository, view: PerceptionView
) -> None:
    """``goal`` is the user's words, and it is here by decision (ADR 0032 §5)."""
    await repository.add(task(1, goal="preparare la riunione"))

    snapshot = await core.assemble(view)

    assert [(one.goal, one.state) for one in snapshot.work.tasks] == [
        ("preparare la riunione", TaskState.QUEUED)
    ]


async def test_a_finished_task_is_not_under_way(
    core: ContextCore, repository: FakeTaskRepository, view: PerceptionView
) -> None:
    await repository.add(task(1, state=TaskState.COMPLETED))

    snapshot = await core.assemble(view)

    assert snapshot.work.tasks == ()
    assert snapshot.work.total == 0


async def test_the_step_under_way_is_named_by_the_plan(
    core: ContextCore, repository: FakeTaskRepository, view: PerceptionView
) -> None:
    one = task(1, state=TaskState.EXECUTING)
    running = step("aprire Mail")
    await repository.add(one)
    await repository.add_plan(
        TaskPlan(
            id=PlanId(uuid4()), created_at=NOW, task_id=one.id, goal=one.goal, steps=(running,)
        )
    )
    await repository.append_event(event(one.id, TaskEventType.STEP_STARTED, step_id=running.id))

    snapshot = await core.assemble(view)

    assert snapshot.work.tasks[0].current_step_id == running.id
    assert snapshot.work.tasks[0].current_step_goal == "aprire Mail"


async def test_a_step_that_finished_is_no_longer_under_way(
    core: ContextCore, repository: FakeTaskRepository, view: PerceptionView
) -> None:
    one = task(1, state=TaskState.EXECUTING)
    running = step()
    await repository.add(one)
    await repository.append_event(event(one.id, TaskEventType.STEP_STARTED, step_id=running.id))
    await repository.append_event(event(one.id, TaskEventType.STEP_COMPLETED, step_id=running.id))

    snapshot = await core.assemble(view)

    assert snapshot.work.tasks[0].current_step_id is None
    assert snapshot.work.tasks[0].current_step_goal is None


async def test_a_started_step_with_no_plan_still_says_which_step(
    core: ContextCore, repository: FakeTaskRepository, view: PerceptionView
) -> None:
    """The step is a fact from the trail; the goal is the plan's, and the plan may not be there."""
    one = task(1, state=TaskState.EXECUTING)
    running = step()
    await repository.add(one)
    await repository.append_event(event(one.id, TaskEventType.STEP_STARTED, step_id=running.id))

    snapshot = await core.assemble(view)

    assert snapshot.work.tasks[0].current_step_id == running.id
    assert snapshot.work.tasks[0].current_step_goal is None


async def test_a_plan_that_does_not_hold_the_step_names_no_goal(
    core: ContextCore, repository: FakeTaskRepository, view: PerceptionView
) -> None:
    one = task(1, state=TaskState.EXECUTING)
    running, other = step(), step("altro")
    await repository.add(one)
    await repository.add_plan(
        TaskPlan(id=PlanId(uuid4()), created_at=NOW, task_id=one.id, goal=one.goal, steps=(other,))
    )
    await repository.append_event(event(one.id, TaskEventType.STEP_STARTED, step_id=running.id))

    snapshot = await core.assemble(view)

    assert snapshot.work.tasks[0].current_step_goal is None


async def test_an_event_about_another_step_does_not_close_the_running_one(
    core: ContextCore, repository: FakeTaskRepository, view: PerceptionView
) -> None:
    """A plan of two steps: one finishing does not mean the other stopped."""
    one = task(1, state=TaskState.EXECUTING)
    running, other = step("aprire Mail"), step("altro")
    await repository.add(one)
    await repository.add_plan(
        TaskPlan(
            id=PlanId(uuid4()),
            created_at=NOW,
            task_id=one.id,
            goal=one.goal,
            steps=(running, other),
        )
    )
    await repository.append_event(event(one.id, TaskEventType.STEP_STARTED, step_id=running.id))
    await repository.append_event(event(one.id, TaskEventType.STEP_COMPLETED, step_id=other.id))

    snapshot = await core.assemble(view)

    assert snapshot.work.tasks[0].current_step_id == running.id
    assert snapshot.work.tasks[0].current_step_goal == "aprire Mail"


async def test_an_event_without_a_step_is_not_a_step_under_way(
    core: ContextCore, repository: FakeTaskRepository, view: PerceptionView
) -> None:
    one = task(1, state=TaskState.EXECUTING)
    await repository.add(one)
    await repository.append_event(event(one.id, TaskEventType.STATE_CHANGED))

    snapshot = await core.assemble(view)

    assert snapshot.work.tasks[0].current_step_id is None


async def test_the_pending_approvals_are_carried_without_their_prompt(
    core: ContextCore,
    repository: FakeTaskRepository,
    approvals: FakeApprovalStore,
    view: PerceptionView,
) -> None:
    """A ``purpose`` is shown where the capability declares it, for the question it declares it
    for (ADR 0029 §6). A composed picture is not that question."""
    one = task(1)
    await repository.add(one)
    await approvals.add(
        Approval(
            id=ApprovalId(uuid4()),
            created_at=NOW,
            task_id=one.id,
            step_id=StepId(uuid4()),
            capability_id=CapabilityId("perception.capture_screen"),
            prompt="Catturare lo schermo per: leggere l'errore",
            status=ApprovalStatus.PENDING,
            expires_at=NOW + timedelta(minutes=30),
        )
    )

    snapshot = await core.assemble(view)

    (carried,) = snapshot.work.pending_approvals
    assert carried.capability_id == "perception.capture_screen"
    assert "prompt" not in type(carried).model_fields


# ----------------------------------------------------------------------------------------
# The limit bites out loud (ADR 0032 §9-bis)
# ----------------------------------------------------------------------------------------


async def test_a_truncated_list_says_how_many_of_how_many(
    core: ContextCore, repository: FakeTaskRepository, view: PerceptionView
) -> None:
    """ "There are no more" and "I am not showing you the rest" must not have the same face."""
    for index in range(5):
        await repository.add(task(index))

    snapshot = await core.assemble(view)

    assert snapshot.work.shown == 2
    assert snapshot.work.total == 5
    assert len(snapshot.work.tasks) == 2


async def test_an_untruncated_list_shows_all_of_them(
    core: ContextCore, repository: FakeTaskRepository, view: PerceptionView
) -> None:
    await repository.add(task(1))

    snapshot = await core.assemble(view)

    assert snapshot.work.shown == snapshot.work.total == 1


async def test_the_total_counts_what_the_limit_hides(
    core: ContextCore, repository: FakeTaskRepository, view: PerceptionView
) -> None:
    """``total`` comes from ``count``, so it does not grow with what is loaded."""
    for index in range(4):
        await repository.add(task(index, deadline=NOW + timedelta(hours=index)))

    snapshot = await core.assemble(view)

    assert snapshot.deadlines.shown == 2
    assert snapshot.deadlines.total == 4
    assert snapshot.work.states == {TaskState.QUEUED: 4}


async def test_the_deadlines_are_the_soonest_and_carry_no_verdict(
    core: ContextCore, repository: FakeTaskRepository, view: PerceptionView
) -> None:
    """No ``overdue``: a comparison with ``at`` is the reader's, and a threshold is a decision."""
    late = task(1, deadline=NOW + timedelta(days=2))
    soon = task(2, deadline=NOW - timedelta(hours=1))
    await repository.add(late)
    await repository.add(soon)
    await repository.add(task(3))

    snapshot = await core.assemble(view)

    assert [one.task_id for one in snapshot.deadlines.deadlines] == [soon.id, late.id]
    assert "overdue" not in type(snapshot.deadlines.deadlines[0]).model_fields


async def test_the_recent_events_are_the_newest_and_are_capped(
    core: ContextCore, repository: FakeTaskRepository, view: PerceptionView
) -> None:
    one = task(1)
    await repository.add(one)
    for index in range(5):
        await repository.append_event(
            event(one.id, TaskEventType.STATE_CHANGED, at=NOW - timedelta(seconds=index))
        )

    snapshot = await core.assemble(view)

    assert len(snapshot.recent.events) == 3
    assert [one.at for one in snapshot.recent.events] == sorted(
        (one.at for one in snapshot.recent.events), reverse=True
    )
    assert snapshot.recent.events[0].at == NOW


async def test_the_events_come_only_from_the_tasks_being_shown(
    core: ContextCore, repository: FakeTaskRepository, view: PerceptionView
) -> None:
    """A trail that is not read is not a trail that is hidden: it belongs to a task outside the
    limit, and the limit is what the section declares."""
    for index in range(3):
        one = task(index)
        await repository.add(one)
        await repository.append_event(event(one.id, TaskEventType.STATE_CHANGED))

    snapshot = await core.assemble(view)

    shown = {one.task_id for one in snapshot.work.tasks}
    assert {one.task_id for one in snapshot.recent.events} == shown


# ----------------------------------------------------------------------------------------
# The node
# ----------------------------------------------------------------------------------------


async def test_the_local_node_is_the_one_ela_runs_on(
    core: ContextCore, registry: FakeDeviceRegistry, view: PerceptionView
) -> None:
    await registry.register(local_device(NOW).model_copy(update={"last_seen_at": NOW}))

    snapshot = await core.assemble(view)

    assert snapshot.device is not None
    assert snapshot.device.device_id == LOCAL_DEVICE_ID
    assert snapshot.device.is_local


async def test_availability_is_the_registrys_answer_and_not_a_field(
    core: ContextCore, registry: FakeDeviceRegistry, view: PerceptionView
) -> None:
    """Architecture rule 20: a heartbeat older than the TTL makes a node unavailable, and only
    the registry may say so — the composer asks and never reads the column."""
    await registry.register(
        local_device(NOW).model_copy(update={"last_seen_at": NOW - timedelta(hours=1)})
    )

    snapshot = await core.assemble(view)

    assert snapshot.device is not None
    assert snapshot.device.available is False


async def test_a_registry_without_the_local_node_says_so(
    core: ContextCore, view: PerceptionView
) -> None:
    """A composition ELA can really be in, visible instead of papered over with a made-up row."""
    snapshot = await core.assemble(view)

    assert snapshot.device is None


async def test_another_node_is_not_mistaken_for_the_local_one(
    core: ContextCore, registry: FakeDeviceRegistry, view: PerceptionView
) -> None:
    await registry.register(
        Device(
            id=DeviceId(uuid4()),
            created_at=NOW,
            name="windows",
            os=OperatingSystem.WINDOWS,
            availability=DeviceAvailability.ONLINE,
            status=DeviceStatus.IDLE,
            privacy=PrivacyLevel.LOCAL_ONLY,
            last_seen_at=NOW,
        )
    )

    snapshot = await core.assemble(view)

    assert snapshot.device is None


# ----------------------------------------------------------------------------------------
# What a snapshot never carries
# ----------------------------------------------------------------------------------------


def test_the_snapshot_carries_no_capture_no_text_no_arguments_no_output() -> None:
    """Asserted on the models, not on one instance: an empty value proves nothing."""
    seen: set[str] = set()
    pending: list[type] = [ContextSnapshot]
    fields: set[str] = set()
    while pending:
        model = pending.pop()
        if model.__name__ in seen:
            continue
        seen.add(model.__name__)
        for name, field in model.model_fields.items():
            fields.add(name)
            for candidate in (field.annotation, *getattr(field.annotation, "__args__", ())):
                if hasattr(candidate, "model_fields"):
                    pending.append(candidate)

    for forbidden in ("text", "lines", "capture_id", "arguments", "output", "prompt", "title"):
        assert forbidden not in fields, forbidden


def test_the_only_user_content_is_the_goal(core: ContextCore) -> None:
    """One thing the user dictated, in two places, and nothing else (ADR 0032 §5)."""
    from ela.domain import ContextDeadline, ContextTask

    assert "goal" in ContextTask.model_fields
    assert "goal" in ContextDeadline.model_fields
    assert "current_step_goal" in ContextTask.model_fields


def test_a_section_cannot_claim_to_show_what_it_does_not_carry() -> None:
    """The validator is the reason ``shown`` is a fact rather than a convention."""
    from ela.domain import ContextDeadlines

    with pytest.raises(ValueError, match="shown must be"):
        ContextDeadlines(deadlines=(), shown=1, total=1)


def test_a_section_cannot_show_more_than_there_is() -> None:
    """``total`` below ``shown`` would be a truncation that hid the wrong direction."""
    from ela.domain import ContextDeadline, ContextDeadlines

    row = ContextDeadline(task_id=TaskId(uuid4()), goal="x", state=TaskState.QUEUED, deadline=NOW)
    with pytest.raises(ValueError, match="total cannot be smaller"):
        ContextDeadlines(deadlines=(row,), shown=1, total=0)


def test_the_work_section_is_held_to_the_same_two_rules() -> None:
    from ela.domain import ContextTask, ContextWork

    row = ContextTask(task_id=TaskId(uuid4()), goal="x", state=TaskState.QUEUED)
    with pytest.raises(ValueError, match="shown must be"):
        ContextWork(tasks=(), shown=1, total=1)
    with pytest.raises(ValueError, match="total cannot be smaller"):
        ContextWork(tasks=(row,), shown=1, total=0)
