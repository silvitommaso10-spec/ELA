"""``fs.read`` and ``fs.write`` (spec §18): the filesystem outside the workspace (M13.1).

Two boundaries, checked by two components on purpose (§28: a tool never trusts its caller). The
Guardian decides whether ``path`` lies inside the **scope** the capability declares — and since
M13.1 it does so whatever the risk, not only for LOW (dec. C) — while these tools decide whether
it lies inside the **root**, the directory ``ELA_FS_ROOT`` names, and refuse everything else
before touching the disk (§33, §58).

Where a path leads is classified by :mod:`ela.tools.paths`, the same function the verifiers use
(ADR 0014 §2): one order, one set of codes, one place where it is written what a link pointing
outside is called. Nothing here creates the root — ELA never invents the user's folder, and a
missing root refuses every call, which is the answer of §33.

``fs.write`` carries one thing ``workspace.write_note`` does not: ``overwrite``, an **assertion
about the world** rather than a request (M13.1 dec. Q). The question the user answers names the
resolved target and whether something is already there, read from the machine; this tool reads it
again immediately before writing and refuses if it has moved **either way** — a file that appeared
where a creation was approved, or one that vanished where an overwrite was. A criterion that names
one direction is half a defence, and the missing case is the one a race loses.

**The limit that remains, declared.** A component swapped between the classification and the
``open`` is not seen by either — :mod:`ela.tools.notes` declares the same limit for the workspace,
and here it is wider, because the root is the user's own house and not a folder ELA made.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import ClassVar, Final

from ela.domain import CapabilityId, ErrorMetadata, JsonMapping
from ela.ports import Clock, IdGenerator, Prospect, Target
from ela.tools.base import ARGUMENTS_INVALID, Outcome, Tool
from ela.tools.paths import (
    PATH_INVALID,
    PATH_IS_DIRECTORY,
    PATH_MISSING,
    PATH_NOT_REGULAR,
    PATH_OUTSIDE_ROOT,
    PATH_SYMLINK,
    classify,
    resolve_workspace,
)

__all__ = [
    "FS_READ",
    "FS_READ_TOOL_NAME",
    "FS_WRITE",
    "FS_WRITE_TOOL_NAME",
    "CREATES",
    "FILE",
    "OVERWRITES",
    "READS",
    "IO_ERROR",
    "NO_ROOT",
    "OVERWRITE_MISMATCH",
    "FsReadTool",
    "FsWriteTool",
]

FS_READ: Final = CapabilityId("fs.read")
FS_WRITE: Final = CapabilityId("fs.write")
FS_READ_TOOL_NAME: Final = "fs-read"
FS_WRITE_TOOL_NAME: Final = "fs-write"

IO_ERROR: Final = "io.error"
OVERWRITE_MISMATCH: Final = "fs.overwrite_mismatch"
"""What was approved is not what the disk says now, in either direction (M13.1 dec. Q)."""

CREATES: Final = "creates a new file"
OVERWRITES: Final = "overwrites a file that is already there"
READS: Final = "reads a file that is there"
"""What a "yes" does, said by the capability that would do it (M13.1 dec. G, blocker 2).

Three sentences and not one table of two: «overwrites a file that is already there» is true of a
write and false of a read, and an advisory that says the wrong thing teaches the reader to stop
reading it. No surface holds any of them — they travel with the question.
"""

FILE: Final = "file"
"""What the target of ``fs.read`` and ``fs.write`` is called — the tool's word, not a surface's
(M13.2 dec. 12): a page that wrote «Il file» beside every target would be lending it to a
program."""

NO_ROOT: Final = "fs.no_root"
"""The declared root is not there, and ELA does not make it (M13.1 dec. A).

A refusal and not a folder: ``ELA_FS_ROOT`` names the user's own directory, and a tool that
created it would have chosen a place nobody declared. The start-up check refuses a missing root
before anything runs; this is the same answer one syscall from the disk, because a folder can be
removed while ELA is running and ``mkdir(parents=True)`` would put it back without being asked.
"""

WRITE_REFUSALS: Final[frozenset[str]] = frozenset(
    {PATH_INVALID, PATH_OUTSIDE_ROOT, PATH_SYMLINK, PATH_IS_DIRECTORY}
)
"""The path problems ``fs.write`` names with their own code; the rest is :data:`IO_ERROR`."""

READ_REFUSALS: Final[frozenset[str]] = frozenset(
    {PATH_INVALID, PATH_OUTSIDE_ROOT, PATH_SYMLINK, PATH_IS_DIRECTORY, PATH_MISSING}
)
"""And the ones ``fs.read`` names: a missing file is a refusal for a reader, not a target."""

DIRECTORY_MODE: Final = 0o700
FILE_MODE: Final = 0o600
WRITE_FLAGS: Final = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
READ_FLAGS: Final = (
    os.O_RDONLY
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_NONBLOCK", 0)
)
"""Read-only, never through a link, closed on exec — and **non-blocking**.

