"""A download and the guard of the disk (M13.17, ADR 0074 §7; decision 52 of the review of its
SPEC): the two waits of a download that come after the look — making the folder, placing the
file —, each given up at the limit.

- **A folder the disk does not make** answers ``fs.no_answer`` before the gesture: no folder, and
  nothing asked of the browser.
- **A placing given up** answers ``fs.no_answer`` with its one gesture; and when the disk answers,
  **nothing of what the browser wrote stays** — the file it left under a name of its own is taken
  away, as for a download that fell (ADR 0070): the abandoned work never gives it the plan's name.

The disk that does not answer is built by injection, as in
``tests/tools/test_the_disk_that_does_not_answer.py``: the second look at the target — the one
right before the file is placed — waits on an event the test holds.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from ela.domain import ExecutionStatus
from ela.testing.fakes import FakeBrowser, FakeIdGenerator, FakePage, FakeStop, FakeTaskPages
from ela.tools import browser_files
from ela.tools.browser_files import BROWSER_DOWNLOAD, BrowserDownloadTool
from ela.tools.disk import NO_ANSWER, Disk, DiskSilent
from tests.tools.test_browser_files import BYTES, CLOCK, DOWNLOAD, SITES, decision, root, with_
from tests.tools.test_the_disk_that_does_not_answer import LIMIT, guards


class SilentAt(Disk):
    """The guard of a disk that answers every wait but the ``at``-th, which it gives up at once."""

    def __init__(self, at: int) -> None:
        super().__init__(limit=LIMIT)
        self.at = at
        self.runs = 0

    async def run[T](self, work: Callable[[Any], T], what: str) -> T:
        self.runs += 1
        if self.runs == self.at:
            raise DiskSilent(f"{what}: the disk did not answer within {LIMIT:g} s")
        return await super().run(work, what)


def a_tool(folder: Path, browser: FakeBrowser, disk: Disk) -> BrowserDownloadTool:
    return BrowserDownloadTool(
        folder,
        SITES,
        browser,
        CLOCK,
        FakeIdGenerator(),
        protected={},
        pages=FakeTaskPages(),
        disk=disk,
    )


async def test_a_folder_the_disk_does_not_make_ends_the_step_before_the_gesture(
    tmp_path: Path,
) -> None:
    folder = root(tmp_path)
    browser = FakeBrowser(FakePage(download=BYTES))
    disk = SilentAt(2)
    arguments = with_(DOWNLOAD, file="ELA/nuova/scaricato.bin")

    result = await a_tool(folder, browser, disk).execute(
        decision(BROWSER_DOWNLOAD), arguments, FakeStop()
    )

    assert disk.runs == 2, "the look answered; the folder was the wait given up"
    assert result.error is not None and result.error.code == NO_ANSWER
    assert result.output["gestures"] == 0
    assert browser.downloads == [] and browser.opened == []
    assert not (folder / "ELA" / "nuova").exists()


async def test_a_placing_given_up_leaves_nothing_of_what_the_browser_wrote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = root(tmp_path)
    browser = FakeBrowser(FakePage(download=BYTES))
    released = threading.Event()
    real = browser_files.looked_for_a_write
    calls: list[int] = []

    def held(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        if len(calls) == 2:  # the look again, right before the file is placed
            released.wait()
        return real(*args, **kwargs)

    monkeypatch.setattr(browser_files, "looked_for_a_write", held)
    try:
        result = await a_tool(folder, browser, Disk(limit=LIMIT)).execute(
            decision(BROWSER_DOWNLOAD), DOWNLOAD, FakeStop()
        )
    finally:
        released.set()
        for thread in guards():
            thread.join(10)

    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None and result.error.code == NO_ANSWER
    assert result.output["gestures"] == 1
    assert browser.downloads != [], "the browser did write the file"
    assert sorted(one.name for one in (folder / "ELA" / "prova").iterdir()) == []
