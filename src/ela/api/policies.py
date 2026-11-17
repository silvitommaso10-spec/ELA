"""The routes of the policies of §59: preview, create, list, revoke (M13.12, ADR 0062; decision 9).

**The one place a policy is born and revoked** (architecture rule 66): outside this module nobody
calls :func:`~ela.permissions.authorization_from_policy`, nobody saves a grant without
``approval_id``, and nobody revokes one. Who chooses writes (decision 6): the person who holds the
Core's token, or a console, through the pages of ``/console/policies`` that call these functions
(rule 55). The middleware decides who reaches what: no route here names a kind.

The birth is the pure function's, then **«partirebbe»** (decision 7): the tool of the capability is
asked the same prospect that precedes a question, at the limits and on the sites of the policy, with
ELA's own sentence where the call needs one — a policy no session could use now is a defence that
seems active, and the tool's refusal is the creation's. **For a capability whose scope is one value
per call** — ``fs.write``, the gestures, the login and the four files from the browser — there is no
call to build: the tool is asked about each place of the scope, in order, with the values of the
second dimension (M13.15, ADR 0071), and the first refusal is the creation's; the place as the
Core's disk names it is what the preview shows beside the entry (M13.14, ADR 0068).
The preview is the same road without a write; the confirmation carries the model the preview named,
and a prospect that names another refuses it.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from typing import Annotated, Any, Final
from uuid import UUID

from fastapi import APIRouter, Query

from ela.api.deps import ElaDep, IdentityDep
from ela.api.errors import ApiError
from ela.api.schemas import (
    ActionOut,
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
    amount,
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
    scope_is_a_list,
    short_id,
    shown_at_birth,
    shown_of,
    state_of,
)
from ela.ports import Guided, NotFoundError, ShownEntry

__all__ = [
    "ENDED_DAYS",
    "READS_GO_ON",
    "RECENT_MAX",
    "SESSION_GOES_ON",
    "PolicyNotLiveError",
    "PolicyPreviewChangedError",
    "PolicyWouldNotStartError",
    "created",
    "ended_of",
    "policies_of",
    "preview_of",
    "revoked_policy",
    "router",
]

router = APIRouter(prefix="/policies", tags=["policies"])

SESSION_GOES_ON: Final = (
    "a session already running under it goes on until it ends: to stop it, ela task cancel <id>"
)
"""What a revocation says of a session it already covered (decision 5): the grant was spent
before it, and the stop of a task is the «ferma». **Only for the policy of a guided session**
(M13.15, ADR 0071; decision 20, answer 40): one whose declaration names a model's route."""
READS_GO_ON: Final = "The reads it covers go on with it, up to its own looks, seconds and cost"
"""Since M13.9 (ADR 0063 §1; decision 29) a session with the profile covers the reads its model
writes: a revocation does not stop those either. **Only for a policy whose capability declares what
it ``covers``** (M13.15, ADR 0071; answer 40): the reads of ``browser.guided`` are ``browser.read``,
which nothing covers."""


RECENT_MAX: Final = 5
"""How many of its last actions a policy shows (M13.14, ADR 0068; decision 13): five
``TOOL_EXECUTED`` with its id, the most recent first — not five events of any kind."""

ENDED_DAYS: Final = 30
"""Which ended policies the console still shows (M13.14, ADR 0068; answer 30 of the review of its
SPEC): those whose end is less than thirty days old, or still to come — a revoked one, or one whose
uses are spent."""

ON_THE_CORE: Final = "only a step that runs on the Core: a step on a node asks"
"""What the preview of a policy that covers only the Core says (M13.14, ADR 0068; decision 10)."""


