"""Who is calling: three identities, one middleware (spec §58; ADR 0023 §7; ADR 0037 §3, §4).

Until M12.1 one static token opened the local API: one token, one identity (§2.1), on loopback.
Since M12.1 the middleware recognises three (D10), all through the same header:

* **the Core** — ``Bearer <ELA_API_TOKEN>`` — on every route but the ones that speak *as* a node;
  it becomes the user at this machine (:data:`~ela.devices.local.LOCAL_USER`);
* **a node** — ``Bearer <device_id>.<secret>`` — on the node's routes only (:data:`NODE_ROUTES`);
* **an enrollment code** — ``Bearer <code>`` — on ``POST /nodes/enroll`` only, and once.

The check is a **middleware** and not a dependency: a dependency can be forgotten on a new route,
a middleware cannot — so a path that does not exist answers ``401`` too, and a route M12.2 adds
without extending :data:`NODE_ROUTES` answers ``401`` to a node, which is the safe direction.
Every way of failing gets **the same** ``401``: a ``403`` would tell "you are not allowed" from
"you are not known", and that difference is information (ADR 0023 §7).

The identity it resolves travels with the request, on ``request.state``, and the routes read it
from there and never from the header: this is the only module of ``ela.api`` that reads it
(architecture rule 47). It is also the only one that compares a credential, in constant time
(rule 31): the Core's token as bytes, a node's secret as the SHA-256 the registry keeps.

What is written and what is counted (ADR 0037 §13): a refusal that names a node that exists — a
wrong secret, a revoked node, a node on a route that is not its own — is ``DEVICE_REJECTED`` in
the audit; one that names nothing is anonymous, and is counted by reason in the memory of this
process for ``/diagnostics`` — reset at every start, and declared so.
"""

from __future__ import annotations

import secrets
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Final
from urllib.parse import parse_qsl
from uuid import UUID

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from ela.api import pages
from ela.api.problems import problem
from ela.composition import Ela
from ela.devices import LOCAL_USER, Rejection, fingerprint
from ela.domain import Actor, ActorKind, DeviceId, DeviceRole, PrivacyLevel
from ela.ports import NotFoundError, WireCode

__all__ = [
    "CODE_ROUTES",
    "COMPANION_CODE_ROUTES",
    "COMPANION_PREFIX",
    "COMPANION_ROUTES",
    "COOKIE_MAX_AGE",
    "NODE_ROUTES",
    "SCHEME",
    "SEPARATOR",
    "Anonymous",
    "Identity",
    "Kind",
    "authorized",
    "count",
    "forgotten",
    "identity_middleware",
    "note",
    "same_origin",
    "unauthorized",
    "welcome",
]

SCHEME = "bearer"
"""``Authorization: Bearer <credential>``."""
AUTHORIZATION_HEADER: Final = "authorization"
"""The header a machine presents an identity in — and the one a browser cannot set (dec. C.1)."""
SEPARATOR: Final = "."
"""Between a node's id and its secret: it is in neither a ``token_urlsafe`` nor a UUID."""
NODE_ROUTES: Final = frozenset(
    {
        ("GET", "/nodes/me"),
        ("POST", "/nodes/heartbeat"),
        ("PUT", "/nodes/me"),
        ("POST", "/nodes/work"),
        ("POST", "/nodes/work/result"),
        ("POST", "/nodes/work/renew"),
    }
)
"""What an identity of a node may call (ADR 0037 §4, C3): a closed list, M12.2 and M12.3 extend it.

Six, and every pair is **literal**: the middleware compares the concrete path of the request, so
the id of an assignment travels in the **body** (ADR 0038 §11, the user's decision of 2026-09-11).
With ``/nodes/work/{assignment_id}/result`` a node would have been refused here — and the Core's
token would not have been stopped — while two tests of M12.1 stayed green: teaching the middleware
templates would have been "a defence that looks active". So ADR 0037 §4, «no id in a node's
routes», stays literally true, and the middleware is untouched.
"""
CODE_ROUTES: Final = frozenset({("POST", "/nodes/enroll")})
"""The one route an enrollment code opens."""

