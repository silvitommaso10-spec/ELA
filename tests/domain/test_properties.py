"""Property tests: what the hand-written examples show on one value, hypothesis shows on many."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import BaseModel, ValidationError

from ela.domain import ProviderRequest, RiskLevel, Task, TaskState
from tests.domain.examples import NOW, PROVIDER_REQUEST_ID, TASK_ID
from tests.domain.strategies import MODEL_STRATEGIES, json_mappings, utc_datetimes

MODELS = sorted(MODEL_STRATEGIES, key=lambda model: model.__name__)


@pytest.mark.parametrize("model", MODELS, ids=lambda model: model.__name__)
def test_json_roundtrip_property(model: type[BaseModel]) -> None:
    @given(MODEL_STRATEGIES[model])
    @settings(max_examples=40, deadline=None)
    def check(instance: BaseModel) -> None:
        assert type(instance).model_validate_json(instance.model_dump_json()) == instance

    check()


@pytest.mark.parametrize("model", MODELS, ids=lambda model: model.__name__)
def test_python_roundtrip_property(model: type[BaseModel]) -> None:
    @given(MODEL_STRATEGIES[model])
    @settings(max_examples=40, deadline=None)
    def check(instance: BaseModel) -> None:
        assert type(instance).model_validate(instance.model_dump()) == instance

    check()


@pytest.mark.parametrize("model", MODELS, ids=lambda model: model.__name__)
def test_dump_is_idempotent_and_does_not_mutate(model: type[BaseModel]) -> None:
    @given(MODEL_STRATEGIES[model])
    @settings(max_examples=25, deadline=None)
    def check(instance: BaseModel) -> None:
        before = instance.model_dump_json()
        assert instance.model_dump() == instance.model_dump()
        assert instance.model_dump_json() == before

    check()


@pytest.mark.parametrize("model", MODELS, ids=lambda model: model.__name__)
def test_instances_are_frozen(model: type[BaseModel]) -> None:
    @given(MODEL_STRATEGIES[model])
    @settings(max_examples=10, deadline=None)
    def check(instance: BaseModel) -> None:
        name = next(iter(type(instance).model_fields))
        with pytest.raises(ValidationError, match="frozen"):
            setattr(instance, name, getattr(instance, name))

    check()


@given(json_mappings)
@settings(max_examples=50, deadline=None)
def test_any_json_payload_is_frozen(payload: dict[str, object]) -> None:
    request = ProviderRequest(
        id=PROVIDER_REQUEST_ID,
        created_at=NOW,
        purpose="p",
        input="i",
        parameters=payload,
    )

    def assert_frozen(value: object) -> None:
        if isinstance(value, Mapping):
            with pytest.raises(TypeError):
                value["intruder"] = "no"  # type: ignore[index]
            for item in value.values():
                assert_frozen(item)
        elif isinstance(value, tuple):
            for item in value:
                assert_frozen(item)
        else:
            assert not isinstance(value, list | dict | set)

    assert_frozen(request.parameters)


@given(utc_datetimes)
@settings(max_examples=50, deadline=None)
def test_naive_datetime_is_always_rejected(moment: datetime) -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        Task(
            id=TASK_ID,
            created_at=moment.replace(tzinfo=None),
            goal="g",
            state=TaskState.CREATED,
        )


@given(st.lists(st.sampled_from(list(range(5))), min_size=2, max_size=5))
@settings(max_examples=25, deadline=None)
def test_risk_order_is_total(indexes: list[int]) -> None:
    levels = [list(RiskLevel)[index] for index in indexes]
    ordered = sorted(levels)
    assert [level.severity for level in ordered] == sorted(level.severity for level in levels)
