"""The fixture that keeps one test of the real browser from leaving anything to the next (M13.10,
decision 56 (a) of the review of its implementation).

On the CI of ubuntu, twice in four rounds, a process of a browser was found among the descendants
of a worker by a dozen tests after the one that left it — named by its first fifteen characters
only, «Google Chrome f», and by no test. And the fixture itself fell at the teardown of six of them
with «Set of Tasks/Futures is empty»: an empty set is not something to wait for.

So: nothing is waited for when there is nothing to wait for; and **a process found before a test
begins is named whole** — its command line as the system reads it, ``/proc/<pid>/cmdline`` on
Linux — **with the test that ran before on that worker**, which is the one that left it.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.browser_leftovers import scratch
from tests.infrastructure.machine import test_browser as shell

LINUX = Path("/proc").is_dir()


@pytest.fixture
def ended() -> Iterator[subprocess.Popen[bytes]]:
    """A child that has ended and that nobody has collected yet: the kernel keeps its entry, and
    on Linux no command line. Its end is the end of a pipe only it holds — an event, and one that
    collects nothing —; collected after the test."""
    read, write = os.pipe()
    child = subprocess.Popen(["/bin/sh", "-c", "exit 0"], pass_fds=(write,))
    os.close(write)
    try:
        assert os.read(read, 1) == b""
    finally:
        os.close(read)
    yield child
    child.wait()


async def test_an_empty_set_of_closings_is_not_something_to_wait_for() -> None:
    await shell.settled_after(set())


async def test_the_closings_left_are_given_the_loop_before_it_is_torn_down() -> None:
    ended = asyncio.Event()

    async def closing() -> None:
        ended.set()

    await shell.settled_after({asyncio.ensure_future(closing())})

    assert ended.is_set()


def test_a_process_is_named_by_its_whole_command_line_as_the_system_reads_it() -> None:
    """This very process: its command line has more than fifteen characters, and names Python."""
    said = shell.command_line(os.getpid())

    assert len(said) > 15
    assert Path(sys.executable).name in said or "python" in said.lower()


def test_a_process_that_is_gone_is_named_as_gone() -> None:
    assert shell.command_line(2**22 + 12345) == "(gone)"


@pytest.mark.skipif(not LINUX, reason="only Linux has /proc")
def test_on_linux_the_command_line_is_read_from_proc() -> None:
    raw = Path(f"/proc/{os.getpid()}/cmdline").read_bytes()

    assert shell.command_line(os.getpid()) == raw.replace(b"\0", b" ").decode().strip()


def test_what_was_left_is_named_with_the_test_that_ran_before_on_the_worker() -> None:
    said = shell.left_before(
        [(4242, "Google Chrome f")],
        "tests/infrastructure/machine/test_browser.py::test_the_one_before",
        lambda pid: "/opt/google/chrome-for-testing/chrome --type=renderer --lang=en-US",
    )

    assert "tests/infrastructure/machine/test_browser.py::test_the_one_before" in said
    assert "4242 (Google Chrome f)" in said
    assert "/opt/google/chrome-for-testing/chrome --type=renderer --lang=en-US" in said


def test_the_first_test_of_a_worker_has_no_test_before_it() -> None:
    said = shell.left_before([(1, "x")], "", lambda pid: "x --y")

    assert "no test ran before it on this worker" in said


def test_a_process_that_ended_and_was_not_collected_is_named_all_the_same(
    ended: subprocess.Popen[bytes],
) -> None:
    assert shell.command_line(ended.pid) not in ("", "(gone)")


@pytest.mark.skipif(not LINUX, reason="only Linux keeps no command line for it")
def test_on_linux_it_is_named_by_its_state_and_by_the_parent_that_should_collect_it(
    ended: subprocess.Popen[bytes],
) -> None:
    said = shell.command_line(ended.pid)

    assert said.startswith("(no command line: state ")
    assert f", child of {os.getpid()}: " in said
    assert "python" in said.lower()


def test_what_runs_before_a_test_begins_is_named_whole_with_the_test_before_and_swept() -> None:
    """What the fixture does before every test of the real browser, on a process of its own."""
    child = subprocess.Popen(["/bin/sleep", "61"])
    folder = scratch()
    try:
        said = shell.found_before(folder, "tests/x.py::test_the_one_before")
        swept = child.poll() if child.poll() is not None else child.wait(timeout=10)
    finally:
        child.kill()  # a test that fails leaves nothing either: a no-op once it is collected
        child.wait()
        shutil.rmtree(folder, ignore_errors=True)

    assert swept != 0
    assert f"{child.pid} (" in said
    assert "/bin/sleep 61" in said
    assert "left by tests/x.py::test_the_one_before" in said
