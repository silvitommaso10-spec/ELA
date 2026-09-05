"""``authorization_from_approval``: a "yes" becomes a grant only in its own context (§30, ADR 0012).

Every grant produced here is single use and bound to the task, step and capability the approval
cites, with the approved targets as scope; every approval that cites something else, was not
granted, was not signed or came late produces an ``ApprovalMismatchError`` and nothing more.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest

from ela.domain import (
    ApprovalStatus,
    Authorization,
    AuthorizationId,
    CapabilitySpec,
    PermissionOutcome,
    StepId,
    Task,
    TaskStep,
)
from ela.permissions import (
    CHECKS,
    DEFAULT_AUTHORIZATION_TTL,
    MAX_AUTHORIZATION_TTL,
    ApprovalMismatchError,
    Check,
    PermissionsError,
    Rule,
    authorization_from_approval,
)
from tests.domain.examples import (
    APPROVAL,
    LATER,
    MUCH_LATER,
    NOW,
    OTHER_STEP,
    OTHER_STEP_ID,
    TASK,
    TASK_STEP,
)
from tests.permissions.support import (
    COMPLETE,
    COMPLETE_ARGS,
    GUARDED_NOTE,
    NOTE,
    NOTE_ARGS,
    OTHER_TASK_ID,
    harness,
)

GRANT_ID = AuthorizationId(UUID("00000000-0000-4000-8000-000000000431"))
OTHER_TASK = TASK.model_copy(update={"id": OTHER_TASK_ID})
STEP_FOR_COMPLETE = TASK_STEP.model_copy(update={"required_capabilities": (COMPLETE.id,)})
APPROVAL_FOR_COMPLETE = APPROVAL.model_copy(update={"capability_id": COMPLETE.id, "targets": ()})
GUARDED_APPROVAL = APPROVAL.model_copy(update={"capability_id": GUARDED_NOTE.id})
GUARDED_STEP = TASK_STEP.model_copy(update={"required_capabilities": (GUARDED_NOTE.id,)})


def convert(
    approval: Any = APPROVAL,
    *,
    task: Task = TASK,
    step: TaskStep = TASK_STEP,
    capability: CapabilitySpec = NOTE,
    now: datetime = NOW,
    ttl: timedelta = DEFAULT_AUTHORIZATION_TTL,
) -> Authorization:
    return authorization_from_approval(
        approval,
        task=task,
        step=step,
        capability=capability,
        now=now,
        authorization_id=GRANT_ID,
        ttl=ttl,
    )


def mismatch(approval: Any = APPROVAL, **context: Any) -> ApprovalMismatchError:
    with pytest.raises(ApprovalMismatchError) as caught:
        convert(approval, **context)
    return caught.value


# --------------------------------------------------------------------------------------
# The grant
# --------------------------------------------------------------------------------------


def test_a_coherent_approval_becomes_a_single_use_grant_bound_to_its_context() -> None:
    grant = convert()
    assert grant.id == GRANT_ID
    assert grant.created_at == NOW
    assert grant.capability_id == NOTE.id
    assert grant.approval_id == APPROVAL.id
    assert grant.task_id == TASK.id
    assert grant.step_id == TASK_STEP.id
    assert grant.max_uses == 1
    assert grant.granted_by == APPROVAL.responded_by
    assert grant.expires_at == NOW + DEFAULT_AUTHORIZATION_TTL


def test_the_scope_is_the_approved_targets_not_the_folder() -> None:
    """Decision B: "yes to writing this note" authorises that note."""
    assert APPROVAL.targets == ("workspace/notes/briefing.md",)
    assert convert().scope == APPROVAL.targets
    assert convert().scope != NOTE.scope


def test_without_targets_the_scope_is_the_registered_scope() -> None:
    grant = convert(APPROVAL_FOR_COMPLETE, step=STEP_FOR_COMPLETE, capability=COMPLETE)
    assert grant.scope == COMPLETE.scope == ()
    note_approval = APPROVAL.model_copy(update={"targets": ()})
    assert convert(note_approval).scope == NOTE.scope == ("workspace/notes",)


def test_the_metadata_say_where_the_grant_comes_from_and_nothing_private() -> None:
    grant = convert()
    assert grant.metadata == {"origin": "approval", "decision_id": str(APPROVAL.decision_id)}
    unprompted = convert(APPROVAL.model_copy(update={"decision_id": None}))
    assert unprompted.metadata == {"origin": "approval", "decision_id": None}
    assert APPROVAL.prompt not in str(grant.model_dump())


def test_the_grant_satisfies_the_domain_invariant() -> None:
    """ADR 0012 §1: what this function builds is what the type admits."""
    grant = convert()
    assert Authorization.model_validate(grant.model_dump()) == grant


# --------------------------------------------------------------------------------------
# The TTL (decision C)
# --------------------------------------------------------------------------------------


def test_the_default_ttl_is_one_hour_and_the_maximum_a_day() -> None:
    assert timedelta(hours=1) == DEFAULT_AUTHORIZATION_TTL
    assert timedelta(hours=24) == MAX_AUTHORIZATION_TTL


def test_the_ttl_is_a_parameter_up_to_the_maximum() -> None:
    assert convert(ttl=timedelta(minutes=5)).expires_at == NOW + timedelta(minutes=5)
    assert convert(ttl=MAX_AUTHORIZATION_TTL).expires_at == NOW + MAX_AUTHORIZATION_TTL


@pytest.mark.parametrize(
    "ttl",
    [timedelta(0), timedelta(seconds=-1), MAX_AUTHORIZATION_TTL + timedelta(microseconds=1)],
    ids=["zero", "negative", "above-the-cap"],
)
def test_a_ttl_outside_the_bounds_is_a_configuration_error(ttl: timedelta) -> None:
    with pytest.raises(ValueError, match="ttl must be positive and at most"):
        convert(ttl=ttl)


# --------------------------------------------------------------------------------------
# What is refused (§30): the first check that fails wins
# --------------------------------------------------------------------------------------

_MISMATCHES: list[tuple[str, dict[str, Any], dict[str, Any], Check, str]] = [
    ("pending", {"status": ApprovalStatus.PENDING}, {}, Check.STATUS, "PENDING, not GRANTED"),
    ("rejected", {"status": ApprovalStatus.REJECTED}, {}, Check.STATUS, "REJECTED, not GRANTED"),
    ("expired", {"status": ApprovalStatus.EXPIRED}, {}, Check.STATUS, "EXPIRED, not GRANTED"),
    ("nobody-responded", {"responded_by": None}, {}, Check.RESPONDER, "who responded"),
    ("empty-responder", {"responded_by": ""}, {}, Check.RESPONDER, "who responded"),
    ("no-response-time", {"responded_at": None}, {}, Check.RESPONDER, "when it was answered"),
    ("answered-at-expiry", {"expires_at": LATER}, {}, Check.TIMELY, "after it expired"),
    ("answered-late", {"responded_at": MUCH_LATER}, {}, Check.TIMELY, "after it expired"),
    ("wrong-task", {}, {"task": OTHER_TASK}, Check.TASK, f"about task {APPROVAL.task_id}"),
    ("wrong-step", {}, {"step": OTHER_STEP}, Check.STEP, f"about step {APPROVAL.step_id}"),
    (
        "wrong-capability",
        {},
        {"capability": COMPLETE, "step": STEP_FOR_COMPLETE},
        Check.CAPABILITY,
        f"about {APPROVAL.capability_id}, not {COMPLETE.id}",
    ),
    (
        "step-declares-other-capabilities",
        {},
        {"step": TASK_STEP.model_copy(update={"required_capabilities": (COMPLETE.id,)})},
        Check.STEP_COHERENCE,
        f"does not require {NOTE.id}",
    ),
    (
        "target-outside-the-scope",
        {"targets": ("elsewhere/notes/a.md",)},
        {},
        Check.TARGETS,
        "not within the scope",
    ),
    (
        "target-with-dot-dot",
        {"targets": ("workspace/notes/../secrets.md",)},
        {},
        Check.TARGETS,
        "not within the scope",
    ),
    ("absolute-target", {"targets": ("/workspace/notes/a.md",)}, {}, Check.TARGETS, "not within"),
    (
        "one-target-out-of-two-outside",
        {"targets": ("workspace/notes/a.md", "workspace/other.md")},
        {},
        Check.TARGETS,
        "not within the scope",
    ),
    (
        "targets-on-a-capability-without-targets",
        {"capability_id": COMPLETE.id, "targets": ("workspace/notes/a.md",)},
        {"capability": COMPLETE, "step": STEP_FOR_COMPLETE},
        Check.TARGETS,
        "has no scoped arguments",
    ),
]


@pytest.mark.parametrize(
    ("approval_changes", "context", "check", "message"),
    [m[1:] for m in _MISMATCHES],
    ids=[m[0] for m in _MISMATCHES],
)
def test_an_out_of_context_yes_produces_no_grant(
    approval_changes: dict[str, Any], context: dict[str, Any], check: Check, message: str
) -> None:
    error = mismatch(APPROVAL.model_copy(update=approval_changes), **context)
    assert error.check is check
    assert message in error.reason
    assert error.approval_id == APPROVAL.id
    assert str(APPROVAL.id) in str(error)
    assert isinstance(error, PermissionsError)


def test_an_approval_that_cites_the_wrong_task_generates_nothing_even_if_everything_else_fits() -> (
    None
):
    """The milestone's headline test (§30): right step, right capability, wrong task."""
    wrong_task = APPROVAL.model_copy(update={"task_id": OTHER_TASK_ID})
    error = mismatch(wrong_task)
    assert error.check is Check.TASK
    assert str(OTHER_TASK_ID) in error.reason
    assert str(TASK.id) in error.reason


