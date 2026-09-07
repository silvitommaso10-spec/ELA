"""The static token that opens the local API (spec §58; ADR 0023 §7).

One token, one identity (§2.1), on loopback. The check is a **middleware** and not a dependency:
a dependency can be forgotten on a new route, a middleware cannot — and so a path that does not
exist answers ``401`` too, which means an unauthenticated caller cannot even learn which routes
ELA has.

A missing token and a wrong one get the same answer: a ``403`` would tell the difference between
"you are not allowed" and "you are not known", and that difference is information.
"""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from ela.api.problems import problem

__all__ = ["SCHEME", "UNAUTHORIZED", "authorized", "token_middleware"]

SCHEME = "bearer"
"""``Authorization: Bearer <token>``."""
UNAUTHORIZED = "unauthorized"
"""The error code of every refusal here, whatever the reason was."""

Call = Callable[[Request], Awaitable[Response]]


def authorized(header: str | None, token: str) -> bool:
    """Whether ``header`` presents ``token``, compared in constant time.

    The comparison is on bytes: ``compare_digest`` refuses non-ASCII strings, and a token typed
    with an accented character would otherwise raise instead of being rejected.
    """
    if header is None:
        return False
    scheme, _, presented = header.partition(" ")
    if scheme.lower() != SCHEME:
        return False
    return secrets.compare_digest(presented.strip().encode(), token.encode())


def token_middleware(token: str) -> Callable[[Request, Call], Awaitable[Response]]:
    """The middleware that lets a request through only if it carries ``token``."""

    async def guard(request: Request, call_next: Call) -> Response:
        if not authorized(request.headers.get("authorization"), token):
            return JSONResponse(
                status_code=401,
                content=problem(UNAUTHORIZED, "a valid bearer token is required"),
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await call_next(request)

    return guard
