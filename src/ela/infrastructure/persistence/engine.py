"""The async engine and session factory of the persistence layer (ADR 0006).

Only the ``sqlite`` dialect is supported in this version: any other URL is refused at engine
creation, before a connection is attempted (§33: fail fast, not later). The URL is written without
a driver; :func:`async_url` derives ``sqlite+aiosqlite`` for the engine, :func:`sync_url` is what
alembic uses.

Every connection runs ``PRAGMA foreign_keys=ON`` — SQLite keeps foreign keys off by default, and
the schema relies on them (``task_events.task_id``, ``tasks.parent_id``) — and
``PRAGMA recursive_triggers=ON``: without it SQLite does not fire the DELETE triggers of an
``INSERT OR REPLACE``, and the append-only triggers of ``audit_events`` could be walked around
(ADR 0007).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import URL, event, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

__all__ = ["async_url", "ensure_directory", "make_engine", "make_session_factory", "sync_url"]

SQLITE = "sqlite"
ASYNC_DRIVER = "sqlite+aiosqlite"
MEMORY = ":memory:"
DIRECTORY_MODE = 0o700
"""The database directory holds tasks, authorizations and the audit trail (§57)."""
CONNECTION_PRAGMAS = ("PRAGMA foreign_keys=ON", "PRAGMA recursive_triggers=ON")


def _parse(url: str) -> URL:
    parsed = make_url(url)
    backend = parsed.get_backend_name()
    if backend != SQLITE:
        raise ValueError(
            f"only the {SQLITE!r} dialect is supported in this version, not {backend!r}"
        )
    database = parsed.database
    if database is not None and database.startswith("~"):
        database = Path(database).expanduser().as_posix()
    return parsed.set(database=database)


def is_memory(url: URL) -> bool:
    """Whether the URL names an in-memory database (``sqlite://`` or ``sqlite:///:memory:``)."""
    return not url.database or url.database == MEMORY


def async_url(url: str) -> URL:
    """The URL with the async driver, ``~`` expanded; ``ValueError`` unless sqlite."""
    return _parse(url).set(drivername=ASYNC_DRIVER)


def sync_url(url: str) -> URL:
    """The URL with the standard-library driver, for alembic; same checks as :func:`async_url`."""
    return _parse(url).set(drivername=SQLITE)


def ensure_directory(url: URL) -> None:
    """Create the directory of a file database, private to the user (``0o700``)."""
    if is_memory(url):
        return
    assert url.database is not None
    Path(url.database).parent.mkdir(mode=DIRECTORY_MODE, parents=True, exist_ok=True)


def _configure_connection(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    for pragma in CONNECTION_PRAGMAS:
        cursor.execute(pragma)
    cursor.close()


def make_engine(url: str) -> AsyncEngine:
    """An async engine on ``url``: directory created, foreign keys and recursive triggers on, one
    shared connection for ``:memory:`` so that every session sees the same database."""
    target = async_url(url)
    ensure_directory(target)
    if is_memory(target):
        engine = create_async_engine(target, poolclass=StaticPool)
    else:
        engine = create_async_engine(target)
    event.listen(engine.sync_engine, "connect", _configure_connection)
    return engine


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Sessions bound to ``engine``; objects stay usable after commit (the mapper reads them)."""
    return async_sessionmaker(engine, expire_on_commit=False)
