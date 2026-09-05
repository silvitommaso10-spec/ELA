"""The Task Graph on hand-made shapes: validation, order, readiness, propagation, the fold.

The random shapes are in ``test_graph_properties.py``; here every rule of ADR 0009 has the one
small case that shows it.
"""

from __future__ import annotations

from uuid import UUID

import pytest

from ela.domain import (
    StepId,
    StepState,
    TaskEvent,
    TaskEventId,
    TaskEventType,
    TaskState,
)
from ela.tasks.errors import (
    CyclicDependencyError,
    GraphError,
    IllegalStepTransitionError,
    InvalidGraphError,
    TaskError,
    UnknownStepError,
)
from ela.tasks.graph import (
    STEP_EVENTS,
    STEP_TRANSITIONS,
    TERMINAL_STEP_STATES,
    GraphState,
    TaskGraph,
    can_step_transition,
)
from tests.domain.examples import NOW, TASK_ID, TASK_PLAN
from tests.tasks.graphs import chain, diamond, sid, step

P = StepState


def event(kind: TaskEventType, step_id: StepId | None, tail: int) -> TaskEvent:
    return TaskEvent(
        id=TaskEventId(UUID(int=tail)),
        created_at=NOW,
        task_id=TASK_ID,
        event_type=kind,
        step_id=step_id,
    )


def started(step_id: StepId, tail: int = 1) -> TaskEvent:
    return event(TaskEventType.STEP_STARTED, step_id, tail)


def completed(step_id: StepId, tail: int = 2) -> TaskEvent:
    return event(TaskEventType.STEP_COMPLETED, step_id, tail)


# --------------------------------------------------------------------------------------
# The tables
# --------------------------------------------------------------------------------------


def test_terminal_step_states_have_no_exit() -> None:
    assert {P.COMPLETED, P.FAILED, P.CANCELLED} == TERMINAL_STEP_STATES
    for state in TERMINAL_STEP_STATES:
        assert STEP_TRANSITIONS[state] == frozenset()


def test_the_table_is_total_and_has_no_self_transition() -> None:
    assert set(STEP_TRANSITIONS) == set(StepState)
    for state, targets in STEP_TRANSITIONS.items():
        assert state not in targets


def test_the_legal_moves_are_the_four_of_adr_0009() -> None:
    legal = {(a, b) for a, targets in STEP_TRANSITIONS.items() for b in targets}
    assert legal == {
        (P.PENDING, P.RUNNING),
        (P.PENDING, P.CANCELLED),
        (P.RUNNING, P.COMPLETED),
        (P.RUNNING, P.FAILED),
    }
    assert can_step_transition(P.PENDING, P.RUNNING)
    assert not can_step_transition(P.PENDING, P.COMPLETED)
    assert not can_step_transition(P.RUNNING, P.CANCELLED)


def test_every_step_event_type_moves_a_step_somewhere_legal() -> None:
    assert set(STEP_EVENTS) == {t for t in TaskEventType if t.name.startswith("STEP_")}
    for target in STEP_EVENTS.values():
        assert any(can_step_transition(source, target) for source in StepState)


def test_the_tables_are_immutable() -> None:
    with pytest.raises(TypeError):
        STEP_TRANSITIONS[P.PENDING] = frozenset()  # type: ignore[index]
    with pytest.raises(TypeError):
        STEP_EVENTS[TaskEventType.NOTE] = P.RUNNING  # type: ignore[index]


def test_graph_errors_are_task_errors() -> None:
    for error in (
        InvalidGraphError,
        CyclicDependencyError,
        UnknownStepError,
        IllegalStepTransitionError,
    ):
        assert issubclass(error, GraphError) and issubclass(error, TaskError)


# --------------------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------------------


def test_an_empty_plan_is_a_graph_with_no_steps() -> None:
    graph = TaskGraph(())
    assert len(graph) == 0 and graph.order == ()
    assert graph.states(()) == {}
    assert graph.ready({}) == ()
    assert graph.is_complete({}) and not graph.is_blocked({})


