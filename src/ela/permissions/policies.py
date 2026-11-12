"""The policies of §59: how one is born, when it covers a call, and what is said about it (M13.12,
ADR 0062).

A policy is an :class:`~ela.domain.Authorization` without ``approval_id``: the user's own standing
yes, with a scope — the sites, the folders —, the limits per call the capability declares, the
uses if the user sets them, and an end. It makes a call autonomous **without lowering any level**
(decision 2): a capability is covered only if it declares what a policy must bound (decision 1),
and since M13.14 that includes a ``HIGH`` which does — ``fs.write``, ``browser.act``,
``browser.act_as_you`` — but never one that launches a program, and never a ``CRITICAL`` (ADR
0068).

**One predicate** (decision 4), :func:`shortfall`: the first reason a policy does not cover a call,
or none, in the order of :data:`GAPS`. The Guardian reads it in two slices — :data:`UNCOVERED`
in ``_mismatch``, :data:`UNUSABLE` in ``_unusable`` —, the executor the same two in
``select_authorization``, and the question all of it, in :func:`why_lines`: three readers, one
answer, the form of
``asks_at_every_use`` (ADR 0045 §3) extended.

**One birth** (decision 6), :func:`authorization_from_policy`: the checks of :data:`POLICY_CHECKS`,
in their order, before any grant exists; the first that fails is a
:class:`~ela.permissions.errors.PolicyRefusedError`. It is called by the route of the creation and
by nobody else (architecture rule 66).

Pure, like ``authorizations.py``: no clock, no ids, no store — ``now`` is the caller's fact.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, Final

from ela.domain import (
    Authorization,
    AuthorizationId,
    CapabilityId,
    CapabilitySpec,
    JsonValue,
    PolicyBounds,
)
from ela.permissions.capabilities import is_valid_scope_entry, is_valid_value
from ela.permissions.errors import PolicyRefusedError
from ela.permissions.rows import asks_at_every_use, no_policy_for
from ela.permissions.scope import scope_covers, targets_of
from ela.ports import CapabilityRegistryPort, NotFoundError

__all__ = [
    "GAPS",
    "MAX_DAYS",
    "MIN_DAYS",
    "POLICY_CHECKS",
    "POLICY_PROSPECT",
    "SHORT_ID",
    "UNCOVERED",
    "UNUSABLE",
    "WHY_DAYS",
    "WHY_MAX",
    "Gap",
    "PolicyCheck",
    "PolicyRequest",
    "PolicyState",
    "Shortfall",
    "authorization_from_policy",
    "never_covered",
    "prospect_arguments",
    "scope_is_a_list",
    "short_id",
    "shortfall",
    "state_of",
    "why_lines",
]

MIN_DAYS: Final = 1
MAX_DAYS: Final = 90
"""How long a policy may live, in days, chosen by Tommaso with **no default** (decision 3d): a
boundary ELA chose for you was decided by nobody, and a permission nobody rereads stops being a
choice — ninety days is the most."""

WHY_DAYS: Final = 30
WHY_MAX: Final = 3
"""Which policies the line «why I ask» names (decision 8): the live ones, and the ones that ended
less than thirty days before the question; at most three, the most recent first."""

SHORT_ID: Final = 8
"""How many characters of its id name a policy where a person reads it (decision 19): the form a
question already uses for a machine (M13.3, decision 10)."""

POLICY_PROSPECT: Final = "A call that a standing policy of yours would cover."
"""ELA's own sentence for every free argument the tool's prospect needs (decision 7): the goal of a
session. It is never saved, never in the audit, and never sent anywhere."""


def short_id(authorization_id: AuthorizationId) -> str:
    return str(authorization_id)[:SHORT_ID]


# ----------------------------------------------------------------------------------------
# The predicate
# ----------------------------------------------------------------------------------------


class Gap(StrEnum):
    """Why a policy does not cover a call, in the order of decision 4 (ADR 0062, ADR 0068)."""

    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"
    EXHAUSTED = "EXHAUSTED"
    """The policy has uses, and they are spent (M13.14, ADR 0068): usable no, covering yes — the
    step asks, like a revoked or expired one."""
    TERMS = "TERMS"
    """The capability declares no terms, or not the ones the policy was born under."""
    ELSEWHERE = "ELSEWHERE"
    """The terms say ``on_the_core`` and the step is not placed on the Core — on a node, or where
    the caller did not say (M13.14, ADR 0068; decision 10): the policy's folder is the Core's."""
    SITE = "SITE"
    LIMIT = "LIMIT"
    ARGUMENT = "ARGUMENT"
    """The call carries an argument the policy's terms do not call a limit, the scope or free."""


