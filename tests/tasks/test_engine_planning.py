"""What the Task Engine gives the Planner: a child, a denial from PLANNING, the author of a plan.

M14.2, ADR 0058. The call that writes a plan is a ``model.complete`` step of a task of its own — the
**child** of the task to plan, the first producer of ``parent_id`` — so that it goes through the
Guardian, the question and the cap like every other call (decision A). The engine creates it
(``create_child``, which moves no state, like ``create``), and closes the parent when that call is
denied (``deny_by_planning``, ``PLANNING → DENIED``): a no of the user is a denial, not a failure
(decision 1 of the review).
"""

from __future__ import annotations

import pytest

from ela.domain import (
    AuditEventType,
    PlanAuthor,
    PlanAuthorKind,
    PrivacyLevel,
    TaskId,
    TaskState,
)
from ela.ports import NotFoundError
from ela.tasks.engine import OPERATIONS, TASK_NAMESPACE, child_id
from ela.tasks.errors import TaskEngineError
from tests.domain.examples import ELA_ACTOR, MODEL_AUTHOR
from tests.tasks.support import (
    HOUR,
    Harness,
    created,
    h,
    plan_for,
    planning,
    planning_denied,
)

__all__ = ["h"]

S = TaskState


async def test_a_child_is_born_created_with_the_parent_s_request_and_deadline(h: Harness) -> None:
    parent = await created(h, deadline=h.clock.now() + HOUR)

    child = await h.engine.create_child(parent.id, key="planning", goal="plan the task")

    assert child.id == child_id(parent.id, "planning")
    assert child.state is S.CREATED
    assert child.parent_id == parent.id
    assert child.intent_id == parent.intent_id
    assert child.deadline == parent.deadline
    assert child.goal == "plan the task"


async def test_a_child_is_born_at_the_strictest_level_whatever_the_parent_s(h: Harness) -> None:
    """A task ELA creates for itself comes into the world at the default and cannot widen itself
    (``engine.create``): the call that writes a plan runs on the Core."""
    parent = await created(h)

    child = await h.engine.create_child(parent.id, key="planning", goal="g")

    assert child.max_privacy is PrivacyLevel.LOCAL_ONLY


async def test_one_child_per_parent_and_key_however_many_times_it_is_asked(h: Harness) -> None:
    parent = await created(h)

    first = await h.engine.create_child(parent.id, key="planning", goal="g")
    again = await h.engine.create_child(parent.id, key="planning", goal="another goal")

    assert again == first
    created_events = [e for e in await h.audit.read() if e.task_id == first.id]
    assert len(created_events) == 1


def test_the_id_of_a_child_is_derived_from_its_parent_and_its_key() -> None:
    parent = TaskId(TASK_NAMESPACE)

    assert child_id(parent, "planning") != child_id(parent, "other")
    assert child_id(parent, "planning") == child_id(parent, "planning")


async def test_a_child_of_nobody_is_refused(h: Harness) -> None:
    with pytest.raises(NotFoundError):
        await h.engine.create_child(TaskId(TASK_NAMESPACE), key="planning", goal="g")


async def test_the_audit_of_a_child_names_its_parent_and_its_key(h: Harness) -> None:
    parent = await created(h)

    child = await h.engine.create_child(parent.id, key="planning", goal="plan the task")

    audit = (await h.audit.read())[-1]
    assert audit.event_type is AuditEventType.TASK_CREATED
    assert audit.task_id == child.id
    assert audit.actor == ELA_ACTOR
    assert audit.payload["operation"] == "create_child"
    assert audit.payload["parent_id"] == str(parent.id)
    assert audit.payload["key"] == "planning"
    assert audit.payload["max_privacy"] == PrivacyLevel.LOCAL_ONLY.value
    assert f"child of task {parent.id}" in audit.summary


# ----------------------------------------------------------------------------------------
# deny_by_planning
# ----------------------------------------------------------------------------------------


def test_deny_by_planning_is_a_row_of_the_table_from_planning_only() -> None:
    row = OPERATIONS["deny_by_planning"]
    assert (row.sources, row.target, row.audit_type, row.key) == (
        frozenset({S.PLANNING}),
        S.DENIED,
        AuditEventType.TASK_DENIED,
        "planning_task_id",
    )


async def _denied_child(h: Harness) -> tuple[TaskId, TaskId]:
    parent, child = await planning_denied(h)
    return parent.id, child.id


async def test_a_parent_whose_planning_was_denied_is_denied_with_the_reason(h: Harness) -> None:
    parent, child = await _denied_child(h)
    reason = f"the planning task {child} was denied: deny_by_approval: rejected by u"

    moved = await h.engine.deny_by_planning(parent, planning_task_id=child, reason=reason)

    assert moved.state is S.DENIED
    audit = (await h.audit.read())[-1]
    assert audit.event_type is AuditEventType.TASK_DENIED
    assert audit.summary == f"deny_by_planning: PLANNING -> DENIED ({reason})"
    assert audit.payload["planning_task_id"] == str(child)


async def test_the_same_planning_task_twice_is_one_denial(h: Harness) -> None:
    parent, child = await _denied_child(h)

    first = await h.engine.deny_by_planning(parent, planning_task_id=child, reason="r")
    again = await h.engine.deny_by_planning(parent, planning_task_id=child, reason="r")

    assert again == first


async def test_a_planning_task_that_is_not_the_parent_s_child_is_refused(h: Harness) -> None:
    parent, child = await _denied_child(h)
    other = await planning(h, with_plan=False)

    with pytest.raises(TaskEngineError, match="not the planning task of"):
        await h.engine.deny_by_planning(other.id, planning_task_id=child, reason="r")
    assert (await h.repository.get(parent)).state is S.PLANNING


async def test_a_planning_task_that_was_not_denied_denies_nothing(h: Harness) -> None:
    parent = await planning(h, with_plan=False)
    child = await h.engine.create_child(parent.id, key="planning", goal="g")

    with pytest.raises(TaskEngineError, match="was not denied"):
        await h.engine.deny_by_planning(parent.id, planning_task_id=child.id, reason="r")
    assert (await h.repository.get(parent.id)).state is S.PLANNING


# ----------------------------------------------------------------------------------------
# PLAN_CREATED says who wrote the plan
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "author",
    [PlanAuthor(by=PlanAuthorKind.HAND), PlanAuthor(by=PlanAuthorKind.PLANNER), MODEL_AUTHOR],
    ids=["hand", "planner", "model"],
)
async def test_the_audit_of_a_plan_says_who_wrote_it(h: Harness, author: PlanAuthor) -> None:
    task = await planning(h, with_plan=False)

    await h.engine.plan(task.id, plan_for(task.id).model_copy(update={"author": author}))

    audit = (await h.audit.read())[-1]
    assert audit.event_type is AuditEventType.PLAN_CREATED
    assert audit.payload["author"] == author.model_dump(mode="json", exclude_none=True)