def test_the_first_failing_check_wins_in_the_documented_order() -> None:
    everything_wrong = APPROVAL.model_copy(
        update={
            "status": ApprovalStatus.PENDING,
            "responded_by": None,
            "task_id": OTHER_TASK_ID,
            "targets": ("/etc/passwd",),
        }
    )
    assert mismatch(everything_wrong).check is Check.STATUS
    granted = everything_wrong.model_copy(update={"status": ApprovalStatus.GRANTED})
    assert mismatch(granted).check is Check.RESPONDER
    signed = granted.model_copy(update={"responded_by": "tommaso"})
    assert mismatch(signed).check is Check.TASK
    right_task = signed.model_copy(update={"task_id": TASK.id})
    assert mismatch(right_task).check is Check.TARGETS


def test_the_checks_run_in_the_order_of_the_table() -> None:
    assert CHECKS == (
        Check.STATUS,
        Check.RESPONDER,
        Check.TIMELY,
        Check.TASK,
        Check.STEP,
        Check.CAPABILITY,
        Check.STEP_COHERENCE,
        Check.TARGETS,
    )
    assert set(CHECKS) == set(Check)


def test_a_step_that_declares_nothing_does_not_constrain() -> None:
    """ADR 0011 §15 read the same way here: an empty tuple is "not declared"."""
    undeclared = TASK_STEP.model_copy(update={"required_capabilities": ()})
    assert convert(step=undeclared).step_id == TASK_STEP.id


