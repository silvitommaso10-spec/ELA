"""The stop after the k-th write: derived, not a list of windows (M6.3c, proposal 4 of the SPEC).

The first draft of the SPEC listed the windows in which a stop left a step RUNNING or made ``run``
raise, and the re-read found two more it did not have (P9, P10). This test does not list: the
stores of the world count their writes — the task's row, its trail, the audit, the results, the
approvals, the grants, the assignments —, and for every plan of :data:`PLANS` and every ``k`` from
1 to the number of writes of the run without a stop, a new world in which the stop lands right
after the k-th.

**Right after**, as the world allows it: at the first call to a store after the k-th write in which
the engine does not hold the task's lock. A write inside an engine operation is under that lock,
and a real «ferma» would wait for it there; so it waits here too, and lands as soon as the operation
has released it. The stop is the engine's own ``cancel``, as the route of the «ferma» calls it.

It asserts: ``run`` returns and does not raise; the outcome is ``cancelled`` — with a reason that is
never empty, and the step in progress said —, or the final state the task had already reached;
and then the invariant of decision 1: no step RUNNING in a task that has ended. The three
exceptions of criterion 2 need a tool that has not returned or a node's claim, and ``run`` returns
only after its tool, and no node claims here.

It covers the writes of the world, not the ``await`` of its reads: the SPEC says so.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import pytest

from ela.domain import (
    Halt,
    PrivacyLevel,
    StepState,
    TaskId,
    TaskState,
)
from ela.executive import OUTCOMES, Run, RunOutcome
from ela.ports import StopPoint
from ela.tasks.engine import TERMINAL_STATES, TaskEngine
from ela.tasks.errors import TaskError
from ela.testing.fakes import (
    FakeApprovalStore,
    FakeAssignmentStore,
    FakeAuditLog,
    FakeAuthorizationStore,
    FakeExecutionResultStore,
    FakeTaskRepository,
    FakeTool,
)
from tests.executive.support import World, fake_tools, world
from tests.permissions.support import ECHO, GUARDED_ECHO, NOTE

WRITES = frozenset(
    {
        "add",
        "add_plan",
        "append",
        "append_event",
        "claim",
        "consume",
        "cut_short",
        "deliver",
        "expire",
        "grant",
        "renew",
        "respond",
        "save",
        "withdraw",
    }
)
"""The methods of the stores that write: everything else they offer reads."""
STOP_WORDS = "ferma"


@dataclass
class Stopper:
    """Counts the writes of one run and, after the k-th, stops the task through the engine."""

    k: int | None
    engine: TaskEngine | None = None
    task_id: TaskId | None = None
    writes: int = 0
    due: bool = False
    applied: bool = False
    too_late: bool = False
    busy: bool = False

    @property
    def counting(self) -> bool:
        return self.task_id is not None and not self.busy

    async def wrote(self) -> None:
        self.writes += 1
        if self.writes == self.k:
            self.due = True
        await self.land()

    async def land(self) -> None:
        if not self.due or self.applied or self.too_late:
            return
        assert self.engine is not None and self.task_id is not None
        lock = self.engine._locks.get(self.task_id)  # noqa: SLF001 — is an operation under way?
        if lock is not None and lock.locked():
            return
        self.busy = True
        try:
            await self.engine.cancel(self.task_id, reason=STOP_WORDS)
            self.applied = True
        except TaskError:
            self.too_late = True  # the task had already ended: the stop came after the end
        finally:
            self.busy = False


class Watched:
    """A store whose every call is a place where a due stop may land, and whose writes count."""

    def __init__(self, inner: object, stopper: Stopper) -> None:
        self._inner = inner
        self._stopper = stopper

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self._inner, name)
        if not inspect.iscoroutinefunction(attribute):
            return attribute
        stopper = self._stopper

        async def watched(*args: Any, **kwargs: Any) -> Any:
            if stopper.counting:
                await stopper.land()
            answer = await attribute(*args, **kwargs)
            if name in WRITES and stopper.counting:
                await stopper.wrote()
            return answer

        return watched


def watched_world(stopper: Stopper, **options: Any) -> World:
    w = world(
        repository=Watched(FakeTaskRepository(), stopper),  # type: ignore[arg-type]
        audit=Watched(FakeAuditLog(), stopper),  # type: ignore[arg-type]
        results=Watched(FakeExecutionResultStore(), stopper),  # type: ignore[arg-type]
        approvals=Watched(FakeApprovalStore(), stopper),  # type: ignore[arg-type]
        store=Watched(FakeAuthorizationStore(), stopper),  # type: ignore[arg-type]
        assignment_store=Watched(FakeAssignmentStore(), stopper),  # type: ignore[arg-type]
        **options,
    )
    stopper.engine = w.engine
    return w


# ----------------------------------------------------------------------------------------
# The plans: one step, two steps, a step that fails, one that asks, one that goes to a node
# ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Plan:
    name: str
    prepare: Callable[[World], Awaitable[TaskId]]
    options: dict[str, Any] = field(default_factory=dict)
    tools: Callable[[World], list[FakeTool]] | None = None


async def _one(w: World) -> TaskId:
    task, _ = await w.queued(ECHO.id)
    return task.id


async def _two(w: World) -> TaskId:
    task, _ = await w.queued(ECHO.id, NOTE.id)
    return task.id


async def _asks(w: World) -> TaskId:
    task, _ = await w.queued(GUARDED_ECHO.id)
    return task.id


async def _node(w: World) -> TaskId:
    await w.remote()
    task, _ = await w.queued(ECHO.id, max_privacy=PrivacyLevel.TRUSTED)
    return task.id


def _with_a_point(w: World) -> list[FakeTool]:
    """The echo of the world, declaring a point and a STARTED record: the two things a stop reads
    in the call — whether the tool passed its point, and what the store holds."""
    tools = fake_tools(w.clock, w.ids)
    tools[ECHO.id] = FakeTool(
        ECHO.id,
        w.clock,
        w.ids,
        name=f"fake-{ECHO.id}",
        output={"ok": True},
        idempotent=False,
        stop_point=StopPoint(here="the point", on_a_node=None),
    )
    return list(tools.values())


PLANS = (
    Plan("one-step", _one),
    Plan("two-steps", _two),
    Plan("a-step-that-fails", _one, options={"failing": frozenset({ECHO.id})}),
    Plan("a-step-that-asks", _asks),
    Plan("a-step-on-a-node", _node),
    Plan("a-step-with-a-point-and-a-started-record", _one, tools=_with_a_point),
)


async def a_run(plan: Plan, k: int | None) -> tuple[World, Stopper, TaskId, Run]:
    stopper = Stopper(k)
    options = dict(plan.options)
    if plan.tools is not None:
        options["tools"] = plan.tools(world())
    w = watched_world(stopper, **options)
    task_id = await plan.prepare(w)
    stopper.task_id = task_id
    run = await w.runner.run(task_id)
    stopper.task_id = None
    return w, stopper, task_id, run


async def running_steps(w: World, task_id: TaskId) -> list[str]:
    graph = await w.engine.graph(task_id)
    return [str(step) for step, state in graph.states.items() if state is StepState.RUNNING]


@pytest.mark.parametrize("plan", PLANS, ids=lambda plan: plan.name)
async def test_a_stop_after_any_write_of_a_run_is_an_outcome_and_leaves_nothing_running(
    plan: Plan,
) -> None:
    _, counted, _, baseline = await a_run(plan, None)
    assert counted.writes > 0
    assert baseline.outcome is not RunOutcome.CANCELLED

    seen: set[RunOutcome] = set()
    for k in range(1, counted.writes + 1):
        w, stopper, task_id, run = await a_run(plan, k)
        task = await w.task(task_id)
        where = f"{plan.name}, stopped after write {k} of {counted.writes}"

        assert run.task.state is task.state, where
        assert run.outcome is OUTCOMES[task.state], where
        if stopper.applied:
            assert task.state is TaskState.CANCELLED, where
            assert run.outcome is RunOutcome.CANCELLED, where
            assert run.reason, where
            assert STOP_WORDS in run.reason, where
        else:
            assert run.outcome is baseline.outcome, where
        if task.state in TERMINAL_STATES:
            assert await running_steps(w, task_id) == [], where
        if run.outcome is RunOutcome.CANCELLED and run.halt is not None:
            assert run.halt is not Halt.FINISHING, where
        seen.add(run.outcome)

    assert RunOutcome.CANCELLED in seen, "no k stopped the task: the sweep proved nothing"


async def test_the_sweep_counts_the_writes_of_the_run_and_not_of_the_preparation() -> None:
    """The negative case of the counter: a stop due after the last write of the run lands
    nowhere, and the run is the one without a stop."""
    _, counted, _, baseline = await a_run(PLANS[0], None)
    w, stopper, task_id, run = await a_run(PLANS[0], counted.writes + 1)

    assert not stopper.due and not stopper.applied
    assert run.outcome is baseline.outcome is RunOutcome.COMPLETED
    assert (await w.task(task_id)).state is TaskState.COMPLETED


async def test_a_stop_that_comes_after_the_end_is_too_late_and_changes_nothing() -> None:
    """The last write of a completed run is the audit of TASK_COMPLETED: a stop due there finds
    the task ended, and the engine refuses it."""
    _, counted, _, _ = await a_run(PLANS[0], None)
    w, stopper, task_id, run = await a_run(PLANS[0], counted.writes)

    assert stopper.due
    assert run.outcome is RunOutcome.COMPLETED
    w_task = await w.task(task_id)
    assert w_task.state is TaskState.COMPLETED
    stopper.task_id = task_id
    await stopper.land()
    assert stopper.too_late and not stopper.applied
