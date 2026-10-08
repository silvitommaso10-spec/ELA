"""Who wrote a plan: three authors, and the fields of the third (M14.2, ADR 0058; decision 5).

``HAND`` is the route a person sends a plan to; ``PLANNER`` is the Planner's own code — the plan of
one step it gives the task that asks the model —; ``MODEL`` is the model, through the Planner. Only
``MODEL`` names the result the plan came from and the model that wrote it, and the domain refuses
those two fields on the other authors: a value that meant «the code» or «the model» according to
whether another field were there is a reading that goes wrong.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from ela.domain import ExecutionId, PlanAuthor, PlanAuthorKind, TaskPlan
from tests.domain.examples import MODEL_AUTHOR, TASK_PLAN

RESULT = ExecutionId(MODEL_AUTHOR.result_id)  # type: ignore[arg-type]


def test_the_three_authors_are_the_ones_the_review_decided() -> None:
    assert [kind.value for kind in PlanAuthorKind] == ["HAND", "PLANNER", "MODEL"]


@pytest.mark.parametrize("kind", [PlanAuthorKind.HAND, PlanAuthorKind.PLANNER], ids=str)
def test_the_hand_and_the_code_name_no_result_and_no_model(kind: PlanAuthorKind) -> None:
    author = PlanAuthor(by=kind)

    assert (author.result_id, author.model) == (None, None)


@pytest.mark.parametrize("kind", [PlanAuthorKind.HAND, PlanAuthorKind.PLANNER], ids=str)
@pytest.mark.parametrize(
    "extra", [{"result_id": RESULT}, {"model": "claude-opus-5-5"}], ids=["result", "model"]
)
def test_a_result_or_a_model_on_the_hand_or_the_code_is_refused(
    kind: PlanAuthorKind, extra: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError, match="only a plan the model wrote"):
        PlanAuthor(by=kind, **extra)


def test_the_model_names_the_result_and_the_model() -> None:
    assert MODEL_AUTHOR.by is PlanAuthorKind.MODEL
    assert MODEL_AUTHOR.result_id is not None
    assert MODEL_AUTHOR.model == "claude-opus-5-5"


@pytest.mark.parametrize(
    "missing",
    [{"result_id": None}, {"model": None}, {"model": ""}],
    ids=["result", "model", "empty"],
)
def test_the_model_without_its_result_or_its_name_is_refused(missing: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="a plan the model wrote names"):
        PlanAuthor.model_validate({**MODEL_AUTHOR.model_dump(), **missing})


def test_a_plan_says_who_wrote_it_and_has_no_default() -> None:
    payload = {key: value for key, value in TASK_PLAN.model_dump().items() if key != "author"}

    with pytest.raises(ValidationError, match="author"):
        TaskPlan.model_validate(payload)


def test_the_example_plan_was_written_by_hand() -> None:
    """Every plan before M14.2 was: the example says so, and so does the migration (``0014``)."""
    assert TASK_PLAN.author == PlanAuthor(by=PlanAuthorKind.HAND)
