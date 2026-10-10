"""ELA's close: when it returns, nothing of the browser runs any more (M13.4e, decision 51).

Until M13.4e the close released the database and waited for nobody. The task that closes every
page at ELA's stop was nobody's to wait for: if the loop was torn down while one of its calls of
Playwright was in flight, that call was cancelled, waited for an answer the cancelled reader of the
pipe never delivered, and **``asyncio.run`` did not return** — the process stayed, with its driver
and its browser alive (measured, ``docs/milestones/M13.4e.md``).

Two kinds of test, because two things are asserted:

* **a process exits** — so the ELA under test is a process of its own
  (``tests/composition/closing.py``), with the real browser, closed with a call in flight, with and
  without the ``SIGINT`` uvicorn raises again; and what it had started is gone when it has exited;
* **what the close does, in which order, and that it runs to its end whoever cancels it** — with a
  browser that records, in this process, because ``ela.composition`` is inside the gate.

The guard of the first kind is the test's and never the one that fires: an ELA that does not exit
fails there, after having been killed with its own session and nothing else.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import threading
from collections.abc import Awaitable, Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from ela.composition import Ela, Settings, build
from ela.testing.fakes import FakeBrowser, FakePower
from tests.composition.closing import INTERRUPTED
from tests.composition.support import create_schema, database_url, declare

CHILD = Path(__file__).with_name("closing.py")
ROOT = CHILD.parents[2]
GUARD_SECONDS = 60
PAGE = b'<form><input id="nome" name="nome" disabled><button id="invia">Invia</button></form>'
POSIX = pytest.mark.skipif(sys.platform == "win32", reason="a session and SIGINT are POSIX's")


@pytest.fixture
def origin() -> Iterator[str]:
    """A page of the test's own, on ``127.0.0.1``: a form whose field cannot be written yet."""

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


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def closed(mode: str, folder: Path, origin: str) -> tuple[int, list[tuple[int, str]]]:
    """Run an ELA that closes in ``mode``: its exit code, and what its browser had started.

    The child is the leader of a session of its own, so a child that does not exit is killed with
    its group — and nothing else of this machine — before the test fails.
    """
    folder.mkdir()
    child = subprocess.Popen(
        [sys.executable, str(CHILD), mode, str(folder), origin],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
        cwd=ROOT,
    )
    try:
        out, err = child.communicate(timeout=GUARD_SECONDS)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        child.communicate()
        pytest.fail(
            f"ELA closed with «{mode}» and did not exit within {GUARD_SECONDS} s: the loop was "
            "torn down with a call of the browser's in flight"
        )
    rows = [json.loads(line) for line in out.splitlines() if line.startswith("{")]
    assert rows, f"the child said nothing before its close:\n{err}"
    return child.returncode, [(pid, name) for pid, name in rows[0]["started"]]


# ----------------------------------------------------------------------------------------
# A process exits, and nothing it started is left
# ----------------------------------------------------------------------------------------


@POSIX
@pytest.mark.parametrize("mode", ["close", "fill"])
def test_an_ela_closed_with_its_browser_at_work_exits_and_leaves_no_process(
    mode: str, tmp_path: Path, origin: str
) -> None:
    code, started = closed(mode, tmp_path / "ela", origin)

    assert code == 0
    assert "node" in [name for _, name in started], "the control: a driver was running"
    assert [name for pid, name in started if alive(pid)] == []


@POSIX
@pytest.mark.parametrize("mode", ["close-sigint", "fill-sigint"])
def test_a_close_entered_with_a_cancellation_pending_still_closes_the_browser(
    mode: str, tmp_path: Path, origin: str
) -> None:
    """After a Ctrl-C uvicorn raises the ``SIGINT`` again when ``serve`` returns, and the handler
    of ``asyncio.run`` cancels the task that is about to close ELA. The close runs to its end all
    the same, gives the cancellation back, and the process ends as it ends today after a Ctrl-C."""
    code, started = closed(mode, tmp_path / "ela", origin)

    assert code == INTERRUPTED
    assert "node" in [name for _, name in started]
    assert [name for pid, name in started if alive(pid)] == []


@POSIX
@pytest.mark.parametrize(("mode", "code"), [("pool", 0), ("pool-sigint", INTERRUPTED)])
def test_the_database_is_released_whole_after_a_ctrl_c_too(
    mode: str, code: int, tmp_path: Path, origin: str
) -> None:
    """What the database's release gains (decision 51). With more than one connection in the pool
    a close cancelled at its first wait closed one and left the others: the write-ahead log was
    not written back, and whoever copied ``ela.db`` alone did not have the last writes."""
    folder = tmp_path / "ela"

    exited, _ = closed(mode, folder, origin)

    assert sorted(file.name for file in folder.glob("ela.db*")) == ["ela.db"]
    assert exited == code