GAPS: Final[tuple[Gap, ...]] = tuple(Gap)
"""The order, read by the table of ADR 0062: the first gap found is the reason."""
UNUSABLE: Final[tuple[Gap, ...]] = (Gap.REVOKED, Gap.EXPIRED, Gap.EXHAUSTED)
"""The half that says *usable* (ADR 0011 §6): a policy here asks, it is never denied."""
UNCOVERED: Final[tuple[Gap, ...]] = (Gap.TERMS, Gap.ELSEWHERE, Gap.SITE, Gap.LIMIT, Gap.ARGUMENT)
"""The half that says *covers*: a policy here is never handed over by the executor."""


@dataclass(frozen=True, slots=True)
class Shortfall:
    """The first reason a policy does not cover a call: which gap, and the sentence.

    The sentence names the policy by its short id and by numbers, **never a site and never the
    words of the call** (decision 8): it stands above the ceiling of every page."""

    gap: Gap
    reason: str


@dataclass(frozen=True, slots=True)
class _Call:
    """The facts of one call the predicate reads: its arguments, the instant, how many times the
    policy was used, and whether the step is placed on the Core — ``None`` when the caller did
    not say, which a policy ``on_the_core`` does not cover (§33)."""

    arguments: Mapping[str, object]
    now: datetime
    uses: int
    on_the_core: bool | None


Check = Callable[[Authorization, CapabilitySpec, _Call], str | None]


def _revoked(policy: Authorization, capability: CapabilitySpec, call: _Call) -> str | None:
    if policy.revoked_at is None:
        return None
    return f"policy {short_id(policy.id)} was revoked on {policy.revoked_at.date().isoformat()}"


def _expired(policy: Authorization, capability: CapabilitySpec, call: _Call) -> str | None:
    assert policy.expires_at is not None  # a policy always ends: the domain's invariant
    if policy.expires_at > call.now:
        return None
    return f"policy {short_id(policy.id)} expired on {policy.expires_at.date().isoformat()}"


def _exhausted(policy: Authorization, capability: CapabilitySpec, call: _Call) -> str | None:
    if policy.max_uses is None or call.uses < policy.max_uses:
        return None
    return f"policy {short_id(policy.id)} was used {call.uses} of its {policy.max_uses} times"


def _terms(policy: Authorization, capability: CapabilitySpec, call: _Call) -> str | None:
    declared = capability.policy_terms
    if declared is None:
        return f"{capability.id} declares no terms for a policy (policy {short_id(policy.id)})"
    bounds = policy.bounds
    if (
        bounds is None
        or bounds.terms != declared
        or set(bounds.limits) != set(bounds.terms.limits)
        # What the capability's sessions cover, with the covered schema, is part of what a policy
        # was born under (M13.9, decision 29): the closed world of ADR 0062 §1, extended.
        or bounds.covers != capability.covers
    ):
        return (
            f"{capability.id} declares other terms than those policy {short_id(policy.id)} was "
            "created under"
        )
    return None


def _elsewhere(policy: Authorization, capability: CapabilitySpec, call: _Call) -> str | None:
    bounds = policy.bounds
    assert bounds is not None  # ``TERMS`` runs first, in every slice that reaches this
    if not bounds.terms.on_the_core or call.on_the_core is True:
        return None
    return (
        f"policy {short_id(policy.id)} covers only a step that runs on the Core, and this step is "
        "not one"
    )


def _site(policy: Authorization, capability: CapabilitySpec, call: _Call) -> str | None:
    if scope_covers(policy.scope, targets_of(capability, call.arguments)):
        return None
    names = ", ".join(capability.scoped_arguments)
    return f"a value of {names} is not among those of policy {short_id(policy.id)}"


def _number(value: object) -> Decimal | None:
    """A limit as a number: an ``int`` (never a ``bool``) or a text ``Decimal`` reads, finite."""
    if isinstance(value, bool) or not isinstance(value, int | str):
        return None
    try:
        number = Decimal(value)
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _limit(policy: Authorization, capability: CapabilitySpec, call: _Call) -> str | None:
    bounds = policy.bounds
    assert bounds is not None  # ``TERMS`` runs first, in every slice that reaches this
    for name in bounds.terms.limits:
        cap, value = bounds.limits[name], call.arguments.get(name)
        limit = _number(cap)
        if limit is None:
            return f"{name} of policy {short_id(policy.id)} is not a number"
        called = _number(value)
        if called is None:
            return f"{name} of this call is not a number"
        if called > limit:
            return f"{name} {value} is above the {cap} of policy {short_id(policy.id)}"
    return None


