"""What every tool of ELA shares (spec §27, §28; ADR 0005 §5, ADR 0013 §7).

A tool implements :class:`~ela.ports.ToolPort`: it receives a
:class:`~ela.domain.PermissionDecision` as data and, before doing anything, refuses one that
does not allow — not ``ALLOWED``, about another capability, or expired at the tool's own clock
(closed bound: expiring now is expired). That check is the same for every tool and lives here
once, in :meth:`Tool.execute`; a subclass writes only :meth:`Tool._run`, which acts on the
arguments and answers with an :class:`Outcome`.

A failure while acting is an :class:`Outcome` with an error code, turned into a FAILED
:class:`~ela.domain.ExecutionResult`: a result, never an exception, so the executor can always
record that the tool ran (§32, §63 "eseguire non è riuscire"). A tool owns its clock and its id
source (ADR 0005 §7) and never holds the Guardian or a store (contract of ``test_tool.py``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

from ela.domain import (
    CapabilityId,
    ErrorMetadata,
    ExecutionId,
    ExecutionResult,
    ExecutionStatus,
    JsonMapping,
    PermissionDecision,
    PermissionOutcome,
)
from ela.ports import Clock, IdGenerator, NotAllowedError

__all__ = ["ARGUMENTS_INVALID", "Outcome", "Tool", "check_decision"]

ARGUMENTS_INVALID = "arguments.invalid"
"""An argument is missing or of the wrong type. The Guardian validated the schema already
(ADR 0011 §3); a tool checks again because it never trusts its caller (§28)."""


@dataclass(frozen=True, slots=True)
class Outcome:
    """What :meth:`Tool._run` produced: an output, or an error code with a reason.

    ``code`` set means FAILED; the ``message`` names what went wrong in words that may enter the
    audit trail — a path, a type name, an OS error — never the content of an argument (§57).
    """

    output: JsonMapping
    code: str | None = None
    message: str = ""

    @property
    def succeeded(self) -> bool:
        return self.code is None


def check_decision(
    decision: PermissionDecision, capability_id: CapabilityId, now: datetime
) -> None:
    """The contract of ADR 0005 §5: :class:`~ela.ports.NotAllowedError` unless ``decision``
    allows *this* capability *now*; ``None`` if it does."""
    if decision.capability_id != capability_id:
        raise NotAllowedError(capability_id, f"the decision is about {decision.capability_id}")
    if decision.outcome is not PermissionOutcome.ALLOWED:
        raise NotAllowedError(capability_id, f"outcome is {decision.outcome.value}")
    if decision.expires_at is not None and decision.expires_at <= now:
        raise NotAllowedError(
            capability_id, f"decision expired at {decision.expires_at.isoformat()}"
        )


class Tool(ABC):
    """A tool: the decision check, the timing and the result shape, once for all (ADR 0013 §7).

    ``error_codes`` and ``output_keys`` declare what a subclass can produce; ADR 0013 documents
    them per tool and ``tests/docs/test_adr_executor.py`` compares.

    ``idempotent`` says whether running the tool twice with the same arguments leaves the world
    as running it once does. It has **no default**: a subclass declares it, because the answer is
    the tool's alone and forgetting it must not read as a yes. It is what crash window 7a rests
    on (ADR 0015 §8) — the instant between the tool's effect and the insert of its result, where
    a retry runs the tool again — and :class:`~ela.tools.registry.ToolRegistry` refuses to
    register a tool that does not declare it true: the first tool that cannot promise it brings
    the STARTED protocol of ADR 0015 §8 with it.
    """

    error_codes: ClassVar[frozenset[str]] = frozenset({ARGUMENTS_INVALID})
    output_keys: ClassVar[frozenset[str]] = frozenset()
    idempotent: ClassVar[bool]

    def __init__(
        self, capability_id: CapabilityId, clock: Clock, ids: IdGenerator, *, name: str
    ) -> None:
        self._capability_id = capability_id
        self._clock = clock
        self._ids = ids
        self._name = name

    @property
    def capability_id(self) -> CapabilityId:
        return self._capability_id

    @property
    def name(self) -> str:
        return self._name

    async def execute(
        self, decision: PermissionDecision, arguments: JsonMapping
    ) -> ExecutionResult:
        """Check the decision, act, and answer with a result whose status says how it went."""
        started = self._clock.now()
        check_decision(decision, self._capability_id, started)
        outcome = await self._run(arguments)
        finished = self._clock.now()
        error = (
            None
            if outcome.code is None
            else ErrorMetadata(
                code=outcome.code, message=outcome.message, tool_name=self._name, retryable=False
            )
        )
        return ExecutionResult(
            id=ExecutionId(self._ids.new_uuid()),
            created_at=finished,
            capability_id=self._capability_id,
            status=ExecutionStatus.SUCCEEDED if outcome.succeeded else ExecutionStatus.FAILED,
            task_id=decision.task_id,
            step_id=decision.step_id,
            tool_name=self._name,
            output=outcome.output,
            error=error,
            duration_ms=max(0, int((finished - started).total_seconds() * 1000)),
        )

    @abstractmethod
    async def _run(self, arguments: JsonMapping) -> Outcome:
        """Act on already-allowed ``arguments``; a failure is an :class:`Outcome` with a code."""
