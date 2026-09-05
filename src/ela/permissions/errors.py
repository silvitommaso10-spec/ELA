"""Errors of the permissions package (spec §28, §29, §33).

Every error here is raised *before* anything happens: a capability that cannot enter the
catalogue leaves no catalogue behind, an argument that violates the schema is refused before a
decision is even considered. Naming the failure is what lets the caller tell "the id is
unknown" from "the schema is wrong" without reading a message.
"""

from __future__ import annotations

from ela.domain import CapabilityId, RiskLevel
from ela.ports import NotFoundError

__all__ = [
    "CapabilityNotFound",
    "InvalidArgumentsError",
    "InvalidCapabilityError",
    "PermissionsError",
    "RiskNotAllowedError",
]


class PermissionsError(Exception):
    """Base class of every error the permissions package raises on its own."""


class CapabilityNotFound(NotFoundError):
    """``get`` on an id the catalogue does not hold (§28).

    A :class:`~ela.ports.NotFoundError`, as the port promises: a caller that handles port errors
    in one clause keeps working, one that wants to know it was a capability catches this.
    """

    def __init__(self, capability_id: CapabilityId) -> None:
        super().__init__("capability", capability_id)
        self.capability_id = capability_id


class InvalidCapabilityError(PermissionsError):
    """A specification the catalogue refuses: bad schema, bad scope, inconsistent fields (§28)."""

    def __init__(self, capability_id: CapabilityId, reason: str) -> None:
        self.capability_id = capability_id
        self.reason = reason
        super().__init__(f"capability {capability_id!r} is invalid: {reason}")


class RiskNotAllowedError(InvalidCapabilityError):
    """A specification above the highest risk v0.1 admits (§29: no HIGH, no CRITICAL)."""

    def __init__(self, capability_id: CapabilityId, risk: RiskLevel, max_risk: RiskLevel) -> None:
        self.risk = risk
        self.max_risk = max_risk
        super().__init__(
            capability_id, f"risk {risk.value} is above {max_risk.value}, the maximum of v0.1"
        )


class InvalidArgumentsError(PermissionsError):
    """Arguments that do not satisfy the capability's ``input_schema`` (§28, §33).

    ``errors`` lists every violation, each as ``<json path>: <message>``, in path order: the
    caller sees the whole picture at once instead of the first problem only.
    """

    def __init__(self, capability_id: CapabilityId, errors: tuple[str, ...]) -> None:
        self.capability_id = capability_id
        self.errors = errors
        super().__init__(
            f"arguments for {capability_id!r} violate its schema: " + "; ".join(errors)
        )
