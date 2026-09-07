"""``ela perception``: what ELA sees of this machine, on a terminal.

The assertion that matters is the rendering rule: a §11 state is never printed on its own. ``OFF``
alone would tell the reader that a device is switched off, when what ELA means may be that it
could not look — and the terminal is where that difference is either kept or quietly lost.
"""

from __future__ import annotations

import json

import pytest

from ela.cli.errors import OK
from ela.cli.system import sensor
from ela.domain import SensorCause, SensorState, SystemPermission
from tests.cli.support import Cli, plain

pytestmark = pytest.mark.usefixtures("_perception_on")


@pytest.fixture
def _perception_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ELA_PERCEPTION_ENABLED", "true")


async def test_it_prints_both_sensors_with_their_cause(cli: Cli) -> None:
    answered = await cli("perception")

    assert answered.exit_code == OK
    output = plain(answered.stdout)
    assert "microphone" in output
    assert "camera" in output


@pytest.mark.parametrize("cause", list(SensorCause))
def test_a_state_is_never_rendered_without_its_cause(cause: SensorCause) -> None:
    """Every line that shows a sensor goes through one function, and this is what it promises."""
    rendered = sensor({"state": SensorState.OFF.value, "cause": cause.value})

    assert rendered.startswith("OFF (")
    assert rendered != "OFF"
    assert cause.value.lower().replace("_", " ") in rendered


async def test_the_permissions_are_named_one_line_each(cli: Cli) -> None:
    output = plain((await cli("perception")).stdout)

    for permission in SystemPermission:
        assert f"permission {permission.value.lower()}" in output


async def test_nothing_changed_says_so_instead_of_printing_an_empty_line(cli: Cli) -> None:
    """A blank where a list should be reads as a bug; "nothing" reads as an answer."""
    await cli("perception")
    output = plain((await cli("perception")).stdout)

    assert "nothing" in output


async def test_json_carries_the_whole_answer(cli: Cli) -> None:
    answered = await cli("perception", "--json")

    payload = json.loads(answered.stdout)
    assert set(payload["permissions"]) == {p.value for p in SystemPermission}
    assert set(payload["microphone"]) == {"state", "cause"}


async def test_diagnostics_shows_what_ela_may_do_on_this_machine(cli: Cli) -> None:
    """The missing permission is visible without asking for perception at all (ADR 0028 §8)."""
    output = plain((await cli("diagnostics")).stdout)

    assert "perception" in output
    assert "on request" in output
