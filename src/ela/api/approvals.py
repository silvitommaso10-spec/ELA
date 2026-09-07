"""The user's answer to a request for consent (spec §30, §62; ADR 0015 §9, ADR 0023 §8).

**This module is the one exemption to architecture rule 19**, by path: it is the only place in
``src/ela`` that calls ``ApprovalStore.respond``. A "yes" is the user's, and the Core does not
answer its own requests — so the call lives where the user reaches ELA, and nowhere else.

The order is the decision (ADR 0015 §9): ``respond`` **first**, the engine **after**. If the
engine moved first and ``respond`` failed, the task would be QUEUED with a request still PENDING
and the executor's retry would ask for it again, in a loop.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from ela.api.deps import ElaDep
from ela.api.schemas import AnswerIn, ApprovalOut, TaskOut
from ela.domain import Approval, ApprovalId, ApprovalStatus, Task, TaskId, TaskState
from ela.ports import ApprovalAlreadyAnsweredError, NotFoundError

__all__ = ["router"]

router = APIRouter(tags=["approvals"])


@router.get("/approvals")
async def pending_approvals(
    ela: ElaDep, limit: Annotated[int | None, Query(ge=1)] = None
) -> tuple[ApprovalOut, ...]:
    """What waits for an answer, across every task, oldest first.

    ``now`` is always passed: an expired request could no longer be answered — ``respond``
    refuses it — and showing it would be asking the user for something they cannot give (§33).
    """
    waiting = await ela.approvals.pending(now=ela.clock.now(), limit=limit)
    return tuple(ApprovalOut.of(one) for one in waiting)


@router.post("/tasks/{task_id}/approve")
async def approve(task_id: UUID, body: AnswerIn, ela: ElaDep) -> TaskOut:
    """ "Yes": the request is granted and the task goes back in the queue."""
    return await _answer(task_id, body, ela, ApprovalStatus.GRANTED)


@router.post("/tasks/{task_id}/deny")
async def deny(task_id: UUID, body: AnswerIn, ela: ElaDep) -> TaskOut:
    """ "No": the request is rejected and the task is DENIED. A refusal is an answer (§62)."""
    return await _answer(task_id, body, ela, ApprovalStatus.REJECTED)


async def _answer(task_id: UUID, body: AnswerIn, ela: ElaDep, status: ApprovalStatus) -> TaskOut:
    identifier = TaskId(task_id)
    approval = await ela.approvals.get(ApprovalId(body.approval_id))
    if approval.task_id != identifier:
        raise NotFoundError("approval", f"{body.approval_id} of task {task_id}")
    try:
        answered = await ela.approvals.respond(
            approval.id,
            status=status,
            responded_by=ela.settings.core.user_name,
            now=ela.clock.now(),
        )
    except ApprovalAlreadyAnsweredError:
        return TaskOut.of(await _already_answered(identifier, approval.id, ela, status))
    return TaskOut.of(await _move(identifier, answered, ela, status))


async def _already_answered(
    task_id: TaskId, approval_id: ApprovalId, ela: ElaDep, status: ApprovalStatus
) -> Task:
    """Crash window 5c of ADR 0015 §8, repaired here because it opens here.

    The answer is in the store and the engine was never told: whoever answers finds a
    WAITING_APPROVAL task with a request already resolved, and calls ``approve``/``deny`` again.
    A *different* answer is not that window — it is a second answer to a question already
    answered — and it is refused with the store's own error.
    """
    stored = await ela.approvals.get(approval_id)
    if stored.status is not status:
        raise ApprovalAlreadyAnsweredError(approval_id, stored.status)
    task = await ela.repository.get(task_id)
    if task.state is not TaskState.WAITING_APPROVAL:
        return task  # the answer was recorded *and* applied: nothing is left to do
    return await _move(task_id, stored, ela, status)


async def _move(task_id: TaskId, approval: Approval, ela: ElaDep, status: ApprovalStatus) -> Task:
    """The engine, after the store, never before it (ADR 0015 §9)."""
    if status is ApprovalStatus.GRANTED:
        return await ela.engine.approve(task_id, approval)
    return await ela.engine.deny(task_id, approval=approval)
