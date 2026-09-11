"""Tasks over HTTP: create, read, plan, run, stop (spec §14, §15, §65; ADR 0023 §6, §9).

**The plan arrives from outside** because the Planner (§13) does not exist yet: ``/plan`` does
``start_planning`` → ``plan`` → ``queue``, and the day the Planner arrives it takes exactly that
place. Every transition is the Task Engine's; this module writes nothing of its own.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from ela.api.deps import ElaDep, IdentityDep, RunningDep
from ela.api.errors import TaskAlreadyRunningError
from ela.api.schemas import CancelIn, PlanIn, RunOut, TaskCreate, TaskDetail, TaskOut
from ela.devices.local import (
    LOCAL_DEVICE_ID,
)
from ela.domain import (
    IntentChannel,
    IntentId,
    TaskId,
    TaskState,
    UserIntent,
)
from ela.tasks.graph import TaskGraph

__all__ = ["PLAN_IS_TEMPORARY", "router"]

PLAN_IS_TEMPORARY = (
    "**The shape of this request is temporary and unversioned.** ELA has no Planner (spec §13) "
    "yet, so a plan is written by hand and sent here; the day the Planner writes plans itself, "
    "this endpoint's schema may change — or the endpoint may go — **without a version bump**. "
    "Build nothing long-lived on it.\n\n"
    "Attaches the plan and queues the task: CREATED to PLANNING to (plan) to QUEUED. A plan that "
    "cannot be a graph — a cycle, a dependency on a step outside the plan, a duplicate id — is "
    "refused before the task is moved, and nothing is written."
)
"""What the API says about itself where whoever uses it will read it (review of M8.1).

The limit was declared in ADR 0023, and a limit that lives only in an ADR is one the caller
never sees: it belongs in the description the schema carries, next to the request it is about.
"""

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", status_code=201)
async def create_task(body: TaskCreate, ela: ElaDep) -> TaskOut:
    """A task from what the user asked (§12). It has no plan yet, so nothing runs."""
    intent = UserIntent(
        id=IntentId(ela.ids.new_uuid()),
        created_at=ela.clock.now(),
        text=body.text,
        channel=IntentChannel.API,
    )
    task = await ela.engine.create(intent, goal=body.goal, deadline=body.deadline)
    return TaskOut.of(task)


@router.get("")
async def list_tasks(
    ela: ElaDep,
    state: Annotated[list[TaskState] | None, Query()] = None,
    limit: Annotated[int | None, Query(ge=1)] = None,
) -> tuple[TaskOut, ...]:
    """The tasks in insertion order; ``state`` may be repeated, ``limit`` applies after it."""
    states = frozenset(state) if state else None
    tasks = await ela.repository.tasks(states=states, limit=limit)
    return tuple(TaskOut.of(task) for task in tasks)


@router.get("/{task_id}")
async def read_task(task_id: UUID, ela: ElaDep) -> TaskDetail:
    """The task and where each of its steps stands. No plan yet: ``steps`` is empty."""
    task = await ela.repository.get(TaskId(task_id))
    graph = None if task.plan_id is None else await ela.engine.graph(TaskId(task_id))
    return TaskDetail.of_graph(task, graph)


@router.post("/{task_id}/plan", description=PLAN_IS_TEMPORARY)
async def attach_plan(task_id: UUID, body: PlanIn, ela: ElaDep) -> TaskOut:
    """Attach the plan and queue the task: CREATED → PLANNING → (plan) → QUEUED.

    The plan is turned into a graph **before** the task is moved. ``engine.plan`` would refuse it
    anyway — it is the same ``TaskGraph.from_plan`` — but by then the task would sit in PLANNING
    with no plan and no way back, and a caller who mistyped a dependency would have bricked their
    own task. Nothing is written for a plan that cannot be a graph.

    A task **already** PLANNING is planned without asking the engine to move it again: that is
    where a previously refused plan may have left it.
    """
    identifier = TaskId(task_id)
    plan = body.to_domain(task_id, ela.ids.new_uuid(), ela.clock.now())
    TaskGraph.from_plan(plan)
    if (await ela.repository.get(identifier)).state is TaskState.CREATED:
        await ela.engine.start_planning(identifier)
    await ela.engine.plan(identifier, plan)
    task = await ela.engine.queue(identifier, reason="planned through the API")
    return TaskOut.of(task)


@router.post("/{task_id}/run")
async def run_task(task_id: UUID, ela: ElaDep, running: RunningDep) -> RunOut:
    """Walk the plan as far as it goes and say where it stopped (ADR 0019).

    Synchronous: the answer comes back when the run stops, which is when the task closes, when
    the user's consent is needed, or when no node is eligible. A second ``run`` of the same task
    while this one is walking is refused, not queued (ADR 0023 §9).
    """
    identifier = TaskId(task_id)
    if identifier in running:
        raise TaskAlreadyRunningError(identifier)
    # The local node is this process: a request being served is proof it is alive, and without a
    # heartbeat within the TTL the orchestrator would find no eligible node and the task would
    # wait forever (ADR 0016 §3). A node that reports itself on a schedule is M8.3.
    await ela.devices.heartbeat(LOCAL_DEVICE_ID)
    running.add(identifier)
    try:
        run = await ela.runner.run(identifier)
    finally:
        running.discard(identifier)
    return RunOut(
        task=TaskOut.of(run.task),
        outcome=run.outcome.value,
        steps=tuple(run.steps),
        reason=run.reason,
    )


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: UUID, body: CancelIn, ela: ElaDep, identity: IdentityDep) -> TaskOut:
    """Stop the task (§65). The actor is the user: stopping ELA is the user's, always.

    Whoever the middleware resolved for the call (D12; ADR 0037 §15) — in M12.1 only the Core's
    token reaches this route, so it is the user at this machine.
    """
    task = await ela.engine.cancel(TaskId(task_id), reason=body.reason, actor=identity.actor)
    return TaskOut.of(task)
