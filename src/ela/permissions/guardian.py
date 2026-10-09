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
4. **Policy row** (:data:`RISK_POLICY`): CRITICAL is denied. Then the **scope**, on every row
   that has not denied: a capability that declares one has every target inside it, whatever its
   risk (M13.1 dec. C — until M13.1 only the LOW row checked it).
5. **Authorization.** A grant that does not *cover* the call (another capability, task or
   step, a scope that misses the targets, a use count that cannot be true, a standing policy for
   a row that asks at every use) denies, always: the Guardian never ignores a fact it was handed,
   and an incoherent caller is a doubt. Then, on a row that asks (:data:`ASKING_RULES`: MEDIUM,
   and HIGH at every use since M13.1) or when the specification or the step requires one: a
   covering, *usable* grant allows; none, or one expired or exhausted, asks for approval. A grant
   that is not needed is ignored if it merely is not usable — an unused grant is not an
   incoherence.

Whatever goes wrong inside the evaluation is a ``DENIED`` decision, never an exception (§33):
the only errors that escape are a clock or an id generator that cannot even produce a denial.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
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
    DeviceId,
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
from ela.permissions.policies import UNCOVERED, UNUSABLE, shortfall
from ela.permissions.rows import ASKING_RULES, RISK_POLICY, Rule, asks_at_every_use
from ela.permissions.scope import scope_covers, targets_of
from ela.ports import AuditLog, CapabilityRegistryPort, Clock, IdGenerator, NotFoundError

__all__ = [
    "ASKING_RULES",
    "asks_at_every_use",
    "DEFAULT_DECISION_TTL",
    "GUARDIAN_ACTOR",
    "MAX_DECISION_TTL",
    "POLICY_VERSION",
    "RISK_POLICY",
    "PermissionGuardian",
    "Rule",
]

POLICY_VERSION: Final = "v0.2"
"""Which policy produced a decision; recorded in every decision and every audit event.

**It was ``v0.1`` until M13.1**, and it moves with the table it names. The ``HIGH`` row stopped
being ``DENY`` and the scope stopped signing its denials with the row that allows: a decision
stamped ``v0.1`` that permits a HIGH would say the reader could look the table up in ADR 0011 and
find it, and they could not. A version that does not move when its table moves is the same kind of
lie as a code named after the wrong boundary (M13.1 dec. B).

Old rows in the audit keep saying ``v0.1``, and that is the point of stamping it.
"""

DEFAULT_DECISION_TTL: Final = timedelta(minutes=5)
"""How long an ``ALLOWED`` decision stays usable (ADR 0011 §9).

Long enough for the decision to travel from the Core to a node (§56), short enough that a
decision kept aside cannot be replayed once its authorization is gone.
"""

MAX_DECISION_TTL: Final = timedelta(hours=1)
"""The ceiling ``ELA_DECISION_TTL_SECONDS`` may not pass (M8.3, ADR 0025 §6).

A :class:`~ela.domain.PermissionDecision` is an answer given **in a context**, and a context that
lasts an hour is already longer than anything ELA is doing right now. Beyond that it stops being
a decision and becomes a permission — and permissions have an entity of their own, which is
:class:`~ela.domain.Authorization`, with its own grant, its own uses and its own audit. A TTL
without a ceiling would let the shorter-lived of the two quietly outlive the longer one.
"""

