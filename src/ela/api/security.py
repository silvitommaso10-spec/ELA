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
from uuid import UUID

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from ela.api.problems import problem
from ela.composition import Ela
from ela.devices import LOCAL_USER, Rejection, fingerprint
from ela.domain import Actor, ActorKind, DeviceId
from ela.ports import NotFoundError

__all__ = [
    "CODE_ROUTES",
    "NODE_ROUTES",
    "SCHEME",
    "SEPARATOR",
    "UNAUTHORIZED",
    "Anonymous",
    "Identity",
    "Kind",
    "authorized",
    "count",
    "identity_middleware",
    "unauthorized",
]

SCHEME = "bearer"
"""``Authorization: Bearer <credential>``."""
UNAUTHORIZED = "unauthorized"
"""The error code of every refusal here, whatever the reason was."""
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

Call = Callable[[Request], Awaitable[Response]]


class Kind(StrEnum):
    """Which of the three identities the middleware resolved (D10)."""

    CORE = "core"
    NODE = "node"
    CODE = "code"


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


@dataclass(frozen=True, slots=True)
class Identity:
    """Who the middleware resolved for this request, as the routes read it (ADR 0037 §3)."""

    kind: Kind
    device_id: DeviceId | None = None
    code: str | None = None

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
        content=problem(UNAUTHORIZED, "a valid bearer token is required"),
        headers={"WWW-Authenticate": "Bearer"},
    )


def count(request: Request, reason: Anonymous) -> JSONResponse:
    """Refuse an anonymous request, and count why, for ``/diagnostics`` (ADR 0037 §13)."""
    refused: Counter[str] = request.app.state.refused
    refused[reason.value] += 1
    return unauthorized()


def identity_middleware(ela: Ela) -> Callable[[Request, Call], Awaitable[Response]]:
    """The middleware that resolves who is calling, or refuses the request."""
    token = ela.settings.api.token

    async def guard(request: Request, call_next: Call) -> Response:
        route = (request.method, request.url.path)
        header = request.headers.get("authorization")
        credential = _credential(header)
        if credential is None:
            return count(request, Anonymous.MISSING)
        if authorized(header, token):
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


async def _node(
    ela: Ela, request: Request, route: tuple[str, str], claimed: str, secret: str
) -> Identity | Response:
    """A node's identity, or the refusal — written if it names a node that exists."""
    try:
        device_id = DeviceId(UUID(claimed))
    except ValueError:
        return count(request, Anonymous.UNKNOWN_CREDENTIAL)
    try:
        secret_hash = await ela.devices.secret_hash(device_id)
    except NotFoundError:
        return count(request, Anonymous.UNKNOWN_NODE)
    # ``or ""`` and not ``is None``: ``local`` keeps no hash, and a comparison with nothing is the
    # same constant-time refusal as one with the wrong hash (rule 31 watches both names here).
    presented_hash = fingerprint(secret)
    if not secrets.compare_digest(presented_hash.encode(), (secret_hash or "").encode()):
        await ela.devices.reject(device_id, Rejection.BAD_SECRET)
        return unauthorized()
    if (await ela.devices.get(device_id)).revoked_at is not None:
        await ela.devices.reject(device_id, Rejection.REVOKED)
        return unauthorized()
    if route not in NODE_ROUTES:
        await ela.devices.reject(device_id, Rejection.ROUTE_NOT_ALLOWED)
        return unauthorized()
    return Identity(Kind.NODE, device_id=device_id)
