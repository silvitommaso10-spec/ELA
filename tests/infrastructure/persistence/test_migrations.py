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
    SqlDeviceRegistry,
    SqlEnrollmentStore,
    SqlTaskRepository,
    make_engine,
    verify_chain,
)
from ela.infrastructure.persistence.orm import APPEND_ONLY_TRIGGERS, Base
from tests.architecture.violations import REPO_ROOT
from tests.domain.examples import (
    AUDIT_EVENT,
    DEVICE,
    ENROLLED_DEVICE,
    NOW,
    POLICY_AUTHORIZATION,
    SECRET_HASH,
    TASK,
    TASK_PLAN,
    WAITING_ENROLLMENT,
)

ALEMBIC_INI = REPO_ROOT / "alembic.ini"
ALEMBIC = Path(sys.executable).parent / "alembic"
TABLES = {
    "tasks",
    "task_events",
    "authorizations",
    "audit_events",
    "task_plans",
    "approvals",
    "execution_results",
    "devices",
    "enrollments",
    "assignments",
}
REVISIONS = [
    "0010",
    "0009",
    "0008",
    "0007",
    "0006",
    "0005",
    "0004",
    "0003",
    "0002",
    "0001",
]  # newest first, as ``walk_revisions`` yields them
TRIGGERS_SQL = "SELECT name, sql FROM sqlite_master WHERE type = 'trigger' ORDER BY name"
STARTED_INDEX = "ux_execution_results_started_step"
"""One ``STARTED`` record per step (ADR 0021 §1-bis), as a partial unique index."""
OPEN_STEP_INDEX = "ux_assignments_open_step"
"""One assignment per step that is not ``EXPIRED`` (ADR 0038 §7), as a partial unique index."""
INDEXES_SQL = (
    "SELECT name, sql FROM sqlite_master WHERE type = 'index' AND sql IS NOT NULL ORDER BY name"
)
"""The indexes the schema declares. ``sql IS NULL`` filters out the ones SQLite creates for a
UNIQUE column: those are the constraint, not a declaration of ours."""
EXPECTED_COLUMNS = {
    name: {column.name for column in table.columns} for name, table in Base.metadata.tables.items()
}


def config_for(db: Path, metadata: MetaData | None = None) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db.as_posix()}")
    if metadata is not None:
        config.attributes["target_metadata"] = metadata
    return config


def _indexes(db: Path) -> dict[str, str]:
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    try:
        with engine.connect() as connection:
            return {name: _normalised(sql) for name, sql in connection.execute(text(INDEXES_SQL))}
    finally:
        engine.dispose()


def _normalised(sql: str) -> str:
    """The index DDL with its whitespace flattened: Alembic and ``create_all`` word it the same
    way but do not always space it the same way."""
    return " ".join(sql.split())


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


def test_upgrade_creates_the_same_indexes_as_the_orm(db: Path, tmp_path: Path) -> None:
    """Alembic's check compares that an index *exists*; it does not compare the predicate of a
    partial one. ``ux_execution_results_started_step`` is a constraint only while its
    ``WHERE status = 'STARTED'`` is there (ADR 0021 §1-bis), so the two schemas — the migrated
    one and the one ``create_all`` builds — are compared as DDL, predicate included.
    """
    command.upgrade(config_for(db), "head")
    built = tmp_path / "from-metadata.db"
    engine = create_engine(f"sqlite:///{built.as_posix()}")
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()
    migrated = _indexes(db)
    assert migrated == _indexes(built)
    assert "status = 'STARTED'" in migrated[STARTED_INDEX]
    assert "state <> 'EXPIRED'" in migrated[OPEN_STEP_INDEX]


