"""``terminal.run`` (spec §18): a program of those declared, with the arguments of this call
(M13.2, ADR 0047).

**A command is ``argv``, from the argument to the process.** The plan names a program — a path
relative to ``/``, in the grammar of every scope — and a **list** of arguments; the process receives
``["/" + program, *args]`` as that list, with no shell and no ``PATH`` search in between: nothing to
quote, nothing to escape, no expansion. ELA runs the declared path, so a program that chooses what
to do from its own name keeps doing so; the question names the file it leads to as well.

**The boundary is which programs, and the judgement on each call is the user's** (dec. 2). The
Guardian keeps the scope; this tool keeps the identity of each program fixed at start-up
(:mod:`ela.tools.programs`), and refuses — **before the question**, in the one function the
question and the run share — what can be known without launching: a program that is not one of
those, that is not there or not the one of the start-up, a folder a program cannot start from, an
argument no process can receive (dec. 5). What cannot be known is not pretended: whether it ends,
with which code, what it prints, what it touches. A file the kernel refuses to execute is found only
by trying, and it is the one refusal after a yes (``terminal.not_started``).

**What a program receives is decided here and executed to the letter by the launcher** (dec. 15):
four environment variables and nothing else — the ``PATH`` below, ``HOME`` and ``TMPDIR`` computed
by the composition once, ``LANG`` —, the end of a file on stdin, a folder inside the scope of M13.1
and never ELA's own, a timeout, a breath between ``SIGTERM`` and ``SIGKILL``, and half of the
ceiling for the head and half for the tail of each stream.

**The folder is not a boundary, and the question says so** (dec. 6): the boundary of M13.1 holds for
``fs.read`` and ``fs.write`` because ELA executes them; ``/bin/cp`` is executed by the program.
"""

from __future__ import annotations

import codecs
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Final

from ela.domain import CapabilityId, CommandOutput, ErrorMetadata, JsonMapping, JsonValue
from ela.ports import (
    Captured,
    Clock,
    Command,
    CommandLauncher,
    Ending,
    IdGenerator,
    Invocation,
    Prospect,
    Target,
)
from ela.tools.base import ARGUMENTS_INVALID, Outcome, Tool
from ela.tools.fs import NO_ROOT
from ela.tools.paths import (
    PATH_CODES,
    PATH_IS_DIRECTORY,
    PATH_NOT_REGULAR,
    classify,
    resolve_workspace,
)
from ela.tools.programs import NO_PROGRAM, NOT_DECLARED, PROGRAM_CHANGED, Programs

__all__ = [
    "ARGUMENTS_UNPASSABLE",
    "AUDIT_NUMBERS",
    "CLOSED_PATH",
    "CWD_NOT_A_FOLDER",
    "GRACE_SECONDS",
    "LANGUAGE",
    "NOT_STARTED",
    "PROGRAM",
    "RUNS",
    "STOPPED",
    "TERMINAL_RUN",
    "TERMINAL_TOOL_NAME",
    "TIMEOUT",
    "Terminal",
    "TerminalRunTool",
    "decoded",
    "stream",
]

TERMINAL_RUN: Final = CapabilityId("terminal.run")
TERMINAL_TOOL_NAME: Final = "terminal-run"

ARGUMENTS_UNPASSABLE: Final = "terminal.arguments_unpassable"
"""An argument no process can receive: a NUL byte, or more than the system passes (dec. 5)."""
CWD_NOT_A_FOLDER: Final = "terminal.cwd_not_a_folder"
"""The folder named is a file, or something that is not a folder: a program cannot start there."""
NOT_STARTED: Final = "terminal.not_started"
"""The kernel refused the ``exec``: the one refusal the rule of ADR 0045 §6-bis lets through,
because it is the one found only by trying (dec. 5)."""
TIMEOUT: Final = "terminal.timeout"
"""The program was still running at the timeout, and ELA stopped its process group (dec. 7)."""
STOPPED: Final = "terminal.stopped"
"""ELA was stopping while the program ran, and stopped its process group («La ripresa»). Not
:data:`TIMEOUT`: the time had not run out, and a code that names the wrong reason is a false
diagnosis even when the outcome is right (M13.1 dec. B)."""

PROGRAM: Final = "program"
"""What the target of this capability is called, in the tool's own word (dec. 12)."""
RUNS: Final = (
    "runs this program from this folder: it can read and change whatever you can, and ELA sees "
    "what it prints, not what it changes"
)
"""What a yes does, said by the capability that would do it (the form of ADR 0045 §6): the folder is
where the program starts, not where it stays."""

