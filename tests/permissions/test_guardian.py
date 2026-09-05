"""``PermissionGuardian.decide``: catalogue, arguments, step, policy by risk, authorizations,
expiry, fail-safe (ADR 0011).

Every ``ALLOWED`` here has a justification the reader can point at; every doubt is ``DENIED``
and every "ask" is ``REQUIRES_APPROVAL``, never the other way round.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Any
from uuid import UUID

import pytest

from ela.domain import (
    CapabilityId,
    CapabilitySpec,
    PermissionDecision,
    PermissionOutcome,
    RiskLevel,
    StepId,
)
from ela.permissions import (
    DEFAULT_DECISION_TTL,
    POLICY_VERSION,
    RISK_POLICY,
    PermissionGuardian,
    Rule,
)
from ela.permissions import guardian as guardian_module
from ela.testing.fakes import FakeAuditLog, FakeCapabilityRegistry, FakeClock, FakeIdGenerator
from tests.domain.examples import TASK
from tests.permissions.support import (
    CATALOGUE,
    COMPLETE,
    COMPLETE_ARGS,
    CRITICAL,
    ECHO,
    ECHO_ARGS,
    GUARDED_ECHO,
    GUARDED_NOTE,
    HIGH,
    LOOSE_NOTE,
    NOTE,
    NOTE_ARGS,
    OTHER_STEP,
    OTHER_TASK_ID,
    UNCONSTRAINED_SCOPE,
    Harness,
    grant,
    harness,
    step_for,
)

ALLOWED, DENIED, REQUIRES_APPROVAL = PermissionOutcome


@pytest.fixture
def h() -> Harness:
    return harness()


def rule_of(decision: PermissionDecision) -> Rule:
    return Rule(str(decision.metadata["rule"]))


# --------------------------------------------------------------------------------------
# 1. Catalogue
# --------------------------------------------------------------------------------------


def test_an_unknown_capability_is_denied_with_a_reason(h: Harness) -> None:
    unknown = ECHO.model_copy(update={"id": CapabilityId("nobody.knows")})
    decision = h.guardian.decide(unknown, ECHO_ARGS)
    assert decision.outcome is DENIED
    assert rule_of(decision) is Rule.CATALOGUE
    assert "no rule" in decision.reason and "§33" in decision.reason


@pytest.mark.parametrize(
    "changes",
    [
        {"risk": RiskLevel.SAFE},
        {"scope": ("workspace",)},
        {"scoped_arguments": ()},
        {"requires_authorization": True},
        {"input_schema": {"type": "object"}},
        {"description": "the same, but not"},
    ],
    ids=["risk", "scope", "scoped_arguments", "requires_authorization", "schema", "description"],
)
def test_a_specification_that_differs_from_the_catalogue_is_denied(
    h: Harness, changes: dict[str, Any]
) -> None:
    tampered = NOTE.model_copy(update=changes)
    decision = h.guardian.decide(tampered, NOTE_ARGS)
    assert decision.outcome is DENIED
    assert rule_of(decision) is Rule.CATALOGUE
    assert "differs from the catalogue" in decision.reason
    assert decision.risk is NOTE.risk, "the registered risk, not the one the caller claims"


def test_the_identical_specification_gets_the_policy(h: Harness) -> None:
    assert h.guardian.decide(ECHO.model_copy(), ECHO_ARGS).outcome is ALLOWED


# --------------------------------------------------------------------------------------
# 2. Arguments
# --------------------------------------------------------------------------------------


def test_arguments_that_violate_the_schema_are_denied_before_anything_else(h: Harness) -> None:
    decision = h.guardian.decide(ECHO, {"message": 42})
    assert decision.outcome is DENIED
    assert rule_of(decision) is Rule.ARGUMENTS
    assert "$.message" in decision.reason


def test_the_reason_names_the_paths_and_never_the_values(h: Harness) -> None:
    """§57: the reason ends up in the audit log, so it carries no argument content."""
    decision = h.guardian.decide(ECHO, {"message": "ok", "secret": "SECRET-VALUE"})
    assert decision.outcome is DENIED
    assert rule_of(decision) is Rule.ARGUMENTS
    assert "SECRET-VALUE" not in decision.reason
    assert "'secret'" not in decision.reason
    assert decision.reason.endswith("at $")


def test_bad_arguments_beat_the_risk_row(h: Harness) -> None:
    decision = h.guardian.decide(HIGH, {"message": 42})
    assert rule_of(decision) is Rule.ARGUMENTS


# --------------------------------------------------------------------------------------
# 3. Step coherence (decision 15)
# --------------------------------------------------------------------------------------


def test_a_step_that_requires_other_capabilities_denies_this_one(h: Harness) -> None:
    step = step_for(NOTE.id)
    decision = h.guardian.decide(ECHO, ECHO_ARGS, task=TASK, step=step)
    assert decision.outcome is DENIED
    assert rule_of(decision) is Rule.STEP_MISMATCH
    assert str(step.id) in decision.reason and "core.echo" in decision.reason


def test_a_step_mismatch_beats_a_valid_authorization(h: Harness) -> None:
    decision = h.guardian.decide(
        COMPLETE, COMPLETE_ARGS, step=step_for(ECHO.id), authorization=grant(COMPLETE)
    )
    assert decision.outcome is DENIED
    assert rule_of(decision) is Rule.STEP_MISMATCH


@pytest.mark.parametrize(
    "step",
    [None, step_for(), step_for(ECHO.id), step_for(NOTE.id, ECHO.id, COMPLETE.id)],
    ids=["no-step", "undeclared", "declared", "declared-among-others"],
)
def test_no_step_or_a_step_that_declares_it_leaves_the_policy_to_decide(
    h: Harness, step: Any
) -> None:
    decision = h.guardian.decide(ECHO, ECHO_ARGS, task=TASK, step=step)
    assert decision.outcome is ALLOWED
    assert rule_of(decision) is Rule.ALLOW


def test_a_step_that_declares_the_capability_relaxes_nothing(h: Harness) -> None:
    assert h.guardian.decide(HIGH, ECHO_ARGS, step=step_for(HIGH.id)).outcome is DENIED
    without_grant = h.guardian.decide(COMPLETE, COMPLETE_ARGS, step=step_for(COMPLETE.id))
    assert without_grant.outcome is REQUIRES_APPROVAL


# --------------------------------------------------------------------------------------
# 4. The policy rows
# --------------------------------------------------------------------------------------


def test_safe_is_allowed_without_authorization(h: Harness) -> None:
    decision = h.guardian.decide(ECHO, ECHO_ARGS)
    assert decision.outcome is ALLOWED
    assert rule_of(decision) is Rule.ALLOW
    assert decision.authorization_id is None
    assert decision.risk is RiskLevel.SAFE
    assert decision.metadata == {"policy": POLICY_VERSION, "rule": "ALLOW", "targets": ()}
    assert POLICY_VERSION in decision.reason


def test_low_within_scope_is_allowed(h: Harness) -> None:
    decision = h.guardian.decide(NOTE, NOTE_ARGS)
    assert decision.outcome is ALLOWED
    assert rule_of(decision) is Rule.ALLOW_WITHIN_SCOPE
    assert decision.metadata["targets"] == ("workspace/notes/briefing.md",)


@pytest.mark.parametrize(
    "path",
    [
        "workspace/notes-old/x.md",
        "../workspace/notes/x.md",
        "/workspace/notes/x.md",
        "workspace/./notes/x.md",
        "other/x.md",
    ],
)
def test_low_outside_scope_is_denied_naming_the_scope(h: Harness, path: str) -> None:
    decision = h.guardian.decide(NOTE, {**NOTE_ARGS, "path": path})
    assert decision.outcome is DENIED
    assert rule_of(decision) is Rule.ALLOW_WITHIN_SCOPE
    assert "workspace/notes" in decision.reason and "not within scope" in decision.reason
    assert decision.metadata["targets"] == (path,)


@pytest.mark.parametrize(
    "arguments, targets",
    [({"body": "..."}, (None,)), ({"path": 7, "body": "..."}, (None,))],
    ids=["missing", "not-a-string"],
)
def test_a_scoped_argument_that_is_missing_or_not_a_string_is_outside(
    h: Harness, arguments: dict[str, Any], targets: tuple[Any, ...]
) -> None:
    decision = h.guardian.decide(LOOSE_NOTE, arguments)
    assert decision.outcome is DENIED
    assert rule_of(decision) is Rule.ALLOW_WITHIN_SCOPE
    assert decision.metadata["targets"] == targets


def test_a_scope_that_constrains_no_argument_is_denied(h: Harness) -> None:
    decision = h.guardian.decide(UNCONSTRAINED_SCOPE, ECHO_ARGS)
    assert decision.outcome is DENIED
    assert rule_of(decision) is Rule.ALLOW_WITHIN_SCOPE
    assert "workspace" in decision.reason


def test_medium_without_authorization_requires_approval(h: Harness) -> None:
    decision = h.guardian.decide(COMPLETE, COMPLETE_ARGS, task=TASK)
    assert decision.outcome is REQUIRES_APPROVAL
    assert rule_of(decision) is Rule.APPROVAL_UNLESS_AUTHORIZED
    assert "none was given" in decision.reason
    assert decision.expires_at is None


def test_medium_with_a_valid_authorization_is_allowed(h: Harness) -> None:
    authorization = grant(COMPLETE)
    decision = h.guardian.decide(COMPLETE, COMPLETE_ARGS, authorization=authorization)
    assert decision.outcome is ALLOWED
    assert rule_of(decision) is Rule.APPROVAL_UNLESS_AUTHORIZED
    assert decision.authorization_id == authorization.id
    assert str(authorization.id) in decision.reason


@pytest.mark.parametrize("spec", [HIGH, CRITICAL], ids=lambda s: s.risk.value)
def test_high_and_critical_are_denied_even_with_a_valid_authorization(
    h: Harness, spec: CapabilitySpec
) -> None:
    decision = h.guardian.decide(spec, ECHO_ARGS, authorization=grant(spec), step=step_for(spec.id))
    assert decision.outcome is DENIED
    assert rule_of(decision) is Rule.DENY
    assert spec.risk.value in decision.reason and POLICY_VERSION in decision.reason


def test_a_risk_level_without_a_policy_row_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    """The table is data; a level it does not know is a doubt, not a pass."""
    rows = {level: rule for level, rule in RISK_POLICY.items() if level is not RiskLevel.SAFE}
    without_safe = MappingProxyType(rows)
    monkeypatch.setattr(guardian_module, "RISK_POLICY", without_safe)
    decision = harness().guardian.decide(ECHO, ECHO_ARGS)
    assert decision.outcome is DENIED
    assert rule_of(decision) is Rule.DENY


def test_the_policy_table_covers_every_risk_level() -> None:
    assert set(RISK_POLICY) == set(RiskLevel)
    assert RISK_POLICY[RiskLevel.HIGH] is RISK_POLICY[RiskLevel.CRITICAL] is Rule.DENY


# --------------------------------------------------------------------------------------
# Decision E: requires_authorization only tightens
# --------------------------------------------------------------------------------------


def test_a_safe_capability_that_requires_authorization_asks_for_it(h: Harness) -> None:
    decision = h.guardian.decide(GUARDED_ECHO, ECHO_ARGS)
    assert decision.outcome is REQUIRES_APPROVAL
    assert rule_of(decision) is Rule.AUTHORIZATION_REQUIRED


def test_a_safe_capability_that_requires_authorization_is_allowed_with_one(h: Harness) -> None:
    authorization = grant(GUARDED_ECHO)
    decision = h.guardian.decide(GUARDED_ECHO, ECHO_ARGS, authorization=authorization)
    assert decision.outcome is ALLOWED
    assert rule_of(decision) is Rule.AUTHORIZATION_REQUIRED
    assert decision.authorization_id == authorization.id


def test_a_step_that_requires_authorization_tightens_a_safe_capability(h: Harness) -> None:
    step = step_for(ECHO.id, requires_authorization=True)
    assert h.guardian.decide(ECHO, ECHO_ARGS, step=step).outcome is REQUIRES_APPROVAL
    with_grant = h.guardian.decide(ECHO, ECHO_ARGS, step=step, authorization=grant(ECHO))
    assert with_grant.outcome is ALLOWED


def test_a_denial_of_the_row_comes_before_the_question(h: Harness) -> None:
    """LOW, outside the scope, requiring an authorization nobody gave: DENIED, not "ask" — the
    user is never asked to approve what would be denied anyway."""
    decision = h.guardian.decide(GUARDED_NOTE, {**NOTE_ARGS, "path": "elsewhere/x.md"})
    assert decision.outcome is DENIED
    assert rule_of(decision) is Rule.ALLOW_WITHIN_SCOPE


# --------------------------------------------------------------------------------------
# 5. Authorizations: expired or exhausted ask, wrong ones deny
# --------------------------------------------------------------------------------------


def test_an_expired_authorization_requires_approval(h: Harness) -> None:
    expired = grant(COMPLETE, expires_at=h.now - timedelta(seconds=1))
    decision = h.guardian.decide(COMPLETE, COMPLETE_ARGS, authorization=expired)
    assert decision.outcome is REQUIRES_APPROVAL
    assert "expired" in decision.reason
    assert decision.authorization_id == expired.id, "echoed, even if not applied"


def test_expiry_is_closed_at_the_exact_instant(h: Harness) -> None:
    """ADR 0005 §2-bis: ``expires_at <= now`` is expired, also for the authorization."""
    at_now = grant(COMPLETE, expires_at=h.now)
    decision = h.guardian.decide(COMPLETE, COMPLETE_ARGS, authorization=at_now)
    assert decision.outcome is REQUIRES_APPROVAL
    just_after = grant(COMPLETE, expires_at=h.now + timedelta(microseconds=1))
    decision = h.guardian.decide(COMPLETE, COMPLETE_ARGS, authorization=just_after)
    assert decision.outcome is ALLOWED


@pytest.mark.parametrize(
    "max_uses, uses, outcome",
    [(1, 0, ALLOWED), (1, 1, REQUIRES_APPROVAL), (3, 2, ALLOWED), (3, 5, REQUIRES_APPROVAL)],
)
def test_an_exhausted_authorization_requires_approval(
    h: Harness, max_uses: int, uses: int, outcome: PermissionOutcome
) -> None:
    authorization = grant(COMPLETE, max_uses=max_uses)
    decision = h.guardian.decide(
        COMPLETE, COMPLETE_ARGS, authorization=authorization, authorization_uses=uses
    )
    assert decision.outcome is outcome
    if outcome is REQUIRES_APPROVAL:
        assert f"used {uses} of {max_uses}" in decision.reason


def test_without_a_use_limit_the_count_never_exhausts(h: Harness) -> None:
    decision = h.guardian.decide(
        COMPLETE, COMPLETE_ARGS, authorization=grant(COMPLETE), authorization_uses=10**6
    )
    assert decision.outcome is ALLOWED


def test_a_negative_use_count_is_a_doubt(h: Harness) -> None:
    decision = h.guardian.decide(
        COMPLETE, COMPLETE_ARGS, authorization=grant(COMPLETE), authorization_uses=-1
    )
    assert decision.outcome is DENIED
    assert "cannot be true" in decision.reason


def test_an_authorization_for_another_capability_is_denied(h: Harness) -> None:
    decision = h.guardian.decide(COMPLETE, COMPLETE_ARGS, authorization=grant(ECHO))
    assert decision.outcome is DENIED
    assert rule_of(decision) is Rule.APPROVAL_UNLESS_AUTHORIZED
    assert "does not cover" in decision.reason and "core.echo" in decision.reason


def test_an_authorization_bound_to_a_task_needs_that_task(h: Harness) -> None:
    bound = grant(COMPLETE, task_id=TASK.id)
    other = TASK.model_copy(update={"id": OTHER_TASK_ID})

    def outcome(task: Any) -> PermissionOutcome:
        return h.guardian.decide(COMPLETE, COMPLETE_ARGS, task=task, authorization=bound).outcome

    assert outcome(TASK) is ALLOWED
    assert outcome(other) is DENIED
    assert outcome(None) is DENIED


def test_an_authorization_bound_to_a_step_needs_that_step(h: Harness) -> None:
    step = step_for(COMPLETE.id)
    bound = grant(COMPLETE, task_id=TASK.id, step_id=step.id)
    allowed = h.guardian.decide(COMPLETE, COMPLETE_ARGS, task=TASK, step=step, authorization=bound)
    assert allowed.outcome is ALLOWED
    other = OTHER_STEP.model_copy(update={"required_capabilities": (COMPLETE.id,)})
    denied = h.guardian.decide(COMPLETE, COMPLETE_ARGS, task=TASK, step=other, authorization=bound)
    assert denied.outcome is DENIED
    assert str(step.id) in denied.reason
    no_step = h.guardian.decide(COMPLETE, COMPLETE_ARGS, task=TASK, authorization=bound)
    assert no_step.outcome is DENIED


def test_an_authorization_whose_scope_does_not_cover_the_targets_is_denied(h: Harness) -> None:
    elsewhere = grant(GUARDED_NOTE, scope=("workspace/other",))
    decision = h.guardian.decide(GUARDED_NOTE, NOTE_ARGS, authorization=elsewhere)
    assert decision.outcome is DENIED
    assert "workspace/other" in decision.reason and "workspace/notes/briefing.md" in decision.reason
    unscoped = grant(GUARDED_NOTE, scope=())
    assert h.guardian.decide(GUARDED_NOTE, NOTE_ARGS, authorization=unscoped).outcome is DENIED
    covering = grant(GUARDED_NOTE)
    assert h.guardian.decide(GUARDED_NOTE, NOTE_ARGS, authorization=covering).outcome is ALLOWED


def test_an_authorization_with_a_scope_for_a_capability_without_targets_is_denied(
    h: Harness,
) -> None:
    """A scope on ``model.complete`` constrains nothing: a doubt, like on the capability."""
    scoped = grant(COMPLETE, scope=("workspace/notes",))
    assert h.guardian.decide(COMPLETE, COMPLETE_ARGS, authorization=scoped).outcome is DENIED


def test_a_wrong_authorization_that_also_expired_is_still_wrong(h: Harness) -> None:
    wrong_and_old = grant(ECHO, expires_at=h.now - timedelta(days=1))
    decision = h.guardian.decide(COMPLETE, COMPLETE_ARGS, authorization=wrong_and_old)
    assert decision.outcome is DENIED


# --------------------------------------------------------------------------------------
# Expiry of the decision (decision 9)
# --------------------------------------------------------------------------------------


def test_an_allowed_decision_expires_after_the_ttl(h: Harness) -> None:
    decision = h.guardian.decide(ECHO, ECHO_ARGS)
    assert decision.expires_at == h.now + DEFAULT_DECISION_TTL


def test_the_ttl_is_a_constructor_parameter() -> None:
    short = harness(ttl=timedelta(seconds=30))
    assert short.guardian.decide(ECHO, ECHO_ARGS).expires_at == short.now + timedelta(seconds=30)


@pytest.mark.parametrize("ttl", [timedelta(0), timedelta(seconds=-1)], ids=["zero", "negative"])
def test_a_non_positive_ttl_is_refused_at_construction(ttl: timedelta) -> None:
    with pytest.raises(ValueError, match="decision_ttl must be positive"):
        PermissionGuardian(
            FakeCapabilityRegistry(CATALOGUE),
            FakeClock(),
            FakeIdGenerator(),
            FakeAuditLog(),
            decision_ttl=ttl,
        )


def test_an_allowed_decision_never_outlives_its_authorization(h: Harness) -> None:
    soon = grant(COMPLETE, expires_at=h.now + timedelta(minutes=1))
    decision = h.guardian.decide(COMPLETE, COMPLETE_ARGS, authorization=soon)
    assert decision.outcome is ALLOWED
    assert decision.expires_at == soon.expires_at
    later = grant(COMPLETE, expires_at=h.now + timedelta(hours=1))
    assert h.guardian.decide(COMPLETE, COMPLETE_ARGS, authorization=later).expires_at == (
        h.now + DEFAULT_DECISION_TTL
    )
    forever = grant(COMPLETE)
    assert h.guardian.decide(COMPLETE, COMPLETE_ARGS, authorization=forever).expires_at == (
        h.now + DEFAULT_DECISION_TTL
    )


@pytest.mark.parametrize(
    "spec, arguments, outcome",
    [(HIGH, ECHO_ARGS, DENIED), (COMPLETE, COMPLETE_ARGS, REQUIRES_APPROVAL)],
    ids=["denied", "requires-approval"],
)
def test_only_allowed_decisions_expire(
    h: Harness, spec: CapabilitySpec, arguments: dict[str, Any], outcome: PermissionOutcome
) -> None:
    decision = h.guardian.decide(spec, arguments)
    assert decision.outcome is outcome
    assert decision.expires_at is None


# --------------------------------------------------------------------------------------
# Form of the decision (decision 10)
# --------------------------------------------------------------------------------------


def test_the_decision_takes_its_id_and_instant_from_the_ports(h: Harness) -> None:
    decision = h.guardian.decide(ECHO, ECHO_ARGS)
    assert decision.id == UUID("00000000-0000-4000-8000-000000000001")
    assert decision.created_at == h.now
    assert decision.capability_id == ECHO.id


def test_the_decision_echoes_its_context(h: Harness) -> None:
    step = step_for(COMPLETE.id)
    authorization = grant(COMPLETE, task_id=TASK.id, step_id=step.id)
    decision = h.guardian.decide(
        COMPLETE, COMPLETE_ARGS, task=TASK, step=step, authorization=authorization
    )
    assert (decision.task_id, decision.step_id) == (TASK.id, step.id)
    assert decision.authorization_id == authorization.id
    assert decision.approval_id is None


# --------------------------------------------------------------------------------------
# Fail-safe (decision 7)
# --------------------------------------------------------------------------------------


class _BrokenRegistry:
    def get(self, capability_id: CapabilityId) -> CapabilitySpec:
        raise RuntimeError("the catalogue is on fire")

    def specs(self) -> tuple[CapabilitySpec, ...]:
        return ()


def test_an_error_inside_the_evaluation_is_a_denial_not_an_exception() -> None:
    h = harness(registry=_BrokenRegistry())
    decision = h.guardian.decide(ECHO, ECHO_ARGS, task=TASK)
    assert decision.outcome is DENIED
    assert rule_of(decision) is Rule.INTERNAL_ERROR
    assert decision.reason.startswith("internal error")
    assert decision.metadata["error"] == "RuntimeError"
    assert "on fire" not in decision.reason, "the message could carry anything; the type cannot"
    assert decision.task_id == TASK.id and decision.created_at == h.now


class _BrokenClock:
    def now(self) -> datetime:
        raise OSError("no clock")


class _BrokenIds:
    def new_uuid(self) -> UUID:
        raise OSError("no entropy")


def test_a_clock_that_fails_produces_no_decision_at_all() -> None:
    guardian = PermissionGuardian(
        FakeCapabilityRegistry(CATALOGUE), _BrokenClock(), FakeIdGenerator(), FakeAuditLog()
    )
    with pytest.raises(OSError, match="no clock"):
        guardian.decide(ECHO, ECHO_ARGS)


def test_an_id_generator_that_fails_produces_no_decision_at_all() -> None:
    guardian = PermissionGuardian(
        FakeCapabilityRegistry(CATALOGUE), FakeClock(), _BrokenIds(), FakeAuditLog()
    )
    with pytest.raises(OSError, match="no entropy"):
        guardian.decide(ECHO, ECHO_ARGS)


def test_the_guardian_is_synchronous_and_touches_no_audit_in_decide(h: Harness) -> None:
    h.guardian.decide(ECHO, ECHO_ARGS)
    assert h.audit._events == ()  # noqa: SLF001 — the fake's state, read on purpose


def test_the_real_clock_and_an_aware_instant_agree() -> None:
    """Sanity: ``FakeClock`` hands out aware UTC instants, so the expiry arithmetic is aware."""
    assert harness().now.tzinfo is UTC


def test_step_ids_in_reasons_are_the_step_given(h: Harness) -> None:
    step = step_for(NOTE.id).model_copy(
        update={"id": StepId(UUID("00000000-0000-4000-8000-000000000042"))}
    )
    decision = h.guardian.decide(ECHO, ECHO_ARGS, step=step)
    assert "00000000-0000-4000-8000-000000000042" in decision.reason
