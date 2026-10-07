"""The Planner, end to end on the pipeline: a child task that asks, a yes, one call, a plan.

M14.2, ADR 0058. The call that writes a plan is a ``model.complete`` step of a task of its own,
the **child** of the task to plan (decision A, decision 1 of the review): it asks with its worst
case, the yes mints a grant of one use, the cap reserves, the tool calls, the verifier verifies —
the road of every call. What the model wrote is read strictly, validated, and attached to the parent
through the door of a plan written by hand; the parent is ``QUEUED`` and **nobody runs it**
(decision H). Every way the planning ends is one row of the table of proposal 1.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ela.domain import (
    AuditEventType,
    ErrorMetadata,
    ExecutionStatus,
    PlanAuthorKind,
    TaskId,
    TaskState,
)
from ela.executive.planner import (
    PLANNER_CALL_FAILED,
    PLANNER_NO_PLAN,
    PLANNER_TRUNCATED,
    PLANNER_UNANSWERED,
    PLANNER_UNVERIFIABLE,
    PlanningError,
    PlanningOutcome,
    planning_id,
)
from ela.permissions.capabilities import CORE_ECHO
from tests.executive.planning import (
    ECHO_STEP,
    NO_PLAN,
    NO_PLAN_REASON,
    NOTE_STEP,
    Planned,
    plan_of,
    step,
)

S = TaskState
E = AuditEventType


@pytest.fixture
def world(tmp_path: Path) -> Planned:
    return Planned(tmp_path / "workspace")


async def reason_of(world: Planned, task_id: TaskId) -> str:
    return (await world.runner.answer(task_id)).reason or ""


# ----------------------------------------------------------------------------------------
# Asking: a child that asks, and nothing that leaves before the yes
# ----------------------------------------------------------------------------------------


async def test_asking_creates_the_child_and_stops_at_its_question(world: Planned) -> None:
    task = await world.task()

    asked = await world.planner.plan(task.id)

    assert asked.outcome is PlanningOutcome.WAITING_APPROVAL
    assert asked.task.state is S.PLANNING
    child = asked.planning_task
    assert child is not None
    assert child.id == planning_id(task.id)
    assert child.parent_id == task.id
    assert child.state is S.WAITING_APPROVAL
    assert asked.approval is not None
    assert asked.approval.task_id == child.id
    assert asked.approval.capability_id == "model.complete"
    assert world.model.requests == (), "nothing leaves before the yes"


async def test_the_child_s_plan_is_one_model_complete_step_written_by_the_planner(
    world: Planned,
) -> None:
    task = await world.task()
    await world.planner.plan(task.id)

    plan = await world.repository.plan(planning_id(task.id))

    assert plan.author.by is PlanAuthorKind.PLANNER
    assert (plan.author.result_id, plan.author.model) == (None, None)
    (only,) = plan.steps
    spec = world.registry.get(only.required_capabilities[0])
    assert only.required_capabilities == ("model.complete",)
    assert (only.risk, only.requires_authorization) == (spec.risk, spec.requires_authorization)
    assert only.success_conditions == ("model.answered", "model.routed_as_asked")


async def test_the_question_names_the_task_its_goal_and_what_leaves(world: Planned) -> None:
    """Decision 2: the goal of the child's step, which the three surfaces already show."""
    task = await world.task()

    asked = await world.planner.plan(task.id)

    assert asked.approval is not None
    goal = asked.approval.metadata["asked"]["goal"]  # type: ignore[index]
    assert str(task.id) in goal
    assert task.goal in goal
    assert "the goal, the Planner's instructions and the catalogue of 3 capabilities" in goal
    assert "no scope, no device, no context" in goal
    assert "worst_case" in asked.approval.metadata["asked"]  # type: ignore[operator]


