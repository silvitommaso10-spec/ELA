"""Contract of ``PermissionGuardianPort`` (spec §27, §33): pure, synchronous, DENIED when in doubt.

The fail-safe is the one clause every Guardian — the fake and the real one (M4.2) — must
satisfy: a capability it has no rule for is denied, with a reason. And no Guardian holds a tool
or a provider (§27, §47): it decides on specifications and context, it never executes.
"""

from __future__ import annotations

import inspect
from typing import get_type_hints

from ela.domain import CapabilityId, PermissionDecision, PermissionOutcome
from ela.ports import ModelProvider, PermissionGuardianPort, ProviderRegistry, ToolPort
from tests.domain.examples import (
    CAPABILITY_SPEC,
    SINGLE_USE_AUTHORIZATION,
    TASK,
    TASK_STEP,
)

UNKNOWN_SPEC = CAPABILITY_SPEC.model_copy(update={"id": CapabilityId("nobody.knows_this")})
ARGUMENTS = {"path": "workspace/notes/briefing.md", "body": "..."}


def test_unknown_capability_is_denied(guardian: PermissionGuardianPort) -> None:
    decision = guardian.decide(UNKNOWN_SPEC, ARGUMENTS)
    assert decision.outcome is PermissionOutcome.DENIED
    assert decision.reason.strip() != ""


def test_decide_is_synchronous(guardian: PermissionGuardianPort) -> None:
    result = guardian.decide(UNKNOWN_SPEC, ARGUMENTS)
    assert not inspect.isawaitable(result)
    assert isinstance(result, PermissionDecision)


def test_decision_echoes_the_request(guardian: PermissionGuardianPort) -> None:
    decision = guardian.decide(
        CAPABILITY_SPEC,
        ARGUMENTS,
        task=TASK,
        step=TASK_STEP,
        authorization=SINGLE_USE_AUTHORIZATION,
    )
    assert decision.capability_id == CAPABILITY_SPEC.id
    assert decision.risk is CAPABILITY_SPEC.risk
    assert decision.task_id == TASK.id
    assert decision.step_id == TASK_STEP.id
    assert decision.authorization_id == SINGLE_USE_AUTHORIZATION.id
    assert decision.created_at.tzinfo is not None


def test_decision_without_context_has_no_context(guardian: PermissionGuardianPort) -> None:
    decision = guardian.decide(CAPABILITY_SPEC, ARGUMENTS)
    assert decision.task_id is None
    assert decision.step_id is None
    assert decision.authorization_id is None


def test_decide_takes_the_use_count_as_a_fact(guardian: PermissionGuardianPort) -> None:
    """``authorization_uses`` is supplied by the caller (ADR 0011); doubt stays DENIED with it."""
    decision = guardian.decide(UNKNOWN_SPEC, ARGUMENTS, authorization_uses=3)
    assert decision.outcome is PermissionOutcome.DENIED


def test_guardian_holds_no_tool_and_no_provider(guardian: PermissionGuardianPort) -> None:
    """Mirror of ``test_tool_holds_no_guardian_and_no_store``: the Guardian never executes."""
    forbidden = (ToolPort, ModelProvider, ProviderRegistry)
    for name, value in vars(guardian).items():
        assert not isinstance(value, forbidden), f"{type(guardian).__name__}.{name}"
    for method in (type(guardian).__init__, type(guardian).decide):
        for name, hint in get_type_hints(method).items():
            assert hint not in forbidden, f"{method.__qualname__}({name})"
