"""``ToolRegistry``, ``VerifierRegistry``, ``tools_v01`` and ``verifiers_v01`` beyond the
contract (ADR 0013 §10, ADR 0014 §2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ela.domain import CapabilityId
from ela.permissions import MODEL_COMPLETE, catalogue_v01
from ela.ports import AlreadyExistsError
from ela.testing.fakes import FakeClock, FakeIdGenerator, FakeTool
from ela.tools import (
    CORE_ECHO,
    EchoTool,
    EchoVerifier,
    NotIdempotentError,
    Tool,
    ToolNotFound,
    ToolRegistry,
    VerifierNotFound,
    VerifierRegistry,
    WriteNoteTool,
    WriteNoteVerifier,
    tools_v01,
    verifiers_v01,
)


def test_get_unknown_names_the_capability() -> None:
    registry = ToolRegistry(())
    with pytest.raises(ToolNotFound) as caught:
        registry.get(CapabilityId("nobody.knows_this"))
    assert caught.value.capability_id == "nobody.knows_this"
    assert "tool 'nobody.knows_this' not found" in str(caught.value)


def test_tools_v01_implements_a_subset_of_the_catalogue_without_model_complete(
    tmp_path: Path,
) -> None:
    registry = tools_v01(root=tmp_path, clock=FakeClock(), ids=FakeIdGenerator())
    implemented = {tool.capability_id for tool in registry.tools()}
    declared = {spec.id for spec in catalogue_v01().specs()}
    assert implemented < declared
    assert declared - implemented == {MODEL_COMPLETE}
    with pytest.raises(ToolNotFound):
        registry.get(MODEL_COMPLETE)
    echo, notes = registry.tools()
    assert isinstance(echo, EchoTool)
    assert isinstance(notes, WriteNoteTool)
    assert notes.root == tmp_path.resolve()


def test_the_registry_is_frozen() -> None:
    registry = ToolRegistry(())
    assert not hasattr(registry, "__dict__")
    with pytest.raises(AttributeError):
        registry.extra = 1  # type: ignore[attr-defined]


def test_verifier_get_unknown_names_the_capability() -> None:
    registry = VerifierRegistry(())
    with pytest.raises(VerifierNotFound) as caught:
        registry.get(CapabilityId("nobody.knows_this"))
    assert caught.value.capability_id == "nobody.knows_this"
    assert "verifier 'nobody.knows_this' not found" in str(caught.value)


def test_verifiers_v01_covers_exactly_the_tools_of_v01(tmp_path: Path) -> None:
    """Every tool has its verifier and no verifier lacks a tool: a capability without both is
    not executable (ADR 0014 §3)."""
    tools = tools_v01(root=tmp_path, clock=FakeClock(), ids=FakeIdGenerator())
    verifiers = verifiers_v01(root=tmp_path)
    assert {v.capability_id for v in verifiers.verifiers()} == {
        t.capability_id for t in tools.tools()
    }
    with pytest.raises(VerifierNotFound):
        verifiers.get(MODEL_COMPLETE)
    echo, notes = verifiers.verifiers()
    assert isinstance(echo, EchoVerifier)
    assert isinstance(notes, WriteNoteVerifier)
    assert notes._root == tmp_path.resolve()  # noqa: SLF001


def test_the_verifier_registry_is_frozen() -> None:
    registry = VerifierRegistry(())
    assert not hasattr(registry, "__dict__")
    with pytest.raises(AttributeError):
        registry.extra = 1  # type: ignore[attr-defined]


# --------------------------------------------------------------------------------------
# Only idempotent tools are registered (review of M5.3, ADR 0015 §8)
# --------------------------------------------------------------------------------------


def test_the_tools_of_v01_promise_that_twice_is_once(tmp_path: Path) -> None:
    """Crash window 7a is repaired by running the tool again: every registered tool says so."""
    registry = tools_v01(root=tmp_path, clock=FakeClock(), ids=FakeIdGenerator())
    assert [tool.idempotent for tool in registry.tools()] == [True, True]  # type: ignore[attr-defined]
    assert EchoTool.idempotent is WriteNoteTool.idempotent is True


def test_a_tool_that_is_not_idempotent_is_refused_and_named() -> None:
    """Negative case: the first non-idempotent tool cannot enter without the STARTED protocol."""
    tool = FakeTool(
        CapabilityId("model.complete"), FakeClock(), FakeIdGenerator(), name="x", idempotent=False
    )
    with pytest.raises(NotIdempotentError) as caught:
        ToolRegistry((tool,))
    assert caught.value.capability_id == CapabilityId("model.complete")
    assert caught.value.name == "x"
    assert caught.value.declared is False
    assert "idempotent=False" in str(caught.value)
    assert "STARTED protocol of ADR 0015 §8" in str(caught.value)
    assert "7a" in str(caught.value)


def test_a_tool_that_does_not_declare_it_is_refused_too() -> None:
    """A doubt is not a yes (§33): forgetting the attribute reads as "no", never as "yes"."""

    class _Undeclared:
        capability_id = CapabilityId("core.echo")
        name = "undeclared"

        async def execute(self, decision: object, arguments: object) -> object:  # pragma: no cover
            raise AssertionError("never registered, never called")

    with pytest.raises(NotIdempotentError) as caught:
        ToolRegistry((_Undeclared(),))  # type: ignore[arg-type]
    assert caught.value.declared is None
    assert "declares no idempotent" in str(caught.value)
    assert not hasattr(Tool, "idempotent")  # the base gives no default to inherit by mistake


def test_the_refusal_comes_before_the_duplicate_check() -> None:
    """A non-idempotent duplicate is refused for what makes it dangerous, not for its key."""
    echo = EchoTool(FakeClock(), FakeIdGenerator())
    liar = FakeTool(CORE_ECHO, FakeClock(), FakeIdGenerator(), name="liar", idempotent=False)
    with pytest.raises(NotIdempotentError):
        ToolRegistry((echo, liar))
    with pytest.raises(AlreadyExistsError):
        ToolRegistry((echo, EchoTool(FakeClock(), FakeIdGenerator())))
