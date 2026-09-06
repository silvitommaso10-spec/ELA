"""``workspace.write_note`` (spec §29, LOW): writes a note, only inside the workspace.

The Guardian decides whether ``path`` lies within the capability's scope (``workspace/notes``,
ADR 0011 §4); this tool decides whether it lies within the **workspace** — the directory of
``ELA_WORKSPACE_DIR`` — and refuses everything else before touching the disk (§33, §58). The two
boundaries are checked by two components on purpose (§28: a tool never trusts its caller): the
scope protects the folder, the tool protects the filesystem.

Four checks, in order, each a FAILED result with its code and nothing written (ADR 0013 §12):

1. :data:`PATH_INVALID` — ``path`` is a relative POSIX path with no empty, ``.`` or ``..``
   segment, no backslash, no NUL. ``a/../b`` is refused even though it would resolve inside:
   traversal is refused as a *shape*, not as an outcome.
2. :data:`PATH_SYMLINK` — no existing component of ``root / path`` is a symbolic link, whether
   it points inside or outside the workspace: writing *through* a link is a doubt.
3. :data:`PATH_OUTSIDE_WORKSPACE` — the resolved target is not under the resolved root: the
   safety net behind 1 and 2.
4. :data:`PATH_IS_DIRECTORY` — the target exists and is a directory.

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

__all__ = [
    "DIRECTORY_MODE",
    "FILE_MODE",
    "IO_ERROR",
    "NOTES_TOOL_NAME",
    "PATH_INVALID",
    "PATH_IS_DIRECTORY",
    "PATH_OUTSIDE_WORKSPACE",
    "PATH_SYMLINK",
    "WORKSPACE_WRITE_NOTE",
    "WriteNoteTool",
    "is_relative_note_path",
]

WORKSPACE_WRITE_NOTE: Final = CapabilityId("workspace.write_note")
NOTES_TOOL_NAME: Final = "workspace-notes"

PATH_INVALID: Final = "path.invalid"
PATH_SYMLINK: Final = "path.symlink"
PATH_OUTSIDE_WORKSPACE: Final = "path.outside_workspace"
PATH_IS_DIRECTORY: Final = "path.is_directory"
IO_ERROR: Final = "io.error"

FORBIDDEN_PARTS: Final[frozenset[str]] = frozenset({"", ".", ".."})
FORBIDDEN_CHARACTERS: Final = ("\\", "\0")
DIRECTORY_MODE: Final = 0o700
FILE_MODE: Final = 0o600
OPEN_FLAGS: Final = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)


def is_relative_note_path(path: str) -> bool:
    """Whether ``path`` has the shape a note path must have (check 1).

    Relative, with no empty, ``.`` or ``..`` segment, no backslash and no NUL: the syntax of a
    scope entry (ADR 0010 §3), restated here because a tool imports nothing of the Guardian.
    """
    if any(character in path for character in FORBIDDEN_CHARACTERS):
        return False
    return not any(part in FORBIDDEN_PARTS for part in path.split("/"))


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

    def __init__(
        self, root: Path | str, clock: Clock, ids: IdGenerator, *, name: str = NOTES_TOOL_NAME
    ) -> None:
        super().__init__(WORKSPACE_WRITE_NOTE, clock, ids, name=name)
        directory = Path(root).expanduser().absolute()
        directory.mkdir(mode=DIRECTORY_MODE, parents=True, exist_ok=True)
        self._root = directory.resolve()

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
        """Checks 1–4 of the module docstring; the first that fails names itself."""
        if not is_relative_note_path(path):
            return Outcome(
                {}, PATH_INVALID, f"{path!r} is not a relative path without '.', '..' or '\\'"
            )
        current = self._root
        for part in path.split("/"):
            current = current / part
            if current.is_symlink():
                return Outcome({}, PATH_SYMLINK, f"{path!r} goes through a symbolic link")
        target = self._root / path
        if not target.resolve().is_relative_to(self._root):
            return Outcome({}, PATH_OUTSIDE_WORKSPACE, f"{path!r} resolves outside the workspace")
        if target.is_dir():
            return Outcome({}, PATH_IS_DIRECTORY, f"{path!r} is a directory")
        return None
