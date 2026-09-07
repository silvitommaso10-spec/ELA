"""Immutability is deep: fields cannot be reassigned and their contents cannot be mutated."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from pydantic import BaseModel, ValidationError

from ela.domain import CapabilitySpec, Device, TaskPlan
from tests.domain.examples import EXAMPLES

MODELS = sorted(EXAMPLES, key=lambda model: model.__name__)


@pytest.mark.parametrize("model", MODELS, ids=lambda model: model.__name__)
def test_assignment_is_rejected(model: type[BaseModel]) -> None:
    example = EXAMPLES[model]
    for name in model.model_fields:
        with pytest.raises(ValidationError, match="frozen"):
            setattr(example, name, getattr(example, name))


@pytest.mark.parametrize("model", MODELS, ids=lambda model: model.__name__)
def test_sequences_are_tuples(model: type[BaseModel]) -> None:
    example = EXAMPLES[model]
    for name in model.model_fields:
        value = getattr(example, name)
        assert not isinstance(value, list | set | dict), f"{model.__name__}.{name}"


def _payloads(model: type[BaseModel]) -> list[Mapping[str, object]]:
    example = EXAMPLES[model]
    return [
        value for name in model.model_fields if isinstance(value := getattr(example, name), Mapping)
    ]


MODELS_WITH_PAYLOAD = [model for model in MODELS if _payloads(model)]


@pytest.mark.parametrize("model", MODELS_WITH_PAYLOAD, ids=lambda model: model.__name__)
def test_json_payloads_cannot_be_mutated(model: type[BaseModel]) -> None:
    for payload in _payloads(model):
        with pytest.raises(TypeError):
            payload["intruder"] = "no"  # type: ignore[index]


def test_models_without_a_json_payload_are_the_expected_ones() -> None:
    """A payload is opt-in: Actor and ProviderUsage are fully typed and need none.

    ``TaskStep`` left this list in M6.3: ``arguments`` is a JSON payload (ADR 0018), and it is
    frozen like every other one — a plan that could be edited in place after the Guardian read it
    would be a plan nobody decided about.
    """
    without = sorted(model.__name__ for model in MODELS if not _payloads(model))
    assert without == ["Actor", "ProviderUsage"]


def test_nested_mapping_is_frozen_too() -> None:
    """A dict inside a payload is frozen as well: shallow immutability would be a lie."""
    properties = EXAMPLES[CapabilitySpec].input_schema["properties"]
    assert isinstance(properties, Mapping)
    with pytest.raises(TypeError):
        properties["path"] = "no"  # type: ignore[index]


def test_nested_array_becomes_a_tuple() -> None:
    device = EXAMPLES[Device]
    families = device.capabilities[0].attributes["families"]
    assert families == ("ada", "hopper")
    assert isinstance(families, tuple)


def test_nested_models_are_frozen() -> None:
    step = EXAMPLES[TaskPlan].steps[0]
    with pytest.raises(ValidationError, match="frozen"):
        step.goal = "other"


def test_model_copy_produces_a_new_frozen_model() -> None:
    """Changing an entity means building another one, which is again immutable."""
    device = EXAMPLES[Device]
    renamed = device.model_copy(update={"name": "Windows"})
    assert renamed.name == "Windows"
    assert device.name == "MacBook"
    with pytest.raises(ValidationError, match="frozen"):
        renamed.name = "again"
