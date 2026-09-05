"""How an :class:`~ela.domain.Approval` becomes an :class:`~ela.domain.Authorization` (§30).

§30: a "yes" out of context authorises nothing. The approval the user answered cites a task, a
step, a capability and the targets it was asked about; the executor (M5) brings the task, the
step and the registered capability it is about to run; this module checks that they are the same
ones — in the order of :data:`CHECKS`, documented in ADR 0012 §2 — and only then builds the grant:
single use, bound to that task and step, with the approved targets as scope, expiring after
``ttl``. Any mismatch is an :class:`~ela.permissions.errors.ApprovalMismatchError` and no grant.

Pure: no clock, no ids, no store. ``now`` and ``authorization_id`` are the caller's facts, as
``authorization_uses`` is for the Guardian (ADR 0011 §5), so every branch here is a function the
tests can exhaust. Whoever calls this saves the grant and writes ``AUTHORIZATION_GRANTED``
(ADR 0012 §6); outside this package nobody builds an ``Authorization`` at all (rule 15).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final

from ela.domain import (
    Approval,
    ApprovalStatus,
    Authorization,
    AuthorizationId,
    CapabilitySpec,
    Task,
    TaskStep,
)
from ela.permissions.errors import ApprovalMismatchError
from ela.permissions.scope import scope_covers

__all__ = [
    "CHECKS",
    "DEFAULT_AUTHORIZATION_TTL",
    "MAX_AUTHORIZATION_TTL",
    "Check",
    "authorization_from_approval",
]

DEFAULT_AUTHORIZATION_TTL: Final = timedelta(hours=1)
"""How long a grant born from an approval stays usable (ADR 0012 §2, decision C).

It serves the step that asked for it: an hour covers a long queue without leaving a bearer title
open for days. A setting with this default in M8.1, capped by :data:`MAX_AUTHORIZATION_TTL`.
"""
MAX_AUTHORIZATION_TTL: Final = timedelta(hours=24)
"""The longest ``ttl`` this function accepts (decision C): above it is a configuration error."""


class Check(StrEnum):
    """The checks an approval must pass, in the order they run (ADR 0012 §2)."""

    STATUS = "STATUS"
    """The approval is GRANTED: PENDING, REJECTED and EXPIRED authorise nothing."""
    RESPONDER = "RESPONDER"
    """Someone signed it: ``responded_by`` and ``responded_at`` are present."""
    TIMELY = "TIMELY"
    """The answer came before the request expired (closed bound: at the instant is late)."""
    TASK = "TASK"
    """It cites the task about to run."""
    STEP = "STEP"
    """It cites the step about to run."""
    CAPABILITY = "CAPABILITY"
    """It cites the capability about to run."""
    STEP_COHERENCE = "STEP_COHERENCE"
    """The step declares that capability, or declares none (ADR 0011 §15: tightens only)."""
    TARGETS = "TARGETS"
    """Its targets are inside the registered scope, on a capability that has targets."""


Checker = Callable[[Approval, Task, TaskStep, CapabilitySpec], str | None]
"""Why the approval fails this check, or ``None`` if it passes."""


def _status(approval: Approval, task: Task, step: TaskStep, spec: CapabilitySpec) -> str | None:
    if approval.status is not ApprovalStatus.GRANTED:
        return f"the approval is {approval.status.value}, not GRANTED"
    return None


def _responder(approval: Approval, task: Task, step: TaskStep, spec: CapabilitySpec) -> str | None:
    if not approval.responded_by:
        return "the approval does not say who responded"
    if approval.responded_at is None:
        return "the approval does not say when it was answered"
    return None


def _timely(approval: Approval, task: Task, step: TaskStep, spec: CapabilitySpec) -> str | None:
    assert approval.responded_at is not None  # RESPONDER ran first
    if approval.expires_at is not None and approval.responded_at >= approval.expires_at:
        return (
            f"the approval was answered at {approval.responded_at.isoformat()}, after it expired "
            f"at {approval.expires_at.isoformat()}"
        )
    return None


def _task(approval: Approval, task: Task, step: TaskStep, spec: CapabilitySpec) -> str | None:
    if approval.task_id != task.id:
        return f"the approval is about task {approval.task_id}, not {task.id}"
    return None


def _step(approval: Approval, task: Task, step: TaskStep, spec: CapabilitySpec) -> str | None:
    if approval.step_id != step.id:
        return f"the approval is about step {approval.step_id}, not {step.id}"
    return None


def _capability(approval: Approval, task: Task, step: TaskStep, spec: CapabilitySpec) -> str | None:
    if approval.capability_id != spec.id:
        return f"the approval is about {approval.capability_id}, not {spec.id}"
    return None


def _step_coherence(
    approval: Approval, task: Task, step: TaskStep, spec: CapabilitySpec
) -> str | None:
    if step.required_capabilities and spec.id not in step.required_capabilities:
        return f"step {step.id} does not require {spec.id}"
    return None


def _targets(approval: Approval, task: Task, step: TaskStep, spec: CapabilitySpec) -> str | None:
    if not approval.targets:
        return None
    if not spec.scoped_arguments:
        return f"the approval names targets but {spec.id} has no scoped arguments"
    if not scope_covers(spec.scope, approval.targets):
        return (
            f"targets {list(approval.targets)} of the approval are not within the scope "
            f"{list(spec.scope)} of {spec.id}"
        )
    return None


_CHECKERS: Final[dict[Check, Checker]] = {
    Check.STATUS: _status,
    Check.RESPONDER: _responder,
    Check.TIMELY: _timely,
    Check.TASK: _task,
    Check.STEP: _step,
    Check.CAPABILITY: _capability,
    Check.STEP_COHERENCE: _step_coherence,
    Check.TARGETS: _targets,
}

CHECKS: Final[tuple[Check, ...]] = tuple(_CHECKERS)
"""The order the checks run in; the first that fails wins (ADR 0012 §2)."""


def authorization_from_approval(
    approval: Approval,
    *,
    task: Task,
    step: TaskStep,
    capability: CapabilitySpec,
    now: datetime,
    authorization_id: AuthorizationId,
    ttl: timedelta = DEFAULT_AUTHORIZATION_TTL,
) -> Authorization:
    """The single-use grant ``approval`` authorises for this task, step and capability (§30).

    ``capability`` is the *registered* specification (the Guardian checks the catalogue again at
    decision time). Raises :class:`~ela.permissions.errors.ApprovalMismatchError` on the first
    check of :data:`CHECKS` that fails, ``ValueError`` for a ``ttl`` outside
    ``(0, MAX_AUTHORIZATION_TTL]`` — a configuration error, not a context one.
    """
    if not timedelta(0) < ttl <= MAX_AUTHORIZATION_TTL:
        raise ValueError(f"ttl must be positive and at most {MAX_AUTHORIZATION_TTL}, not {ttl}")
    for check in CHECKS:
        reason = _CHECKERS[check](approval, task, step, capability)
        if reason is not None:
            raise ApprovalMismatchError(approval.id, check, reason)
    assert approval.responded_by is not None  # RESPONDER passed
    return Authorization(
        id=authorization_id,
        created_at=now,
        capability_id=capability.id,
        scope=approval.targets or capability.scope,
        granted_by=approval.responded_by,
        approval_id=approval.id,
        task_id=task.id,
        step_id=step.id,
        expires_at=now + ttl,
        max_uses=1,
        metadata={
            "origin": "approval",
            "decision_id": None if approval.decision_id is None else str(approval.decision_id),
        },
    )
