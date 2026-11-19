"""The guard of the disk (M13.17, ADR 0074; decision 12 of its starting block, answers 34 and 40,
decisions 52 and 53 of the review of its SPEC).

A disk that does not answer is **built by injection** (decision 26): the functions the tools call
are wrapped so that they wait on an event the test holds, in the guard's thread. Nothing here
waits on a clock to know that something happened: a released wait is joined, a standing one is
counted by the guard itself.

- **A wait has a limit**, and the Core answers while it lasts: the tool returns ``fs.no_answer``
  within the limit, for a look, a read and a write.
- **At most four abandoned waits stand** (answer 40): the fifth is refused at once, without a
  thread; released, the count falls and a look succeeds again.
- **A write abandoned while it was looking never writes** (decision 52); one abandoned inside the
  write may still land, and its sentence says so.
- **``fs.no_answer`` is not retried** (decision 53), and **a «stop» during a wait waits at most the
  limit**.
- **The start-up's guard** (:func:`within_the_limit`) answers, passes an error on, and gives up at
  its limit.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from ela.domain import (
    CapabilityId,
    DecisionId,
    ExecutionStatus,
    PermissionDecision,
    PermissionOutcome,
    RiskLevel,
)
from ela.ports import ToolStopped
from ela.testing.fakes import FakeClock, FakeIdGenerator, FakeStop
from ela.tools import fs as fs_module
from ela.tools.disk import (
    ABANDONED_MOST,
    DISK_LIMIT_SECONDS,
    MAKING_THE_FOLDER,
    NO_ANSWER,
    WRITING,
    Abandoned,
    Disk,
    DiskSilent,
    Gone,
    within_the_limit,
)
from ela.tools.fs import FS_READ, FS_WRITE, FsReadTool, FsWriteTool

NOW = datetime(2026, 11, 18, 10, 0, tzinfo=UTC)
LIMIT = 0.2
"""A short limit, given by the test: what is asserted — the wait is given up at the limit and not
after — is as true of a fifth of a second as of ten seconds."""


def decision(capability_id: CapabilityId) -> PermissionDecision:
    return PermissionDecision(
        id=DecisionId(FakeIdGenerator().new_uuid()),
        created_at=NOW,
        capability_id=capability_id,
        risk=RiskLevel.HIGH,
        outcome=PermissionOutcome.ALLOWED,
        reason="allowed for this test",
        expires_at=NOW.replace(hour=11),
    )


@pytest.fixture
def root(tmp_path: Path) -> Path:
    declared = tmp_path / "files"
    (declared / "ELA").mkdir(parents=True)
    (declared / "ELA" / "c'è.md").write_text("già qui\n")
    return declared


def guards() -> list[threading.Thread]:
    return [one for one in threading.enumerate() if one.name == "ela-disk"]


@contextmanager
def a_disk_that_does_not_answer(
    monkeypatch: pytest.MonkeyPatch, name: str, module: Any = fs_module
) -> Iterator[threading.Event]:
    """``module.name`` waits on the event before it does what it does: the disk does not answer
    until the test releases it. On the way out the event is set and every thread of the guard
    joined, so no wait outlives its test."""
    released = threading.Event()
    real = getattr(module, name)

    def held(*args: Any, **kwargs: Any) -> Any:
        released.wait()
        return real(*args, **kwargs)

    monkeypatch.setattr(module, name, held)
    try:
        yield released
    finally:
        released.set()
        for thread in guards():
            thread.join(10)


# ----------------------------------------------------------------------------------------
# The guard itself
# ----------------------------------------------------------------------------------------


async def test_a_wait_that_answers_gives_its_value_and_passes_its_error_on() -> None:
    disk = Disk(limit=LIMIT)

    def fails(_: Gone) -> None:
        raise OSError("refused")

    assert await disk.run(lambda _: 42, "a look") == 42
    with pytest.raises(OSError, match="refused"):
        await disk.run(fails, "a look")
    assert disk.waiting == 0 and disk.limit == LIMIT
    assert DISK_LIMIT_SECONDS == 10.0 and ABANDONED_MOST == 4
    assert Disk().limit == DISK_LIMIT_SECONDS


async def test_a_wait_past_its_limit_is_given_up_and_the_loop_answers_meanwhile() -> None:
    disk, released = Disk(limit=LIMIT), threading.Event()
    beats: list[float] = []

    async def heart() -> None:
        while not released.is_set():
            beats.append(time.monotonic())
            await asyncio.sleep(0.01)

    beating = asyncio.ensure_future(heart())
    began = time.monotonic()
    with pytest.raises(DiskSilent) as silent:
        await disk.run(lambda _: released.wait(), "a look at 'ELA/x'")
    took = time.monotonic() - began
    released.set()
    await beating
    for thread in guards():
        thread.join(10)

    assert took < LIMIT + 1, "the wait was not given up at its limit"
    assert len(beats) > 3, "the loop stood still while the disk did not answer"
    assert str(silent.value) == (
        "a look at 'ELA/x': the disk did not answer within 0.2 s, and ELA stopped waiting; "
        "nothing was written"
    )
    assert disk.waiting == 0


async def test_the_fifth_wait_is_refused_at_once_and_a_released_disk_answers_again() -> None:
    """Answer 40: four standing, the fifth without a thread; released, the count falls."""
    disk, released = Disk(limit=LIMIT), threading.Event()
    for _ in range(ABANDONED_MOST):
        with pytest.raises(DiskSilent):
            await disk.run(lambda _: released.wait(), "a look")
    assert disk.waiting == ABANDONED_MOST
    started = len(guards())

    with pytest.raises(DiskSilent) as refused:
        await disk.run(lambda _: 1, "a look at 'ELA/y'")

    assert len(guards()) == started, "the fifth opened a thread"
    assert str(refused.value) == (
        "a look at 'ELA/y': 4 waits on the disk are still standing, the most ELA leaves waiting — "
        "they end when the disk answers, and nothing new is asked of it until then"
    )
    released.set()
    for thread in guards():
        thread.join(10)
    assert disk.waiting == 0
    assert await disk.run(lambda _: 1, "a look") == 1


async def test_a_wait_whose_work_ends_as_it_is_given_up_gives_the_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The work ends in the instant between the limit and the abandonment: its outcome is on its
    way, and it is the answer — no wait is counted as standing."""
    disk, released = Disk(limit=LIMIT), threading.Event()
    giving_up = Disk._abandoned  # noqa: SLF001 — the instant under test

    def after_the_work(self: Disk, gone: Gone, wait: Any) -> str | None:
        released.set()
        for thread in guards():
            thread.join(10)
        return giving_up(self, gone, wait)

    monkeypatch.setattr(Disk, "_abandoned", after_the_work)

    assert await disk.run(lambda _: released.wait() and 7, "a look") == 7
    assert disk.waiting == 0


