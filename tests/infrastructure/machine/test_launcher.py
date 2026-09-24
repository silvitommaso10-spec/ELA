"""The launcher of ``terminal.run``, on **real children** (M13.2, ADR 0047).

What the tool decides — ``argv``, the environment, the folder, the times, the two halves of the
output — the launcher executes to the letter, and this file asserts it where it can only be
asserted: on a process that really starts. Plain POSIX, so it runs on both runners of ``make
check``; the grandchildren are made with ``sys.executable``, which every runner has.

Each property is asserted as a **fact**, not as a time (ADR 0026 §6): the group is empty when the
launcher returns, the grandchild that held the pipe did not hold the launcher. Where a wait is
unavoidable it is a deadlock guard — a hang becomes a failure — and never what decides the verdict.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import subprocess
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path

import pytest

from ela.infrastructure.machine import ProcessGroupLauncher
from ela.ports import Command, Ending

GUARD = 30.0
"""A deadlock guard, and nothing else: no verdict here depends on it."""
ENVIRONMENT = (
    ("PATH", "/usr/bin:/bin:/usr/sbin:/sbin"),
    ("HOME", "/tmp/ela-casa"),
    ("TMPDIR", "/tmp/ela-tmp"),
    ("LANG", "C.UTF-8"),
)


def command(
    *argv: str,
    folder: Path,
    timeout: float = GUARD,
    grace: float = 0.2,
    head: int = 4096,
    tail: int = 4096,
) -> Command:
    return Command(
        argv=argv,
        environment=ENVIRONMENT,
        folder=str(folder),
        timeout=timeout,
        grace=grace,
        head=head,
        tail=tail,
    )


def python(source: str) -> tuple[str, str, str]:
    return (sys.executable, "-c", textwrap.dedent(source))


@pytest.fixture
def launcher() -> ProcessGroupLauncher:
    return ProcessGroupLauncher(asyncio.Event())


@pytest.fixture
def leftovers() -> Iterator[list[int]]:
    """Pids a test made on purpose to outlive its launcher: killed at the end whatever happens."""
    pids: list[int] = []
    yield pids
    for pid in pids:
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)


def gone(group: int) -> bool:
    try:
        os.killpg(group, 0)
    except ProcessLookupError:
        return True
    return False


# ----------------------------------------------------------------------------------------
# What the child receives
# ----------------------------------------------------------------------------------------


async def test_argv_arrives_as_a_list_and_nothing_is_interpreted_on_the_way(
    launcher: ProcessGroupLauncher, tmp_path: Path
) -> None:
    """Criterion 1: a space, a quote, a ``$`` and a backslash arrive identical — no shell."""
    arguments = ("una frase con spazi", "'virgolette'", '"doppie"', "$HOME", "a\\b", "*")

    ran = await launcher.run(
        command(
            *python("import json, sys; print(json.dumps(sys.argv[1:]))"),
            *arguments,
            folder=tmp_path,
        )
    )

    assert ran.ending is Ending.EXITED and ran.code == 0
    assert json.loads(ran.stdout.head) == list(arguments)


async def test_the_child_receives_the_closed_environment_and_nothing_else(
    launcher: ProcessGroupLauncher, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Criterion 4: ``/usr/bin/env`` prints the four names, and a variable of the Core's does not
    arrive — nor ``SSH_AUTH_SOCK``, nor a ``PATH`` with ``.venv/bin`` in front."""
    monkeypatch.setenv("ELA_API_TOKEN_DI_PROVA", "non-deve-arrivare")
    monkeypatch.setenv("SSH_AUTH_SOCK", "/tmp/agente")

    ran = await launcher.run(command("/usr/bin/env", folder=tmp_path))

    assert ran.ending is Ending.EXITED and ran.code == 0
    printed = ran.stdout.head.decode().splitlines()
    assert sorted(printed) == sorted(f"{name}={value}" for name, value in ENVIRONMENT)