def _argument(policy: Authorization, capability: CapabilitySpec, call: _Call) -> str | None:
    bounds = policy.bounds
    assert bounds is not None  # ``TERMS`` runs first, in every slice that reaches this
    terms = bounds.terms
    allowed = {*terms.limits, *terms.free, *capability.scoped_arguments}
    for name in call.arguments:
        if name in allowed:
            continue
        if name in terms.uncovered:
            return (
                f"{name} is never covered by a policy: policy {short_id(policy.id)} does not "
                "cover this call"
            )
        return f"{name} is not among the terms of policy {short_id(policy.id)}"
    return None


_CHECKS: Final[dict[Gap, Check]] = {
    Gap.REVOKED: _revoked,
    Gap.EXPIRED: _expired,
    Gap.EXHAUSTED: _exhausted,
    Gap.TERMS: _terms,
    Gap.ELSEWHERE: _elsewhere,
    Gap.SITE: _site,
    Gap.LIMIT: _limit,
    Gap.ARGUMENT: _argument,
}


def shortfall(
    policy: Authorization,
    capability: CapabilitySpec,
    arguments: Mapping[str, object],
    *,
    now: datetime,
    uses: int = 0,
    on_the_core: bool | None = None,
    gaps: tuple[Gap, ...] = GAPS,
) -> Shortfall | None:
    """The first reason ``policy`` does not cover this call of ``capability``, or ``None``.

    ``capability`` is the **registered** specification; ``gaps`` one of :data:`GAPS`,
    :data:`UNUSABLE` or :data:`UNCOVERED` — slices of one order, never another one. The limits are
    compared as ``Decimal`` (decision 3b): ``1.1`` and ``1.10`` are the same limit, and a value that
    is not a finite number does not cover — a reason, never an exception (decision 10).

    ``uses`` is how many times the policy was used, read from the store by the caller, and
    ``on_the_core`` whether the step is placed on the Core (M13.14, ADR 0068): ``None`` — not
    said — is not the Core, and a policy whose terms say ``on_the_core`` does not cover it.
    """
    call = _Call(arguments, now, uses, on_the_core)
    for gap in gaps:
        reason = _CHECKS[gap](policy, capability, call)
        if reason is not None:
            return Shortfall(gap, reason)
    return None


# ----------------------------------------------------------------------------------------
# State
# ----------------------------------------------------------------------------------------


class PolicyState(StrEnum):
    """Where a policy stands, derived and never stored. ``EXHAUSTED`` since M13.14 (ADR 0068;
    answer 30 of the review of its SPEC): a policy that can cover nothing any more is not ``LIVE``
    — it stands among the ended ones, with the expired and the revoked."""

    LIVE = "LIVE"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"
    EXHAUSTED = "EXHAUSTED"


def state_of(policy: Authorization, now: datetime, *, uses: int) -> PolicyState:
    """The state of ``policy`` at ``now``, having been used ``uses`` times: revoked, expired,
    exhausted, in the order of :data:`GAPS`, or live."""
    if policy.revoked_at is not None:
        return PolicyState.REVOKED
    assert policy.expires_at is not None  # a policy always ends: the domain's invariant
    if policy.expires_at <= now:
        return PolicyState.EXPIRED
    if policy.max_uses is not None and uses >= policy.max_uses:
        return PolicyState.EXHAUSTED
    return PolicyState.LIVE


def _ended(policy: Authorization) -> datetime:
    """When a policy stopped being usable: the first of its revocation and its end."""
    assert policy.expires_at is not None  # a policy always ends: the domain's invariant
    if policy.revoked_at is None:
        return policy.expires_at
    return min(policy.revoked_at, policy.expires_at)


# ----------------------------------------------------------------------------------------
# The line «why I ask» (decision 8)
# ----------------------------------------------------------------------------------------


def why_lines(
    policies: Iterable[tuple[Authorization, int]],
    capability: CapabilitySpec,
    arguments: Mapping[str, object],
    *,
    now: datetime,
    on_the_core: bool | None,
) -> tuple[str, ...]:
    """Why a call of ``capability`` asks, policy by policy — the question's line, composed here
    and never elsewhere (decision 8).

    The policies of the capability born before ``now`` that are live, or that ended less than
    :data:`WHY_DAYS` before it; at most :data:`WHY_MAX`, the most recent first; for each, the first
    reason of :func:`shortfall`. A policy the predicate finds covering is named as such: the step
    asks again for the yes it was already given, because a step's own yes is its answer
    (ADR 0015 §6) and a policy does not replace it.

    Each policy comes **with its uses**, read from the store by the caller, and the step with
    whether it is placed on the Core (M13.14, ADR 0068): the function stays pure.
    """
    window = now - timedelta(days=WHY_DAYS)
    considered = sorted(
        (
            (one, uses)
            for one, uses in policies
            if one.approval_id is None and one.created_at <= now and _ended(one) > window
        ),
        key=lambda pair: pair[0].created_at,
        reverse=True,
    )[:WHY_MAX]
    if not considered:
        return (f"no policy of yours for {capability.id}",)
    lines = []
    for one, uses in considered:
        found = shortfall(one, capability, arguments, now=now, uses=uses, on_the_core=on_the_core)
        if found is None:
            lines.append(
                f"policy {short_id(one.id)} covers this call: this step asks again for the yes "
                "it was given"
            )
        else:
            lines.append(found.reason)
    return tuple(lines)


