"""The four exit codes as a contract (ADR 0024 §3, §6).

They are what a script branches on, so the property under test is not only that each code can
happen but that they do not **swap**: an ELA that refuses never exits like an ELA that is not
there, and an ELA that is not there never exits like a refusal. Getting that wrong would make a
retry loop hammer a task ELA has already said no to.

And it is checked on **every command**, not on a sample: the table of ADR 0024 §3 gives each
command the codes it may produce, this module reads that table and drives every row through the
three ways of failing. A command added without a row, or a row added without an invocation here,
fails before it can lie.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import typer
from pydantic import SecretStr

from ela.api import server
from ela.cli import client
from ela.cli.errors import CONFIGURATION, OK, REFUSED, UNREACHABLE, fail
from ela.composition import ApiSettings, Ela
from tests.cli.support import Cli, plain, unreachable
from tests.docs.test_adr_cli import documented_command_exits, documented_commands

MISSING = "11111111-1111-4111-8111-111111111111"
PLAN = str(Path(__file__).resolve().parents[2] / "docs" / "examples" / "first-task.json")

INVOCATIONS: dict[str, tuple[str, ...]] = {
    "health": ("health",),
    "diagnostics": ("diagnostics",),
    "approvals": ("approvals",),
    "perception": ("perception",),
    "context": ("context",),
    "voice": ("voice",),
    "voice preview": ("voice", "preview", "VZOd9FMXDnXRZpGn0thg"),
    "voice audition": ("voice", "audition", "VZOd9FMXDnXRZpGn0thg"),
    "task create": ("task", "create", "una cosa"),
    "task list": ("task", "list"),
    "task show": ("task", "show", MISSING),
    "task results": ("task", "results", MISSING),
    "task plan": ("task", "plan", MISSING, "--file", PLAN),
    "task run": ("task", "run", MISSING),
    "task approve": ("task", "approve", MISSING, "--approval", MISSING),
    "task deny": ("task", "deny", MISSING, "--approval", MISSING),
    "task cancel": ("task", "cancel", MISSING),
    "audit tail": ("audit", "tail"),
    "audit verify": ("audit", "verify"),
    "device list": ("device", "list"),
    "node enroll": ("node", "enroll", "--privacy", "TRUSTED"),
    "node revoke": ("node", "revoke", MISSING),
    "provider list": ("provider", "list"),
}
"""One valid invocation per command that talks to ELA — valid, so that what is being tested is
how it *ends* and not that its arguments were wrong. ``init`` and ``serve`` are not here: they
open no client, and the two codes under test are a client's."""


def calling_commands() -> list[str]:
    return [name for name, route in documented_commands().items() if route is not None]


def test_every_command_of_the_table_has_an_invocation_here() -> None:
    """Closed world: a command added to ADR 0024 §3 is a command driven by the tests below."""
    assert set(INVOCATIONS) == set(calling_commands())


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


@pytest.mark.parametrize("command", sorted(INVOCATIONS), ids=sorted(INVOCATIONS))
async def test_ela_is_not_there(
    cli: Cli, ela: Ela, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    """Nothing answered, so nothing was refused either: the code is not the one for a refusal."""
    monkeypatch.setattr(
        client,
        "connect",
        lambda: client.open_client(ela.settings.api, transport=httpx.MockTransport(unreachable)),
    )

    result = await cli(*INVOCATIONS[command])

    assert result.exit_code == UNREACHABLE, result.output
    assert UNREACHABLE in documented_command_exits()[command]


@pytest.mark.parametrize("command", sorted(INVOCATIONS), ids=sorted(INVOCATIONS))
async def test_a_token_ela_does_not_know_is_a_refusal_for_every_command(
    cli: Cli, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    """ELA answered 401: every command reports it as a refusal, and none of them as a crash."""
    wrong = ApiSettings(api_token=SecretStr("z" * 40))
    monkeypatch.setattr(
        client, "connect", lambda: client.open_client(wrong, transport=cli.transport)
    )

    result = await cli(*INVOCATIONS[command])

    assert result.exit_code == REFUSED, result.output
    assert "unauthorized" in plain(result.stderr)
    assert REFUSED in documented_command_exits()[command]


@pytest.mark.parametrize("command", sorted(INVOCATIONS), ids=sorted(INVOCATIONS))
async def test_no_token_at_all_never_reaches_ela(
    cli: Cli, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    """Without the token the CLI cannot even ask: that is the configuration code, for all of
    them, and never the one that says ELA refused."""
    monkeypatch.delenv("ELA_API_TOKEN", raising=False)
    monkeypatch.setattr(client, "connect", _real_connect)

    result = await cli(*INVOCATIONS[command])

    assert result.exit_code == CONFIGURATION, result.output
    assert "ELA_API_TOKEN" in plain(result.stderr)


@pytest.mark.parametrize("command", ["init", "serve"], ids=["init", "serve"])
async def test_a_local_command_never_opens_a_client(
    cli: Cli, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    """Which is why its row promises two codes and not four (ADR 0024 §3): there is nothing to
    refuse it and no port to find closed."""

    def never() -> client.ElaClient:
        raise AssertionError(f"{command} opened a client")

    monkeypatch.setattr(client, "connect", never)
    monkeypatch.setattr(server, "serve", lambda settings: None)

    result = await cli(command)

    assert result.exit_code == OK, result.output
    assert documented_command_exits()[command] == {OK, CONFIGURATION}


def _real_connect() -> client.ElaClient:
    """The production ``connect``, which reads the environment: the fixture replaced it."""
    return client.open_client(client.api_settings())


async def test_a_command_that_does_not_exist_never_reaches_ela(cli: Cli) -> None:
    """click's own code for a bad command line is the same one: what you gave me is wrong."""
    assert (await cli("taks", "list")).exit_code == CONFIGURATION