CLOSED_PATH: Final = "/usr/bin:/bin:/usr/sbin:/sbin"
"""The ``PATH`` of every command: fixed, the same on every runner, without ELA's ``.venv/bin`` in
front. Not a boundary — a program admitted that launches another by absolute path launches it
anyway."""
LANGUAGE: Final = "C.UTF-8"
"""``LANG``: UTF-8, and nothing of the locale of whoever started ELA."""
GRACE_SECONDS: Final = 2.0
"""The breath between ``SIGTERM`` and ``SIGKILL`` to the group (dec. 7). A decision, so it is here,
in the gate, and handed to the launcher like the timeout."""

AUDIT_NUMBERS: Final[frozenset[str]] = frozenset(
    {
        "argument_count",
        "exit_code",
        "signal",
        "stdout.shown",
        "stdout.total",
        "stderr.shown",
        "stderr.total",
    }
)
"""What of a command enters ``TOOL_EXECUTED``: numbers, and only numbers (dec. 10, ADR 0047). Never
the arguments, never stdout or stderr, never the folder outside the message of a refusal."""

POINTER: Final = 8
"""The bytes a pointer takes in the vector ``execve`` receives, for ``argv`` and for the
environment."""


@dataclass(frozen=True, slots=True)
class Terminal:
    """What the composition hands the tool, once, at start-up.

    ``programs`` with the identities fixed there; ``root`` and ``scope`` are the pair of M13.1, and
    a command starts in ``root/scope`` or below it; ``home`` and ``temporary`` are computed by the
    composition with ``Path.home()`` and ``tempfile.gettempdir()`` — never read from ``os.environ``
    here (ADR 0001) —; ``argument_limit`` is what the system passes to ``execve``.
    """

    programs: Programs
    root: Path
    scope: str
    timeout_seconds: int
    output_max_bytes: int
    home: str
    temporary: str
    argument_limit: int


@dataclass(frozen=True, slots=True)
class _Call:
    """A call that would start: the facts of the question, and the command the launcher would
    get."""

    invocation: Invocation
    command: Command


