"""Health and diagnostics (spec §54): is ELA alive, and how is it put together right now.

``/health`` reads through a port, so "alive" means the database answered and not merely that a
process is listening. ``/diagnostics`` says how this ELA is composed — never a secret (not the
API token, not the provider key) and never the user's content (no goals, no arguments, no
output): it answers *what ELA is wired to*, not *what ELA is doing* (ADR 0023 §6).

That line is also what decides how much of perception appears here: the operating-system
permissions, because a missing permission is wiring — it says what ELA *can* do on this machine —
and not the state of the microphone, which is the world and lives on ``/perception``.
"""

from __future__ import annotations

from importlib.metadata import version

from fastapi import APIRouter, Request

from ela.api.deps import ElaDep
from ela.api.errors import DatabaseUnavailableError
from ela.api.schemas import (
    CaptureStoreOut,
    DiagnosticsOut,
    HealthOut,
    PerceptionSummaryOut,
    VoiceOut,
)
from ela.tasks.engine import RecoverySummary
from ela.tools.settings import MAX_SPOKEN_CHARACTERS

__all__ = ["router"]

router = APIRouter(tags=["system"])


@router.get("/health")
async def health(ela: ElaDep) -> HealthOut:
    """Alive, and the database answers. Protected like every other route (ADR 0023 §7)."""
    try:
        await ela.repository.tasks(limit=1)
    except Exception as broken:  # noqa: BLE001 — whatever went wrong, the answer is 503
        raise DatabaseUnavailableError(str(broken)) from broken
    return HealthOut(status="ok", database="ok", now=ela.clock.now())


@router.get("/diagnostics")
async def diagnostics(request: Request, ela: ElaDep) -> DiagnosticsOut:
    """How ELA is composed, and what start-up's ``recover()`` found (ADR 0023 §11)."""
    # ``count`` and not ``tasks()``: this line used to count ten tasks by loading ten, and would
    # have loaded ten thousand (review of M8.1, ADR 0025 §2). What it prints does not change.
    tasks = {state.value: total for state, total in (await ela.repository.count()).items()}

    # Never ``device.availability`` from here: it is derived, and deriving it is the registry's
    # (architecture rule 20). What this asks for is the answer, not the column.
    nodes = {device.name: "unavailable" for device in await ela.devices.devices()}
    for device in await ela.devices.available():
        nodes[device.name] = "available"

    # The last observation, never a fresh one: ``/diagnostics`` says what ELA is wired to and is
    # called by whatever watches ELA, so it must stay free. Looking is ``/perception``'s job.
    seen = ela.perception.view.observation
    held = ela.captures.retained()

    recovered: RecoverySummary = request.app.state.recovery
    return DiagnosticsOut(
        version=version("ela"),
        database=ela.settings.persistence.db_url,
        workspace=str(ela.settings.workspace.workspace_dir),
        user_name=ela.settings.core.user_name,
        providers={name: ela.providers.get(name).status.value for name in ela.providers.names()},
        task_types=tuple(sorted(ela.settings.routing.model_routes)),
        default_profile=ela.settings.routing.model_default_route.profile,
        capabilities=tuple(spec.id for spec in ela.capabilities.specs()),
        tools=tuple(tool.name for tool in ela.tools.tools()),
        devices=nodes,
        tasks=tasks,
        pending_approvals=len(await ela.approvals.pending(now=ela.clock.now())),
        recovered={
            "failed": len(recovered.failed),
            "skipped": len(recovered.skipped),
            "expired": len(recovered.expired),
        },
        perception=PerceptionSummaryOut(
            enabled=ela.settings.perception.perception_enabled,
            watching=ela.settings.perception.loop_enabled,
            observed_at=seen.observed_at,
            permissions=dict(seen.permissions),
            captures=CaptureStoreOut(
                retained=len(held),
                bytes=sum(one.bytes for one in held),
                ttl_seconds=ela.settings.captures.capture_ttl_seconds,
                max_count=ela.settings.captures.capture_max_count,
                max_bytes=ela.settings.captures.capture_max_bytes,
            ),
        ),
        # Asked here, not remembered: ``available`` is two syscalls and makes no sound, so the
        # honest answer is the one from this instant rather than a belief with an age.
        voice=VoiceOut(
            enabled=ela.settings.voice.voice_enabled,
            available=await ela.speech.available(),
            voice=ela.settings.voice.voice_name,
            max_characters=MAX_SPOKEN_CHARACTERS,
            timeout_seconds=ela.settings.voice.voice_timeout_seconds,
        ),
    )