def test_a_missing_predicate_would_be_detected(db: Path, tmp_path: Path) -> None:
    """Negative case: an index on the same columns without the predicate is a different index —
    it would forbid two results of any status for one step, not two STARTED records."""
    command.upgrade(config_for(db), "head")
    other = tmp_path / "total-index.db"
    engine = create_engine(f"sqlite:///{other.as_posix()}")
    try:
        with engine.begin() as connection:
            connection.execute(
                text("CREATE TABLE execution_results (task_id TEXT, step_id TEXT, status TEXT); ")
            )
            connection.execute(
                text(f"CREATE UNIQUE INDEX {STARTED_INDEX} ON execution_results (task_id, step_id)")
            )
    finally:
        engine.dispose()
    assert "status = 'STARTED'" not in _indexes(other)[STARTED_INDEX]
    assert _indexes(other)[STARTED_INDEX] != _indexes(db)[STARTED_INDEX]


def test_a_missing_assignment_predicate_would_be_detected(db: Path, tmp_path: Path) -> None:
    """The twin for ``0009``: without ``WHERE state <> 'EXPIRED'`` the index is total, and a step
    released after an expiry could never be handed out again (ADR 0038 §7)."""
    command.upgrade(config_for(db), "head")
    other = tmp_path / "total-assignment-index.db"
    engine = create_engine(f"sqlite:///{other.as_posix()}")
    try:
        with engine.begin() as connection:
            connection.execute(
                text("CREATE TABLE assignments (task_id TEXT, step_id TEXT, state TEXT); ")
            )
            connection.execute(
                text(f"CREATE UNIQUE INDEX {OPEN_STEP_INDEX} ON assignments (task_id, step_id)")
            )
    finally:
        engine.dispose()
    assert "state <> 'EXPIRED'" not in _indexes(other)[OPEN_STEP_INDEX]
    assert _indexes(other)[OPEN_STEP_INDEX] != _indexes(db)[OPEN_STEP_INDEX]


def test_the_sensitivity_column_is_born_with_the_strictest_default(db: Path) -> None:
    """``0010``: the tasks written before the column existed keep doing what they did — staying on
    this machine. The ``server_default`` is what says so to anything that inserts a row without the
    column, which is why it stays on the column instead of being dropped after a backfill."""
    command.upgrade(config_for(db), "0009")
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO tasks (id, created_at, goal, state, metadata)"
                    " VALUES ('t1', '2026-01-01', 'g', 'CREATED', '{}')"
                )
            )
        command.upgrade(config_for(db), "0010")
        with engine.connect() as connection:
            levels = [row[0] for row in connection.execute(text("SELECT max_privacy FROM tasks"))]
    finally:
        engine.dispose()

    assert levels == ["LOCAL_ONLY"]


def test_downgrade_of_the_sensitivity_column_takes_it_away(db: Path) -> None:
    """Reversible, and what it reverses is a fact of the user's: every declared level goes with the
    column, which is why it is a downgrade and not a repair."""
    config = config_for(db)
    command.upgrade(config, "head")
    assert "max_privacy" in _tables(db)["tasks"]

    command.downgrade(config, "0009")

    assert "max_privacy" not in _tables(db)["tasks"]


def test_downgrade_of_the_audit_migration_is_refused(db: Path) -> None:
    """Removing the audit log is never a tooling operation (ADR 0007 §7).

    From head the reversible ``0004`` and ``0003`` are undone first, then ``0002`` refuses and
    stays.
    """
    config = config_for(db)
    command.upgrade(config, "head")
    with pytest.raises(NotImplementedError, match="no downgrade"):
        command.downgrade(config, "0001")
    assert "audit_events" in _tables(db)
    assert set(_tables(db)) == TABLES - {
        "task_plans",
        "approvals",
        "execution_results",
        "devices",
        "enrollments",
        "assignments",
    }
    assert _triggers(db) == APPEND_ONLY_TRIGGERS
    assert _version(db) == "0002"


def test_downgrade_of_the_plans_migration_removes_the_table(db: Path) -> None:
    """``0003`` does not touch ``audit_events``, so it stays reversible (ADR 0008)."""
    config = config_for(db)
    command.upgrade(config, "head")
    command.downgrade(config, "0002")
    assert set(_tables(db)) == TABLES - {
        "task_plans",
        "approvals",
        "execution_results",
        "devices",
        "enrollments",
        "assignments",
    }
    assert _version(db) == "0002"