class TerminalRunTool(Tool):
    """Runs a declared program and returns its output, in head and tail (§18, **HIGH**)."""

    error_codes: ClassVar[frozenset[str]] = frozenset(
        {
            ARGUMENTS_INVALID,
            NOT_DECLARED,
            NO_PROGRAM,
            PROGRAM_CHANGED,
            ARGUMENTS_UNPASSABLE,
            CWD_NOT_A_FOLDER,
            NO_ROOT,
            NOT_STARTED,
            TIMEOUT,
            STOPPED,
            *PATH_CODES - {PATH_IS_DIRECTORY, PATH_NOT_REGULAR},
        }
    )
    output_keys: ClassVar[frozenset[str]] = frozenset(
        {
            "program",
            "runs",
            "args",
            "argument_count",
            "cwd",
            "expect_exit",
            "ended",
            "exit_code",
            "signal",
            "stdout",
            "stderr",
        }
    )
    audit_numbers: ClassVar[frozenset[str]] = AUDIT_NUMBERS
    idempotent: ClassVar[bool] = False
    """**Not idempotent**: a command is an act, and its second run is a new question (dec. 7).

    The executor writes a STARTED record before the launch, and a retry that finds it without an
    outcome closes the step as interrupted and **never launches again** (ADR 0021 §2): if ELA dies
    mid-command the command survives it (ADR 0036 §6), and nobody knows what it did.
    """

    def __init__(
        self,
        terminal: Terminal,
        launcher: CommandLauncher,
        clock: Clock,
        ids: IdGenerator,
        *,
        name: str = TERMINAL_TOOL_NAME,
    ) -> None:
        super().__init__(TERMINAL_RUN, clock, ids, name=name)
        self._terminal = terminal
        self._root = resolve_workspace(terminal.root)
        self._launcher = launcher

    async def prospect(self, arguments: JsonMapping) -> Prospect:
        """What this command would meet now, and what the question names (dec. 5, 12)."""
        looked = self._look(arguments)
        if isinstance(looked, Outcome):
            return Prospect(
                refusal=ErrorMetadata(
                    code=looked.code or NO_PROGRAM,
                    message=looked.message,
                    tool_name=self.name,
                    retryable=looked.retryable,
                )
            )
        invocation = looked.invocation
        return Prospect(
            target=Target(resolved=invocation.program, exists=True, does=RUNS, label=PROGRAM),
            invocation=invocation,
        )

    def _look(self, arguments: JsonMapping) -> Outcome | _Call:
        """**The one place a command decides**, read by the question and by the run (dec. 5).

        In the order of what a person can fix: the shape of the call, the program, the arguments,
        the folder. The identity of the program is compared with the start-up's here, so it is
        compared twice — when the question is composed and immediately before the launch (dec. 4).
        """
        program, args, cwd, expected = (
            arguments.get("program"),
            arguments.get("args"),
            arguments.get("cwd"),
            arguments.get("expect_exit", 0),
        )
        if not isinstance(program, str):
            return Outcome({}, ARGUMENTS_INVALID, "program must be a string")
        if not isinstance(args, list | tuple) or not all(isinstance(one, str) for one in args):
            return Outcome({}, ARGUMENTS_INVALID, "args must be a list of strings")
        if cwd is not None and not isinstance(cwd, str):
            return Outcome({}, ARGUMENTS_INVALID, "cwd must be a string")
        if type(expected) is not int:
            return Outcome({}, ARGUMENTS_INVALID, "expect_exit must be an integer")
        problem = self._terminal.programs.problem(program)
        if problem is not None:
            return Outcome({}, problem.code, problem.message)
        start = self._terminal.programs.at_start(program)
        assert start is not None and start.runs is not None  # noqa: S101 — ``problem`` said so
        argv = ("/" + program, *(str(one) for one in args))
        environment = self._environment()
        unpassable = self._unpassable(argv, environment)
        if unpassable is not None:
            return Outcome({}, ARGUMENTS_UNPASSABLE, unpassable)
        folder = self._folder(cwd)
        if isinstance(folder, Outcome):
            return folder
        limit = self._terminal.output_max_bytes
        return _Call(
            Invocation(
                program=argv[0],
                runs=start.runs,
                arguments=argv[1:],
                folder=str(folder),
                timeout_seconds=self._terminal.timeout_seconds,
                expect_exit=expected,
            ),
            Command(
                argv=argv,
                environment=environment,
                folder=str(folder),
                timeout=float(self._terminal.timeout_seconds),
                grace=GRACE_SECONDS,
                head=limit // 2,
                tail=limit - limit // 2,
            ),
        )

    def _environment(self) -> tuple[tuple[str, str], ...]:
        """Four names and nothing else (dec. 1): not a variable of ELA's, not the ssh agent."""
        return (
            ("PATH", CLOSED_PATH),
            ("HOME", self._terminal.home),
            ("TMPDIR", self._terminal.temporary),
            ("LANG", LANGUAGE),
        )

    def _unpassable(
        self, argv: tuple[str, ...], environment: tuple[tuple[str, str], ...]
    ) -> str | None:
        """Why no process could receive these arguments, or ``None``. Never the arguments."""
        if any("\0" in one for one in argv):
            return "an argument holds a NUL byte, which no process can receive"
        try:
            for one in argv:
                one.encode()
        except UnicodeEncodeError:
            return "an argument holds a lone surrogate, which is not text a process can receive"
        strings = (*argv, *(f"{name}={value}" for name, value in environment))
        size = sum(len(one.encode()) + 1 + POINTER for one in strings) + 2 * POINTER
        if size > self._terminal.argument_limit:
            return (
                f"the arguments take {size} bytes and this system passes at most "
                f"{self._terminal.argument_limit} to a program"
            )
        return None

    def _folder(self, cwd: str | None) -> Path | Outcome:
        """The folder the command starts from: the scope of M13.1, or a folder inside it (dec. 6).

        The **same** classification as ``fs.*``, twice — the scope against the root, then ``cwd``
        against the scope — with the answer turned round: a folder is what is wanted, and a file is
        a refusal of its own. So «inside the scope» is ``path.outside_root``, and there is no second
        definition of inside.
        """
        if not self._root.is_dir():
            return Outcome(
                {},
                NO_ROOT,
                f"{self._root} is not there: ELA does not create the folder you declared in "
                "ELA_FS_ROOT",
            )
        scope = self._root / self._terminal.scope
        refused = _a_folder(self._root, self._terminal.scope)
        if refused is not None:
            return refused
        if cwd is None:
            return scope
        refused = _a_folder(scope, cwd)
        if refused is not None:
            return refused
        return scope / cwd

    async def _run(self, arguments: JsonMapping) -> Outcome:
        looked = self._look(arguments)
        if isinstance(looked, Outcome):
            return looked
        invocation = looked.invocation
        ran = await self._launcher.run(looked.command)
        if ran.ending is Ending.NOT_STARTED:
            return Outcome({}, NOT_STARTED, f"{invocation.program} did not start: {ran.failure}")
        output: dict[str, JsonValue] = {
            "program": invocation.program,
            "runs": invocation.runs,
            "args": list(invocation.arguments),
            "argument_count": len(invocation.arguments),
            "cwd": invocation.folder,
            "expect_exit": invocation.expect_exit,
            "ended": _ENDED[ran.ending],
            "exit_code": ran.code,
            "signal": ran.signal,
            "stdout": stream(ran.stdout).model_dump(mode="json"),
            "stderr": stream(ran.stderr).model_dump(mode="json"),
        }
        if ran.ending is Ending.TIMED_OUT:
            return Outcome(
                output,
                TIMEOUT,
                f"{invocation.program} was still running after {invocation.timeout_seconds} s: "
                "ELA stopped its process group",
            )
        if ran.ending is Ending.STOPPED:
            return Outcome(
                output,
                STOPPED,
                f"ELA was stopping while {invocation.program} ran, and stopped its process group",
            )
        return Outcome(output)


