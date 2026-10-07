"""Tasks over HTTP: create, read, plan, run, stop (spec §14, §15, §65; ADR 0023 §6, §9).

**A plan arrives in two ways** since M14.2 (ADR 0058). ``/plan`` takes a plan written by hand and
does ``start_planning`` → ``plan`` → ``queue``; ``/planning`` asks ELA's Planner (§13), whose plan
enters by that same door — ``engine.plan`` and ``queue`` — and nobody else's. Every transition is
the Task Engine's; this module writes nothing of its own.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from ela.api.deps import ElaDep, IdentityDep, RunningDep
from ela.api.errors import PlanNotReadyError, TaskAlreadyRunningError
from ela.api.schemas import (
    ApprovalOut,
    CancelIn,
    FinishedOut,
    FinishedTaskOut,
    PlanIn,
    PlanningOut,
    RunOut,
    TaskCreate,
    TaskDetail,
    TaskOut,
)
from ela.composition import Ela
from ela.domain import (
    IntentChannel,
    IntentId,
    Task,
    TaskId,
    TaskState,
    TaskStep,
    UserIntent,
)
from ela.executive import Run
from ela.executive.planner import Planning, PlanningError, is_planning_task, planning_id
from ela.executive.readiness import Unready, readiness
from ela.tasks.engine import TERMINAL_STATES
from ela.tasks.graph import TaskGraph

__all__ = ["PLAN_IS_TEMPORARY", "close_if_free", "router", "settle_the_plan_of"]

PLAN_IS_TEMPORARY = (
    "**The shape of this request is the shape of a plan written by hand, and it is unversioned.** "
    "ELA's Planner (spec §13) writes plans itself, through `POST /tasks/{task_id}/planning`; this "
    "endpoint stays for the plans a person writes — the tests and the proofs drive ELA with them "
    "—, and its schema may change **without a version bump**. Build nothing long-lived on it.\n\n"
    "Attaches the plan and queues the task: CREATED to PLANNING to (plan) to QUEUED. A plan that "
    "cannot be a graph — a cycle, a dependency on a step outside the plan, a duplicate id — or "
    "with a step the executor would refuse — not exactly one capability of the catalogue, no "
    "success condition, one outside its verifier's vocabulary — is refused before the task is "
    "moved, and nothing is written. A task ELA is planning takes no plan by hand."
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
    """The task and where each of its steps stands. No plan yet: ``steps`` is empty.

    Since M14.2 (ADR 0058) it says who wrote the plan, and for a task ELA was asked to plan its
    planning task and, when the model wrote no plan, the model's reason: what the user reads before
    starting a plan the model wrote (decision I).
    """
    return await detail_of(TaskId(task_id), ela)


async def detail_of(task_id: TaskId, ela: Ela, planning: Planning | None = None) -> TaskDetail:
    """The detail of ``task_id``, with its author and its planning: one composer for the read and
    for the answer of ``/planning``."""
    task = await ela.repository.get(task_id)
    graph = None if task.plan_id is None else await ela.engine.graph(task_id)
    author = None if task.plan_id is None else (await ela.repository.plan(task_id)).author
    if planning is None and not is_planning_task(task):
        planning = await ela.planner.view(task_id)
    child = None if planning is None else planning.planning_task
    return TaskDetail.of_graph(
        task,
        graph,
        await ela.executor.halt(task.id),
        author=author,
        planning_task_id=None if child is None else child.id,
        no_plan=None if planning is None else planning.no_plan,
    )


@router.post("/{task_id}/plan", description=PLAN_IS_TEMPORARY)
async def attach_plan(task_id: UUID, body: PlanIn, ela: ElaDep) -> TaskOut:
    """Attach the plan and queue the task: CREATED → PLANNING → (plan) → QUEUED.

    The plan is turned into a graph **before** the task is moved. ``engine.plan`` would refuse it
    anyway — it is the same ``TaskGraph.from_plan`` — but by then the task would sit in PLANNING
    with no plan and no way back, and a caller who mistyped a dependency would have bricked their
    own task. Nothing is written for a plan that cannot be a graph.

    A task **already** PLANNING is planned without asking the engine to move it again: that is
    where a previously refused plan may have left it.

    Since M14.2 (ADR 0058, decision 8 of the review) the steps also pass the executor's own
    preconditions — :func:`~ela.executive.readiness.readiness` — **before** anything is written: a
    plan the executor would refuse at the first run, leaving its task ``EXECUTING``, is a ``422``
    here. The arguments stay the Guardian's, at the run: a plan written by hand may want to show a
    denial.
    """
    identifier = TaskId(task_id)
    plan = body.to_domain(task_id, ela.ids.new_uuid(), ela.clock.now())
    TaskGraph.from_plan(plan)
    _ready(plan.steps, ela)
    if (planning := (await ela.planner.view(identifier)).planning_task) is not None:
        raise PlanningError(identifier, f"ELA is planning this task: task {planning.id}")
    if (await ela.repository.get(identifier)).state is TaskState.CREATED:
        await ela.engine.start_planning(identifier)
    await ela.engine.plan(identifier, plan)
    task = await ela.engine.queue(identifier, reason="planned through the API")
    return TaskOut.of(task)


def _ready(steps: tuple[TaskStep, ...], ela: Ela) -> None:
    """Refuse a plan with a step the executor would refuse, naming the step by position (§57: the
    sentence quotes no word of the plan)."""
    for index, step in enumerate(steps):
        ready = readiness(
            step, capabilities=ela.capabilities, tools=ela.tools, verifiers=ela.verifiers
        )
        if isinstance(ready, Unready):
            raise PlanNotReadyError(f"step {index + 1} of {len(steps)} {ready.said}")


@router.post("/{task_id}/planning")
async def plan_task(task_id: UUID, ela: ElaDep, running: RunningDep) -> PlanningOut:
    """Ask ELA's Planner for the plan of this task, as far as it goes (M14.2, ADR 0058).

    Re-entrant, like ``run``: the first call creates the planning task and walks it to its
    question; after the yes, the next call — or a ``run`` of the planning task — makes the call,
    and the plan is validated and attached, the task ``QUEUED``. **Nothing is started** (decision
    H). Under the lock of ``run`` of both tasks: two gestures at once on one task are a caller's
    bug, a ``409``.
    """
    identifier = TaskId(task_id)
    child = planning_id(identifier)
    if identifier in running or child in running:
        raise TaskAlreadyRunningError(identifier)
    running.update((identifier, child))
    try:
        planning = await ela.planner.plan(identifier)
    finally:
        running.difference_update((identifier, child))
    return await planning_out(planning, ela)


async def planning_out(planning: Planning, ela: Ela) -> PlanningOut:
    return PlanningOut(
        task=await detail_of(planning.task.id, ela, planning),
        planning_task=(
            None if planning.planning_task is None else TaskOut.of(planning.planning_task)
        ),
        outcome=planning.outcome.value,
        reason=planning.reason,
        approval=None if planning.approval is None else ApprovalOut.of(planning.approval),
        no_plan=planning.no_plan,
        problems=planning.problems,
    )


async def settle_the_plan_of(task: Task, ela: Ela) -> None:
    """After a run, a no or a stop of a planning task, the task it plans is settled (M14.2): planned
    from what the model wrote, or closed with its planning task's reason. Nothing for any other."""
    if is_planning_task(task):
        assert task.parent_id is not None
        await ela.planner.settle(TaskId(task.parent_id))


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
        await settle_the_plan_of(run.task, ela)
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
    # The planning of M14.2 (ADR 0058): a stopped task stops the call that would plan it — a yes
    # given later would pay for a plan nobody can attach —, and a stopped planning task closes the
    # task it plans.
    stopped = await ela.planner.stop_planning(identifier, reason=body.reason)
    if stopped is not None:
        await close_if_free(stopped.id, ela, running)
    task = await ela.repository.get(identifier)
    await settle_the_plan_of(task, ela)
    return TaskOut.of(task)


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