async def test_a_cancelled_wait_is_given_up_and_counted_until_the_disk_answers() -> None:
    disk, released = Disk(limit=5.0), threading.Event()
    waiting = asyncio.ensure_future(disk.run(lambda _: released.wait(), "a look"))
    while not guards():
        await asyncio.sleep(0)
    waiting.cancel()

    with pytest.raises(asyncio.CancelledError):
        await waiting

    assert disk.waiting == 1
    released.set()
    for thread in guards():
        thread.join(10)
    assert disk.waiting == 0


async def test_a_write_abandoned_while_it_made_its_folder_will_not_write_the_file() -> None:
    disk, released = Disk(limit=LIMIT), threading.Event()
    written: list[str] = []

    def folder_then_file(gone: Gone) -> None:
        gone.begin(MAKING_THE_FOLDER)
        released.wait()
        gone.begin(WRITING)
        written.append("file")

    with pytest.raises(DiskSilent) as silent:
        await disk.run(folder_then_file, "a write of 'ELA/x'")
    released.set()
    for thread in guards():
        thread.join(10)

    assert str(silent.value).endswith(
        "the folder may still be made, and the file will not be written"
    )
    assert written == []


def test_the_mark_refuses_a_step_once_the_wait_is_given_up() -> None:
    gone = Gone()
    gone.begin("writing")
    assert not gone.abandoned
    assert gone._abandon() == "writing"  # noqa: SLF001 — the guard's side of the mark
    assert gone.abandoned
    with pytest.raises(Abandoned):
        gone.begin("writing")


def test_the_guard_of_the_start_up_answers_passes_errors_on_and_gives_up() -> None:
    released = threading.Event()

    def fails(_: Gone) -> None:
        raise PermissionError("no")

    assert within_the_limit(lambda _: "there", "a look", limit=LIMIT) == "there"
    with pytest.raises(PermissionError):
        within_the_limit(fails, "a look", limit=LIMIT)
    with pytest.raises(DiskSilent) as silent:
        within_the_limit(lambda _: released.wait(), "ELA_FS_SCOPE: 'Documents'", limit=LIMIT)
    released.set()

    assert str(silent.value) == (
        "ELA_FS_SCOPE: 'Documents': the system did not answer within 0.2 s. If a window asked for "
        "a permission, answer it and start ELA again"
    )


# ----------------------------------------------------------------------------------------
# The tools: a look, a read, a write
# ----------------------------------------------------------------------------------------


