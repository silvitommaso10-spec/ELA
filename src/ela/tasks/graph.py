"""Task Graph (spec §15): the dependencies between the steps of a plan, and where each step stands.

§13 gives every :class:`~ela.domain.TaskStep` its ``dependencies``; §15 wants the state of the
work to belong to ELA, not to a node. This module is the pure half of both (ADR 0009):

* :class:`TaskGraph` validates that the steps of a plan form a DAG — unique ids, dependencies on
  other steps of the same plan, no cycle — and gives a deterministic topological ``order``.
* The state of a step is not stored anywhere: it is **folded from the trail** of the task
  (:meth:`TaskGraph.states`), from the ``STEP_*`` events with a ``step_id``. The trail is
  persisted and belongs to the task, so the state of the graph is persisted and independent of
  any device by construction.
* :meth:`TaskGraph.ready` says which steps may run (PENDING, every dependency COMPLETED);
  :meth:`TaskGraph.to_cancel` says which steps a failure takes down with it (every PENDING
  descendant).

Nothing here does I/O or writes an event: who records that a step started, completed or failed
is the Task Engine (:mod:`ela.tasks.engine`), the only writer of ``STEP_*`` events (rule 11).
Like the state machine of M1.2, this module applies tables and nothing else: when the trail says
something the table forbids, the answer is an error, not a guess (§33).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Final, NamedTuple

from ela.domain import StepId, StepState, TaskEvent, TaskEventType, TaskPlan, TaskStep
from ela.tasks.errors import (
    CyclicDependencyError,
    IllegalStepTransitionError,
    InvalidGraphError,
    UnknownStepError,
)

__all__ = [
    "STEP_EVENTS",
    "STEP_TRANSITIONS",
    "TERMINAL_STEP_STATES",
    "GraphState",
    "StepStates",
    "TaskGraph",
    "can_step_transition",
]

_S = StepState

TERMINAL_STEP_STATES: Final[frozenset[StepState]] = frozenset(
    {_S.COMPLETED, _S.FAILED, _S.CANCELLED}
)
"""States a step never leaves. A retry of a failed step is a new step, never the same one."""

STEP_TRANSITIONS: Final[Mapping[StepState, frozenset[StepState]]] = MappingProxyType(
    {
        _S.PENDING: frozenset({_S.RUNNING, _S.CANCELLED}),
        _S.RUNNING: frozenset({_S.COMPLETED, _S.FAILED}),
        _S.COMPLETED: frozenset(),
        _S.FAILED: frozenset(),
        _S.CANCELLED: frozenset(),
    }
)
"""The legal moves of a step (ADR 0009), one row per state, total by construction.