COMPANION_PREFIX: Final = "/companion/"
"""Where the pages live, and the one prefix whose refusals are pages (M12.5 dec. C.3, D)."""
COMPANION_ROUTES: Final = frozenset(
    {
        ("GET", "/companion/"),
        ("GET", "/companion/approval"),
        ("POST", "/companion/answer"),
        ("GET", "/companion/tokens.css"),
        ("GET", "/companion/components.css"),
    }
)
"""What an identity that carries the cookie may call: literal pairs, like :data:`NODE_ROUTES`.

The reason is ADR 0038 §11's: teaching the middleware a template would be «a defence that looks
active», so an id travels in the query or in the body and never in a path (M12.5 dec. D).
"""
COMPANION_CODE_ROUTES: Final = frozenset({("POST", "/companion/enroll")})
"""The one route a companion's code opens, and the one route where a **form** carries it.

Rule 1 of dec. C.3: on this route neither a header nor a cookie is looked at, because an iPhone
whose cookie was revoked has to be able to enrol again — and the credential a browser can present
in a form is the code.
"""
COMPANION_COOKIE: Final = "ela_companion"
"""The name of the cookie that carries a companion's credential (dec. C.1).

Read and written **here** and nowhere else in ``ela.api`` (architecture rule 47): a second place
that wrote it would be a second place that decides who is calling, and the one that forgets a
revocation.
"""
COOKIE_MAX_AGE: Final = 400 * 24 * 60 * 60
"""Four hundred days, the ceiling draft RFC 6265bis asks browsers to enforce: past it the iPhone
enrols again. Longer would be a number the browser silently shortens."""
CODE_FIELD: Final = "code"
"""The field of the enrolment form that carries the code (dec. C.3, rule 1)."""
SET_COOKIE: Final = "set-cookie"
ORIGIN: Final = "origin"
ENROL_AGAIN: Final = "Incolla qui il codice che hai coniato al Mac."
"""What the enrolment page says when nobody is known: it asks, and tells nothing else."""
NOT_HERE: Final = "questa richiesta non arriva da una pagina di ELA"
"""The refusal of a form that came from somewhere else (dec. C.1)."""

Call = Callable[[Request], Awaitable[Response]]


class Kind(StrEnum):
    """Which identity the middleware resolved (D10; M12.5 dec. A for the fourth)."""

    CORE = "core"
    NODE = "node"
    CODE = "code"
    COMPANION = "companion"
    """A browser that carries the cookie of an identity enrolled as ``COMPANION``.

    A fourth kind and not a second flavour of ``NODE``: the bearer is part of the role, so a
    node's credential in a cookie and a companion's in a header are both refused (dec. A).
    """


class Anonymous(StrEnum):
    """Why a request that named no node that exists was refused: counted, never written."""

    MISSING = "missing"
    """No credential at all."""
    UNKNOWN_CREDENTIAL = "unknown_credential"
    """Neither the Core's token nor a node's credential, where a code is not accepted."""
    UNKNOWN_NODE = "unknown_node"
    """The shape of a node's credential, for an id nobody enrolled."""
    UNKNOWN_CODE = "unknown_code"
    """A code nobody issued."""
    EXPIRED_CODE = "expired_code"
    """A code past its expiry, never spent."""
    CORE_ON_A_NODE_ROUTE = "core_on_a_node_route"
    """The Core's token on a route that speaks as a node: the Core is not a node (ADR 0037 §4)."""
    CORE_ON_A_COMPANION_ROUTE = "core_on_a_companion_route"
    """The Core's token on a page of the companion: the Core is not a browser (M12.5 dec. C.3).

    A reason of its own and not ``core_on_a_node_route``, which would lie in the name — and the
    name is what somebody reads in ``/diagnostics`` a month later.
    """
    NOT_FROM_ELA = "not_from_ela"
    """A form under the prefix that did not come from a page of ELA: no ``Origin``, or another
    site's (dec. C.1). The measures saw it present from Safari, from the web app and from
    Chrome."""


@dataclass(frozen=True, slots=True)
class Identity:
    """Who the middleware resolved for this request, as the routes read it (ADR 0037 §3)."""

    kind: Kind
    device_id: DeviceId | None = None
    code: str | None = None
    role: DeviceRole | None = None
    """What this identity is, for whoever needs to know which routes it may call (M12.5 dec. A)."""
    privacy: PrivacyLevel | None = None
    """The ceiling the user imposed on this identity at enrolment (M12.5 dec. F.2).

    Carried here because the middleware already holds the row when it checks the revocation: a
    page that had to read the registry again would be a page reading the world, which rule 55
    forbids — and the ceiling is a fact of *who is calling*, which is what this class is.
    """

    @property
    def actor(self) -> Actor:
        """Who signs what this identity does: the user at this machine, or the node itself."""
        if self.kind is Kind.CORE:
            return LOCAL_USER
        return Actor(kind=ActorKind.DEVICE, id=str(self.node))

    @property
    def node(self) -> DeviceId:
        """The node this identity is; only a node's identity has one."""
        if self.device_id is None:
            raise ValueError(f"a {self.kind.value} identity is not a node")
        return self.device_id


