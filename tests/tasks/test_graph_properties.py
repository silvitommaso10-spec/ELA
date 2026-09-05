"""Property tests of the Task Graph on random DAGs (ADR 0009, decision 5 of M3.2).

Whatever the shape: the order respects every edge, the greedy scheduler completes everything,
a failure takes down exactly the pending descendants, the fold of the generated trail is the
simulated state, and one back edge always makes a cycle that is found and reported.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ela.domain import StepId, StepState, TaskEvent, TaskEventId, TaskEventType, TaskStep
from ela.tasks.errors import CyclicDependencyError
from ela.tasks.graph import TERMINAL_STEP_STATES, TaskGraph
from tests.domain.examples import NOW, TASK_ID
from tests.tasks.graphs import cyclic_dags, dags

P = StepState


class Simulation:
    """Drives a graph through start/complete/fail, keeping states and the trail it would leave."""

    def __init__(self, steps: tuple[TaskStep, ...]) -> None:
        self.graph = TaskGraph(steps)
        self.states: dict[StepId, StepState] = dict.fromkeys(self.graph.steps, P.PENDING)
        self.trail: list[TaskEvent] = []

    def _record(self, kind: TaskEventType, step_id: StepId, state: StepState) -> None:
        self.states[step_id] = state
        self.trail.append(
            TaskEvent(
                id=TaskEventId(UUID(int=len(self.trail) + 1)),
                created_at=NOW,
                task_id=TASK_ID,
                event_type=kind,
                step_id=step_id,
            )
        )

    def start(self, step_id: StepId) -> None:
        assert step_id in self.graph.ready(self.states)
        self._record(TaskEventType.STEP_STARTED, step_id, P.RUNNING)

    def complete(self, step_id: StepId) -> None:
        assert self.states[step_id] is P.RUNNING
        self._record(TaskEventType.STEP_COMPLETED, step_id, P.COMPLETED)

    def fail(self, step_id: StepId) -> None:
        assert self.states[step_id] is P.RUNNING
        self._record(TaskEventType.STEP_FAILED, step_id, P.FAILED)
        for dependent in self.graph.to_cancel(step_id, self.states):
            self._record(TaskEventType.STEP_CANCELLED, dependent, P.CANCELLED)

    def check_invariants(self) -> None:
        graph, states = self.graph, self.states
        for step_id in graph.order:
            if states[step_id] in (P.RUNNING, P.COMPLETED):
                assert all(states[d] is P.COMPLETED for d in graph.dependencies(step_id))
            if states[step_id] in (P.FAILED, P.CANCELLED):
                assert all(states[d] is P.CANCELLED for d in graph.descendants(step_id))
        ready = graph.ready(states)
        assert list(ready) == [s for s in graph.order if s in ready]  # topological order
        for step_id in ready:
            assert states[step_id] is P.PENDING
            assert all(states[d] is P.COMPLETED for d in graph.dependencies(step_id))
        doomed = {
            d
            for s in graph.order
            if states[s] in (P.FAILED, P.CANCELLED)
            for d in graph.descendants(s)
        }
        assert not (set(ready) & doomed)
        assert graph.states(self.trail) == states


@given(steps=dags())
@settings(max_examples=200, deadline=None)
def test_the_order_is_a_permutation_that_respects_every_edge(steps: tuple[TaskStep, ...]) -> None:
    graph = TaskGraph(steps)
    order = graph.order
    assert sorted(order, key=str) == sorted((s.id for s in steps), key=str)
    position = {step_id: index for index, step_id in enumerate(order)}
    for s in steps:
        for dependency in s.dependencies:
            assert position[dependency] < position[s.id]
    assert TaskGraph(steps).order == order  # deterministic
    for s in steps:
        for d in graph.descendants(s.id):
            assert position[s.id] < position[d]


@given(steps=dags())
@settings(max_examples=200, deadline=None)
def test_the_greedy_scheduler_completes_every_dag(steps: tuple[TaskStep, ...]) -> None:
    sim = Simulation(steps)
    rounds = 0
    while not sim.graph.is_complete(sim.states):
        ready = sim.graph.ready(sim.states)
        assert ready, "not complete, nothing failed, yet nothing is ready"
        for step_id in ready:
            sim.start(step_id)
        sim.check_invariants()
        for step_id in ready:
            sim.complete(step_id)
        sim.check_invariants()
        rounds += 1
        assert rounds <= len(steps)
    assert not sim.graph.is_blocked(sim.states)
    assert sim.graph.ready(sim.states) == ()
    assert sorted(
        (e.step_id for e in sim.trail if e.event_type is TaskEventType.STEP_STARTED), key=str
    ) == sorted((s.id for s in steps), key=str)


@given(steps=dags(), choices=st.lists(st.integers(min_value=0, max_value=10**6), max_size=40))
@settings(max_examples=200, deadline=None)
def test_random_walks_keep_the_invariants(steps: tuple[TaskStep, ...], choices: list[int]) -> None:
    """Start, complete or fail a random legal step at every turn; the invariants never break."""
    sim = Simulation(steps)
    for choice in choices:
        ready = sim.graph.ready(sim.states)
        running = [s for s in sim.graph.order if sim.states[s] is P.RUNNING]
        moves = [("start", s) for s in ready] + [
            (k, s) for s in running for k in ("complete", "fail")
        ]
        if not moves:
            break
        kind, step_id = moves[choice % len(moves)]
        getattr(sim, kind)(step_id)
        sim.check_invariants()
    for step_id, state in sim.states.items():
        if state is P.CANCELLED:
            # Every cancelled step has a failed ancestor: nothing is cancelled for no reason.
            failed = {s for s in sim.graph.order if sim.states[s] is P.FAILED}
            assert any(step_id in sim.graph.descendants(f) for f in failed)
    assert not (sim.graph.is_complete(sim.states) and sim.graph.is_blocked(sim.states))


@given(steps=dags(), choice=st.integers(min_value=0, max_value=10**6))
@settings(max_examples=200, deadline=None)
def test_a_failure_takes_down_exactly_the_pending_descendants(
    steps: tuple[TaskStep, ...], choice: int
) -> None:
    sim = Simulation(steps)
    sources = sim.graph.ready(sim.states)
    if not sources:
        return
    victim = sources[choice % len(sources)]
    sim.start(victim)
    before = dict(sim.states)
    sim.fail(victim)
    for step_id in sim.graph.order:
        if step_id == victim:
            assert sim.states[step_id] is P.FAILED
        elif step_id in sim.graph.descendants(victim):
            assert sim.states[step_id] is P.CANCELLED
        else:
            assert sim.states[step_id] is before[step_id]
    sim.check_invariants()
    assert sim.graph.is_blocked(sim.states)
    assert sim.graph.to_cancel(victim, sim.states) == ()


@given(case=cyclic_dags())
@settings(max_examples=200, deadline=None)
def test_one_back_edge_is_always_a_cycle_and_the_cycle_is_real(
    case: tuple[tuple[TaskStep, ...], StepId, StepId],
) -> None:
    steps, ancestor, descendant = case
    with pytest.raises(CyclicDependencyError) as excinfo:
        TaskGraph(steps)
    cycle = excinfo.value.cycle
    assert len(cycle) >= 2 and len(set(cycle)) == len(cycle)
    by_id = {s.id: s for s in steps}
    for current, following in zip(cycle, (*cycle[1:], cycle[0]), strict=True):
        assert following in by_id[current].dependencies
    # The DAG had no cycle, so every cycle goes through the one edge that was added.
    assert ancestor in cycle and descendant in cycle


@given(steps=dags(), choices=st.lists(st.integers(min_value=0, max_value=10**6), max_size=40))
@settings(max_examples=100, deadline=None)
def test_terminal_steps_never_move_again(steps: tuple[TaskStep, ...], choices: list[int]) -> None:
    sim = Simulation(steps)
    frozen: dict[StepId, StepState] = {}
    for choice in choices:
        ready = sim.graph.ready(sim.states)
        running = [s for s in sim.graph.order if sim.states[s] is P.RUNNING]
        moves = [("start", s) for s in ready] + [
            (k, s) for s in running for k in ("complete", "fail")
        ]
        if not moves:
            break
        kind, step_id = moves[choice % len(moves)]
        getattr(sim, kind)(step_id)
        for s, state in sim.states.items():
            if s in frozen:
                assert sim.states[s] is frozen[s]
            elif state in TERMINAL_STEP_STATES:
                frozen[s] = state
