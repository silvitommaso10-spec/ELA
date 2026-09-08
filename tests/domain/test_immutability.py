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
    """A payload is opt-in, and every model here is fully typed and needs none.

    ``TaskStep`` left this list in M6.3: ``arguments`` is a JSON payload (ADR 0018), and it is
    frozen like every other one — a plan that could be edited in place after the Guardian read
    it would be a plan nobody decided about. ``ModelRoute`` joined it in M7.3: a route is four
    declared values, and a metadata bag on a routing decision would be a place to smuggle in a
    choice the policy did not make (ADR 0022 §2).

    Three of the four perception models joined in M10.1, and for them it is a §57 property
    rather than a preference: a free-form bag on an observation is exactly where a window
    title, a filename or a transcript would eventually be put "just for context". What ELA
    perceives is the declared fields and nothing else, and the milestone that first reads
    content will have to add a typed field and argue for it.

    ``Observation`` is **not** here, and that is the point rather than an exception: its
    ``permissions`` is a mapping, so it is checked by the test above like every other
    payload — which is how the frozen permissions map gets proved instead of assumed.
    """
    without = sorted(model.__name__ for model in MODELS if not _payloads(model))
    assert without == [
        "Actor",
        "ModelRoute",
        "PerceptionChange",
        "ProviderUsage",
        "RawObservation",
        "SensorStatus",
    ]


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
