"""The gate on the Planner's call: the cap of ADR 0057, on the road of every call (decision A).

The call that writes a plan is a ``model.complete`` of the planning task, so the cap reserves it
in the ``STARTED`` and denies it with ``deny_by_cap`` — **from EXECUTING, which is where the child
is**: no new source of ``deny_by_cap`` (ADR 0057 §7), no exemption. A call a yes could not let out
is denied before the question, and nobody is woken (ADR 0057 §6). The parent then ends
``DENIED`` with ``deny_by_planning``, the child's reason inside its own. The proof by hand does not
reach this: the suite does (criterion 3).
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from ela.domain import AuditEventType, ExecutionStatus, TaskState
from ela.executive.planner import PlanningOutcome, planning_id
from tests.executive.planning import Planned

S = TaskState


async def reason_of(world: Planned, task_id: object) -> str:
    return (await world.runner.answer(task_id)).reason or ""  # type: ignore[arg-type]


async def test_without_a_cap_the_child_is_denied_before_its_question_and_nothing_leaves(
    tmp_path: Path,
) -> None:
    world = Planned(tmp_path / "workspace", cap=None)
    task = await world.task()

    asked = await world.planner.plan(task.id)

    assert asked.outcome is PlanningOutcome.DENIED
    child = await world.repository.get(planning_id(task.id))
    assert child.state is S.DENIED
    assert asked.approval is None, "no question a yes could not answer"
    assert world.model.requests == ()
    assert [
        r
        for r in await world.results.for_step(
            child.id, (await world.repository.plan(child.id)).steps[0].id
        )
    ] == []
    reason = await reason_of(world, task.id)
    assert reason.startswith("deny_by_planning: PLANNING -> DENIED (the planning task ")
    assert "deny_by_cap" in reason
    assert "ELA_SPENDING_CAP_USD" in reason


async def test_a_cap_too_small_for_the_worst_case_denies_the_call_before_the_question(
    tmp_path: Path,
) -> None:
    world = Planned(tmp_path / "workspace", cap=Decimal("0.001"))
    task = await world.task()

    asked = await world.planner.plan(task.id)

    assert asked.outcome is PlanningOutcome.DENIED
    assert world.model.requests == ()
    assert "the monthly cap would be crossed" in await reason_of(world, task.id)


async def test_the_question_names_the_worst_case_and_what_the_month_has_left(
    tmp_path: Path,
) -> None:
    world = Planned(tmp_path / "workspace")
    task = await world.task()

    asked = await world.planner.plan(task.id)

    assert asked.approval is not None
    pieces = asked.approval.metadata["asked"]
    assert "worst_case" in pieces and "left" in pieces  # type: ignore[operator]


async def test_a_month_spent_between_the_question_and_the_yes_denies_after_the_yes(
    tmp_path: Path,
) -> None:
    """The numbers of the question were of that instant (ADR 0057 §8): after the yes the gate
    reads the month again, and a yes does not raise the cap (decision G of M14.1)."""
    world = Planned(tmp_path / "workspace", cap=Decimal("0.015"))
    first = await world.task("primo")
    second = await world.task("secondo")
    asked_first = await world.planner.plan(first.id)
    asked_second = await world.planner.plan(second.id)
    await world.yes(asked_first)
    await world.yes(asked_second)

    await world.planner.plan(first.id)
    second_planned = await world.planner.plan(second.id)

    child = await world.repository.get(planning_id(second.id))
    assert child.state is S.DENIED
    assert second_planned.outcome is PlanningOutcome.DENIED
    assert "deny_by_cap" in await reason_of(world, second.id)


async def test_the_call_that_left_was_reserved_in_its_started_record(tmp_path: Path) -> None:
    world = Planned(tmp_path / "workspace")

    task_id, _ = await world.planned()

    child = planning_id(task_id)
    plan = await world.repository.plan(child)
    rows = await world.results.for_step(child, plan.steps[0].id)
    started = [row for row in rows if row.status is ExecutionStatus.STARTED]
    assert len(started) == 1 and started[0].worst_case is not None
    executed = [
        e
        for e in await world.audit.read(task_id=child)
        if e.event_type is AuditEventType.TOOL_EXECUTED
    ]
    assert executed and executed[0].usage is not None
