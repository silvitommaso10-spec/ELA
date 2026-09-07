"""The nodes ELA can operate through, read-only (spec §16, §56; ADR 0024 §5).

``/diagnostics`` says how ELA is composed and names the nodes in one word each; this says what
the registry actually knows about them — what each one runs, which tools it has, when it was last
heard from — which is what a person asking "why is this task waiting" needs to see.

Availability is **derived**, never the stored column (architecture rule 20, ADR 0016 §3): the
route asks the registry twice, once for every node and once for the ones still worth using, and
reports the answer rather than the field.
"""

from __future__ import annotations

from fastapi import APIRouter

from ela.api.deps import ElaDep
from ela.api.schemas import DeviceOut

__all__ = ["router"]

router = APIRouter(tags=["devices"])


@router.get("/devices")
async def list_devices(ela: ElaDep) -> tuple[DeviceOut, ...]:
    """Every registered node, in registration order, all judged against the same instant."""
    usable = {device.id for device in await ela.devices.available()}
    return tuple(
        DeviceOut.of(device, available=device.id in usable)
        for device in await ela.devices.devices()
    )
