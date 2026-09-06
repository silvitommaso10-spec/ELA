"""``workspace.write_note`` (spec §29, LOW): writes a note, only inside the workspace.

The Guardian decides whether ``path`` lies within the capability's scope (``workspace/notes``,
ADR 0011 §4); this tool decides whether it lies within the **workspace** — the directory of
``ELA_WORKSPACE_DIR`` — and refuses everything else before touching the disk (§33, §58). The two
boundaries are checked by two components on purpose (§28: a tool never trusts its caller): the
scope protects the folder, the tool protects the filesystem.

Where the path leads is classified by :mod:`ela.tools.paths`, once for this tool and for its
verifier (ADR 0014 §2): one order, one set of codes, so the two cannot disagree on a path. Each
refusal is a FAILED result with its code and nothing written (ADR 0013 §12): :data:`PATH_INVALID`,
:data:`PATH_OUTSIDE_WORKSPACE`, :data:`PATH_SYMLINK`, :data:`PATH_IS_DIRECTORY`; a target that
cannot be reached or is not a regular file is :data:`IO_ERROR` with the reason — the tool's I/O
failure code, the shared classification in the message. A missing target is what the tool
creates.

The file is then written with ``O_NOFOLLOW`` and mode ``0o600``, its directories with ``0o700``
(§57, as the database directory), and overwritten if it exists: a note is rewritten, which is
what makes a retry after a crash harmless (ADR 0013 §8). A link slipped into an intermediate
directory between the checks and the write is a declared limit of a local, single-user
workspace.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar, Final

from ela.domain import CapabilityId, JsonMapping
from ela.ports import Clock, IdGenerator
from ela.tools.base import ARGUMENTS_INVALID, Outcome, Tool
from ela.tools.paths import (
    PATH_INVALID,
    PATH_IS_DIRECTORY,
    PATH_MISSING,
    PATH_OUTSIDE_WORKSPACE,
    PATH_SYMLINK,
    classify,
    resolve_workspace,
)

__all__ = [
    "DIRECTORY_MODE",
    "FILE_MODE",
    "IO_ERROR",
    "NOTES_TOOL_NAME",
    "WORKSPACE_WRITE_NOTE",
    "WriteNoteTool",
]

WORKSPACE_WRITE_NOTE: Final = CapabilityId("workspace.write_note")
NOTES_TOOL_NAME: Final = "workspace-notes"

IO_ERROR: Final = "io.error"

REFUSALS: Final[frozenset[str]] = frozenset(
    {PATH_INVALID, PATH_OUTSIDE_WORKSPACE, PATH_SYMLINK, PATH_IS_DIRECTORY}
)
"""The path problems the tool names with their own code; the rest is :data:`IO_ERROR`."""

DIRECTORY_MODE: Final = 0o700
FILE_MODE: Final = 0o600
OPEN_FLAGS: Final = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)


class WriteNoteTool(Tool):
    """Writes ``body`` at ``root / path`` (§29), never outside ``root``.

    ``root`` is expanded, made absolute, created if missing (``0o700``) and **resolved**: the
    boundary is the real directory, so a root that is itself a link is followed once, here, and
    every later comparison is against where it really is.
    """

    error_codes: ClassVar[frozenset[str]] = frozenset(
        {
            ARGUMENTS_INVALID,
            PATH_INVALID,
            PATH_SYMLINK,
            PATH_OUTSIDE_WORKSPACE,
            PATH_IS_DIRECTORY,
            IO_ERROR,
        }
    )
    output_keys: ClassVar[frozenset[str]] = frozenset({"path", "bytes"})
    idempotent: ClassVar[bool] = True
    """The note is overwritten with the same body: writing it twice leaves the same file, which
    is what makes the retry of crash window 7a harmless (ADR 0015 §8)."""

    def __init__(
        self, root: Path | str, clock: Clock, ids: IdGenerator, *, name: str = NOTES_TOOL_NAME
    ) -> None:
        super().__init__(WORKSPACE_WRITE_NOTE, clock, ids, name=name)
        Path(root).expanduser().absolute().mkdir(mode=DIRECTORY_MODE, parents=True, exist_ok=True)
        self._root = resolve_workspace(root)

    @property
    def root(self) -> Path:
        """The resolved workspace directory."""
        return self._root

    async def _run(self, arguments: JsonMapping) -> Outcome:
        path = arguments.get("path")
        body = arguments.get("body")
        if not isinstance(path, str) or not isinstance(body, str):
            return Outcome({}, ARGUMENTS_INVALID, "path and body must be strings")
        refused = self._refusal(path)
        if refused is not None:
            return refused
        target = self._root / path
        try:
            target.parent.mkdir(mode=DIRECTORY_MODE, parents=True, exist_ok=True)
            data = body.encode("utf-8")
            descriptor = os.open(target, OPEN_FLAGS, FILE_MODE)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
        except OSError as error:
            return Outcome({}, IO_ERROR, f"{type(error).__name__}: {error.strerror or error}")
        return Outcome({"path": path, "bytes": len(data)})

    def _refusal(self, path: str) -> Outcome | None:
        """The shared classification, read as a writer: a missing note is what gets written."""
        problem = classify(self._root, path)
        if problem is None or problem.code == PATH_MISSING:
            return None
        code = problem.code if problem.code in REFUSALS else IO_ERROR
        return Outcome({}, code, problem.message(path))
