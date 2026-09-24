"""How ``build`` wires the terminal (M13.2; ADR 0047): what the settings declare, and what stops.

Three facts of the composition, each one a place where the wrong wiring would be silent. The
programs of ``ELA_TERMINAL_PROGRAMS`` reach the catalogue, and the placeholder of the factory never
does (decision 16, the shape of M13.1 dec. A-bis). The tool is built with the scope of M13.1, the
closed environment the composition computes once — ``HOME`` and ``TMPDIR`` from ``Path.home()``
and ``tempfile.gettempdir()``, never from ``os.environ`` (decision 1) — and the limit of the
system. And the **stop**: the event the signal handler raises (ADR 0038 §11) is one event, shared
by the pages' long-polls and by the launcher of the terminal, because a Ctrl-C of ``ela serve``
does not reach a command in a group of its own («La ripresa»).
"""

from __future__ import annotations

import json
import os
import platform
import tempfile
from pathlib import Path

import pytest

from ela.api.app import create_app
from ela.composition import Ela, Settings, build
from ela.composition.system import WINDOWS_COMMAND_LINE, argument_limit
from ela.permissions import TERMINAL_RUN, UNDECLARED_PROGRAMS
from tests.composition.support import create_schema, database_url, declare


async def test_the_declared_programs_reach_the_catalogue_and_the_placeholder_never_does(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    declare(monkeypatch, tmp_path, ELA_TERMINAL_PROGRAMS=json.dumps(["bin/echo"]))
    await create_schema(database_url(tmp_path))
    ela = await build(Settings.load())
    try:
        scope = ela.capabilities.get(TERMINAL_RUN).scope
    finally:
        await ela.aclose()

    assert scope == ("bin/echo",)
    assert UNDECLARED_PROGRAMS[0] not in scope


async def test_no_program_declared_is_an_empty_scope_and_not_the_placeholder(ela: Ela) -> None:
    assert ela.capabilities.get(TERMINAL_RUN).scope == ()


async def test_the_tool_starts_commands_in_the_scope_of_m13_1_with_the_closed_environment(
    ela: Ela,
) -> None:
    terminal = ela.tools.get(TERMINAL_RUN)._terminal  # type: ignore[attr-defined]  # noqa: SLF001

    assert terminal.root == ela.settings.filesystem.root
    assert terminal.scope == ela.settings.filesystem.scope
    assert terminal.home == str(Path.home())
    assert terminal.temporary == tempfile.gettempdir()
    assert terminal.timeout_seconds == ela.settings.terminal.timeout_seconds
    assert terminal.output_max_bytes == ela.settings.terminal.output_max_bytes
    assert terminal.argument_limit == argument_limit(platform.system())


@pytest.mark.parametrize("system", ["Darwin", "Linux"])
def test_a_posix_system_s_limit_is_the_one_execve_passes(system: str) -> None:
    assert argument_limit(system) == os.sysconf("SC_ARG_MAX")


def test_windows_limit_is_the_command_line_and_never_asks_sysconf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``os.sysconf`` does not exist on Windows, and the job ``windows-latest`` builds the Core in
    the conformance suite: a ``build`` that asked for it there would not start. Deleting it here is
    what that machine is, for this one question (an ``if`` per system, rule 37)."""
    monkeypatch.delattr(os, "sysconf")

    assert argument_limit("Windows") == WINDOWS_COMMAND_LINE


async def test_the_signal_of_stopping_is_one_event_for_the_pages_and_the_launcher(
    ela: Ela,
) -> None:
    app = create_app(ela)
    launcher = ela.tools.get(TERMINAL_RUN)._launcher  # type: ignore[attr-defined]  # noqa: SLF001

    assert app.state.stopping is ela.stopping
    assert launcher._stopping is ela.stopping  # noqa: SLF001
