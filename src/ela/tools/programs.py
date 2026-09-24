"""Which programs ``terminal.run`` may launch, and whether each is still the one of the start-up
(M13.2 dec. 3, 4; ADR 0047).

The shape of :mod:`ela.tools.paths`, one module for the tool and its verifier: the tool refuses a
program before the question and again before the launch, the verifier reads the same fact after,
and two copies of «is this still the program» would be two answers (ADR 0014 §2). **Read-only by
construction** — ``realpath``, ``stat``, ``access`` and a read to hash, never a write (rule 18
covers this module as it covers the verifiers).

**One definition of «declared program»: the table fixed at start-up.** Every entry of
``ELA_TERMINAL_PROGRAMS`` is resolved **once** — the file the declared path leads to, and the sha256
of its content — and every later reading is compared with that. A path the Guardian lets through
because it starts with a declared one (``usr/bin/git/x``, the prefix of the scope's grammar) is not
in the table, and is refused as :data:`NOT_DECLARED`: a file has no children.

**What this does not protect**, declared: a program changed **before** the start is the program the
start fixed; and the window between the last comparison and the ``exec`` stays open — the one ADR
0045 §7 declares between ``classify`` and ``open`` —, because closing it would mean executing from a
descriptor already open and verified, and macOS has no ``fexecve``.
"""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

__all__ = [
    "NOT_DECLARED",
    "NO_PROGRAM",
    "PROGRAM_CHANGED",
    "PROGRAM_CODES",
    "Identity",
    "ProgramProblem",
    "Programs",
    "identity_of",
]

NOT_DECLARED: Final = "terminal.not_declared"
"""A program that is not one of those whose identity was fixed at start-up."""
NO_PROGRAM: Final = "terminal.no_program"
"""Nothing that runs is there now: missing, a dangling link, a file that does not execute."""
PROGRAM_CHANGED: Final = "terminal.program_changed"
"""The file the declared path leads to is not the one of the start-up — another file, or another
content, or one that was not there then (dec. 4)."""
PROGRAM_CODES: Final[frozenset[str]] = frozenset({NOT_DECLARED, NO_PROGRAM, PROGRAM_CHANGED})

CHUNK: Final = 1 << 20


@dataclass(frozen=True, slots=True)
class Identity:
    """What a declared path leads to: the file, and the digest of what it holds.

    ``runs`` is ``None`` when nothing is there; ``digest`` is ``None`` when nothing that executes is
    there — absent, a folder, a file without the execute bit — or when what is there cannot be read,
    because a program ELA cannot hash is a program whose identity it cannot vouch for. Two
    identities are the same program only if both halves agree.
    """

    runs: str | None
    digest: str | None

    @property
    def executable(self) -> bool:
        return self.digest is not None


@dataclass(frozen=True, slots=True)
class ProgramProblem:
    """Why a program is not the one to launch: a code, and a sentence that names the path.

    The path is configuration the user wrote, never the user's content (§57); the sentence says
    what to do when there is something to do.
    """

    code: str
    message: str


def identity_of(entry: str) -> Identity:
    """What ``/entry`` leads to now: read from the disk, never from what a plan said."""
    resolved = os.path.realpath("/" + entry)
    try:
        mode = os.stat(resolved).st_mode
    except OSError:  # nothing there, a dangling link, a component that is not a folder
        return Identity(runs=None, digest=None)
    if not stat.S_ISREG(mode) or not os.access(resolved, os.X_OK):
        return Identity(runs=resolved, digest=None)
    try:
        digest = _sha256(resolved)
    except OSError:  # it went away between the stat and the read: nothing that runs is there
        return Identity(runs=resolved, digest=None)
    return Identity(runs=resolved, digest=digest)


def _sha256(path: str) -> str:
    hashed = hashlib.sha256()
    with open(path, "rb") as handle:  # noqa: PTH123 — a read, the only one this module does
        while chunk := handle.read(CHUNK):
            hashed.update(chunk)
    return hashed.hexdigest()


class Programs:
    """The programs ``terminal.run`` may launch, each with the identity of the start-up."""

    __slots__ = ("_table",)

    def __init__(self, table: Mapping[str, Identity]) -> None:
        self._table: Mapping[str, Identity] = MappingProxyType(dict(table))

    @classmethod
    def fixed(cls, entries: Iterable[str]) -> Programs:
        """Resolve every entry **now**, once: the start-up of ELA, and nothing later."""
        return cls({entry: identity_of(entry) for entry in entries})

    def at_start(self, entry: str) -> Identity | None:
        """The identity fixed at start-up, or ``None`` for an entry nobody declared."""
        return self._table.get(entry)

    def problem(self, entry: str) -> ProgramProblem | None:
        """Why ``entry`` is not the program to launch now, or ``None`` if it is (dec. 4, 5)."""
        full = "/" + entry
        start = self._table.get(entry)
        if start is None:
            return ProgramProblem(
                NOT_DECLARED,
                f"{full!r} is not one of the programs declared in ELA_TERMINAL_PROGRAMS",
            )
        now = identity_of(entry)
        if not now.executable:
            return ProgramProblem(
                NO_PROGRAM, f"{full!r} is not there, does not execute, or cannot be read"
            )
        if now != start:
            return ProgramProblem(
                PROGRAM_CHANGED,
                f"{full!r} changed after ELA started (an update, for instance): "
                "restart ELA to accept it",
            )
        return None