# ----------------------------------------------------------------------------------------
# What the close does, in which order, and that it runs to its end
# ----------------------------------------------------------------------------------------


class Settling(FakeBrowser):
    """A browser that says what it found when ELA asked it to settle."""

    def __init__(self, stopping: Callable[[], bool], usable: Callable[[], Awaitable[bool]]) -> None:
        super().__init__()
        self._stopping = stopping
        self._usable = usable
        self.found: list[tuple[bool, bool]] = []
        self.reached = asyncio.Event()
        self.released = asyncio.Event()
        self.released.set()
        self.failing: Exception | None = None

    async def settle(self, grace: Callable[[], Awaitable[None]]) -> tuple[str, ...]:
        self.found.append((self._stopping(), await self._usable()))
        self.reached.set()
        await self.released.wait()
        if self.failing is not None:
            raise self.failing
        return await super().settle(grace)


async def an_ela(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Ela, Settling]:
    declare(monkeypatch, tmp_path)
    await create_schema(database_url(tmp_path))
    made: list[Ela] = []

    async def usable() -> bool:
        async with made[0].database.connect() as connection:
            return (await connection.exec_driver_sql("select 1")).scalar() == 1

    browser = Settling(lambda: made[0].stopping.is_set(), usable)
    made.append(await build(Settings.load(), power=FakePower(), browser=browser))
    return made[0], browser


def pooled(ela: Ela) -> int:
    return int(ela.database.pool.checkedin())  # type: ignore[attr-defined]


async def test_the_close_raises_the_stop_settles_the_browser_and_then_releases_the_database(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ela, browser = await an_ela(monkeypatch, tmp_path)
    assert ela.browser is browser and not ela.stopping.is_set()

    await ela.aclose()

    assert ela.stopping.is_set(), "closing is stopping: nobody had raised the stop"
    assert browser.found == [(True, True)], (
        "the browser is settled after the stop, and while the database still answers"
    )
    assert pooled(ela) == 0, "and then the database is released"


async def test_the_grace_of_the_close_is_the_one_the_composition_declares(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from ela.composition.root import BROWSER_CLOSE_GRACE_SECONDS

    ela, browser = await an_ela(monkeypatch, tmp_path)
    await ela.aclose()
    waited: list[float] = []

    async def sleep(seconds: float) -> None:
        waited.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", sleep)
    (grace,) = browser.settled
    await grace()

    assert waited == [BROWSER_CLOSE_GRACE_SECONDS] == [5]


async def test_what_the_browser_had_to_kill_is_handed_to_whoever_closes_ela_and_nothing_otherwise(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ela, browser = await an_ela(monkeypatch, tmp_path)
    told: list[tuple[str, ...]] = []

    await ela.aclose(killed=told.append)
    assert told == [], "a browser that closed by itself is nothing to say"

    browser.killed = ("node", "chrome-headless-shell")
    await ela.aclose(killed=told.append)
    await ela.aclose()

    assert told == [("node", "chrome-headless-shell")]
    assert len(browser.settled) == 3, (
        "closing again settles again: it is idempotent, not remembered"
    )


async def test_a_close_entered_with_a_cancellation_pending_runs_to_its_end_and_gives_it_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ela, browser = await an_ela(monkeypatch, tmp_path)

    async def served() -> None:
        task = asyncio.current_task()
        assert task is not None
        try:
            task.cancel()  # what the handler of ``asyncio.run`` does to the task ``_serve`` runs in
        finally:
            await ela.aclose()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.create_task(served())

    assert browser.found == [(True, True)]
    assert pooled(ela) == 0


async def test_a_close_cancelled_twice_while_the_browser_settles_still_runs_to_its_end(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ela, browser = await an_ela(monkeypatch, tmp_path)
    browser.released.clear()
    closing = asyncio.create_task(ela.aclose())
    async with asyncio.timeout(
        5
    ):  # the test's guard: a close that never asks the browser fails here
        await browser.reached.wait()

    closing.cancel()
    await asyncio.sleep(0)
    closing.cancel()
    await asyncio.sleep(0)
    assert not closing.done(), "cancelled, and still waiting for its own closing"
    browser.released.set()
    with pytest.raises(asyncio.CancelledError):
        await closing

    assert pooled(ela) == 0, "the database was released after the browser, not instead of it"


async def test_a_browser_that_cannot_be_settled_does_not_keep_the_database_open(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ela, browser = await an_ela(monkeypatch, tmp_path)
    browser.failing = RuntimeError("a browser that could not be settled")

    with pytest.raises(RuntimeError, match="could not be settled"):
        await ela.aclose()

    assert pooled(ela) == 0
