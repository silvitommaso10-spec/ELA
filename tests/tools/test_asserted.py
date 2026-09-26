"""``asserted``: what a call says of a machine ELA has not looked at (M13.3, form D; ADR 0048).

Beside ``prospect``, which looks. For a step placed on a node whose verifier reads the machine the
Core's disk is the wrong one, so the question names what the plan asserts — the path as written, and
for a write whether it creates or overwrites — in the tool's own words; the node's tool, which is
this code, compares that with its disk before acting. Only what needs no disk refuses here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ela.ports import Target
from ela.testing.fakes import FakeClock, FakeIdGenerator
from ela.tools import (
    ARGUMENTS_INVALID,
    ASSERTED_CREATES,
    ASSERTED_OVERWRITES,
    ASSERTED_READS,
    PATH_INVALID,
    EchoTool,
    FsReadTool,
    FsWriteTool,
)


@pytest.fixture
def nowhere(tmp_path: Path) -> Path:
    """A root that does not exist: ``asserted`` must not need one, since it looks at nothing."""
    return tmp_path / "not-there"


@pytest.mark.parametrize(
    ("overwrite", "does"), [(False, ASSERTED_CREATES), (True, ASSERTED_OVERWRITES)]
)
async def test_a_write_asserts_the_plan_s_overwrite_in_the_tool_s_words(
    nowhere: Path, overwrite: bool, does: str
) -> None:
    tool = FsWriteTool(nowhere, FakeClock(), FakeIdGenerator())

    asserted = await tool.asserted({"path": "ELA/prova.md", "body": "x", "overwrite": overwrite})

    assert asserted.refusal is None
    assert asserted.target == Target(
        resolved="ELA/prova.md", exists=overwrite, does=does, label="file"
    )


async def test_a_read_asserts_the_file_is_there(nowhere: Path) -> None:
    asserted = await FsReadTool(nowhere, FakeClock(), FakeIdGenerator()).asserted(
        {"path": "ELA/prova.md"}
    )

    assert asserted.target == Target(
        resolved="ELA/prova.md", exists=True, does=ASSERTED_READS, label="file"
    )


@pytest.mark.parametrize("path", ["../fuori.md", "nota.md:x", "CON.md", "prova.md."])
async def test_the_grammar_refuses_before_the_question_on_every_machine(
    nowhere: Path, path: str
) -> None:
    for asked in (
        await FsReadTool(nowhere, FakeClock(), FakeIdGenerator()).asserted({"path": path}),
        await FsWriteTool(nowhere, FakeClock(), FakeIdGenerator()).asserted(
            {"path": path, "body": "x", "overwrite": False}
        ),
    ):
        assert asked.target is None
        assert asked.refusal is not None and asked.refusal.code == PATH_INVALID


@pytest.mark.parametrize(
    "arguments",
    [{"path": 3, "body": "x", "overwrite": False}, {"path": "a.md", "body": "x", "overwrite": 1}],
)
async def test_arguments_of_the_wrong_shape_are_refused_without_a_disk(
    nowhere: Path, arguments: dict[str, object]
) -> None:
    asked = await FsWriteTool(nowhere, FakeClock(), FakeIdGenerator()).asserted(arguments)

    assert asked.refusal is not None and asked.refusal.code == ARGUMENTS_INVALID
    read = await FsReadTool(nowhere, FakeClock(), FakeIdGenerator()).asserted({"path": 3})
    assert read.refusal is not None and read.refusal.code == ARGUMENTS_INVALID


async def test_a_tool_that_works_on_no_path_asserts_nothing() -> None:
    asked = await EchoTool(FakeClock(), FakeIdGenerator()).asserted({"message": "ciao"})

    assert (asked.target, asked.refusal, asked.invocation) == (None, None, None)
