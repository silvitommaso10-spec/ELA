"""The property of ADR 0026 §7 on the plans ELA's Planner builds (M14.2, ADR 0058, criterion 6).

    for any step the model can write and the Planner accepts, the Guardian's outcome is never more
    permissive than the outcome of the same call with no step at all, and the decision carries the
    catalogue's risk.

``test_client_plan_properties.py`` states it for a step a client builds by hand. A step the
Planner builds is narrower — its ``risk`` and ``requires_authorization`` are the registered spec's,
never the model's, because the schema of the answer has neither — and the property is asserted on
it anyway: the narrowing is a line of ``drafted_plan``, and a line can change.

The drafts are generated over the catalogue the Planner offers, with arguments the schema accepts
and arguments it does not; what ``drafted_plan`` refuses is not a step, and has nothing to decide.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final
from uuid import UUID

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ela.domain import ExecutionId, PlanAuthor, PlanAuthorKind, PlanId, TaskId, TaskPlan
from ela.executive.planner import Draft, catalogue, drafted_plan
from tests.executive.planning import NOTE_BODY, NOTE_PATH, Planned
from tests.permissions.test_client_plan_properties import PERMISSIVENESS

NOW: Final = datetime(2026, 10, 7, 12, tzinfo=UTC)
TASK: Final = TaskId(UUID("00000000-0000-4000-8000-0000000000aa"))
PLAN: Final = PlanId(UUID("00000000-0000-4000-8000-0000000000ab"))
AUTHOR: Final = PlanAuthor(
    by=PlanAuthorKind.MODEL,
    result_id=ExecutionId(UUID("00000000-0000-4000-8000-0000000000ac")),
    model="claude-opus-5-5",
)
VALID: Final[dict[str, dict[str, Any]]] = {
    "core.echo": {"message": "ciao"},
    "workspace.write_note": {"path": NOTE_PATH, "body": NOTE_BODY},
    "model.complete": {"input": "Che cos'è un grafo?", "task_type": "reasoning"},
}
"""One set of arguments each capability's schema accepts, the drafts' starting point."""


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> Planned:
    return Planned(Path(tmp_path_factory.mktemp("planner")) / "workspace")


def offered(world: Planned) -> list[Any]:
    return list(
        catalogue(capabilities=world.registry, tools=world.tools, verifiers=world.verifiers)
    )


@st.composite
def drafts(draw: st.DrawFn, entries: list[Any]) -> Draft:
    entry = draw(st.sampled_from(entries))
    arguments = dict(VALID[entry.spec.id])
    arguments.update(
        draw(
            st.dictionaries(
                st.sampled_from([*entry.spec.input_schema.get("properties", {}), "extra"]),
                st.one_of(st.text(max_size=12), st.integers(), st.booleans()),
                max_size=2,
            )
        )
    )
    conditions = draw(
        st.lists(st.sampled_from(entry.conditions), min_size=1, unique=True).map(tuple)
    )
    return Draft(
        name="step",
        goal=draw(st.text(max_size=20)),
        capability=str(entry.spec.id),
        arguments=arguments,
        after=(),
        expected_result="what the model expects",
        success_conditions=conditions,
    )


def plan_of(world: Planned, draft: Draft) -> TaskPlan | None:
    built = drafted_plan(
        (draft,),
        task_id=TASK,
        goal="the task's goal",
        plan_id=PLAN,
        created_at=NOW,
        author=AUTHOR,
        capabilities=world.registry,
        tools=world.tools,
        verifiers=world.verifiers,
        router=world.router,
    )
    return built if isinstance(built, TaskPlan) else None


@given(data=st.data())
@settings(deadline=None, max_examples=300)
def test_a_step_the_planner_builds_is_never_more_permissive_than_no_step_at_all(
    world: Planned, data: st.DataObject
) -> None:
    plan = plan_of(world, data.draw(drafts(offered(world))))
    if plan is None:
        return
    (step,) = plan.steps
    spec = world.registry.get(step.required_capabilities[0])

    baseline = world.guardian.decide(spec, step.arguments, step=None)
    reached = world.guardian.decide(spec, step.arguments, step=step)

    assert PERMISSIVENESS[reached.outcome] <= PERMISSIVENESS[baseline.outcome]
    assert reached.risk is spec.risk
    assert (step.risk, step.requires_authorization) == (spec.risk, spec.requires_authorization)


def test_the_property_is_not_vacuous(world: Planned) -> None:
    """Every capability the Planner offers yields a plan with its valid arguments, and the three
    reach the three levels the property compares: SAFE runs, LOW runs inside the scope, MEDIUM
    asks — so a baseline that were always DENIED would be seen here."""
    outcomes = {}
    for entry in offered(world):
        draft = Draft(
            "step",
            "goal",
            str(entry.spec.id),
            VALID[entry.spec.id],
            (),
            "expected",
            entry.conditions,
        )
        plan = plan_of(world, draft)
        assert plan is not None, entry.spec.id
        (step,) = plan.steps
        outcomes[entry.spec.id] = world.guardian.decide(
            entry.spec, step.arguments, step=step
        ).outcome.value

    assert set(outcomes) == set(VALID)
    assert outcomes["model.complete"] == "REQUIRES_APPROVAL"
    assert outcomes["core.echo"] == "ALLOWED"
