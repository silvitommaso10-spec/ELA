"""Contract of ``ToolRegistryPort`` (spec §28; ADR 0013 §10): one tool per capability, read-only.

Every implementation is built by ``implementations.py`` with the same two tools
(``REGISTRY_TOOLS``): the contract reads them back by their own ``capability_id`` and checks
that nothing can be added afterwards — the port has ``get`` and ``tools`` and an implementation
may have no public member beyond them.
"""

from __future__ import annotations

import pytest

from ela.domain import CapabilityId
from ela.ports import AlreadyExistsError, NotFoundError, ToolRegistryPort
from ela.testing.fakes import FakeClock, FakeIdGenerator, FakeTool, FakeToolRegistry
from ela.tools import ToolRegistry
from tests.contracts.implementations import REGISTRY_TOOLS
from tests.contracts.protocols import members

NOTE_TOOL, ECHO_TOOL = REGISTRY_TOOLS


def test_get_returns_the_tool_keyed_by_its_own_capability(tool_registry: ToolRegistryPort) -> None:
    assert tool_registry.get(NOTE_TOOL.capability_id) is NOTE_TOOL
    assert tool_registry.get(ECHO_TOOL.capability_id) is ECHO_TOOL


def test_get_unknown_is_not_found(tool_registry: ToolRegistryPort) -> None:
    with pytest.raises(NotFoundError):
        tool_registry.get(CapabilityId("nobody.knows_this"))


def test_tools_in_construction_order_as_a_tuple(tool_registry: ToolRegistryPort) -> None:
    tools = tool_registry.tools()
    assert isinstance(tools, tuple)
    assert tools == REGISTRY_TOOLS


def test_no_public_member_beyond_the_port(tool_registry: ToolRegistryPort) -> None:
    public = {name for name in dir(tool_registry) if not name.startswith("_")}
    assert public == set(members(ToolRegistryPort)) == {"get", "tools"}


@pytest.mark.parametrize("registry", [FakeToolRegistry, ToolRegistry], ids=lambda c: c.__name__)
def test_two_tools_for_one_capability_are_refused(registry: type) -> None:
    twin = FakeTool(NOTE_TOOL.capability_id, FakeClock(), FakeIdGenerator(), name="twin")
    with pytest.raises(AlreadyExistsError):
        registry((NOTE_TOOL, twin))