def _credential(header: str | None) -> str | None:
    """What a ``Bearer`` header presents, or ``None`` for anything else."""
    if header is None:
        return None
    scheme, _, credential = header.partition(" ")
    if scheme.lower() != SCHEME:
        return None
    return credential.strip() or None


def authorized(header: str | None, token: str) -> bool:
    """Whether ``header`` presents ``token``, compared in constant time.

    The comparison is on bytes: ``compare_digest`` refuses non-ASCII strings, and a token typed
    with an accented character would otherwise raise instead of being rejected.
    """
    credential = _credential(header)
    if credential is None:
        return False
    return secrets.compare_digest(credential.encode(), token.encode())


def unauthorized() -> JSONResponse:
    """The one answer every refusal gets: the same status, the same body, the same header."""
    return JSONResponse(
        status_code=401,
        content=problem(WireCode.UNAUTHORIZED, "a valid bearer token is required"),
        headers={"WWW-Authenticate": "Bearer"},
    )


def note(request: Request, reason: Anonymous) -> None:
    """Count why an anonymous request was refused, for ``/diagnostics`` (ADR 0037 §13).

    Split from :func:`count` in M12.5: under the prefix the same refusal is a **page**, and the
    counter must not depend on which body the caller gets.
    """
    refused: Counter[str] = request.app.state.refused
    refused[reason.value] += 1


def count(request: Request, reason: Anonymous) -> JSONResponse:
    """Refuse an anonymous request, and count why, for ``/diagnostics`` (ADR 0037 §13)."""
    note(request, reason)
    return unauthorized()


def enrolment(request: Request, reason: Anonymous, *, message: str = ENROL_AGAIN) -> Response:
    """The ``401`` of the companion: the enrolment form, counted like every other refusal.

    **The same page whatever the path** under the prefix (dec. C.3, rule 3), so that knocking
    without a credential teaches only that the prefix asks for a code — which the JSON of the
    other ``401`` already says of ELA.
    """
    note(request, reason)
    return pages.page("enrol", status=401, styled=False, message=message)


def forgotten(response: Response) -> Response:
    """``response``, telling the browser to drop a cookie that is worth nothing any more.

    Only for a cookie that was **presented and failed** (dec. C.3, rule 3, second case). A request
    that presented none gets the same page **without** this: P1 measured that a browser can hold a
    good cookie back — ``Strict`` did not arrive after the iPhone restarted, and the cookie was
    there — so clearing on nothing would destroy a credential that works and send the user back
    to the Mac to enrol again.
    """
    response.headers.append(SET_COOKIE, f"{COMPANION_COOKIE}=; Max-Age=0; Path={COMPANION_PREFIX}")
    return response


def welcome(device_id: DeviceId, secret: str) -> Response:
    """The answer that hands a browser its credential, once: the cookie, and the home page.

    ``HttpOnly`` so no script can read it — there are none, and the policy forbids them, but the
    flag costs nothing and outlives both. ``SameSite=Lax`` because P1 measured ``Strict`` being
    held back in the two ways the page is actually opened, the notification's tap and the
    Shortcut, while ``Lax`` arrived every time (dec. C.1). No ``Secure``: the tailnet is the
    encryption (ADR 0037 §2), and Safari accepts ``Secure`` on ``http`` only for the loopback.
    ``Path`` keeps it off the icons the browser asks for by itself, which P1 also measured.
    """
    return Response(
        status_code=303,
        headers={
            "Location": COMPANION_PREFIX,
            SET_COOKIE: (
                f"{COMPANION_COOKIE}={device_id}{SEPARATOR}{secret}; HttpOnly; SameSite=Lax; "
                f"Path={COMPANION_PREFIX}; Max-Age={COOKIE_MAX_AGE}"
            ),
        },
    )


