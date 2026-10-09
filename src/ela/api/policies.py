"""The routes of the policies of §59: preview, create, list, revoke (M13.12, ADR 0062; decision 9).

**The one place a policy is born and revoked** (architecture rule 66): outside this module nobody
calls :func:`~ela.permissions.authorization_from_policy`, nobody saves a grant without
``approval_id``, and nobody revokes one. Who chooses writes (decision 6): the person who holds the
Core's token, or a console, through the pages of ``/console/policies`` that call these functions
(rule 55). The middleware decides who reaches what: no route here names a kind.

The birth is the pure function's, then **«partirebbe»** (decision 7): the tool of the capability is
asked the same prospect that precedes a question, at the limits and on the sites of the policy, with
ELA's own sentence where the call needs one — a policy no session could use now is a defence that
seems active, and the tool's refusal is the creation's. The preview is the same road without a
write; the confirmation carries the model the preview named, and a prospect that names another
refuses it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Final
from uuid import UUID

from fastapi import APIRouter, Query

from ela.api.deps import ElaDep, IdentityDep
from ela.api.errors import ApiError
from ela.api.schemas import (
    LimitOut,
    PoliciesOut,
    PolicyConfirmIn,
    PolicyIn,
    PolicyOut,
    PreviewOut,
    RevokedOut,
    TermsOut,
)
from ela.api.security import Identity
from ela.api.tasks import answerer
from ela.composition import Ela
from ela.domain import (
    Actor,
    AuditEvent,
    AuditEventId,
    AuditEventType,
    Authorization,
    AuthorizationId,
    CapabilitySpec,
    JsonValue,
)
from ela.permissions import (
    MAX_DAYS,
    MIN_DAYS,
    PolicyRequest,
    PolicyState,
    authorization_from_policy,
    never_covered,
    no_policy_for,
    prospect_arguments,
    short_id,
    state_of,
)
from ela.ports import Guided, NotFoundError

__all__ = [
    "RUNNING",
    "PolicyNotLiveError",
    "PolicyPreviewChangedError",
    "PolicyWouldNotStartError",
    "created",
    "policies_of",
    "preview_of",
    "revoked_policy",
    "router",
]

router = APIRouter(prefix="/policies", tags=["policies"])

RUNNING: Final = (
    "a session already running under it goes on until it ends: to stop it, ela task cancel <id>"
)
"""What a revocation says of a session it already covered (decision 5): the grant was spent
before it, and the stop of a task is the «ferma»."""


class PolicyWouldNotStartError(ApiError):
    """The tool refused the call at the limits and on the sites of the policy (decision 7): no
    session could use it now. The tool's own code is the first word of the message."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


class PolicyPreviewChangedError(ApiError):
    """The confirmation named a model the prospect does not name now: preview again."""

    def __init__(self, named: str, now: str) -> None:
        super().__init__(
            f"the preview named {named!r}, and the default route now reads {now!r}: preview again"
        )


class PolicyNotLiveError(ApiError):
    """A revocation of a policy that ended: there is nothing left to take away. One already revoked
    is the store's own answer, :class:`~ela.ports.AuthorizationAlreadyRevokedError`, with the
    instant of the first revocation — the same answer whether the two came one after the other or
    raced."""

    def __init__(self, policy: Authorization) -> None:
        assert policy.expires_at is not None  # a policy always ends: the domain's invariant
        super().__init__(
            f"policy {short_id(policy.id)} expired at {policy.expires_at.isoformat()}: "
            "there is nothing to revoke"
        )


# ----------------------------------------------------------------------------------------
# The list
# ----------------------------------------------------------------------------------------


@router.get("")
async def list_policies(
    ela: ElaDep,
    everything: Annotated[
        bool, Query(alias="all", description="the revoked and the ended too")
    ] = False,
) -> PoliciesOut:
    """The live policies — with ``all``, the revoked and the ended too — and what can be created."""
    return await policies_of(ela, everything=everything)


