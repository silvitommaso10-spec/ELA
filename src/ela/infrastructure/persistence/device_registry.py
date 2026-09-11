"""``DeviceRegistryPort`` on SQLAlchemy (port in :mod:`ela.ports`, spec §16; ADR 0006, 0016, 0037).

A node is inserted once and replaced explicitly, the two operations the port names apart: the
UNIQUE on ``id`` makes a second ``register`` an ``AlreadyExistsError`` at the database, and
``update`` is one statement whose ``rowcount`` says whether the node was there. Nothing here
judges availability — the deadline of a heartbeat lives in
:class:`~ela.devices.registry.DeviceRegistry`, above the port (ADR 0016 §3); this table stores
what it is told.

Since M12.1 each half of the row has its own statement, on disjoint columns (ADR 0037 §9): the
announcement writes :data:`~ela.ports.ANNOUNCED_FIELDS` only if the row is still at the revision
the node saw and is not revoked; the observation writes the observed columns it carries; the
revocation writes ``revoked_at`` once. Each is one conditional ``UPDATE``, and when it touches no
row a read in the same transaction names the reason — the safety is in the ``UPDATE``, the
``SELECT`` only names the error (ADR 0012 §5). The hash of a node's secret is a column of the row
and never a field of the entity (architecture rule 46): :meth:`SqlDeviceRegistry.secret_hash` is
its one way out.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from ela.domain import Device, DeviceAvailability, DeviceId, DeviceStatus, PowerSource
from ela.infrastructure.persistence.engine import make_session_factory
from ela.infrastructure.persistence.mappers import device_to_row, device_values, row_to_device
from ela.infrastructure.persistence.orm import DeviceRow
from ela.ports import (
    ANNOUNCED_FIELDS,
    AlreadyExistsError,
    DeviceRevokedError,
    IdentityConflictError,
    NotFoundError,
)

__all__ = ["SqlDeviceRegistry"]

DEVICE = "device"


def _rowcount(result: object) -> int:
    return cast(CursorResult[Any], result).rowcount


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
        await self._insert(device_to_row(device), device.id)

    async def enroll(self, device: Device, *, secret_hash: str) -> None:
        row = device_to_row(device)
        row.secret_hash = secret_hash
        await self._insert(row, device.id)

    async def _insert(self, row: DeviceRow, device_id: DeviceId) -> None:
        async with self._sessions() as session, session.begin():
            session.add(row)
            try:
                await session.flush()
            except IntegrityError:
                raise AlreadyExistsError(DEVICE, device_id) from None

    async def update(self, device: Device) -> None:
        values: dict[str, Any] = device_values(device)
        async with self._sessions() as session, session.begin():
            result = await session.execute(
                update(DeviceRow).where(DeviceRow.id == device.id).values(**values)
            )
            if _rowcount(result) == 0:
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

    async def secret_hash(self, device_id: DeviceId) -> str | None:
        async with self._sessions() as session:
            row = await session.scalar(select(DeviceRow).where(DeviceRow.id == device_id))
            if row is None:
                raise NotFoundError(DEVICE, device_id)
            return row.secret_hash

    async def announce(self, device: Device, *, expected_revision: int) -> int:
        """One conditional ``UPDATE`` of the declared half; if it touches no row, one read names
        the error (ADR 0037 §9)."""
        declared = {
            column: value
            for column, value in device_values(device).items()
            if column in ANNOUNCED_FIELDS
        }
        async with self._sessions() as session, session.begin():
            result = await session.execute(
                update(DeviceRow)
                .where(
                    DeviceRow.id == device.id,
                    DeviceRow.revision == expected_revision,
                    DeviceRow.revoked_at.is_(None),
                )
                .values(**declared, revision=DeviceRow.revision + 1)
            )
            if _rowcount(result) == 0:
                row = await session.scalar(select(DeviceRow).where(DeviceRow.id == device.id))
                raise _why_not_announced(device.id, row, expected_revision)
        return expected_revision + 1

    async def observe(
        self,
        device_id: DeviceId,
        *,
        seen_at: datetime,
        availability: DeviceAvailability,
        status: DeviceStatus | None = None,
        current_workload: float | None = None,
        power_source: PowerSource | None = None,
    ) -> None:
        observed: dict[str, Any] = {"last_seen_at": seen_at, "availability": availability.value}
        if status is not None:
            observed["status"] = status.value
        if current_workload is not None:
            observed["current_workload"] = current_workload
        if power_source is not None:
            observed["power_source"] = power_source.value
        async with self._sessions() as session, session.begin():
            result = await session.execute(
                update(DeviceRow).where(DeviceRow.id == device_id).values(**observed)
            )
            if _rowcount(result) == 0:
                raise NotFoundError(DEVICE, device_id)

    async def revoke(self, device_id: DeviceId, *, at: datetime) -> bool:
        async with self._sessions() as session, session.begin():
            result = await session.execute(
                update(DeviceRow)
                .where(DeviceRow.id == device_id, DeviceRow.revoked_at.is_(None))
                .values(revoked_at=at)
            )
            if _rowcount(result):
                return True
            if await session.scalar(select(DeviceRow.seq).where(DeviceRow.id == device_id)) is None:
                raise NotFoundError(DEVICE, device_id)
            return False


def _why_not_announced(device_id: DeviceId, row: DeviceRow | None, expected: int) -> Exception:
    """The error for an announcement that matched nothing: unknown, revoked, else a stale revision.

    Revoked before stale: a revoked node is told it is revoked whatever revision it believed, and
    that is the one answer it can do something with (ADR 0037 §12).
    """
    if row is None:
        return NotFoundError(DEVICE, device_id)
    if row.revoked_at is not None:
        return DeviceRevokedError(device_id, row.revoked_at)
    return IdentityConflictError(device_id, expected, row.revision)
