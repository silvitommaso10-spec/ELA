"""**The one place a test says what machine it needs** — and the guard that turns a skip on the
machine a test covers into a red (M9.5, ADR 0069: ADR 0047 §18 paid).

A ``skipif`` that reads the machine declares a precondition, and if it fires on the system the test
exists to cover the test proves nothing any more: a line in a summary, which turns nothing red.
Until 2026-11-17 the conditions were written in ninety places, each by hand; three tests of M13.9b
forgot to copy one and ubuntu was red for a week (``tests/profile_browser.py``). Here:

* every condition that reads the machine is a :class:`Condition` with a name, **one reading** — made
  once in a process, and only when a test that needs it is about to run: some cost, one asks
  macOS for a permission — and **where it must hold, by declaration**. Where the product has the
  condition, the reading is the product's (:data:`PROFILE_BROWSER`, :data:`CLAUDE_CODE`,
  :data:`AUDIO_INPUT`, :data:`SCREEN_RECORDING`);
* a test says what it needs with :func:`needs` — a mark, never a ``skipif`` of its own: outside
  this file nobody writes one (``tests/architecture/test_skips_are_written_in_one_place.py``);
* **the guard** (:func:`guard`, called by the hook of ``tests/conftest.py`` before each test is set
  up): where a condition the test needs is missing **and need not be there**, the test is skipped,
  with the reason in the summary; where one is missing **that must be there**, the test is **red**,
  saying what is missing. The decision is :func:`decision`, a pure function with its negative cases
  in ``tests/test_machines.py``, which are never skipped;
* **a test that runs on no job of the CI is red on every machine** unless a declared place says
  why (:func:`runs_on`, :func:`nowhere_said`): the jobs are :data:`JOBS`, what the Windows job
  collects is its ``pytest`` line in ``.github/workflows/ci.yml``, and the declared places are
  ``tests/windows.py`` and a condition's own :attr:`Condition.nowhere`.

**What «the machine» is when it is pretended** (``tests/foreign_machine.py``): each condition is
compared with the machine **in the same reading it fires by**. A condition on the system reads
``platform.system()``, which the plugin pretends — under ``make check-linux`` the system is Linux,
and a test that covers Linux must run there —; one on the kernel reads ``sys.platform`` or
``/proc``, which the plugin does not pretend — there the kernel is Darwin's, and a test of Linux's
kernel is skipped without a red. The guard has no idea of the machine of its own: it has each
condition's.

**Where the session runs as root** (``CLAUDE.md``, the cloud session) the bits of a mode do not
bind whoever runs the suite: that is what the tests that need :data:`PERMISSIONS_BITE` cover, and
they are skipped with the reason — **on a runner of the CI they are red** (decision 65).
"""

from __future__ import annotations

import asyncio
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Literal

import pytest

from ela.infrastructure.machine.account import SUPPORTED
from tests.windows import OUTSIDE_THE_WINDOWS_JOB

ROOT: Final = Path(__file__).resolve().parent.parent
MARK: Final = "needs"
"""The name of the mark :func:`needs` makes, registered by ``tests/conftest.py``."""


@dataclass(frozen=True)
class Machine:
    """A machine as the conditions see it: its system (``platform.system()``, which
    ``tests/foreign_machine.py`` pretends), its kernel (``sys.platform``, which it does not), and
    whether it is a runner of the CI (``GITHUB_ACTIONS``)."""

    system: str
    kernel: str
    runner: bool


def here() -> Machine:
    """This machine, read the way the conditions read it."""
    return Machine(platform.system(), sys.platform, os.environ.get("GITHUB_ACTIONS") == "true")


