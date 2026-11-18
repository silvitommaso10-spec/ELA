"""A read says how large it is, and has a ceiling (M13.17, ADR 0074; decision 11 of its starting
block, answers 46 and 49 of the review of its SPEC; E2 and E4 of its SPEC).

- **The question names the size** of the file as the disk says it when the question is composed:
  the tool's target carries it, and the executor puts it among what the question names, for the
  three surfaces that answer.
- **A file over 8 MiB is refused before the question**, with ``fs.too_large`` and the two sizes,
  never a hash.
- **A file that grew after the look** is the same refusal at the read: at most the ceiling and one
  byte are read.
- **The verifier of a read rereads at most the ceiling.**
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from ela.domain import (
    CapabilityId,
    DecisionId,
    ExecutionId,
    ExecutionResult,
    ExecutionStatus,
    PermissionDecision,
    PermissionOutcome,
    RiskLevel,
)
from ela.executive import ASKED
from ela.ports import Prospect, Target
from ela.testing.fakes import FakeClock, FakeIdGenerator, FakeStop
from ela.tools import fs as fs_module
from ela.tools.fs import FS_READ, FS_READ_MAX_BYTES, TOO_LARGE, FsReadTool
from ela.tools.verifiers import FS_CONTENT_MATCHES, FsReadVerifier
from tests.executive.test_policy_high import high_world
from tests.permissions.catalogue_calls import CATALOGUE

NOW = datetime(2026, 11, 18, 10, 0, tzinfo=UTC)


def decision() -> PermissionDecision:
    return PermissionDecision(
        id=DecisionId(FakeIdGenerator().new_uuid()),
        created_at=NOW,
        capability_id=FS_READ,
        risk=RiskLevel.MEDIUM,
        outcome=PermissionOutcome.ALLOWED,
        reason="allowed for this test",
        expires_at=NOW.replace(hour=11),
    )


@pytest.fixture
def root(tmp_path: Path) -> Path:
    declared = tmp_path / "files"
    (declared / "ELA").mkdir(parents=True)
    return declared


def reader(root: Path) -> FsReadTool:
    return FsReadTool(root, FakeClock(NOW), FakeIdGenerator(), protected={})


def test_the_ceiling_is_eight_mebibytes() -> None:
    """E2 passed up to 32 MiB; E4 — the peak at most twice the rest — up to 8: the largest that
    passes both."""
    assert FS_READ_MAX_BYTES == 8 * 1024 * 1024


async def test_the_question_of_a_read_names_the_size_of_the_file(root: Path) -> None:
    (root / "ELA" / "nota.md").write_text("ventidue byte di testo", encoding="utf-8")

    seen = await reader(root).prospect({"path": "ELA/nota.md", "purpose": "la prova"})

    assert seen.refusal is None and seen.target is not None
    assert seen.target.size == len(b"ventidue byte di testo")


async def test_a_file_over_the_ceiling_is_refused_before_the_question(root: Path) -> None:
    with (root / "ELA" / "grande.bin").open("wb") as big:
        big.truncate(FS_READ_MAX_BYTES + 1)

    seen = await reader(root).prospect({"path": "ELA/grande.bin", "purpose": "la prova"})

    assert seen.refusal is not None and seen.refusal.code == TOO_LARGE
    assert str(FS_READ_MAX_BYTES + 1) in seen.refusal.message
    assert str(FS_READ_MAX_BYTES) in seen.refusal.message
    assert "no question is asked" in seen.refusal.message


async def test_a_file_at_the_ceiling_is_read(root: Path) -> None:
    (root / "ELA" / "giusto.txt").write_bytes(b"a" * FS_READ_MAX_BYTES)

    result = await reader(root).execute(
        decision(), {"path": "ELA/giusto.txt", "purpose": "p"}, FakeStop()
    )

    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.output["bytes"] == FS_READ_MAX_BYTES


async def test_a_file_that_grew_after_the_look_is_refused_at_the_read(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The disk says a small file at the look — injected —, and holds a large one at the read."""
    (root / "ELA" / "cresce.txt").write_bytes(b"a" * (FS_READ_MAX_BYTES + 10))
    real = os.lstat

    class Small:
        def __init__(self, held: os.stat_result) -> None:
            self.st_size = 10
            self.st_nlink = held.st_nlink
            self.st_mode = held.st_mode

    def small(path: Any, *args: Any, **kwargs: Any) -> Any:
        return Small(real(path, *args, **kwargs))

    monkeypatch.setattr(fs_module, "os", _WithLstat(small))

    result = await reader(root).execute(
        decision(), {"path": "ELA/cresce.txt", "purpose": "p"}, FakeStop()
    )

    assert result.error is not None and result.error.code == TOO_LARGE
    assert "grew past" in result.error.message
    assert str(FS_READ_MAX_BYTES + 1) in result.error.message, "one byte past the ceiling, no more"


async def test_the_verifier_of_a_read_rereads_at_most_the_ceiling(root: Path) -> None:
    (root / "ELA" / "grande.txt").write_bytes(b"a" * (FS_READ_MAX_BYTES + 100))
    result = ExecutionResult(
        id=ExecutionId(FakeIdGenerator().new_uuid()),
        created_at=NOW,
        capability_id=FS_READ,
        status=ExecutionStatus.SUCCEEDED,
        output={"path": "ELA/grande.txt", "bytes": 1, "content": "a"},
    )

    (failure,) = await FsReadVerifier(root, protected={}).verify(
        (FS_CONTENT_MATCHES,), {"path": "ELA/grande.txt"}, result
    )

    assert failure.details["actual_bytes"] == FS_READ_MAX_BYTES + 1


async def test_the_executor_puts_the_size_of_a_read_among_what_the_question_names() -> None:
    """The three surfaces that answer show a size when the question carries one (the closed world
    of ``tests/api/test_answering_surfaces.py``); here, that a read's question carries it."""
    capability = CapabilityId("fs.read")
    w = high_world(CATALOGUE.get(capability))
    task, step = await w.running(
        capability, arguments={"path": "ELA/nota.md", "purpose": "p"}, requires_authorization=True
    )
    w.tool(capability).prospects = Prospect(
        target=Target(resolved="/x/ELA/nota.md", exists=True, does="reads", label="file", size=22)
    )

    execution = await w.execute(task.id, step.id)

    assert execution.approval is not None
    assert execution.approval.metadata[ASKED]["size"] == 22


class _WithLstat:
    """``os`` as ``fs`` reads it, with an ``lstat`` of the test's."""

    def __init__(self, lstat: Any) -> None:
        self.lstat = lstat

    def __getattr__(self, name: str) -> Any:
        return getattr(os, name)
