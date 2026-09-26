"""``relocatable``: whether a node's claimed work may move to another machine (M13.3, form E).

Declared by every tool, with no default — the form of ``idempotent`` and ``audit_numbers`` —, and
**not another name for idempotent**: ``fs.read`` is repeatable on its machine, and on another one
the same path is another file. The registry refuses silence, and ``True`` beside an ``idempotent``
``False``: what cannot be done again here is not done again elsewhere. Neither refusal has a
producer in production; each holds by its negative case, built here with a fake (form E).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ela.permissions import CORE_ECHO
from ela.testing.fakes import FakeClock, FakeIdGenerator, FakeTool
from ela.tools import (
    ECHO_TOOL_NAME,
    FS_READ_TOOL_NAME,
    EchoTool,
    RelocationError,
    Tool,
    ToolRegistry,
)
from tests.tools.test_registry import _production


def test_no_tool_inherits_an_answer() -> None:
    assert not hasattr(Tool, "relocatable"), "the base gives no default to inherit by mistake"
    assert EchoTool.relocatable is True


def test_only_the_echo_moves_and_fs_read_is_what_makes_it_a_declaration(tmp_path: Path) -> None:
    """The values of form E: ``core.echo`` yes, every other tool no — and ``fs.read`` is the tool
    whose ``idempotent`` and ``relocatable`` differ."""
    tools, _, _ = _production(tmp_path)

    moves = {tool.name for tool in tools.tools() if tool.relocatable}
    apart = {tool.name for tool in tools.tools() if tool.idempotent and not tool.relocatable}

    assert moves == {ECHO_TOOL_NAME}
    assert FS_READ_TOOL_NAME in apart


def test_a_tool_that_says_nothing_is_refused() -> None:
    class _Silent:
        capability_id = CORE_ECHO
        name = "silent"
        idempotent = True
        audit_numbers: frozenset[str] = frozenset()

    with pytest.raises(RelocationError) as caught:
        ToolRegistry((_Silent(),))  # type: ignore[arg-type]

    assert "relocatable" in str(caught.value)


def test_a_non_boolean_answer_is_refused_like_silence() -> None:
    tool = FakeTool(CORE_ECHO, FakeClock(), FakeIdGenerator())
    tool._relocatable = "yes"  # type: ignore[assignment]

    with pytest.raises(RelocationError):
        ToolRegistry((tool,))


def test_what_cannot_be_repeated_here_cannot_move_elsewhere() -> None:
    tool = FakeTool(CORE_ECHO, FakeClock(), FakeIdGenerator(), idempotent=False, relocatable=True)

    with pytest.raises(RelocationError) as caught:
        ToolRegistry((tool,))

    assert "relocatable True and idempotent False" in str(caught.value)


@pytest.mark.parametrize(
    ("idempotent", "relocatable"), [(True, True), (True, False), (False, False)]
)
def test_the_three_legal_pairs_are_accepted(idempotent: bool, relocatable: bool) -> None:
    tool = FakeTool(
        CORE_ECHO, FakeClock(), FakeIdGenerator(), idempotent=idempotent, relocatable=relocatable
    )

    assert ToolRegistry((tool,)).get(CORE_ECHO).relocatable is relocatable


def test_the_fake_follows_idempotent_unless_a_test_sets_it() -> None:
    """The one predicate the claim read before M13.3: a test that turns ``idempotent`` off after
    building its world keeps meaning what it meant."""
    tool = FakeTool(CORE_ECHO, FakeClock(), FakeIdGenerator())
    assert tool.relocatable is True
    tool.idempotent = False
    assert tool.relocatable is False
    tool.idempotent = True
    tool.relocatable = False
    assert tool.relocatable is False
