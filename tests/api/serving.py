"""A real ``ela serve``, in a process of its own, with its browser at work (M13.4e, the second
part: decisions 55 and 56).

Not a test: the child ``test_serving_signals.py`` starts, because what it asserts is how **a
process ends after a signal** — and the process under test cannot be the one that runs the suite.

    python tests/api/serving.py MODE FOLDER ORIGIN PORT

It is ``ela serve`` itself — ``ela.cli.app.main`` with ``serve`` on its command line, so the real
server, the real signals and the real end —, on a database in ``FOLDER`` and on ``PORT`` of
loopback. One thing is added, and only one: once ``build`` has returned, a task opens a page of
``ORIGIN`` — served by the test — with the browser ELA built, and puts it in the state ``MODE``
names:

* ``open`` — a page open. The stop a signal raises is what closes it: ELA's close is entered with
  that closing in flight.
* ``stuck`` — a page open, and **the driver stopped** (``SIGSTOP``): a browser that will not answer
  when it is told to close.

Then one line of JSON on stdout: the processes the browser had started. The test sends the signal
after that line.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main(mode: str, folder: Path, origin: str, port: str) -> None:
    sys.path.insert(0, str(ROOT))
    from tests.composition.closing import declare, started

    declare(folder)
    os.environ["ELA_API_PORT"] = port

    from ela.api import server
    from ela.cli.app import main as ela
    from ela.composition import Ela, Settings
    from ela.permissions import BROWSER_READ
    from ela.testing.fakes import FakePower, FakeStop
    from tests.composition.support import create_schema

    asyncio.run(create_schema(os.environ["ELA_DB_URL"]))
    building = server.build
    held: list[asyncio.Task[None]] = []

    async def at_work(ela: Ela) -> None:
        # The browser ELA built, reached where its tools hold it: the one the close settles.
        browser = ela.tools.get(BROWSER_READ)._browser  # type: ignore[attr-defined]  # noqa: SLF001
        await browser.open(origin + "/", lambda url: True, FakeStop())
        mine = os.getpid()
        if mode == "stuck":
            for pid in browser._driver_pids():  # noqa: SLF001 — the drivers the adapter started
                os.kill(pid, signal.SIGSTOP)
        print(json.dumps({"pid": mine, "started": started()}), flush=True)

    async def built(settings: Settings) -> Ela:
        made = await building(settings, power=FakePower())
        held.append(asyncio.get_running_loop().create_task(at_work(made)))
        return made

    server.build = built  # type: ignore[assignment]
    sys.argv = ["ela", "serve"]
    ela()


if __name__ == "__main__":
    # What a process started from a terminal finds. A worker of the suite may ignore ``SIGINT``,
    # and an ignored signal is inherited across ``exec``.
    signal.signal(signal.SIGINT, signal.default_int_handler)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.signal(signal.SIGHUP, signal.SIG_DFL)
    main(sys.argv[1], Path(sys.argv[2]), sys.argv[3], sys.argv[4])
