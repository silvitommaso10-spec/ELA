"""``AuthorizationStore`` on SQLAlchemy (port in :mod:`ela.ports`, spec §30, §59; ADR 0006, 0012).

The grant is frozen; the store owns the use counter as a column of the same row. ``consume``
spends one use in a single conditional ``UPDATE`` — ``SET uses = uses + 1 WHERE … AND uses <
max_uses AND expires_at > :now`` — that SQLite runs under its write lock, so two concurrent calls
on a single-use grant cannot both see ``uses = 0`` (ADR 0012 §5). Whether a grant *covers* a call
stays the Guardian's judgement (ADR 0011); the store only refuses to spend what cannot be spent.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from ela.domain import Authorization, AuthorizationId, CapabilityId
from ela.infrastructure.persistence.engine import make_session_factory
from ela.infrastructure.persistence.mappers import authorization_to_row, row_to_authorization
from ela.infrastructure.persistence.orm import AuthorizationRow
from ela.ports import (
    AlreadyExistsError,
    AuthorizationExhaustedError,
    AuthorizationExpiredError,
    NotFoundError,
)

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

    async def consume(self, authorization_id: AuthorizationId, *, now: datetime) -> int:
        """One conditional ``UPDATE``; if it touches no row, one read names the error (ADR 0012)."""
        async with self._sessions() as session, session.begin():
            result = await session.execute(
                update(AuthorizationRow)
                .where(
                    AuthorizationRow.id == authorization_id,
                    or_(
                        AuthorizationRow.max_uses.is_(None),
                        AuthorizationRow.uses < AuthorizationRow.max_uses,
                    ),
                    or_(AuthorizationRow.expires_at.is_(None), AuthorizationRow.expires_at > now),
                )
                .values(uses=AuthorizationRow.uses + 1)
            )
            if cast(CursorResult[Any], result).rowcount == 0:
                row = await session.scalar(
                    select(AuthorizationRow).where(AuthorizationRow.id == authorization_id)
                )
                raise _why_not_consumed(authorization_id, row, now)
            return await self._uses(session, authorization_id)

    @staticmethod
    async def _uses(session: AsyncSession, authorization_id: AuthorizationId) -> int:
        uses = await session.scalar(
            select(AuthorizationRow.uses).where(AuthorizationRow.id == authorization_id)
        )
        if uses is None:
            raise NotFoundError(AUTHORIZATION, authorization_id)
        return uses


def _why_not_consumed(
    authorization_id: AuthorizationId, row: AuthorizationRow | None, now: datetime
) -> Exception:
    """The error for an ``UPDATE`` that matched nothing: unknown, expired, else exhausted.

    The safety is in the ``UPDATE``; this read only names the reason, in the Guardian's order
    (ADR 0011 §5: expired before exhausted).
    """
    if row is None:
        return NotFoundError(AUTHORIZATION, authorization_id)
    if row.expires_at is not None and row.expires_at <= now:
        return AuthorizationExpiredError(authorization_id, row.expires_at)
    assert row.max_uses is not None
    return AuthorizationExhaustedError(authorization_id, row.uses, row.max_uses)
