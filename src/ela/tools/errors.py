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

__all__ = ["NotIdempotentError", "ToolNotFound", "ToolsError", "VerifierNotFound"]


class ToolsError(Exception):
    """Base class of every error the tools package raises on its own."""


class NotIdempotentError(ToolsError):
    """A tool that does not promise that running it twice is running it once (ADR 0015 §8).

    Raised by :class:`~ela.tools.registry.ToolRegistry` at construction, before anything can be
    executed: crash window 7a — the instant between the tool's effect and the insert of its
    result — is repaired by *repeating* the tool, and that repair is only safe while every
    registered tool is idempotent. A tool that is not, or that does not say, needs the STARTED
    protocol of ADR 0015 §8 first: a result persisted as STARTED before the tool acts, a retry
    that verifies instead of repeating, and no tool ever started twice for one execution id.
    """

    def __init__(self, capability_id: CapabilityId, name: str, declared: object) -> None:
        self.capability_id = capability_id
        self.name = name
        self.declared = declared
        said = "declares idempotent=False" if declared is False else "declares no idempotent"
        super().__init__(
            f"tool {name!r} for {capability_id} {said}: a retry after a crash repeats the tool "
            f"(crash window 7a), so a tool that cannot promise it needs the STARTED protocol of "
            f"ADR 0015 §8 first"
        )


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
