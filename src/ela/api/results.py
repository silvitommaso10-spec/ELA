"""What the tools produced, read back (spec §57, §63; M8.3, ADR 0025 §4).

This is the one route of ELA that returns the user's **content**: the text a model answered, the
body a note was written with. Everywhere else the API says what happened — states, decisions,
audit entries — and §32 keeps the trail free of content on purpose (architecture rule 23).

It is a route and not an afterthought on ``GET /tasks/{id}`` because the two answer different
questions: that one says where a task stands, this one says what it made. Before M8.3 the second
question had no answer at all, so a plan could complete and show nothing — which, on a plan whose
only step asks a model, reads exactly like ELA not working.

The content stays on loopback, behind the user's token, and reaches nobody else: architecture
rule 29 keeps ``output`` to a single response model, so a field added to another schema cannot
carry it out through a route that was never meant to.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from ela.api.deps import ElaDep
from ela.api.schemas import ExecutionResultOut
from ela.domain import TaskId

__all__ = ["router"]

router = APIRouter(prefix="/tasks", tags=["results"])


@router.get("/{task_id}/results")
async def read_results(task_id: UUID, ela: ElaDep) -> tuple[ExecutionResultOut, ...]:
    """Every result this task produced, in insertion order; empty if it produced none.

    The task is read first, so an id nobody knows is a ``404`` and not an empty list: "this task
    has no results" and "there is no such task" are different answers, and a caller that cannot
    tell them apart has to guess.
    """
    await ela.repository.get(TaskId(task_id))
    results = await ela.results.for_task(TaskId(task_id))
    return tuple(ExecutionResultOut.of(result) for result in results)