async def test_the_child_starts_in_the_folder_it_was_given_and_never_in_ela_s(
    launcher: ProcessGroupLauncher, tmp_path: Path
) -> None:
    """Criterion 9: today every child of ELA starts in ELA's folder, which holds its ``.env``."""
    folder = (tmp_path / "progetto").resolve()
    folder.mkdir()

    ran = await launcher.run(command(*python("import os; print(os.getcwd())"), folder=folder))

    assert ran.stdout.head.decode().strip() == str(folder)
    assert Path.cwd().resolve() != folder


def test_the_child_reads_the_end_of_file_and_not_the_stdin_of_ela(tmp_path: Path) -> None:
    """Criterion 5: the Core is given a stdin **with data in it**, and its child reads nothing.

    In a process of its own, because a worker of the suite must keep its own stdin: the Core here
    is a small script that runs the launcher, and the data is on its stdin, as a TTY would be.
    """
    script = textwrap.dedent(
        f"""
        import asyncio, sys
        from ela.infrastructure.machine import ProcessGroupLauncher
        from ela.ports import Command
        child = [sys.executable, "-c", "import sys; print(repr(sys.stdin.read()))"]
        ran = asyncio.run(ProcessGroupLauncher(asyncio.Event()).run(Command(
            argv=tuple(child), environment={ENVIRONMENT!r}, folder={str(tmp_path)!r},
            timeout=30.0, grace=0.2, head=4096, tail=4096)))
        print(ran.stdout.head.decode().strip())
        """
    )

    core = subprocess.run(
        [sys.executable, "-c", script],
        input=b"dati che il figlio non deve leggere\n",
        capture_output=True,
        timeout=GUARD,
        check=True,
    )

    assert core.stdout.decode().strip() == "''"


# ----------------------------------------------------------------------------------------
# How it ends, and what it leaves behind
# ----------------------------------------------------------------------------------------


async def test_a_code_is_an_exit_and_a_signal_is_a_signal(
    launcher: ProcessGroupLauncher, tmp_path: Path
) -> None:
    exited = await launcher.run(command(*python("raise SystemExit(3)"), folder=tmp_path))
    hung_up = await launcher.run(
        command(*python("import os, signal; os.kill(os.getpid(), signal.SIGHUP)"), folder=tmp_path)
    )

    assert (exited.ending, exited.code, exited.signal) == (Ending.EXITED, 3, None)
    assert (hung_up.ending, hung_up.code, hung_up.signal) == (Ending.SIGNALLED, None, 1)


def grandchild(pids: Path) -> str:
    """A child that makes a grandchild, says both pids — on stdout and in ``pids``, which is the
    event a test waits for — prints a line, and never ends by itself."""
    return f"""
        import os, pathlib, subprocess, sys, time
        grandchild = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
        print("parziale", flush=True)
        pathlib.Path({str(pids)!r}).write_text(f"{{os.getpid()}} {{grandchild.pid}}")
        time.sleep(600)
    """


async def written(pids: Path) -> tuple[int, int]:
    """The two pids, once the child has written them: a wait on an event, under the guard."""
    async with asyncio.timeout(GUARD):
        while len(said := (pids.read_text() if pids.exists() else "").split()) < 2:
            await asyncio.sleep(0.02)
    return int(said[0]), int(said[1])


async def test_past_the_timeout_the_group_is_empty_when_the_launcher_returns(
    launcher: ProcessGroupLauncher, tmp_path: Path, leftovers: list[int]
) -> None:
    """Criterion 10: the grandchild included, and asserted as a fact of the process table."""
    pids = tmp_path / "pids"
    running = asyncio.create_task(
        launcher.run(command(*python(grandchild(pids)), folder=tmp_path, timeout=3.0))
    )
    child, grand = await written(pids)
    leftovers.extend((child, grand))

    ran = await asyncio.wait_for(running, GUARD)

    assert ran.ending is Ending.TIMED_OUT
    assert gone(child), "the group of the command outlived the launcher"
    assert b"parziale" in ran.stdout.head, "and what it printed until then is kept"


