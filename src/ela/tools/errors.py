"""Errors of the tools package (spec §28, §33).

A tool reports what went wrong *while acting* as a FAILED :class:`~ela.domain.ExecutionResult`
with a named error code, never as an exception (ADR 0013 §7): the executor records every result,
and a tool that raised halfway would leave the audit trail without the fact that it ran. The
exceptions here are raised *before* anything happens — a lookup that misses — and named so a
caller can tell them apart without reading a message.
"""

from __future__ import annotations

from ela.domain import CapabilityId
from ela.ports import NotFoundError

__all__ = ["ToolNotFound", "ToolsError", "VerifierNotFound"]


class ToolsError(Exception):
    """Base class of every error the tools package raises on its own."""


class ToolNotFound(NotFoundError):
    """``get`` on a capability no registered tool implements (§28).

    A :class:`~ela.ports.NotFoundError`, as the port promises; the executor raises it before any
    decision is asked, so that no grant is spent on a capability nothing can execute.
    """

    def __init__(self, capability_id: CapabilityId) -> None:
        super().__init__("tool", capability_id)
        self.capability_id = capability_id


class VerifierNotFound(NotFoundError):
    """``get`` on a capability no registered verifier checks (§63; ADR 0014).

    Raised by the executor before any decision, like :class:`ToolNotFound`: an action that
    cannot be verified is not executed, and no grant is spent on it.
    """

    def __init__(self, capability_id: CapabilityId) -> None:
        super().__init__("verifier", capability_id)
        self.capability_id = capability_id