def same_origin(request: Request) -> bool:
    """Whether this form came from a page of ELA (dec. C.1).

    ``SameSite=Lax`` already keeps the cookie off a ``POST`` born on another site; this is the
    second half, and it is the one that does not depend on the browser's default. An absent
    ``Origin`` is a no: the measures saw it present from Safari, from the web app of the home
    screen and from Chrome, so refusing it costs nothing and guessing would.
    """
    origin = request.headers.get(ORIGIN)
    return origin is not None and origin.rstrip("/") == str(request.base_url).rstrip("/")


def identity_middleware(ela: Ela) -> Callable[[Request, Call], Awaitable[Response]]:
    """The middleware that resolves who is calling, or refuses the request.

    The four rules of M12.5 dec. C.3, **in this order**: the enrolment form of the companion,
    which looks at neither a header nor a cookie; a request that presents a header, resolved as it
    always was; a request with no header under the prefix, resolved from the cookie; everything
    else, the ``401`` of today.
    """
    token = ela.settings.api.token

    async def guard(request: Request, call_next: Call) -> Response:
        route = (request.method, request.url.path)
        if route in COMPANION_CODE_ROUTES:
            return await _from_the_form(request, call_next)
        header = request.headers.get(AUTHORIZATION_HEADER)
        credential = _credential(header)
        if credential is None and request.url.path.startswith(COMPANION_PREFIX):
            return await _from_the_cookie(ela, request, route, call_next)
        if credential is None:
            return count(request, Anonymous.MISSING)
        if authorized(header, token):
            if route in COMPANION_ROUTES | COMPANION_CODE_ROUTES:
                return count(request, Anonymous.CORE_ON_A_COMPANION_ROUTE)
            if route in NODE_ROUTES | CODE_ROUTES:
                return count(request, Anonymous.CORE_ON_A_NODE_ROUTE)
            request.state.identity = Identity(Kind.CORE)
            return await call_next(request)
        claimed, separator, secret = credential.partition(SEPARATOR)
        if separator:
            resolved = await _node(ela, request, route, claimed, secret)
            if isinstance(resolved, Response):
                return resolved
            request.state.identity = resolved
            return await call_next(request)
        if route in CODE_ROUTES:
            request.state.identity = Identity(Kind.CODE, code=credential)
            return await call_next(request)
        return count(request, Anonymous.UNKNOWN_CREDENTIAL)

    return guard


async def _from_the_form(request: Request, call_next: Call) -> Response:
    """Rule 1: ``POST /companion/enroll`` resolves the ``code`` of the form, and nothing else.

    Not the header, not the cookie: an iPhone whose credential was revoked has to be able to enrol
    again, and the one thing a browser can carry here is what the user pasted. The body is read
    here and reaches the route whole — Starlette replays what a middleware consumed, and a test of
    its own pins that promise (``tests/api/test_security.py``).
    """
    if not same_origin(request):
        return _not_from_ela(request)
    code = _form(await request.body()).get(CODE_FIELD, "").strip()
    if not code:
        return enrolment(request, Anonymous.MISSING)
    request.state.identity = Identity(Kind.CODE, code=code, role=DeviceRole.COMPANION)
    return await call_next(request)


async def _from_the_cookie(
    ela: Ela, request: Request, route: tuple[str, str], call_next: Call
) -> Response:
    """Rule 3: under the prefix, with no header, the cookie is the bearer — of companions only.

    Three ends, and they are different on purpose (dec. C.3, and the two reviews):

    * **a cookie that fails** — unknown, wrong secret, revoked, or a *node's* credential put in a
      cookie — gets the enrolment page and the clearing of that cookie, because it is worth
      nothing;
    * **no cookie at all** gets the same page **without** the clearing: a browser can hold a good
      cookie back (P1), and clearing on nothing would destroy a credential that works;
    * **a good companion on a path that is not one of its routes** gets a ``404`` and keeps its
      cookie: whoever presents a credential that works already knows they have one, so there is
      nothing to hide — and the enrolment form would invite them to leave the old identity alive
      in the registry with a secret nobody holds any more.
    """
    if request.method != "GET" and not same_origin(request):
        return _not_from_ela(request)
    # ``cookie`` and not ``presented``: rule 31 watches the names a secret goes by inside this
    # module, and what is in hand here is the *carrier*. What it carries is ``secret``, and the
    # only thing done to it is the constant-time comparison below.
    cookie = request.cookies.get(COMPANION_COOKIE)
    if cookie is None:
        return enrolment(request, Anonymous.MISSING)
    claimed, separator, secret = cookie.partition(SEPARATOR)
    if not separator:
        return forgotten(enrolment(request, Anonymous.UNKNOWN_CREDENTIAL))
    try:
        device_id = DeviceId(UUID(claimed))
    except ValueError:
        return forgotten(enrolment(request, Anonymous.UNKNOWN_CREDENTIAL))
    try:
        secret_hash = await ela.devices.secret_hash(device_id)
    except NotFoundError:
        return forgotten(enrolment(request, Anonymous.UNKNOWN_NODE))
    if not _proves(secret, secret_hash):
        await ela.devices.reject(device_id, Rejection.BAD_SECRET)
        return forgotten(_page_401(request))
    device = await ela.devices.get(device_id)
    if device.revoked_at is not None:
        await ela.devices.reject(device_id, Rejection.REVOKED)
        return forgotten(_page_401(request))
    if device.role is not DeviceRole.COMPANION:
        await ela.devices.reject(device_id, Rejection.ROUTE_NOT_ALLOWED)
        return forgotten(_page_401(request))
    if route not in COMPANION_ROUTES:
        await ela.devices.reject(device_id, Rejection.ROUTE_NOT_ALLOWED)
        return pages.page("missing", status=404)
    request.state.identity = Identity(
        Kind.COMPANION, device_id=device_id, role=device.role, privacy=device.privacy
    )
    await ela.devices.contacted(device_id)
    return await call_next(request)