def test_the_example_plan_is_a_valid_graph() -> None:
    graph = TaskGraph.from_plan(TASK_PLAN)
    assert graph.order == tuple(s.id for s in TASK_PLAN.steps)
    assert graph.dependencies(TASK_PLAN.steps[1].id) == {TASK_PLAN.steps[0].id}
    assert graph.dependents(TASK_PLAN.steps[0].id) == {TASK_PLAN.steps[1].id}


def test_a_self_dependency_is_a_cycle_of_length_one() -> None:
    with pytest.raises(CyclicDependencyError) as excinfo:
        TaskGraph((step(0, sid(0)),))
    assert excinfo.value.cycle == (sid(0),)
    assert str(sid(0)) in str(excinfo.value)


def test_a_two_cycle_is_rejected_and_reported() -> None:
    with pytest.raises(CyclicDependencyError) as excinfo:
        TaskGraph((step(0, sid(1)), step(1, sid(0))))
    assert set(excinfo.value.cycle) == {sid(0), sid(1)}


def test_a_three_cycle_behind_a_valid_prefix_is_rejected() -> None:
    steps = (step(0), step(1, sid(0), sid(3)), step(2, sid(1)), step(3, sid(2)))
    with pytest.raises(CyclicDependencyError) as excinfo:
        TaskGraph(steps)
    assert set(excinfo.value.cycle) == {sid(1), sid(2), sid(3)}


def test_an_unknown_dependency_is_rejected() -> None:
    with pytest.raises(InvalidGraphError, match="not in the plan"):
        TaskGraph((step(0, sid(9)),))


def test_a_duplicate_step_id_is_rejected() -> None:
    with pytest.raises(InvalidGraphError, match="appears twice"):
        TaskGraph((step(0), step(0)))


def test_a_dependency_listed_twice_is_rejected() -> None:
    with pytest.raises(InvalidGraphError, match="twice"):
        TaskGraph((step(0), step(1, sid(0), sid(0))))


def test_an_unknown_step_is_refused_everywhere() -> None:
    graph = TaskGraph(chain(2))
    for query in (graph.step, graph.dependencies, graph.dependents, graph.descendants):
        with pytest.raises(UnknownStepError):
            query(sid(9))
    assert sid(9) not in graph and sid(0) in graph


# --------------------------------------------------------------------------------------
# Order and structure
# --------------------------------------------------------------------------------------


def test_a_plan_in_topological_order_keeps_its_order() -> None:
    graph = TaskGraph(diamond())
    assert graph.order == (sid(0), sid(1), sid(2), sid(3))


def test_ties_are_broken_by_plan_order() -> None:
    steps = diamond()
    reordered = (steps[3], steps[2], steps[1], steps[0])
    graph = TaskGraph(reordered)
    assert graph.order == (sid(0), sid(2), sid(1), sid(3))
    assert tuple(graph.steps) == tuple(s.id for s in reordered)


def test_descendants_are_transitive_and_ordered() -> None:
    graph = TaskGraph(diamond())
    assert graph.descendants(sid(0)) == (sid(1), sid(2), sid(3))
    assert graph.descendants(sid(1)) == (sid(3),)
    assert graph.descendants(sid(3)) == ()
    assert graph.dependents(sid(0)) == {sid(1), sid(2)}


# --------------------------------------------------------------------------------------
# The fold: from the trail to the states
# --------------------------------------------------------------------------------------


def test_a_step_never_named_is_pending_and_other_events_are_ignored() -> None:
    graph = TaskGraph(chain(2))
    trail = (
        event(TaskEventType.STATE_CHANGED, None, 1),
        event(TaskEventType.HEARTBEAT, None, 2),
        event(TaskEventType.NOTE, sid(0), 3),
        started(sid(0), 4),
    )
    assert graph.states(trail) == {sid(0): P.RUNNING, sid(1): P.PENDING}


def test_the_fold_follows_the_events() -> None:
    graph = TaskGraph(diamond())
    trail = (
        started(sid(0), 1),
        completed(sid(0), 2),
        started(sid(1), 3),
        event(TaskEventType.STEP_FAILED, sid(1), 4),
        event(TaskEventType.STEP_CANCELLED, sid(3), 5),
    )
    states = graph.states(trail)
    assert states == {sid(0): P.COMPLETED, sid(1): P.FAILED, sid(2): P.PENDING, sid(3): P.CANCELLED}
    with pytest.raises(TypeError):
        states[sid(2)] = P.RUNNING  # type: ignore[index]


