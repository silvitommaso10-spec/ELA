"""A closing of the browser has a limit (M13.9d, ADR 0072): **no step of a tool of the browser stays
running past the tool's time and a closing with a written limit**, whatever the browser or its
driver do — die, or never answer.

On 2026-11-17 the browser of the profile died 1,28 s after its launch, in the hand proof of M13.15,
and the step stayed ``RUNNING`` for half an hour; the stop of the task did not free it, ELA's own
stop did. The cause, measured on test profiles (``docs/milestones/M13.9d.md``, «La misura»): after
the tool's time, every wait of a closing waited with no bound — and Playwright 1.63.0 leaves
without an answer a call in flight on a session of the browser when the browser dies.

**Every precondition is built, never hoped for**, on the two browsers where the case is:

* the browser dies while the door's ``deny`` travels and the file is still arriving — the browser
  stopped (``SIGSTOP``), the ``deny`` sent, **the driver's own protocol log read until it says it
  wrote it** (an event, not a duration), then ``SIGKILL``. No crash and no report on the machine:
  no test of the suite writes one (decision 89);
* the driver and the browser stopped while the file arrives, so that nothing answers any more —
  the tool's time runs out, or the task is stopped;
* the driver stopped when the launch is asked of it;
* two openings of the same browser, one whose driver answers no more;
* a download that succeeded, and whose closing meets a driver that answers no more;
* a closing that does not end even once its driver is killed — injected;
* the browser that dies before its download is announced;
* a use of a page whose driver answers no more;
* the announced file taken away even when the closing of the door does not end.

The limit is the test's own, short (:data:`LIMIT`): the composition gives ELA's,
``BROWSER_CLOSE_GRACE_SECONDS``.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import subprocess
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import pytest
from playwright.async_api._context_manager import PlaywrightContextManager

from ela.domain import ExecutionResult, ExecutionStatus
from ela.infrastructure.machine import browser as adapter
from ela.infrastructure.machine.account import AccountChrome
from ela.permissions import BROWSER_DOWNLOAD, BROWSER_DOWNLOAD_AS_YOU
from ela.ports import BrowserFailed, Downloaded
from ela.testing.fakes import FakeIdGenerator, FakeStop, FakeTaskPages
from ela.tools.browser import FAILED, STOPPED, TIMEOUT
from ela.tools.browser_files import AccountDownloadTool, BrowserDownloadTool
from tests.browser_leftovers import running
from tests.infrastructure.machine import test_account_browser as account
from tests.infrastructure.machine import test_the_boundary as bounds
from tests.infrastructure.machine.test_browser import CLOCK, decision
from tests.infrastructure.machine.test_the_files_of_a_page import (
    FILE,
    SITE,
    Slow,
    browsing,
    folder,
    root,
    sites,
)

served = bounds.served
nothing_left_behind = bounds.nothing_left_behind
judged = bounds.judged
profile = account.profile
only, until = bounds.only, bounds.until

LIMIT: Final = 2.0
"""The limit of a closing these tests give their browsers, in seconds. Short, and above the
longest healthy closing measured under the load of the suite (decision 92 of M13.9d)."""
TOOL: Final = 3
"""The tool's time of a step whose time runs out before the browser is launched."""
ARRIVING_TOOL: Final = 10
"""The tool's time of a step whose time runs out while its file arrives: room for the launch of
the browser of the profile under the load of the suite (4,53 s the longest, measured in
M13.9d's registration), and then the time runs out."""
LONG_TOOL: Final = 30
"""The tool's time of a step that must end before it: ELA's own."""
WITHIN: Final = LIMIT + adapter.GONE_SECONDS + LIMIT
"""How long after its cancellation a step may last: the limit; the kill, whose wait for the
kernel is bounded by ``GONE_SECONDS``; and the limit again, for what the kill did not end. The
written bound of ADR 0072, not a measure."""
OTHERS: Final = "di-qualcun-altro.crdownload"
"""A file of somebody else's in the folder of the download, whose name ends as the browser's
files do while they arrive: it stays — what ELA takes away it takes by identifier, never by
resemblance (decision 91)."""
ARGUMENTS: Final = {
    "site": SITE,
    "path": "/slow.bin",
    "file": "ELA/prova/il-file.bin",
    "overwrite": False,
    "purpose": "la prova di M13.9d",
}
DENY: Final = '"behavior":"deny"'


