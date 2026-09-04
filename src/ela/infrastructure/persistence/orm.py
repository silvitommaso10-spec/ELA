"""The tables, as SQLAlchemy rows that know nothing of the domain (ADR 0006).

This module never imports :mod:`ela.domain` and no row subclasses a domain model: the bridge is
:mod:`ela.infrastructure.persistence.mappers`, one function per direction. A row is a storage
shape — integer sequence for insertion order, strings for enums, JSON for payloads — and the
domain entity is rebuilt from it, validated, on every read.

Every table has ``seq`` as an auto-incrementing primary key because the ports promise reads in
insertion order and SQLite only offers a counter as ``INTEGER PRIMARY KEY``; the domain id stays
the unique key that foreign keys reference. ``sqlite_autoincrement`` keeps a ``seq`` from ever
being reused.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, Uuid, text
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

__all__ = ["AuthorizationRow", "Base", "TaskEventRow", "TaskRow", "UtcDateTime"]


class UtcDateTime(TypeDecorator[datetime]):
    """An aware UTC instant stored in a database without time zones.

    SQLAlchemy's ``DateTime`` on SQLite drops the ``tzinfo`` on the way in, and the domain refuses
    a naive datetime on the way out. So: a naive value in is a caller's bug (``ValueError``), an
    aware value is normalised to UTC and stored naive, and what comes back is tagged UTC again.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("UtcDateTime needs a timezone-aware datetime")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC)


class Base(DeclarativeBase):
    """Root of every mapped row; ``Base.metadata`` is what alembic compares against."""


class TaskRow(Base):
    """A :class:`~ela.domain.Task`, as stored (§14, §15)."""

    __tablename__ = "tasks"
    __table_args__ = {"sqlite_autoincrement": True}

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[UUID] = mapped_column(Uuid, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    intent_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    plan_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    parent_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("tasks.id"), nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False)


class TaskEventRow(Base):
    """A :class:`~ela.domain.TaskEvent`, as stored: the trail of one task (§14)."""

    __tablename__ = "task_events"
    __table_args__ = {"sqlite_autoincrement": True}

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[UUID] = mapped_column(Uuid, unique=True, nullable=False)
    task_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tasks.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    step_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    previous_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    new_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False)


class AuthorizationRow(Base):
    """An :class:`~ela.domain.Authorization`, as stored, plus the store's own use counter (§30).

    ``uses`` is not a field of the frozen domain entity: the store counts on its behalf
    (ADR 0005 §11) and increments it atomically in SQL.
    """

    __tablename__ = "authorizations"
    __table_args__ = {"sqlite_autoincrement": True}

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[UUID] = mapped_column(Uuid, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    capability_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    scope: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    granted_by: Mapped[str] = mapped_column(String(255), nullable=False)
    approval_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    task_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    step_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False)
    uses: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
