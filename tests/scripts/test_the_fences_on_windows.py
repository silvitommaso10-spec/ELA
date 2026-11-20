"""**The fences of the scripts on Windows** (M13.17b, decision 11): ``tests/conftest.py`` is
loaded by the job ``node-windows`` too, and what M13.17b says of Windows is proved here, on that
job's line.

What the sonda of the connections read in CPython's source and did not measure (M13.17b, «Le
sonde»): asyncio's proactor loop, the default on Windows, connects with ``ConnectEx`` and never
passes through ``socket.socket.connect`` — so the fence has a second door there,
``BaseProactorEventLoop.sock_connect`` —; and a loop of asyncio is born with a ``socketpair`` that,
where ``_socket`` has none, connects to a listener of this same process. And on Windows a bare name
is never derived: ``CreateProcess`` does not look in the ``PATH`` alone.

**Nothing here reaches the real world with the fences broken**: the launch is this interpreter with
``pass``, the listener a child of the test.
"""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tests import machines, script_fences
from tests.scripts.test_a_script_never_reaches_the_real_world import (
    A_SCRIPT,
    a_listener_of_another_process,  # noqa: F401 — the fixture, used by name below
    a_script,
    caught,
)

pytestmark = machines.needs(
    machines.WINDOWS, why="the proactor loop and CreateProcess are Windows's"
)


def test_the_fences_are_installed_on_windows() -> None:
    from asyncio import proactor_events

    from pydantic_settings.sources.providers.dotenv import DotEnvSettingsSource

    assert "fork" not in script_fences.OS_LAUNCHERS and "system" in script_fences.OS_LAUNCHERS
    for guarded in (
        subprocess.Popen._execute_child,  # type: ignore[attr-defined]
        socket.socket.connect,
        socket.socket.connect_ex,
        socket.socket.bind,
        socket.getaddrinfo,
        proactor_events.BaseProactorEventLoop.sock_connect,
        DotEnvSettingsSource._read_env_files,
        *(getattr(os, name) for name in script_fences.OS_LAUNCHERS),
    ):
        assert getattr(guarded, script_fences.GUARDED, False), guarded


def test_a_launch_from_a_script_is_refused_on_windows() -> None:
    refusal = caught(
        lambda: a_script(A_SCRIPT)(
            lambda: subprocess.run([sys.executable, "-c", "pass"], check=True)
        )
    )

    assert isinstance(refusal, script_fences.LaunchFromAScript)


def test_a_bare_name_is_never_derived_on_windows() -> None:
    assert script_fences.resolved_program("python", None, None) is None


def test_a_connection_of_asyncio_on_the_proactor_is_refused_at_its_own_door(
    a_listener_of_another_process: tuple[int, Path],  # noqa: F811 — the fixture imported above
) -> None:
    port, mark = a_listener_of_another_process
    mark.unlink(missing_ok=True)

    async def connect() -> None:
        assert isinstance(asyncio.get_running_loop(), asyncio.ProactorEventLoop)
        await asyncio.open_connection("127.0.0.1", port)

    refusal = caught(lambda: a_script(A_SCRIPT)(lambda: asyncio.run(connect())))

    assert isinstance(refusal, script_fences.ConnectionFromAScript), refusal
    assert not mark.exists()


def test_a_loop_of_asyncio_is_born_without_a_refusal_from_a_script() -> None:
    """Its ``socketpair``, where it is CPython's own, connects to a listener this process bound."""
    a_script(A_SCRIPT)(lambda: asyncio.run(asyncio.sleep(0)))


def test_the_home_and_the_folder_of_work_are_the_test_s_on_windows(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    base = tmp_path_factory.getbasetemp().resolve()

    assert Path.home().resolve().is_relative_to(base)
    assert Path.cwd().resolve().is_relative_to(base)
