"""Contract of ``ToolPort`` (spec §27, §28, §52): no execution without an allowing decision.

The decision is data the tool receives; the tool never holds the Guardian or the store that
produced it (CLAUDE.md "Architettura", ADR 0005).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import get_type_hints

import pytest

from ela.domain import CapabilityId, ExecutionResult, PermissionDecision, PermissionOutcome
from ela.ports import (
    AuthorizationStore,
    Clock,
    NotAllowedError,
    PermissionGuardianPort,
    ToolPort,
)
from tests.domain.examples import PERMISSION_DECISION

LONG_AGO = datetime(2000, 1, 1, tzinfo=UTC)
FAR_AHEAD = datetime(2100, 1, 1, tzinfo=UTC)
ARGUMENTS = {"path": "workspace/notes/briefing.md", "body": "..."}


def decision_for(tool: ToolPort, **update: object) -> PermissionDecision:
    """An ALLOWED, unexpired decision about this tool's capability, then ``update`` applied."""
    base = {
        "capability_id": tool.capability_id,
        "outcome": PermissionOutcome.ALLOWED,
        "expires_at": None,
    }
    return PERMISSION_DECISION.model_copy(update={**base, **update})


async def test_allowed_decision_executes(tool: ToolPort) -> None:
    decision = decision_for(tool, expires_at=FAR_AHEAD)
    result = await tool.execute(decision, ARGUMENTS)
    assert isinstance(result, ExecutionResult)
    assert result.capability_id == tool.capability_id
    assert result.tool_name == tool.name
    assert result.task_id == decision.task_id
    assert result.step_id == decision.step_id


@pytest.mark.parametrize(
    "outcome", [PermissionOutcome.DENIED, PermissionOutcome.REQUIRES_APPROVAL], ids=str
)
async def test_non_allowed_decision_is_refused(tool: ToolPort, outcome: PermissionOutcome) -> None:
    with pytest.raises(NotAllowedError):
        await tool.execute(decision_for(tool, outcome=outcome), ARGUMENTS)


async def test_expired_decision_is_refused(tool: ToolPort) -> None:
    with pytest.raises(NotAllowedError):
        await tool.execute(decision_for(tool, expires_at=LONG_AGO), ARGUMENTS)


async def test_expiry_is_closed(tool: ToolPort, clock: Clock) -> None:
    """A decision expiring at this very instant is already expired (ADR 0005).

    The tool's own clock is not reachable through the port, so the boundary is probed with a
    fake clock's instant: any implementation whose clock is at or past ``expires_at`` must refuse.
    The exact-instant case on the fake tool is in ``tests/testing/test_fakes.py``.
    """
    with pytest.raises(NotAllowedError):
        await tool.execute(decision_for(tool, expires_at=clock.now()), ARGUMENTS)


async def test_decision_for_another_capability_is_refused(tool: ToolPort) -> None:
    other = CapabilityId("some.other_capability")
    assert other != tool.capability_id
    with pytest.raises(NotAllowedError):
        await tool.execute(decision_for(tool, capability_id=other), ARGUMENTS)


def test_tool_holds_no_guardian_and_no_store(tool: ToolPort) -> None:
    forbidden = (PermissionGuardianPort, AuthorizationStore)
    for name, value in vars(tool).items():
        assert not isinstance(value, forbidden), f"{type(tool).__name__}.{name}"
    for method in (type(tool).__init__, type(tool).execute):
        for name, hint in get_type_hints(method).items():
            assert hint not in forbidden, f"{method.__qualname__}({name})"