async def test_asking_again_before_the_yes_asks_nothing_more(world: Planned) -> None:
    task = await world.task()
    first = await world.planner.plan(task.id)

    again = await world.planner.plan(task.id)

    assert again.outcome is PlanningOutcome.WAITING_APPROVAL
    assert again.approval == first.approval
    assert world.model.requests == ()


# ----------------------------------------------------------------------------------------
# The yes, the call, the plan
# ----------------------------------------------------------------------------------------


async def test_after_the_yes_one_call_writes_the_plan_and_the_task_is_queued(
    world: Planned,
) -> None:
    task_id, planned = await world.planned()

    assert planned.outcome is PlanningOutcome.PLANNED
    assert planned.task.state is S.QUEUED
    assert planned.planning_task is not None and planned.planning_task.state is S.COMPLETED
    assert len(world.model.requests) == 1, "one call"
    plan = await world.repository.plan(task_id)
    assert plan.author.by is PlanAuthorKind.MODEL
    assert plan.author.model == "fake-model"
    result = await world.results.get(plan.author.result_id)  # type: ignore[arg-type]
    assert result.task_id == planning_id(task_id)
    assert result.status is ExecutionStatus.SUCCEEDED
    assert [one.required_capabilities for one in plan.steps] == [
        ("core.echo",),
        ("workspace.write_note",),
    ]


async def test_the_planner_writes_and_does_not_start(world: Planned) -> None:
    """Decision H: with a valid plan the task is QUEUED as after /plan; the run is the user's."""
    task_id, _ = await world.planned()

    types = [event.event_type for event in await world.audit.read(task_id=task_id)]
    assert AuditEventType.TASK_STARTED not in types
    assert types[-2:] == [AuditEventType.PLAN_CREATED, AuditEventType.TASK_QUEUED]
    assert (await world.repository.get(task_id)).state is S.QUEUED


async def test_the_plan_enters_by_the_door_of_a_plan_written_by_hand(world: Planned) -> None:
    task_id, _ = await world.planned()

    created = [e for e in await world.audit.read(task_id=task_id) if e.event_type is E.PLAN_CREATED]
    (one,) = created
    assert one.payload["operation"] == "plan"
    assert one.payload["author"]["by"] == "MODEL"  # type: ignore[index]
    assert one.payload["goal"] == (await world.repository.get(task_id)).goal
    queued = (await world.audit.read(task_id=task_id))[-1]
    assert queued.summary == "queue: PLANNING -> QUEUED (planned by ELA's Planner)"


async def test_the_plan_of_the_model_runs_like_any_other(world: Planned, tmp_path: Path) -> None:
    task_id, _ = await world.planned()

    run = await world.runner.run(task_id)

    assert run.task.state is S.COMPLETED
    note = tmp_path / "workspace" / NOTE_STEP["arguments"]["path"]
    assert note.read_text(encoding="utf-8") == NOTE_STEP["arguments"]["body"]


async def test_asking_again_after_the_plan_answers_the_plan_and_calls_nobody(
    world: Planned,
) -> None:
    task_id, planned = await world.planned()

    again = await world.planner.plan(task_id)

    assert again.outcome is PlanningOutcome.PLANNED
    assert again.task.plan_id == planned.task.plan_id
    assert len(world.model.requests) == 1


async def test_the_yes_and_a_run_of_the_child_plan_the_parent_through_settle(
    world: Planned,
) -> None:
    """The page's yes runs the child (``answered_and_resumed``); the route then settles."""
    task = await world.task()
    asked = await world.planner.plan(task.id)
    await world.yes(asked)
    await world.runner.run(planning_id(task.id))

    settled = await world.planner.settle(task.id)

    assert settled.outcome is PlanningOutcome.PLANNED
    assert settled.task.state is S.QUEUED


# ----------------------------------------------------------------------------------------
# The ends that are not a plan: the table of proposal 1, one row each
# ----------------------------------------------------------------------------------------


