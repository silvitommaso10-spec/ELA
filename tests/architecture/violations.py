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
    Case(
        "permissions-imports-tasks",
        "permissions-imports",
        "permissions/guardian.py",
        "from ela.tasks.engine import TaskEngine\n",
        "ela.tasks.engine.TaskEngine",
    ),
    Case(
        "permissions-imports-tools",
        "permissions-imports",
        "permissions/guardian.py",
        "import ela.tools\n",
        "ela.tools",
    ),
    Case(
        "permissions-imports-pydantic",
        "permissions-imports",
        "permissions/policy.py",
        "import pydantic\n",
        "pydantic",
    ),
    Case(
        "permissions-imports-audit",
        "permissions-imports",
        "permissions/policy.py",
        "from ela.audit import chain\n",
        "ela.audit.chain",
    ),
    Case(
        "decision-allowed-by-executive",
        "decision-builders",
        "executive/loop.py",
        "from ela.domain import PermissionDecision, PermissionOutcome\n"
        "d = PermissionDecision(id=i, created_at=n, capability_id=c, "
        "outcome=PermissionOutcome.ALLOWED, risk=r, reason='ok')\n",
        "PermissionDecision(outcome=...)",
    ),
    Case(
        "decision-allowed-with-a-string",
        "decision-builders",
        "tools/shell.py",
        "import ela.domain\n"
        "def ok(i, n, c, r):\n"
        "    return ela.domain.PermissionDecision(id=i, created_at=n, capability_id=c, "
        "outcome='ALLOWED', risk=r, reason='ok')\n",
        "PermissionDecision(outcome=...)",
    ),
    Case(
        "decision-outcome-from-a-variable",
        "decision-builders",
        "executive/loop.py",
        "from ela.domain import PermissionDecision\n"
        "def build(i, n, c, r, outcome):\n"
        "    return PermissionDecision(id=i, created_at=n, capability_id=c, "
        "outcome=outcome, risk=r, reason='?')\n",
        "PermissionDecision(outcome=...)",
    ),
    Case(
        "decision-built-from-kwargs",
        "decision-builders",
        "infrastructure/persistence/decisions.py",
        "from ela.domain import PermissionDecision\n"
        "def load(row):\n    return PermissionDecision(**row)\n",
        "PermissionDecision(outcome=...)",
    ),
    Case(
        "decision-outcome-copied",
        "decision-builders",
        "executive/loop.py",
        "from ela.domain import PermissionOutcome\n"
        "def soften(d):\n"
        '    return d.model_copy(update={"outcome": PermissionOutcome.ALLOWED})\n',
        'model_copy(update={"outcome": ...})',
    ),
    Case(
        "decide-called-by-executive",
        "decide-callers",
        "executive/loop.py",
        "def run(guardian, spec, args):\n    return guardian.decide(spec, args)\n",
        ".decide(",
    ),
    Case(
        "authorization-built-by-executive",
        "authorization-builders",
        "executive/loop.py",
        "from ela.domain import Authorization\n"
        "def grant(i, n, c):\n"
        "    return Authorization(id=i, created_at=n, capability_id=c, granted_by='ela')\n",
        "Authorization(...)",
    ),
    Case(
        "authorization-built-via-the-module",
        "authorization-builders",
        "tools/shell.py",
        "import ela.domain\n"
        "def grant(i, n, c):\n"
        "    return ela.domain.Authorization(id=i, created_at=n, capability_id=c, "
        "granted_by='ela')\n",
        "Authorization(...)",
    ),
    Case(
        "authorization-widened-by-copy",
        "authorization-builders",
        "executive/loop.py",
        'def reuse(a):\n    return a.model_copy(update={"max_uses": None})\n',
        "model_copy(update={'max_uses': ...})",
    ),
    Case(
        "authorization-unbound-by-copy",
        "authorization-builders",
        "executive/loop.py",
        'def unbind(a):\n    return a.model_copy(update={"task_id": None, "step_id": None})\n',
        "model_copy(update={'step_id': ...})",
    ),
    Case(
        "authorization-built-by-another-persistence-module",
        "authorization-builders",
        "infrastructure/persistence/rows.py",
        "from ela.domain import Authorization\ndef load(row):\n    return Authorization(**row)\n",
        "Authorization(...)",
    ),
    Case(
        "decide-called-by-tools",
        "decide-callers",
        "tools/runner.py",
        "async def run(self, spec, args):\n"
        "    return await self._executor.guardian.decide(spec, args, task=None)\n",
        ".decide(",
    ),
    Case(
        "tool-executed-by-tools",
        "tool-execute-callers",
        "tools/runner.py",
        "async def run(tool, decision, args):\n    return await tool.execute(decision, args)\n",
        ".execute(",
    ),
    Case(
        "tool-executed-by-another-executive-module",
        "tool-execute-callers",
        "executive/orchestrator.py",
        "class O:\n    async def run(self, d, a):\n        return await self._tool.execute(d, a)\n",
        ".execute(",
    ),
    Case(
        "tool-executed-inside-persistence",
        "tool-execute-callers",
        "infrastructure/persistence/rows.py",
        "async def run(tool, d, a):\n    return await tool.execute(d, a)\n",
        ".execute(",
    ),
    Case(
        "step-completed-by-another-executive-module",
        "step-completers",
        "executive/orchestrator.py",
        "class O:\n"
        "    async def run(self, t, s, r):\n"
        "        return await self._engine.complete_step(t, s, r)\n",
        ".complete_step(",
    ),
    Case(
        "step-completed-by-tasks",
        "step-completers",
        "tasks/runner.py",
        "async def run(engine, t, s, r):\n    return await engine.complete_step(t, s, r)\n",
        ".complete_step(",
    ),
    Case(
        "approval-answered-by-the-executor",
        "approval-responders",
        "executive/executor.py",
        "class X:\n"
        "    async def run(self, a):\n"
        "        return await self._approvals.respond(a, status=1, responded_by='ela', now=0)\n",
        ".respond(",
    ),
    Case(
        "approval-answered-by-tasks",
        "approval-responders",
        "tasks/answers.py",
        "async def run(store, a):\n"
        "    return await store.respond(a, status=1, responded_by='x', now=0)\n",
        ".respond(",
    ),
    Case(
        "verifier-opens-for-writing",
        "verifier-read-only",
        "tools/verifiers.py",
        "def w(p):\n    with open(p, 'w') as h:\n        return h\n",
        "open(",
    ),
    Case(
        "verifier-opens-with-a-variable-mode",
        "verifier-read-only",
        "tools/verifiers.py",
        "def w(p, m):\n    return open(p, mode=m)\n",
        "open(",
    ),
    Case(
        "verifier-os-opens-for-writing",
        "verifier-read-only",
        "tools/verifiers.py",
        "import os\ndef w(p):\n    return os.open(p, os.O_WRONLY | os.O_CREAT)\n",
        ".open(",
    ),
    Case(
        "verifier-fdopens-for-writing",
        "verifier-read-only",
        "tools/verifiers.py",
        "import os\ndef w(fd):\n    return os.fdopen(fd, 'wb')\n",
        ".fdopen(",
    ),
    Case(
        "verifier-writes-a-descriptor",
        "verifier-read-only",
        "tools/verifiers.py",
        "import os\ndef w(fd):\n    return os.write(fd, b'x')\n",
        ".write(",
    ),
    Case(
        "verifier-unlinks",
        "verifier-read-only",
        "tools/verifiers.py",
        "import os\ndef w(p):\n    os.unlink(p)\n",
        ".unlink(",
    ),
    Case(
        "verifier-renames",
        "verifier-read-only",
        "tools/verifiers.py",
        "from pathlib import Path\ndef w(p, q):\n    Path(p).rename(q)\n",
        ".rename(",
    ),
    Case(
        "verifier-writes-text",
        "verifier-read-only",
        "tools/verifiers.py",
        "from pathlib import Path\ndef w(p):\n    Path(p).write_text('')\n",
        ".write_text(",
    ),
    Case(
        "verifier-makes-a-directory",
        "verifier-read-only",
        "tools/verifiers.py",
        "from pathlib import Path\ndef w(p):\n    Path(p).mkdir(parents=True)\n",
        ".mkdir(",
    ),
    Case(
        "verifier-uses-shutil",
        "verifier-read-only",
        "tools/verifiers.py",
        "import shutil\ndef w(p, q):\n    shutil.copymode(p, q)\n",
        ".copymode(",
    ),
    Case(
        "path-classification-unlinks",
        "verifier-read-only",
        "tools/paths.py",
        "import os\ndef w(p):\n    os.unlink(p)\n",
        ".unlink(",
    ),
    Case(
        "path-classification-touches",
        "verifier-read-only",
        "tools/paths.py",
        "from pathlib import Path\ndef w(p):\n    Path(p).touch()\n",
        ".touch(",
    ),
    Case(
        "availability-read-in-executive",
        "device-availability-readers",
        "executive/placement.py",
        "def usable(device):\n    return device.availability == 'ONLINE'\n",
        ".availability",
    ),
    Case(
        "availability-built-in-tasks",
        "device-availability-readers",
        "tasks/nodes.py",
        "from ela.domain import Device\n"
        "def make(i, n):\n"
        "    return Device(id=i, created_at=n, availability='ONLINE')\n",
        "availability=",
    ),
    Case(
        "device-port-in-executive",
        "device-port-readers",
        "executive/placement.py",
        "from ela.ports import DeviceRegistryPort\n"
        "async def nodes(port: DeviceRegistryPort):\n    return await port.devices()\n",
        "ela.ports.DeviceRegistryPort",
    ),
    Case(
        "device-port-in-testing",
        "device-port-readers",
        "testing/nodes.py",
        "from ela.ports import DeviceRegistryPort\n",
        "ela.ports.DeviceRegistryPort",
    ),
    Case(
        "device-port-in-api",
        "device-port-readers",
        "api/wiring.py",
        "from ela.ports import DeviceRegistryPort\n",
        "ela.ports.DeviceRegistryPort",
    ),
    Case(
        "devices-import-tasks",
        "devices-isolation",
        "devices/placement.py",
        "from ela.tasks.engine import TaskEngine\n",
        "ela.tasks.engine.TaskEngine",
    ),
    Case(
        "devices-import-tasks-relative",
        "devices-isolation",
        "devices/placement.py",
        "from ..tasks import graph\n",
        "ela.tasks.graph",
    ),
    Case(
        "executor-receiver-outside-the-runner",
        "tool-execute-callers",
        "executive/loop.py",
        "class R:\n"
        "    async def run(self, t, s, d):\n"
        "        return await self._executor.execute(t, s, device_id=d)\n",
        ".execute(",
    ),
    Case(
        "tool-executed-by-a-lookalike-receiver",
        "tool-execute-callers",
        "executive/loop.py",
        "class R:\n    async def run(self, d, a):\n        return await self._tool.execute(d, a)\n",
        ".execute(",
    ),
    Case(
        "audit-arguments-as-a-payload-key",
        "audit-arguments",
        "executive/trace.py",
        "from ela.domain import AuditEvent\n"
        "def event(i, n, t, args):\n"
        "    return AuditEvent(id=i, created_at=n, event_type=t, "
        'payload={"arguments": args})\n',
        '"arguments"',
    ),
    Case(
        "audit-arguments-as-a-variable",
        "audit-arguments",
        "executive/trace.py",
        "from ela.domain import AuditEvent\n"
        "def event(i, n, t, arguments):\n"
        "    return AuditEvent(id=i, created_at=n, event_type=t, "
        'payload={"what": arguments})\n',
        "arguments",
    ),
    Case(
        "audit-arguments-from-the-step",
        "audit-arguments",
        "tasks/trace.py",
        "from ela.domain import AuditEvent\n"
        "def event(i, n, t, step):\n"
        "    return AuditEvent(id=i, created_at=n, event_type=t, "
        'payload={"what": step.arguments})\n',
        ".arguments",
    ),
    Case(
        "anthropic-in-the-registry",
        "anthropic-import-isolation",
        "providers/registry.py",
        "import anthropic\n",
        "anthropic",
    ),
    Case(
        "anthropic-in-the-executor",
        "anthropic-import-isolation",
        "executive/summary.py",
        "from anthropic import AsyncAnthropic\n",
        "anthropic.AsyncAnthropic",
    ),
)

