"""``WriteNoteTool`` (§29, LOW): writes inside the workspace and nowhere else (ADR 0013 §12).

Every negative case asserts two things: the result names the refusal, and the filesystem is
untouched — no file created inside or outside the root, no link target rewritten.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from ela.domain import ExecutionStatus, PermissionOutcome
from ela.ports import NotAllowedError
from ela.testing.fakes import FakeClock, FakeIdGenerator
from ela.tools import (
    ARGUMENTS_INVALID,
    DIRECTORY_MODE,
    FILE_MODE,
    IO_ERROR,
    NOTES_TOOL_NAME,
    PATH_INVALID,
    PATH_IS_DIRECTORY,
    PATH_OUTSIDE_WORKSPACE,
    PATH_SYMLINK,
    WORKSPACE_WRITE_NOTE,
    WriteNoteTool,
    is_relative_note_path,
)
from tests.tools.support import allowed

NOTE = "workspace/notes/briefing.md"
BODY = "# Briefing\n\nTre punti.\n"
DECISION = allowed(WORKSPACE_WRITE_NOTE)


def snapshot(directory: Path) -> set[tuple[str, int | None]]:
    """Every entry under ``directory`` with its size, to prove nothing changed."""
    found: set[tuple[str, int | None]] = set()
    for path in directory.rglob("*"):
        size = path.stat().st_size if path.is_file() and not path.is_symlink() else None
        found.add((str(path.relative_to(directory)), size))
    return found


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "workspace"


@pytest.fixture
def tool(root: Path) -> WriteNoteTool:
    return WriteNoteTool(root, FakeClock(), FakeIdGenerator())


async def test_writes_the_note_privately_and_reports_it(tool: WriteNoteTool, root: Path) -> None:
    result = await tool.execute(DECISION, {"path": NOTE, "body": BODY})
    assert result.status is ExecutionStatus.SUCCEEDED
    written = root / NOTE
    assert written.read_text(encoding="utf-8") == BODY
    assert result.output == {"path": NOTE, "bytes": len(BODY.encode("utf-8"))}
    assert result.tool_name == NOTES_TOOL_NAME
    assert result.error is None
    assert stat.S_IMODE(written.stat().st_mode) == FILE_MODE
    assert stat.S_IMODE(written.parent.stat().st_mode) == DIRECTORY_MODE
    assert stat.S_IMODE(root.stat().st_mode) == DIRECTORY_MODE


async def test_overwrites_an_existing_note(tool: WriteNoteTool, root: Path) -> None:
    await tool.execute(DECISION, {"path": NOTE, "body": "first, and longer"})
    result = await tool.execute(DECISION, {"path": NOTE, "body": "second"})
    assert result.status is ExecutionStatus.SUCCEEDED
    assert (root / NOTE).read_text(encoding="utf-8") == "second"


def test_the_root_is_created_expanded_and_resolved(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    tool = WriteNoteTool(link, FakeClock(), FakeIdGenerator())
    assert tool.root == real.resolve()
    fresh = WriteNoteTool(tmp_path / "new" / "deeper", FakeClock(), FakeIdGenerator())
    assert fresh.root.is_dir()
    assert stat.S_IMODE(fresh.root.stat().st_mode) == DIRECTORY_MODE


def test_a_tilde_in_the_root_is_the_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    tool = WriteNoteTool("~/notes", FakeClock(), FakeIdGenerator())
    assert tool.root == (tmp_path / "notes").resolve()


async def test_a_root_that_is_a_link_writes_into_the_real_directory(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    tool = WriteNoteTool(link, FakeClock(), FakeIdGenerator())
    result = await tool.execute(DECISION, {"path": "a.md", "body": "x"})
    assert result.status is ExecutionStatus.SUCCEEDED
    assert (real / "a.md").read_text(encoding="utf-8") == "x"


# --------------------------------------------------------------------------------------
# Refusals: nothing is written, inside or outside
# --------------------------------------------------------------------------------------


async def refused(tool: WriteNoteTool, root: Path, arguments: dict[str, object], code: str) -> str:
    before_root, before_parent = snapshot(root), snapshot(root.parent)
    result = await tool.execute(DECISION, arguments)
    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None
    assert result.error.code == code, result.error.message
    assert result.error.tool_name == tool.name
    assert result.output == {}
    assert snapshot(root) == before_root
    assert snapshot(root.parent) == before_parent
    return result.error.message


@pytest.mark.parametrize(
    "path",
    [
        "../x.md",
        "a/../../x.md",
        "a/../b.md",
        "..",
        "/etc/x.md",
        "./a.md",
        "a/./b.md",
        "a//b.md",
        "a/",
        "/",
        "",
        "a\\b.md",
        "C:\\x.md",
        "a\0b.md",
    ],
    ids=repr,
)
async def test_traversal_absolute_and_malformed_paths_are_refused(
    tool: WriteNoteTool, root: Path, path: str
) -> None:
    await refused(tool, root, {"path": path, "body": BODY}, PATH_INVALID)
    assert not is_relative_note_path(path)


async def test_an_absolute_path_inside_the_root_is_still_refused(
    tool: WriteNoteTool, root: Path
) -> None:
    """Absolute is absolute, even when it would land inside: the shape is wrong."""
    await refused(tool, root, {"path": str(root / "inside.md"), "body": BODY}, PATH_INVALID)


@pytest.mark.parametrize(
    "arguments",
    [
        {"body": BODY},
        {"path": NOTE},
        {"path": 42, "body": BODY},
        {"path": NOTE, "body": ["not", "text"]},
        {"path": None, "body": None},
    ],
    ids=repr,
)
async def test_missing_or_non_string_arguments_are_refused(
    tool: WriteNoteTool, root: Path, arguments: dict[str, object]
) -> None:
    await refused(tool, root, arguments, ARGUMENTS_INVALID)


async def test_a_directory_link_to_the_outside_is_refused_and_the_outside_untouched(
    tool: WriteNoteTool, root: Path, tmp_path: Path
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (root / "notes").symlink_to(elsewhere, target_is_directory=True)
    message = await refused(
        tool, root, {"path": "notes/a.md", "body": BODY}, PATH_OUTSIDE_WORKSPACE
    )
    assert "notes/a.md" in message
    assert list(elsewhere.iterdir()) == []


async def test_a_file_link_to_the_outside_is_refused_and_its_target_unchanged(
    tool: WriteNoteTool, root: Path, tmp_path: Path
) -> None:
    secret = tmp_path / "secret.md"
    secret.write_text("untouched", encoding="utf-8")
    (root / "notes").mkdir()
    (root / "notes" / "a.md").symlink_to(secret)
    await refused(tool, root, {"path": "notes/a.md", "body": BODY}, PATH_OUTSIDE_WORKSPACE)
    assert secret.read_text(encoding="utf-8") == "untouched"


async def test_a_link_pointing_inside_the_root_is_refused_too(
    tool: WriteNoteTool, root: Path
) -> None:
    (root / "real").mkdir()
    (root / "alias").symlink_to(root / "real", target_is_directory=True)
    await refused(tool, root, {"path": "alias/a.md", "body": BODY}, PATH_SYMLINK)
    assert list((root / "real").iterdir()) == []


async def test_a_link_to_the_outside_is_named_as_outside_a_link_inside_as_a_link(
    tool: WriteNoteTool, root: Path, tmp_path: Path
) -> None:
    """One classification for the tool and the verifier (ela.tools.paths): where the path
    resolves is checked before the links, so a link that escapes is "outside" and a link that
    stays is "a link" — the same code the verifier answers with."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (root / "out").symlink_to(elsewhere, target_is_directory=True)
    (root / "real").mkdir()
    (root / "in").symlink_to(root / "real", target_is_directory=True)
    outside = await refused(tool, root, {"path": "out/a.md", "body": BODY}, PATH_OUTSIDE_WORKSPACE)
    inside = await refused(tool, root, {"path": "in/a.md", "body": BODY}, PATH_SYMLINK)
    assert "resolves outside the workspace" in outside
    assert "symbolic link" in inside
    assert list(elsewhere.iterdir()) == [] and list((root / "real").iterdir()) == []


