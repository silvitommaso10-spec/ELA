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
from ela.composition import Ela
from ela.domain import ProbeFamily, RawObservation, SensorCause, SensorState, SystemPermission
from tests.cli.support import Cli, plain

pytestmark = pytest.mark.usefixtures("_perception_on")


@pytest.fixture
def _perception_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ELA_PERCEPTION_ENABLED", "true")


class Machine:
    """The machine as the test says it is: what every look reads, until the test changes it.

    On the real probe ``ela perception`` reads the applications open on the desk of whoever runs
    the suite, and «nothing changed between two looks» is then a fact about that desk. Found red
    on 2026-10-11: the tests of M13.9 open the real Chrome for Testing, and it appeared between
    the two looks of the test below. A test asserts only what it built — here a machine that
    stands still, or one where an application opens when the test says so.
    """

    def __init__(self) -> None:
        self.running: tuple[str, ...] = ("com.example.editor",)
        self.looks = 0

    async def read(self, families: frozenset[ProbeFamily]) -> RawObservation:
        self.looks += 1
        return RawObservation(running_bundle_ids=self.running)


@pytest.fixture
def _every_look_looks(monkeypatch: pytest.MonkeyPatch) -> None:
    """No reading stays fresh: a second command reads the machine again, where by default it
    would answer what the first one saw — and «nothing changed» would be said without a look."""
    for family in ProbeFamily:
        monkeypatch.setenv(f"ELA_PERCEPTION_{family.value}_INTERVAL_SECONDS", "0")


@pytest.fixture
def machine(ela: Ela) -> Machine:
    """ELA's perception on a machine of the test's. **Taken before** ``cli`` by the tests that
    want it: the CLI's fixture starts ELA, and ELA looks once as it starts."""
    built = Machine()
    ela.perception._probe = built  # type: ignore[assignment]
    return built


def changed(output: str) -> str:
    """What the line «changed» of ``ela perception`` says."""
    (line,) = [one for one in output.splitlines() if one.startswith("changed")]
    return line.removeprefix("changed").strip()


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


@pytest.mark.usefixtures("_every_look_looks")
async def test_nothing_changed_says_so_instead_of_printing_an_empty_line(
    machine: Machine, cli: Cli
) -> None:
    """A blank where a list should be reads as a bug; "nothing" reads as an answer."""
    await cli("perception")
    looked = machine.looks
    output = plain((await cli("perception")).stdout)

    assert machine.looks == looked + 1, "the second command looked, and found the same machine"
    assert changed(output) == "nothing"


@pytest.mark.usefixtures("_every_look_looks")
async def test_an_application_that_opens_between_two_looks_is_named_and_not_nothing(
    machine: Machine, cli: Cli
) -> None:
    """The other half, and what the test above stood on without building it: a machine that
    moves between two looks is a change, named — the answer is "nothing" only when it is."""
    await cli("perception")
    machine.running = ("com.example.browser", "com.example.editor")
    output = plain((await cli("perception")).stdout)

    assert changed(output) == (
        "running_bundle_ids: com.example.editor -> com.example.browser,com.example.editor"
    )


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