def test_a_completed_without_a_started_is_an_illegal_step_transition() -> None:
    graph = TaskGraph(chain(1))
    with pytest.raises(IllegalStepTransitionError) as excinfo:
        graph.states((completed(sid(0)),))
    assert (excinfo.value.step_id, excinfo.value.current, excinfo.value.requested) == (
        sid(0),
        "PENDING",
        "COMPLETED",
    )


def test_a_second_started_is_an_illegal_step_transition() -> None:
    graph = TaskGraph(chain(1))
    with pytest.raises(IllegalStepTransitionError, match="RUNNING to RUNNING"):
        graph.states((started(sid(0), 1), started(sid(0), 2)))


def test_a_step_event_for_an_unknown_step_is_refused() -> None:
    graph = TaskGraph(chain(1))
    with pytest.raises(UnknownStepError) as excinfo:
        graph.states((started(sid(9)),))
    assert excinfo.value.step_id == sid(9)


def test_a_step_event_without_a_step_id_is_refused() -> None:
    graph = TaskGraph(chain(1))
    with pytest.raises(UnknownStepError, match="without step_id"):
        graph.states((started(None),))  # type: ignore[arg-type]


# --------------------------------------------------------------------------------------
# Ready, to_cancel, complete, blocked
# --------------------------------------------------------------------------------------


def test_ready_is_the_sources_when_everything_is_pending() -> None:
    graph = TaskGraph(diamond())
    assert graph.ready(graph.states(())) == (sid(0),)
    forest = TaskGraph((step(2), step(0), step(1, sid(0))))
    assert forest.ready(forest.states(())) == (sid(2), sid(0))


def test_ready_needs_every_dependency_completed() -> None:
    graph = TaskGraph(diamond())
    states = dict(graph.states((started(sid(0), 1), completed(sid(0), 2))))
    assert graph.ready(states) == (sid(1), sid(2))
    states[sid(1)] = P.RUNNING
    assert graph.ready(states) == (sid(2),)
    states[sid(1)] = P.COMPLETED
    assert graph.ready(states) == (sid(2),)  # step 3 still waits for 2
    states[sid(2)] = P.COMPLETED
    assert graph.ready(states) == (sid(3),)


def test_to_cancel_is_the_pending_descendants_only() -> None:
    graph = TaskGraph(diamond())
    states = {sid(0): P.FAILED, sid(1): P.PENDING, sid(2): P.CANCELLED, sid(3): P.PENDING}
    assert graph.to_cancel(sid(0), states) == (sid(1), sid(3))
    assert graph.to_cancel(sid(3), states) == ()


def test_complete_and_blocked() -> None:
    graph = TaskGraph(chain(2))
    assert not graph.is_complete({sid(0): P.COMPLETED, sid(1): P.PENDING})
    assert graph.is_complete({sid(0): P.COMPLETED, sid(1): P.COMPLETED})
    assert not graph.is_blocked({sid(0): P.COMPLETED, sid(1): P.RUNNING})
    assert graph.is_blocked({sid(0): P.FAILED, sid(1): P.CANCELLED})
    assert graph.is_blocked({sid(0): P.COMPLETED, sid(1): P.CANCELLED})


def test_graph_state_delegates_to_the_graph() -> None:
    graph = TaskGraph(diamond())
    state = GraphState(graph, graph.states((started(sid(0), 1), completed(sid(0), 2))))
    assert state.ready() == graph.ready(state.states) == (sid(1), sid(2))
    assert state.to_cancel(sid(0)) == (sid(1), sid(2), sid(3))
    assert not state.is_complete and not state.is_blocked


def test_step_states_are_not_task_states() -> None:
    """Same names, different enums: a step state is never a task state."""
    assert P.COMPLETED is not TaskState.COMPLETED
    assert not isinstance(P.COMPLETED, TaskState)
    assert [s.value for s in StepState] == [
        "PENDING",
        "RUNNING",
        "COMPLETED",
        "FAILED",
        "CANCELLED",
    ]