@dataclass(frozen=True, eq=False)
class Condition:
    """Something a test needs of the machine — compared by identity: each is written once, here."""

    name: str
    """What it is, as a red says it."""
    read: Callable[[], str | None] = field(repr=False)
    """``None`` where it holds; where it does not, why not — the reason a skip says."""
    required: Callable[[Machine], bool] = field(repr=False)
    """Where it must hold, by declaration: there a test that needs it and finds it missing is
    red."""
    where: str
    """The same, in words."""
    nowhere: str | None = None
    """Why no job of the CI has it, when that is so: a test that needs it runs on no job, and this
    is the declared reason (:func:`nowhere_said`)."""
    binary: bool = False
    """Whether it names **a real binary the test launches**, one a milestone brings — the browser of
    the profile, the binary of Claude Code: a test that needs it is «of the binary» in the measure
    of time (decision 79 of the review at ``ad1826c``, ADR 0069), derived from the marks and not
    from a list of files (:func:`of_a_binary`)."""

    def __repr__(self) -> str:
        return self.name


def _posix(machine: Machine) -> bool:
    return machine.kernel != "win32"


def _everywhere(_: Machine) -> bool:
    return True


def _on_a_runner(machine: Machine) -> bool:
    return machine.runner


def _on_a_mac_runner(machine: Machine) -> bool:
    return machine.runner and machine.kernel == "darwin"


def _the_system(name: str) -> Condition:
    def read() -> str | None:
        found = platform.system()
        return None if found == name else f"this system is {found}"

    return Condition(
        f"the system {name}", read, lambda machine: machine.system == name, f"on {name}"
    )


def _the_kernel(name: str, kernel: str) -> Condition:
    def read() -> str | None:
        if sys.platform == kernel:
            return None
        return f"this kernel is {sys.platform}"

    return Condition(
        f"the kernel of {name}",
        read,
        lambda machine: machine.kernel == kernel,
        f"on the kernel of {name}",
    )


def _a_program(name: str, found: Callable[[], bool]) -> Condition:
    return Condition(
        name,
        lambda: None if found() else f"{name} is not on this machine",
        _posix,
        "on Darwin and Linux",
    )


DARWIN: Final = _the_system("Darwin")
WINDOWS: Final = _the_system("Windows")
DARWIN_KERNEL: Final = _the_kernel("Darwin", "darwin")
LINUX_KERNEL: Final = _the_kernel("Linux", "linux")
WINDOWS_KERNEL: Final = _the_kernel("Windows", "win32")


def _a_posix_kernel() -> str | None:
    if sys.platform != "win32":
        return None
    return "this kernel is Windows's"


POSIX: Final = Condition("a POSIX kernel", _a_posix_kernel, _posix, "on Darwin and Linux")
"""Signals, process groups, the bits of a mode, ``ps``, FIFOs: what Windows does not have."""
PROC: Final = Condition(
    "/proc",
    lambda: None if Path("/proc").is_dir() else "this machine has no /proc",
    lambda machine: machine.kernel == "linux",
    "on the kernel of Linux",
)
"""What only Linux has: a process read by another, the way ``test_nothing_left_behind.py`` and
``test_agent_session.py`` read one. Read from ``/proc`` itself, not from ``sys.platform``."""

MAKE: Final = _a_program("make", lambda: shutil.which("make") is not None)
LSOF: Final = _a_program("lsof", lambda: shutil.which("lsof") is not None)
OPENSSL: Final = _a_program("openssl", lambda: shutil.which("openssl") is not None)
USR_BIN_TRUE: Final = _a_program("/usr/bin/true", Path("/usr/bin/true").exists)
USR_BIN_TIME: Final = _a_program("/usr/bin/time", Path("/usr/bin/time").exists)


def _claude_code() -> str | None:
    from ela.infrastructure.machine.agent import bundled_binary

    if sys.platform != "win32" and os.access(bundled_binary(), os.X_OK):
        return None
    return "the binary of Claude Code that the SDK's wheel carries is not on this machine"


CLAUDE_CODE: Final = Condition(
    "the binary of Claude Code of the wheel",
    _claude_code,
    _posix,
    "on Darwin and Linux",
    binary=True,
)
"""The product's own: :func:`ela.infrastructure.machine.agent.bundled_binary`."""


def _git(*arguments: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *arguments], cwd=ROOT, capture_output=True, check=False)


def _a_repository() -> str | None:
    if _git("ls-files", "--eol", "-z").returncode != 0:
        return "not a git repository: nobody to ask which files it tracks"
    return None


