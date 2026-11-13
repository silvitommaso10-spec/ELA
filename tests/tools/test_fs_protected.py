"""What no write reaches, a file with two names, and a place a policy would name (M13.14, ADR 0068).

Three answers of ``fs.write`` that M13.14 adds, each red before its code (decision 9, answers 25 and
31 of the review of the SPEC):

- **what ELA uses to exist** — the list the composition derives, the one the root is checked
  against at the start-up — is refused at every write, ``path.ela_s_own``, under a yes or under a
  policy, before the question and before the write;
- **a file with more than one name** is not overwritten, ``path.hard_link``: the places are
  compared as paths, and a second name of a file of ELA's would step around the comparison;
- :meth:`FsWriteTool.prospect_place` says whether a write could start in a folder a policy would
  name: there, a folder, inside the root without a link, and nothing of ELA's — and when it could,
  the folder as this disk names it, for the preview.

The list is injected: a test never names a place of the machine it runs on.
"""

from __future__ import annotations

import os
import sys
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
from ela.testing.fakes import FakeClock, FakeIdGenerator, FakeStop
from ela.tools import FS_WRITE, FsWriteTool
from ela.tools import paths as paths_module
from ela.tools.fs import (
    ELA_S_OWN,
    FOLDER,
    HARD_LINK,
    IO_ERROR,
    NO_ROOT,
    NOT_A_FOLDER,
    WRITE_REFUSALS,
    WRITES_IN,
    looked_for_a_write,
)
from ela.tools.paths import (
    PATH_INVALID,
    PATH_MISSING,
    PATH_OUTSIDE_ROOT,
    PATH_SYMLINK,
    PATH_UNREACHABLE,
)

NOW = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)
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
    (declared / "ELA").mkdir(parents=True)
    return declared


def writer(root: Path, **protected: Path) -> FsWriteTool:
    return FsWriteTool(
        root,
        FakeClock(NOW),
        FakeIdGenerator(),
        protected={what.replace("_", " "): place for what, place in protected.items()},
    )


async def write(tool: FsWriteTool, **arguments: object) -> tuple[ExecutionStatus, str | None]:
    result = await tool.execute(decision(FS_WRITE), arguments, FakeStop())
    return result.status, None if result.error is None else result.error.code


# ----------------------------------------------------------------------------------------
# What ELA uses to exist: never written (decision 9)
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "place", "overwrite"),
    [
        ("ELA/casa/nota.md", "ELA/casa", False),
        ("ELA/casa", "ELA/casa", False),
        ("ELA/nuovo", "ELA/nuovo/dentro", False),
    ],
    ids=["lies-within", "is", "holds"],
)
async def test_a_write_that_reaches_what_ela_uses_to_exist_is_refused_and_writes_nothing(
    root: Path, path: str, place: str, overwrite: bool
) -> None:
    """Is, holds or lies within: the three ways of «contain one another» of the start-up, here at
    every write — before the question and before the write, with the place named and the body
    never."""
    tool = writer(root, the_database=root / place)
    arguments = {"path": path, "body": BODY, "overwrite": overwrite}

    asked = await tool.prospect(arguments)
    status, code = await write(tool, **arguments)

    assert asked.refusal is not None and asked.refusal.code == ELA_S_OWN
    assert "the database" in asked.refusal.message and BODY not in asked.refusal.message
    assert (status, code) == (ExecutionStatus.FAILED, ELA_S_OWN)
    assert not (root / path).exists()


async def test_a_write_beside_what_ela_uses_to_exist_is_written(root: Path) -> None:
    """The positive case: the list refuses what it names, and nothing next to it."""
    tool = writer(root, the_database=root / "ELA" / "casa")

    assert await write(tool, path="ELA/nota.md", body=BODY, overwrite=False) == (
        ExecutionStatus.SUCCEEDED,
        None,
    )