@dataclass
class Made:
    """A browser of these tests, with its limit, and what it said it killed."""

    browser: Any
    killed: list[tuple[str, ...]] = field(default_factory=list)


@pytest.fixture(params=[bounds.EMPTY, pytest.param(bounds.PROFILE, marks=bounds.ON_A_MAC)])
async def made(request: pytest.FixtureRequest, nothing_left_behind: None) -> AsyncIterator[Made]:
    """Each of the two browsers, with :data:`LIMIT`: the folder of the profile is taken only for
    the browser of the profile."""
    said: list[tuple[str, ...]] = []
    if request.param == bounds.EMPTY:
        browser: Any = bounds.empty(closing=LIMIT, killed=said.append)
    else:
        browser = account.chrome(
            request.getfixturevalue("profile"), closing=LIMIT, killed=said.append
        )
    yield Made(browser, said)
    for page in list(browser._pages):
        await browser.close(page)


def _parents() -> dict[int, int]:
    printed = subprocess.run(
        ["/bin/ps", "-A", "-o", "pid=,ppid="], capture_output=True, text=True, check=True
    ).stdout
    rows = [line.split() for line in printed.splitlines()]
    return {int(row[0]): int(row[1]) for row in rows if len(row) == 2}


def tree(drivers: list[int]) -> list[int]:
    """The drivers and everything they started, as the kernel says it now: by parentage."""
    parents = _parents()
    found, todo = list(drivers), list(drivers)
    while todo:
        one = todo.pop()
        for pid, parent in parents.items():
            if parent == one and pid not in found:
                found.append(pid)
                todo.append(pid)
    return found


def browsers_of(drivers: list[int]) -> list[int]:
    """The main process of each browser the drivers started."""
    return [pid for pid, parent in _parents().items() if parent in drivers]


def signalled(pids: list[int], number: signal.Signals) -> None:
    for pid in pids:
        try:
            os.kill(pid, number)
        except ProcessLookupError:
            continue


def left_running(pids: list[int]) -> list[int]:
    return [pid for pid in pids if running(pid)]


async def ended_within(
    step: asyncio.Future[Any], seconds: float, frozen: list[int], what: str
) -> None:
    """``step`` ended within ``seconds`` — **or ELA stayed hung**: then what was frozen is killed
    by pid, so that the test ends, and the test fails saying so."""
    done, _ = await asyncio.wait({step}, timeout=seconds)
    if done:
        return
    signalled(frozen, signal.SIGKILL)
    await asyncio.wait({step}, timeout=bounds.LONG)
    pytest.fail(f"ELA stayed hung: {what} had not ended {seconds:g} s after its cause")


def download_tool(browser: Any, origin: str, seconds: int, tmp_path: Path) -> tuple[Any, str, Path]:
    """The real tool of ``browser.download`` or ``browser.download_as_you``, and the folder its file
    goes to — with a file of somebody else's in it."""
    under = root(tmp_path)
    kind = AccountDownloadTool if isinstance(browser, AccountChrome) else BrowserDownloadTool
    capability = BROWSER_DOWNLOAD_AS_YOU if isinstance(browser, AccountChrome) else BROWSER_DOWNLOAD
    tool = kind(
        under,
        browsing(origin, seconds),
        browser,
        CLOCK,
        FakeIdGenerator(),
        pages=FakeTaskPages(),
        protected={},
    )
    into = under / "ELA" / "prova"
    into.mkdir()
    (into / OTHERS).write_bytes(b"di qualcun altro")
    return tool, capability, into


async def started(tool: Any, capability: str, stop: FakeStop) -> asyncio.Future[ExecutionResult]:
    prospect = await tool.prospect(ARGUMENTS)
    assert prospect.refusal is None, prospect.refusal
    return asyncio.ensure_future(
        tool.execute(decision(capability), ARGUMENTS, stop, prospect.named or {})
    )


