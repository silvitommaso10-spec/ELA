"""The registries of tools and verifiers (spec §28, §63; ADR 0013 §10, ADR 0014 §2).

:class:`ToolRegistry` implements :class:`~ela.ports.ToolRegistryPort` and
:class:`VerifierRegistry` implements :class:`~ela.ports.VerifierRegistryPort`: one entry per
capability, fixed at construction. Like the capability catalogue (ADR 0010 §1) neither has a
way to change after it is built: what ELA can *execute* and what it can *verify* are decided
when the registries are, and every entry is keyed by its own ``capability_id`` — there is no
argument through which a tool or a verifier could claim another capability.
:func:`tools_v01` and :func:`verifiers_v01` build the pairs of this version, mirrors of
``catalogue_v01``: every tool has its verifier, and a capability without both is not executable.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from types import MappingProxyType

from ela.domain import CapabilityId
from ela.ports import AlreadyExistsError, Clock, IdGenerator, ToolPort, VerifierPort
from ela.tools.echo import EchoTool
from ela.tools.errors import NotIdempotentError, ToolNotFound, VerifierNotFound
from ela.tools.notes import WriteNoteTool
from ela.tools.verifiers import EchoVerifier, WriteNoteVerifier

__all__ = ["ToolRegistry", "VerifierRegistry", "tools_v01", "verifiers_v01"]


class ToolRegistry:
    """Tools by capability id, frozen at construction (port ``ToolRegistryPort``).

    **Only idempotent tools are registered** (review of M5.3): crash window 7a is repaired by
    running the tool again, and that is safe only while every tool that can be executed promises
    that twice is once. A tool that declares ``idempotent = False``, or that does not declare it
    at all — a doubt is not a yes (§33) — is refused here, with the STARTED protocol of ADR 0015
    §8 named in the message. So the first non-idempotent tool cannot enter without implementing
    that protocol first: the guard does not depend on anyone remembering.
    """

    __slots__ = ("_tools",)

    def __init__(self, tools: Iterable[ToolPort]) -> None:
        table: dict[CapabilityId, ToolPort] = {}
        for tool in tools:
            declared = getattr(tool, "idempotent", None)
            if declared is not True:
                raise NotIdempotentError(tool.capability_id, tool.name, declared)
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


class VerifierRegistry:
    """Verifiers by capability id, frozen at construction (port ``VerifierRegistryPort``)."""

    __slots__ = ("_verifiers",)

    def __init__(self, verifiers: Iterable[VerifierPort]) -> None:
        table: dict[CapabilityId, VerifierPort] = {}
        for verifier in verifiers:
            if verifier.capability_id in table:
                raise AlreadyExistsError("verifier", verifier.capability_id)
            table[verifier.capability_id] = verifier
        self._verifiers: Mapping[CapabilityId, VerifierPort] = MappingProxyType(table)

    def get(self, capability_id: CapabilityId) -> VerifierPort:
        """The verifier of this capability; :class:`VerifierNotFound` if there is none."""
        try:
            return self._verifiers[capability_id]
        except KeyError:
            raise VerifierNotFound(capability_id) from None

    def verifiers(self) -> tuple[VerifierPort, ...]:
        """Every verifier, in construction order."""
        return tuple(self._verifiers.values())


def tools_v01(*, root: Path | str, clock: Clock, ids: IdGenerator) -> ToolRegistry:
    """The tools of v0.1 that run without a provider: ``core.echo`` and ``workspace.write_note``.

    ``model.complete`` has no tool yet (M7.2): the executor refuses it before any decision.
    """
    return ToolRegistry((EchoTool(clock, ids), WriteNoteTool(root, clock, ids)))


def verifiers_v01(*, root: Path | str) -> VerifierRegistry:
    """The verifiers of the tools of :func:`tools_v01`, on the same workspace ``root``.

    No clock and no id source: a verifier creates no entity. ``model.complete`` has no verifier,
    as it has no tool.
    """
    return VerifierRegistry((EchoVerifier(), WriteNoteVerifier(root)))