class PolicyWouldNotStartError(ApiError):
    """The tool refused the call at the limits and on the sites of the policy (decision 7): no
    session could use it now. The tool's own code is the first word of the message."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


class PolicyPreviewChangedError(ApiError):
    """The confirmation named a model the prospect does not name now: preview again."""

    def __init__(self, named: str | None, now: str | None) -> None:
        super().__init__(
            f"the preview named {named!r}, and the default route now reads {now!r}: preview again"
        )


class PolicyNotLiveError(ApiError):
    """A revocation of a policy that ended — expired, or with its uses spent (M13.14, ADR 0068;
    answer 30 of the review): there is nothing left to take away. One already revoked is the
    store's own answer, :class:`~ela.ports.AuthorizationAlreadyRevokedError`, with the instant of
    the first revocation — the same answer whether the two came one after the other or raced."""

    def __init__(self, policy: Authorization, state: PolicyState, uses: int) -> None:
        assert policy.expires_at is not None  # a policy always ends: the domain's invariant
        if state is PolicyState.EXHAUSTED:
            assert policy.max_uses is not None  # exhausted: it has uses
            ended = f"was used {uses} of its {amount(policy.max_uses, 'use', 'uses')}"
        else:
            ended = f"expired at {policy.expires_at.isoformat()}"
        super().__init__(f"policy {short_id(policy.id)} {ended}: there is nothing to revoke")


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
            uses = await ela.authorizations.uses(grant.id)
            if not everything and state_of(grant, now, uses=uses) is not PolicyState.LIVE:
                continue
            policies.append(await _out(grant, ela))
    sites = tuple(ela.settings.browser.sites)
    admitting = tuple(
        _terms_of(spec, sites) for spec in ela.capabilities.specs() if no_policy_for(spec) is None
    )
    return PoliciesOut(policies=tuple(policies), admitting=admitting)


async def ended_of(ela: Ela) -> tuple[PolicyOut, ...]:
    """The policies that are not live and whose end is less than :data:`ENDED_DAYS` old, or still
    to come — revoked, or with their uses spent: what the console shows among the ended ones, and
    where it says a policy has finished its uses (M13.14, ADR 0068)."""
    window = ela.clock.now() - timedelta(days=ENDED_DAYS)
    listed = await policies_of(ela, everything=True)
    return tuple(
        one
        for one in listed.policies
        if one.state != PolicyState.LIVE.value and one.expires_at > window
    )


async def _out(grant: Authorization, ela: Ela) -> PolicyOut:
    assert grant.bounds is not None and grant.expires_at is not None  # a policy
    uses = await ela.authorizations.uses(grant.id)
    spec = ela.capabilities.get(grant.capability_id)
    shown = shown_of(grant)
    return PolicyOut(
        id=grant.id,
        short=short_id(grant.id),
        capability=grant.capability_id,
        risk=spec.risk.value,
        does=None if spec.policy_words is None else spec.policy_words.does,
        goes=None if spec.policy_words is None else spec.policy_words.goes,
        scope=grant.scope,
        resolved=None if shown is None else shown[0],
        by_value=grant.bounds.terms.by_value,
        # What the birth showed, and never ``bounds.values``: an id of an entry is the plan's.
        values=None if shown is None else shown[1],
        limits={name: str(value) for name, value in grant.bounds.limits.items()},
        uncovered=grant.bounds.terms.uncovered,
        model=grant.bounds.terms.model,
        state=state_of(grant, ela.clock.now(), uses=uses).value,
        created_at=grant.created_at,
        created_by=await answerer(grant.granted_by, ela),
        expires_at=grant.expires_at,
        revoked_at=grant.revoked_at,
        uses=uses,
        max_uses=grant.max_uses,
        remaining=None if grant.max_uses is None else max(0, grant.max_uses - uses),
        recent=await _recent(grant, ela),
    )


async def _recent(grant: Authorization, ela: Ela) -> tuple[ActionOut, ...]:
    """The last actions done under ``grant``, read from the audit and never stored (M13.14, ADR
    0068; decision 13): its ``TOOL_EXECUTED``, at most :data:`RECENT_MAX`, the most recent first."""
    events = await ela.audit.read(
        authorization_id=grant.id,
        event_type=AuditEventType.TOOL_EXECUTED,
        limit=RECENT_MAX,
        newest_first=True,
    )
    return tuple(
        ActionOut(
            at=event.created_at,
            task=None if event.task_id is None else str(event.task_id)[:8],
            step=None if event.step_id is None else str(event.step_id),
            capability=event.capability_id,
            status=str(event.payload.get("status", "")),
            targets=_targets(event.payload.get("targets")),
        )
        for event in events
    )


def _targets(value: object) -> tuple[str | None, ...]:
    """The targets of a ``TOOL_EXECUTED`` as the executor wrote them: strings, or ``null``."""
    if not isinstance(value, list | tuple):
        return ()
    return tuple(one if isinstance(one, str) else None for one in value)


def _terms_of(spec: CapabilitySpec, sites: tuple[str, ...]) -> TermsOut:
    assert spec.policy_terms is not None  # ``no_policy_for`` said it admits one
    properties: Mapping[str, Any] = spec.input_schema.get("properties", {})  # type: ignore[assignment]
    words = spec.policy_words
    return TermsOut(
        capability=spec.id,
        description=spec.description,
        risk=spec.risk.value,
        does=None if words is None else words.does,
        goes=None if words is None else words.goes,
        on_the_core=spec.policy_terms.on_the_core,
        scope=spec.scope,
        by_value=spec.policy_terms.by_value,
        choices=sites if spec.policy_terms.by_value == "site" else (),
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
) -> tuple[Authorization, CapabilitySpec, Guided | None, tuple[str | None, ...]]:
    """The grant the request asks for, what its prospect says, and each place of its scope as the
    Core's disk names it — or the first refusal. **The grant carries what its birth showed**
    (M13.15, ADR 0071): the places resolved, and the values of its second dimension as a surface may
    show them — a site as itself, an entry by its name and its masked username.

    The pure checks of decision 6 first, then «partirebbe» (decision 7): nothing written yet.
    """
    grant = authorization_from_policy(
        PolicyRequest(
            capability_id=body.capability,
            scope=tuple(body.scope),
            limits=dict(body.limits),
            days=body.days,
            uses=body.uses,
            values={name: tuple(values) for name, values in body.values.items()},
        ),
        catalogue=ela.capabilities,
        granted_by=identity.actor.id,
        now=ela.clock.now(),
        authorization_id=AuthorizationId(ela.ids.new_uuid()),
    )
    spec = ela.capabilities.get(grant.capability_id)
    tool = ela.tools.get(spec.id)
    if not scope_is_a_list(spec):
        # One value per call (M13.14, ADR 0068): the tool is asked about each place, in order —
        # with every value of the second dimension (M13.15, ADR 0071): the product is covered.
        assert grant.bounds is not None  # a policy
        values = grant.bounds.values
        resolved: list[str | None] = []
        shown: tuple[str, ...] = values
        for place in grant.scope:
            looked = await tool.prospect_place(place, values)
            if looked.refusal is not None:
                raise PolicyWouldNotStartError(looked.refusal.code, looked.refusal.message)
            resolved.append(None if looked.target is None else looked.target.resolved)
            if looked.entries:
                # An entry of the vault is shown by its name and its masked username, as the
                # question of a login shows it — and the id it was asked by stays in ``bounds``.
                shown = tuple(_entry_shown(one) for one in looked.entries)
        grant = shown_at_birth(grant, resolved=resolved, values=shown)
        return grant, spec, None, tuple(resolved)
    prospect = await tool.prospect(prospect_arguments(grant, spec))
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
    return grant, spec, guided, tuple(None for _ in grant.scope)


def _entry_shown(entry: ShownEntry) -> str:
    """An entry of the vault as the views of a policy say it: its name, and its username masked."""
    return entry.name if entry.username is None else f"{entry.name} ({entry.username})"


@router.post("/preview")
async def preview(body: PolicyIn, ela: ElaDep, identity: IdentityDep) -> PreviewOut:
    """What the creation would approve, with the same refusals and no write (decision 9)."""
    return await preview_of(body, ela, identity)


async def preview_of(body: PolicyIn, ela: Ela, identity: Identity) -> PreviewOut:
    grant, spec, guided, resolved = await _born(body, ela, identity)
    assert grant.bounds is not None and grant.expires_at is not None
    one_call = "" if guided is None else guided.one_call
    model = None if guided is None else guided.model
    words = spec.policy_words
    return PreviewOut(
        capability=spec.id,
        description=spec.description,
        risk=spec.risk.value,
        does=None if words is None else words.does,
        goes=None if words is None else words.goes,
        scope=grant.scope,
        resolved=resolved,
        by_value=grant.bounds.terms.by_value,
        values=() if (shown := shown_of(grant)) is None else shown[1],
        together="" if words is None or words.together is None else words.together,
        limits={name: str(value) for name, value in grant.bounds.limits.items()},
        days=body.days,
        expires_at=grant.expires_at,
        uses=(
            "no limit of uses"
            if grant.max_uses is None
            else f"at most {amount(grant.max_uses, 'use', 'uses')}"
        ),
        on_the_core=ON_THE_CORE if grant.bounds.terms.on_the_core else "",
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
    grant, spec, guided, _ = await _born(body, ela, identity)
    named = None if guided is None else guided.model
    # «No model» is a ``None`` from the CLI and an empty text from the console's form: the same.
    if (body.model or None) != named:
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
            "on_the_core": terms.on_the_core,
            "by_value": terms.by_value,
        },
        "expires_at": grant.expires_at.isoformat(),
        "days": body.days,
        "uses": grant.max_uses,
    }
    payload.update(_values_audited(grant))
    await _audit(
        ela,
        identity.actor,
        AuditEventType.AUTHORIZATION_GRANTED,
        grant,
        f"grant: policy {grant.id} for {spec.id}, {amount(body.days, 'day', 'days')}",
        payload,
    )
    return await _out(grant, ela)


def _values_audited(grant: Authorization) -> dict[str, JsonValue]:
    """What the audit of a birth says of the second dimension (M13.15, ADR 0071; decision 10,
    answer 44): **how many** values, always — read from what the birth showed, never from the ids
    —, and the values themselves only for sites. An entry of the vault: the count alone, neither
    its id nor its name."""
    assert grant.bounds is not None  # a policy
    shown = shown_of(grant)
    if grant.bounds.terms.by_value is None or shown is None:
        return {}
    said: dict[str, JsonValue] = {"values": len(shown[1])}
    if grant.bounds.terms.by_value == "site":
        said["sites"] = list(shown[1])
    return said


def running_of(grant: Authorization) -> str | None:
    """What a revocation of ``grant`` says goes on (M13.15, ADR 0071; decision 20, answer 40),
    derived from the terms the policy was born under: the session, for a policy whose declaration
    names a model's route — a guided session —; and the reads, for one that also ``covers``
    them. ``None`` for every other policy: nothing it covered goes on."""
    assert grant.bounds is not None  # a policy
    if grant.bounds.terms.route is None:
        return None
    if grant.bounds.covers is None:
        return SESSION_GOES_ON
    return f"{SESSION_GOES_ON}. {READS_GO_ON}"


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
    uses = await ela.authorizations.uses(grant.id)
    state = state_of(grant, now, uses=uses)
    if state in (PolicyState.EXPIRED, PolicyState.EXHAUSTED):
        raise PolicyNotLiveError(grant, state, uses)
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
    return RevokedOut(policy=await _out(gone, ela), running=running_of(gone))


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