MAIN_REFS: Final = ("main", "origin/main")
"""Where the history of ``main`` is, in a clone of the developer and in a runner's."""


def _the_history() -> str | None:
    """The reason the history of ``main`` cannot be read here, or ``None``. A shallow clone answers
    ``git log`` with a success and a truncated history: a test that simply ran would pass seeing
    nothing. The CI checks out with ``fetch-depth: 0`` for this."""
    shallow = _git("rev-parse", "--is-shallow-repository")
    if shallow.returncode != 0:
        return "not a git repository"
    if shallow.stdout.decode().strip() == "true":
        return "shallow clone: the history of main is not here (git fetch --unshallow)"
    for ref in MAIN_REFS:
        if _git("rev-parse", "--verify", "--quiet", ref).returncode == 0:
            return None
    return "no main and no origin/main in this clone: the history the test reads is not here"


GIT_REPOSITORY: Final = Condition(
    "a git repository", _a_repository, _everywhere, "wherever the suite runs"
)
GIT_HISTORY: Final = Condition(
    "the history of main", _the_history, _everywhere, "wherever the suite runs"
)


def permissions_bite() -> bool:
    """Whether ``chmod(0o000)`` really denies **this** process, measured instead of assumed.

    A test that needs the system to refuse has a precondition — *I am not the user who is allowed
    anyway* — and root is allowed anyway. It is not a property of the platform, so it is not
    declared by naming one (ADR 0031 §6): it is **constructed and measured**."""
    with tempfile.NamedTemporaryFile(delete=False) as handle:
        target = Path(handle.name)
    try:
        target.chmod(0o000)
        try:
            with target.open("rb"):
                return False
        except OSError:
            return True
    finally:
        target.chmod(0o600)
        target.unlink()


PERMISSIONS_BITE: Final = Condition(
    "a user the bits of a mode bind",
    lambda: None if permissions_bite() else "chmod does not deny this user: it is root",
    _on_a_runner,
    "on a runner of the CI, whose user is not root",
)


def _ignores_case() -> str | None:
    """Asked of the volume the tests build their folders on: a folder made, and looked for in
    capitals."""
    with tempfile.TemporaryDirectory() as made:
        (Path(made) / "a-name").mkdir()
        if (Path(made) / "A-NAME").is_dir():
            return None
    return "this volume tells the cases of a name apart: a folder has one spelling on it"


IGNORES_CASE: Final = Condition(
    "a volume that ignores the case of a name",
    _ignores_case,
    lambda machine: machine.kernel == "darwin",
    "on the system volume of macOS",
)
ON_A_RUNNER: Final = Condition(
    "a runner of the CI",
    lambda: (
        None
        if os.environ.get("GITHUB_ACTIONS") == "true"
        else "GITHUB_ACTIONS is not set: this is not a runner"
    ),
    _on_a_runner,
    "on a runner of the CI",
)


def _in_a_thread(work: Callable[[], Any]) -> Any:
    """Run ``work`` in a thread of its own: an event loop made there touches no loop of the
    thread that sets the tests up."""
    with ThreadPoolExecutor(max_workers=1) as one:
        return one.submit(work).result()


def _screen_recording() -> str | None:
    """The permission read the way ELA reads it — the real probe, which asks and never prompts
    (ADR 0028 §2)."""
    from datetime import timedelta

    from ela.domain import ProbeFamily
    from ela.infrastructure.machine import DarwinProbe

    async def read() -> bool | None:
        families = frozenset({ProbeFamily.PERMISSIONS})
        observed = await DarwinProbe(timeout=timedelta(seconds=5)).read(families)
        return observed.screen_recording_permission

    if _in_a_thread(lambda: asyncio.run(read())) is True:
        return None
    return "Screen Recording is not granted here (or could not be read)"


SCREEN_RECORDING: Final = Condition(
    "the permission of Screen Recording",
    _screen_recording,
    _on_a_mac_runner,
    "on the runner of macOS",
)