ALLOWED: tuple[Case, ...] = (
    Case(
        "availability-inside-devices",
        "device-availability-readers",
        "devices/policy.py",
        "def usable(device):\n    return device.availability == 'ONLINE'\n",
        "",
    ),
    Case(
        "device-port-in-the-registry",
        "device-port-readers",
        "devices/store.py",
        "from ela.ports import DeviceRegistryPort\n",
        "",
    ),
    Case(
        "devices-import-ports-and-domain",
        "devices-isolation",
        "devices/placement.py",
        "from ela.domain import Device\nfrom ela.ports import AuditLog\n",
        "",
    ),
    Case(
        "runner-calls-the-executor",
        "tool-execute-callers",
        "executive/runner.py",
        "class R:\n"
        "    async def run(self, t, s, d):\n"
        "        return await self._executor.execute(t, s, device_id=d)\n",
        "",
    ),
    Case(
        "anthropic-inside-its-adapter",
        "anthropic-import-isolation",
        "providers/anthropic/other.py",
        "import anthropic\nfrom anthropic import AsyncAnthropic\n",
        "",
    ),
    Case(
        "the-adapter-package-is-not-the-library",
        "anthropic-import-isolation",
        "providers/registry.py",
        "from ela.providers.anthropic import AnthropicProvider\n",
        "",
    ),
    Case(
        "audit-targets-not-arguments",
        "audit-arguments",
        "executive/trace.py",
        "from ela.domain import AuditEvent\n"
        "def event(i, n, t, targets):\n"
        "    return AuditEvent(id=i, created_at=n, event_type=t, "
        'payload={"targets": list(targets)})\n',
        "",
    ),
    Case(
        "arguments-outside-an-audit-event",
        "audit-arguments",
        "executive/pipeline.py",
        "async def call(tool, decision, arguments):\n"
        "    return await tool.execute(decision, arguments)\n",
        "",
    ),
    Case("domain-stdlib-pydantic", "domain", "domain.py", "import enum\nimport pydantic\n", ""),
    Case(
        "approval-store-defines-respond",
        "approval-responders",
        "infrastructure/persistence/answers.py",
        "class S:\n"
        "    async def respond(self, a, *, status, responded_by, now):\n"
        "        return a\n",
        "",
    ),
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
    Case(
        "permissions-imports-domain-ports-jsonschema",
        "permissions-imports",
        "permissions/extra.py",
        "import json\nimport jsonschema\nfrom jsonschema import Draft202012Validator\n"
        "from ela.domain import CapabilitySpec\nfrom ela.ports import NotFoundError\n"
        "from ela.permissions import capabilities\nfrom . import errors\n",
        "",
    ),
    Case(
        "decision-allowed-by-the-guardian",
        "decision-builders",
        "permissions/guardian2.py",
        "from ela.domain import PermissionDecision, PermissionOutcome\n"
        "d = PermissionDecision(id=i, created_at=n, capability_id=c, "
        "outcome=PermissionOutcome.ALLOWED, risk=r, reason='ok')\n",
        "",
    ),
    Case(
        "decision-allowed-by-the-fake",
        "decision-builders",
        "testing/extra.py",
        "from ela.domain import PermissionDecision, PermissionOutcome\n"
        "def table(i, n, c, r, outcome):\n"
        "    return PermissionDecision(id=i, created_at=n, capability_id=c, "
        "outcome=outcome, risk=r, reason='table')\n",
        "",
    ),
    Case(
        "decision-denied-by-executive",
        "decision-builders",
        "executive/loop.py",
        "import ela.domain\nfrom ela.domain import PermissionDecision, PermissionOutcome\n"
        "d = PermissionDecision(id=i, created_at=n, capability_id=c, "
        "outcome=PermissionOutcome.DENIED, risk=r, reason='no')\n"
        "e = ela.domain.PermissionDecision(id=i, created_at=n, capability_id=c, "
        "outcome='DENIED', risk=r, reason='no')\n"
        'f = d.model_copy(update={"reason": "still no"})\n',
        "",
    ),
    Case(
        "authorization-built-by-permissions",
        "authorization-builders",
        "permissions/policy.py",
        "from ela.domain import Authorization\n"
        "def grant(i, n, c):\n"
        "    return Authorization(id=i, created_at=n, capability_id=c, granted_by='policy')\n",
        "",
    ),
    Case(
        "authorization-built-by-the-fake",
        "authorization-builders",
        "testing/extra.py",
        "from ela.domain import Authorization\n"
        "def grant(i, n, c):\n"
        "    return Authorization(id=i, created_at=n, capability_id=c, granted_by='fake')\n",
        "",
    ),
    Case(
        "authorization-copied-without-widening",
        "authorization-builders",
        "executive/loop.py",
        "from ela.domain import AuthorizationId\n"
        'def relabel(a, i):\n    return a.model_copy(update={"metadata": {"seen": True}})\n'
        "def key(a):\n    return AuthorizationId(a.id)\n",
        "",
    ),
    Case(
        "decide-called-by-the-guardian",
        "decide-callers",
        "permissions/guardian2.py",
        "class G:\n"
        "    async def authorize(self, spec, args):\n"
        "        return self.decide(spec, args)\n",
        "",
    ),
    Case(
        "decide-defined-by-the-fake",
        "decide-callers",
        "testing/extra.py",
        "class FakeG:\n"
        "    def decide(self, spec, args):\n"
        "        return decide_table(spec, args)\n",
        "",
    ),
    Case(
        "tool-executed-by-the-executor",
        "tool-execute-callers",
        "executive/executor.py",
        "async def run(tool, decision, args):\n    return await tool.execute(decision, args)\n",
        "",
    ),
    Case(
        "sql-executed-by-persistence",
        "tool-execute-callers",
        "infrastructure/persistence/repo.py",
        "from sqlalchemy import select\n"
        "async def head(session, connection, cursor):\n"
        "    await session.execute(select(1))\n"
        "    await connection.execute(select(1))\n"
        "    cursor.execute('PRAGMA foreign_keys=ON')\n",
        "",
    ),
    Case(
        "execute-defined-by-a-tool",
        "tool-execute-callers",
        "tools/extra.py",
        "class T:\n"
        "    async def execute(self, decision, arguments):\n"
        "        return run(decision, arguments)\n",
        "",
    ),
    Case(
        "step-completed-by-the-executor",
        "step-completers",
        "executive/executor.py",
        "async def run(engine, t, s, r):\n    return await engine.complete_step(t, s, r)\n",
        "",
    ),
    Case(
        "complete-step-defined-by-the-engine",
        "step-completers",
        "tasks/engine2.py",
        "class E:\n    async def complete_step(self, t, s, r):\n        return r\n",
        "",
    ),
    Case(
        "verifier-reads-only",
        "verifier-read-only",
        "tools/verifiers.py",
        "import os\n"
        "def r(p):\n"
        "    d = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)\n"
        "    with os.fdopen(d, 'rb') as h:\n"
        "        return h.read()\n"
        "def s(p):\n"
        "    with open(p, 'rb') as h, open(p) as g:\n"
        "        return h.read() + g.read()\n"
        "def t(p):\n"
        "    return os.lstat(p).st_mode, os.fstat(3)\n",
        "",
    ),
    Case(
        "writes-outside-the-verifiers-module",
        "verifier-read-only",
        "tools/extra.py",
        "import os\ndef w(p):\n    os.unlink(p)\n",
        "",
    ),
    Case(
        "path-classification-reads-only",
        "verifier-read-only",
        "tools/paths.py",
        "from pathlib import Path\n"
        "def c(root, p):\n"
        "    t = Path(root) / p\n"
        "    return t.resolve(), t.is_symlink(), t.lstat().st_mode\n",
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
