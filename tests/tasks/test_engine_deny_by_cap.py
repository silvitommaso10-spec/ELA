"""``deny_by_cap``: a call the Guardian allowed, denied by the month's cap (M14.1, ADR 0057).

The cap is not a permission and a "yes" does not raise it (decision G). So the denial is an
operation of its own, from ``EXECUTING`` only — the call was about to leave —, keyed by the
decision it names, which **allowed** the call: the trail reads ``PERMISSION_DECIDED`` ``ALLOWED``
and then ``TASK_DENIED``, and the reason is the sentence that names the line of the ``.env``.
"""

from __future__ import annotations

from uuid import UUID

import pytest

from ela.domain import AuditEventType, PermissionOutcome, TaskId, TaskState
from ela.tasks.engine import OPERATIONS
from ela.tasks.errors import TaskEngineError
from ela.tasks.state_machine import IllegalTransitionError
from tests.domain.examples import ELA_ACTOR
from tests.tasks.support import Harness, decision_for, executing, h, planning, waiting_approval

__all__ = ["h"]

S = TaskState
REASON = "no monthly cap: ELA_SPENDING_CAP_USD in the Core's .env sets it, in USD"
NUMBERS = {"code": "spending.no_cap", "month": "2026-10", "cap": None, "currency": "USD"}


def allowed(task_id: TaskId):  # type: ignore[no-untyped-def]
    return decision_for(task_id, PermissionOutcome.ALLOWED)


def test_it_is_a_row_of_the_table_from_executing_only() -> None:
    row = OPERATIONS["deny_by_cap"]
    assert (row.sources, row.target, row.audit_type, row.key) == (
        frozenset({S.EXECUTING}),
        S.DENIED,
        AuditEventType.TASK_DENIED,
        "decision_id",
    )


async def test_it_denies_as_ela_with_the_reason_and_the_numbers(h: Harness) -> None:
    task = await executing(h)
    decision = allowed(task.id)

    moved = await h.engine.deny_by_cap(task.id, decision=decision, reason=REASON, payload=NUMBERS)

    assert moved.state is S.DENIED
    audit = (await h.audit.read())[-1]
    assert audit.event_type is AuditEventType.TASK_DENIED
    assert audit.actor == ELA_ACTOR
    assert audit.decision_id == decision.id
    assert audit.payload["operation"] == "deny_by_cap"
    assert audit.payload["reason"] == REASON
    assert audit.payload["capability_id"] == decision.capability_id
    assert {key: audit.payload[key] for key in NUMBERS} == NUMBERS


async def test_the_same_decision_twice_is_one_denial(h: Harness) -> None:
    task = await executing(h)
    decision = allowed(task.id)
    first = await h.engine.deny_by_cap(task.id, decision=decision, reason=REASON, payload=NUMBERS)
    events = len(await h.audit.read())

    again = await h.engine.deny_by_cap(task.id, decision=decision, reason=REASON, payload=NUMBERS)

    assert again == first
    assert len(await h.audit.read()) == events


async def test_it_needs_a_decision_about_this_task(h: Harness) -> None:
    task = await executing(h)
    before = await h.snapshot(task.id)
    with pytest.raises(TaskEngineError, match="about task"):
        await h.engine.deny_by_cap(
            task.id, decision=allowed(TaskId(UUID(int=99))), reason=REASON, payload=NUMBERS
        )
    assert await h.snapshot(task.id) == before


@pytest.mark.parametrize(
    "outcome", [PermissionOutcome.DENIED, PermissionOutcome.REQUIRES_APPROVAL], ids=str
)
async def test_it_needs_a_decision_that_allowed_the_call(
    h: Harness, outcome: PermissionOutcome
) -> None:
    """A Guardian's no is ``deny_by_decision``; the cap only ever stops what was allowed."""
    task = await executing(h)
    before = await h.snapshot(task.id)
    with pytest.raises(TaskEngineError, match="the Guardian allowed"):
        await h.engine.deny_by_cap(
            task.id, decision=decision_for(task.id, outcome), reason=REASON, payload=NUMBERS
        )
    assert await h.snapshot(task.id) == before


@pytest.mark.parametrize("make", [planning, waiting_approval], ids=["planning", "waiting"])
async def test_not_from_a_task_whose_call_was_not_about_to_leave(h: Harness, make) -> None:  # type: ignore[no-untyped-def]
    task = await make(h)
    with pytest.raises((IllegalTransitionError, TaskEngineError)):
        await h.engine.deny_by_cap(
            task.id, decision=allowed(task.id), reason=REASON, payload=NUMBERS
        )
