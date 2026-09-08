"""What is going on right now, composed in one instant (spec §44; M10.4, ADR 0032).

One route, and it **observes**, for the reason ``/perception`` observes: somebody asking what is
happening wants the answer of now, not the answer of the last cadence. What a tick actually
re-reads is the cadence's business, so this costs one helper process at most and nothing when
nothing is due.

The line against ``/diagnostics`` is that route's own docstring — it says *what ELA is wired to*,
not *what ELA is doing*. ``/context`` is the other half of that sentence, and neither grows into
the other.

It carries **state**, plus the one piece of user content that was decided rather than inherited:
the goals of the tasks, which ``GET /tasks`` already returns to this reader under this token
(ADR 0032 §5). No screen text, no capture, no step arguments, no execution output — answering
"what is the user doing" by reading the screen costs a capability, and what costs a capability is
not context (architecture rule 38).
"""

from __future__ import annotations

from fastapi import APIRouter

from ela.api.deps import ElaDep
from ela.api.schemas import ContextOut

__all__ = ["router"]

router = APIRouter(tags=["context"])


@router.get("/context")
async def context(ela: ElaDep) -> ContextOut:
    """Look, then compose: the seven questions of §44 with their answers and their absences."""
    await ela.perception.tick()
    snapshot = await ela.context.assemble(ela.perception.view)
    return ContextOut(
        at=snapshot.at,
        activity=snapshot.activity,
        device=snapshot.device,
        work=snapshot.work,
        deadlines=snapshot.deadlines,
        recent=snapshot.recent,
        questions=snapshot.questions,
    )