PENDING → CANCELLED is the propagation of a failure; RUNNING → CANCELLED does not exist because
a step only starts once its dependencies are COMPLETED, which is terminal: nothing a running step
depends on can fail afterwards. The Mermaid diagram of ADR 0009 is checked against this table.
"""

STEP_EVENTS: Final[Mapping[TaskEventType, StepState]] = MappingProxyType(
    {
        TaskEventType.STEP_STARTED: _S.RUNNING,
        TaskEventType.STEP_COMPLETED: _S.COMPLETED,
        TaskEventType.STEP_FAILED: _S.FAILED,
        TaskEventType.STEP_CANCELLED: _S.CANCELLED,
    }
)
"""Which trail event moves a step where: the fold of :meth:`TaskGraph.states` reads this."""

StepStates = Mapping[StepId, StepState]
"""The state of every step of a plan, keyed by step id."""


def can_step_transition(current: StepState, new_state: StepState) -> bool:
    """Whether the table allows ``current -> new_state``."""
    return new_state in STEP_TRANSITIONS[current]


class TaskGraph:
    """The steps of one plan as a validated DAG, in a deterministic topological order.

    Immutable once built. Construction raises :class:`~ela.tasks.errors.InvalidGraphError` for a
    duplicate step id, a dependency on a step that is not in the plan, or a dependency listed
    twice, and :class:`~ela.tasks.errors.CyclicDependencyError` for a cycle (a self-dependency
    is a cycle of length one). The order is Kahn's algorithm with ties broken by the position in
    the plan, so a plan that is already in topological order keeps its order, and the same plan
    always gives the same order.
    """

    __slots__ = ("_dependencies", "_dependents", "_order", "_steps")

    def __init__(self, steps: Iterable[TaskStep]) -> None:
        by_id: dict[StepId, TaskStep] = {}
        for step in steps:
            if step.id in by_id:
                raise InvalidGraphError(f"step {step.id} appears twice in the plan")
            by_id[step.id] = step
        dependencies: dict[StepId, frozenset[StepId]] = {}
        dependents: dict[StepId, set[StepId]] = {step_id: set() for step_id in by_id}
        for step_id, step in by_id.items():
            seen: set[StepId] = set()
            for dependency in step.dependencies:
                if dependency not in by_id:
                    raise InvalidGraphError(
                        f"step {step_id} depends on {dependency}, which is not in the plan"
                    )
                if dependency in seen:
                    raise InvalidGraphError(f"step {step_id} lists {dependency} twice")
                seen.add(dependency)
                if dependency != step_id:
                    dependents[dependency].add(step_id)
            dependencies[step_id] = frozenset(seen)
        self._steps: Mapping[StepId, TaskStep] = MappingProxyType(by_id)
        self._dependencies: Mapping[StepId, frozenset[StepId]] = MappingProxyType(dependencies)
        self._dependents: Mapping[StepId, frozenset[StepId]] = MappingProxyType(
            {step_id: frozenset(found) for step_id, found in dependents.items()}
        )
        self._order = self._topological_order()

    @classmethod
    def from_plan(cls, plan: TaskPlan) -> TaskGraph:
        """The graph of a plan's steps."""
        return cls(plan.steps)

    # ----------------------------------------------------------------------------------
    # Structure
    # ----------------------------------------------------------------------------------

    @property
    def steps(self) -> Mapping[StepId, TaskStep]:
        """The steps by id, in plan order."""
        return self._steps

    @property
    def order(self) -> tuple[StepId, ...]:
        """Every step, dependencies before dependents, ties in plan order."""
        return self._order

    def __len__(self) -> int:
        return len(self._steps)

    def __contains__(self, step_id: object) -> bool:
        return step_id in self._steps

    def step(self, step_id: StepId) -> TaskStep:
        """The step with this id; :class:`~ela.tasks.errors.UnknownStepError` if none."""
        try:
            return self._steps[step_id]
        except KeyError:
            raise UnknownStepError(step_id) from None

    def dependencies(self, step_id: StepId) -> frozenset[StepId]:
        """The steps ``step_id`` waits for (direct)."""
        self.step(step_id)
        return self._dependencies[step_id]

    def dependents(self, step_id: StepId) -> frozenset[StepId]:
        """The steps that wait for ``step_id`` (direct)."""
        self.step(step_id)
        return self._dependents[step_id]

    def descendants(self, step_id: StepId) -> tuple[StepId, ...]:
        """Every step that transitively waits for ``step_id``, in topological order."""
        self.step(step_id)
        reached: set[StepId] = set()
        frontier = deque([step_id])
        while frontier:
            for dependent in self._dependents[frontier.popleft()]:
                if dependent not in reached:
                    reached.add(dependent)
                    frontier.append(dependent)
        return tuple(step for step in self._order if step in reached)

    def _topological_order(self) -> tuple[StepId, ...]:
        """Kahn's algorithm; a leftover means a cycle, which is then located and reported."""
        position = {step_id: index for index, step_id in enumerate(self._steps)}
        remaining = {step_id: len(deps) for step_id, deps in self._dependencies.items()}
        ready = sorted(
            (step_id for step_id, count in remaining.items() if count == 0),
            key=position.__getitem__,
        )
        order: list[StepId] = []
        while ready:
            current = ready.pop(0)
            order.append(current)
            released: list[StepId] = []
            for dependent in self._dependents[current]:
                remaining[dependent] -= 1
                if remaining[dependent] == 0:
                    released.append(dependent)
            ready = sorted([*ready, *released], key=position.__getitem__)
        if len(order) != len(self._steps):
            raise CyclicDependencyError(self._find_cycle(set(remaining) - set(order)))
        return tuple(order)

    def _find_cycle(self, candidates: set[StepId]) -> tuple[StepId, ...]:
        """One cycle among the steps Kahn's algorithm could not order.

        Every candidate still has an unresolved dependency among the candidates, so following
        dependencies from any of them (in plan order, for determinism) must revisit a step.
        """
        position = {step_id: index for index, step_id in enumerate(self._steps)}
        start = min(candidates, key=position.__getitem__)
        path: list[StepId] = []
        current = start
        while current not in path:
            path.append(current)
            current = min(
                (d for d in self._dependencies[current] if d in candidates),
                key=position.__getitem__,
            )
        return tuple(path[path.index(current) :])

    # ----------------------------------------------------------------------------------
    # State
    # ----------------------------------------------------------------------------------

    def states(self, events: Iterable[TaskEvent]) -> StepStates:
        """The state of every step, folded from the ``STEP_*`` events of a trail.

        Events of other types are ignored. A ``STEP_*`` event without ``step_id``, or with one
        the plan does not contain, raises :class:`~ela.tasks.errors.UnknownStepError`; one that
        moves a step against :data:`STEP_TRANSITIONS` raises
        :class:`~ela.tasks.errors.IllegalStepTransitionError`. A step never named is PENDING.
        """
        states: dict[StepId, StepState] = dict.fromkeys(self._steps, _S.PENDING)
        for event in events:
            target = STEP_EVENTS.get(event.event_type)
            if target is None:
                continue
            if event.step_id is None or event.step_id not in states:
                raise UnknownStepError(event.step_id)
            current = states[event.step_id]
            if not can_step_transition(current, target):
                raise IllegalStepTransitionError(event.step_id, current.value, target.value)
            states[event.step_id] = target
        return MappingProxyType(states)

    def ready(self, states: StepStates) -> tuple[StepId, ...]:
        """The steps that may run now: PENDING, every dependency COMPLETED; topological order."""
        return tuple(
            step_id
            for step_id in self._order
            if states[step_id] is _S.PENDING
            and all(states[dep] is _S.COMPLETED for dep in self._dependencies[step_id])
        )

    def to_cancel(self, step_id: StepId, states: StepStates) -> tuple[StepId, ...]:
        """The PENDING descendants of ``step_id``: what its failure takes down, in order."""
        return tuple(d for d in self.descendants(step_id) if states[d] is _S.PENDING)

    def is_complete(self, states: StepStates) -> bool:
        """Every step COMPLETED; true for a plan with no steps (ADR 0004 P7)."""
        return all(states[step_id] is _S.COMPLETED for step_id in self._steps)

    def is_blocked(self, states: StepStates) -> bool:
        """Some step FAILED or CANCELLED: the plan can never complete."""
        return any(states[step_id] in (_S.FAILED, _S.CANCELLED) for step_id in self._steps)


class GraphState(NamedTuple):
    """A graph together with where its steps stand: what the engine returns (ADR 0009)."""

    graph: TaskGraph
    states: StepStates

    def ready(self) -> tuple[StepId, ...]:
        return self.graph.ready(self.states)

    def to_cancel(self, step_id: StepId) -> tuple[StepId, ...]:
        return self.graph.to_cancel(step_id, self.states)

    @property
    def is_complete(self) -> bool:
        return self.graph.is_complete(self.states)

    @property
    def is_blocked(self) -> bool:
        return self.graph.is_blocked(self.states)
