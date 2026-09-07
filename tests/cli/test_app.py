"""The ``ela`` command itself: which sub-commands it has, and how it is invoked.

The list is asserted here and against ADR 0024 in ``tests/docs/test_adr_cli.py``: here it is the
shape (every command reachable, nothing hidden), there it is the agreement with the document.
"""

from __future__ import annotations

import runpy

import pytest

import ela.cli.app as commands
from ela.cli.app import app
from tests.cli.support import Cli


def command_paths() -> set[str]:
    """Every command path the app serves, ``task run`` written as ``task run``."""
    found = set()
    for name, group in [("", app)]:
        for command in group.registered_commands:
            found.add(f"{name}{command.name}")
    for group in app.registered_groups:
        assert group.typer_instance is not None
        for command in group.typer_instance.registered_commands:
            found.add(f"{group.name} {command.name}")
    return found


def test_every_command_of_the_milestone_is_there() -> None:
    assert command_paths() == {
        "init",
        "serve",
        "health",
        "diagnostics",
        "approvals",
        "task create",
        "task list",
        "task show",
        "task results",
        "task plan",
        "task run",
        "task approve",
        "task deny",
        "task cancel",
        "audit tail",
        "audit verify",
        "device list",
        "provider list",
    }


async def test_the_help_lists_the_groups_without_reaching_ela(cli: Cli) -> None:
    """``--help`` answers with ELA stopped: it is the app talking, not the API."""
    result = await cli("--help")

    assert result.exit_code == 0
    for group in ("task", "audit", "device", "provider"):
        assert group in result.stdout


def test_main_runs_the_app(monkeypatch: pytest.MonkeyPatch) -> None:
    ran: list[bool] = []
    monkeypatch.setattr(commands, "app", lambda: ran.append(True))

    commands.main()

    assert ran == [True]


def test_python_m_ela_cli_runs_main(monkeypatch: pytest.MonkeyPatch) -> None:
    ran: list[bool] = []
    monkeypatch.setattr(commands, "main", lambda: ran.append(True))

    runpy.run_module("ela.cli.__main__", run_name="__main__")

    assert ran == [True]
