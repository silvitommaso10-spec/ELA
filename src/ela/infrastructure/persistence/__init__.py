"""Persistence of the Core's state on SQLite (spec §54 "persistence"; ADR 0006).

SQLAlchemy 2 async on ``aiosqlite``; ORM rows kept apart from the domain entities and translated
by an explicit mapper; schema owned by alembic (``migrations/``). Configuration comes from
:class:`PersistenceSettings` (``ELA_DB_URL``). The audit log (§32) is append-only at every level
and hash-chained; :func:`verify_chain` checks the chain (ADR 0007).
"""

from ela.infrastructure.persistence.audit_log import SqlAuditLog, verify_chain
from ela.infrastructure.persistence.authorization_store import SqlAuthorizationStore
from ela.infrastructure.persistence.engine import (
    async_url,
    ensure_directory,
    make_engine,
    make_session_factory,
    sync_url,
)
from ela.infrastructure.persistence.settings import PersistenceSettings, default_db_url
from ela.infrastructure.persistence.task_repository import SqlTaskRepository

__all__ = [
    "PersistenceSettings",
    "SqlAuditLog",
    "SqlAuthorizationStore",
    "SqlTaskRepository",
    "async_url",
    "default_db_url",
    "ensure_directory",
    "make_engine",
    "make_session_factory",
    "sync_url",
    "verify_chain",
]
