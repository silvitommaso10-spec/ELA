"""The gateway of a guided session, on ELA's own port (M14.3, ADR 0060; decision 5).

One route, ``POST /sessions/<step>/v1/messages``: the path Claude Code calls when its
``ANTHROPIC_BASE_URL`` is the session's gateway. The middleware has resolved the session already —
its token, from this machine, while it is open (``api/security.py``) —; the route hands the body
to the room of the sessions, which weighs the call against the reservation and forwards it only if
admitted, and passes the answer back **event by event**. Nothing of the body is read here: the
user's sentence and the pages are in it (§57).

Every other path of a session — ``count_tokens``, ``HEAD /api/hello``, ``GET /v1/models`` — has no
route, and is refused without stopping anything: ``count_tokens`` would send the content out once
more, and the other two are of service.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from ela.api.deps import ElaDep
from ela.domain import ErrorMetadata, StepId
from ela.executive.sessions import SESSIONS_PATH

__all__ = ["BETA_HEADER", "REFUSED_STATUS", "router"]

router = APIRouter(prefix=SESSIONS_PATH, tags=["sessions"])

BETA_HEADER = "anthropic-beta"
"""The one header of the session's request passed on: what the provider must know of the call."""

REFUSED_STATUS = 400
"""How a call the room refused is answered: in the provider's own shape of an error, so that the
session reads it as one — and the room has already stopped the session."""


@router.post("/{session}/v1/messages")
async def messages(session: UUID, request: Request, ela: ElaDep) -> Response:
    """One call of the session: admitted and forwarded, or refused before the network."""
    relayed = await ela.sessions.relay(
        StepId(session), await request.body(), request.headers.get(BETA_HEADER)
    )
    if isinstance(relayed, ErrorMetadata):
        return JSONResponse(
            status_code=REFUSED_STATUS,
            content={
                "type": "error",
                "error": {"type": "invalid_request_error", "message": relayed.message},
            },
        )
    return StreamingResponse(
        relayed.chunks, status_code=relayed.status, media_type=relayed.content_type
    )
