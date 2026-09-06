"""``ToolRegistry`` and ``tools_v01`` beyond the contract (ADR 0013 §10)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ela.domain import CapabilityId
from ela.permissions import MODEL_COMPLETE, catalogue_v01
from ela.testing.fakes import FakeClock, FakeIdGenerator
from ela.tools import EchoTool, ToolNotFound, ToolRegistry, WriteNoteTool, tools_v01


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
