"""The four exit codes as a contract (ADR 0024 §6).

They are what a script branches on, so the property under test is not only that each code can
happen but that they do not **swap**: an ELA that refuses never exits like an ELA that is not
there, and an ELA that is not there never exits like a refusal. Getting that wrong would make a
retry loop hammer a task ELA has already said no to.
"""

from __future__ import annotations

import httpx
import pytest
import typer

from ela.cli import client
from ela.cli.errors import CONFIGURATION, OK, REFUSED, UNREACHABLE, fail
from ela.composition import Ela
from tests.cli.support import Cli, unreachable

MISSING = "11111111-1111-4111-8111-111111111111"


def test_the_four_codes_are_four() -> None:
    assert len({OK, REFUSED, CONFIGURATION, UNREACHABLE}) == 4


def test_a_failure_is_a_sentence_on_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(typer.Exit) as raised:
        fail(REFUSED, "not_found: no such task")

    captured = capsys.readouterr()
    assert raised.value.exit_code == REFUSED
    assert captured.err.strip() == "ela: not_found: no such task"
    assert captured.out == ""


async def test_it_worked(cli: Cli) -> None:
    assert (await cli("health")).exit_code == OK


async def test_ela_said_no(cli: Cli) -> None:
    """A 404 is an answer: the task is not there, and ELA is."""
    result = await cli("task", "show", MISSING)

    assert result.exit_code == REFUSED
    assert result.exit_code != UNREACHABLE


async def test_ela_is_not_there(cli: Cli, ela: Ela, monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing answered, so nothing was refused either: the code is not the one for a refusal."""
    monkeypatch.setattr(
        client,
        "connect",
        lambda: client.open_client(ela.settings.api, transport=httpx.MockTransport(unreachable)),
    )

    for command in (("health",), ("task", "show", MISSING), ("audit", "verify")):
        result = await cli(*command)

        assert result.exit_code == UNREACHABLE, command
        assert result.exit_code != REFUSED


async def test_the_configuration_is_wrong_and_nothing_was_sent(
    cli: Cli, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The token is missing: the CLI cannot even ask, so this is not a refusal either."""
    monkeypatch.delenv("ELA_API_TOKEN", raising=False)
    monkeypatch.setattr(client, "connect", _real_connect)

    result = await cli("health")

    assert result.exit_code == CONFIGURATION
    assert "ELA_API_TOKEN" in result.stderr


def _real_connect() -> client.ElaClient:
    """The production ``connect``, which reads the environment: the fixture replaced it."""
    return client.open_client(client.api_settings())


async def test_a_command_that_does_not_exist_never_reaches_ela(cli: Cli) -> None:
    """click's own code for a bad command line is the same one: what you gave me is wrong."""
    assert (await cli("taks", "list")).exit_code == CONFIGURATION
