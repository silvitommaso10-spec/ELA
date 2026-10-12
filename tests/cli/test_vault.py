"""``ela vault``: the state of the vault, the key handed over a pipe, and the lock (M13.9,
ADR 0063; decisions 16 and 32).

``status`` prints what the vault is and, when it is locked, **the whole line to paste** — composed
by ELA with the declared program, never with a placeholder. ``open`` reads the session key **from
its stdin** and refuses a terminal: a key is not typed and not pasted. It is never printed —
accepted or refused — and nothing but the key is sent. ``close`` locks the vault and makes ELA
forget.
"""

from __future__ import annotations

import asyncio
import io
import json
import shlex
import stat
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from click.testing import Result
from typer.testing import CliRunner

from ela.api import create_app
from ela.cli import client
from ela.cli import vault as command
from ela.cli.app import app as ela_app
from ela.composition import Ela, Settings, build
from ela.composition.system import own_command
from ela.ports import VAULT_LOCKED
from ela.testing.fakes import FakePower, FakeVault
from tests.cli.support import Cli, LoopTransport
from tests.composition.support import create_schema, database_url, declare

PROGRAM = "ELA_VAULT_PROGRAM"
KEY = "the-key-of-the-fake-vault"


def program(folder: Path) -> Path:
    made = folder / "bw"
    made.write_bytes(b"\xcf\xfa\xed\xfe a native program")
    made.chmod(made.stat().st_mode | stat.S_IXUSR)
    return made


@dataclass(frozen=True)
class Vaulted:
    """The command line pointed at an ELA with a declared program and a vault of the test's."""

    ela: Ela
    vault: FakeVault
    transport: LoopTransport
    at: Path

    async def __call__(self, *arguments: str, input: str | None = None) -> Result:
        return await asyncio.to_thread(CliRunner().invoke, ela_app, list(arguments), input=input)

    def sent(self, path: str) -> list[dict[str, object]]:
        """The bodies of the requests the command made to ``path``."""
        return [
            json.loads(request.content)
            for request in self.transport.requests
            if request.url.path == path
        ]


@pytest.fixture
async def vaulted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[Vaulted]:
    folder = tmp_path / "Application Support"
    folder.mkdir()
    at = program(folder)
    declare(monkeypatch, tmp_path, **{PROGRAM: str(at)})
    await create_schema(database_url(tmp_path))
    vault = FakeVault(state=VAULT_LOCKED)
    ela = await build(Settings.load(), power=FakePower(), vault=vault)
    application = create_app(ela)
    transport = LoopTransport(application, asyncio.get_running_loop())
    monkeypatch.setattr(
        client, "connect", lambda: client.open_client(ela.settings.api, transport=transport)
    )
    try:
        async with application.router.lifespan_context(application):
            yield Vaulted(ela, vault, transport, at)
    finally:
        await ela.aclose()


# ----------------------------------------------------------------------------------------
# status
# ----------------------------------------------------------------------------------------


async def test_status_without_a_declared_program_says_which_line_to_write(cli: Cli) -> None:
    result = await cli("vault", "status")

    assert result.exit_code == 0, result.output
    assert "undeclared" in result.output
    assert PROGRAM in result.output
    assert "unlock --raw" not in result.output, "without a program there is no line to paste"


async def test_status_of_a_locked_vault_prints_the_whole_line_to_paste(vaulted: Vaulted) -> None:
    """Criterion 24: the line carries the declared program — here a path with a space, quoted as a
    shell wants it — and no placeholder; it stands on a line of its own, to be copied whole."""
    result = await vaulted("vault", "status")

    assert result.exit_code == 0, result.output
    line = f"'{vaulted.at}' unlock --raw | {shlex.quote(str(own_command()))} vault open"
    assert line in result.output.splitlines()
    assert " | ela " not in result.output, "never a name to look for in the PATH (decision 98)"
    assert "<" not in result.output and "…" not in result.output
    assert "locked" in result.output and str(vaulted.at) in result.output


async def test_status_of_an_open_vault_says_when_ela_forgets_the_key(vaulted: Vaulted) -> None:
    await vaulted("vault", "open", input=KEY + "\n")

    result = await vaulted("vault", "status")

    assert result.exit_code == 0, result.output
    forgets_at = vaulted.ela.vault.forgets_at
    assert forgets_at is not None
    assert "unlocked" in result.output
    assert forgets_at.isoformat().replace("+00:00", "Z") in result.output
    assert "unlock --raw" not in result.output


async def test_status_as_json_is_the_api_s_own_answer(vaulted: Vaulted) -> None:
    result = await vaulted("vault", "status", "--json")

    said = json.loads(result.output)
    assert said["state"] == "locked"
    assert said["opens_with"] == (
        f"'{vaulted.at}' unlock --raw | {shlex.quote(str(own_command()))} vault open"
    )


# ----------------------------------------------------------------------------------------
# open: the key, from a pipe
# ----------------------------------------------------------------------------------------


async def test_open_reads_the_key_from_its_stdin_sends_it_alone_and_never_prints_it(
    vaulted: Vaulted,
) -> None:
    """``bw unlock --raw`` prints the key and a newline: the newline is not the key."""
    result = await vaulted("vault", "open", input=KEY + "\n")

    assert result.exit_code == 0, result.output
    assert vaulted.sent("/vault/session") == [{"key": KEY}]
    assert KEY not in result.output
    assert "forgets the key at" in result.output
    assert vaulted.ela.vault.forgets_at is not None


