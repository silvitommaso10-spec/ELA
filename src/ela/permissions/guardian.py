"""The Permission Guardian (spec §27, §29, §32, §33, §47; ADR 0011, M4.2).

"ELA decide cosa sarebbe utile fare, il Guardian decide se ELA è autorizzata a farlo" (§47).
:class:`PermissionGuardian` implements :class:`~ela.ports.PermissionGuardianPort`: ``decide`` is
a synchronous, pure function from a capability specification, a call's arguments and its
context to a :class:`~ela.domain.PermissionDecision`; ``authorize`` is the audited entry point
the executor calls (M5) — it decides and writes one ``PERMISSION_DECIDED`` event.

The Guardian owns no tool, no store and no provider (§27, ADR 0005 §4): it receives the
catalogue it trusts, a clock, an id source and the audit log, and the caller hands it the
authorization that would cover the call together with how many times it has been used.

Order of the checks, the first that denies wins (ADR 0011 §3):

1. **Catalogue.** The specification must be registered and identical to the registered one;
   otherwise nobody could tell a ``model.complete`` with ``risk=SAFE`` from the real thing.
2. **Arguments.** Valid against the *registered* schema (``validate_arguments``, M4.1).
3. **Step.** A step that declares its capabilities and does not name this one is a deviation
   from the approved plan.
4. **Policy row** (:data:`RISK_POLICY`): HIGH and CRITICAL are denied; LOW needs every target
   inside the capability's scope.
5. **Authorization**, when MEDIUM or when the specification or the step requires one: a valid
   grant allows, a missing, expired or exhausted one asks for approval, a grant that does not
   cover the call is a doubt and denies.

Whatever goes wrong inside the evaluation is a ``DENIED`` decision, never an exception (§33):
the only errors that escape are a clock or an id generator that cannot even produce a denial.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from ela.domain import (
    Actor,
    ActorKind,
    AuditEvent,
    AuditEventId,
    AuditEventType,
    Authorization,
    CapabilitySpec,
    DecisionId,
    JsonMapping,
    JsonValue,
    PermissionDecision,
    PermissionOutcome,
    RiskLevel,
    Task,
    TaskStep,
)
from ela.permissions.capabilities import validate_arguments
from ela.permissions.errors import InvalidArgumentsError
from ela.permissions.scope import scope_covers, targets_of
from ela.ports import AuditLog, CapabilityRegistryPort, Clock, IdGenerator, NotFoundError

__all__ = [
    "DEFAULT_DECISION_TTL",
    "GUARDIAN_ACTOR",
    "POLICY_VERSION",
    "RISK_POLICY",
    "PermissionGuardian",
    "Rule",
]

POLICY_VERSION: Final = "v0.1"
"""Which policy produced a decision; recorded in every decision and every audit event."""

DEFAULT_DECISION_TTL: Final = timedelta(minutes=5)
"""How long an ``ALLOWED`` decision stays usable (ADR 0011 §9).