async def test_a_directory_target_is_refused(tool: WriteNoteTool, root: Path) -> None:
    (root / "workspace" / "notes").mkdir(parents=True)
    await refused(tool, root, {"path": "workspace/notes", "body": BODY}, PATH_IS_DIRECTORY)
    assert (root / "workspace" / "notes").is_dir()


async def test_an_os_error_is_a_failed_result_not_an_exception(
    tool: WriteNoteTool, root: Path
) -> None:
    (root / "workspace").write_text("a file where a directory should be", encoding="utf-8")
    message = await refused(tool, root, {"path": NOTE, "body": BODY}, IO_ERROR)
    assert "cannot be reached: NotADirectoryError" in message


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no FIFOs on this platform")
async def test_a_target_that_is_not_a_regular_file_is_an_io_error(
    tool: WriteNoteTool, root: Path
) -> None:
    """A FIFO or a socket at the path: the shared classification says not regular, the tool
    names it with its own I/O code and never opens it (an open for writing would block)."""
    (root / "workspace" / "notes").mkdir(parents=True)
    os.mkfifo(root / NOTE)
    message = await refused(tool, root, {"path": NOTE, "body": BODY}, IO_ERROR)
    assert "is not a regular file" in message


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
async def test_a_read_only_directory_is_an_io_error(tool: WriteNoteTool, root: Path) -> None:
    folder = root / "workspace" / "notes"
    folder.mkdir(parents=True)
    folder.chmod(0o500)
    try:
        await refused(tool, root, {"path": NOTE, "body": BODY}, IO_ERROR)
    finally:
        folder.chmod(0o700)


async def test_the_contract_is_checked_before_the_path(tool: WriteNoteTool, root: Path) -> None:
    with pytest.raises(NotAllowedError):
        await tool.execute(
            DECISION.model_copy(update={"outcome": PermissionOutcome.DENIED}),
            {"path": NOTE, "body": BODY},
        )
    assert snapshot(root) == set()


def test_declares_its_output_and_error_codes() -> None:
    assert WriteNoteTool.output_keys == {"path", "bytes"}
    assert WriteNoteTool.error_codes == {
        ARGUMENTS_INVALID,
        PATH_INVALID,
        PATH_SYMLINK,
        PATH_OUTSIDE_WORKSPACE,
        PATH_IS_DIRECTORY,
        IO_ERROR,
    }


@pytest.mark.parametrize("path", ["a.md", "workspace/notes/a.md", "deep/er/x", "a.b/c"])
def test_well_formed_relative_paths(path: str) -> None:
    assert is_relative_note_path(path)