async def test_open_refuses_a_terminal_and_sends_nothing(
    vaulted: Vaulted, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A key is not typed and not pasted: typed, it would be in the terminal's scrollback."""
    monkeypatch.setattr(command, "stdin_is_a_terminal", lambda: True)

    result = await vaulted("vault", "open", input=KEY + "\n")

    assert result.exit_code == 2
    assert "vault status" in result.output and "whole line" in result.output
    assert "| ela vault open" not in result.output, "no line that may not work (decision 98)"
    assert vaulted.sent("/vault/session") == []
    assert vaulted.vault.calls == []


class Watched(io.BytesIO):
    """A pipe that says whether anybody read from it."""

    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.touched: list[str] = []

    def read(self, size: int | None = -1) -> bytes:
        self.touched.append("read")
        return super().read(size)

    def read1(self, size: int | None = -1) -> bytes:
        self.touched.append("read1")
        return super().read1(size)

    def readinto(self, buffer: Any) -> int:
        self.touched.append("readinto")
        return super().readinto(buffer)

    def readline(self, size: int | None = -1) -> bytes:
        self.touched.append("readline")
        return super().readline(size)


def watched(monkeypatch: pytest.MonkeyPatch, arrives: str) -> Watched:
    """The stdin of the next command, as a pipe that is watched. The runner of the tests makes
    the stdin of a command from a text and nothing else: here it is given this one instead."""
    pipe = Watched(arrives.encode())
    monkeypatch.setattr("typer.testing.make_input_stream", lambda input, charset: pipe)
    return pipe


async def test_open_looks_for_its_token_before_it_reads_the_pipe(
    vaulted: Vaulted, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Decision 107, from the proof: launched from a folder with no ``.env`` the command read
    the pipe first — the user had typed the master password for the vault's program by then —
    and only afterwards found it could not talk to ELA. It looks for what it needs to talk to
    ELA first, and reads nothing if it is not there."""
    monkeypatch.delenv("ELA_API_TOKEN", raising=False)
    monkeypatch.setattr(client, "connect", lambda: client.open_client(client.api_settings()))
    pipe = watched(monkeypatch, KEY + "\n")

    result = await vaulted("vault", "open")

    assert result.exit_code == 2, result.output
    assert "ELA_API_TOKEN" in result.output
    assert pipe.touched == [], "the key the vault's program wrote was not taken"
    assert vaulted.sent("/vault/session") == []


async def test_a_pipe_is_read_when_the_token_is_there(
    vaulted: Vaulted, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other side of the same seam: the pipe of the test is one the command does read."""
    pipe = watched(monkeypatch, KEY + "\n")

    result = await vaulted("vault", "open")

    assert result.exit_code == 0, result.output
    assert pipe.touched, "the precondition of the test above: this pipe sees a reading"
    assert vaulted.sent("/vault/session") == [{"key": KEY}]


@pytest.mark.parametrize("arrived", ["", "\n", "   \n"], ids=["nothing", "a-newline", "blanks"])
async def test_open_with_nothing_on_its_stdin_sends_nothing(vaulted: Vaulted, arrived: str) -> None:
    """``bw unlock`` that failed — a wrong master password — prints no key: nothing is sent."""
    result = await vaulted("vault", "open", input=arrived)

    assert result.exit_code == 2
    assert "no key arrived" in result.output
    assert vaulted.sent("/vault/session") == []


async def test_open_with_a_key_that_does_not_open_exits_1_and_does_not_print_it(
    vaulted: Vaulted,
) -> None:
    wrong = "a-key-that-opens-nothing-SENTINEL"

    result = await vaulted("vault", "open", input=wrong + "\n")

    assert result.exit_code == 1
    assert "vault.key_refused" in result.output
    assert wrong not in result.output


def test_the_terminal_is_asked_of_the_stdin_and_of_nothing_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The seam the tests replace, held to what it reads: the stdin — the pipe is on the stdin,
    and the stdout of ``ela vault open`` may well be a terminal."""

    class Stream:
        def __init__(self, terminal: bool) -> None:
            self._terminal = terminal

        def isatty(self) -> bool:
            return self._terminal

    monkeypatch.setattr(command.sys, "stdin", Stream(True))
    monkeypatch.setattr(command.sys, "stdout", Stream(False))
    assert command.stdin_is_a_terminal() is True

    monkeypatch.setattr(command.sys, "stdin", Stream(False))
    monkeypatch.setattr(command.sys, "stdout", Stream(True))
    assert command.stdin_is_a_terminal() is False


# ----------------------------------------------------------------------------------------
# close
# ----------------------------------------------------------------------------------------


async def test_close_locks_the_vault_and_says_that_ela_forgot_the_key(vaulted: Vaulted) -> None:
    await vaulted("vault", "open", input=KEY + "\n")

    result = await vaulted("vault", "close")

    assert result.exit_code == 0, result.output
    assert "locked" in result.output and "forgot" in result.output
    assert vaulted.vault.calls[-1] == "lock"
    assert vaulted.ela.vault.forgets_at is None


async def test_close_that_could_not_lock_exits_1_and_says_the_key_was_forgotten(
    vaulted: Vaulted,
) -> None:
    await vaulted("vault", "open", input=KEY + "\n")
    vaulted.at.write_bytes(b"\xcf\xfa\xed\xfe an update ELA did not see start")

    result = await vaulted("vault", "close")

    assert result.exit_code == 1
    assert "vault.program_changed" in result.output
    assert "ELA forgot the key" in result.output