GUARDIAN_ACTOR: Final = Actor(kind=ActorKind.SYSTEM, id="permission-guardian")
"""Who signs ``PERMISSION_DECIDED``: the Guardian acts on its own, nobody asked it to decide."""


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
        # 4-bis. The scope, on every row that has not already denied (M13.1 dec. C): a capability
        #        that declares a boundary has it enforced whatever its risk, and a target outside
        #        is denied *before* any question — the order §3 of ADR 0011 keeps on purpose.
        if not scope_covers(registered.scope, targets):
            return _Verdict(
                PermissionOutcome.DENIED,
                Rule.SCOPE,
                f"targets {_describe(targets)} of {capability.id} are not within scope "
                f"{list(registered.scope)}",
                risk,
                targets,
            )
        # 4-ter. The step's narrowing (M14.3, ADR 0060): a step may tighten the scope and never
        #        widen it — the gestures of a guided session are held to the session's sites.
        if step is not None and step.within is not None and not scope_covers(step.within, targets):
            return _Verdict(
                PermissionOutcome.DENIED,
                Rule.SCOPE,
                f"targets {_describe(targets)} of {capability.id} are not within the step's "
                f"scope {list(step.within)}",
                risk,
                targets,
            )

        # 5a. A grant that does not cover the call is a caller's incoherence: DENIED, needed or
        #     not (ADR 0011 §6). The Guardian never ignores a fact it was handed.
        if authorization is not None:
            mismatch = _mismatch(
                authorization, registered, task, step, targets, authorization_uses, arguments, now
            )
            if mismatch is not None:
                return _Verdict(
                    PermissionOutcome.DENIED,
                    Rule.AUTHORIZATION_MISMATCH,
                    f"authorization does not cover this call of {capability.id}: {mismatch}",
                    risk,
                    targets,
                )

        # 5b. Is a grant needed? MEDIUM always; SAFE/LOW when the spec or the step requires it
        #     (decision E). If not, a covering grant that is not usable is simply not used.
        required = registered.requires_authorization or (
            step is not None and step.requires_authorization
        )
        if rule not in ASKING_RULES and not required:
            return _Verdict(
                PermissionOutcome.ALLOWED,
                rule,
                f"{capability.id} is {risk.value}: allowed by policy {POLICY_VERSION}",
                risk,
                targets,
            )
        settled_by = rule if rule in ASKING_RULES else Rule.AUTHORIZATION_REQUIRED
        if authorization is None:
            return _Verdict(
                PermissionOutcome.REQUIRES_APPROVAL,
                settled_by,
                f"{capability.id} requires an authorization: none was given",
                risk,
                targets,
            )
        unusable = _unusable(authorization, authorization_uses, now, registered, arguments)
        if unusable is not None:
            return _Verdict(
                PermissionOutcome.REQUIRES_APPROVAL,
                settled_by,
                f"{capability.id} requires an authorization: {unusable}",
                risk,
                targets,
            )
        # A grant without ``approval_id`` is a policy of §59, and the reason says so (M13.12,
        # decision 9): «covered by policy …» is what the audit and the summary of a task read.
        kind = "authorization" if authorization.approval_id is not None else "policy"
        return _Verdict(
            PermissionOutcome.ALLOWED,
            settled_by,
            f"{capability.id} is covered by {kind} {authorization.id}",
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
        device_id: DeviceId | None = None,
    ) -> PermissionDecision:
        """Decide and record the decision as ``PERMISSION_DECIDED`` (§32; ADR 0011 §8).

        The arguments never enter the payload — they can carry the user's content (§57) — the
        targets do. If the audit log refuses the event the exception escapes and the decision is
        not returned: a decision that was not recorded does not exist.

        ``device_id`` is the node the call is about (ADR 0019 §4): it reaches the audit event and
        **nothing else**. :meth:`decide` does not take it and no rule of ADR 0011 reads it — a
        node that could change an outcome would be a second permission axis, weaker than this one
        and outside it, which is the mirror of why risk stays out of the orchestrator's score
        (ADR 0017 §4).
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
                device_id=device_id,
                decision_id=decision.id,
                authorization_id=decision.authorization_id,
                payload=payload,
            )
        )
        return decision


def _mismatch(
    authorization: Authorization,
    spec: CapabilitySpec,
    task: Task | None,
    step: TaskStep | None,
    targets: tuple[object, ...],
    uses: int,
    arguments: JsonMapping,
    now: datetime,
) -> str | None:
    """Why ``authorization`` does not *cover* this call, or ``None`` if it does (ADR 0011 §6).

    A grant for another capability, another task or step, or a use count that cannot be true: the
    wrong grant in the Guardian's hands, a doubt whether or not a grant was needed. Checked before
    usability: a wrong grant that also expired is still a wrong grant.

    **For a grant born from a yes**, then, a scope that does not cover the targets. **For a policy
    of §59** (``approval_id`` ``None``), the row first — no policy reaches a row that asks at every
    use (ADR 0045 §3), and the reason names it — and then the half of the one predicate that says
    *covers* (M13.12, ADR 0062; decision 4): the terms, the sites, the limits one at a time, the
    arguments no policy covers. The other half, *usable*, is :func:`_unusable`'s.
    """
    if authorization.capability_id != spec.id:
        return f"authorization {authorization.id} is for {authorization.capability_id}"
    if authorization.task_id is not None and (task is None or task.id != authorization.task_id):
        return f"authorization {authorization.id} is bound to task {authorization.task_id}"
    if authorization.step_id is not None and (step is None or step.id != authorization.step_id):
        return f"authorization {authorization.id} is bound to step {authorization.step_id}"
    if uses < 0:
        return f"a use count of {uses} cannot be true"
    if authorization.approval_id is not None:
        if not scope_covers(authorization.scope, targets):
            return (
                f"scope {list(authorization.scope)} of authorization {authorization.id} does not "
                f"cover targets {_describe(targets)}"
            )
        return None
    if asks_at_every_use(spec.risk):
        return (
            f"authorization {authorization.id} is a standing policy (§59) and {spec.id} is "
            f"{spec.risk.value}: only a grant born from an approval covers it"
        )
    found = shortfall(authorization, spec, arguments, now=now, gaps=UNCOVERED)
    return None if found is None else found.reason


def _unusable(
    authorization: Authorization,
    uses: int,
    now: datetime,
    spec: CapabilitySpec,
    arguments: JsonMapping,
) -> str | None:
    """Why a covering ``authorization`` cannot be used now — revoked, expired (closed bound, ADR
    0005 §2-bis) or exhausted — or ``None`` if it can. Not an incoherence: the normal "ask" of §62.

    For a policy of §59 the revocation and the expiry are the other half of the one predicate
    (M13.12, decision 4): revoked means not usable, so the step asks and is never denied.
    """
    if authorization.approval_id is None:
        found = shortfall(authorization, spec, arguments, now=now, gaps=UNUSABLE)
        if found is not None:
            return found.reason
    elif authorization.expires_at is not None and authorization.expires_at <= now:
        return f"authorization {authorization.id} expired at {authorization.expires_at.isoformat()}"
    if authorization.max_uses is not None and uses >= authorization.max_uses:
        return f"authorization {authorization.id} was used {uses} of {authorization.max_uses} times"
    return None


def _json_targets(targets: tuple[object, ...]) -> list[JsonValue]:
    """Targets as the audit and the decision keep them: strings, or ``null`` for what is not."""
    return [target if isinstance(target, str) else None for target in targets]


def _describe(targets: tuple[object, ...]) -> str:
    return repr(_json_targets(targets))
