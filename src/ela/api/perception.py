"""What ELA sees of the machine it runs on (spec §10, §11; M10.1, ADR 0028).

One route, and it observes: a caller asking what the state is wants the answer of now, so the
read runs a tick. What a tick actually re-reads is the cadence's business — a family inside its
interval answers what it last saw, with the ``observed_at`` that says when — so this costs one
helper process at most, and nothing at all when nothing is due.

It reads **state, never content**: no screen, no audio, no window titles. The first route that
carries content will be born with a capability and an authorization, and this one deliberately is
not the precedent for it (ADR 0028 §9).
"""

from __future__ import annotations

from fastapi import APIRouter

from ela.api.deps import ElaDep
from ela.api.schemas import PerceptionOut

__all__ = ["router"]

router = APIRouter(tags=["perception"])


@router.get("/perception")
async def perception(ela: ElaDep) -> PerceptionOut:
    """Look, and answer with what ELA believes and what changed when it last looked."""
    changes = await ela.perception.tick()
    observation = ela.perception.view.observation
    settings = ela.settings.perception
    return PerceptionOut(
        enabled=settings.perception_enabled,
        watching=settings.loop_enabled,
        observed_at=observation.observed_at,
        microphone=observation.microphone,
        camera=observation.camera,
        permissions=dict(observation.permissions),
        display_count=observation.display_count,
        display_asleep=observation.display_asleep,
        screen_locked=observation.screen_locked,
        on_console=observation.on_console,
        idle_seconds=observation.idle_seconds,
        changes=changes,
    )
