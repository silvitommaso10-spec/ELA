"""``engine.py`` (ADR 0006 §3–§4): URL handling, the private directory, foreign keys on."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from ela.infrastructure.persistence import (
    async_url,
    ensure_directory,
    make_engine,
    make_session_factory,
    sync_url,
)
from ela.infrastructure.persistence.engine import DIRECTORY_MODE, is_memory
from tests.contracts.implementations import MEMORY_URL
from tests.infrastructure.persistence.conftest import create_schema

# ----------------------------------------------------------------------------------------
# URLs
# ----------------------------------------------------------------------------------------


def test_async_url_adds_the_aiosqlite_driver() -> None:
    url = async_url("sqlite:////var/lib/ela/ela.db")
    assert url.drivername == "sqlite+aiosqlite"
    assert url.database == "/var/lib/ela/ela.db"


def test_sync_url_uses_the_standard_library_driver() -> None:
    assert str(sync_url("sqlite+aiosqlite:////tmp/x.db")) == "sqlite:////tmp/x.db"


def test_an_explicit_aiosqlite_driver_is_accepted() -> None:
    assert async_url("sqlite+aiosqlite:///x.db").drivername == "sqlite+aiosqlite"


@pytest.mark.parametrize("url", ["sqlite:///~/.ela/ela.db", "sqlite:///~/ela.db"])
def test_tilde_is_expanded(url: str) -> None:
    database = async_url(url).database
    assert database is not None
    assert database.startswith(Path.home().as_posix())
    assert "~" not in database


@pytest.mark.parametrize("url", ["postgresql://ela@localhost/ela", "mysql+pymysql:///ela"])
def test_other_dialects_are_refused(url: str) -> None:
    with pytest.raises(ValueError, match="only the 'sqlite' dialect"):
        async_url(url)
    with pytest.raises(ValueError, match="only the 'sqlite' dialect"):
        make_engine(url)


@pytest.mark.parametrize("url", ["sqlite://", "sqlite:///:memory:"])
def test_memory_urls_are_recognised(url: str) -> None:
    assert is_memory(async_url(url))


def test_a_file_url_is_not_memory() -> None:
    assert not is_memory(async_url("sqlite:///x.db"))


# ----------------------------------------------------------------------------------------
# Directory
# ----------------------------------------------------------------------------------------


def test_ensure_directory_creates_the_parent_privately(tmp_path: Path) -> None:
    directory = tmp_path / "nested" / ".ela"
    ensure_directory(sync_url(f"sqlite:///{(directory / 'ela.db').as_posix()}"))
    assert directory.is_dir()
    if os.name != "nt":
        assert directory.stat().st_mode & 0o777 == DIRECTORY_MODE


def test_ensure_directory_does_nothing_for_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    ensure_directory(sync_url(MEMORY_URL))
    assert list(tmp_path.iterdir()) == []


async def test_make_engine_creates_the_directory_and_the_file(tmp_path: Path) -> None:
    path = tmp_path / ".ela" / "ela.db"
    engine = make_engine(f"sqlite:///{path.as_posix()}")
    try:
        assert path.parent.is_dir()
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        assert path.is_file()
    finally:
        await engine.dispose()


# ----------------------------------------------------------------------------------------
# Connections
# ----------------------------------------------------------------------------------------


PRAGMAS = ["foreign_keys", "recursive_triggers"]


@pytest.mark.parametrize("pragma", PRAGMAS)
async def test_pragma_is_on_for_a_new_connection(file_url: str, pragma: str) -> None:
    engine = make_engine(file_url)
    try:
        async with engine.connect() as connection:
            assert (await connection.execute(text(f"PRAGMA {pragma}"))).scalar() == 1
    finally:
        await engine.dispose()


@pytest.mark.parametrize("pragma", PRAGMAS)
async def test_without_the_listener_sqlite_keeps_the_pragma_off(file_url: str, pragma: str) -> None:
    """Negative case: the PRAGMAs are our doing, SQLite does not enable them by itself."""
    engine = create_async_engine(async_url(file_url))
    try:
        async with engine.connect() as connection:
            assert (await connection.execute(text(f"PRAGMA {pragma}"))).scalar() == 0
    finally:
        await engine.dispose()


async def test_foreign_keys_are_enforced(file_url: str) -> None:
    engine = make_engine(file_url)
    try:
        await create_schema(engine)
        async with engine.begin() as connection:
            with pytest.raises(IntegrityError, match="FOREIGN KEY"):
                await connection.execute(
                    text(
                        "INSERT INTO task_events (id, task_id, created_at, event_type, message,"
                        " metadata) VALUES ('e1', 't-unknown', '2026-01-01', 'NOTE', '', '{}')"
                    )
                )
    finally:
        await engine.dispose()


async def test_memory_engine_shares_one_database_between_sessions() -> None:
    engine = make_engine(MEMORY_URL)
    try:
        assert isinstance(engine.pool, StaticPool)
        await create_schema(engine)
        sessions = make_session_factory(engine)
        async with sessions() as first, sessions() as second:
            tables = await second.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            names = {row[0] for row in tables}
            assert names >= {"tasks", "task_events", "authorizations", "audit_events"}
            await first.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


async def test_sessions_do_not_expire_on_commit() -> None:
    engine = make_engine(MEMORY_URL)
    try:
        assert make_session_factory(engine).kw["expire_on_commit"] is False
    finally:
        await engine.dispose()
