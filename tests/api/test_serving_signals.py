"""How ``ela serve`` ends after a signal (M13.4e, the second part: decisions 55 and 56).

**After ``SIGINT``, ``SIGTERM`` or ``SIGHUP`` ELA's close runs whole** — the stop, the browser at
rest within its grace, the database released — **and only then the process ends, as it ended
before for whoever launched it. A second signal ends the grace at once.**

Measured before it was written (``docs/milestones/M13.4e.md``): until this, only a Ctrl-C reached
the close. After a ``SIGTERM`` — which is how ``pkill`` stops ELA — uvicorn raised the signal again
on its way out of ``serve`` and the process died there; a ``SIGHUP`` killed it at once; and a
second Ctrl-C while the close waited tore the loop down with a call of the browser's in flight,
which is a process that does not exit.

The ELA under test is a process of its own (``tests/api/serving.py``): the real ``ela serve``, the
real signals, the real browser. Nothing here is an upper bound on a time: that the hurry ended
the wait **before the grace ran out** is what the line on stderr says — it is written only then —,
and the guard is the test's and never the one that fires. What a failing run leaves is taken away
by the pids the child named and by the folder its browser was given.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from tests.browser_leftovers import Left, left, named, running, scratch, sweep

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="SIGHUP, a session and ps are POSIX's"
)

CHILD = Path(__file__).with_name("serving.py")
ROOT = CHILD.parents[2]
GUARD_SECONDS = 60
GRACE_SECONDS = 5
HANDED_SECONDS = 1
"""The grace an ELA of these tests is handed, where the test is not the one that watches ELA's own
whole (decision 76): what is asserted of a grace — killed at it and not before, said, and the end
of the signal — does not ask for five seconds to be true."""
PAGE = b"<p>a page of the test's</p>"
SIGNALS = ["SIGINT", "SIGTERM", "SIGHUP"]
"""By name: read as numbers inside a test, never when the module is imported — a system without
``SIGHUP`` skips these tests, and must be able to read the file to skip them."""
INTERRUPTED = 130
WITHIN = f"ela: the browser did not close within {GRACE_SECONDS} s of the stop: ELA killed"
WITHIN_THE_HANDED = WITHIN.replace(f"{GRACE_SECONDS} s", f"{HANDED_SECONDS} s")
HURRIED = "ela: the browser had not closed when a second signal arrived: ELA killed"
NO_TEST_WAITS_IT_OUT = 60 * GUARD_SECONDS
"""A grace handed to ELA that cannot run out inside a test: the guard of :func:`served` ends the
test long before it. What ends the wait of the close is then an event, and never this clock."""


@pytest.fixture
def origin() -> Iterator[str]:
    """A page of the test's own, on ``127.0.0.1``."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)

        def log_message(self, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.fixture
def profiles() -> Iterator[Path]:
    """The temporary folder of the child's driver: where its browser's profile is, and by which
    whatever a failing run leaves is found and taken away."""
    folder = scratch()
    try:
        yield folder
    finally:
        sweep(folder)
        shutil.rmtree(folder, ignore_errors=True)


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@dataclass(frozen=True)
class Ended:
    """How an ``ela serve`` ended, and what it left."""

    code: int
    error: str
    started: tuple[tuple[int, str], ...]
    database: tuple[str, ...]
    seconds: float
    left: Left
    waited: bool
    """Whether ELA's close began to wait for the browser: the child says so when the grace of the
    close is asked for — the browser had not closed by itself when the close was entered."""

    def still_running(self) -> list[str]:
        return [name for pid, name in self.started if running(pid)]


def _reached(event: threading.Event, child: subprocess.Popen[str]) -> bool:
    """Wait for ``event``, for as long as the child lives and the guard allows."""
    deadline = time.monotonic() + GUARD_SECONDS
    while not event.wait(0.05):
        if child.poll() is not None or time.monotonic() > deadline:
            return event.is_set()
    return True


def served(
    mode: str,
    folder: Path,
    origin: str,
    profiles: Path,
    *signals: int,
    grace: int | None = None,
) -> Ended:
    """Start ``ela serve`` with its browser in ``mode``, send it ``signals`` — the second **when
    ELA's close has begun to wait for the browser**, which the child says —, and say how it ended.
    ``grace`` is the grace that ELA is handed in the place of its own, in seconds.

    The child is the leader of a session of its own. One that does not exit is killed with its
    group before the test fails; and whatever of its browser is left — a stopped process whose
    driver has died is in nobody's group — is taken away by its pid and by ``profiles``."""
    folder.mkdir()
    child = subprocess.Popen(
        [
            sys.executable,
            str(CHILD),
            mode,
            str(folder),
            origin,
            str(free_port()),
            *(() if grace is None else (str(grace),)),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
        cwd=ROOT,
        env={**os.environ, "TMPDIR": str(profiles)},
    )
    assert child.stdout is not None and child.stderr is not None
    said: list[str] = []
    errors: list[str] = []
    ready = threading.Event()
    waiting = threading.Event()

    def listen(stream: Iterator[str], kept: list[str], signs: dict[str, threading.Event]) -> None:
        for line in stream:
            kept.append(line)
            for sign, event in signs.items():
                if sign in line:
                    event.set()

    readers = [
        threading.Thread(
            target=listen,
            args=(child.stdout, said, {'"started"': ready, '"grace"': waiting}),
            daemon=True,
        ),
        threading.Thread(target=listen, args=(child.stderr, errors, {}), daemon=True),
    ]
    for reader in readers:
        reader.start()

    def heard() -> str:
        for reader in readers:
            reader.join(5)
        return "".join(errors)

    started: tuple[tuple[int, str], ...] = ()
    try:
        if not _reached(ready, child):
            pytest.fail(f"the child never said its browser was at work:\n{heard()}")
        row = json.loads(next(line for line in said if '"started"' in line))
        started = tuple((pid, name) for pid, name in row["started"])
        assert named(profiles), (
            "the control: the browser's profile is in the folder this test gave its driver — "
            "else «nothing is left» below would be true of a folder nobody used"
        )
        began = time.monotonic()
        child.send_signal(signals[0])
        for later in signals[1:]:
            if not _reached(waiting, child):
                pytest.fail(
                    "the close never began to wait for the browser, so there is no «inside the "
                    f"close» to send {signal.Signals(later).name} into:\n{heard()}"
                )
            child.send_signal(later)
        try:
            child.wait(timeout=GUARD_SECONDS)
        except subprocess.TimeoutExpired:
            names = [signal.Signals(number).name for number in signals]
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
            pytest.fail(f"ela serve did not exit within {GUARD_SECONDS} s of {names}:\n{heard()}")
        seconds = time.monotonic() - began
        error = heard()
        found = left(profiles)
    finally:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
        sweep(profiles, also=tuple(pid for pid, _ in started))
    return Ended(
        child.returncode,
        error,
        started,
        tuple(sorted(file.name for file in folder.glob("ela.db*"))),
        seconds,
        found,
        waiting.is_set(),
    )


def numbered(name: str) -> int:
    return int(getattr(signal, name))


def end_of(name: str) -> int:
    """How ``ela serve`` ends for whoever launched it — measured on the code before this, where a
    ``SIGINT`` was the only one of the three that reached the close: 130 after a ``SIGINT``, and
    after the other two the death that signal gives."""
    return INTERRUPTED if name == "SIGINT" else -numbered(name)


@pytest.mark.parametrize("name", SIGNALS)
def test_with_its_browser_at_work_ela_closes_whole_and_then_ends_as_the_signal_ended_it(
    name: str, tmp_path: Path, origin: str, profiles: Path
) -> None:
    """Criterion 12. A page is open when the signal arrives, and its browser is held: the stop the
    signal raises tells the page to close, **and the close is entered with that closing in
    flight** — the child says the close began to wait, and lets the browser go then. The close
    waits for it, nobody is killed, nothing it started is left, the database is one file, and
    whoever launched it sees the end of that signal."""
    ended = served("open", tmp_path / "ela", origin, profiles, numbered(name))

    assert len(ended.started) > 1, "the control: a driver and its browser were running"
    assert ended.waited, "the control: the close was entered with the closing in flight"
    assert ended.database == ("ela.db",), "the close ran: the database was released whole"
    assert ended.still_running() == []
    assert not ended.left, "and nothing of the browser is left on this machine"
    assert "killed" not in ended.error, "the browser closed by itself, and nobody was killed"
    assert ended.code == end_of(name)


THE_WHOLE = "SIGTERM"
"""The one signal after which the grace watched is ELA's own, whole: how ``pkill`` stops ELA."""


@pytest.mark.parametrize("name", SIGNALS)
def test_a_browser_that_does_not_answer_is_killed_at_the_grace_and_then_ela_ends(
    name: str, tmp_path: Path, origin: str, profiles: Path
) -> None:
    """Criterion 13. The driver is stopped: told to close, the browser does not. **At the grace**
    — the line says it ran out, and the process did not end before that time: a lower bound, which
    a slow machine only makes truer — ELA kills what the adapter had started, says it, releases
    the database, and ends as the signal ended it.

    **One of the three watches ELA's own grace, whole; the others a grace they hand ELA**
    (decision 76): the number is what the line says and what the process waited, whichever it
    is."""
    handed = None if name == THE_WHOLE else HANDED_SECONDS
    ended = served("stuck", tmp_path / "ela", origin, profiles, numbered(name), grace=handed)

    waited, line = (GRACE_SECONDS, WITHIN) if handed is None else (handed, WITHIN_THE_HANDED)
    assert ended.waited
    assert line in ended.error and "1 node" in ended.error
    assert HURRIED not in ended.error
    assert ended.seconds >= waited, "killed at the grace, not at the signal"
    assert ended.database == ("ela.db",)
    assert ended.still_running() == []
    assert not ended.left, "a killed browser leaves its profile: the adapter takes it away"
    assert ended.code == end_of(name)


def test_the_grace_one_test_watches_whole_is_the_one_ela_is_built_with() -> None:
    """The number these tests wait and read is ELA's, and the one they hand is another."""
    from ela.api import server
    from ela.composition import root

    assert GRACE_SECONDS == root.BROWSER_CLOSE_GRACE_SECONDS == server.BROWSER_CLOSE_GRACE_SECONDS
    assert HANDED_SECONDS < GRACE_SECONDS and THE_WHOLE in SIGNALS


@pytest.mark.parametrize("name", SIGNALS)
def test_a_second_signal_inside_the_close_ends_the_grace_at_once(
    name: str, tmp_path: Path, origin: str, profiles: Path
) -> None:
    """Criterion 14 (decision 55). The same browser that does not answer, and a second signal
    **sent when the close has begun to wait for it** — the child says when. During the close the
    handler is still ELA's: the signal does not kill, it ends the grace. The line says the hurry
    ended the wait. The process exits, and the end is the signal's.

    **The grace of this ELA is one no test waits out** (decision 114, 2026-10-12): with ELA's
    own five seconds the second signal had to reach the close before a real clock ran out, and
    on a loaded machine it did not — the test was red twice in a day, green alone every time,
    and a green that depends on the load is a green by chance. Now only one thing can end the
    wait: the second signal. If ELA did not hear it, the process does not exit, and the guard
    of ``served`` says so."""
    again = numbered(name)
    ended = served(
        "stuck", tmp_path / "ela", origin, profiles, again, again, grace=NO_TEST_WAITS_IT_OUT
    )

    assert ended.waited, "the control: the second signal was sent inside the close"
    assert HURRIED in ended.error and "1 node" in ended.error
    assert "did not close within" not in ended.error, "it was not the grace that ended the wait"
    assert ended.database == ("ela.db",)
    assert ended.still_running() == []
    assert not ended.left
    assert ended.code == end_of(name)