def door_of(browser: Any) -> Any:
    (opened,) = browser._pages.values()
    return opened.door


def arriving(browser: Any, into: Path) -> bool:
    """The download the gesture started is in the folder, under the name the browser gave it."""
    if len(browser._pages) != 1:
        return False
    asked = door_of(browser).asked
    return bool(asked) and any((into / name).exists() for name in (asked, f"{asked}.crdownload"))


def sentinel(browser: Any) -> Path | None:
    """A file in the folder of the profile, for the browser of the profile: what a kill leaves."""
    if not isinstance(browser, AccountChrome):
        return None
    made = browser._profile / "ela-sentinella"
    made.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    made.write_text("resta")
    return made


# ----------------------------------------------------------------------------------------------
# The browser that dies while the deny of the door travels
# ----------------------------------------------------------------------------------------------


async def test_a_browser_that_dies_with_the_deny_in_flight_is_said_at_once_and_its_file_goes(
    made: Made, served: list[Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**The precondition of 2026-11-17, built with no crash.** The browser dies while the door's
    ``deny`` travels and the file is still arriving: the step ends at once — not at the tool's
    time — with ``browser.failed``, «the browser ended by itself»; what the browser had announced
    for the gesture is taken away, and a file of somebody else's stays.

    **It asserts the fact of Playwright it stands on** (decision 95): when ELA asks the driver to
    stop, the ``deny`` is still without an answer. The day an update of Playwright answers it when
    the browser dies, this test is red and says so, instead of passing for another reason."""
    log = tmp_path / "protocol.log"
    monkeypatch.setenv("DEBUG", "pw:protocol")
    monkeypatch.setenv("DEBUG_FILE", str(log))
    slow = Slow()
    served.append(slow)
    browser = made.browser
    tool, capability, into = download_tool(browser, slow.origin, LONG_TOOL, tmp_path)
    denying = adapter._Door.shut
    sending: list[asyncio.Future[Any]] = []
    killed_at: list[float] = []
    written: list[bool] = []
    frozen: list[int] = []

    def denies() -> int:
        return log.read_text(errors="replace").count(DENY) if log.exists() else 0

    async def dying(door: Any) -> None:
        if sending or door._state != "closing":
            return await denying(door)
        frozen.extend(browsers_of(browser._driver_pids()))
        signalled(frozen, signal.SIGSTOP)
        before = denies()
        sending.append(asyncio.ensure_future(denying(door)))
        await until(lambda: denies() > before, "the driver's log saying it wrote the deny")
        written.append(arriving(browser, into))
        signalled(frozen, signal.SIGKILL)
        killed_at.append(asyncio.get_running_loop().time())
        await sending[0]

    monkeypatch.setattr(adapter._Door, "shut", dying)
    unanswered: list[bool] = []
    stopping = PlaywrightContextManager.__aexit__

    async def stopped(manager: Any, *args: Any) -> None:
        if sending and not unanswered:
            unanswered.append(not sending[0].done())
        await stopping(manager, *args)

    monkeypatch.setattr(PlaywrightContextManager, "__aexit__", stopped)

    step = await started(tool, capability, FakeStop())
    await until(lambda: killed_at, "the browser killed with the deny in flight")
    await ended_within(
        step, WITHIN, [*browser._driver_pids(), *frozen], "the step of a browser that died"
    )

    assert unanswered == [True], (
        "the precondition was not built: Playwright answered the deny in flight before ELA "
        "stopped the driver — the fact ADR 0072 stands on is gone"
    )
    assert written == [True], "the browser had not written its file when it died"
    result = step.result()
    assert result.status is ExecutionStatus.FAILED, result
    assert result.error is not None and result.error.code == FAILED, result.error
    assert adapter.ENDED in result.error.message
    assert sorted(os.listdir(into)) == [OTHERS]
    assert made.killed == []


# ----------------------------------------------------------------------------------------------
# A driver and a browser that answer no more
# ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("ended_by", ["the tool's time", "the stop of the task"])
async def test_a_driver_and_a_browser_that_answer_no_more_are_killed_at_the_limit(
    made: Made, served: list[Any], tmp_path: Path, ended_by: str
) -> None:
    """The file arrives, and the driver and the browser stop answering: **the step ends within the
    limit of its cause** — the tool's time, or the stop of the task, which takes the same road
    (decision 82) —, with the code of that cause. At the limit the driver and everything it
    started are killed, by parentage; what the browser had announced is taken away, a file of
    somebody else's stays, the folder of the profile stays — and a page opens on it again."""
    slow = Slow()
    served.append(slow)
    browser = made.browser
    kept = sentinel(browser)
    seconds = ARRIVING_TOOL if ended_by == "the tool's time" else LONG_TOOL
    tool, capability, into = download_tool(browser, slow.origin, seconds, tmp_path)
    stop = FakeStop()

    step = await started(tool, capability, stop)
    began = asyncio.get_running_loop().time()
    await until(lambda: slow.half_sent.is_set() and arriving(browser, into), "half a file")
    frozen = tree(browser._driver_pids())
    signalled(frozen, signal.SIGSTOP)
    if ended_by == "the stop of the task":
        stop.event.set()
        cause = asyncio.get_running_loop().time()
    else:
        cause = began + ARRIVING_TOOL
    await ended_within(step, cause + WITHIN - asyncio.get_running_loop().time(), frozen, "the step")

    result = step.result()
    code = TIMEOUT if ended_by == "the tool's time" else STOPPED
    assert result.error is not None and result.error.code == code, result.error
    assert left_running(frozen) == []
    assert sorted(os.listdir(into)) == [OTHERS]
    assert len(made.killed) == 1 and adapter.DRIVER in made.killed[0], made.killed
    if kept is not None:
        assert kept.read_text() == "resta"
        again = await browser.open(slow.origin + "/", only(slow), FakeStop())
        await browser.close(again.page)


@pytest.mark.parametrize("ended_by", ["the tool's time", "the stop of the task"])
async def test_a_driver_that_never_answers_the_launch_is_killed_at_the_limit(
    made: Made, served: list[Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ended_by: str
) -> None:
    """The driver stopped when the launch is asked of it — the silence of a driver, built: no
    answer to the launch, none to its abort, and no closing begun. **Only the guard ends it**:
    the tool's time or the stop of the task — the same road (decision 82) — cancels the opening,
    and at the limit the driver is killed."""
    browser = made.browser
    a, _ = sites(served)
    seconds = TOOL if ended_by == "the tool's time" else LONG_TOOL
    tool, capability, _into = download_tool(browser, a.origin, seconds, tmp_path)
    kind = type(browser)
    launching = kind._begun
    frozen: list[int] = []

    async def frozen_first(self: Any, playwright: Any) -> Any:
        frozen.extend(self._driver_pids())
        signalled(frozen, signal.SIGSTOP)
        return await launching(self, playwright)

    monkeypatch.setattr(kind, "_begun", frozen_first)
    stop = FakeStop()

    step = await started(tool, capability, stop)
    began = asyncio.get_running_loop().time()
    if ended_by == "the stop of the task":
        await until(lambda: frozen, "the driver stopped when the launch is asked of it")
        stop.event.set()
        cause = asyncio.get_running_loop().time()
    else:
        cause = began + TOOL
    await ended_within(step, cause + WITHIN - asyncio.get_running_loop().time(), frozen, "the step")

    result = step.result()
    code = TIMEOUT if ended_by == "the tool's time" else STOPPED
    assert result.error is not None and result.error.code == code, result.error
    assert frozen and left_running(frozen) == []
    assert made.killed == [(adapter.DRIVER,)]


# ----------------------------------------------------------------------------------------------
# One opening kills its own driver, and nothing else
# ----------------------------------------------------------------------------------------------


async def test_an_opening_kills_only_its_own_driver(
    nothing_left_behind: None, served: list[Any]
) -> None:
    """Two pages of the same empty browser: the driver and the browser of the first answer no
    more, and its close kills them at the limit; **the second goes on**, read and closed as
    ever. The browser of the profile holds one opening at a time (``ProfileBusy``): the case is
    not there."""
    said: list[tuple[str, ...]] = []
    browser = bounds.empty(closing=LIMIT, killed=said.append)
    a, _ = sites(served)
    a.pages[("GET", "/")] = (200, bounds.HTML, '<p id="x">uno</p>')
    first = await browser.open(a.origin + "/", only(a), FakeStop())
    mine = browser._driver_pids()
    second = await browser.open(a.origin + "/", only(a), FakeStop())
    (theirs,) = set(browser._driver_pids()) - set(mine)
    frozen = tree(mine)
    signalled(frozen, signal.SIGSTOP)

    closing = asyncio.ensure_future(browser.close(first.page))
    await ended_within(closing, WITHIN, frozen, "the close of the first page")

    assert left_running(frozen) == []
    assert running(theirs)
    assert await browser.text(second.page, "#x") == "uno"
    await browser.close(second.page)
    assert len(said) == 1 and said[0].count(adapter.DRIVER) == 1, said


# ----------------------------------------------------------------------------------------------
# What succeeded stays so
# ----------------------------------------------------------------------------------------------


async def test_a_download_that_succeeded_stays_so_when_its_closing_is_killed(
    made: Made, served: list[Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The file arrived whole; then the driver and the browser answer no more, and the closing of
    the page meets them. **The download returns as it is** — the file is there —, and the kill
    is said (decision 93)."""
    browser = made.browser
    a, _ = sites(served)
    into = folder(tmp_path)
    finishing = adapter._Door.done
    frozen: list[int] = []

    async def then_frozen(door: Any, place: Path, *, kept: bool) -> None:
        await finishing(door, place, kept=kept)
        if kept and not frozen:
            frozen.extend(tree(browser._driver_pids()))
            signalled(frozen, signal.SIGSTOP)

    monkeypatch.setattr(adapter._Door, "done", then_frozen)

    downloading = asyncio.ensure_future(
        browser.downloaded_from(a.origin + "/file.bin", only(a), FakeStop(), str(into))
    )
    await until(lambda: frozen, "the driver and the browser stopped once the file arrived")
    await ended_within(downloading, WITHIN, frozen, "the download whose closing was stopped")

    got = downloading.result()
    assert isinstance(got, Downloaded)
    assert (into / got.name).read_bytes() == FILE
    assert left_running(frozen) == []
    assert len(made.killed) == 1 and adapter.DRIVER in made.killed[0], made.killed


# ----------------------------------------------------------------------------------------------
# What does not end even after the kill
# ----------------------------------------------------------------------------------------------


async def test_a_closing_that_does_not_end_even_after_the_kill_is_left_and_said(
    nothing_left_behind: None, served: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A closing that waits for something no kill ends — injected: the branch of the guard
    that leaves a task (decision 93). The close returns within the written bound; the line of the
    kill names what was left; and **ELA's close does not wait for it**."""
    said: list[tuple[str, ...]] = []
    stopping = asyncio.Event()
    browser = bounds.empty(stopping, closing=LIMIT, killed=said.append)
    a, _ = sites(served)
    opened = await browser.open(a.origin + "/links", only(a), FakeStop())
    never = asyncio.Event()

    async def never_ending(page: Any) -> None:
        # Deaf to the cancellation too: what the limit leaves is left, not ended.
        while not never.is_set():
            with contextlib.suppress(asyncio.CancelledError):
                await never.wait()

    monkeypatch.setattr(adapter, "_shut", never_ending)
    killed = tree(browser._driver_pids())

    closing = asyncio.ensure_future(browser.close(opened.page))
    try:
        await ended_within(closing, WITHIN, killed, "the close of a page whose closing never ends")
        assert left_running(killed) == []
        assert len(said) == 1 and adapter.LEFT in said[0], said
        stopping.set()
        settling = asyncio.ensure_future(browser.settle(lambda: asyncio.sleep(LIMIT)))
        await ended_within(settling, WITHIN, [], "ELA's close of the browser")
        assert settling.result() == ()
    finally:
        never.set()


# ----------------------------------------------------------------------------------------------
# The other parts of the guard: the end before the announcement, a use of a page, the door's
# closing that never ends
# ----------------------------------------------------------------------------------------------

NOTHING: Final = '<button id="nothing">niente</button>'
"""A page whose button starts nothing: the wait for the download's announcement does not end."""


async def test_a_browser_that_dies_before_its_download_is_announced_is_said_at_once(
    made: Made, served: list[Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gesture is made, and the browser dies while ELA waits for what it led to — an
    announcement, a page, a refusal: none comes from a browser that died. **The wait wakes at
    the end of the browser** (decision 81), and the download says it at once."""
    browser = made.browser
    a, _ = sites(served)
    a.pages[("GET", "/")] = (200, bounds.HTML, NOTHING)
    into = folder(tmp_path)
    waiting = asyncio.Event()
    first_of = adapter.PlaywrightBrowser._first_of

    async def told(self: Any, opened: Any, *events: asyncio.Event) -> None:
        waiting.set()
        await first_of(self, opened, *events)

    monkeypatch.setattr(adapter.PlaywrightBrowser, "_first_of", told)
    opened = await browser.open(a.origin + "/", only(a), FakeStop())

    downloading = asyncio.ensure_future(
        browser.download(opened.page, "#nothing", FakeStop(), str(into))
    )
    await until(waiting.is_set, "the wait for what the gesture led to")
    dead = browsers_of(browser._driver_pids())
    signalled(dead, signal.SIGKILL)
    await ended_within(downloading, WITHIN, dead, "the download of a browser that died")

    with pytest.raises(BrowserFailed, match=adapter.ENDED):
        downloading.result()
    assert os.listdir(into) == []


async def test_a_use_of_a_page_whose_driver_answers_no_more_is_killed_at_its_limit(
    made: Made, served: list[Any]
) -> None:
    """A use of a page — the wait for an element — whose driver and browser answer no more,
    cancelled by whoever waited for it: **the guard kills the driver of that page**, the one it
    was told the use asked (``_used``), and leaves nothing."""
    browser = made.browser
    a, _ = sites(served)
    a.pages[("GET", "/")] = (200, bounds.HTML, NOTHING)
    opened = await browser.open(a.origin + "/", only(a), FakeStop())
    frozen = tree(browser._driver_pids())
    signalled(frozen, signal.SIGSTOP)

    waiting = asyncio.ensure_future(
        asyncio.wait_for(browser.appeared(opened.page, "#never"), timeout=1.0)
    )
    await ended_within(waiting, 1.0 + WITHIN, frozen, "a use of a page whose driver was stopped")

    with pytest.raises(TimeoutError):
        waiting.result()
    assert left_running(frozen) == []
    assert len(made.killed) == 1 and adapter.DRIVER in made.killed[0], made.killed
    assert adapter.LEFT not in made.killed[0]


async def test_the_announced_file_goes_even_when_the_door_s_closing_does_not_end(
    made: Made, served: list[Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The file arrives, the download is cancelled, and the door's closing does not end — not
    even once the browser is killed: injected. **What the browser had announced goes all the
    same**, from the disk, by the limit (decision 91); a file of somebody else's stays."""
    slow = Slow()
    served.append(slow)
    browser = made.browser
    into = folder(tmp_path)
    (into / OTHERS).write_bytes(b"di qualcun altro")
    never = asyncio.Event()

    async def never_done(door: Any, place: Path, *, kept: bool) -> None:
        while not never.is_set():
            with contextlib.suppress(asyncio.CancelledError):
                await never.wait()

    monkeypatch.setattr(adapter._Door, "done", never_done)

    downloading = asyncio.ensure_future(
        browser.downloaded_from(slow.origin + "/slow.bin", only(slow), FakeStop(), str(into))
    )
    try:
        await until(lambda: slow.half_sent.is_set() and arriving(browser, into), "half a file")
        killed = tree(browser._driver_pids())
        downloading.cancel()
        await ended_within(downloading, WITHIN, killed, "a download whose door never closes")

        assert sorted(os.listdir(into)) == [OTHERS]
        assert left_running(killed) == []
        assert any(adapter.LEFT in names for names in made.killed), made.killed
    finally:
        never.set()


for _name, _test in list(globals().items()):
    if _name.startswith("test_") and asyncio.iscoroutinefunction(_test):
        globals()[_name] = bounds.bounded(_test)
