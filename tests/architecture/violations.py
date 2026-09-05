"""Synthetic modules that violate (or legitimately satisfy) each architecture rule.

Shared by the pytest rules and the import-linter contracts: both must agree on every case.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "src" / "ela"


@dataclass(frozen=True)
class Case:
    id: str
    rule: str
    path: str  # relative to the ``ela`` package
    source: str
    imported: str  # what the rule must report (empty for allowed cases)

    @property
    def module(self) -> str:
        parts = list(Path(self.path).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        return ".".join(["ela", *parts])


VIOLATIONS: tuple[Case, ...] = (
    Case("domain-third-party", "domain", "domain.py", "import yaml\n", "yaml"),
    Case(
        "domain-infra-library", "domain", "domain.py", "from httpx import Client\n", "httpx.Client"
    ),
    Case("domain-ports", "domain", "domain.py", "from ela import ports\n", "ela.ports"),
    Case("domain-relative", "domain", "domain.py", "from . import tasks\n", "ela.tasks"),
    Case("ports-pydantic", "ports", "ports.py", "import pydantic\n", "pydantic"),
    Case("ports-infra-library", "ports", "ports.py", "import sqlalchemy\n", "sqlalchemy"),
    Case(
        "ports-providers",
        "ports",
        "ports.py",
        "from ela.providers import registry\n",
        "ela.providers.registry",
    ),
    Case("ports-sibling", "ports", "ports.py", "from ela import tasks\n", "ela.tasks"),
    Case("infra-tasks", "infra-libraries", "tasks/engine.py", "import anthropic\n", "anthropic"),
    Case(
        "infra-executive",
        "infra-libraries",
        "executive/app.py",
        "from fastapi import FastAPI\n",
        "fastapi.FastAPI",
    ),
    Case("infra-root-module", "infra-libraries", "cli.py", "import typer\n", "typer"),
    Case(
        "infra-type-checking",
        "infra-libraries",
        "memory/store.py",
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import sqlalchemy\n",
        "sqlalchemy",
    ),
    Case(
        "infra-inside-function",
        "infra-libraries",
        "tools/shell.py",
        "def run() -> None:\n    import openai  # noqa: F401\n",
        "openai",
    ),
    Case(
        "core-tasks-providers",
        "core-isolation",
        "tasks/planner.py",
        "from ela.providers import registry\n",
        "ela.providers.registry",
    ),
    Case(
        "core-permissions-infrastructure",
        "core-isolation",
        "permissions/store.py",
        "import ela.infrastructure.db\n",
        "ela.infrastructure.db",
    ),
    Case(
        "core-audit-relative",
        "core-isolation",
        "audit/log.py",
        "from .. import providers\n",
        "ela.providers",
    ),
    Case(
        "core-executive-submodule",
        "core-isolation",
        "executive/loop.py",
        "from ela.providers.claude import Claude\n",
        "ela.providers.claude.Claude",
    ),
    Case(
        "state-model-copy",
        "state-changes",
        "tasks/engine.py",
        'def run(task):\n    return task.model_copy(update={"state": TaskState.EXECUTING})\n',
        'model_copy(update={"state": ...})',
    ),
    Case(
        "state-task-constructed-executing",
        "state-changes",
        "executive/loop.py",
        "from ela.domain import Task, TaskState\n"
        "t = Task(id=i, created_at=now, goal='g', state=TaskState.EXECUTING)\n",
        "Task(state=...)",
    ),
    Case(
        "state-task-constructed-variable",
        "state-changes",
        "tasks/engine.py",
        "import ela.domain\n"
        "def make(state):\n    return ela.domain.Task(id=i, created_at=n, goal='g', state=state)\n",
        "Task(state=...)",
    ),
    Case(
        "testing-imported-by-executive",
        "testing-isolation",
        "executive/loop.py",
        "from ela.testing.fakes import FakeClock\n",
        "ela.testing.fakes.FakeClock",
    ),
    Case(
        "testing-imported-by-tasks",
        "testing-isolation",
        "tasks/engine.py",
        "import ela.testing\n",
        "ela.testing",
    ),
    Case(
        "testing-imported-by-providers",
        "testing-isolation",
        "providers/claude.py",
        "from ela import testing\n",
        "ela.testing",
    ),
    Case(
        "testing-imports-tasks",
        "testing-imports",
        "testing/extra.py",
        "from ela.tasks import state_machine\n",
        "ela.tasks.state_machine",
    ),
    Case(
        "testing-imports-providers",
        "testing-imports",
        "testing/extra.py",
        "from ela.providers import registry\n",
        "ela.providers.registry",
    ),
    Case(
        "testing-imports-pydantic",
        "testing-imports",
        "testing/extra.py",
        "import pydantic\n",
        "pydantic",
    ),
    Case(
        "infra-alembic-in-tasks",
        "infra-libraries",
        "tasks/migrate.py",
        "import alembic\n",
        "alembic",
    ),
    Case(
        "infra-aiosqlite-in-audit",
        "infra-libraries",
        "audit/store.py",
        "import aiosqlite\n",
        "aiosqlite",
    ),
    Case(
        "state-task-constructed-in-persistence",
        "state-changes",
        "infrastructure/persistence/loader.py",
        "from ela.domain import Task, TaskState\n"
        "def load(row):\n"
        "    return Task(id=row.id, created_at=row.created_at, goal=row.goal, "
        "state=TaskState(row.state))\n",
        "Task(state=...)",
    ),
    Case(
        "orm-meets-domain",
        "orm-separation",
        "infrastructure/persistence/models.py",
        "from sqlalchemy.orm import DeclarativeBase\nfrom ela.domain import Task\n",
        "ela.domain.Task",
    ),
    Case(
        "orm-meets-domain-anywhere",
        "orm-separation",
        "memory/rows.py",
        "import sqlalchemy.orm\nimport ela.domain\n",
        "ela.domain",
    ),
    Case(
        "audit-adapter-imports-update",
        "audit-append-only",
        "infrastructure/persistence/audit_log.py",
        "from sqlalchemy import select, update\n",
        "update",
    ),
    Case(
        "audit-adapter-calls-delete",
        "audit-append-only",
        "infrastructure/persistence/audit_log.py",
        "async def forget(session, row):\n    await session.delete(row)\n",
        "delete",
    ),
    Case(
        "audit-adapter-calls-merge",
        "audit-append-only",
        "infrastructure/persistence/audit_log.py",
        "def rewrite(session, row):\n    return session.merge(row)\n",
        "merge",
    ),
    Case(
        "audit-adapter-raw-sql",
        "audit-append-only",
        "infrastructure/persistence/audit_log.py",
        "from sqlalchemy import text\nPURGE = text('delete from audit_events where seq > :keep')\n",
        "text: DELETE",
    ),
    Case(
        "state-machine-imported-by-executive",
        "state-machine-callers",
        "executive/planner.py",
        "from ela.tasks.state_machine import transition\n",
        "ela.tasks.state_machine.transition",
    ),
    Case(
        "state-machine-imported-by-persistence",
        "state-machine-callers",
        "infrastructure/persistence/loader.py",
        "from ela.tasks import state_machine\n",
        "ela.tasks.state_machine",
    ),
    Case(
        "step-event-built-by-executive",
        "step-event-writers",
        "executive/orchestrator.py",
        "from ela.domain import TaskEvent, TaskEventType\n"
        "e = TaskEvent(id=i, created_at=n, task_id=t, event_type=TaskEventType.STEP_STARTED, "
        "step_id=s)\n",
        "TaskEvent(event_type=STEP_*)",
    ),
    Case(
        "step-event-built-with-a-string",
        "step-event-writers",
        "devices/node.py",
        "import ela.domain\n"
        "def done(i, n, t, s):\n"
        "    return ela.domain.TaskEvent(id=i, created_at=n, task_id=t, "
        "event_type='STEP_COMPLETED', step_id=s)\n",
        "TaskEvent(event_type=STEP_*)",
    ),
)

ALLOWED: tuple[Case, ...] = (
    Case("domain-stdlib-pydantic", "domain", "domain.py", "import enum\nimport pydantic\n", ""),
    Case("ports-domain", "ports", "ports.py", "from ela.domain import Task\nimport typing\n", ""),
    Case("ports-domain-relative", "ports", "ports.py", "from . import domain\n", ""),
    Case("infra-providers", "infra-libraries", "providers/claude.py", "import anthropic\n", ""),
    Case("infra-api", "infra-libraries", "api/app.py", "from fastapi import FastAPI\n", ""),
    Case(
        "infra-infrastructure",
        "infra-libraries",
        "infrastructure/db.py",
        "import sqlalchemy\n",
        "",
    ),
    Case("core-domain", "core-isolation", "tasks/state.py", "from ela.domain import Task\n", ""),
    Case("core-tools-providers", "core-isolation", "tools/shell.py", "import ela.providers\n", ""),
    Case(
        "state-task-created",
        "state-changes",
        "tasks/engine.py",
        "from ela.domain import Task, TaskState\n"
        "t = Task(id=i, created_at=now, goal='g', state=TaskState.CREATED)\n"
        'u = t.model_copy(update={"goal": "other"})\n',
        "",
    ),
    Case(
        "testing-self-import",
        "testing-isolation",
        "testing/extra.py",
        "from ela.testing import fakes\n",
        "",
    ),
    Case(
        "testing-imports-ports",
        "testing-imports",
        "testing/extra.py",
        "import asyncio\nfrom ela.domain import Task\nfrom ela.ports import Clock\n"
        "from ela.testing import fakes\nfrom . import fakes as again\n",
        "",
    ),
    Case(
        "infra-alembic-in-infrastructure",
        "infra-libraries",
        "infrastructure/migrate.py",
        "import alembic\nimport aiosqlite\n",
        "",
    ),
    Case(
        "state-mapper-rehydrates",
        "state-changes",
        "infrastructure/persistence/mappers.py",
        "from ela.domain import Task, TaskState\n"
        "def load(row):\n"
        "    return Task(id=row.id, created_at=row.created_at, goal=row.goal, "
        "state=TaskState(row.state))\n",
        "",
    ),
    Case(
        "mapper-imports-orm-module",
        "orm-separation",
        "infrastructure/persistence/bridge.py",
        "from ela.domain import Task\nfrom ela.infrastructure.persistence.orm import TaskRow\n",
        "",
    ),
    Case(
        "repository-imports-sqlalchemy",
        "orm-separation",
        "infrastructure/persistence/repo.py",
        "from sqlalchemy import select\nfrom sqlalchemy.ext.asyncio import AsyncSession\n"
        "from ela.domain import Task\n",
        "",
    ),
    Case(
        "orm-without-domain",
        "orm-separation",
        "infrastructure/persistence/rows.py",
        "from sqlalchemy.orm import DeclarativeBase\nfrom ela.ports import NotFoundError\n",
        "",
    ),
    Case(
        "audit-adapter-begin-immediate",
        "audit-append-only",
        "infrastructure/persistence/audit_log.py",
        "from sqlalchemy import select, text\n"
        "LOCK = text('BEGIN IMMEDIATE')\n"
        "def head(session):\n    return session.scalar(select(1))\n",
        "",
    ),
    Case(
        "task-repository-uses-update",
        "audit-append-only",
        "infrastructure/persistence/task_repository.py",
        "from sqlalchemy import update\n",
        "",
    ),
    Case(
        "state-machine-imported-by-engine",
        "state-machine-callers",
        "tasks/engine2.py",
        "from ela.tasks.state_machine import transition\nfrom . import state_machine\n",
        "",
    ),
    Case(
        "task-errors-imported-by-executive",
        "state-machine-callers",
        "executive/planner.py",
        "from ela.tasks.errors import TaskError\nfrom ela.tasks import errors\n",
        "",
    ),
    Case(
        "step-event-built-by-engine",
        "step-event-writers",
        "tasks/engine2.py",
        "from ela.domain import TaskEvent, TaskEventType\n"
        "e = TaskEvent(id=i, created_at=n, task_id=t, event_type=TaskEventType.STEP_FAILED, "
        "step_id=s)\n",
        "",
    ),
    Case(
        "note-event-built-by-executive",
        "step-event-writers",
        "executive/orchestrator.py",
        "from ela.domain import TaskEvent, TaskEventType\n"
        "e = TaskEvent(id=i, created_at=n, task_id=t, event_type=TaskEventType.NOTE)\n"
        "f = TaskEvent(id=i, created_at=n, task_id=t, event_type=kind)\n",
        "",
    ),
)

CASES = VIOLATIONS + ALLOWED


def copy_package(destination: Path) -> Path:
    """Copy ``src/ela`` under ``destination/src`` and return the copied package root."""
    pkg_root = destination / "src" / "ela"
    shutil.copytree(PACKAGE_ROOT, pkg_root, ignore=shutil.ignore_patterns("__pycache__"))
    return pkg_root


def apply(case: Case, pkg_root: Path) -> None:
    """Write the case's module into the copied package, creating packages as needed."""
    target = pkg_root / case.path
    package_dir = target.parent
    package_dir.mkdir(parents=True, exist_ok=True)
    for directory in [package_dir, *package_dir.parents]:
        if directory == pkg_root:
            break
        (directory / "__init__.py").touch()
    target.write_text(case.source, encoding="utf-8")
