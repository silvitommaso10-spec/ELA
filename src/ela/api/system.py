"""Health and diagnostics (spec §54): is ELA alive, and how is it put together right now.

``/health`` reads through a port, so "alive" means the database answered and not merely that a
process is listening. ``/diagnostics`` says how this ELA is composed — never a secret (not the
API token, not the provider key) and never the user's content (no goals, no arguments, no
output): it answers *what ELA is wired to*, not *what ELA is doing* (ADR 0023 §6).
"""

from __future__ import annotations

from importlib.metadata import version

from fastapi import APIRouter, Request

from ela.api.deps import ElaDep
from ela.api.errors import DatabaseUnavailableError
from ela.api.schemas import DiagnosticsOut, HealthOut
from ela.tasks.engine import RecoverySummary

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
    )