``O_NONBLOCK`` is not an optimisation: without it the check one line below cannot run. Opening a
FIFO for reading **blocks until somebody opens the other end**, so a target that stopped being a
regular file between the classification and the open would hang the tool instead of being refused
by ``fstat`` — a defence in depth that the syscall never lets reach. On a regular file the flag
changes nothing. Found by writing the test for that race, not by the suite (M13.1)."""
CHUNK: Final = 64 * 1024


class FsReadTool(Tool):
    """Reads the file at ``root / path`` and returns its text (§18, MEDIUM).

    **Where the bytes go** (M13.1 dec. P): into the **result**, which is what ``fs.read`` exists
    for and which stays on its own route with rule 29 — the content and its size, ``bytes``. They
    never reach the audit, which keeps the path (§57, and ADR 0011: what enters an append-only log
    is never redacted); until M13.1b this said the audit kept the size too, and no event ever did.
    A failure carries sizes, never hashes, the way ``WriteNoteVerifier`` already does.

    A file that is not valid UTF-8 is a refusal and not a guess: ELA reads text, and a decoder
    that replaced what it could not read would put something in the result that is not in the
    file.
    """

    error_codes: ClassVar[frozenset[str]] = frozenset(
        {
            ARGUMENTS_INVALID,
            PATH_INVALID,
            PATH_SYMLINK,
            PATH_OUTSIDE_ROOT,
            PATH_IS_DIRECTORY,
            PATH_MISSING,
            NO_ROOT,
            IO_ERROR,
        }
    )
    output_keys: ClassVar[frozenset[str]] = frozenset({"path", "bytes", "content"})
    idempotent: ClassVar[bool] = True
    audit_numbers: ClassVar[frozenset[str]] = frozenset()
    """Reading twice leaves the disk as it was: a retry after a crash costs a second read."""

    def __init__(
        self, root: Path | str, clock: Clock, ids: IdGenerator, *, name: str = FS_READ_TOOL_NAME
    ) -> None:
        super().__init__(FS_READ, clock, ids, name=name)
        self._root = resolve_workspace(root)

    @property
    def root(self) -> Path:
        """The resolved root: ``ELA_FS_ROOT``, never created here."""
        return self._root

    async def prospect(self, arguments: JsonMapping) -> Prospect:
        """What a read of this path would meet now (dec. G, and the rule of ADR 0045 §6-bis)."""
        return _prospect(self._look(arguments), self.name)

    def _look(self, arguments: JsonMapping) -> tuple[Outcome | None, Target | None]:
        """The one place a read decides, read by the question and by the run.

        A file that is not there is **a refusal and not a question**: asking somebody to approve
        a read that cannot succeed is asking for an answer that changes nothing.
        """
        path = arguments.get("path")
        if not isinstance(path, str):
            return Outcome({}, ARGUMENTS_INVALID, "path must be a string"), None
        if not self._root.is_dir():
            return Outcome({}, NO_ROOT, _no_root(self._root)), None
        problem = classify(self._root, path)
        if problem is not None:
            code = problem.code if problem.code in READ_REFUSALS else IO_ERROR
            return Outcome({}, code, problem.message(path)), None
        return None, Target(resolved=str(self._root / path), exists=True, does=READS, label=FILE)

    async def _run(self, arguments: JsonMapping) -> Outcome:
        refused, _ = self._look(arguments)
        if refused is not None:
            return refused
        path = arguments["path"]
        assert isinstance(path, str)
        try:
            data = _read(self._root / path)
        except OSError as error:
            return Outcome({}, IO_ERROR, f"{type(error).__name__}: {error.strerror or error}")
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            return Outcome({}, IO_ERROR, f"{path!r} is not UTF-8 text ({len(data)} bytes)")
        return Outcome({"path": path, "bytes": len(data), "content": content})


class FsWriteTool(Tool):
    """Writes ``body`` at ``root / path``, never outside ``root`` (§18, **HIGH**).

    The first tool of a ``HIGH`` capability, and the reason the row exists at all: outside the
    workspace a write is irreversible while §37 does not exist.
    """

    error_codes: ClassVar[frozenset[str]] = frozenset(
        {
            ARGUMENTS_INVALID,
            PATH_INVALID,
            PATH_SYMLINK,
            PATH_OUTSIDE_ROOT,
            PATH_IS_DIRECTORY,
            OVERWRITE_MISMATCH,
            NO_ROOT,
            IO_ERROR,
        }
    )
    output_keys: ClassVar[frozenset[str]] = frozenset({"path", "bytes", "overwrote"})
    idempotent: ClassVar[bool] = False
    audit_numbers: ClassVar[frozenset[str]] = frozenset()
    """**Not idempotent, and this is the difference from a note.**

    ``workspace.write_note`` may be repeated because rewriting the same body leaves the same
    file. Here a repetition is not the same act: the first run turns a creation into an
    overwrite, so the second one meets a world the approval did not describe and is refused by
    :data:`OVERWRITE_MISMATCH`. Declaring ``True`` would make the executor replay it after a
    crash and call that refusal a failure of the step (ADR 0021 §1).
    """

    def __init__(
        self, root: Path | str, clock: Clock, ids: IdGenerator, *, name: str = FS_WRITE_TOOL_NAME
    ) -> None:
        super().__init__(FS_WRITE, clock, ids, name=name)
        self._root = resolve_workspace(root)

    @property
    def root(self) -> Path:
        """The resolved root: ``ELA_FS_ROOT``, never created here."""
        return self._root

    async def prospect(self, arguments: JsonMapping) -> Prospect:
        """What a write of this path would meet now (dec. G, and ADR 0045 §6-bis).

        **This is where the contradiction is caught.** If the plan asserts «nothing is there» and
        something is, or the other way round, the call would be refused the instant it ran — so
        there is no question to ask, and asking it would be asking somebody to approve what ELA
        already knows it will refuse (ADR 0011 §3).
        """
        return _prospect(self._look(arguments), self.name)

    def _look(self, arguments: JsonMapping) -> tuple[Outcome | None, Target | None]:
        """The one place a write decides: read by the question and by the run.

        The comparison is between the ``overwrite`` the call asserts and the disk. Because the
        question is only composed when the two already agree, the assertion **is** the fact the
        user approved — which is what makes the refusal below true when it fires later.
        """
        path = arguments.get("path")
        body = arguments.get("body")
        overwrite = arguments.get("overwrite")
        if not isinstance(path, str) or not isinstance(body, str):
            return Outcome({}, ARGUMENTS_INVALID, "path and body must be strings"), None
        if not isinstance(overwrite, bool):
            return Outcome({}, ARGUMENTS_INVALID, "overwrite must be a boolean"), None
        if not self._root.is_dir():
            return Outcome({}, NO_ROOT, _no_root(self._root)), None
        problem = classify(self._root, path)
        if problem is not None and problem.code != PATH_MISSING:
            code = problem.code if problem.code in WRITE_REFUSALS else IO_ERROR
            return Outcome({}, code, problem.message(path)), None
        there = problem is None
        if there is not overwrite:
            return Outcome({}, OVERWRITE_MISMATCH, _moved(path, declared=overwrite)), None
        does = OVERWRITES if there else CREATES
        return None, Target(resolved=str(self._root / path), exists=there, does=does, label=FILE)

    async def _run(self, arguments: JsonMapping) -> Outcome:
        refused, _ = self._look(arguments)
        if refused is not None:
            return refused
        path, body = arguments["path"], arguments["body"]
        assert isinstance(path, str) and isinstance(body, str)
        target = self._root / path
        try:
            target.parent.mkdir(mode=DIRECTORY_MODE, parents=True, exist_ok=True)
            data = body.encode("utf-8")
            descriptor = os.open(target, WRITE_FLAGS, FILE_MODE)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
        except OSError as error:
            return Outcome({}, IO_ERROR, f"{type(error).__name__}: {error.strerror or error}")
        return Outcome(
            {"path": path, "bytes": len(data), "overwrote": bool(arguments["overwrite"])}
        )


def _prospect(looked: tuple[Outcome | None, Target | None], tool_name: str) -> Prospect:
    """A tool's own refusal, turned into what the executor needs before asking.

    The conversion and nothing else: the decision was taken in ``_look``, which is also what runs
    when the tool really runs. One fact, one definition, one place.
    """
    refused, target = looked
    if refused is None:
        return Prospect(target=target)
    return Prospect(
        refusal=ErrorMetadata(
            code=refused.code or IO_ERROR,
            message=refused.message,
            tool_name=tool_name,
            retryable=refused.retryable,
        )
    )


def _no_root(root: Path) -> str:
    """The root, which is a configured directory and never the user's content (§57)."""
    return f"{root} is not there: ELA does not create the folder you declared in ELA_FS_ROOT"


def _moved(path: str, *, declared: bool) -> str:
    """Both directions, named (M13.1 dec. Q). The path, never the content (§57).

    **«Declared», not «approved»**, and the word carries the whole of ADR 0045 §6-bis. This
    refusal is born in two places: before the question, where nobody has approved anything yet,
    and before the write, where what was approved *is* what the plan declared — because the
    question is composed only when the declaration and the disk already agree. «Approved» would
    be a false diagnosis in the first place and a true one in the second; «declared» is true in
    both, so there is one message and not two.
    """
    if declared:
        return f"{path!r} was declared as an overwrite and nothing is there now"
    return f"{path!r} was declared as a new file and something is there now"


def _read(target: Path) -> bytes:
    """The file's bytes, opened read-only and never through a link.

    ``fstat`` on the open descriptor reconfirms the regular file the classification saw: between
    the two something could have changed, and what is read is what the descriptor holds.
    """
    descriptor = os.open(target, READ_FLAGS)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError(PATH_NOT_REGULAR)
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, CHUNK):
            chunks.append(chunk)
    finally:
        os.close(descriptor)
    return b"".join(chunks)
