"""Every model survives a JSON round-trip unchanged: §49 entities the Core can persist and ship."""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from ela.domain import CapabilitySpec, Device, ProviderUsage, Task, TaskPlan, TaskStep
from tests.domain.examples import EXAMPLES
from tests.domain.examples import TASK_STEP as STEP

MODELS = sorted(EXAMPLES, key=lambda model: model.__name__)


@pytest.mark.parametrize("model", MODELS, ids=lambda model: model.__name__)
def test_json_roundtrip(model: type[BaseModel]) -> None:
    example = EXAMPLES[model]
    assert model.model_validate_json(example.model_dump_json()) == example


@pytest.mark.parametrize("model", MODELS, ids=lambda model: model.__name__)
def test_python_roundtrip(model: type[BaseModel]) -> None:
    example = EXAMPLES[model]
    assert model.model_validate(example.model_dump()) == example


@pytest.mark.parametrize("model", MODELS, ids=lambda model: model.__name__)
def test_dump_produces_plain_json_containers(model: type[BaseModel]) -> None:
    """Frozen inside, plain outside: what leaves the domain is ordinary JSON."""
    dumped = json.loads(EXAMPLES[model].model_dump_json())
    assert isinstance(dumped, dict)


def test_enums_serialise_as_their_name() -> None:
    dumped = json.loads(EXAMPLES[Task].model_dump_json())
    assert dumped["state"] == "PLANNING"


def test_uuids_serialise_as_strings() -> None:
    dumped = json.loads(EXAMPLES[Task].model_dump_json())
    assert dumped["id"] == "00000000-0000-4000-8000-000000000003"


def test_datetimes_serialise_as_utc_iso8601() -> None:
    dumped = json.loads(EXAMPLES[Task].model_dump_json())
    assert dumped["created_at"] == "2026-09-04T10:30:00Z"


def test_decimal_cost_keeps_its_precision() -> None:
    dumped = json.loads(EXAMPLES[ProviderUsage].model_dump_json())
    assert dumped["cost"] == "0.0123"


def test_json_payload_keeps_its_shape() -> None:
    dumped = json.loads(EXAMPLES[CapabilitySpec].model_dump_json())
    assert dumped["input_schema"]["required"] == ["path", "body"]
    assert isinstance(dumped["input_schema"]["properties"], dict)


def test_nested_models_roundtrip() -> None:
    plan = EXAMPLES[TaskPlan]
    assert TaskPlan.model_validate_json(plan.model_dump_json()).steps == plan.steps


def test_json_schema_is_generated() -> None:
    """The models are also a contract for the API layer (§54): the schema must build."""
    schema = Device.model_json_schema()
    assert schema["properties"]["privacy"]
    assert schema["additionalProperties"] is False


def test_a_frozen_payload_with_an_array_can_be_handed_to_another_model() -> None:
    """Found implementing M13.2: ``args`` is the first plan argument that is an array.

    A ``JsonMapping`` freezes an array into a tuple, and ``JsonValue`` refused a tuple — so a step
    parsed by the API could not become the domain's ``TaskStep``: «input was not a valid JSON
    value». Nothing had an array before, and a mapping inside a mapping had the same fate
    (``model.complete``'s ``parameters``). Frozen is what the domain hands around, so frozen must
    be what it accepts.
    """
    first = TaskStep(
        id=STEP.id,
        created_at=STEP.created_at,
        goal=STEP.goal,
        required_capabilities=STEP.required_capabilities,
        arguments={"args": ["a", "b"], "parameters": {"max_tokens": 10, "stop": ["x"]}},
        risk=STEP.risk,
        expected_result=STEP.expected_result,
        requires_authorization=STEP.requires_authorization,
    )

    again = TaskStep.model_validate(first.model_dump())
    handed = TaskStep(**{**first.model_dump(exclude={"arguments"}), "arguments": first.arguments})

    assert handed.arguments == first.arguments == again.arguments
    assert handed.model_dump()["arguments"] == {
        "args": ["a", "b"],
        "parameters": {"max_tokens": 10, "stop": ["x"]},
    }
