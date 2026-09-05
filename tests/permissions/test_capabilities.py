"""``CapabilityRegistry``: validated and frozen at construction, read-only after (ADR 0010).

Construction refuses what the catalogue must not hold — all or nothing; reading is ``get`` and
``specs`` and nothing else; ``catalogue_v01`` is the three capabilities of §29.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

import pytest

from ela.domain import CapabilityId, CapabilitySpec, RiskLevel
from ela.permissions import (
    CORE_ECHO,
    DEFAULT_NOTES_SCOPE,
    MAX_RISK,
    MODEL_COMPLETE,
    V01_INTRODUCED_AT,
    WORKSPACE_WRITE_NOTE,
    CapabilityNotFound,
    CapabilityRegistry,
    InvalidCapabilityError,
    RiskNotAllowedError,
    catalogue_v01,
    check_capability,
    is_valid_scope_entry,
)
from ela.ports import AlreadyExistsError, CapabilityRegistryPort, NotFoundError
from tests.contracts.protocols import members
from tests.domain.examples import CAPABILITY_SPEC, NOW

ECHO = CapabilitySpec(
    id=CapabilityId("test.echo"),
    created_at=NOW,
    description="d",
    risk=RiskLevel.SAFE,
    input_schema={"type": "object", "properties": {"message": {"type": "string"}}},
    requires_authorization=False,
)


def spec(**changes: Any) -> CapabilitySpec:
    return CAPABILITY_SPEC.model_copy(update=changes)


# --------------------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------------------


def test_get_returns_the_registered_spec_unchanged() -> None:
    registry = CapabilityRegistry([CAPABILITY_SPEC, ECHO])
    assert registry.get(CAPABILITY_SPEC.id) == CAPABILITY_SPEC
    assert registry.get(ECHO.id) == ECHO


def test_unknown_id_is_capability_not_found_which_is_not_found() -> None:
    registry = CapabilityRegistry([ECHO])
    with pytest.raises(CapabilityNotFound) as info:
        registry.get(CAPABILITY_SPEC.id)
    assert isinstance(info.value, NotFoundError)
    assert info.value.capability_id == CAPABILITY_SPEC.id
    assert info.value.key == CAPABILITY_SPEC.id


def test_specs_keeps_construction_order_as_a_tuple() -> None:
    registry = CapabilityRegistry([ECHO, CAPABILITY_SPEC])
    assert registry.specs() == (ECHO, CAPABILITY_SPEC)
    assert CapabilityRegistry([CAPABILITY_SPEC, ECHO]).specs() == (CAPABILITY_SPEC, ECHO)


def test_an_empty_registry_is_allowed() -> None:
    assert CapabilityRegistry([]).specs() == ()


# --------------------------------------------------------------------------------------
# Immutability (the security property)
# --------------------------------------------------------------------------------------


def test_public_api_is_exactly_the_port() -> None:
    public = {name for name in dir(CapabilityRegistry) if not name.startswith("_")}
    assert public == set(members(CapabilityRegistryPort)) == {"get", "specs"}


def test_the_catalogue_is_a_read_only_mapping_and_cannot_grow() -> None:
    registry = CapabilityRegistry([ECHO])
    catalogue = registry._specs
    assert isinstance(catalogue, MappingProxyType)
    with pytest.raises(TypeError):
        catalogue[CAPABILITY_SPEC.id] = CAPABILITY_SPEC  # type: ignore[index]
    with pytest.raises(AttributeError):
        registry.extra = 1  # type: ignore[attr-defined]
    assert registry.specs() == (ECHO,)


def test_construction_does_not_keep_or_mutate_the_iterable() -> None:
    given = [ECHO]
    registry = CapabilityRegistry(given)
    given.append(CAPABILITY_SPEC)
    assert registry.specs() == (ECHO,)
    assert given == [ECHO, CAPABILITY_SPEC]


def test_a_generator_is_consumed_once() -> None:
    registry = CapabilityRegistry(s for s in (ECHO, CAPABILITY_SPEC))
    assert registry.specs() == (ECHO, CAPABILITY_SPEC)


# --------------------------------------------------------------------------------------
# Construction refuses (all or nothing)
# --------------------------------------------------------------------------------------


def test_duplicate_id_is_already_exists() -> None:
    with pytest.raises(AlreadyExistsError):
        CapabilityRegistry([ECHO, ECHO.model_copy(update={"risk": RiskLevel.LOW})])


@pytest.mark.parametrize("risk", [RiskLevel.HIGH, RiskLevel.CRITICAL])
def test_risk_above_medium_is_refused(risk: RiskLevel) -> None:
    with pytest.raises(RiskNotAllowedError) as info:
        CapabilityRegistry([spec(risk=risk)])
    assert isinstance(info.value, InvalidCapabilityError)
    assert info.value.risk is risk
    assert info.value.max_risk is MAX_RISK is RiskLevel.MEDIUM
    assert info.value.capability_id == CAPABILITY_SPEC.id


@pytest.mark.parametrize("risk", [RiskLevel.SAFE, RiskLevel.LOW, RiskLevel.MEDIUM])
def test_risk_up_to_medium_is_admitted(risk: RiskLevel) -> None:
    registry = CapabilityRegistry([spec(risk=risk)])
    assert registry.get(CAPABILITY_SPEC.id).risk is risk


def test_a_late_critical_spec_leaves_no_partial_registry() -> None:
    """The failing element is last: the whole construction fails, nothing is returned."""
    with pytest.raises(RiskNotAllowedError):
        CapabilityRegistry([ECHO, CAPABILITY_SPEC, spec(risk=RiskLevel.CRITICAL)])


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "nope"},
        {"type": "object", "properties": ["path"]},
        {"type": "object", "required": "path"},
    ],
    ids=["unknown-type", "properties-not-an-object", "required-not-an-array"],
)
def test_invalid_json_schema_is_refused(schema: dict[str, Any]) -> None:
    with pytest.raises(InvalidCapabilityError, match="not a valid JSON Schema"):
        CapabilityRegistry([spec(input_schema=schema, scope=(), scoped_arguments=())])


@pytest.mark.parametrize(
    "entry",
    [
        "/workspace/notes",
        "workspace/notes/",
        "workspace//notes",
        "../notes",
        "a/../b",
        "./notes",
        "",
        "a\\b",
    ],
)
def test_malformed_scope_entry_is_refused(entry: str) -> None:
    assert not is_valid_scope_entry(entry)
    with pytest.raises(InvalidCapabilityError, match="scope entry"):
        CapabilityRegistry([spec(scope=(entry,))])


@pytest.mark.parametrize("entry", ["workspace/notes", "notes", "a/b/c.d", "with space/ok"])
def test_well_formed_scope_entry_is_admitted(entry: str) -> None:
    assert is_valid_scope_entry(entry)
    assert CapabilityRegistry([spec(scope=(entry,))]).get(CAPABILITY_SPEC.id).scope == (entry,)


def test_scoped_argument_must_be_a_declared_string_property() -> None:
    with pytest.raises(InvalidCapabilityError, match="scoped argument 'missing'"):
        CapabilityRegistry([spec(scoped_arguments=("missing",))])
    integer_path = {
        "type": "object",
        "properties": {"path": {"type": "integer"}, "body": {"type": "string"}},
    }
    with pytest.raises(InvalidCapabilityError, match="scoped argument 'path'"):
        CapabilityRegistry([spec(input_schema=integer_path)])
    untyped_path = {"type": "object", "properties": {"path": True}}
    with pytest.raises(InvalidCapabilityError, match="scoped argument 'path'"):
        CapabilityRegistry([spec(input_schema=untyped_path)])


def test_schema_without_properties_cannot_have_scoped_arguments() -> None:
    with pytest.raises(InvalidCapabilityError, match="scoped argument 'path'"):
        CapabilityRegistry([spec(input_schema={"type": "object"})])


def test_scope_and_scoped_arguments_come_together() -> None:
    with pytest.raises(InvalidCapabilityError, match="both present or both absent"):
        CapabilityRegistry([spec(scoped_arguments=())])
    with pytest.raises(InvalidCapabilityError, match="both present or both absent"):
        CapabilityRegistry([spec(scope=())])
    assert CapabilityRegistry([spec(scope=(), scoped_arguments=())]).specs()[0].scope == ()


def test_check_capability_returns_none_for_a_valid_spec() -> None:
    assert check_capability(CAPABILITY_SPEC) is None


def test_checks_run_in_the_documented_order() -> None:
    """Risk first, then schema, then scope, then scoped arguments, then consistency."""
    everything_wrong = spec(
        risk=RiskLevel.CRITICAL, input_schema={"type": "nope"}, scope=("../x",), scoped_arguments=()
    )
    with pytest.raises(RiskNotAllowedError):
        check_capability(everything_wrong)
    with pytest.raises(InvalidCapabilityError, match="JSON Schema"):
        check_capability(everything_wrong.model_copy(update={"risk": RiskLevel.LOW}))
    schema_ok = everything_wrong.model_copy(
        update={"risk": RiskLevel.LOW, "input_schema": CAPABILITY_SPEC.input_schema}
    )
    with pytest.raises(InvalidCapabilityError, match="scope entry"):
        check_capability(schema_ok)
    with pytest.raises(InvalidCapabilityError, match="both present"):
        check_capability(schema_ok.model_copy(update={"scope": ("x",)}))


# --------------------------------------------------------------------------------------
# The catalogue of v0.1 (§29)
# --------------------------------------------------------------------------------------


def test_catalogue_v01_holds_exactly_the_three_capabilities_of_the_spec() -> None:
    specs = catalogue_v01().specs()
    assert [s.id for s in specs] == [CORE_ECHO, WORKSPACE_WRITE_NOTE, MODEL_COMPLETE]
    assert [s.id for s in specs] == ["core.echo", "workspace.write_note", "model.complete"]
    by_id = {s.id: s for s in specs}
    assert by_id[CORE_ECHO].risk is RiskLevel.SAFE
    assert by_id[WORKSPACE_WRITE_NOTE].risk is RiskLevel.LOW
    assert by_id[MODEL_COMPLETE].risk is RiskLevel.MEDIUM
    assert all(s.created_at == V01_INTRODUCED_AT for s in specs)
    assert V01_INTRODUCED_AT.tzinfo is not None


def test_catalogue_v01_scope_and_authorization_flags() -> None:
    registry = catalogue_v01()
    echo, note, complete = registry.specs()
    assert (echo.scope, echo.scoped_arguments, echo.requires_authorization) == ((), (), False)
    assert note.scope == (DEFAULT_NOTES_SCOPE,) == ("workspace/notes",)
    assert note.scoped_arguments == ("path",)
    assert note.requires_authorization is False
    assert (complete.scope, complete.scoped_arguments) == ((), ())
    assert complete.requires_authorization is True


def test_catalogue_v01_schemas_refuse_unknown_arguments() -> None:
    for capability in catalogue_v01().specs():
        assert capability.input_schema["type"] == "object"
        assert capability.input_schema["additionalProperties"] is False


def test_catalogue_v01_notes_scope_is_a_parameter() -> None:
    note = catalogue_v01(notes_scope="home/tommaso/notes").get(WORKSPACE_WRITE_NOTE)
    assert note.scope == ("home/tommaso/notes",)
    with pytest.raises(InvalidCapabilityError, match="scope entry"):
        catalogue_v01(notes_scope="../x")


def test_catalogue_v01_is_built_fresh_every_time() -> None:
    assert catalogue_v01() is not catalogue_v01()
    assert catalogue_v01().specs() == catalogue_v01().specs()
