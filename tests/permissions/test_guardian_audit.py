"""``PermissionGuardian.authorize``: each decision becomes one ``PERMISSION_DECIDED`` (ADR 0011 §8).

The payload carries what the decision was about — outcome, rule, targets — and never the
arguments (§57). If the log refuses the event, the decision is not returned at all.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from ela.domain import (
    ActorKind,
    AuditEvent,
    AuditEventType,
    CapabilitySpec,
    PermissionOutcome,
)
from ela.permissions import GUARDIAN_ACTOR, POLICY_VERSION, PermissionGuardian
from ela.testing.fakes import FakeCapabilityRegistry, FakeClock, FakeIdGenerator
from tests.domain.examples import TASK
from tests.permissions.support import (
    CATALOGUE,
    COMPLETE,
    COMPLETE_ARGS,
    ECHO,
    ECHO_ARGS,
    HIGH,
    NOTE,
    NOTE_ARGS,
    Harness,
    grant,
    harness,
    step_for,
)


@pytest.fixture
def h() -> Harness:
    return harness()


async def events(h: Harness) -> tuple[AuditEvent, ...]:
    return await h.audit.read()


async def test_authorize_returns_the_decision_and_records_it_once(h: Harness) -> None:
    step = step_for(NOTE.id)
    decision = await h.guardian.authorize(NOTE, NOTE_ARGS, task=TASK, step=step)
    recorded = await events(h)
    assert len(recorded) == 1
    (event,) = recorded
    assert event.event_type is AuditEventType.PERMISSION_DECIDED
    assert event.actor == GUARDIAN_ACTOR
    assert event.actor.kind is ActorKind.SYSTEM and event.actor.id == "permission-guardian"
    assert event.decision_id == decision.id
    assert event.capability_id == NOTE.id
    assert (event.task_id, event.step_id) == (TASK.id, step.id)
    assert event.authorization_id is None
    assert event.created_at == decision.created_at
    assert event.summary == f"decide: ALLOWED workspace.write_note (LOW): {decision.reason}"


async def test_the_payload_carries_the_decision_not_the_arguments(h: Harness) -> None:
    decision = await h.guardian.authorize(NOTE, {**NOTE_ARGS, "body": "SECRET-BODY"})
    (event,) = await events(h)
    assert event.payload["outcome"] == "ALLOWED"
    assert event.payload["risk"] == "LOW"
    assert event.payload["rule"] == "ALLOW_WITHIN_SCOPE"
    assert event.payload["reason"] == decision.reason
    assert event.payload["targets"] == ("workspace/notes/briefing.md",)  # frozen by the domain
    assert event.payload["policy"] == POLICY_VERSION
    assert decision.expires_at is not None
    assert event.payload["expires_at"] == decision.expires_at.isoformat()
    assert "error" not in event.payload
    serialized = json.dumps(event.model_dump(mode="json"))
    assert "SECRET-BODY" not in serialized
    assert "body" not in event.payload


@pytest.mark.parametrize(
    "spec, arguments, outcome",
    [
        (ECHO, ECHO_ARGS, PermissionOutcome.ALLOWED),
        (HIGH, ECHO_ARGS, PermissionOutcome.DENIED),
        (COMPLETE, COMPLETE_ARGS, PermissionOutcome.REQUIRES_APPROVAL),
    ],
    ids=lambda v: v.value if isinstance(v, PermissionOutcome) else "",
)
async def test_every_outcome_is_recorded(
    h: Harness, spec: CapabilitySpec, arguments: dict[str, Any], outcome: PermissionOutcome
) -> None:
    decision = await h.guardian.authorize(spec, arguments)
    assert decision.outcome is outcome
    (event,) = await events(h)
    assert event.payload["outcome"] == outcome.value
    assert event.payload["expires_at"] == (
        None if decision.expires_at is None else decision.expires_at.isoformat()
    )
    assert event.summary.startswith(f"decide: {outcome.value} {spec.id} ({spec.risk.value}): ")


async def test_the_authorization_applied_is_in_the_event(h: Harness) -> None:
    authorization = grant(COMPLETE)
    decision = await h.guardian.authorize(
        COMPLETE, COMPLETE_ARGS, authorization=authorization, authorization_uses=0
    )
    assert decision.outcome is PermissionOutcome.ALLOWED
    (event,) = await events(h)
    assert event.authorization_id == authorization.id


class _BrokenRegistry:
    def get(self, capability_id: object) -> CapabilitySpec:
        raise RuntimeError("boom")

    def specs(self) -> tuple[CapabilitySpec, ...]:
        return ()


async def test_an_internal_error_is_recorded_with_its_type() -> None:
    h = harness(registry=_BrokenRegistry())
    decision = await h.guardian.authorize(ECHO, ECHO_ARGS)
    assert decision.outcome is PermissionOutcome.DENIED
    (event,) = await events(h)
    assert event.payload["error"] == "RuntimeError"
    assert event.payload["rule"] == "INTERNAL_ERROR"


class _RefusingAuditLog:
    """A log that refuses every append: what a full disk or a broken chain looks like."""

    async def append(self, event: AuditEvent) -> None:
        raise OSError("disk full")

    async def read(self, **filters: Any) -> tuple[AuditEvent, ...]:
        return ()


async def test_a_decision_the_log_refuses_is_not_delivered() -> None:
    guardian = PermissionGuardian(
        FakeCapabilityRegistry(CATALOGUE), FakeClock(), FakeIdGenerator(), _RefusingAuditLog()
    )
    with pytest.raises(OSError, match="disk full"):
        await guardian.authorize(ECHO, ECHO_ARGS)


async def test_two_calls_are_two_events_with_two_decisions(h: Harness) -> None:
    first = await h.guardian.authorize(ECHO, ECHO_ARGS)
    second = await h.guardian.authorize(HIGH, ECHO_ARGS)
    recorded = await events(h)
    assert [event.decision_id for event in recorded] == [first.id, second.id]
    assert len({event.id for event in recorded}) == 2