_ENDED: Final = {
    Ending.EXITED: "exited",
    Ending.SIGNALLED: "signalled",
    Ending.TIMED_OUT: "stopped_by_ela",
    Ending.STOPPED: "stopped_by_ela",
}


def _a_folder(root: Path, path: str) -> Outcome | None:
    """``None`` when ``root / path`` is a folder a program may start from; the refusal otherwise."""
    problem = classify(root, path)
    if problem is None or problem.code == PATH_NOT_REGULAR:
        return Outcome(
            {}, CWD_NOT_A_FOLDER, f"{path!r} is not a folder: a program cannot start from it"
        )
    if problem.code == PATH_IS_DIRECTORY:
        return None
    return Outcome({}, problem.code, problem.message(path))


# ----------------------------------------------------------------------------------------
# Head and tail, and the bytes that are not text (dec. 8)
# ----------------------------------------------------------------------------------------


def stream(captured: Captured) -> CommandOutput:
    """One stream as the result keeps it: head and tail on a character, the cut in raw bytes.

    When everything fits, all of it is the head and nothing is missing. When it does not, the head
    gives back an incomplete character at its end and the tail one at its start — the bytes they
    give back are counted with what is missing, so every number stays a count of raw bytes.
    """
    kept = len(captured.head) + len(captured.tail)
    if kept == captured.total:
        text, replaced = decoded(captured.head + captured.tail)
        return CommandOutput(
            head=text,
            tail="",
            cut_after=captured.total,
            missing=0,
            shown=captured.total,
            total=captured.total,
            replaced=replaced,
        )
    head, tail = _whole_head(captured.head), _whole_tail(captured.tail)
    head_text, head_replaced = decoded(head)
    tail_text, tail_replaced = decoded(tail)
    shown = len(head) + len(tail)
    return CommandOutput(
        head=head_text,
        tail=tail_text,
        cut_after=len(head),
        missing=captured.total - shown,
        shown=shown,
        total=captured.total,
        replaced=head_replaced + tail_replaced,
    )


def _whole_head(data: bytes) -> bytes:
    """``data`` without an incomplete UTF-8 sequence at its end."""
    for back in range(1, min(4, len(data)) + 1):
        byte = data[-back]
        if byte & 0xC0 != 0x80:  # the lead of the last sequence, or an ASCII byte
            needed = 2 if byte >= 0xC0 else 1
            needed = 3 if byte >= 0xE0 else needed
            needed = 4 if byte >= 0xF0 else needed
            return data[:-back] if back < needed else data
    return data


def _whole_tail(data: bytes) -> bytes:
    """``data`` without the continuation bytes of a sequence that began before it."""
    start = 0
    while start < min(3, len(data)) and data[start] & 0xC0 == 0x80:
        start += 1
    return data[start:]


def decoded(data: bytes) -> tuple[str, int]:
    """``data`` as ``errors="replace"`` decodes it, and how many sequences were replaced.

    Counted as Python replaces them — one U+FFFD per invalid sequence — and never by counting
    U+FFFD in the text, which a program may print itself. Linear: each decode starts where the last
    error ended, over a view that copies nothing.
    """
    view = memoryview(data)
    parts: list[str] = []
    replaced = 0
    start = 0
    while start < len(view):
        try:
            text, _ = codecs.utf_8_decode(view[start:], "strict", True)
        except UnicodeDecodeError as error:
            valid, _ = codecs.utf_8_decode(view[start : start + error.start], "strict", True)
            parts.extend((valid, "\ufffd"))
            replaced += 1
            start += error.end
            continue
        parts.append(text)
        break
    return "".join(parts), replaced
