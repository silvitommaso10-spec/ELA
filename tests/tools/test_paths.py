"""``ela.tools.paths`` (ADR 0014 §2, review of M5.2): one classification of a note path, shared
by the tool and by its verifier, so that the two can never disagree on where a path leads.

The parity test is the point: for every malformed or misplaced path, the tool refuses to write
and the verifier refuses to verify **with the same code**. The two problems only a reader can
see (a target that is not a regular file, a target the OS cannot look at) are the tool's
``io.error`` with the shared reason in the message — the tool's own codes are fixed by ADR 0013.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Callable
from pathlib import Path

import pytest

from ela.domain import ExecutionStatus
from ela.testing.fakes import FakeClock, FakeIdGenerator
from ela.tools import (
    IO_ERROR,
    NOTE_EXISTS,
    PATH_CODES,
    PATH_INVALID,
    PATH_IS_DIRECTORY,
    PATH_MISSING,
    PATH_NOT_REGULAR,
    PATH_OUTSIDE_WORKSPACE,
    PATH_SYMLINK,
    PATH_UNREACHABLE,
    WORKSPACE_WRITE_NOTE,
    PathProblem,
    WriteNoteTool,
    WriteNoteVerifier,
    classify,
    is_relative_note_path,
    resolve_workspace,
)
from tests.tools.support import allowed
from tests.tools.test_verifiers import snapshot, succeeded

BODY = "body\n"
Setup = Callable[[Path, Path], str]
"""Arranges the workspace (``root``) and the outside (``tmp_path``); returns the path to ask."""


def _shape(path: str) -> Setup:
    return lambda root, tmp: path


def _dir_link_outside(root: Path, tmp: Path) -> str:
    (tmp / "elsewhere").mkdir()
    (root / "out").symlink_to(tmp / "elsewhere", target_is_directory=True)
    return "out/a.md"


def _file_link_outside(root: Path, tmp: Path) -> str:
    (tmp / "secret.md").write_text("untouched", encoding="utf-8")
    (root / "notes").mkdir()
    (root / "notes" / "a.md").symlink_to(tmp / "secret.md")
    return "notes/a.md"


def _link_inside(root: Path, tmp: Path) -> str:
    (root / "real").mkdir()
    (root / "alias").symlink_to(root / "real", target_is_directory=True)
    return "alias/a.md"


def _directory(root: Path, tmp: Path) -> str:
    (root / "workspace" / "notes").mkdir(parents=True)
    return "workspace/notes"


def _under_a_file(root: Path, tmp: Path) -> str:
    (root / "workspace").write_text("a file where a directory should be", encoding="utf-8")
    return "workspace/notes/a.md"


def _fifo(root: Path, tmp: Path) -> str:
    (root / "notes").mkdir()
    os.mkfifo(root / "notes" / "a.md")
    return "notes/a.md"


REFUSED_BY_BOTH: list[tuple[str, Setup, str]] = [
    *[
        (f"shape {p!r}", _shape(p), PATH_INVALID)
        for p in [
            "../x.md",
            "/etc/x.md",
            "a//b.md",
            "a\\b.md",
            "",
            "./a.md",
            "a/../b.md",
            "a\0b.md",
        ]
    ],
    ("directory link outside", _dir_link_outside, PATH_OUTSIDE_WORKSPACE),
    ("file link outside", _file_link_outside, PATH_OUTSIDE_WORKSPACE),
    ("link inside", _link_inside, PATH_SYMLINK),
    ("directory", _directory, PATH_IS_DIRECTORY),
]
READER_ONLY: list[tuple[str, Setup, str]] = [
    ("under a file", _under_a_file, PATH_UNREACHABLE),
    ("fifo", _fifo, PATH_NOT_REGULAR),
]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "workspace"


async def _tool_and_verifier(root: Path, path: str) -> tuple[str | None, str, str | None, str]:
    """(tool code, tool message, verifier code, verifier message) for ``path``."""
    tool = WriteNoteTool(root, FakeClock(), FakeIdGenerator())
    verifier = WriteNoteVerifier(root)
    before = snapshot(root)
    result = await tool.execute(allowed(WORKSPACE_WRITE_NOTE), {"path": path, "body": BODY})
    assert result.status is ExecutionStatus.FAILED and result.error is not None
    assert snapshot(root) == before  # the tool wrote nothing
    failures = await verifier.verify(
        (NOTE_EXISTS,), {"path": path, "body": BODY}, succeeded(WORKSPACE_WRITE_NOTE)
    )
    assert snapshot(root) == before  # the verifier changed nothing
    (failure,) = failures
    return result.error.code, result.error.message, failure.code, failure.message


@pytest.mark.parametrize(
    ("case", "setup", "code"), REFUSED_BY_BOTH, ids=[c for c, _, _ in REFUSED_BY_BOTH]
)
async def test_tool_and_verifier_refuse_a_malformed_path_with_the_same_code(
    root: Path, tmp_path: Path, case: str, setup: Setup, code: str
) -> None:
    root.mkdir()
    path = setup(root, tmp_path)
    tool_code, tool_message, verifier_code, verifier_message = await _tool_and_verifier(root, path)
    assert tool_code == verifier_code == code, case
    assert tool_message == verifier_message, case


@pytest.mark.parametrize(("case", "setup", "code"), READER_ONLY, ids=[c for c, _, _ in READER_ONLY])
async def test_what_only_a_reader_can_name_is_the_tools_io_error_with_the_shared_reason(
    root: Path, tmp_path: Path, case: str, setup: Setup, code: str
) -> None:
    root.mkdir()
    path = setup(root, tmp_path)
    tool_code, tool_message, verifier_code, verifier_message = await _tool_and_verifier(root, path)
    assert verifier_code == code, case
    assert tool_code == IO_ERROR, case
    assert tool_message == verifier_message, case


# --------------------------------------------------------------------------------------
# classify on its own
# --------------------------------------------------------------------------------------


def test_the_codes_are_seven_and_the_problem_carries_the_path_in_its_message() -> None:
    assert {
        PATH_INVALID,
        PATH_OUTSIDE_WORKSPACE,
        PATH_SYMLINK,
        PATH_UNREACHABLE,
        PATH_MISSING,
        PATH_IS_DIRECTORY,
        PATH_NOT_REGULAR,
    } == PATH_CODES
    problem = PathProblem(PATH_MISSING, "does not exist")
    assert problem.message("a/b.md") == "'a/b.md' does not exist"


def test_a_regular_file_is_no_problem_and_a_missing_one_is_missing(root: Path) -> None:
    (root / "notes").mkdir(parents=True)
    (root / "notes" / "a.md").write_text("x", encoding="utf-8")
    real = resolve_workspace(root)
    assert classify(real, "notes/a.md") is None
    missing = classify(real, "notes/b.md")
    assert missing == PathProblem(PATH_MISSING, "does not exist")
    assert classify(real, "nowhere/at/all.md") == PathProblem(PATH_MISSING, "does not exist")


def test_the_order_is_shape_then_outside_then_link_then_target(root: Path, tmp_path: Path) -> None:
    """A link that points outside is 'outside' (2 before 3); one that points inside is 'a link'
    (3 before 5); a link to a directory outside is still 'outside', not 'a directory'."""
    root.mkdir()
    (tmp_path / "elsewhere").mkdir()
    (root / "out").symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    (root / "real").mkdir()
    (root / "alias").symlink_to(root / "real", target_is_directory=True)
    real = resolve_workspace(root)
    assert classify(real, "../out").code == PATH_INVALID
    assert classify(real, "out").code == PATH_OUTSIDE_WORKSPACE
    assert classify(real, "out/a.md").code == PATH_OUTSIDE_WORKSPACE
    assert classify(real, "alias").code == PATH_SYMLINK
    assert classify(real, "alias/a.md").code == PATH_SYMLINK
    assert classify(real, "real").code == PATH_IS_DIRECTORY


def test_a_fifo_is_not_regular_and_a_path_under_a_file_is_unreachable(root: Path) -> None:
    root.mkdir()
    os.mkfifo(root / "pipe")
    assert stat.S_ISFIFO((root / "pipe").lstat().st_mode)
    (root / "file.md").write_text("x", encoding="utf-8")
    real = resolve_workspace(root)
    assert classify(real, "pipe") == PathProblem(PATH_NOT_REGULAR, "is not a regular file")
    assert classify(real, "file.md/x") == PathProblem(
        PATH_UNREACHABLE, "cannot be reached: NotADirectoryError"
    )


@pytest.mark.parametrize("path", ["a.md", "a/b.md", "workspace/notes/x.md", "a.b/c-d_e.md"])
def test_well_formed_relative_paths(path: str) -> None:
    assert is_relative_note_path(path)


def test_the_module_reads_only(root: Path) -> None:
    """Behavioural twin of rule 18: classifying every kind of path leaves the tree untouched."""
    (root / "notes").mkdir(parents=True)
    (root / "notes" / "a.md").write_text("x", encoding="utf-8")
    real = resolve_workspace(root)
    before = snapshot(root)
    for path in ["notes/a.md", "notes/b.md", "notes", "../x", "notes/a.md/x", "new/dir/c.md"]:
        classify(real, path)
    assert snapshot(root) == before
    assert not (root / "new").exists()
