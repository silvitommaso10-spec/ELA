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
from typing import Any, Final
from uuid import UUID

from sqlalchemy import (
    DDL,
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
    event,
    text,
)
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.types import TypeDecorator

__all__ = [
    "APPEND_ONLY_TRIGGERS",
    "HASHED_COLUMNS",
    "AppendOnlyViolation",
    "ApprovalRow",
    "AuditEventRow",
    "AuthorizationRow",
    "Base",
    "DeviceRow",
    "ExecutionResultRow",
    "TaskEventRow",
    "TaskPlanRow",
    "TaskRow",
    "UtcDateTime",
]

HASH_LENGTH: Final = 64
"""A SHA-256 in lowercase hex (``ela.audit.chain``); the column is sized from it."""


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


class TaskPlanRow(Base):
    """A :class:`~ela.domain.TaskPlan`, as stored: one per task (§13, §14; ADR 0008).

    ``task_id`` is UNIQUE: a task has at most one plan, and replanning is not a thing in v0.1
    (ADR 0004). The steps are value-like and immutable, so they travel as one JSON array; a table
    of their own would be a migration with an ADR, the day something needs to query them in SQL.
    """

    __tablename__ = "task_plans"
    __table_args__ = {"sqlite_autoincrement": True}

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[UUID] = mapped_column(Uuid, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    task_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tasks.id"), unique=True, nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
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


class ApprovalRow(Base):
    """An :class:`~ela.domain.Approval`, as stored (§30; ADR 0015).

    No foreign key on ``task_id``: a store apart from the repository, like ``authorizations``
    (ADR 0006 §6). ``respond`` fills ``status``, ``responded_at`` and ``responded_by`` with one
    conditional ``UPDATE``; nothing else is ever rewritten.
    """

    __tablename__ = "approvals"
    __table_args__ = {"sqlite_autoincrement": True}

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[UUID] = mapped_column(Uuid, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    task_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    step_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    capability_id: Mapped[str] = mapped_column(String(255), nullable=False)
    targets: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    decision_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    responded_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False)


class ExecutionResultRow(Base):
    """An :class:`~ela.domain.ExecutionResult`, as stored (§63; ADR 0015).

    ``output`` is the user's content (§57): it lives here, in the private database, and never
    in ``audit_events``. Insert-only; no foreign key on ``task_id`` (nullable in the domain).

    ``usage`` is what a provider call inside the execution consumed (§32; M7.2, ADR 0021 §3),
    as one JSON document — ``cost`` a string, because a ``Decimal`` that went through a float
    would stop adding up. Nullable: a tool that calls no provider has none, and that is not zero.
    A ``STARTED`` row (ADR 0021 §1) is one of these too, with no output, no error and no usage:
    what it records is that a tool that cannot be run twice was about to run.
    """

    __tablename__ = "execution_results"
    __table_args__ = {"sqlite_autoincrement": True}

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[UUID] = mapped_column(Uuid, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    capability_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    task_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    step_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    device_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    decision_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    authorization_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    output: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False)
    usage: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    """Last on purpose: ``ALTER TABLE ADD COLUMN`` appends, so a database built by
    ``create_all`` and one built by the migrations have the columns in the same order."""


class DeviceRow(Base):
    """A :class:`~ela.domain.Device`, as stored (§16; ADR 0016).

    No foreign key: a store apart from the repository, like ``authorizations`` (ADR 0006 §6).
    ``availability`` is indexed because the orchestrator (§17) will ask for the nodes that answer,
    but what a reader gets is not this column: ``DeviceRegistry`` answers availability from
    ``last_seen_at`` and the TTL (ADR 0016 §3). The column holds the last state observed.
    """

    __tablename__ = "devices"
    __table_args__ = {"sqlite_autoincrement": True}

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[UUID] = mapped_column(Uuid, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    os: Mapped[str] = mapped_column(String(32), nullable=False)
    availability: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    capabilities: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    available_tools: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    performance: Mapped[str] = mapped_column(String(32), nullable=False)
    network: Mapped[str] = mapped_column(String(32), nullable=False)
    power_source: Mapped[str] = mapped_column(String(32), nullable=False)
    privacy: Mapped[str] = mapped_column(String(32), nullable=False)
    current_workload: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False)


class AuditEventRow(Base):
    """An :class:`~ela.domain.AuditEvent`, as stored, plus the two hashes of the chain (§32).

    ``prev_hash`` is the ``row_hash`` of the row before it in ``seq`` order (``GENESIS_HASH`` for
    the first); ``row_hash`` is the hash of ``prev_hash`` and the :data:`HASHED_COLUMNS`. Both
    are UNIQUE: two rows cannot claim the same predecessor, so the chain cannot fork, and the
    genesis can be claimed once. The actor is two columns so that "who" stays queryable
    (ADR 0003).
    """

    __tablename__ = "audit_events"
    __table_args__ = {"sqlite_autoincrement": True}

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[UUID] = mapped_column(Uuid, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    task_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    step_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    capability_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decision_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    authorization_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    device_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    usage: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    prev_hash: Mapped[str] = mapped_column(String(HASH_LENGTH), unique=True, nullable=False)
    row_hash: Mapped[str] = mapped_column(String(HASH_LENGTH), unique=True, nullable=False)


CHAIN_COLUMNS: Final = ("prev_hash", "row_hash")
HASHED_COLUMNS: Final = tuple(
    column.name
    for column in AuditEventRow.__table__.columns
    if column.name not in ("seq", *CHAIN_COLUMNS)
)
"""The content of an audit row, in the order hashed (ADR 0007): every column but ``seq``, which
the database assigns, and the two chain columns (``prev_hash`` enters the hash as the previous
hash, ``row_hash`` is the result)."""

APPEND_ONLY_MESSAGE: Final = "audit_events is append-only"
APPEND_ONLY_TRIGGERS: Final = {
    "audit_events_no_update": (
        f"CREATE TRIGGER audit_events_no_update BEFORE UPDATE ON audit_events "
        f"BEGIN SELECT RAISE(ABORT, '{APPEND_ONLY_MESSAGE}'); END"
    ),
    "audit_events_no_delete": (
        f"CREATE TRIGGER audit_events_no_delete BEFORE DELETE ON audit_events "
        f"BEGIN SELECT RAISE(ABORT, '{APPEND_ONLY_MESSAGE}'); END"
    ),
}
"""The database level of append-only: SQLite refuses UPDATE and DELETE on the table itself.

Created by ``create_all`` (below) and, with the same text, by migration ``0002``. They cover
``INSERT OR REPLACE`` too, but only with ``PRAGMA recursive_triggers=ON`` (``engine.py``).
"""

for _trigger in APPEND_ONLY_TRIGGERS.values():
    event.listen(AuditEventRow.__table__, "after_create", DDL(_trigger))  # type: ignore[no-untyped-call]


class AppendOnlyViolation(Exception):
    """An ORM session tried to update or delete an audit row (ADR 0007: refused before any SQL)."""

    def __init__(self, row: object) -> None:
        super().__init__(f"{APPEND_ONLY_MESSAGE}: refusing to change {row!r}")


@event.listens_for(Session, "before_flush")
def _refuse_audit_changes(session: Session, _context: object, _instances: object) -> None:
    """The ORM level of append-only: an audit row in ``dirty`` or ``deleted`` aborts the flush.

    Registered on the ``Session`` class, so it runs for every session in the process (an
    ``AsyncSession`` wraps one). Other tables are untouched: only ``AuditEventRow`` is refused.
    """
    for row in (*session.dirty, *session.deleted):
        if isinstance(row, AuditEventRow):
            raise AppendOnlyViolation(row)