Long enough for the decision to travel from the Core to a node (§56), short enough that a
decision kept aside cannot be replayed once its authorization is gone.
"""

GUARDIAN_ACTOR: Final = Actor(kind=ActorKind.SYSTEM, id="permission-guardian")
"""Who signs ``PERMISSION_DECIDED``: the Guardian acts on its own, nobody asked it to decide."""


class Rule(StrEnum):
    """Which check settled a decision; ``metadata["rule"]`` of every decision (ADR 0011 §3).

    The first four are the rows of :data:`RISK_POLICY`, one per risk level; the others are the
    checks that run before the row, or the fail-safe.
    """

    ALLOW = "ALLOW"
    ALLOW_WITHIN_SCOPE = "ALLOW_WITHIN_SCOPE"
    APPROVAL_UNLESS_AUTHORIZED = "APPROVAL_UNLESS_AUTHORIZED"
    DENY = "DENY"
    CATALOGUE = "CATALOGUE"
    ARGUMENTS = "ARGUMENTS"
    STEP_MISMATCH = "STEP_MISMATCH"
    AUTHORIZATION_REQUIRED = "AUTHORIZATION_REQUIRED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


RISK_POLICY: Final[Mapping[RiskLevel, Rule]] = MappingProxyType(
    {
        RiskLevel.SAFE: Rule.ALLOW,
        RiskLevel.LOW: Rule.ALLOW_WITHIN_SCOPE,
        RiskLevel.MEDIUM: Rule.APPROVAL_UNLESS_AUTHORIZED,
        RiskLevel.HIGH: Rule.DENY,
        RiskLevel.CRITICAL: Rule.DENY,
    }
)
"""Policy v0.1 by risk level (§29). Data, compared with the table of ADR 0011 by the tests; a
level missing from it is denied."""


@dataclass(frozen=True, slots=True)
class _Verdict:
    """What the evaluation concluded, before it becomes a :class:`PermissionDecision`."""

    outcome: PermissionOutcome
    rule: Rule
    reason: str
    risk: RiskLevel
    targets: tuple[object, ...] = ()
    applied_authorization: Authorization | None = None
    error: str | None = None


class _AuthorizationStatus(StrEnum):
    VALID = "VALID"
    EXPIRED = "EXPIRED"
    EXHAUSTED = "EXHAUSTED"
    MISMATCH = "MISMATCH"


class PermissionGuardian:
    """The Guardian of v0.1: catalogue, policy by risk, scope, authorizations, audit (ADR 0011)."""

    def __init__(
        self,
        registry: CapabilityRegistryPort,
        clock: Clock,
        ids: IdGenerator,
        audit: AuditLog,
        *,
        decision_ttl: timedelta = DEFAULT_DECISION_TTL,
    ) -> None:
        if decision_ttl <= timedelta(0):
            raise ValueError(f"decision_ttl must be positive, not {decision_ttl}")
        self._registry = registry
        self._clock = clock
        self._ids = ids
        self._audit = audit
        self._decision_ttl = decision_ttl

    # ----------------------------------------------------------------------------------
    # The port: decide
    # ----------------------------------------------------------------------------------

    def decide(
        self,
        capability: CapabilitySpec,
        arguments: JsonMapping,
        *,
        task: Task | None = None,
        step: TaskStep | None = None,
        authorization: Authorization | None = None,
        authorization_uses: int = 0,
    ) -> PermissionDecision:
        """Decide about one call; never raises for anything that happens inside the evaluation.

        The clock and the id generator are read *before* the evaluation: if they fail there is
        no decision at all, which is still "do not act". Everything after that — a registry that
        raises, malformed input, a bug — becomes ``DENIED`` with the exception's type as reason.
        """
        now = self._clock.now()
        decision_id = DecisionId(self._ids.new_uuid())
        try:
            verdict = self._evaluate(
                capability, arguments, task, step, authorization, authorization_uses, now
            )
        except Exception as error:  # the fail-safe of §33: doubt is DENIED, never an exception
            verdict = _Verdict(
                PermissionOutcome.DENIED,
                Rule.INTERNAL_ERROR,
                f"internal error: {type(error).__name__}",
                capability.risk,
                error=type(error).__name__,
            )
        metadata: dict[str, JsonValue] = {
            "policy": POLICY_VERSION,
            "rule": verdict.rule.value,
            "targets": _json_targets(verdict.targets),
        }
        if verdict.error is not None:
            metadata["error"] = verdict.error
        return PermissionDecision(
            id=decision_id,
            created_at=now,
            capability_id=capability.id,
            outcome=verdict.outcome,
            risk=verdict.risk,
            reason=verdict.reason,
            task_id=None if task is None else task.id,
            step_id=None if step is None else step.id,
            authorization_id=None if authorization is None else authorization.id,
            expires_at=self._expiry(verdict, now),
            metadata=metadata,
        )

    def _expiry(self, verdict: _Verdict, now: datetime) -> datetime | None:
        """``ALLOWED`` expires after the TTL, and no later than the authorization it rests on."""
        if verdict.outcome is not PermissionOutcome.ALLOWED:
            return None
        expires_at = now + self._decision_ttl
        applied = verdict.applied_authorization
        if applied is not None and applied.expires_at is not None:
            expires_at = min(expires_at, applied.expires_at)
        return expires_at

    def _evaluate(
        self,
        capability: CapabilitySpec,
        arguments: JsonMapping,
        task: Task | None,
        step: TaskStep | None,
        authorization: Authorization | None,
        authorization_uses: int,
        now: datetime,
    ) -> _Verdict:
        # 1. Catalogue: the specification must be the registered one (ADR 0011 §2).
        try:
            registered = self._registry.get(capability.id)
        except NotFoundError:
            return _Verdict(
                PermissionOutcome.DENIED,
                Rule.CATALOGUE,
                f"no rule for {capability.id}: not in the catalogue, denied by default (§33)",
                capability.risk,
            )
        if registered != capability:
            return _Verdict(
                PermissionOutcome.DENIED,
                Rule.CATALOGUE,
                f"specification of {capability.id} differs from the catalogue",
                registered.risk,
            )
        risk = registered.risk

        # 2. Arguments: valid against the registered schema (ADR 0010 §4).
        try:
            validate_arguments(registered, arguments)
        except InvalidArgumentsError as error:
            paths = ", ".join(violation.partition(": ")[0] for violation in error.errors)
            return _Verdict(
                PermissionOutcome.DENIED,
                Rule.ARGUMENTS,
                f"arguments of {capability.id} violate the registered schema at {paths}",
                risk,
            )
        targets = targets_of(registered, arguments)

        # 3. Step: a plan that declared its capabilities is not left silently (ADR 0011 §15).
        if (
            step is not None
            and step.required_capabilities
            and registered.id not in step.required_capabilities
        ):
            return _Verdict(
                PermissionOutcome.DENIED,
                Rule.STEP_MISMATCH,
                f"step {step.id} does not require {capability.id}",
                risk,
                targets,
            )

        # 4. The policy row (ADR 0011 §3): the denials of the table come before any question.
        rule = RISK_POLICY.get(risk)
        if rule is None or rule is Rule.DENY:
            return _Verdict(
                PermissionOutcome.DENIED,
                Rule.DENY,
                f"risk {risk.value} is not allowed by policy {POLICY_VERSION} (§29)",
                risk,
                targets,
            )
        if rule is Rule.ALLOW_WITHIN_SCOPE and not scope_covers(registered.scope, targets):
            return _Verdict(
                PermissionOutcome.DENIED,
                rule,
                f"targets {_describe(targets)} of {capability.id} are not within scope "
                f"{list(registered.scope)}",
                risk,
                targets,
            )

        # 5. Authorization: MEDIUM always, SAFE/LOW when something requires it (decision E).
        required = registered.requires_authorization or (
            step is not None and step.requires_authorization
        )
        if rule is not Rule.APPROVAL_UNLESS_AUTHORIZED and not required:
            return _Verdict(
                PermissionOutcome.ALLOWED,
                rule,
                f"{capability.id} is {risk.value}: allowed by policy {POLICY_VERSION}",
                risk,
                targets,
            )
        settled_by = (
            rule if rule is Rule.APPROVAL_UNLESS_AUTHORIZED else Rule.AUTHORIZATION_REQUIRED
        )
        if authorization is None:
            return _Verdict(
                PermissionOutcome.REQUIRES_APPROVAL,
                settled_by,
                f"{capability.id} requires an authorization: none was given",
                risk,
                targets,
            )
        status, detail = _authorization_status(
            authorization, registered, task, step, targets, authorization_uses, now
        )
        if status is _AuthorizationStatus.MISMATCH:
            return _Verdict(
                PermissionOutcome.DENIED,
                settled_by,
                f"authorization does not cover this call of {capability.id}: {detail}",
                risk,
                targets,
            )
        if status is not _AuthorizationStatus.VALID:
            return _Verdict(
                PermissionOutcome.REQUIRES_APPROVAL,
                settled_by,
                f"{capability.id} requires an authorization: {detail}",
                risk,
                targets,
            )
        return _Verdict(
            PermissionOutcome.ALLOWED,
            settled_by,
            f"{capability.id} is covered by authorization {authorization.id}",
            risk,
            targets,
            applied_authorization=authorization,
        )

    # ----------------------------------------------------------------------------------
    # The audited entry point: authorize
    # ----------------------------------------------------------------------------------

    async def authorize(
        self,
        capability: CapabilitySpec,
        arguments: JsonMapping,
        *,
        task: Task | None = None,
        step: TaskStep | None = None,
        authorization: Authorization | None = None,
        authorization_uses: int = 0,
    ) -> PermissionDecision:
        """Decide and record the decision as ``PERMISSION_DECIDED`` (§32; ADR 0011 §8).

        The arguments never enter the payload — they can carry the user's content (§57) — the
        targets do. If the audit log refuses the event the exception escapes and the decision is
        not returned: a decision that was not recorded does not exist.
        """
        decision = self.decide(
            capability,
            arguments,
            task=task,
            step=step,
            authorization=authorization,
            authorization_uses=authorization_uses,
        )
        targets = decision.metadata["targets"]
        payload: dict[str, JsonValue] = {
            "outcome": decision.outcome.value,
            "risk": decision.risk.value,
            "policy": decision.metadata["policy"],
            "rule": decision.metadata["rule"],
            "reason": decision.reason,
            "targets": list(targets) if isinstance(targets, tuple) else targets,
            "expires_at": None if decision.expires_at is None else decision.expires_at.isoformat(),
        }
        if "error" in decision.metadata:
            payload["error"] = decision.metadata["error"]
        await self._audit.append(
            AuditEvent(
                id=AuditEventId(self._ids.new_uuid()),
                created_at=decision.created_at,
                event_type=AuditEventType.PERMISSION_DECIDED,
                actor=GUARDIAN_ACTOR,
                summary=(
                    f"decide: {decision.outcome.value} {decision.capability_id} "
                    f"({decision.risk.value}): {decision.reason}"
                ),
                task_id=decision.task_id,
                step_id=decision.step_id,
                capability_id=decision.capability_id,
                decision_id=decision.id,
                authorization_id=decision.authorization_id,
                payload=payload,
            )
        )
        return decision


def _authorization_status(
    authorization: Authorization,
    spec: CapabilitySpec,
    task: Task | None,
    step: TaskStep | None,
    targets: tuple[object, ...],
    uses: int,
    now: datetime,
) -> tuple[_AuthorizationStatus, str]:
    """Whether ``authorization`` covers this call, and why not (ADR 0011 §5–§6).

    A grant for another capability, another task or step, or a scope that does not cover the
    targets is a *mismatch*: the wrong grant in the Guardian's hands, a doubt. An expired or
    exhausted grant is the normal "ask" of §62, like no grant at all. Mismatches are checked
    first: a wrong grant that also expired is still a wrong grant.
    """
    if authorization.capability_id != spec.id:
        return _AuthorizationStatus.MISMATCH, (
            f"authorization {authorization.id} is for {authorization.capability_id}"
        )
    if authorization.task_id is not None and (task is None or task.id != authorization.task_id):
        return _AuthorizationStatus.MISMATCH, (
            f"authorization {authorization.id} is bound to task {authorization.task_id}"
        )
    if authorization.step_id is not None and (step is None or step.id != authorization.step_id):
        return _AuthorizationStatus.MISMATCH, (
            f"authorization {authorization.id} is bound to step {authorization.step_id}"
        )
    if not scope_covers(authorization.scope, targets):
        return _AuthorizationStatus.MISMATCH, (
            f"scope {list(authorization.scope)} of authorization {authorization.id} does not "
            f"cover targets {_describe(targets)}"
        )
    if uses < 0:
        return _AuthorizationStatus.MISMATCH, f"a use count of {uses} cannot be true"
    if authorization.expires_at is not None and authorization.expires_at <= now:
        return _AuthorizationStatus.EXPIRED, (
            f"authorization {authorization.id} expired at {authorization.expires_at.isoformat()}"
        )
    if authorization.max_uses is not None and uses >= authorization.max_uses:
        return _AuthorizationStatus.EXHAUSTED, (
            f"authorization {authorization.id} was used {uses} of {authorization.max_uses} times"
        )
    return _AuthorizationStatus.VALID, "covered"


def _json_targets(targets: tuple[object, ...]) -> list[JsonValue]:
    """Targets as the audit and the decision keep them: strings, or ``null`` for what is not."""
    return [target if isinstance(target, str) else None for target in targets]


def _describe(targets: tuple[object, ...]) -> str:
    return repr(_json_targets(targets))