async def test_a_refused_plan_ends_the_task_failed_with_the_step_and_the_constraint(
    tmp_path: Path,
) -> None:
    world = Planned(
        tmp_path / "workspace",
        answer=plan_of(ECHO_STEP, step(NOTE_STEP, success_conditions=["made.up"])),
    )

    task_id, planned = await world.planned()

    assert planned.outcome is PlanningOutcome.FAILED
    assert planned.task.state is S.FAILED
    assert planned.planning_task is not None and planned.planning_task.state is S.COMPLETED
    assert planned.problems and planned.problems[0].startswith("step 2 of 2")
    assert (await reason_of(world, task_id)).startswith(
        f"fail: PLANNING -> FAILED ({PLANNER_UNVERIFIABLE}: step 2 of 2 (workspace.write_note): "
    )
    assert len(world.model.requests) == 1, "no second call, no repair (decision G)"
    assert (await world.repository.get(task_id)).plan_id is None


async def test_no_plan_ends_the_task_failed_and_the_model_s_words_stay_out_of_the_audit(
    tmp_path: Path,
) -> None:
    world = Planned(tmp_path / "workspace", answer=NO_PLAN)

    task_id, planned = await world.planned("Spegni la luce della cucina.")

    assert planned.outcome is PlanningOutcome.FAILED
    assert planned.no_plan == NO_PLAN_REASON
    reason = await reason_of(world, task_id)
    assert reason.startswith(f"fail: PLANNING -> FAILED ({PLANNER_NO_PLAN}: ")
    assert str(planning_id(task_id)) in reason
    every = " ".join(e.model_dump_json() for e in await world.audit.read())
    assert NO_PLAN_REASON not in every, "ADR 0021 §7: the text of an answer is in no AuditEvent"
    again = await world.planner.plan(task_id)
    assert again.no_plan == NO_PLAN_REASON, "read again from the private store"


async def test_the_user_s_no_denies_the_task_and_nothing_leaves(world: Planned) -> None:
    task = await world.task()
    asked = await world.planner.plan(task.id)
    await world.no(asked)

    settled = await world.planner.settle(task.id)

    assert settled.outcome is PlanningOutcome.DENIED
    assert settled.task.state is S.DENIED
    reason = await reason_of(world, task.id)
    assert reason.startswith(
        f"deny_by_planning: PLANNING -> DENIED (the planning task {planning_id(task.id)} was "
        "denied: deny_by_approval: "
    )
    assert "rejected by tommaso" in reason
    assert world.model.requests == ()


async def test_a_call_that_failed_ends_the_task_failed_with_the_child_s_reason(
    tmp_path: Path,
) -> None:
    error = ErrorMetadata(code="provider.server_error", message="overloaded", retryable=True)
    world = Planned(tmp_path / "workspace", error=error)

    task_id, planned = await world.planned()

    assert planned.outcome is PlanningOutcome.FAILED
    assert planned.planning_task is not None and planned.planning_task.state is S.FAILED
    reason = await reason_of(world, task_id)
    assert reason.startswith(f"fail: PLANNING -> FAILED ({PLANNER_CALL_FAILED}: the planning task ")
    assert "provider.server_error" in reason


async def test_an_answer_cut_at_max_tokens_is_a_refused_plan(tmp_path: Path) -> None:
    world = Planned(tmp_path / "workspace", finish_reason="max_tokens")

    task_id, planned = await world.planned()

    assert planned.outcome is PlanningOutcome.FAILED
    assert (await reason_of(world, task_id)).startswith(
        f"fail: PLANNING -> FAILED ({PLANNER_TRUNCATED}: "
    )


async def test_a_child_that_was_cancelled_cancels_the_parent(world: Planned) -> None:
    task = await world.task()
    await world.planner.plan(task.id)
    await world.engine.cancel(planning_id(task.id), reason="ferma")

    settled = await world.planner.settle(task.id)

    assert settled.outcome is PlanningOutcome.CANCELLED
    assert settled.task.state is S.CANCELLED
    assert "the planning task" in await reason_of(world, task.id)


