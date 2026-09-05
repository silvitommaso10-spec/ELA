"""The alembic migrations apply from zero, undo cleanly, and match the ORM (ADR 0006 §9)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from sqlalchemy import Column, MetaData, String, Table, create_engine, inspect, text

from ela.infrastructure.persistence import (
    SqlAuditLog,
    SqlAuthorizationStore,
    SqlTaskRepository,
    make_engine,
    verify_chain,
)
from ela.infrastructure.persistence.orm import APPEND_ONLY_TRIGGERS, Base
from tests.architecture.violations import REPO_ROOT
from tests.domain.examples import AUDIT_EVENT, NOW, POLICY_AUTHORIZATION, TASK, TASK_PLAN

ALEMBIC_INI = REPO_ROOT / "alembic.ini"
ALEMBIC = Path(sys.executable).parent / "alembic"
TABLES = {"tasks", "task_events", "authorizations", "audit_events", "task_plans"}
REVISIONS = ["0003", "0002", "0001"]  # newest first, as ``walk_revisions`` yields them
TRIGGERS_SQL = "SELECT name, sql FROM sqlite_master WHERE type = 'trigger' ORDER BY name"
EXPECTED_COLUMNS = {
    name: {column.name for column in table.columns} for name, table in Base.metadata.tables.items()
}


def config_for(db: Path, metadata: MetaData | None = None) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db.as_posix()}")
    if metadata is not None:
        config.attributes["target_metadata"] = metadata
    return config


def _tables(db: Path) -> dict[str, set[str]]:
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    try:
        inspector = inspect(engine)
        return {
            name: {column["name"] for column in inspector.get_columns(name)}
            for name in inspector.get_table_names()
            if name != "alembic_version"
        }
    finally:
        engine.dispose()


def _triggers(db: Path) -> dict[str, str]:
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    try:
        with engine.connect() as connection:
            return dict(connection.execute(text(TRIGGERS_SQL)).all())
    finally:
        engine.dispose()


def _version(db: Path) -> str:
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    try:
        with engine.connect() as connection:
            return connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    finally:
        engine.dispose()


@pytest.fixture
def db(tmp_path: Path) -> Path:
    return tmp_path / "ela.db"


def test_the_revisions_form_one_chain_with_one_head(db: Path) -> None:
    script = ScriptDirectory.from_config(config_for(db))
    assert script.get_heads() == [REVISIONS[0]]
    assert [revision.revision for revision in script.walk_revisions()] == REVISIONS


def test_upgrade_from_zero_creates_the_schema(db: Path) -> None:
    command.upgrade(config_for(db), "head")
    assert _tables(db) == EXPECTED_COLUMNS
    assert set(EXPECTED_COLUMNS) == TABLES


def test_upgrade_creates_the_append_only_triggers(db: Path) -> None:
    """Alembic does not compare triggers: the migration must carry the same SQL as ``orm.py``."""
    command.upgrade(config_for(db), "head")
    assert _triggers(db) == APPEND_ONLY_TRIGGERS


def test_downgrade_of_the_audit_migration_is_refused(db: Path) -> None:
    """Removing the audit log is never a tooling operation (ADR 0007 §7).

    From head the reversible ``0003`` is undone first, then ``0002`` refuses and stays.
    """
    config = config_for(db)
    command.upgrade(config, "head")
    with pytest.raises(NotImplementedError, match="no downgrade"):
        command.downgrade(config, "0001")
    assert "audit_events" in _tables(db)
    assert "task_plans" not in _tables(db)
    assert _triggers(db) == APPEND_ONLY_TRIGGERS
    assert _version(db) == "0002"


def test_downgrade_of_the_plans_migration_removes_the_table(db: Path) -> None:
    """``0003`` does not touch ``audit_events``, so it stays reversible (ADR 0008)."""
    config = config_for(db)
    command.upgrade(config, "head")
    command.downgrade(config, "0002")
    assert set(_tables(db)) == TABLES - {"task_plans"}
    assert _version(db) == "0002"


def test_downgrade_to_base_from_0001_removes_everything(db: Path) -> None:
    """The migrations before the audit log stay reversible."""
    config = config_for(db)
    command.upgrade(config, "0001")
    assert "audit_events" not in _tables(db)
    command.downgrade(config, "base")
    assert _tables(db) == {}


def test_migrations_and_orm_do_not_drift(db: Path) -> None:
    config = config_for(db)
    command.upgrade(config, "head")
    command.check(config)


def test_drift_is_detected(db: Path) -> None:
    """Negative case: one more column in the metadata than in the migrated database."""
    drifted = MetaData()
    for table in Base.metadata.tables.values():
        table.to_metadata(drifted)
    Table("tasks", drifted, Column("colour", String(8)), extend_existing=True)
    config = config_for(db, drifted)
    command.upgrade(config, "head")
    with pytest.raises(CommandError, match="New upgrade operations detected"):
        command.check(config)


def test_check_refuses_a_database_that_is_not_at_head(db: Path) -> None:
    with pytest.raises(CommandError, match="not up to date"):
        command.check(config_for(db))


async def test_the_adapters_work_on_the_migrated_database(db: Path) -> None:
    command.upgrade(config_for(db), "head")
    engine = make_engine(f"sqlite:///{db.as_posix()}")
    try:
        repository = SqlTaskRepository(engine)
        store = SqlAuthorizationStore(engine)
        log = SqlAuditLog(engine)
        await repository.add(TASK)
        await repository.add_plan(TASK_PLAN)
        await store.grant(POLICY_AUTHORIZATION)
        await log.append(AUDIT_EVENT)
        assert await repository.get(TASK.id) == TASK
        assert await repository.plan(TASK.id) == TASK_PLAN
        assert await store.consume(POLICY_AUTHORIZATION.id, now=NOW) == 1
        assert await log.read() == (AUDIT_EVENT,)
        assert (await verify_chain(engine)).length == 1
    finally:
        await engine.dispose()


def test_the_cli_reads_ela_db_url_and_creates_the_directory(tmp_path: Path) -> None:
    """End to end: ``alembic upgrade head`` from the repo root, configured only by the variable."""
    db = tmp_path / ".ela" / "ela.db"
    env = {**os.environ, "ELA_DB_URL": f"sqlite:///{db.as_posix()}"}
    env.pop("ELA_DOTENV", None)
    result = subprocess.run(
        [str(ALEMBIC), "upgrade", "head"],
        cwd=REPO_ROOT,  # where alembic.ini is; %(here)s makes the ini itself location-proof
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert set(_tables(db)) == TABLES
