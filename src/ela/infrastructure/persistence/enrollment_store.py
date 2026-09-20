"""``EnrollmentStore`` on SQLAlchemy (port in :mod:`ela.ports`, spec §16; ADR 0037 §5, §8).

A code is kept as its SHA-256 and spent by one conditional ``UPDATE`` —
``WHERE code_hash = :h AND consumed_at IS NULL AND expires_at > :now`` — the shape of
``SqlAuthorizationStore.consume`` (ADR 0012 §5): of two nodes presenting the same code, the
database lets one through. When the statement touches no row, a read in the same transaction names
the reason, and never with the hash: an error can reach a response body.

Found by its hash, which architecture rule 31 allows for the code and not for a node's secret
(ADR 0037 §16): the code is a 256-bit value, so a lookup by its hash can leak at most the hash,
and the hash is not what opens the door.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Final, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from ela.domain import DeviceId, DeviceRole, Enrollment
from ela.infrastructure.persistence.engine import make_session_factory
from ela.infrastructure.persistence.mappers import enrollment_to_row, row_to_enrollment
from ela.infrastructure.persistence.orm import EnrollmentRow
from ela.ports import (
    AlreadyExistsError,
    EnrollmentConsumedError,
    EnrollmentExpiredError,
    EnrollmentRoleError,
    NotFoundError,
)

__all__ = ["SqlEnrollmentStore"]

ENROLLMENT: Final = "enrollment"
CODE: Final = "code"
"""What an error names instead of the hash: the store holds nothing it could safely print."""


class SqlEnrollmentStore:
    """The one-shot codes of M12.1 in ``enrollments`` (port ``EnrollmentStore``)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._sessions = make_session_factory(engine)

    @property
    def engine(self) -> AsyncEngine:
        """The engine this store is bound to."""
        return self._engine

    async def offer(self, enrollment: Enrollment) -> None:
        async with self._sessions() as session, session.begin():
            session.add(enrollment_to_row(enrollment))
            try:
                await session.flush()
            except IntegrityError:
                raise AlreadyExistsError(ENROLLMENT, CODE) from None

    async def consume(
        self, code_hash: str, *, device_id: DeviceId, now: datetime, role: DeviceRole
    ) -> Enrollment:
        """One conditional ``UPDATE``; then one read, which returns the code or names the error.

        ``role`` is a condition of the statement, beside the expiry (M12.5 dec. C.5): a code minted
        for the other role touches no row, so it is not spent and the user can present it where it
        belongs.
        """
        async with self._sessions() as session, session.begin():
            result = await session.execute(
                update(EnrollmentRow)
                .where(
                    EnrollmentRow.code_hash == code_hash,
                    EnrollmentRow.consumed_at.is_(None),
                    EnrollmentRow.expires_at > now,
                    EnrollmentRow.role == role.value,
                )
                .values(consumed_at=now, device_id=device_id)
            )
            row = await session.scalar(
                select(EnrollmentRow).where(EnrollmentRow.code_hash == code_hash)
            )
            if cast(CursorResult[Any], result).rowcount == 0 or row is None:
                raise _why_not_consumed(row, role)
            return row_to_enrollment(row)


def _why_not_consumed(row: EnrollmentRow | None, role: DeviceRole) -> Exception:
    """Unknown, else spent, else the wrong role, else expired — the port's order.

    Spent before expired: a code spent and then expired still names the node it gave birth to,
    which is what ``DEVICE_REJECTED`` ``code_reused`` reports (ADR 0037 §13). The role comes before
    the expiry because it is a fact about *this request* and not about time: a code offered on the
    wrong route is answered the same way a minute after it was minted and a minute after it died,
    and the user is told the one thing they can act on (M12.5 dec. C.5).
    """
    if row is None:
        return NotFoundError(ENROLLMENT, CODE)
    if row.device_id is not None:
        return EnrollmentConsumedError(DeviceId(row.device_id))
    if row.role != role.value:
        return EnrollmentRoleError(DeviceRole(row.role), role)
    return EnrollmentExpiredError(row.expires_at)
