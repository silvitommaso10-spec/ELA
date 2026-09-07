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
from ela.ports import (
    AlreadyExistsError,
    Clock,
    IdGenerator,
    ModelRouterPort,
    ProviderRegistryPort,
    ToolPort,
    VerifierPort,
)
from ela.tools.echo import EchoTool
from ela.tools.errors import NotIdempotentError, ToolNotFound, VerifierNotFound
from ela.tools.model import ModelCompleteTool
from ela.tools.notes import WriteNoteTool
from ela.tools.verifiers import EchoVerifier, ModelCompleteVerifier, WriteNoteVerifier

__all__ = ["ToolRegistry", "VerifierRegistry", "tools_v01", "verifiers_v01"]


class ToolRegistry:
    """Tools by capability id, frozen at construction (port ``ToolRegistryPort``).

    **Every tool declares whether it is idempotent, and none may stay silent** (M5.3, then M7.2).
    Until M7.2 the registry accepted only ``True``, because crash window 7a was repaired by
    running the tool again and that repair is safe only while twice is once. ADR 0021 §1 brings
    the STARTED protocol the guard was waiting for, so ``False`` is now a legal answer: the
    executor writes a STARTED record before such a tool acts and never runs it twice for one
    step. What is still refused is a tool that declares *nothing*, or something that is not a
    boolean — the executor reads this flag to choose between repeating a run and refusing to,
    and a doubt is not a yes (§33).
    """

    __slots__ = ("_tools",)

    def __init__(self, tools: Iterable[ToolPort]) -> None:
        table: dict[CapabilityId, ToolPort] = {}
        for tool in tools:
            declared = getattr(tool, "idempotent", None)
            if not isinstance(declared, bool):
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


def tools_v01(
    *,
    root: Path | str,
    clock: Clock,
    ids: IdGenerator,
    router: ModelRouterPort,
    providers: ProviderRegistryPort,
) -> ToolRegistry:
    """The three tools of v0.1, in the order of the catalogue (§29).

    ``router`` decides which provider answers ``model.complete`` and with which profile (§25,
    ADR 0022), and ``providers`` is where the name it chose is resolved. Both are mandatory: a
    registry that quietly dropped the third tool when nobody passed them would make a capability
    disappear from what ELA can do, and a provider with no credentials already has a way to say
    so — it registers ``UNAVAILABLE``, the router skips it, and if there is nothing else the call
    fails with ``provider.unavailable`` without touching the network (ADR 0020 §2).
    """
    return ToolRegistry(
        (
            EchoTool(clock, ids),
            WriteNoteTool(root, clock, ids),
            ModelCompleteTool(router, providers, clock, ids),
        )
    )


def verifiers_v01(*, root: Path | str, router: ModelRouterPort) -> VerifierRegistry:
    """The verifiers of the tools of :func:`tools_v01`, on the same workspace ``root``.

    No clock and no id source: a verifier creates no entity. ``router`` is the **same** port the
    tools were given, and it is asked the same question again: a verifier that read the route out
    of the result would be checking the tool's word, and a verifier that had a policy of its own
    would be checking a second opinion (ADR 0022 §10). No provider: the verifier of
    ``model.complete`` reads the result of the call and never makes another one.
    """
    return VerifierRegistry(
        (EchoVerifier(), WriteNoteVerifier(root), ModelCompleteVerifier(router))
    )
