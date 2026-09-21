"""Building a real ELA in a test: a database on disk, a workspace, and the seven settings.

The database is a **file** and not ``:memory:``: ``build`` opens the engine itself from
``ELA_DB_URL``, and two in-memory engines are two different databases — the schema a test created
would not be the schema ELA finds. On a file, the migration a test applies is the one ELA reads.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from ela.composition import Ela, Settings, build
from ela.infrastructure.persistence import make_engine
from ela.infrastructure.persistence.orm import Base
from ela.testing.fakes import FakePower

TOKEN = "x" * 40
"""Long enough for ``ELA_API_TOKEN`` and empty of entropy: a plausible-looking token committed to
the repository is how a secret scanner learns to ignore secrets (M5.3, the CI fix)."""

DB = "ELA_DB_URL"
WORKSPACE = "ELA_WORKSPACE_DIR"
API_TOKEN = "ELA_API_TOKEN"
PERCEPTION = "ELA_PERCEPTION_ENABLED"
CAPTURES = "ELA_CAPTURE_DIR"
POLL = "ELA_NODE_POLL_SECONDS"
FS_ROOT = "ELA_FS_ROOT"
FS_SCOPE = "ELA_FS_SCOPE"


def declare(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **extra: str) -> None:
    """The minimum an ELA needs, plus whatever the test wants to say.

    Perception is **off** unless a test asks for it, and for the same reason the database is a
    temporary file: with it on, every application start-up spawns a helper and reads *this*
    machine, so the suite would say one thing on a Mac and another on a runner. The tests that
    are about perception turn it back on and say what the probe answers.
    """
    monkeypatch.setenv(DB, database_url(tmp_path))
    monkeypatch.setenv(WORKSPACE, str(tmp_path / "workspace"))
    # Beside the temporary database, for the same reason it is beside the real one — and because
    # a test that left the default alone would create ``~/.ela/captures`` on whoever ran it.
    monkeypatch.setenv(CAPTURES, str(tmp_path / "captures"))
    monkeypatch.setenv(API_TOKEN, TOKEN)
    # The folder ``fs.read`` and ``fs.write`` may touch (M13.1 dec. A): both lines or no start-up,
    # and under ``tmp_path`` for the reason the captures are — a test that left them out would be
    # a test that cannot start, and one that named a real folder would write in somebody's home.
    monkeypatch.setenv(FS_ROOT, str(_declared_root(tmp_path)))
    monkeypatch.setenv(FS_SCOPE, "ela")
    # Off by default, but a fixture that turned it on before this ran keeps it on: the
    # environment has already been emptied of ``ELA_`` by ``_only_the_declared_environment``,
    # so anything present here was put there by the test on purpose.
    monkeypatch.setenv(PERCEPTION, os.environ.get(PERCEPTION, "false"))
    # A second, not the twenty-five of production: ``POST /nodes/work`` holds a request that found
    # nothing for this long, and a suite that waited out the real window would pay it per test
    # (M12.2, ADR 0038 §11). What the window *is* has its own test, in ``tests/composition``.
    monkeypatch.setenv(POLL, os.environ.get(POLL, "1"))
    for name, value in extra.items():
        monkeypatch.setenv(name, value)


def _declared_root(tmp_path: Path) -> Path:
    """A root that exists and is nothing of ELA's own: created here, because ELA never creates it.

    It sits beside the workspace and the captures rather than inside them, which is what the
    start-up check requires: the folder ELA may touch for the user cannot contain, or be
    contained by, the folder ELA uses to exist (M13.1 dec. F).
    """
    root = tmp_path / "files"
    root.mkdir(exist_ok=True)
    return root


def database_url(tmp_path: Path) -> str:
    return f"sqlite:///{(tmp_path / 'ela.db').as_posix()}"


async def create_schema(url: str) -> None:
    """What ``uv run alembic upgrade head`` does, without alembic: ELA refuses to start without."""
    engine = make_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


@pytest.fixture(autouse=True)
def _only_the_declared_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """No ``ELA_`` variable and no ``.env`` but the ones the test asks for.

    Both matter: the suite must say the same thing on a machine where ELA is configured for real
    and on a machine where it is not.
    """
    for name in list(os.environ):
        if name.startswith("ELA_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    declare(monkeypatch, tmp_path)
    return Settings.load()


@pytest.fixture
async def ela(settings: Settings) -> AsyncIterator[Ela]:
    """ELA as ``build`` makes it, on a migrated database, released at the end.

    With a :class:`~ela.testing.fakes.FakePower` that answers ``UNKNOWN`` until a test says
    otherwise (M12.3c): ``local``'s heartbeats read the power source, and a placement between
    ``local`` and a node would otherwise depend on whether the machine running the suite is plugged
    in — the same suite saying one thing at the desk and another on the train.
    """
    await create_schema(settings.persistence.db_url)
    built = await build(settings, power=FakePower())
    try:
        yield built
    finally:
        await built.aclose()
