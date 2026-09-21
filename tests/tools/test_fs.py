"""``fs.read`` and ``fs.write``: the filesystem outside the workspace (M13.1).

What is asserted here and nowhere else: the root is never created; a path is refused with the
**same** code the verifier would give it (``tests/tools/test_paths.py`` proves the two agree);
and the fact that was approved — whether the call creates or overwrites — must still be true when
the write happens, **in both directions** (dec. Q).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ela.domain import (
    CapabilityId,
    DecisionId,
    ExecutionStatus,
    PermissionDecision,
    PermissionOutcome,
    RiskLevel,
)
from ela.testing.fakes import FakeClock, FakeIdGenerator
from ela.tools import (
    CREATES,
    FS_READ,
    FS_WRITE,
    OVERWRITE_MISMATCH,
    OVERWRITES,
    READS,
    EchoTool,
    FsReadTool,
    FsWriteTool,
)
from ela.tools.fs import IO_ERROR, NO_ROOT
from ela.tools.paths import (
    PATH_INVALID,
    PATH_IS_DIRECTORY,
    PATH_MISSING,
    PATH_OUTSIDE_ROOT,
    PATH_SYMLINK,
)
from tests.tools.support import PERMISSIONS_BITE

NOW = datetime(2026, 9, 21, 10, 0, tzinfo=UTC)
BODY = "Giovedì alle dieci.\n"


def decision(capability_id: CapabilityId) -> PermissionDecision:
    return PermissionDecision(
        id=DecisionId(FakeIdGenerator().new_uuid()),
        created_at=NOW,
        capability_id=capability_id,
        risk=RiskLevel.HIGH,
        outcome=PermissionOutcome.ALLOWED,
        reason="allowed for this test",
        expires_at=NOW.replace(hour=11),
    )


@pytest.fixture
def root(tmp_path: Path) -> Path:
    declared = tmp_path / "files"
    declared.mkdir()
    return declared


def writer(root: Path) -> FsWriteTool:
    return FsWriteTool(root, FakeClock(NOW), FakeIdGenerator())


def reader(root: Path) -> FsReadTool:
    return FsReadTool(root, FakeClock(NOW), FakeIdGenerator())


async def write(tool: FsWriteTool, **arguments: object) -> tuple[ExecutionStatus, str | None]:
    result = await tool.execute(decision(FS_WRITE), arguments)
    return result.status, None if result.error is None else result.error.code


async def read(tool: FsReadTool, **arguments: object) -> tuple[ExecutionStatus, str | None]:
    result = await tool.execute(decision(FS_READ), arguments)
    return result.status, None if result.error is None else result.error.code


# ----------------------------------------------------------------------------------------
# The root ELA never creates (dec. A)
# ----------------------------------------------------------------------------------------


def test_neither_tool_creates_the_root(tmp_path: Path) -> None:
    """``WriteNoteTool`` creates its workspace; these two never create the user's folder."""
    absent = tmp_path / "not-there"

    writer(absent)
    reader(absent)

    assert not absent.exists()


async def test_a_root_that_is_not_there_refuses_instead_of_making_one(tmp_path: Path) -> None:
    absent = tmp_path / "not-there"

    status, code = await write(writer(absent), path="a.md", body=BODY, overwrite=False)
    read_status, read_code = await read(reader(absent), path="a.md")

    assert (status, code) == (ExecutionStatus.FAILED, NO_ROOT)
    assert (read_status, read_code) == (ExecutionStatus.FAILED, NO_ROOT)
    assert not absent.exists(), "a tool that made the folder would have chosen it for the user"


# ----------------------------------------------------------------------------------------
# Writing, and the fact that was approved (dec. Q)
# ----------------------------------------------------------------------------------------


async def test_a_new_file_is_written_when_a_new_file_was_approved(root: Path) -> None:
    status, code = await write(writer(root), path="note.md", body=BODY, overwrite=False)

    assert (status, code) == (ExecutionStatus.SUCCEEDED, None)
    assert (root / "note.md").read_text(encoding="utf-8") == BODY
    assert (root / "note.md").stat().st_mode & 0o777 == 0o600


async def test_an_existing_file_is_overwritten_when_an_overwrite_was_approved(root: Path) -> None:
    (root / "note.md").write_text("vecchio", encoding="utf-8")

    status, code = await write(writer(root), path="note.md", body=BODY, overwrite=True)

    assert (status, code) == (ExecutionStatus.SUCCEEDED, None)
    assert (root / "note.md").read_text(encoding="utf-8") == BODY


async def test_a_file_that_appeared_after_the_yes_is_refused(root: Path) -> None:
    """Approved as a new file, and something is there now: the race that creates."""
    (root / "note.md").write_text("qualcosa che non c'era", encoding="utf-8")

    status, code = await write(writer(root), path="note.md", body=BODY, overwrite=False)

    assert (status, code) == (ExecutionStatus.FAILED, OVERWRITE_MISMATCH)
    assert (root / "note.md").read_text(encoding="utf-8") == "qualcosa che non c'era"


