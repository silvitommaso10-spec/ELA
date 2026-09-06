"""Where a note path leads, classified once for the tool and for its verifier (ADR 0014 §2,
review of M5.2).

The tool refuses a path before writing; the verifier refuses the same path before reading. If
each had its own checks they could disagree — on the order, on the codes, on what a link that
points outside is called — and a note the tool accepted could be one the verifier cannot find.
So the classification lives here, once, and is **read-only by construction**: ``resolve``,
``is_symlink`` and ``lstat`` only, never ``open``, never a write (rule 18 covers this module as
it covers the verifiers).

:func:`classify` answers in one order, the first problem naming itself:

1. :data:`PATH_INVALID` — not a relative POSIX path, or with an empty, ``.`` or ``..`` segment,
   a backslash or a NUL. ``a/../b`` is refused even though it would resolve inside: traversal
   is refused as a *shape*, not as an outcome.
2. :data:`PATH_OUTSIDE_WORKSPACE` — ``(root / path).resolve()`` is not under the resolved root:
   a link that points outside lands here.
3. :data:`PATH_SYMLINK` — an existing component of ``root / path`` is a symbolic link, even one
   that points inside: going *through* a link is a doubt (§33).
4. :data:`PATH_UNREACHABLE` — the OS cannot look at the target (a component that is a file, a
   loop, a permission): the error's type, never an exception.
5. :data:`PATH_MISSING` — nothing is there. The tool will create it; the verifier will not
   find it.
6. :data:`PATH_IS_DIRECTORY` — the target is a directory.
7. :data:`PATH_NOT_REGULAR` — the target exists and is neither a regular file nor a directory
   (a FIFO, a socket, a device).

``None`` means a regular file is there. Which of these a caller treats as a refusal is the
caller's: the tool writes over :data:`PATH_MISSING`; the verifier reads only ``None``.
"""

from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Final

__all__ = [
    "PATH_CODES",
    "PATH_INVALID",
    "PATH_IS_DIRECTORY",
    "PATH_MISSING",
    "PATH_NOT_REGULAR",
    "PATH_OUTSIDE_WORKSPACE",
    "PATH_SYMLINK",
    "PATH_UNREACHABLE",
    "PathProblem",
    "classify",
    "is_relative_note_path",
    "resolve_workspace",
]

PATH_INVALID: Final = "path.invalid"
PATH_OUTSIDE_WORKSPACE: Final = "path.outside_workspace"
PATH_SYMLINK: Final = "path.symlink"
PATH_UNREACHABLE: Final = "path.unreachable"
PATH_MISSING: Final = "path.missing"
PATH_IS_DIRECTORY: Final = "path.is_directory"
PATH_NOT_REGULAR: Final = "path.not_regular"

PATH_CODES: Final[frozenset[str]] = frozenset(
    {
        PATH_INVALID,
        PATH_OUTSIDE_WORKSPACE,
        PATH_SYMLINK,
        PATH_UNREACHABLE,
        PATH_MISSING,
        PATH_IS_DIRECTORY,
        PATH_NOT_REGULAR,
    }
)
"""Every code :func:`classify` can answer with: one set, shared by the tool and the verifier."""

FORBIDDEN_PARTS: Final[frozenset[str]] = frozenset({"", ".", ".."})
FORBIDDEN_CHARACTERS: Final = ("\\", "\0")


@dataclass(frozen=True, slots=True)
class PathProblem:
    """Why ``root / path`` is not a regular file to write or read: a code and the reason.

    ``reason`` is worded to follow the path — ``"'a/../b' is not a relative path…"`` — and
    names nothing but the path and the OS error's type (§57).
    """

    code: str
    reason: str

    def message(self, path: str) -> str:
        return f"{path!r} {self.reason}"


def is_relative_note_path(path: str) -> bool:
    """Whether ``path`` has the shape a note path must have (check 1).

    Relative, with no empty, ``.`` or ``..`` segment, no backslash and no NUL: the syntax of a
    scope entry (ADR 0010 §3), restated here because a tool imports nothing of the Guardian.
    """
    if any(character in path for character in FORBIDDEN_CHARACTERS):
        return False
    return not any(part in FORBIDDEN_PARTS for part in path.split("/"))


def resolve_workspace(root: Path | str) -> Path:
    """Where the workspace really is: ``root`` expanded, made absolute and resolved.

    Shared by the tool and its verifier so that the two agree on the boundary; nothing is
    created here — the tool creates the directory before resolving it, the verifier never does.
    """
    return Path(root).expanduser().absolute().resolve()


def classify(root: Path, path: str) -> PathProblem | None:
    """The problem with ``root / path`` in the order of the module docstring, or ``None`` if a
    regular file is there. ``root`` is a resolved directory. Reads only."""
    if not is_relative_note_path(path):
        return PathProblem(PATH_INVALID, "is not a relative path without '.', '..' or '\\'")
    target = root / path
    try:
        if not target.resolve().is_relative_to(root):
            return PathProblem(PATH_OUTSIDE_WORKSPACE, "resolves outside the workspace")
        current = root
        for part in path.split("/"):
            current = current / part
            if current.is_symlink():
                return PathProblem(PATH_SYMLINK, "goes through a symbolic link")
        mode = target.lstat().st_mode
    except FileNotFoundError:
        return PathProblem(PATH_MISSING, "does not exist")
    except OSError as error:  # a component that is a file, a loop, a permission
        return PathProblem(PATH_UNREACHABLE, f"cannot be reached: {type(error).__name__}")
    if stat.S_ISDIR(mode):
        return PathProblem(PATH_IS_DIRECTORY, "is a directory")
    if not stat.S_ISREG(mode):
        return PathProblem(PATH_NOT_REGULAR, "is not a regular file")
    return None