async def test_a_child_whose_question_expired_fails_the_parent_unanswered(
    world: Planned,
) -> None:
    task = await world.task()
    asked = await world.planner.plan(task.id)
    assert asked.approval is not None and asked.approval.expires_at is not None
    world.clock.advance(asked.approval.expires_at - world.clock.now())
    await world.engine.recover()
    assert (await world.repository.get(planning_id(task.id))).state is S.EXPIRED

    settled = await world.planner.settle(task.id)

    assert settled.outcome is PlanningOutcome.FAILED
    assert (await reason_of(world, task.id)).startswith(
        f"fail: PLANNING -> FAILED ({PLANNER_UNANSWERED}: "
    )


async def test_cancelling_the_parent_stops_its_planning_child(world: Planned) -> None:
    task = await world.task()
    await world.planner.plan(task.id)

    await world.planner.stop_planning(task.id, reason="ferma")

    assert (await world.repository.get(planning_id(task.id))).state is S.CANCELLED


async def test_settling_twice_writes_the_end_once(world: Planned) -> None:
    task = await world.task()
    asked = await world.planner.plan(task.id)
    await world.no(asked)

    first = await world.planner.settle(task.id)
    again = await world.planner.settle(task.id)

    assert first.task == again.task
    denied = [e for e in await world.audit.read(task_id=task.id) if e.event_type is E.TASK_DENIED]
    assert len(denied) == 1


# ----------------------------------------------------------------------------------------
# At start-up (decision 13): the parents nobody closed
# ----------------------------------------------------------------------------------------


async def test_at_start_up_an_expired_child_closes_its_parent(world: Planned) -> None:
    task = await world.task()
    asked = await world.planner.plan(task.id)
    assert asked.approval is not None and asked.approval.expires_at is not None
    world.clock.advance(asked.approval.expires_at - world.clock.now())
    await world.engine.recover()

    settled = await world.planner.settle_all()

    assert [one.task.id for one in settled] == [task.id]
    assert (await world.repository.get(task.id)).state is S.FAILED


async def test_at_start_up_a_completed_child_settle_never_reached_plans_its_parent(
    world: Planned,
) -> None:
    """A crash between the end of the child and ``settle``: the child is COMPLETED, the parent
    still PLANNING. The start-up finds it with a read of the repository, not a list."""
    task = await world.task()
    asked = await world.planner.plan(task.id)
    await world.yes(asked)
    await world.runner.run(planning_id(task.id))
    assert (await world.repository.get(task.id)).state is S.PLANNING

    settled = await world.planner.settle_all()

    assert [one.outcome for one in settled] == [PlanningOutcome.PLANNED]
    assert (await world.repository.get(task.id)).state is S.QUEUED


async def test_at_start_up_a_parent_still_waiting_is_left_alone(world: Planned) -> None:
    task = await world.task()
    await world.planner.plan(task.id)

    settled = await world.planner.settle_all()

    assert settled == ()
    assert (await world.repository.get(task.id)).state is S.PLANNING


# ----------------------------------------------------------------------------------------
# What the Planner refuses to plan
# ----------------------------------------------------------------------------------------


async def test_a_task_with_a_plan_written_by_hand_is_not_planned_again(world: Planned) -> None:
    _, task_id = await world.planned_and_running(CORE_ECHO, start=False)

    with pytest.raises(PlanningError, match="already has a plan"):
        await world.planner.plan(task_id)


async def test_the_planning_task_itself_is_not_planned(world: Planned) -> None:
    task = await world.task()
    await world.planner.plan(task.id)

    with pytest.raises(PlanningError, match="is the planning task of"):
        await world.planner.plan(planning_id(task.id))


async def test_a_task_that_ended_without_planning_is_not_planned(world: Planned) -> None:
    task = await world.task()
    await world.engine.cancel(task.id, reason="ferma")

    with pytest.raises(PlanningError, match="CANCELLED"):
        await world.planner.plan(task.id)