def test_an_approval_without_expiry_is_never_late() -> None:
    assert convert(APPROVAL.model_copy(update={"expires_at": None})).max_uses == 1


def test_the_instant_before_expiry_is_in_time() -> None:
    just_in_time = APPROVAL.model_copy(
        update={"responded_at": MUCH_LATER - timedelta(microseconds=1), "expires_at": MUCH_LATER}
    )
    assert convert(just_in_time).approval_id == APPROVAL.id


def test_now_is_the_callers_fact() -> None:
    later = datetime(2027, 1, 1, tzinfo=UTC)
    grant = convert(now=later)
    assert grant.created_at == later
    assert grant.expires_at == later + DEFAULT_AUTHORIZATION_TTL


# --------------------------------------------------------------------------------------
# With the Guardian (ADR 0011): the grant covers exactly what was approved
# --------------------------------------------------------------------------------------


def test_the_guardian_allows_the_approved_call_once() -> None:
    h = harness()
    grant = convert(GUARDED_APPROVAL, step=GUARDED_STEP, capability=GUARDED_NOTE, now=h.now)
    first = h.guardian.decide(
        GUARDED_NOTE, NOTE_ARGS, task=TASK, step=GUARDED_STEP, authorization=grant
    )
    assert first.outcome is PermissionOutcome.ALLOWED
    assert first.authorization_id == grant.id
    assert first.expires_at is not None and first.expires_at <= grant.expires_at
    second = h.guardian.decide(
        GUARDED_NOTE,
        NOTE_ARGS,
        task=TASK,
        step=GUARDED_STEP,
        authorization=grant,
        authorization_uses=1,
    )
    assert second.outcome is PermissionOutcome.REQUIRES_APPROVAL
    assert second.metadata["rule"] == Rule.AUTHORIZATION_REQUIRED


def test_the_guardian_denies_a_call_whose_arguments_are_not_the_approved_targets() -> None:
    """Review of decision B: the same folder is not the same note."""
    h = harness()
    grant = convert(GUARDED_APPROVAL, step=GUARDED_STEP, capability=GUARDED_NOTE, now=h.now)
    other_note = {**NOTE_ARGS, "path": "workspace/notes/other.md"}
    decision = h.guardian.decide(
        GUARDED_NOTE, other_note, task=TASK, step=GUARDED_STEP, authorization=grant
    )
    assert decision.outcome is PermissionOutcome.DENIED
    assert decision.metadata["rule"] == Rule.AUTHORIZATION_MISMATCH


def test_the_guardian_denies_the_grant_in_another_task_or_step() -> None:
    h = harness()
    grant = convert(GUARDED_APPROVAL, step=GUARDED_STEP, capability=GUARDED_NOTE, now=h.now)
    other_task = h.guardian.decide(
        GUARDED_NOTE, NOTE_ARGS, task=OTHER_TASK, step=GUARDED_STEP, authorization=grant
    )
    other_step = GUARDED_STEP.model_copy(update={"id": StepId(OTHER_STEP_ID)})
    in_other_step = h.guardian.decide(
        GUARDED_NOTE, NOTE_ARGS, task=TASK, step=other_step, authorization=grant
    )
    for decision in (other_task, in_other_step):
        assert decision.outcome is PermissionOutcome.DENIED
        assert decision.metadata["rule"] == Rule.AUTHORIZATION_MISMATCH


def test_a_medium_capability_is_allowed_with_the_grant_of_its_approval() -> None:
    h = harness()
    grant = convert(APPROVAL_FOR_COMPLETE, step=STEP_FOR_COMPLETE, capability=COMPLETE, now=h.now)
    decision = h.guardian.decide(
        COMPLETE, COMPLETE_ARGS, task=TASK, step=STEP_FOR_COMPLETE, authorization=grant
    )
    assert decision.outcome is PermissionOutcome.ALLOWED
    assert decision.authorization_id == grant.id