# ----------------------------------------------------------------------------------------
# What «partirebbe» asks the tool, and what the preview says (decisions 7 and 9)
# ----------------------------------------------------------------------------------------


def _properties(capability: CapabilitySpec) -> Mapping[str, Any]:
    properties = capability.input_schema.get("properties", {})
    assert isinstance(properties, Mapping)
    return properties


def _required(capability: CapabilitySpec) -> tuple[str, ...]:
    required = capability.input_schema.get("required", ())
    assert isinstance(required, Sequence)
    return tuple(str(name) for name in required)


def scope_is_a_list(capability: CapabilitySpec) -> bool:
    """Whether the scoped arguments of ``capability`` are lists — a guided session's sites — and so
    whether the «partirebbe» of its policy is one call, :func:`prospect_arguments`, or a question
    to the tool for each place of the scope, :meth:`~ela.ports.ToolPort.prospect_place` (M13.14,
    ADR 0068). The catalogue holds them all lists or all single values."""
    properties = _properties(capability)
    return all(
        dict(properties[name]).get("type") == "array" for name in capability.scoped_arguments
    )


def prospect_arguments(policy: Authorization, capability: CapabilitySpec) -> dict[str, JsonValue]:
    """The arguments of a call **at the limits and on the sites of** ``policy`` (decision 7).

    Every limit with the type of its argument; every scoped argument with the whole scope; every
    required free argument with :data:`POLICY_PROSPECT`; nothing uncovered — the default route.
    **Only for a capability whose scoped argument is a list** (M13.14, ADR 0068): for one whose
    scoped argument is one value there is no call to build, and the tool is asked about each
    place instead (:meth:`~ela.ports.ToolPort.prospect_place`).
    """
    bounds = policy.bounds
    assert bounds is not None and capability.policy_terms is not None
    properties = _properties(capability)
    arguments: dict[str, JsonValue] = {}
    for name in capability.policy_terms.free:
        if name in _required(capability):
            arguments[name] = POLICY_PROSPECT
    for name in capability.scoped_arguments:
        arguments[name] = list(policy.scope)
    for name in capability.policy_terms.limits:
        value = bounds.limits[name]
        declared = properties[name]
        arguments[name] = int(str(value)) if declared.get("type") == "integer" else value
    return arguments


def never_covered(
    capability: CapabilitySpec, catalogue: Iterable[CapabilitySpec]
) -> tuple[str, ...]:
    """What a policy of ``capability`` never covers, derived and not written for one capability
    (decision 9; M13.14, ADR 0068): the rows that ask at every use, a call beyond the terms, an
    uncovered argument, a step on a node for a policy of the Core, the gestures of a session — and
    what has already left, which no revocation calls back."""
    terms = capability.policy_terms
    assert terms is not None
    asking = sorted(spec.id for spec in catalogue if asks_at_every_use(spec))
    said = [
        "every call of a capability that asks at every use asks every time: " + ", ".join(asking),
        "a call above a limit, or outside the scope, asks",
    ]
    said.extend(f"a call with {name} asks" for name in terms.uncovered)
    if terms.on_the_core:
        said.append("a step that runs on a node asks: only a step on the Core is covered")
    if terms.route is not None:
        # A capability whose policy names a model's route is a guided session (ADR 0062 §1): its
        # gestures are steps of their own capability, which only a policy of that one covers.
        said.append(
            "a gesture of its sessions asks, unless a policy of the gesture's own capability "
            "covers it"
        )
    said.append("what has left is not taken back: a revocation stops only what comes after")
    return tuple(said)


# ----------------------------------------------------------------------------------------
# The birth (decision 6)
# ----------------------------------------------------------------------------------------


