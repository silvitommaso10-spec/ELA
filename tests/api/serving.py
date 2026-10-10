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

* ``open`` — a page open, and **the browser stopped** (``SIGSTOP``) until ELA's close begins to
  wait for it. The stop a signal raises tells the page to close, and the browser cannot answer:
  the close is entered **with that closing in flight** — built with an event, because left to
  itself the browser closes while the server is still stopping (the review of the repair). When
  the grace begins the browser is let go (``SIGCONT``), and closes within it.
* ``stuck`` — a page open, and **the driver stopped** for good: a browser that will not answer
  when it is told to close.

Two lines of JSON on stdout: the processes the browser had started, when it is in its state — the
test sends the signal after that line —; and ``{"grace": true}`` at the moment ELA's close begins
to wait for the browser, which is when the test sends a second signal **inside the close**.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
from collections.abc import Awaitable, Callable
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
        drivers = set(browser._driver_pids())  # noqa: SLF001 — the drivers the adapter started
        everything = started()
        frozen = (
            sorted(drivers) if mode == "stuck" else [p for p, _ in everything if p not in drivers]
        )
        for pid in frozen:
            os.kill(pid, signal.SIGSTOP)
        settling = browser.settle

        async def settle(grace: Callable[[], Awaitable[None]]) -> tuple[str, ...]:
            async def waited() -> None:
                # The close has begun to wait for the browser: said, and — in ``open`` — the
                # browser let go, so that the closing in flight ends within the grace.
                print(json.dumps({"grace": True}), flush=True)
                if mode == "open":
                    for pid in frozen:
                        os.kill(pid, signal.SIGCONT)
                await grace()

            return await settling(waited)  # type: ignore[no-any-return]

        browser.settle = settle
        print(json.dumps({"pid": os.getpid(), "started": everything}), flush=True)

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
