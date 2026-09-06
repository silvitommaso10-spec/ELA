"""``DeviceRegistryPort`` on SQLAlchemy (port in :mod:`ela.ports`, spec §16; ADR 0006, 0016).

A node is inserted once and replaced explicitly, the two operations the port names apart: the
UNIQUE on ``id`` makes a second ``register`` an ``AlreadyExistsError`` at the database, and
``update`` is one statement whose ``rowcount`` says whether the node was there. Nothing here
judges availability — the deadline of a heartbeat lives in
:class:`~ela.devices.registry.DeviceRegistry`, above the port (ADR 0016 §3); this table stores
what it is told.
"""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from ela.domain import Device, DeviceId
from ela.infrastructure.persistence.engine import make_session_factory
from ela.infrastructure.persistence.mappers import device_to_row, device_values, row_to_device
from ela.infrastructure.persistence.orm import DeviceRow
from ela.ports import AlreadyExistsError, NotFoundError

__all__ = ["SqlDeviceRegistry"]

DEVICE = "device"


class SqlDeviceRegistry:
    """The nodes of §16 in ``devices`` (port ``DeviceRegistryPort``)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._sessions = make_session_factory(engine)

    @property
    def engine(self) -> AsyncEngine:
        """The engine this registry is bound to."""
        return self._engine

    async def register(self, device: Device) -> None:
        async with self._sessions() as session, session.begin():
            session.add(device_to_row(device))
            try:
                await session.flush()
            except IntegrityError:
                raise AlreadyExistsError(DEVICE, device.id) from None

    async def update(self, device: Device) -> None:
        values: dict[str, Any] = device_values(device)
        async with self._sessions() as session, session.begin():
            result = await session.execute(
                update(DeviceRow).where(DeviceRow.id == device.id).values(**values)
            )
            if cast(CursorResult[Any], result).rowcount == 0:
                raise NotFoundError(DEVICE, device.id)

    async def get(self, device_id: DeviceId) -> Device:
        async with self._sessions() as session:
            row = await session.scalar(select(DeviceRow).where(DeviceRow.id == device_id))
            if row is None:
                raise NotFoundError(DEVICE, device_id)
            return row_to_device(row)

    async def devices(self) -> tuple[Device, ...]:
        query = select(DeviceRow).order_by(DeviceRow.seq)
        async with self._sessions() as session:
            rows = await session.scalars(query)
            return tuple(row_to_device(row) for row in rows)