async def test_a_place_spelt_another_way_is_where_the_volume_says_it_is(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The comparison of the start-up (``within``), with the volume's answer handed by the test:
    on a Mac a place typed with other capitals is the same folder, and a comparison of spellings
    alone would let the write through."""
    (root / "ELA" / "Casa").mkdir()
    monkeypatch.setattr(
        paths_module, "same_folder", lambda one, other: str(one).casefold() == str(other).casefold()
    )
    tool = writer(root, ELA_s_home=root / "ELA" / "casa")

    assert await write(tool, path="ELA/Casa/nota.md", body=BODY, overwrite=False) == (
        ExecutionStatus.FAILED,
        ELA_S_OWN,
    )


def test_the_list_is_required_and_kept_as_it_was_given(root: Path) -> None:
    """No default: a tool built without the list would write anywhere under the root. And a copy
    that does not move when the caller's mapping does."""
    given = {"the database": root / "db"}
    tool = FsWriteTool(root, FakeClock(NOW), FakeIdGenerator(), protected=given)
    given["the .env ELA read"] = root / ".env"

    assert dict(tool.protected) == {"the database": root / "db"}
    with pytest.raises(TypeError):
        FsWriteTool(root, FakeClock(NOW), FakeIdGenerator())  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        looked_for_a_write(root, "ELA/a.md", False)  # type: ignore[call-arg]


# ----------------------------------------------------------------------------------------
# A file with more than one name: never overwritten (answer 31)
# ----------------------------------------------------------------------------------------


async def test_a_file_with_two_names_is_not_overwritten_and_neither_name_changes(
    root: Path,
) -> None:
    """The second name may be anywhere on the volume — the test keeps it beside the first —, and
    the comparison of the places, which reads paths, cannot see it."""
    first = root / "ELA" / "uno.md"
    first.write_bytes(b"prima")
    os.link(first, root / "ELA" / "due.md")
    tool = writer(root)
    arguments = {"path": "ELA/uno.md", "body": BODY, "overwrite": True}

    asked = await tool.prospect(arguments)
    status, code = await write(tool, **arguments)

    assert asked.refusal is not None and asked.refusal.code == HARD_LINK
    assert "more than one name" in asked.refusal.message and BODY not in asked.refusal.message
    assert (status, code) == (ExecutionStatus.FAILED, HARD_LINK)
    assert first.read_bytes() == (root / "ELA" / "due.md").read_bytes() == b"prima"


async def test_a_file_with_one_name_is_overwritten_and_a_new_file_has_one(root: Path) -> None:
    (root / "ELA" / "uno.md").write_bytes(b"prima")
    tool = writer(root)

    assert await write(tool, path="ELA/uno.md", body=BODY, overwrite=True) == (
        ExecutionStatus.SUCCEEDED,
        None,
    )
    assert await write(tool, path="ELA/nuovo.md", body=BODY, overwrite=False) == (
        ExecutionStatus.SUCCEEDED,
        None,
    )


def test_a_file_that_cannot_be_looked_at_again_is_an_io_error_and_never_a_write(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Between the classification and the count of the names the file stops answering: a refusal,
    never a write on a file nobody counted (§33)."""
    (root / "ELA" / "uno.md").write_bytes(b"prima")
    real = os.lstat

    def vanishing(path: object, *args: object, **kwargs: object) -> os.stat_result:
        # Only the count of the names fails: the classification, one frame away, still sees it.
        if sys._getframe(1).f_code.co_name == looked_for_a_write.__name__:
            raise FileNotFoundError(2, "No such file or directory")
        return real(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "lstat", vanishing)

    refused, _ = looked_for_a_write(root, "ELA/uno.md", True, protected={})

    assert refused is not None and refused.code == IO_ERROR
    assert "FileNotFoundError" in (refused.message or "")


def test_the_two_codes_are_named_by_every_write() -> None:
    """``fs.write`` and a download share :data:`WRITE_REFUSALS`, and the tool declares both."""
    assert {ELA_S_OWN, HARD_LINK} <= WRITE_REFUSALS
    assert {ELA_S_OWN, HARD_LINK} <= FsWriteTool.error_codes


# ----------------------------------------------------------------------------------------
# A place a policy would name (proposal 7, answer 25)
# ----------------------------------------------------------------------------------------


async def test_a_folder_that_is_there_could_hold_a_write_and_is_named_as_this_disk_names_it(
    root: Path,
) -> None:
    (root / "ELA" / "prova").mkdir()

    looked = await writer(root).prospect_place("ELA/prova")

    assert looked.refusal is None
    assert looked.target is not None
    assert looked.target.resolved == str(root.resolve() / "ELA" / "prova")
    assert (looked.target.exists, looked.target.does, looked.target.label) == (
        True,
        WRITES_IN,
        FOLDER,
    )


@pytest.mark.parametrize(
    ("place", "code"),
    [
        ("../fuori", PATH_INVALID),
        ("ELA/fuori", PATH_OUTSIDE_ROOT),
        ("ELA/dentro", PATH_SYMLINK),
        ("ELA/mai", PATH_MISSING),
        ("ELA/nota.md", NOT_A_FOLDER),
        ("ELA/nota.md/sotto", PATH_UNREACHABLE),
        ("ELA/casa", ELA_S_OWN),
    ],
)
async def test_a_place_no_write_could_start_in_is_refused_with_its_code(
    root: Path, tmp_path: Path, place: str, code: str
) -> None:
    """A link — out of the root or inside it —, a folder that is not there, a file, a path the
    grammar refuses, and a place of ELA's own: each with the code the tool answers with."""
    (tmp_path / "elsewhere").mkdir()
    (root / "ELA" / "fuori").symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    (root / "ELA" / "vera").mkdir()
    (root / "ELA" / "dentro").symlink_to(root / "ELA" / "vera", target_is_directory=True)
    (root / "ELA" / "nota.md").write_text("c'era", encoding="utf-8")
    (root / "ELA" / "casa").mkdir()

    looked = await writer(root, the_database=root / "ELA" / "casa").prospect_place(place)

    assert looked.target is None
    assert looked.refusal is not None and looked.refusal.code == code
    assert looked.refusal.tool_name == "fs-write"
    assert not (root / "ELA" / "mai").exists()


async def test_a_root_that_is_not_there_has_no_place(tmp_path: Path) -> None:
    looked = await writer(tmp_path / "nowhere").prospect_place("ELA")

    assert looked.refusal is not None and looked.refusal.code == NO_ROOT
    assert not (tmp_path / "nowhere").exists()
