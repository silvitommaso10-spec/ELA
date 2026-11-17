"""Decisions for the tool tests: ALLOWED for a capability, or deliberately not."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ela.domain import CapabilityId, PermissionDecision, PermissionOutcome
from tests.domain.examples import PERMISSION_DECISION

FAR_AHEAD = datetime(2100, 1, 1, tzinfo=UTC)


def allowed(capability_id: CapabilityId, **update: Any) -> PermissionDecision:
    """An ALLOWED, unexpired decision about ``capability_id``, then ``update`` applied."""
    base = {
        "capability_id": capability_id,
        "outcome": PermissionOutcome.ALLOWED,
        "expires_at": None,
    }
    return PERMISSION_DECISION.model_copy(update={**base, **update})
