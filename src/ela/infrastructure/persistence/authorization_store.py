"""``AuthorizationStore`` on SQLAlchemy (port in :mod:`ela.ports`, spec §30, §59; ADR 0006).

The grant is frozen; the store owns the use counter (ADR 0005 §11) as a column of the same row and
increments it in SQL — ``uses = uses + 1`` — so that two concurrent ``record_use`` calls never
lose a count. Whether ``uses < max_uses`` still holds is the Guardian's judgement, not the store's.
"""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from ela.domain import Authorization, AuthorizationId, CapabilityId
from ela.infrastructure.persistence.engine import make_session_factory
from ela.infrastructure.persistence.mappers import authorization_to_row, row_to_authorization
from ela.infrastructure.persistence.orm import AuthorizationRow
from ela.ports import AlreadyExistsError, NotFoundError

__all__ = ["SqlAuthorizationStore"]

AUTHORIZATION = "authorization"


class SqlAuthorizationStore:
    """Grants and their use counters in ``authorizations`` (port ``AuthorizationStore``)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._sessions = make_session_factory(engine)

    @property
    def engine(self) -> AsyncEngine:
        """The engine this store is bound to."""
        return self._engine

    async def grant(self, authorization: Authorization) -> None:
        async with self._sessions() as session, session.begin():
            session.add(authorization_to_row(authorization))
            try:
                await session.flush()
            except IntegrityError:
                raise AlreadyExistsError(AUTHORIZATION, authorization.id) from None

    async def get(self, authorization_id: AuthorizationId) -> Authorization:
        async with self._sessions() as session:
            row = await session.scalar(
                select(AuthorizationRow).where(AuthorizationRow.id == authorization_id)
            )
            if row is None:
                raise NotFoundError(AUTHORIZATION, authorization_id)
            return row_to_authorization(row)

    async def for_capability(self, capability_id: CapabilityId) -> tuple[Authorization, ...]:
        query = (
            select(AuthorizationRow)
            .where(AuthorizationRow.capability_id == capability_id)
            .order_by(AuthorizationRow.seq)
        )
        async with self._sessions() as session:
            rows = await session.scalars(query)
            return tuple(row_to_authorization(row) for row in rows)

    async def uses(self, authorization_id: AuthorizationId) -> int:
        async with self._sessions() as session:
            return await self._uses(session, authorization_id)

    async def record_use(self, authorization_id: AuthorizationId) -> int:
        async with self._sessions() as session, session.begin():
            result = await session.execute(
                update(AuthorizationRow)
                .where(AuthorizationRow.id == authorization_id)
                .values(uses=AuthorizationRow.uses + 1)
            )
            if cast(CursorResult[Any], result).rowcount == 0:
                raise NotFoundError(AUTHORIZATION, authorization_id)
            return await self._uses(session, authorization_id)

    @staticmethod
    async def _uses(session: AsyncSession, authorization_id: AuthorizationId) -> int:
        uses = await session.scalar(
            select(AuthorizationRow.uses).where(AuthorizationRow.id == authorization_id)
        )
        if uses is None:
            raise NotFoundError(AUTHORIZATION, authorization_id)
        return uses