async def test_a_file_that_vanished_after_the_yes_is_refused(root: Path) -> None:
    """Approved as an overwrite, and nothing is there now: **the direction a race loses**.

    The half this milestone's first draft was missing, and the reason dec. Q exists: a criterion
    that names one direction is half a defence.
    """
    status, code = await write(writer(root), path="note.md", body=BODY, overwrite=True)

    assert (status, code) == (ExecutionStatus.FAILED, OVERWRITE_MISMATCH)
    assert not (root / "note.md").exists()


async def test_the_refusal_names_the_path_and_never_the_body(root: Path) -> None:
    (root / "note.md").write_text("x", encoding="utf-8")

    result = await writer(root).execute(
        decision(FS_WRITE), {"path": "note.md", "body": "SEGRETO", "overwrite": False}
    )

    assert result.error is not None
    assert "note.md" in result.error.message
    assert "SEGRETO" not in result.error.message


@pytest.mark.parametrize(
    "path, code",
    [
        ("../fuori.md", PATH_INVALID),
        ("a/../b.md", PATH_INVALID),
        ("/assoluto.md", PATH_INVALID),
        ("", PATH_INVALID),
    ],
)
async def test_a_path_of_the_wrong_shape_is_refused_before_the_disk(
    root: Path, path: str, code: str
) -> None:
    status, answered = await write(writer(root), path=path, body=BODY, overwrite=False)

    assert (status, answered) == (ExecutionStatus.FAILED, code)


async def test_a_link_out_of_the_root_is_named_as_out_of_the_root(
    root: Path, tmp_path: Path
) -> None:
    (tmp_path / "altrove").mkdir()
    (root / "via").symlink_to(tmp_path / "altrove")

    status, code = await write(writer(root), path="via/x.md", body=BODY, overwrite=False)

    assert (status, code) == (ExecutionStatus.FAILED, PATH_OUTSIDE_ROOT)


async def test_a_link_inside_the_root_is_still_a_link(root: Path) -> None:
    (root / "vera").mkdir()
    (root / "via").symlink_to(root / "vera")

    status, code = await write(writer(root), path="via/x.md", body=BODY, overwrite=False)

    assert (status, code) == (ExecutionStatus.FAILED, PATH_SYMLINK)


async def test_a_directory_is_not_a_file(root: Path) -> None:
    (root / "cartella").mkdir()

    status, code = await write(writer(root), path="cartella", body=BODY, overwrite=True)

    assert (status, code) == (ExecutionStatus.FAILED, PATH_IS_DIRECTORY)


@pytest.mark.parametrize(
    "arguments",
    [
        {"path": 7, "body": BODY, "overwrite": False},
        {"path": "a.md", "body": 7, "overwrite": False},
        {"path": "a.md", "body": BODY, "overwrite": "sì"},
    ],
    ids=["path", "body", "overwrite"],
)
async def test_arguments_of_the_wrong_type_are_refused(root: Path, arguments: dict) -> None:
    result = await writer(root).execute(decision(FS_WRITE), arguments)

    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None
    assert result.error.code == "arguments.invalid"


# ----------------------------------------------------------------------------------------
# Reading, and where the bytes go (dec. P)
# ----------------------------------------------------------------------------------------


async def test_the_content_is_in_the_result(root: Path) -> None:
    (root / "note.md").write_text(BODY, encoding="utf-8")

    result = await reader(root).execute(decision(FS_READ), {"path": "note.md"})

    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.output["content"] == BODY
    assert result.output["bytes"] == len(BODY.encode("utf-8"))
    assert result.output["path"] == "note.md"


async def test_a_file_that_is_not_there_is_a_refusal_for_a_reader(root: Path) -> None:
    status, code = await read(reader(root), path="assente.md")

    assert (status, code) == (ExecutionStatus.FAILED, PATH_MISSING)


async def test_bytes_that_are_not_text_are_refused_and_never_guessed(root: Path) -> None:
    (root / "immagine.bin").write_bytes(b"\xff\xfe\x00binario")

    result = await reader(root).execute(decision(FS_READ), {"path": "immagine.bin"})

    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None
    assert result.error.code == IO_ERROR
    assert "not UTF-8" in result.error.message


async def test_a_reader_refuses_a_path_of_the_wrong_shape(root: Path) -> None:
    status, code = await read(reader(root), path="../fuori.md")

    assert (status, code) == (ExecutionStatus.FAILED, PATH_INVALID)


async def test_a_reader_refuses_arguments_that_are_not_strings(root: Path) -> None:
    result = await reader(root).execute(decision(FS_READ), {"path": 7})

    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None
    assert result.error.code == "arguments.invalid"


async def test_a_reader_refuses_a_directory(root: Path) -> None:
    (root / "cartella").mkdir()

    status, code = await read(reader(root), path="cartella")

    assert (status, code) == (ExecutionStatus.FAILED, PATH_IS_DIRECTORY)


# ----------------------------------------------------------------------------------------
# What a question is told (dec. G)
# ----------------------------------------------------------------------------------------
# What a question is told, and what is refused before there is a question (dec. G, ADR 0045 §6-bis)
# ----------------------------------------------------------------------------------------