def test_downgrade_of_the_approvals_migration_removes_both_tables(db: Path) -> None:
    """``0004`` does not touch ``audit_events`` either: reversible down to ``0003`` (ADR 0015)."""
    config = config_for(db)
    command.upgrade(config, "head")
    command.downgrade(config, "0003")
    assert set(_tables(db)) == TABLES - {
        "approvals",
        "execution_results",
        "devices",
        "enrollments",
        "assignments",
    }
    assert "task_plans" in _tables(db)
    assert _version(db) == "0003"
    command.upgrade(config, "head")
    assert _tables(db) == EXPECTED_COLUMNS


def test_downgrade_of_the_devices_migration_removes_the_table(db: Path) -> None:
    """``0005`` does not touch ``audit_events`` either: reversible down to ``0004`` (ADR 0016)."""
    config = config_for(db)
    command.upgrade(config, "head")
    command.downgrade(config, "0004")
    assert set(_tables(db)) == TABLES - {"devices", "enrollments", "assignments"}
    assert _version(db) == "0004"
    command.upgrade(config, "head")
    assert _tables(db) == EXPECTED_COLUMNS


def test_downgrade_of_the_identity_migration_removes_what_it_added(db: Path) -> None:
    """``0008`` does not touch ``audit_events``: reversible down to ``0007`` (ADR 0037 §8)."""
    config = config_for(db)
    command.upgrade(config, "head")
    command.downgrade(config, "0007")
    tables = _tables(db)
    assert set(tables) == TABLES - {"enrollments", "assignments"}
    assert {"revision", "revoked_at", "secret_hash"}.isdisjoint(tables["devices"])
    assert _version(db) == "0007"
    command.upgrade(config, "head")
    assert _tables(db) == EXPECTED_COLUMNS


def test_downgrade_of_the_assignments_migration_removes_the_table(db: Path) -> None:
    """``0009`` does not touch ``audit_events``: reversible down to ``0008`` (ADR 0038)."""
    config = config_for(db)
    command.upgrade(config, "head")
    command.downgrade(config, "0008")
    assert set(_tables(db)) == TABLES - {"assignments"}
    assert OPEN_STEP_INDEX not in _indexes(db)
    assert _version(db) == "0008"
    command.upgrade(config, "head")
    assert _tables(db) == EXPECTED_COLUMNS


async def test_a_node_kept_across_the_identity_migration_reads_as_revision_zero(db: Path) -> None:
    """The row ``local`` has on every development database: ``0008`` gives it revision ``0``, no
    revocation and no hash, without anyone rewriting it."""
    config = config_for(db)
    command.upgrade(config, "head")
    before = DEVICE.model_copy(update={"revision": 3})
    engine = make_engine(f"sqlite:///{db.as_posix()}")
    try:
        await SqlDeviceRegistry(engine).register(before)
    finally:
        await engine.dispose()
    command.downgrade(config, "0007")
    command.upgrade(config, "head")
    engine = make_engine(f"sqlite:///{db.as_posix()}")
    try:
        registry = SqlDeviceRegistry(engine)
        assert await registry.get(DEVICE.id) == DEVICE
        assert await registry.secret_hash(DEVICE.id) is None
    finally:
        await engine.dispose()


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
        devices = SqlDeviceRegistry(engine)
        enrollments = SqlEnrollmentStore(engine)
        await enrollments.offer(WAITING_ENROLLMENT)
        spent = await enrollments.consume(
            WAITING_ENROLLMENT.code_hash, device_id=ENROLLED_DEVICE.id, now=NOW
        )
        await devices.enroll(ENROLLED_DEVICE, secret_hash=SECRET_HASH)
        assert spent.device_id == ENROLLED_DEVICE.id
        assert await devices.announce(ENROLLED_DEVICE, expected_revision=1) == 2
        assert await devices.revoke(ENROLLED_DEVICE.id, at=NOW) is True
        assert await devices.secret_hash(ENROLLED_DEVICE.id) == SECRET_HASH
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
