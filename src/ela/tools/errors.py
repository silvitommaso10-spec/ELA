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

__all__ = [
    "NotIdempotentError",
    "SilentVerifierError",
    "ToolNotFound",
    "ToolsError",
    "VerifierNotFound",
]


class ToolsError(Exception):
    """Base class of every error the tools package raises on its own."""


class SilentVerifierError(ToolsError):
    """A verifier that does not *say* whether it reads the machine it runs on (ADR 0038 §14).

    Raised by :class:`~ela.tools.registry.VerifierRegistry` at construction, like
    :class:`NotIdempotentError` for a tool: both answers are legal, and what is refused is
    silence. The orchestrator reads the flag to decide whether a capability may travel to a node
    that is not this one (M12.1, D15), and a doubt must not read as "it may".
    """

    def __init__(self, capability_id: CapabilityId, name: str, declared: object) -> None:
        self.capability_id = capability_id
        self.name = name
        self.declared = declared
        super().__init__(
            f"verifier {name} of {capability_id} does not declare reads_the_machine as a bool "
            f"(it says {declared!r}): whether it may verify an effect elsewhere is unknown"
        )


class NotIdempotentError(ToolsError):
    """A tool that does not *say* whether running it twice is running it once (ADR 0021 §1).

    Raised by :class:`~ela.tools.registry.ToolRegistry` at construction, before anything can be
    executed. Since M7.2 both answers are legal — ``True`` is repaired by repeating the tool
    after a crash (window 7a of ADR 0015 §8), ``False`` runs under the STARTED protocol and is
    never repeated — so what is refused here is **silence**: a tool whose ``idempotent`` is
    missing, or is not a boolean at all. A doubt is not a yes (§33), and the executor reads this
    flag to decide whether a run may be repeated: a wrong guess there repeats an action that
    cannot be repeated.
    """

    def __init__(self, capability_id: CapabilityId, name: str, declared: object) -> None:
        self.capability_id = capability_id
        self.name = name
        self.declared = declared
        super().__init__(
            f"tool {name!r} for {capability_id} declares no boolean idempotent "
            f"({declared!r}): the executor repeats an idempotent tool after a crash and runs a "
            f"non-idempotent one under the STARTED protocol of ADR 0021 §1, and it cannot guess "
            f"which this is"
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
