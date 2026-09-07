"""The audit trail, read-only (spec §32; ADR 0005, ADR 0023 §6).

There is no way to write here and there never will be: the port has ``append`` and ``read``, the
adapter is append-only at four levels (ADR 0007), and what this route does is ``read``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from ela.api.deps import ElaDep
from ela.api.schemas import AuditEventOut
from ela.domain import TaskId

__all__ = ["router"]

router = APIRouter(tags=["audit"])


@router.get("/audit")
async def read_audit(
    ela: ElaDep,
    task_id: UUID | None = None,
    since: datetime | None = None,
    limit: Annotated[int | None, Query(ge=1)] = None,
) -> tuple[AuditEventOut, ...]:
    """Events in append order: of one task, from an instant (inclusive), the first ``limit``.

    No event carries the arguments of a call or the output of a tool — not because this route
    strips them, but because an ``AuditEvent`` never holds them (§57, architecture rule 23).
    """
    events = await ela.audit.read(
        task_id=None if task_id is None else TaskId(task_id), since=since, limit=limit
    )
    return tuple(AuditEventOut.of(event) for event in events)