def _audio_input() -> str | None:
    """Whether an input opens, **said by the product**: the recorder of ELA, as ELA runs it — a
    child process, the module and nothing else —, for no seconds, writing into nothing."""
    from ela.infrastructure.machine.darwin import MICROPHONE_MODULE

    with open(os.devnull, "wb") as sink:
        ran = subprocess.run(  # noqa: S603 — the product's own module, by the running Python
            [sys.executable, "-m", MICROPHONE_MODULE, "0", str(sink.fileno())],
            pass_fds=(sink.fileno(),),
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    try:
        answer = json.loads(ran.stdout)
    except ValueError:
        return f"the recorder said nothing it could be read by: {ran.stderr.strip()[-200:]!r}"
    if answer.get("opened") is True:
        return None
    return f"no audio input opens here: the recorder said {answer}"


AUDIO_INPUT: Final = Condition(
    "an audio input that opens",
    _audio_input,
    _on_a_mac_runner,
    "on the runner of macOS: its queue opens (run 43554146346, read on 2026-11-17)",
)


def _the_browser_of_the_profile() -> str | None:
    if platform.system() == SUPPORTED:
        return None
    return "the browser with the profile is Chrome for Testing on a Mac"


PROFILE_BROWSER: Final = Condition(
    "the browser of the profile",
    _the_browser_of_the_profile,
    lambda machine: machine.system == SUPPORTED,
    f"where the product has it: {SUPPORTED}",
    binary=True,
)
"""The product's own condition: :data:`ela.infrastructure.machine.account.SUPPORTED`, the one its
adapter raises ``BrowserUnsupported`` by. ``tests/profile_browser.py`` puts it where a test takes
that browser."""


def needs(*conditions: Condition, why: str = "") -> pytest.MarkDecorator:
    """The mark of a test that needs ``conditions`` of the machine — on a test, a class, a module
    (``pytestmark``), a parameter. ``why`` is the reason the skip says, before what is missing."""
    if not conditions or not all(isinstance(one, Condition) for one in conditions):
        raise TypeError("needs() takes the conditions of tests/machines.py, at least one")
    return pytest.mark.needs(*conditions, why=why)


# ----------------------------------------------------------------------------------------
# The decision, pure
# ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Decision:
    """What the guard does with a test on a machine: it runs, it is skipped, or it is red."""

    kind: Literal["runs", "skipped", "red"]
    said: str = ""


def decision(
    needed: Sequence[tuple[Condition, str]],
    machine: Machine,
    missing: Callable[[Condition], str | None],
) -> Decision:
    """Whether a test that needs ``needed`` — each condition with the ``why`` of its mark — runs on
    ``machine``, where ``missing`` reads a condition.

    * A condition carried twice is red: once is the rule of the one place.
    * A condition that **need not hold** here and is missing: skipped — the test does not cover this
      machine. These are read first, and the reading stops at the first: what costs to read is
      read only where the test would run.
    * A condition that **must hold** here and is missing: red, saying what and where.
    * Otherwise it runs."""
    seen: set[int] = set()
    twice = []
    for condition, _ in needed:
        if id(condition) in seen:
            twice.append(condition.name)
        seen.add(id(condition))
    if twice:
        return Decision("red", f"the test says twice that it needs {', '.join(twice)}")
    for condition, why in needed:
        if not condition.required(machine):
            absent = missing(condition)
            if absent is not None:
                return Decision("skipped", f"{why} — {absent}" if why else absent)
    for condition, _ in needed:
        if condition.required(machine):
            absent = missing(condition)
            if absent is not None:
                return Decision(
                    "red",
                    f"{condition.name} must be here — {condition.where} — and is not: {absent}. "
                    "A skip here would hide the machine the test covers (tests/machines.py)",
                )
    return Decision("runs")


# ----------------------------------------------------------------------------------------
# The jobs of the CI, and a test that runs on none of them
# ----------------------------------------------------------------------------------------

WORKFLOW: Final = ROOT / ".github" / "workflows" / "ci.yml"


def windows_line(workflow: str) -> list[str]:
    """What the Windows job collects: the files and folders of ``tests/`` on its ``pytest`` line."""
    (job,) = [line for line in workflow.splitlines() if "pytest" in line and "tests/node" in line]
    return [word for word in job.split() if word.startswith("tests/")]


@dataclass(frozen=True)
class Job:
    """A job of the CI: the machine it runs on and what it collects (``None``: the whole suite)."""

    name: str
    machine: Machine
    collects: tuple[str, ...] | None

    def takes(self, path: str) -> bool:
        if self.collects is None:
            return True
        return any(path == one or path.startswith(one.rstrip("/") + "/") for one in self.collects)


def jobs(workflow: str) -> tuple[Job, ...]:
    """The three jobs the merge waits for (``CLAUDE.md``), from the workflow as it is."""
    return (
        Job("make check (ubuntu-24.04)", Machine("Linux", "linux", True), None),
        Job("make check (macos-latest)", Machine("Darwin", "darwin", True), None),
        Job(
            "node suite (windows-latest)",
            Machine("Windows", "win32", True),
            tuple(windows_line(workflow)),
        ),
    )


def runs_on(needed: Iterable[Condition], path: str, among: Iterable[Job]) -> list[str]:
    """The jobs that collect the test of ``path`` and where every condition it needs must hold —
    there it runs, or is red: never skipped."""
    conditions = list(needed)
    return [
        job.name
        for job in among
        if job.takes(path) and all(one.required(job.machine) for one in conditions)
    ]


def nowhere_said(
    needed: Iterable[Condition], path: str, outside: Mapping[str, str] = OUTSIDE_THE_WINDOWS_JOB
) -> str | None:
    """Why a test that runs on no job runs on none, from a declared place — ``tests/windows.py`` for
    a file the Windows job leaves out, a condition's :attr:`Condition.nowhere` — or ``None``."""
    if path in outside:
        return outside[path]
    return next((one.nowhere for one in needed if one.nowhere), None)


# ----------------------------------------------------------------------------------------
# The guard, called by the hook of tests/conftest.py
# ----------------------------------------------------------------------------------------

_read: dict[Condition, str | None] = {}
"""What each condition read on this machine: kept by the condition itself — compared by identity,
and held here, so no other can take its place."""
_jobs: list[tuple[Job, ...]] = []


def missing_here(condition: Condition) -> str | None:
    """``condition`` read on this machine — once in a process."""
    if condition not in _read:
        _read[condition] = condition.read()
    return _read[condition]


def needed_by(item: pytest.Item) -> list[tuple[Condition, str]]:
    """What ``item`` says it needs, from every mark of :func:`needs` it carries."""
    return [
        (condition, str(mark.kwargs.get("why", "")))
        for mark in item.iter_markers(MARK)
        for condition in mark.args
    ]


def of_a_binary(item: Any) -> bool:
    """Whether ``item`` is a test of a real binary: it needs a condition that names one — through
    a mark of its own or the one the collection puts where a test takes the browser of the
    profile."""
    return any(
        isinstance(one, Condition) and one.binary
        for mark in item.iter_markers(MARK)
        for one in mark.args
    )


def carries(item: Any, condition: Condition) -> bool:
    """Whether ``item`` already says it needs ``condition``."""
    return any(condition in mark.args for mark in item.iter_markers(MARK))


def guard(item: pytest.Item) -> None:
    """Before ``item`` is set up: skipped, red, or let run — :func:`decision` on this machine; and
    red wherever it is, if it runs on no job of the CI and no declared place says why."""
    needed = needed_by(item)
    if not needed:
        return
    if not _jobs:
        _jobs.append(jobs(WORKFLOW.read_text(encoding="utf-8")))
    conditions = [condition for condition, _ in needed]
    path = item.nodeid.split("::", 1)[0]
    if not runs_on(conditions, path, _jobs[0]) and nowhere_said(conditions, path) is None:
        pytest.fail(
            f"this test runs on no job of the CI: it needs {conditions}, and no job that collects "
            f"{path} has them all. Say why in a declared place (tests/windows.py, or the "
            "condition's `nowhere`), or let a job run it",
            pytrace=False,
        )
    decided = decision(needed, here(), missing_here)
    if decided.kind == "skipped":
        item.add_marker(pytest.mark.skipif(True, reason=decided.said))
    elif decided.kind == "red":
        pytest.fail(decided.said, pytrace=False)