async def policies_of(ela: Ela, *, everything: bool) -> PoliciesOut:
    now = ela.clock.now()
    policies = []
    for spec in ela.capabilities.specs():
        for grant in await ela.authorizations.for_capability(spec.id):
            if grant.approval_id is not None:
                continue
            if not everything and state_of(grant, now) is not PolicyState.LIVE:
                continue
            policies.append(await _out(grant, ela))
    admitting = tuple(
        _terms_of(spec) for spec in ela.capabilities.specs() if no_policy_for(spec) is None
    )
    return PoliciesOut(policies=tuple(policies), admitting=admitting)


async def _out(grant: Authorization, ela: Ela) -> PolicyOut:
    assert grant.bounds is not None and grant.expires_at is not None  # a policy
    return PolicyOut(
        id=grant.id,
        short=short_id(grant.id),
        capability=grant.capability_id,
        scope=grant.scope,
        limits={name: str(value) for name, value in grant.bounds.limits.items()},
        uncovered=grant.bounds.terms.uncovered,
        model=grant.bounds.terms.model,
        state=state_of(grant, ela.clock.now()).value,
        created_at=grant.created_at,
        created_by=await answerer(grant.granted_by, ela),
        expires_at=grant.expires_at,
        revoked_at=grant.revoked_at,
        uses=await ela.authorizations.uses(grant.id),
    )


def _terms_of(spec: CapabilitySpec) -> TermsOut:
    assert spec.policy_terms is not None  # ``no_policy_for`` said it admits one
    properties: Mapping[str, Any] = spec.input_schema.get("properties", {})  # type: ignore[assignment]
    return TermsOut(
        capability=spec.id,
        description=spec.description,
        scope=spec.scope,
        limits=tuple(
            LimitOut(
                name=name,
                type=str(properties[name].get("type")),
                minimum=properties[name].get("minimum"),
                maximum=properties[name].get("maximum"),
                pattern=properties[name].get("pattern"),
            )
            for name in spec.policy_terms.limits
        ),
        uncovered=spec.policy_terms.uncovered,
        free=spec.policy_terms.free,
        model=spec.policy_terms.model,
        days_min=MIN_DAYS,
        days_max=MAX_DAYS,
    )


# ----------------------------------------------------------------------------------------
# The birth: preview, then the creation
# ----------------------------------------------------------------------------------------


async def _born(
    body: PolicyIn, ela: Ela, identity: Identity
) -> tuple[Authorization, CapabilitySpec, Guided | None]:
    """The grant the request asks for, and what its prospect says — or the first refusal.

    The pure checks of decision 6 first, then «partirebbe» (decision 7): nothing written yet.
    """
    grant = authorization_from_policy(
        PolicyRequest(
            capability_id=body.capability,
            scope=tuple(body.scope),
            limits=dict(body.limits),
            days=body.days,
        ),
        catalogue=ela.capabilities,
        granted_by=identity.actor.id,
        now=ela.clock.now(),
        authorization_id=AuthorizationId(ela.ids.new_uuid()),
    )
    spec = ela.capabilities.get(grant.capability_id)
    prospect = await ela.tools.get(spec.id).prospect(prospect_arguments(grant, spec))
    if prospect.refusal is not None:
        raise PolicyWouldNotStartError(prospect.refusal.code, prospect.refusal.message)
    guided = prospect.guided
    assert spec.policy_terms is not None  # the birth said it admits one
    if guided is not None and guided.model != spec.policy_terms.model:
        # The default route answers with another model than the declaration names — a second
        # provider of the route, chosen now (decision 16): no policy is born under it.
        raise PolicyWouldNotStartError(
            "policy.model_changed",
            f"the declaration of {spec.id} names {spec.policy_terms.model}, and the route now "
            f"reads {guided.model}",
        )
    return grant, spec, guided


@router.post("/preview")
async def preview(body: PolicyIn, ela: ElaDep, identity: IdentityDep) -> PreviewOut:
    """What the creation would approve, with the same refusals and no write (decision 9)."""
    return await preview_of(body, ela, identity)