async def test_at_the_signal_of_stopping_the_group_is_emptied_the_same_way(
    tmp_path: Path, leftovers: list[int]
) -> None:
    """«La ripresa»: a Ctrl-C of ``ela serve`` does not reach a group of its own, so ELA does."""
    stopping = asyncio.Event()
    pids = tmp_path / "pids"
    running = asyncio.create_task(
        ProcessGroupLauncher(stopping).run(command(*python(grandchild(pids)), folder=tmp_path))
    )
    child, grand = await written(pids)
    leftovers.extend((child, grand))
    stopping.set()

    ran = await asyncio.wait_for(running, GUARD)

    assert ran.ending is Ending.STOPPED
    assert gone(child)
    assert b"parziale" in ran.stdout.head


async def test_once_stopping_nothing_new_starts(tmp_path: Path) -> None:
    stopping = asyncio.Event()
    stopping.set()

    ran = await ProcessGroupLauncher(stopping).run(
        command(*python("print('partito')"), folder=tmp_path)
    )

    assert ran.ending is Ending.STOPPED
    assert ran.stdout.total == 0


async def test_a_grandchild_that_escapes_the_group_does_not_hold_the_launcher(
    launcher: ProcessGroupLauncher, tmp_path: Path, leftovers: list[int]
) -> None:
    """Decision 7's declared limit: a program that makes a session of its own survives — and it
    must not keep the launcher waiting on a pipe it still holds."""
    escaping = """
        import os, subprocess, sys
        escaped = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(600)"], start_new_session=True
        )
        print(escaped.pid, flush=True)
    """

    ran = await asyncio.wait_for(
        launcher.run(command(*python(escaping), folder=tmp_path, timeout=3.0)), GUARD
    )

    leftovers.append(int(ran.stdout.head.decode().split()[0]))
    assert ran.ending is Ending.TIMED_OUT


async def test_a_cancelled_run_kills_the_group_and_goes_away(
    launcher: ProcessGroupLauncher, tmp_path: Path, leftovers: list[int]
) -> None:
    marker = tmp_path / "ancora-vivo"
    source = f"""
        import pathlib, time
        time.sleep(1.0)
        pathlib.Path({str(marker)!r}).write_text("x")
    """
    running = asyncio.create_task(launcher.run(command(*python(source), folder=tmp_path)))
    await asyncio.sleep(0.3)
    running.cancel()

    with pytest.raises(asyncio.CancelledError):
        await running
    await asyncio.sleep(1.5)

    assert not marker.exists(), "the child outlived the cancelled run"


async def test_what_the_kernel_refuses_is_a_run_that_never_started(
    launcher: ProcessGroupLauncher, tmp_path: Path
) -> None:
    """Decision 5: the one refusal that is only found by trying."""
    garbage = tmp_path / "non-un-programma"
    garbage.write_bytes(b"\x00\x01\x02 non sono un eseguibile")
    garbage.chmod(0o755)

    ran = await launcher.run(command(str(garbage), folder=tmp_path))

    assert ran.ending is Ending.NOT_STARTED
    assert ran.failure is not None and "Errno" in ran.failure


# ----------------------------------------------------------------------------------------
# The output: capped while it is read, and counted in raw bytes
# ----------------------------------------------------------------------------------------


async def test_the_output_is_capped_while_it_is_read_and_every_byte_is_counted(
    launcher: ProcessGroupLauncher, tmp_path: Path
) -> None:
    """Decision 8: 100 000 bytes through a launcher that keeps ten of the head and ten of the tail.

    The two streams are kept apart, each with its own counts.
    """
    source = """
        import sys
        sys.stdout.write("".join(str(n % 10) for n in range(100000)))
        sys.stderr.write("errore")
    """

    ran = await launcher.run(command(*python(source), folder=tmp_path, head=10, tail=10))

    assert ran.stdout.head == b"0123456789"
    assert ran.stdout.tail == b"0123456789"
    assert ran.stdout.total == 100000
    assert (ran.stderr.head + ran.stderr.tail, ran.stderr.total) == (b"errore", 6)


async def test_what_fits_is_kept_whole(launcher: ProcessGroupLauncher, tmp_path: Path) -> None:
    ran = await launcher.run(command(*python("print('corto')"), folder=tmp_path, head=10, tail=10))

    assert ran.stdout.head + ran.stdout.tail == b"corto\n"
    assert ran.stdout.total == 6
