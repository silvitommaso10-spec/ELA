"""What every verifier of ELA shares (spec §20, §63; ADR 0014).

A verifier implements :class:`~ela.ports.VerifierPort`: after a tool ran, it checks the world
against the success conditions of the step, and only its word — never the tool's — completes
the step. It is a separate object from the tool by construction (a tool that verified itself
would be certifying its own claim) and it is **read-only**: it looks, compares, and changes
nothing (rule 18 keeps the module of the verifiers free of any write).

The contract of the port comes first and lives here once, in :meth:`Verifier.verify`: a result
of another capability, a result that did not succeed, no condition, a condition outside the
vocabulary — each a failure with a named code (:func:`~ela.ports.check_verifiable`), never a
pass. A subclass writes only :meth:`Verifier._check`, one condition at a time, and answers with
an :class:`~ela.domain.ErrorMetadata` when the condition does not hold. Every failure names its
condition in ``details["condition"]`` and says why in words that may enter the audit trail — a
path, a size, an OS error — never the content of an argument or of the world (§57).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import ClassVar, Final

from ela.domain import CapabilityId, ErrorMetadata, ExecutionResult, JsonMapping, JsonValue
from ela.ports import (
    VERIFICATION_NO_CONDITIONS,
    VERIFICATION_NOT_SUCCEEDED,
    VERIFICATION_UNKNOWN_CONDITION,
    VERIFICATION_WRONG_CAPABILITY,
    check_verifiable,
)

__all__ = ["COMMON_FAILURE_CODES", "VERIFICATION_ARGUMENTS_INVALID", "Verifier"]

VERIFICATION_ARGUMENTS_INVALID: Final = "verification.arguments_invalid"
"""An argument the condition needs is missing or of the wrong type. The Guardian and the tool
excluded it already; a verifier checks again because it trusts neither (§28)."""

COMMON_FAILURE_CODES: Final[frozenset[str]] = frozenset(
    {
        VERIFICATION_WRONG_CAPABILITY,
        VERIFICATION_NOT_SUCCEEDED,
        VERIFICATION_NO_CONDITIONS,
        VERIFICATION_UNKNOWN_CONDITION,
        VERIFICATION_ARGUMENTS_INVALID,
    }
)
"""The failure codes every verifier can report, before any condition of its own."""


class Verifier(ABC):
    """A verifier: the contract once, the conditions in the subclass (ADR 0014 §2).

    ``conditions`` is the vocabulary — the success conditions this verifier can check — and
    ``failure_codes`` what it can report; ADR 0014 documents both per verifier and
    ``tests/docs/test_adr_verification.py`` compares.
    """

    conditions: ClassVar[frozenset[str]] = frozenset()
    failure_codes: ClassVar[frozenset[str]] = COMMON_FAILURE_CODES

    def __init__(self, capability_id: CapabilityId, *, name: str) -> None:
        self._capability_id = capability_id
        self._name = name

    @property
    def capability_id(self) -> CapabilityId:
        return self._capability_id

    @property
    def name(self) -> str:
        return self._name

    async def verify(
        self, conditions: Sequence[str], arguments: JsonMapping, result: ExecutionResult
    ) -> tuple[ErrorMetadata, ...]:
        """The contract, then each condition in order; empty means every condition holds."""
        refused = check_verifiable(self._capability_id, self.conditions, conditions, result)
        if refused:
            return refused
        failures = []
        for condition in conditions:
            failure = await self._check(condition, arguments, result)
            if failure is not None:
                failures.append(failure)
        return tuple(failures)

    @abstractmethod
    async def _check(
        self, condition: str, arguments: JsonMapping, result: ExecutionResult
    ) -> ErrorMetadata | None:
        """Whether one known ``condition`` holds: ``None`` if it does, else the failure."""

    def _failure(
        self,
        condition: str,
        code: str,
        message: str,
        *,
        retryable: bool,
        details: dict[str, JsonValue] | None = None,
    ) -> ErrorMetadata:
        """A failure of ``condition``: its code, why, and the sizes or names that explain it."""
        return ErrorMetadata(
            code=code,
            message=message,
            tool_name=None,
            retryable=retryable,
            details={"condition": condition, **({} if details is None else details)},
        )