async def preview_of(body: PolicyIn, ela: Ela, identity: Identity) -> PreviewOut:
    grant, spec, guided = await _born(body, ela, identity)
    assert grant.bounds is not None and grant.expires_at is not None
    one_call = "" if guided is None else guided.one_call
    model = None if guided is None else guided.model
    return PreviewOut(
        capability=spec.id,
        description=spec.description,
        scope=grant.scope,
        limits={name: str(value) for name, value in grant.bounds.limits.items()},
        days=body.days,
        expires_at=grant.expires_at,
        model=model,
        sends="" if guided is None else guided.sends,
        one_call=one_call,
        cost=(
            ""
            if guided is None
            else (
                "the most a session may spend is a reservation, not the real spend: a session "
                f"reserves it whole, and each of its calls reserves up to {one_call} on {model} "
                "before it leaves; the real spend is written when the session ends"
            )
        ),
        never=never_covered(spec, ela.capabilities.specs()),
    )


@router.post("", status_code=201)
async def create(body: PolicyConfirmIn, ela: ElaDep, identity: IdentityDep) -> PolicyOut:
    """The creation: the same road as the preview, then the grant and its audit (decision 6)."""
    return await created(body, ela, identity)


async def created(body: PolicyConfirmIn, ela: Ela, identity: Identity) -> PolicyOut:
    grant, spec, guided = await _born(body, ela, identity)
    named = "" if guided is None else guided.model
    if named != body.model:
        raise PolicyPreviewChangedError(body.model, named)
    await ela.authorizations.grant(grant)
    assert grant.bounds is not None and grant.expires_at is not None
    terms = grant.bounds.terms
    payload: dict[str, JsonValue] = {
        "origin": "policy",
        "scope": list(grant.scope),
        "limits": {name: str(value) for name, value in grant.bounds.limits.items()},
        "terms": {
            "limits": list(terms.limits),
            "uncovered": list(terms.uncovered),
            "free": list(terms.free),
            "route": terms.route,
            "model": terms.model,
        },
        "expires_at": grant.expires_at.isoformat(),
        "days": body.days,
    }
    await _audit(
        ela,
        identity.actor,
        AuditEventType.AUTHORIZATION_GRANTED,
        grant,
        f"grant: policy {grant.id} for {spec.id}, {body.days} day(s)",
        payload,
    )
    return await _out(grant, ela)


# ----------------------------------------------------------------------------------------
# The revocation (decision 5)
# ----------------------------------------------------------------------------------------


@router.post("/{policy_id}/revoke")
async def revoke(policy_id: UUID, ela: ElaDep, identity: IdentityDep) -> RevokedOut:
    """Revoke a live policy: written once, and a session already running goes on."""
    return await revoked_policy(policy_id, ela, identity)


async def revoked_policy(policy_id: UUID, ela: Ela, identity: Identity) -> RevokedOut:
    grant = await ela.authorizations.get(AuthorizationId(policy_id))
    if grant.approval_id is not None:
        # A grant born from a yes is not a policy: this route does not know it.
        raise NotFoundError("policy", str(policy_id))
    now = ela.clock.now()
    if state_of(grant, now) is PolicyState.EXPIRED:
        raise PolicyNotLiveError(grant)
    # A second revocation is the store's to refuse, in the same UPDATE that writes the first.
    gone = await ela.authorizations.revoke(grant.id, at=now)
    payload: dict[str, JsonValue] = {
        "origin": "policy",
        "revoked_at": now.isoformat(),
        "expires_at": None if gone.expires_at is None else gone.expires_at.isoformat(),
        "uses": await ela.authorizations.uses(gone.id),
    }
    await _audit(
        ela,
        identity.actor,
        AuditEventType.AUTHORIZATION_REVOKED,
        gone,
        f"revoke: policy {gone.id} for {gone.capability_id}",
        payload,
    )
    return RevokedOut(policy=await _out(gone, ela), running=RUNNING)


async def _audit(
    ela: Ela,
    actor: Actor,
    kind: AuditEventType,
    grant: Authorization,
    summary: str,
    payload: dict[str, JsonValue],
) -> None:
    """The event of a birth or a revocation, signed by who chose: ``USER``, with the identity the
    middleware resolved — the name and the role are read at the read (ADR 0059 §3)."""
    await ela.audit.append(
        AuditEvent(
            id=AuditEventId(ela.ids.new_uuid()),
            created_at=ela.clock.now(),
            event_type=kind,
            actor=actor,
            summary=summary,
            capability_id=grant.capability_id,
            authorization_id=grant.id,
            payload=payload,
        )
    )
