"""The registry of tools (spec §28; ADR 0013 §10): one tool per capability, fixed at construction.

:class:`ToolRegistry` implements :class:`~ela.ports.ToolRegistryPort`. Like the capability
catalogue (ADR 0010 §1) it has no way to change after it is built: what ELA can *execute* is
decided when the registry is, and a tool registered under a capability is keyed by its own
``capability_id`` — there is no argument through which a tool could claim another one.
:func:`tools_v01` builds the tools of this milestone, the mirror of ``catalogue_v01``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from types import MappingProxyType

from ela.domain import CapabilityId
from ela.ports import AlreadyExistsError, Clock, IdGenerator, ToolPort
from ela.tools.echo import EchoTool
from ela.tools.errors import ToolNotFound
from ela.tools.notes import WriteNoteTool

__all__ = ["ToolRegistry", "tools_v01"]


class ToolRegistry:
    """Tools by capability id, frozen at construction (port ``ToolRegistryPort``)."""

    __slots__ = ("_tools",)

    def __init__(self, tools: Iterable[ToolPort]) -> None:
        table: dict[CapabilityId, ToolPort] = {}
        for tool in tools:
            if tool.capability_id in table:
                raise AlreadyExistsError("tool", tool.capability_id)
            table[tool.capability_id] = tool
        self._tools: Mapping[CapabilityId, ToolPort] = MappingProxyType(table)

    def get(self, capability_id: CapabilityId) -> ToolPort:
        """The tool for this capability; :class:`ToolNotFound` if there is none."""
        try:
            return self._tools[capability_id]
        except KeyError:
            raise ToolNotFound(capability_id) from None

    def tools(self) -> tuple[ToolPort, ...]:
        """Every tool, in construction order."""
        return tuple(self._tools.values())


def tools_v01(*, root: Path | str, clock: Clock, ids: IdGenerator) -> ToolRegistry:
    """The tools of v0.1 that run without a provider: ``core.echo`` and ``workspace.write_note``.

    ``model.complete`` has no tool yet (M7.2): the executor refuses it before any decision.
    """
    return ToolRegistry((EchoTool(clock, ids), WriteNoteTool(root, clock, ids)))
