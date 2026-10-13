"""A real ``ela serve``, in a process of its own, with its browser at work (M13.4e, the second
part: decisions 55 and 56).

Not a test: the child ``test_serving_signals.py`` starts, because what it asserts is how **a
process ends after a signal** — and the process under test cannot be the one that runs the suite.

    python tests/api/serving.py MODE FOLDER ORIGIN PORT [GRACE]

It is ``ela serve`` itself — ``ela.cli.app.main`` with ``serve`` on its command line, so the real
server, the real signals and the real end —, on a database in ``FOLDER`` and on ``PORT`` of
loopback. One thing is added, and only one: once ``build`` has returned, a task opens a page of
``ORIGIN`` — served by the test — with the browser ELA built, and puts it in the state ``MODE``
names:

* ``open`` — a page open, and **the browser stopped** (``SIGSTOP``) until ELA's close begins to
  wait for it. The stop a signal raises tells the page to close, and the browser cannot answer:
  the close is entered **with that closing in flight** — built with an event, because left to
  itself the browser closes while the server is still stopping (the review of the repair). When
  the grace begins the browser is let go (``SIGCONT``), and closes. **In this mode the grace does
  not run out by itself**: how long a machine takes to close a browser it has just let go is the
  machine's — on the macOS runner, under the load of the suite, the grace was not enough
  (2026-10-11) —, and what is asserted is that the close waits for the closing in flight and
  kills nobody. A browser that never closed would meet the guard of the test.
* ``stuck`` — a page open, and **the driver stopped** for good: a browser that will not answer
  when it is told to close.
* ``elsewhere`` — ``stuck``, and **from the moment ELA's close begins to wait for the browser the
  main thread takes no stop signal**: the system must hand the next one to another thread of
  this process, which it may do by itself at any time (decision 141 of M13.9's review; M13.4e,
  the third part). A thread that waits is there from before, so that there is one to hand it
  to; and the main thread takes its signals again once the close is done with the browser, so
  that the process ends as the signal ends it.

``GRACE`` is **a grace handed to this ELA**, in whole seconds, in the place of its own (decision
76): what a test of the signals asserts — that ELA kills at the grace and not before, says so, and
ends as the signal ended it — is as true of a second as of ELA's five, and one test alone watches
those whole. Without it the grace is ELA's. **The test of the second signal hands one that no
test waits out** (decision 114 of M13.9): there the wait of the close must end at the signal, and
a grace that could run out first made the test depend on how loaded the machine was.

Two lines of JSON on stdout: the processes the browser had started, when it is in its state — the
test sends the signal after that line —; and ``{"grace": true}`` at the moment ELA's close begins
to wait for the browser, which is when the test sends a second signal **inside the close**.
"""

from __future__ import annotations

import asyncio
import faulthandler
import json
import os
import signal
import sys
import threading
from collections.abc import Awaitable, Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STILL_HERE_SECONDS = 35
"""After how long a child of these tests says where it is: longer than any of them takes to end
by itself, and shorter than the guard that kills it."""
STUCK = ("stuck", "elsewhere")
"""The modes whose browser will not answer when it is told to close."""
ELSEWHERE = "elsewhere"
STOPS = ("SIGINT", "SIGTERM", "SIGHUP")


def main(mode: str, folder: Path, origin: str, port: str, grace: str | None = None) -> None:
    sys.path.insert(0, str(ROOT))
    from tests.composition.closing import declare, started

    declare(folder)
    os.environ["ELA_API_PORT"] = port

    from ela.api import server
    from ela.cli.app import main as ela
    from ela.composition import Ela, Settings, root

    if grace is not None:
        # The two that read the number: the close that waits it, and the line that says it.
        root.BROWSER_CLOSE_GRACE_SECONDS = int(grace)  # type: ignore[misc]
        server.BROWSER_CLOSE_GRACE_SECONDS = int(grace)  # type: ignore[misc]
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
            sorted(drivers) if mode in STUCK else [p for p, _ in everything if p not in drivers]
        )
        for pid in frozen:
            os.kill(pid, signal.SIGSTOP)
        settling = browser.settle
        stops = {getattr(signal, name) for name in STOPS}
        if mode == ELSEWHERE:
            # Started before the main thread stops taking the signals: a thread takes what the
            # one that started it took.
            threading.Thread(target=threading.Event().wait, daemon=True).start()

        async def settle(grace: Callable[[], Awaitable[None]]) -> tuple[str, ...]:
            async def waited() -> None:
                if mode == ELSEWHERE:
                    signal.pthread_sigmask(signal.SIG_BLOCK, stops)
                # The close has begun to wait for the browser: said, and — in ``open`` — the
                # browser let go, so that the closing in flight ends within the grace.
                print(json.dumps({"grace": True}), flush=True)
                if mode == "open":
                    for pid in frozen:
                        os.kill(pid, signal.SIGCONT)
                    # No clock ends this wait: the close returns because the closing in flight
                    # ended, and whoever waits here is cancelled then.
                    await asyncio.Event().wait()
                await grace()

            try:
                return await settling(waited)  # type: ignore[no-any-return]
            finally:
                if mode == ELSEWHERE:
                    signal.pthread_sigmask(signal.SIG_UNBLOCK, stops)

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
    # A child that is still here after this long is one a test's guard is about to kill: it
    # says where every thread of it is, on the stream the test puts in its failure — so that a
    # red of these tests names the place, and is not only «did not exit». Seen once, under the
    # load of the whole suite, on 2026-10-12: a mechanism that explains it was measured apart —
    # a signal the system hands to another thread did not wake a loop that waits — and repaired
    # on 2026-10-13 (``docs/milestones/M13.4e.md``, the third part); what this prints is how
    # the next one will be told from it. A child that ends as it should has ended long before.
    faulthandler.dump_traceback_later(STILL_HERE_SECONDS, repeat=True, file=sys.stderr)
    signal.signal(signal.SIGINT, signal.default_int_handler)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.signal(signal.SIGHUP, signal.SIG_DFL)
    main(sys.argv[1], Path(sys.argv[2]), sys.argv[3], sys.argv[4], *sys.argv[5:6])
