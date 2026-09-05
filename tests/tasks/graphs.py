"""Step graphs for the tests of the Task Graph: hand-made shapes and random DAGs (hypothesis).

A random DAG is acyclic by construction — step ``i`` may only depend on steps ``0..i-1`` — and
is then handed over in a random plan order, so the topological order is never the plan order by
accident. ``cyclic_dags`` takes such a DAG and adds one edge from an ancestor to a descendant.
"""

from __future__ import annotations

from uuid import UUID

from hypothesis import strategies as st

from ela.domain import RiskLevel, StepId, TaskStep
from ela.tasks.graph import TaskGraph
from tests.domain.examples import NOW

MAX_STEPS = 8


def sid(index: int) -> StepId:
    return StepId(UUID(f"00000000-0000-4000-8000-{1000 + index:012d}"))


def step(index: int, *dependencies: StepId) -> TaskStep:
    return TaskStep(
        id=sid(index),
        created_at=NOW,
        goal=f"step {index}",
        dependencies=dependencies,
        risk=RiskLevel.LOW,
        expected_result=f"result of step {index}",
        requires_authorization=False,
    )


def chain(length: int) -> tuple[TaskStep, ...]:
    """``0 <- 1 <- 2 ...``: each step depends on the previous one."""
    return tuple(step(i, *([sid(i - 1)] if i else [])) for i in range(length))


def diamond() -> tuple[TaskStep, ...]:
    """``0`` at the top, ``1`` and ``2`` depending on it, ``3`` depending on both."""
    return (step(0), step(1, sid(0)), step(2, sid(0)), step(3, sid(1), sid(2)))


@st.composite
def dags(draw: st.DrawFn, max_size: int = MAX_STEPS) -> tuple[TaskStep, ...]:
    """Random steps whose dependencies form a DAG, in a random plan order."""
    size = draw(st.integers(min_value=0, max_value=max_size))
    steps = []
    for index in range(size):
        earlier = [sid(j) for j in range(index) if draw(st.booleans())]
        steps.append(step(index, *earlier))
    return tuple(draw(st.permutations(steps)))


@st.composite
def cyclic_dags(draw: st.DrawFn) -> tuple[tuple[TaskStep, ...], StepId, StepId]:
    """A DAG with at least one edge, plus one back edge: (steps, ancestor, descendant).

    The returned steps are the DAG with ``ancestor`` now also depending on ``descendant``.
    """
    steps = draw(dags(max_size=MAX_STEPS).filter(lambda s: any(x.dependencies for x in s)))
    graph = TaskGraph(steps)
    with_descendants = [s for s in steps if graph.descendants(s.id)]
    ancestor = draw(st.sampled_from(with_descendants))
    descendant = draw(st.sampled_from(sorted(graph.descendants(ancestor.id), key=str)))
    cyclic = tuple(
        s.model_copy(update={"dependencies": (*s.dependencies, descendant)})
        if s.id == ancestor.id
        else s
        for s in steps
    )
    return cyclic, ancestor.id, descendant
