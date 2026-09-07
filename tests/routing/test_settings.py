"""``RoutingSettings`` (ADR 0022 §8): the table from the environment, or the one of §25.

Two variables, both JSON, both replacing what they name in full. What is under test is that ELA
routes sensibly on a machine where nobody configured anything, that an operator can replace the
table, and that what cannot be a table is refused rather than half-read.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from pydantic_settings.exceptions import SettingsError

from ela.ports import ROUTING_UNKNOWN_TASK_TYPE, RoutingError
from ela.routing import BALANCED, CHEAP, DEFAULT_ROUTE, DEFAULT_ROUTES, QUALITY, RoutingSettings

ROUTES = "ELA_MODEL_ROUTES"
DEFAULT = "ELA_MODEL_DEFAULT_ROUTE"


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in (ROUTES, DEFAULT):
        monkeypatch.delenv(variable, raising=False)


def test_the_defaults_are_the_table_of_the_spec() -> None:
    settings = RoutingSettings(_env_file=None)

    assert settings.model_routes == dict(DEFAULT_ROUTES)
    assert settings.model_default_route == DEFAULT_ROUTE
    assert settings.policy().route_for("coding").profile == QUALITY
    assert settings.policy().route_for(None).profile == BALANCED


def test_the_table_is_replaced_in_full_not_merged(monkeypatch: pytest.MonkeyPatch) -> None:
    """ADR 0022 §8: a table half ELA's opinion and half the operator's could not be read off a
    single document."""
    monkeypatch.setenv(
        ROUTES, json.dumps({"coding": {"providers": ["local", "anthropic"], "profile": CHEAP}})
    )
    policy = RoutingSettings(_env_file=None).policy()

    assert policy.task_types() == ("coding",)
    assert policy.route_for("coding").providers == ("local", "anthropic")
    assert policy.route_for("coding").profile == CHEAP
    with pytest.raises(RoutingError) as raised:
        policy.route_for("planning")  # the default table is gone, not merged into
    assert raised.value.code == ROUTING_UNKNOWN_TASK_TYPE


def test_the_default_route_can_be_replaced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DEFAULT, json.dumps({"providers": ["local"], "profile": QUALITY}))
    policy = RoutingSettings(_env_file=None).policy()

    assert policy.route_for(None).providers == ("local",)
    assert policy.route_for(None).profile == QUALITY
    assert policy.task_types() == tuple(sorted(DEFAULT_ROUTES))  # the table is untouched


def test_an_empty_table_routes_only_what_declares_no_type(monkeypatch: pytest.MonkeyPatch) -> None:
    """Legal, and it means what it says: refusing it would deny an operator the right to say
    "nothing but the default route" (ADR 0022 §8)."""
    monkeypatch.setenv(ROUTES, "{}")
    policy = RoutingSettings(_env_file=None).policy()

    assert policy.task_types() == ()
    assert policy.route_for(None) == DEFAULT_ROUTE
    with pytest.raises(RoutingError):
        policy.route_for("coding")


@pytest.mark.parametrize(
    "value",
    [
        "not json at all",
        '{"coding": {"providers": [], "profile": "quality"}}',
        '{"coding": {"providers": ["a", "a"], "profile": "quality"}}',
        '{"coding": {"providers": ["a"], "profile": ""}}',
        '{"coding": {"providers": ["a"]}}',
        '{"coding": {"providers": ["a"], "profile": "quality", "extra": 1}}',
        '{"": {"providers": ["a"], "profile": "quality"}}',
        '{"coding": "quality"}',
    ],
    ids=[
        "not-json",
        "no-provider",
        "repeated-provider",
        "blank-profile",
        "no-profile",
        "unknown-key",
        "blank-task-type",
        "not-a-route",
    ],
)
def test_a_table_that_is_not_a_table_is_refused(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """Refused at construction, with no partial reading: a routing table that ELA understood by
    halves would send the user's content somewhere nobody wrote down (§33)."""
    monkeypatch.setenv(ROUTES, value)
    with pytest.raises((ValidationError, SettingsError)):
        RoutingSettings(_env_file=None)


def test_a_default_route_that_is_not_a_route_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DEFAULT, '{"providers": [], "profile": "balanced"}')
    with pytest.raises(ValidationError):
        RoutingSettings(_env_file=None)


def test_the_variables_are_read_from_a_dotenv_file_too(tmp_path: Path) -> None:
    """The two fields start with ``model_``, pydantic's protected namespace: without
    ``protected_namespaces=()`` declaring them under the ``ELA_`` prefix every other settings
    class uses would warn on every import (ADR 0022 §8)."""
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        f'{ROUTES}={{"coding": {{"providers": ["local"], "profile": "cheap"}}}}\n'
        f'{DEFAULT}={{"providers": ["local"], "profile": "cheap"}}\n',
        encoding="utf-8",
    )

    settings = RoutingSettings(_env_file=dotenv)

    assert settings.policy().route_for("coding").providers == ("local",)
    assert settings.model_default_route.profile == CHEAP


def test_unknown_variables_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ELA_SOMETHING_ELSE", "1")
    RoutingSettings(_env_file=None)
