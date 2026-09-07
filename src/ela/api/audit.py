"""The audit trail, read-only (spec §32; ADR 0005, ADR 0023 §6, ADR 0024 §4).

There is no way to write here and there never will be: the port has ``append`` and ``read``, the
adapter is append-only at four levels (ADR 0007), and what these routes do is ``read`` and
``verify``.

Verifying is the second question the trail exists to answer (§58): a log nobody can check is a
log that has to be believed. It arrives here through the ``AuditVerifier`` protocol, so this
module still names no adapter (architecture rule 27).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from ela.api.deps import ElaDep
from ela.api.schemas import AuditEventOut, ChainOut
from ela.domain import TaskId

__all__ = ["router"]

router = APIRouter(tags=["audit"])


@router.get("/audit/verify")
async def verify_audit(ela: ElaDep) -> ChainOut:
    """Whether the chain still holds, and the two numbers to anchor outside the log.

    A trail that does not verify is a ``409`` with ``audit.tampered`` and the position of the
    first entry that does not fit: an answer that says *where*, because "something is wrong with
    the log" is not something anybody can act on.
    """
    return ChainOut.of(await ela.audit_verifier.verify())


@router.get("/audit")
async def read_audit(
    ela: ElaDep,
    task_id: UUID | None = None,
    since: datetime | None = None,
    limit: Annotated[int | None, Query(ge=1)] = None,
    newest_first: bool = False,
) -> tuple[AuditEventOut, ...]:
    """Events of one task, from an instant (inclusive), ``limit`` of them.

    ``newest_first`` says from **which end** the log is read, and the answer keeps that order:
    appended order by default, so ``limit`` keeps the first entries; from the end when true, so
    ``limit`` keeps the last ones and they come back newest to oldest. That is what a tail is,
    and taking it by reading the whole window and trimming it is what ``ela audit tail`` did
    until M8.3 (ADR 0024 §6, ADR 0025 §3).

    No event carries the arguments of a call or the output of a tool — not because this route
    strips them, but because an ``AuditEvent`` never holds them (§57, architecture rule 23).
    """
    events = await ela.audit.read(
        task_id=None if task_id is None else TaskId(task_id),
        since=since,
        limit=limit,
        newest_first=newest_first,
    )
    return tuple(AuditEventOut.of(event) for event in events)