async def test_the_question_learns_the_resolved_path_and_what_a_yes_would_do(root: Path) -> None:
    (root / "c.md").write_text("x", encoding="utf-8")

    making = await writer(root).prospect({"path": "n.md", "body": BODY, "overwrite": False})
    replacing = await writer(root).prospect({"path": "c.md", "body": BODY, "overwrite": True})

    assert making.refusal is None and making.target is not None
    assert making.target.resolved == str(root / "n.md")
    assert making.target.does == CREATES
    assert replacing.target is not None and replacing.target.does == OVERWRITES


async def test_a_write_whose_assertion_the_disk_contradicts_is_refused_before_the_question(
    root: Path,
) -> None:
    """**The blocker the proof by hand found.** ELA asked to approve what it would refuse.

    The plan asserts «nothing is there» and something is. Before M13.1's repair the question was
    composed anyway — it even said «overwrites», read from the disk — the user said yes, and the
    tool refused because the *plan* said otherwise: two truths for one fact, and a user asked to
    approve what ELA already knew it would refuse (ADR 0011 §3).
    """
    (root / "c.md").write_text("qualcosa", encoding="utf-8")

    prospect = await writer(root).prospect({"path": "c.md", "body": BODY, "overwrite": False})

    assert prospect.target is None
    assert prospect.refusal is not None
    assert prospect.refusal.code == OVERWRITE_MISMATCH


async def test_a_read_of_a_file_that_is_not_there_is_refused_before_the_question(
    root: Path,
) -> None:
    """The same rule on a read: approving it would change nothing (ADR 0045 §6-bis)."""
    prospect = await reader(root).prospect({"path": "assente.md", "purpose": "x"})

    assert prospect.target is None
    assert prospect.refusal is not None
    assert prospect.refusal.code == PATH_MISSING


async def test_a_read_that_would_succeed_says_what_a_read_does(root: Path) -> None:
    """dec. G, blocker 2: the sentence belongs to the capability, and a read does not overwrite."""
    (root / "c.md").write_text("x", encoding="utf-8")

    prospect = await reader(root).prospect({"path": "c.md", "purpose": "x"})

    assert prospect.target is not None
    assert prospect.target.does == READS
    assert "overwrite" not in prospect.target.does


async def test_a_path_the_classification_refuses_has_no_target_and_a_refusal(root: Path) -> None:
    bad = {"path": "../fuori.md", "body": BODY, "overwrite": False}

    prospect = await writer(root).prospect(bad)

    assert prospect.target is None
    assert prospect.refusal is not None and prospect.refusal.code == PATH_INVALID


async def test_a_capability_that_touches_no_file_promises_and_refuses_nothing() -> None:
    """The default of :class:`~ela.tools.base.Tool`: silence is not a permission (dec. G)."""
    tool = EchoTool(FakeClock(NOW), FakeIdGenerator())

    prospect = await tool.prospect({"message": "ciao"})

    assert prospect.target is None and prospect.refusal is None


# ----------------------------------------------------------------------------------------
# The declared root, and the failures the disk itself produces
# ----------------------------------------------------------------------------------------


def test_both_tools_report_the_root_they_resolved(root: Path) -> None:
    assert writer(root).root == root.resolve()
    assert reader(root).root == root.resolve()


@pytest.mark.skipif(not PERMISSIONS_BITE, reason="chmod(0o000) does not deny this user: it is root")
async def test_a_file_the_os_will_not_open_for_reading_is_an_io_error(root: Path) -> None:
    target = root / "note.md"
    target.write_text(BODY, encoding="utf-8")
    target.chmod(0o000)
    try:
        status, code = await read(reader(root), path="note.md")
    finally:
        target.chmod(0o600)

    assert (status, code) == (ExecutionStatus.FAILED, IO_ERROR)


@pytest.mark.skipif(not PERMISSIONS_BITE, reason="chmod(0o000) does not deny this user: it is root")
async def test_a_directory_the_os_will_not_write_into_is_an_io_error(root: Path) -> None:
    (root / "chiusa").mkdir()
    (root / "chiusa").chmod(0o500)
    try:
        status, code = await write(writer(root), path="chiusa/note.md", body=BODY, overwrite=False)
    finally:
        (root / "chiusa").chmod(0o700)

    assert (status, code) == (ExecutionStatus.FAILED, IO_ERROR)


async def test_a_target_that_stops_being_a_regular_file_between_the_checks_is_not_read(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Defence in depth, exercised on purpose: the race the classification cannot see.

    ``classify`` says «a regular file is there», and by the time the descriptor is open it is a
    FIFO. In production the classification refuses a FIFO one step earlier, so this branch is only
    reachable by building the race — which is what makes it worth building.

    Writing this test is what found that ``os.open`` on a FIFO **blocks** until somebody opens the
    other end: the guard one line below could never run. ``READ_FLAGS`` carries ``O_NONBLOCK``
    because of it.
    """
    os.mkfifo(root / "tubo")
    monkeypatch.setattr("ela.tools.fs.classify", lambda *_: None)

    status, code = await read(reader(root), path="tubo")

    assert (status, code) == (ExecutionStatus.FAILED, IO_ERROR)