async def test_a_look_that_does_not_answer_refuses_before_the_question(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = FsReadTool(root, FakeClock(NOW), FakeIdGenerator(), protected={}, disk=Disk(limit=LIMIT))
    with a_disk_that_does_not_answer(monkeypatch, "looked_for_a_read"):
        seen = await tool.prospect({"path": "ELA/c'è.md", "purpose": "p"})

    assert seen.refusal is not None and seen.refusal.code == NO_ANSWER
    assert seen.refusal.retryable is False
    assert 'a look at "ELA/c\'è.md"' in seen.refusal.message


async def test_a_read_that_does_not_answer_fails_and_is_not_retried(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = FsReadTool(root, FakeClock(NOW), FakeIdGenerator(), protected={}, disk=Disk(limit=LIMIT))
    with a_disk_that_does_not_answer(monkeypatch, "read_bytes"):
        result = await tool.execute(
            decision(FS_READ), {"path": "ELA/c'è.md", "purpose": "p"}, FakeStop()
        )

    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None and result.error.code == NO_ANSWER
    assert result.error.retryable is False
    assert result.error.message.endswith("nothing was written")


async def test_a_write_abandoned_while_it_looked_never_writes(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Decision 52: the disk held at the look, then released — and on the disk there is nothing."""
    tool = FsWriteTool(
        root, FakeClock(NOW), FakeIdGenerator(), protected={}, disk=Disk(limit=LIMIT)
    )
    arguments = {"path": "ELA/nuova/nuovo.md", "body": "x", "overwrite": False, "purpose": "p"}
    stop = FakeStop()
    with a_disk_that_does_not_answer(monkeypatch, "looked_for_a_write"):
        result = await tool.execute(decision(FS_WRITE), arguments, stop)

    assert result.error is not None and result.error.code == NO_ANSWER
    assert result.error.message.endswith("nothing was written")
    assert not (root / "ELA" / "nuova").exists(), "an abandoned write made its folder"
    assert stop.listened == [], "the point was passed by a write nobody waited for"


async def test_a_write_abandoned_inside_the_write_says_it_may_still_happen(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = FsWriteTool(
        root, FakeClock(NOW), FakeIdGenerator(), protected={}, disk=Disk(limit=LIMIT)
    )
    arguments = {"path": "ELA/tardi.md", "body": "x", "overwrite": False, "purpose": "p"}
    released = threading.Event()
    real = fs_module.os.open

    def held(*args: Any, **kwargs: Any) -> int:
        released.wait()
        return real(*args, **kwargs)

    monkeypatch.setattr(fs_module, "os", _Proxy(fs_module.os, open=held))
    try:
        result = await tool.execute(decision(FS_WRITE), arguments, FakeStop())
    finally:
        released.set()
        for thread in guards():
            thread.join(10)

    assert result.error is not None and result.error.code == NO_ANSWER
    assert result.error.message.endswith("the write may still happen when the disk answers")
    assert (root / "ELA" / "tardi.md").read_text() == "x", "the write did land, after"


async def test_a_stop_during_a_wait_waits_at_most_the_limit(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Decision 53: a stop is heard at the tool's point, after the look — in the worst case, the
    limit; and the write it would have stopped is not made."""
    tool = FsWriteTool(
        root, FakeClock(NOW), FakeIdGenerator(), protected={}, disk=Disk(limit=LIMIT)
    )
    arguments = {"path": "ELA/fermo.md", "body": "x", "overwrite": False, "purpose": "p"}
    stop = FakeStop(stopped=True)
    began = time.monotonic()
    with a_disk_that_does_not_answer(monkeypatch, "looked_for_a_write"):
        result = await tool.execute(decision(FS_WRITE), arguments, stop)

    assert time.monotonic() - began < LIMIT + 1
    assert result.error is not None and result.error.code == NO_ANSWER
    assert not (root / "ELA" / "fermo.md").exists()


async def test_a_stop_heard_after_an_answered_look_stops_before_the_write(root: Path) -> None:
    """The other side of decision 53: the look answers, the stop is heard at the point, in the
    guard's thread, with nothing between it and the folder."""
    tool = FsWriteTool(
        root, FakeClock(NOW), FakeIdGenerator(), protected={}, disk=Disk(limit=LIMIT)
    )
    arguments = {"path": "ELA/fermo.md", "body": "x", "overwrite": False, "purpose": "p"}

    with pytest.raises(ToolStopped):
        await tool.execute(decision(FS_WRITE), arguments, FakeStop(stopped=True))

    assert not (root / "ELA" / "fermo.md").exists()


class _Proxy:
    """A module with some of its names replaced: what ``fs`` reads as ``os`` in one test."""

    def __init__(self, real: Any, **replaced: Callable[..., Any]) -> None:
        self._real = real
        self._replaced = replaced

    def __getattr__(self, name: str) -> Any:
        if name in self._replaced:
            return self._replaced[name]
        return getattr(self._real, name)
