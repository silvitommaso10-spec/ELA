"""Contract of ``AuthorizingGuardianPort`` (spec §27, §32; ADR 0013 §10): decide and record.

The only implementation is the real Guardian on the fake log (no fake of its own): every call
returns one decision and appends exactly one ``PERMISSION_DECIDED`` that names it, and a doubt
is still ``DENIED``. The audit log is the one the implementation was built with, reached here
through ``vars`` because the port exposes no way to it — on purpose.
"""

from __future__ import annotations

import inspect
from typing import get_type_hints

from ela.domain import AuditEventType, CapabilityId, PermissionDecision, PermissionOutcome
from ela.ports import (
    AuditLog,
    AuthorizingGuardianPort,
    ModelProvider,
    ProviderRegistryPort,
    ToolPort,
)
from tests.domain.examples import CAPABILITY_SPEC, TASK, TASK_STEP

UNKNOWN_SPEC = CAPABILITY_SPEC.model_copy(update={"id": CapabilityId("nobody.knows_this")})
ARGUMENTS = {"path": "workspace/notes/briefing.md", "body": "..."}


def _audit_of(guardian: AuthorizingGuardianPort) -> AuditLog:
    logs = [value for value in vars(guardian).values() if isinstance(value, AuditLog)]
    assert len(logs) == 1, "an authorizing Guardian holds exactly one audit log"
    return logs[0]


async def test_authorize_is_asynchronous_and_returns_a_decision(
    authorizing_guardian: AuthorizingGuardianPort,
) -> None:
    pending = authorizing_guardian.authorize(UNKNOWN_SPEC, ARGUMENTS)
    assert inspect.isawaitable(pending)
    assert isinstance(await pending, PermissionDecision)


async def test_unknown_capability_is_denied(authorizing_guardian: AuthorizingGuardianPort) -> None:
    decision = await authorizing_guardian.authorize(UNKNOWN_SPEC, ARGUMENTS)
    assert decision.outcome is PermissionOutcome.DENIED
    assert decision.reason.strip() != ""


async def test_every_call_records_exactly_one_event_naming_the_decision(
    authorizing_guardian: AuthorizingGuardianPort,
) -> None:
    first = await authorizing_guardian.authorize(UNKNOWN_SPEC, ARGUMENTS, task=TASK, step=TASK_STEP)
    second = await authorizing_guardian.authorize(UNKNOWN_SPEC, ARGUMENTS)
    events = await _audit_of(authorizing_guardian).read()
    assert [event.event_type for event in events] == [AuditEventType.PERMISSION_DECIDED] * 2
    assert [event.decision_id for event in events] == [first.id, second.id]
    assert (events[0].task_id, events[0].step_id) == (TASK.id, TASK_STEP.id)
    assert events[0].created_at == first.created_at


async def test_the_decision_echoes_the_context(
    authorizing_guardian: AuthorizingGuardianPort,
) -> None:
    decision = await authorizing_guardian.authorize(
        UNKNOWN_SPEC, ARGUMENTS, task=TASK, step=TASK_STEP
    )
    assert decision.capability_id == UNKNOWN_SPEC.id
    assert (decision.task_id, decision.step_id) == (TASK.id, TASK_STEP.id)
    assert decision.authorization_id is None


def test_guardian_holds_no_tool_and_no_provider(
    authorizing_guardian: AuthorizingGuardianPort,
) -> None:
    forbidden = (ToolPort, ModelProvider, ProviderRegistryPort)
    for name, value in vars(authorizing_guardian).items():
        assert not isinstance(value, forbidden), f"{type(authorizing_guardian).__name__}.{name}"
    for method in (type(authorizing_guardian).__init__, type(authorizing_guardian).authorize):
        for name, hint in get_type_hints(method).items():
            assert hint not in forbidden, f"{method.__qualname__}({name})"
