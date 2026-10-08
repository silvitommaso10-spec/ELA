"""Why a task ended, read back from the engine's own words (M13.1e, ADR 0059).

The derivation is pure — :func:`~ela.tasks.ending.of_the_audit` and
:func:`~ela.tasks.ending.of_the_trail` —, and :meth:`~ela.tasks.engine.TaskEngine.ending` is the one
reader that holds the ports: the audit, then the trail when the audit has no row (the window of a
crash between the two writes, ADR 0054 §7), and for a task denied by its planning the child that
was denied (M14.2). The cases that go through the routes, one per operation of the engine, are in
``tests/api/test_ends_by_operation.py``.
"""

from __future__ import annotations

import pytest

from ela.domain import (
    ApprovalStatus,
    AuditEvent,
    PermissionOutcome,
    TaskState,
)
from ela.tasks.ending import REASONED, Ending, of_the_audit, of_the_trail
from ela.tasks.engine import LIVE_STATES, OPERATIONS
from ela.tasks.state_machine import TERMINAL_STATES
from tests.domain.examples import AUDIT_EVENT
from tests.tasks.support import (
    ERROR,
    Harness,
    approval_for,
    decision_for,
    executing,
    planning_denied,
    task_in,
    waiting_approval,
)


def closing_summary(events: tuple[AuditEvent, ...], state: TaskState) -> str:
    """The summary of the audit event that wrote the task's state: chosen by the state, not the
    type, as the test of the routes chooses it."""
    return [event for event in events if event.payload.get("new_state") == state.value][-1].summary


def test_the_ends_with_a_reason_are_every_end_but_completed() -> None:
    """Decision B: the set the runner used since M13.1c, now read from here by everyone."""
    assert TERMINAL_STATES - {TaskState.COMPLETED} == REASONED


def test_every_operation_that_closes_a_task_closes_it_in_a_state_of_reasoned_or_completed() -> None:
    """The closure the test of the routes stands on: an operation whose target is final and not
    ``COMPLETED`` is one :data:`REASONED` names."""
    final = {op.target for op in OPERATIONS.values() if op.target in TERMINAL_STATES}
    assert final - {TaskState.COMPLETED} <= REASONED


@pytest.mark.parametrize("state", sorted(LIVE_STATES | {TaskState.COMPLETED}))
async def test_a_task_that_did_not_end_with_a_reason_has_no_ending(
    h: Harness, state: TaskState
) -> None:
    task = await task_in(h, state)

    assert await h.engine.ending(task) is None


async def test_the_reason_is_the_summary_of_the_transition_and_its_payload_the_rest(
    h: Harness,
) -> None:
    task = await waiting_approval(h)
    denied = await h.engine.deny(
        task.id, approval=approval_for(task.id, ApprovalStatus.REJECTED, responded_by="tommaso")
    )

    ending = await h.engine.ending(denied)

    assert ending == Ending(
        reason="deny_by_approval: WAITING_APPROVAL -> DENIED (rejected by tommaso)",
        operation="deny_by_approval",
        code=None,
        responded_by="tommaso",
        planning_task_id=None,
    )
    assert ending.reason == closing_summary(await h.audit.read(), TaskState.DENIED)


async def test_the_code_is_read_from_the_payload_wherever_the_payload_carries_one(
    h: Harness,
) -> None:
    """Decision 1 of the review: not from a list of operations. A failure's code and the cap's
    ``spending.*`` come the same way."""
    failed = await h.engine.fail((await executing(h)).id, ERROR)
    capped = await h.engine.deny_by_cap(
        (task := await executing(h)).id,
        decision=decision_for(task.id, PermissionOutcome.ALLOWED, tail=921),
        reason="no cap is declared",
        payload={"code": "spending.no_cap"},
    )
    guarded = await h.engine.deny(
        (other := await executing(h)).id, decision=decision_for(other.id, tail=922)
    )

    codes = [await h.engine.ending(task) for task in (failed, capped, guarded)]

    assert [None if one is None else one.code for one in codes] == [
        ERROR.code,
        "spending.no_cap",
        None,
    ]


async def test_a_value_of_the_payload_that_is_not_text_is_no_code(h: Harness) -> None:
    """A payload is the engine's JSON: a code that is not a string, or an empty identity, is not one
    a surface can say, and nothing is read from it."""
    task = await task_in(h, TaskState.FAILED)
    event = AUDIT_EVENT.model_copy(
        update={
            "task_id": task.id,
            "summary": "fail: EXECUTING -> FAILED (x)",
            "payload": {"operation": "fail", "new_state": "FAILED", "code": 3, "responded_by": ""},
        }
    )

    found = of_the_audit(task, (event,))

    assert found is not None
    assert (found.code, found.responded_by) == (None, None)


async def test_without_the_audit_row_the_trail_says_the_operation_and_its_words(
    h: Harness,
) -> None:
    """The window of a crash between the trail and the audit (ADR 0054 §7): the message of the
    ``STATE_CHANGED`` with the name of its operation; no code and nobody who answered, which only
    the audit carries — the no still says its id, inside the words."""
    task = await waiting_approval(h)
    denied = await h.engine.deny(
        task.id, approval=approval_for(task.id, ApprovalStatus.REJECTED, responded_by="tommaso")
    )
    trail = await h.repository.events(task.id)

    assert of_the_audit(denied, ()) is None
    assert of_the_trail(denied, trail) == Ending(
        reason="deny_by_approval: rejected by tommaso",
        operation="deny_by_approval",
        code=None,
        responded_by=None,
        planning_task_id=None,
    )


async def test_without_the_audit_row_nor_the_trail_the_state_is_all_there_is(
    h: Harness,
) -> None:
    task = await task_in(h, TaskState.CANCELLED)

    assert of_the_trail(task, ()) == Ending(
        reason="CANCELLED", operation=None, code=None, responded_by=None, planning_task_id=None
    )


async def test_a_trail_change_without_words_is_its_operation_alone(h: Harness) -> None:
    task = await task_in(h, TaskState.CANCELLED)

    found = of_the_trail(task, await h.repository.events(task.id))

    assert found.reason == "cancel"
    assert found.operation == "cancel"


async def test_a_task_denied_by_its_planning_says_who_answered_its_planning_task(
    h: Harness,
) -> None:
    """Fact 2 of the census: the parent's payload names the child, not who answered; the reader
    follows the child, and never reads the id out of the words."""
    parent, child = await planning_denied(h)
    denied = await h.engine.deny_by_planning(
        parent.id, planning_task_id=child.id, reason=f"the planning task {child.id} was denied"
    )

    ending = await h.engine.ending(denied)

    assert ending is not None
    assert ending.operation == "deny_by_planning"
    assert ending.planning_task_id == child.id
    assert ending.responded_by == "tommaso"


async def test_the_child_is_followed_from_the_trail_too(h: Harness) -> None:
    """Without the parent's audit row the key of the trail names the child just the same."""
    parent, child = await planning_denied(h)
    denied = await h.engine.deny_by_planning(
        parent.id, planning_task_id=child.id, reason=f"the planning task {child.id} was denied"
    )

    found = of_the_trail(denied, await h.repository.events(parent.id))

    assert found.planning_task_id == child.id