def _page_401(request: Request) -> Response:
    """The enrolment page for a credential that named a node that exists: written, not counted.

    The audit already holds the ``DEVICE_REJECTED`` (ADR 0037 §13), and counting it as anonymous
    too would say the same refusal twice in two vocabularies.
    """
    return pages.page("enrol", status=401, styled=False, message=ENROL_AGAIN)


def _not_from_ela(request: Request) -> Response:
    """A form that did not come from a page of ELA: refused, counted, and said as a page."""
    note(request, Anonymous.NOT_FROM_ELA)
    return pages.page("refused", status=403, title="Rifiutata", text=NOT_HERE)


def _form(body: bytes) -> dict[str, str]:
    """The fields of an ``application/x-www-form-urlencoded`` body, with the standard library."""
    return dict(parse_qsl(body.decode("utf-8", "replace")))


def _proves(secret: str, secret_hash: str | None) -> bool:
    """Whether ``secret`` is the one the registry keeps the hash of, compared in constant time.

    One place for both bearers (M12.5): the header and the cookie carry the same credential in two
    envelopes, and a second comparison would be a second chance to write it in variable time —
    which is the whole of rule 31.

    ``or ""`` and not ``is None``: ``local`` keeps no hash, and a comparison with nothing is the
    same constant-time refusal as one with the wrong hash.
    """
    presented_hash = fingerprint(secret)
    return secrets.compare_digest(presented_hash.encode(), (secret_hash or "").encode())


async def _node(
    ela: Ela, request: Request, route: tuple[str, str], claimed: str, secret: str
) -> Identity | Response:
    """A node's identity, or the refusal — written if it names a node that exists.

    Since M12.5 the role is checked here too: only a ``WORKER`` may speak through the header, on
    the routes of :data:`NODE_ROUTES`. A ``COMPANION`` is refused before the routes are looked at,
    because what is wrong is not *where* it is calling but *how*.
    """
    try:
        device_id = DeviceId(UUID(claimed))
    except ValueError:
        return count(request, Anonymous.UNKNOWN_CREDENTIAL)
    try:
        secret_hash = await ela.devices.secret_hash(device_id)
    except NotFoundError:
        return count(request, Anonymous.UNKNOWN_NODE)
    if not _proves(secret, secret_hash):
        await ela.devices.reject(device_id, Rejection.BAD_SECRET)
        return unauthorized()
    device = await ela.devices.get(device_id)
    if device.revoked_at is not None:
        await ela.devices.reject(device_id, Rejection.REVOKED)
        return unauthorized()
    if device.role is not DeviceRole.WORKER:
        # The bearer is part of the role (M12.5 dec. A): a companion's secret in a header is
        # refused wherever it is presented, and the audit says why — ``route_not_allowed``, the
        # reason of an identity on ground that is not its own.
        await ela.devices.reject(device_id, Rejection.ROUTE_NOT_ALLOWED)
        return unauthorized()
    if route not in NODE_ROUTES:
        await ela.devices.reject(device_id, Rejection.ROUTE_NOT_ALLOWED)
        return unauthorized()
    return Identity(Kind.NODE, device_id=device_id)
