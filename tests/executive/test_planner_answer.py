"""What the model wrote, read strictly and validated before the door (M14.2, ADR 0058).

Decision D: an unknown key in the model's answer is a refused plan, with the key named — a
``"device"`` ignored in silence would make the criterion of §13 look true. Decision B: before
``engine.plan`` the plan passes the functions the Guardian, the registry, the verifier and the
router already use, not a copy of them — the executor's preconditions (``readiness``),
``validate_arguments``, the router's own check of a ``task_type``, ``TaskGraph.from_plan``. A
plan that does not pass is refused, and the reason names the step by position and the constraint,
never a value (§57).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from ela.domain import (
    PlanAuthorKind,
    PlanId,
    RiskLevel,
    TaskId,
    TaskPlan,
)
from ela.executive.planner import (
    PLANNER_INVALID_ARGUMENTS,
    PLANNER_MALFORMED,
    PLANNER_NOT_A_GRAPH,
    PLANNER_NOT_JSON,
    PLANNER_TRUNCATED,
    PLANNER_UNVERIFIABLE,
    Draft,
    NoPlan,
    Refused,
    answer_schema,
    catalogue,
    drafted_plan,
    read_answer,
)
from tests.domain.examples import MODEL_AUTHOR
from tests.executive.planning import (
    ASK_STEP,
    ECHO_STEP,
    NO_PLAN,
    NO_PLAN_REASON,
    NOTE_PLAN,
    NOTE_STEP,
    Planned,
    plan_of,
    step,
)

TASK = TaskId(UUID("00000000-0000-4000-8000-000000000101"))
PLAN = PlanId(UUID("00000000-0000-4000-8000-000000000102"))
AT = datetime(2026, 10, 7, 12, tzinfo=UTC)


@pytest.fixture
def world(tmp_path: Path) -> Planned:
    return Planned(tmp_path / "workspace")


def read(world: Planned, text: str, finish: str | None = "end_turn") -> Any:
    entries = catalogue(capabilities=world.registry, tools=world.tools, verifiers=world.verifiers)
    return read_answer(text, finish, answer_schema(entries))


def drafted(world: Planned, text: str) -> TaskPlan | Refused:
    drafts = read(world, text)
    assert isinstance(drafts, tuple), drafts
    return drafted_plan(
        drafts,
        task_id=TASK,
        goal="the task's own goal",
        plan_id=PLAN,
        created_at=AT,
        author=MODEL_AUTHOR,
        capabilities=world.registry,
        tools=world.tools,
        verifiers=world.verifiers,
        router=world.router,
    )


def refused(world: Planned, text: str) -> Refused:
    answer = read(world, text)
    if isinstance(answer, tuple):  # drafts: the checks before the door
        answer = drafted(world, text)
    assert isinstance(answer, Refused), answer
    return answer


# ----------------------------------------------------------------------------------------
# The answer: one JSON object, and nothing else
# ----------------------------------------------------------------------------------------


def test_a_plan_is_read_into_drafts_in_its_order(world: Planned) -> None:
    drafts = read(world, NOTE_PLAN)

    assert [draft.name for draft in drafts] == ["greet", "write"]
    assert isinstance(drafts[1], Draft)
    assert drafts[1].after == ("greet",)
    assert drafts[0].after == ()


def test_no_plan_is_an_answer_with_the_model_s_reason(world: Planned) -> None:
    assert read(world, NO_PLAN) == NoPlan(NO_PLAN_REASON)


def test_spaces_around_the_object_are_not_text_around_it(world: Planned) -> None:
    assert isinstance(read(world, f"\n  {NOTE_PLAN}\n"), tuple)


@pytest.mark.parametrize(
    "text",
    [
        f"Here is the plan:\n{NOTE_PLAN}",
        f"```json\n{NOTE_PLAN}\n```",
        "[]",
        '"a plan"',
        "",
        '{"plan": {"steps": [}',
    ],
    ids=["a-sentence-before", "a-code-fence", "an-array", "a-string", "nothing", "broken"],
)
def test_anything_but_one_json_object_is_not_json(world: Planned, text: str) -> None:
    answer = refused(world, text)

    assert answer.code == PLANNER_NOT_JSON


def test_a_key_written_twice_is_not_read_as_the_last_one(world: Planned) -> None:
    text = '{"plan": {"steps": []}, "plan": {"steps": []}}'

    assert refused(world, text).code == PLANNER_MALFORMED


def test_a_string_that_is_not_text_is_refused(world: Planned) -> None:
    text = plan_of(step(ECHO_STEP, arguments={"message": "\ud800"}))

    assert refused(world, text).code == PLANNER_NOT_JSON


def test_an_answer_cut_at_max_tokens_is_not_read(world: Planned) -> None:
    answer = read(world, NOTE_PLAN, finish="max_tokens")

    assert isinstance(answer, Refused)
    assert answer.code == PLANNER_TRUNCATED


# ----------------------------------------------------------------------------------------
# The shape: strict, and the path of what does not fit is named
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "path"),
    [
        (plan_of(step(ECHO_STEP, device="mac")), "$.plan.steps[0].device"),
        (json.dumps({"plan": {"steps": [ECHO_STEP], "goal": "g"}}), "$.plan.goal"),
        (json.dumps({"plan": {"steps": [ECHO_STEP]}, "note": "x"}), "$.note"),
        (plan_of(step(ECHO_STEP, risk="SAFE")), "$.plan.steps[0].risk"),
        (plan_of(step(ECHO_STEP, requires_authorization=False)), "$.plan.steps[0]"),
    ],
    ids=["a-device", "a-goal-of-the-plan", "beside-the-plan", "a-risk", "an-authorization"],
)
def test_an_unknown_key_is_a_refused_plan_with_the_key_named(
    world: Planned, text: str, path: str
) -> None:
    answer = refused(world, text)

    assert answer.code == PLANNER_MALFORMED
    assert path in answer.message


def test_a_long_unknown_key_is_named_cut(world: Planned) -> None:
    key = "k" * 300
    answer = refused(world, plan_of(step(ECHO_STEP, **{key: 1})))

    assert answer.code == PLANNER_MALFORMED
    assert key not in answer.message
    assert "k" * 40 in answer.message


@pytest.mark.parametrize(
    "text",
    [
        json.dumps({}),
        json.dumps({"plan": {"steps": []}, "no_plan": {"reason": "r"}}),
        json.dumps({"plan": {"steps": []}}),
        plan_of({k: v for k, v in ECHO_STEP.items() if k != "success_conditions"}),
        plan_of(step(ECHO_STEP, capability="fs.made_up")),
        plan_of(step(ECHO_STEP, success_conditions=[])),
        plan_of(step(ECHO_STEP, name="Not A Name")),
        json.dumps({"no_plan": {"reason": ""}}),
    ],
    ids=[
        "neither",
        "both",
        "no-step",
        "no-conditions",
        "outside-the-catalogue",
        "empty-conditions",
        "a-bad-name",
        "an-empty-reason",
    ],
)
def test_what_does_not_fit_the_shape_is_malformed(world: Planned, text: str) -> None:
    assert refused(world, text).code == PLANNER_MALFORMED


def test_a_value_the_model_wrote_is_never_in_the_reason(world: Planned) -> None:
    secret = "a-value-only-the-model-wrote"
    answer = refused(world, plan_of(step(ECHO_STEP, capability=secret)))

    assert secret not in answer.message
    assert all(secret not in problem for problem in answer.problems)


# ----------------------------------------------------------------------------------------
# The plan: the catalogue writes what the policy reads
# ----------------------------------------------------------------------------------------


def test_a_valid_plan_is_a_task_plan_of_the_task_written_by_the_model(world: Planned) -> None:
    plan = drafted(world, NOTE_PLAN)

    assert isinstance(plan, TaskPlan)
    assert (plan.id, plan.task_id, plan.created_at) == (PLAN, TASK, AT)
    assert plan.author == MODEL_AUTHOR and plan.author.by is PlanAuthorKind.MODEL
    greet, write = plan.steps
    assert write.dependencies == (greet.id,)
    assert write.required_capabilities == ("workspace.write_note",)
    assert dict(write.arguments) == NOTE_STEP["arguments"]
    assert write.success_conditions == ("note.exists", "note.content_matches")


def test_risk_and_authorization_are_the_catalogue_s(world: Planned) -> None:
    """Decision C: whoever chooses writes. The model does not write them, and cannot."""
    plan = drafted(world, plan_of(ECHO_STEP, NOTE_STEP, ASK_STEP))

    assert isinstance(plan, TaskPlan)
    for one in plan.steps:
        spec = world.registry.get(one.required_capabilities[0])
        assert (one.risk, one.requires_authorization) == (spec.risk, spec.requires_authorization)
    assert plan.steps[2].risk is RiskLevel.MEDIUM and plan.steps[2].requires_authorization


def test_no_step_prefers_a_machine(world: Planned) -> None:
    """Decision E: the closed vocabulary of the traits is empty, so the Planner writes none."""
    plan = drafted(world, NOTE_PLAN)

    assert isinstance(plan, TaskPlan)
    assert all(one.preferred_device_traits == () for one in plan.steps)


def test_the_ids_of_the_steps_are_the_planner_s_and_the_same_every_time(world: Planned) -> None:
    first, again = drafted(world, NOTE_PLAN), drafted(world, NOTE_PLAN)

    assert isinstance(first, TaskPlan) and isinstance(again, TaskPlan)
    assert [one.id for one in first.steps] == [one.id for one in again.steps]
    assert "greet" not in {str(one.id) for one in first.steps}


def test_conditions_outside_the_vocabulary_are_refused_with_the_step_and_a_count(
    world: Planned,
) -> None:
    answer = refused(world, plan_of(ECHO_STEP, step(NOTE_STEP, success_conditions=["x.y"])))

    assert answer.code == PLANNER_UNVERIFIABLE
    assert answer.message.startswith("step 2 of 2 (workspace.write_note): ")
    assert "x.y" not in answer.message


def test_arguments_outside_the_schema_are_refused_with_the_paths(world: Planned) -> None:
    answer = refused(world, plan_of(step(ECHO_STEP, arguments={"message": 1, "extra": "v"})))

    assert answer.code == PLANNER_INVALID_ARGUMENTS
    assert answer.message.startswith("step 1 of 1 (core.echo): ")
    assert "$.message" in answer.message
    assert "extra" not in answer.message, "the paths, as the Guardian says them (ADR 0011 §8)"


def test_a_task_type_outside_the_routing_table_is_refused(world: Planned) -> None:
    """ADR 0022 §6: the Planner writes task types from the table's vocabulary."""
    asked = step(ASK_STEP, arguments={"input": "q", "task_type": "made_up_type"})

    answer = refused(world, plan_of(asked))

    assert answer.code == PLANNER_INVALID_ARGUMENTS
    assert "task_type" in answer.message
    assert "made_up_type" not in answer.message


@pytest.mark.parametrize(
    "text",
    [
        plan_of(ECHO_STEP, step(NOTE_STEP, name="greet")),
        plan_of(step(NOTE_STEP, after=["nobody"])),
        plan_of(step(ECHO_STEP, after=["write"]), NOTE_STEP),
    ],
    ids=["two-steps-named-alike", "after-a-step-not-in-the-plan", "a-circle"],
)
def test_what_is_not_a_graph_is_refused(world: Planned, text: str) -> None:
    assert refused(world, text).code == PLANNER_NOT_A_GRAPH


def test_the_first_constraint_that_falls_gives_the_reason_and_all_are_kept(
    world: Planned,
) -> None:
    text = plan_of(
        step(ECHO_STEP, success_conditions=["x.y"]),
        step(NOTE_STEP, arguments={"path": 1, "body": "b"}),
    )

    answer = refused(world, text)

    assert answer.code == PLANNER_UNVERIFIABLE
    assert len(answer.problems) == 2
    assert answer.problems[0] == answer.message
