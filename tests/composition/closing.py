"""An ELA that closes with its browser at work, in a process of its own (M13.4e).

Not a test: the child ``test_closing.py`` starts, because what it asserts is that **a process
exits** — and the process under test cannot be the one that runs the suite.

    python tests/composition/closing.py MODE FOLDER ORIGIN

It builds ELA with ``build``, on a database in ``FOLDER``, with the real browser; opens a page of
``ORIGIN`` — served by the test —; puts something of the browser in flight; and then closes as
``ela.api.server._serve`` does: ``await ela.aclose()`` in a ``finally``, and the return of ``main``,
after which ``asyncio.run`` tears the loop down.

The modes: ``close`` — a close just asked for —, ``fill`` — a fill waiting for a field that is
disabled —, ``pool`` — no page, three connections in the database's pool. Each also with
``-sigint``: a ``SIGINT`` raised again right before the close, which is what uvicorn does when
``serve`` returns after a Ctrl-C — the handler of ``asyncio.run`` cancels the main task, and the
close is entered with that cancellation pending.

One line of JSON on stdout before the close: the processes the browser had started. Exit code 0;
130 when ``asyncio.run`` raised ``KeyboardInterrupt``, as it does after a Ctrl-C.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INTERRUPTED = 130


def started() -> list[tuple[int, str]]:
    """What this process has started and the kernel still knows — ``ps`` itself aside."""
    out = subprocess.run(
        ["/bin/ps", "-A", "-o", "pid=,ppid=,comm="], capture_output=True, text=True, check=True
    ).stdout
    children: dict[int, list[tuple[int, str]]] = {}
    for line in out.splitlines():
        pid, ppid, name = line.split(None, 2)
        children.setdefault(int(ppid), []).append((int(pid), name.rsplit("/", 1)[-1]))
    found: list[tuple[int, str]] = []
    todo = [os.getpid()]
    while todo:
        for pid, name in children.get(todo.pop(), []):
            if name != "ps":
                found.append((pid, name))
                todo.append(pid)
    return found


def declare(folder: Path) -> None:
    """The minimum an ELA needs, as ``tests.composition.support.declare`` writes it, and nothing
    of the machine's own: no ``ELA_`` variable of whoever runs the suite, no ``.env``."""
    for name in [name for name in os.environ if name.startswith("ELA_")]:
        del os.environ[name]
    os.chdir(folder)
    (folder / "files").mkdir()
    os.environ.update(
        ELA_DB_URL=f"sqlite:///{(folder / 'ela.db').as_posix()}",
        ELA_WORKSPACE_DIR=str(folder / "workspace"),
        ELA_CAPTURE_DIR=str(folder / "captures"),
        ELA_API_TOKEN="x" * 40,
        ELA_FS_ROOT=str(folder / "files"),
        ELA_FS_SCOPE="ELA",
        ELA_TERMINAL_PROGRAMS="[]",
        ELA_BROWSER_SITES="[]",
        ELA_PERCEPTION_ENABLED="false",
        ELA_NODE_POLL_SECONDS="1",
    )


async def main(mode: str, folder: Path, origin: str) -> None:
    sys.path.insert(0, str(ROOT))
    declare(folder)
    from ela.composition import Settings, build
    from ela.permissions import BROWSER_READ
    from ela.testing.fakes import FakePower, FakeStop
    from tests.composition.support import create_schema

    what, _, interrupted = mode.partition("-")
    await create_schema(os.environ["ELA_DB_URL"])
    ela = await build(Settings.load(), power=FakePower())
    try:
        async with ela.database.begin() as connection:
            await connection.exec_driver_sql("create table closing (x integer)")
        if what == "pool":
            gate = asyncio.Event()

            async def held() -> None:
                async with ela.database.begin() as connection:
                    await connection.exec_driver_sql("insert into closing values (1)")
                    await gate.wait()

            holding = [asyncio.create_task(held()) for _ in range(3)]
            while ela.database.pool.checkedout() < len(holding):
                await asyncio.sleep(0)
            gate.set()
            await asyncio.gather(*holding)
        else:
            # The browser ELA built, reached where its tools hold it: the one the close settles.
            browser = ela.tools.get(BROWSER_READ)._browser  # type: ignore[attr-defined]  # noqa: SLF001
            opened = await browser.open(origin + "/", lambda url: True, FakeStop())
            if what == "close":
                asyncio.create_task(browser.close(opened.page))
            else:
                asyncio.create_task(browser.fill(opened.page, "#nome", "x"))
            # One turn, and one more: the call has been handed to the driver, and is in flight.
            await asyncio.sleep(0)
            await asyncio.sleep(0)
        print(json.dumps({"started": started()}), flush=True)
        if interrupted:
            signal.raise_signal(signal.SIGINT)
    finally:
        await ela.aclose()


if __name__ == "__main__":
    # A process started from a terminal has Python's own handler of SIGINT, which is what makes
    # ``asyncio.run`` install its own. A worker of the suite may ignore the signal, and an ignored
    # signal is inherited across ``exec``: without this line the SIGINT below would be raised and
    # dropped, and the close would never be entered cancelled.
    signal.signal(signal.SIGINT, signal.default_int_handler)
    try:
        asyncio.run(main(sys.argv[1], Path(sys.argv[2]), sys.argv[3]))
    except KeyboardInterrupt:
        raise SystemExit(INTERRUPTED) from None
