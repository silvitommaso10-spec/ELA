"""Alembic environment of ELA: the schema is ``Base.metadata``, the database is ``ELA_DB_URL``.

Synchronous on purpose: alembic runs with the standard-library sqlite driver
(:func:`ela.infrastructure.persistence.engine.sync_url`), the application with aiosqlite. Both
derive from the same URL. ``config.attributes["target_metadata"]`` lets a test compare the
database against a different metadata (the negative case of ``alembic check``).
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import MetaData, create_engine
from sqlalchemy.pool import NullPool

from ela.infrastructure.persistence.engine import ensure_directory, sync_url
from ela.infrastructure.persistence.orm import Base
from ela.infrastructure.persistence.settings import PersistenceSettings

config = context.config
target_metadata: MetaData = config.attributes.get("target_metadata", Base.metadata)


def database_url() -> str:
    """``sqlalchemy.url`` from the config if set (tests, ``-x``), else the application setting."""
    configured = config.get_main_option("sqlalchemy.url")
    return configured if configured else PersistenceSettings().db_url


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a connection (``alembic upgrade head --sql``)."""
    context.configure(
        url=sync_url(database_url()),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = sync_url(database_url())
    ensure_directory(url)
    engine = create_engine(url, poolclass=NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
