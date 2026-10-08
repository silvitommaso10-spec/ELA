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

from ela.api.deps import ElaDep, IdentityDep, RunningDep
from ela.api.schemas import AnswerIn, ApprovalOut, TaskOut
from ela.api.security import (
    Identity,
)
from ela.api.tasks import close_if_free, run_task, settle_the_plan_of, task_out
from ela.domain import Approval, ApprovalId, ApprovalStatus, Task, TaskId, TaskState
from ela.ports import ApprovalAlreadyAnsweredError, NotFoundError
from ela.tasks.errors import TaskEngineError

__all__ = ["answered_and_resumed", "router"]

router = APIRouter(tags=["approvals"])


@router.get("/approvals")
async def pending_approvals(
    ela: ElaDep, limit: Annotated[int | None, Query(ge=1)] = None
) -> tuple[ApprovalOut, ...]:
    """What waits for an answer, across every task, oldest first.

    ``now`` is always passed: an expired request could no longer be answered — ``respond``
    refuses it — and showing it would be asking the user for something they cannot give (§33).

    A request whose **task has moved on** is left out for the same reason (review of M8.1): the
    user stopped it (§65), or it expired, and an answer would no longer do anything. The store
    cannot know that — it keeps requests, not tasks — so the check is here, where the task is a
    read away.
    """
    answerable = []
    for one in await ela.approvals.pending(now=ela.clock.now(), limit=limit):
        task = await ela.repository.get(one.task_id)
        if task.state is TaskState.WAITING_APPROVAL:
            answerable.append(ApprovalOut.of(one))
    return tuple(answerable)


@router.post("/tasks/{task_id}/approve")
async def approve(task_id: UUID, body: AnswerIn, ela: ElaDep, identity: IdentityDep) -> TaskOut:
    """ "Yes": the request is granted and the task goes back in the queue."""
    return await _answer(task_id, body, ela, ApprovalStatus.GRANTED, identity)


@router.post("/tasks/{task_id}/deny")
async def deny(
    task_id: UUID, body: AnswerIn, ela: ElaDep, identity: IdentityDep, running: RunningDep
) -> TaskOut:
    """ "No": the request is rejected and the task is DENIED. A refusal is an answer (§62).

    The step that asked did not act, and it does not stay RUNNING in a task that has ended: it is
    closed CANCELLED, under the lock of ``run`` (M6.3c, ADR 0054 §5)."""
    answered = await _answer(task_id, body, ela, ApprovalStatus.REJECTED, identity)
    if answered.state is TaskState.DENIED:
        await close_if_free(TaskId(task_id), ela, running)
        # A no to the call of a planning task closes the task it plans (M14.2, ADR 0058).
        await settle_the_plan_of(await ela.repository.get(TaskId(task_id)), ela)
    return answered


async def _answer(
    task_id: UUID, body: AnswerIn, ela: ElaDep, status: ApprovalStatus, identity: Identity
) -> TaskOut:
    identifier = TaskId(task_id)
    approval = await ela.approvals.get(ApprovalId(body.approval_id))
    if approval.task_id != identifier:
        raise NotFoundError("approval", f"{body.approval_id} of task {task_id}")
    task = await ela.repository.get(identifier)
    if task.state is not TaskState.WAITING_APPROVAL:
        return await task_out(_settled(task, approval, status), ela)
    try:
        answered = await ela.approvals.respond(
            approval.id,
            status=status,
            responded_by=identity.actor.id,
            now=ela.clock.now(),
        )
    except ApprovalAlreadyAnsweredError:
        # Crash window 5c of ADR 0015 §8, repaired here because it opens here: the answer is in
        # the store and the engine was never told. The same answer completes the move; a
        # *different* one is a second answer to a question already answered, and is refused.
        answered = await ela.approvals.get(approval.id)
        if answered.status is not status:
            raise
    return await task_out(await _move(identifier, answered, ela, status), ela)


async def answered_and_resumed(
    found: ApprovalOut,
    *,
    said_yes: bool,
    ela: ElaDep,
    identity: IdentityDep,
    running: RunningDep,
) -> TaskOut:
    """The answer, and — after a "yes" — the run it would otherwise wait for (M12.5 dec. H1).

    **One conduct, in one place** (M17.2 dec. K.1). At the Mac the user does two things,
    ``ela task approve`` and ``ela task run``; a page does the same two in one request, because a
    "yes" that sat there until somebody came home would not make ELA usable away from the Mac.
    Both surfaces call **this**, and not a copy of it three lines long: two copies are two
    conducts, and the first ``if`` somebody changes makes them diverge.

    It lives here, on the **routes' side** of the boundary, for two reasons. This is the module
    that owns a "yes" — the one exemption by path of architecture rule 19 (ADR 0015 §9) — and a
    function of the routes is precisely what a page is allowed to call (rule 55). A third module
    with no router would be a place that rule does not walk, which is where somebody reads the
    world tomorrow.

    A "no" runs nothing: the task is DENIED. And the browser may stop waiting before a long run
    ends — the run goes on, and the next page shows the task's true state (M12.5 dec. H).
    """
    body = AnswerIn(approval_id=ApprovalId(found.id))
    answered = (
        await approve(found.task_id, body, ela, identity)
        if said_yes
        else await deny(found.task_id, body, ela, identity, running)
    )
    if said_yes and answered.state is TaskState.QUEUED:
        await run_task(found.task_id, ela, running)
    return answered


def _settled(task: Task, approval: Approval, status: ApprovalStatus) -> Task:
    """What to say about a task that is no longer waiting for this answer.

    Three cases, and only one of them is an answer at all: the same answer, already recorded and
    already applied, which is idempotent and returns the task as it stands; a *different* answer,
    which the store's own error refuses; and a request still PENDING on a task that has moved on
    — stopped (§65) or expired — where the honest thing is to refuse **before writing**, because
    an answer nobody could act on is a record of a decision that never took effect.
    """
    if approval.status is status:
        return task
    if approval.status is not ApprovalStatus.PENDING:
        raise ApprovalAlreadyAnsweredError(approval.id, approval.status)
    raise TaskEngineError(
        task.id,
        f"task is {task.state.value}, not WAITING_APPROVAL: there is nothing left to answer",
    )


async def _move(task_id: TaskId, approval: Approval, ela: ElaDep, status: ApprovalStatus) -> Task:
    """The engine, after the store, never before it (ADR 0015 §9)."""
    if status is ApprovalStatus.GRANTED:
        return await ela.engine.approve(task_id, approval)
    return await ela.engine.deny(task_id, approval=approval)