class PolicyCheck(StrEnum):
    """The checks a policy passes before it exists, in the order they run (ADR 0062).

    Not ``Check``: that name is the checks of a yes (ADR 0012 §2), and it stays theirs."""

    CATALOGUE = "CATALOGUE"
    ADMITS = "ADMITS"
    SCOPE = "SCOPE"
    LIMITS = "LIMITS"
    USES = "USES"
    """How many uses: none, for no limit, or a whole number from 1 up, with no maximum — the
    user's boundary, never a tighter one of ELA's (M13.14, ADR 0068; decision 8)."""
    DAYS = "DAYS"


POLICY_CHECKS: Final[tuple[PolicyCheck, ...]] = tuple(PolicyCheck)
"""The order the checks run in; the first that fails wins (decision 6)."""


@dataclass(frozen=True, slots=True)
class PolicyRequest:
    """What the user asks for: a capability, its scope, its limits in words, how many days, and
    how many uses — ``None`` for no limit (M13.14, ADR 0068)."""

    capability_id: CapabilityId
    scope: tuple[str, ...]
    limits: Mapping[str, str]
    days: int
    uses: int | None = None


def _refused(check: PolicyCheck, reason: str) -> PolicyRefusedError:
    return PolicyRefusedError(check, reason)


def _limits(request: PolicyRequest, capability: CapabilitySpec) -> dict[str, JsonValue]:
    """The limits of ``request``, exactly the declared ones, each valid for its argument's schema
    and kept in words — an integer as its number."""
    assert capability.policy_terms is not None
    declared = capability.policy_terms.limits
    missing = [name for name in declared if name not in request.limits]
    extra = sorted(name for name in request.limits if name not in declared)
    if missing or extra:
        raise _refused(
            PolicyCheck.LIMITS,
            f"the limits of {capability.id} are {list(declared)}: missing {missing}, not declared "
            f"{extra}",
        )
    properties = _properties(capability)
    kept: dict[str, JsonValue] = {}
    for name in declared:
        written = request.limits[name]
        schema = properties[name]
        value: object = written
        if schema.get("type") == "integer":
            stripped = written.strip()
            value = int(stripped) if stripped.lstrip("-").isdigit() else written
        if not is_valid_value(schema, value):
            raise _refused(
                PolicyCheck.LIMITS, f"limit {name}={written!r} is not valid for {capability.id}"
            )
        kept[name] = str(value) if isinstance(value, int) else written
    return kept


def authorization_from_policy(
    request: PolicyRequest,
    *,
    catalogue: CapabilityRegistryPort,
    granted_by: str,
    now: datetime,
    authorization_id: AuthorizationId,
) -> Authorization:
    """The policy ``request`` asks for, or :class:`PolicyRefusedError` on the first check of
    :data:`POLICY_CHECKS` that fails — before any grant exists (decision 6).

    ``granted_by`` is the identity the middleware resolved; its name and role are read from the
    registry by whoever lists (ADR 0059 §3). Whoever calls this saves the grant and writes
    ``AUTHORIZATION_GRANTED`` — the route of the creation, and nobody else (rule 66).
    """
    try:
        capability = catalogue.get(request.capability_id)
    except NotFoundError:
        raise _refused(
            PolicyCheck.CATALOGUE, f"{request.capability_id} is not in the catalogue"
        ) from None
    refusal = no_policy_for(capability)
    if refusal is not None:
        raise _refused(PolicyCheck.ADMITS, refusal)
    assert capability.policy_terms is not None  # ``no_policy_for`` said it admits one
    if (
        not request.scope
        or not all(is_valid_scope_entry(entry) for entry in request.scope)
        or not scope_covers(capability.scope, request.scope)
    ):
        raise _refused(
            PolicyCheck.SCOPE,
            f"the scope of a policy of {capability.id} is one or more of {list(capability.scope)}",
        )
    limits = _limits(request, capability)
    uses = request.uses
    if uses is not None and (type(uses) is not int or uses < 1):
        raise _refused(
            PolicyCheck.USES,
            f"the uses of a policy are none, for no limit, or a whole number from 1 up, not "
            f"{uses!r}",
        )
    days = request.days
    if type(days) is not int or not MIN_DAYS <= days <= MAX_DAYS:
        raise _refused(
            PolicyCheck.DAYS, f"a policy lives from {MIN_DAYS} to {MAX_DAYS} days, not {days!r}"
        )
    return Authorization(
        id=authorization_id,
        created_at=now,
        capability_id=capability.id,
        scope=tuple(request.scope),
        granted_by=granted_by,
        expires_at=now + timedelta(days=days),
        max_uses=uses,
        bounds=PolicyBounds(terms=capability.policy_terms, limits=limits, covers=capability.covers),
        metadata={"origin": "policy"},
    )
