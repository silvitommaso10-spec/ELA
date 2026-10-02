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
from ela.api.schemas import (
    CancelIn,
    FinishedOut,
    FinishedTaskOut,
    PlanIn,
    RunOut,
    TaskCreate,
    TaskDetail,
    TaskOut,
)
from ela.composition import Ela
from ela.domain import (
    IntentChannel,
    IntentId,
    TaskId,
    TaskState,
    UserIntent,
)
from ela.executive import Run
from ela.tasks.engine import TERMINAL_STATES
from ela.tasks.graph import TaskGraph

__all__ = ["PLAN_IS_TEMPORARY", "close_if_free", "router"]

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
    task = await ela.engine.create(
        intent, goal=body.goal, deadline=body.deadline, max_privacy=body.max_privacy
    )
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


@router.get("/finished")
async def finished_tasks(ela: ElaDep, limit: Annotated[int, Query(ge=1)]) -> FinishedOut:
    """The last ``limit`` tasks to reach a final state, the last first, and how many in all.

    M17.2b (ADR 0049): what the two homes list beside the live tasks. A route of its own because
    its order is not the one ``GET /tasks`` declares, and a different order is a different
    question. **Declared before** ``/{task_id}``: the router takes the first route whose path
    matches, and ``{task_id}`` matches any segment — ``finished`` would be refused as an id.

    ``limit`` is required: the route answers «the last N», and an N that is missing is the caller's
    bug. The count is read **after** the tasks, so ``total`` is never smaller than what came back.
    """
    tasks = await ela.repository.finished(states=TERMINAL_STATES, limit=limit)
    counted = await ela.repository.count(states=TERMINAL_STATES)
    rows: list[FinishedTaskOut] = []
    for task in tasks:
        halt = await ela.executor.halt(task.id)
        rows.append(FinishedTaskOut(**TaskOut.of(task).model_dump(), halt=halt))
    return FinishedOut(tasks=tuple(rows), total=sum(counted.values()))


@router.get("/{task_id}")
async def read_task(task_id: UUID, ela: ElaDep) -> TaskDetail:
    """The task and where each of its steps stands. No plan yet: ``steps`` is empty."""
    task = await ela.repository.get(TaskId(task_id))
    graph = None if task.plan_id is None else await ela.engine.graph(TaskId(task_id))
    return TaskDetail.of_graph(task, graph, await ela.executor.halt(task.id))


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
    the user's consent is needed, when no node is eligible, or when a step went out to a node and
    has not come back (``assigned``, ADR 0038 §10). A second ``run`` of the same task while this
    one is walking is refused, not queued (ADR 0023 §9).
    """
    identifier = TaskId(task_id)
    # The check and the insert with nothing in between (M13.3, C10): ``running_of`` promises it,
    # and until M13.3 a heartbeat and a reading of the power source sat here, so two runs of one
    # task arriving together both passed the check — the race of M13.1b in a configuration ELA
    # declares. Whatever this route does beyond the check, it does holding the lock.
    if identifier not in running:
        running.add(identifier)
    elif (await ela.repository.get(identifier)).state in TERMINAL_STATES:
        # Never a 409 for a task that has ended (M6.3c, decision 16 of the review): whoever holds
        # the lock — another run, a delivery, a claim, the close of a stop — closes what is open,
        # and this run answers as the door would. Two runs of a live task still get the 409.
        return _out(await ela.runner.answer(identifier))
    else:
        raise TaskAlreadyRunningError(identifier)
    try:
        # No heartbeat here (M13.3, ADR 0048 §2): a route that is answering is not who says the
        # machine is alive (ADR 0044 §8). The runner asks the Core's heartbeat for one before every
        # placement, with the power source read at that instant (M12.3c, ADR 0029 §7).
        run = await ela.runner.run(identifier)
    finally:
        running.discard(identifier)
    return _out(run)


def _out(run: Run) -> RunOut:
    return RunOut(
        task=TaskOut.of(run.task),
        outcome=run.outcome.value,
        steps=tuple(run.steps),
        reason=run.reason,
        halt=run.halt,
    )


@router.post("/{task_id}/cancel")
async def cancel_task(
    task_id: UUID, body: CancelIn, ela: ElaDep, identity: IdentityDep, running: RunningDep
) -> TaskOut:
    """Stop the task (§65). The actor is the user: stopping ELA is the user's, always.

    Whoever the middleware resolved for the call (D12; ADR 0037 §15) — in M12.1 only the Core's
    token reaches this route, so it is the user at this machine.

    **The stop does not take the lock of ``run`` to stop** (M6.3c, ADR 0054 §10): that is what lets
    it reach a tool that is running, which hears it at its point of no return. It takes the lock
    **to close** the step the task left open — after the end is written, and only if nobody holds
    it: whoever does, closes it as its last act.
    """
    identifier = TaskId(task_id)
    await ela.engine.cancel(identifier, reason=body.reason, actor=identity.actor)
    await close_if_free(identifier, ela, running)
    return TaskOut.of(await ela.repository.get(identifier))


async def close_if_free(task_id: TaskId, ela: Ela, running: set[TaskId]) -> None:
    """Close the step an ended task left RUNNING, under the lock of ``run`` — **if it is free**
    (M6.3c, ADR 0054 §5). The check and the insert with nothing in between, as for ``run``; a
    lock already taken means its holder rereads the task as its last act and closes it there."""
    if task_id in running:
        return
    running.add(task_id)
    try:
        await ela.executor.close_open_step(task_id)
    finally:
        running.discard(task_id)
