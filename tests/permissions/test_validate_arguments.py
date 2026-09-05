"""``validate_arguments``: a call's arguments against the capability's JSON Schema (ADR 0010 §4).

Every violation is reported, in path order; the frozen payloads of the domain are read as plain
JSON; the three schemas of v0.1 accept what they document and refuse the rest.
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from ela.domain import CapabilityId, CapabilitySpec
from ela.permissions import (
    CORE_ECHO,
    MODEL_COMPLETE,
    WORKSPACE_WRITE_NOTE,
    InvalidArgumentsError,
    PermissionsError,
    catalogue_v01,
    validate_arguments,
)
from tests.domain.examples import CAPABILITY_SPEC

CATALOGUE = catalogue_v01()


def errors_of(spec: CapabilitySpec, arguments: object) -> tuple[str, ...]:
    with pytest.raises(InvalidArgumentsError) as info:
        validate_arguments(spec, cast(Any, arguments))
    assert info.value.capability_id == spec.id
    assert isinstance(info.value, PermissionsError)
    return info.value.errors


def test_valid_arguments_pass_silently() -> None:
    assert validate_arguments(CAPABILITY_SPEC, {"path": "workspace/notes/a.md", "body": ""}) is None


def test_a_frozen_payload_from_the_domain_is_read_as_plain_json() -> None:
    """A ``JsonMapping`` (MappingProxyType, tuples) must validate like the dict it came from."""
    frozen = CAPABILITY_SPEC.model_copy(
        update={"metadata": {"path": "workspace/notes/a.md", "body": "x", "tags": ["a", "b"]}}
    ).metadata
    schema = CAPABILITY_SPEC.model_copy(
        update={
            "input_schema": {
                **dict(CAPABILITY_SPEC.input_schema),
                "properties": {
                    "path": {"type": "string"},
                    "body": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
            }
        }
    )
    assert validate_arguments(schema, frozen) is None
    assert errors_of(schema, {**dict(frozen), "tags": ("a", 1)}) == (
        "$.tags[1]: 1 is not of type 'string'",
    )


def test_a_missing_required_argument_is_reported() -> None:
    assert errors_of(CAPABILITY_SPEC, {"path": "workspace/notes/a.md"}) == (
        "$: 'body' is a required property",
    )


def test_a_wrong_type_is_reported_with_its_path() -> None:
    assert errors_of(CAPABILITY_SPEC, {"path": 3, "body": "x"}) == (
        "$.path: 3 is not of type 'string'",
    )


def test_every_violation_is_reported_in_path_order() -> None:
    errors = errors_of(CAPABILITY_SPEC, {"path": 3, "body": None})
    assert errors == ("$.body: None is not of type 'string'", "$.path: 3 is not of type 'string'")


def test_arguments_must_be_an_object() -> None:
    assert errors_of(CAPABILITY_SPEC, ["path", "body"]) == (
        "$: ['path', 'body'] is not of type 'object'",
    )


def test_the_message_names_the_capability_and_every_error() -> None:
    with pytest.raises(InvalidArgumentsError) as info:
        validate_arguments(CAPABILITY_SPEC, {})
    assert "workspace.write_note" in str(info.value)
    assert "'path' is a required property" in str(info.value)
    assert "'body' is a required property" in str(info.value)


def test_a_permissive_schema_accepts_anything() -> None:
    anything = CAPABILITY_SPEC.model_copy(
        update={"input_schema": {}, "scope": (), "scoped_arguments": ()}
    )
    assert validate_arguments(anything, {"whatever": [1, {"x": None}]}) is None


# --------------------------------------------------------------------------------------
# The three schemas of v0.1
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("capability_id", "arguments"),
    [
        (CORE_ECHO, {"message": "ping"}),
        (WORKSPACE_WRITE_NOTE, {"path": "workspace/notes/briefing.md", "body": "# Briefing"}),
        (MODEL_COMPLETE, {"input": "Summarise this."}),
        (
            MODEL_COMPLETE,
            {
                "input": "Summarise this.",
                "purpose": "summary",
                "instructions": "Be brief.",
                "model_hint": "fast",
                "parameters": {"max_output_tokens": 200},
            },
        ),
    ],
    ids=["echo", "write_note", "complete-minimal", "complete-full"],
)
def test_v01_schemas_accept_their_documented_arguments(
    capability_id: str, arguments: dict[str, Any]
) -> None:
    assert validate_arguments(CATALOGUE.get(CapabilityId(capability_id)), arguments) is None


@pytest.mark.parametrize(
    ("capability_id", "arguments", "expected"),
    [
        (CORE_ECHO, {}, ("$: 'message' is a required property",)),
        (CORE_ECHO, {"message": 1}, ("$.message: 1 is not of type 'string'",)),
        (
            CORE_ECHO,
            {"message": "x", "loud": True},
            ("$: Additional properties are not allowed ('loud' was unexpected)",),
        ),
        (WORKSPACE_WRITE_NOTE, {"path": "a.md"}, ("$: 'body' is a required property",)),
        (
            WORKSPACE_WRITE_NOTE,
            {"path": ["a.md"], "body": "x"},
            ("$.path: ['a.md'] is not of type 'string'",),
        ),
        (MODEL_COMPLETE, {"purpose": "p"}, ("$: 'input' is a required property",)),
        (
            MODEL_COMPLETE,
            {"input": "x", "parameters": "fast"},
            ("$.parameters: 'fast' is not of type 'object'",),
        ),
        (
            MODEL_COMPLETE,
            {"input": "x", "prompt": "x"},
            ("$: Additional properties are not allowed ('prompt' was unexpected)",),
        ),
    ],
    ids=[
        "echo-missing",
        "echo-type",
        "echo-extra",
        "note-missing",
        "note-type",
        "complete-missing",
        "complete-parameters-type",
        "complete-extra",
    ],
)
def test_v01_schemas_refuse_what_they_do_not_document(
    capability_id: str, arguments: dict[str, Any], expected: tuple[str, ...]
) -> None:
    assert errors_of(CATALOGUE.get(CapabilityId(capability_id)), arguments) == expected
