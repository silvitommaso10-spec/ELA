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
    Case("infra-root-module", "infra-libraries", "sync.py", "import typer\n", "typer"),
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
        "core-routing-providers",
        "core-isolation",
        "routing/router.py",
        "from ela.providers.anthropic import AnthropicProvider\n",
        "ela.providers.anthropic.AnthropicProvider",
    ),
    Case(
        "tools-import-routing",
        "tools-routing-isolation",
        "tools/model.py",
        "from ela.routing import RoutePolicy\n",
        "ela.routing.RoutePolicy",
    ),
    Case(
        "tools-import-routing-submodule",
        "tools-routing-isolation",
        "tools/registry.py",
        "from ela.routing.policy import DEFAULT_ROUTES\n",
        "ela.routing.policy.DEFAULT_ROUTES",
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
        "testing-imports-itself",
        "testing-imports",
        "testing/extra.py",
        "from ela.testing import fakes\n",
        "ela.testing.fakes",
    ),
    Case(
        "testing-imports-itself-relatively",
        "testing-imports",
        "testing/extra.py",
        "from . import fakes as again\n",
        "ela.testing.fakes",
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
        "authorization-built-by-the-fake",
        "authorization-builders",
        "testing/extra.py",
        "from ela.domain import Authorization\n"
        "def grant(i, n, c):\n"
        "    return Authorization(id=i, created_at=n, capability_id=c, granted_by='fake')\n",
        "Authorization(...)",
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
        "sql-executed-on-a-connection",
        "tool-execute-callers",
        "infrastructure/persistence/repo.py",
        "from sqlalchemy import select\n"
        "async def head(connection):\n"
        "    await connection.execute(select(1))\n",
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
    # Rule 30 (ADR 0026 §5): a placement that names a node is the orchestrator's to build.
    Case(
        "placement-forged-by-the-runner",
        "placement-builders",
        "executive/loop.py",
        "from ela.devices import PlacementDecision\n"
        "def go(node, req):\n"
        "    return PlacementDecision(created_at=None, task_id=None, step_id=None,\n"
        "                             requirements=req, device=node, scores=(), reason='mine')\n",
        "PlacementDecision(device=...)",
    ),
    Case(
        "placement-built-without-naming-the-device",
        "placement-builders",
        "api/placements.py",
        "from ela.devices import PlacementDecision\n"
        "def go(**kw):\n    return PlacementDecision(**kw)\n",
        "PlacementDecision(device=...)",
    ),
    Case(
        "placement-widened-by-a-copy",
        "placement-builders",
        "executive/widen.py",
        "def go(placement, node):\n    return placement.model_copy(update={'device': node})\n",
        'model_copy(update={"device": ...})',
    ),
    # Rule 31 (ADR 0026 §6): the token is compared in constant time, and only so.
    Case(
        # Two reasons at once is what the real mutation produces; the harness compares one, so
        # each case isolates one reason. That the real mutation is caught — by both — is
        # ``test_the_mutation_that_survived_is_now_reported`` in ``test_layers.py``.
        "token-compared-without-the-safe-call",
        "constant-time-token",
        "api/security.py",
        "def authorized(header, token):\n"
        "    presented = header.partition(' ')[2]\n"
        "    return hash(presented) == hash(token)\n",
        "compare_digest(...)",
    ),
    Case(
        "token-compared-beside-the-safe-call",
        "constant-time-token",
        "api/security.py",
        "import secrets\n"
        "def authorized(header, token):\n"
        "    presented = header.partition(' ')[2]\n"
        "    if presented != token:\n        return False\n"
        "    return secrets.compare_digest(presented.encode(), token.encode())\n",
        "!= on the token",
    ),
    Case(
        "tool-output-on-a-second-schema",
        "tool-output-readers",
        "api/schemas.py",
        "from pydantic import BaseModel\nclass StepOut(BaseModel):\n    output: dict\n",
        "StepOut.output",
    ),
    Case(
        "tool-output-read-by-a-route",
        "tool-output-readers",
        "api/steps.py",
        "def render(result):\n    return {'what': result.output}\n",
        ".output",
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
    Case(
        "provider-called-outside-the-model-tool",
        "provider-complete-callers",
        "executive/summarise.py",
        "async def ask(provider, request):\n    return await provider.complete(request)\n",
        ".complete(",
    ),
    Case(
        "provider-called-by-a-second-tool",
        "provider-complete-callers",
        "tools/draft.py",
        "class D:\n"
        "    async def _run(self, arguments):\n"
        "        return await self._provider.complete(arguments)\n",
        ".complete(",
    ),
    Case(
        "concretes-named-by-the-api",
        "concrete-names",
        "api/wiring.py",
        "from ela.infrastructure.persistence import SqlAuditLog\n",
        "ela.infrastructure.persistence.SqlAuditLog",
    ),
    Case(
        "concretes-named-by-a-tool",
        "concrete-names",
        "tools/summary.py",
        "from ela.providers.anthropic import anthropic_provider\n",
        "ela.providers.anthropic.anthropic_provider",
    ),
    Case(
        "approval-answered-by-a-second-api-module",
        "approval-responders",
        "api/inbox.py",
        "async def yes(store, a):\n"
        "    return await store.respond(a, status=1, responded_by='x', now=0)\n",
        ".respond(",
    ),
    Case(
        "cli-composes-a-world",
        "cli-over-the-api",
        "cli/tasks.py",
        "from ela.composition import Ela\n",
        "Ela",
    ),
    Case(
        "cli-builds",
        "cli-over-the-api",
        "cli/nodes.py",
        "def go(settings: object) -> object:\n    return build(settings)\n",
        "build",
    ),
    Case(
        "cli-imports-the-api",
        "cli-over-the-api",
        "cli/system.py",
        "from ela.api import create_app\n",
        "ela.api.create_app",
    ),
    Case(
        "cli-imports-the-composition-root",
        "cli-over-the-api",
        "cli/audit.py",
        "from ela.composition.root import ELA_ACTOR\n",
        "ela.composition.root.ELA_ACTOR",
    ),
    Case(
        "cli-imported-by-the-api",
        "cli-over-the-api",
        "api/app.py",
        "from ela.cli import main\n",
        "ela.cli.main",
    ),
    # --- machine-access-in-one-place (rule 32, ADR 0028 §1) ---
    Case(
        "machine-ctypes-in-the-core",
        "machine-access-in-one-place",
        "perception/peek.py",
        "import ctypes\n",
        "ctypes",
    ),
    Case(
        "machine-subprocess-in-a-tool",
        "machine-access-in-one-place",
        "tools/run.py",
        "import subprocess\n",
        "subprocess",
    ),
    Case(
        # The spelling the milestone actually uses: an import of ``asyncio`` is innocent and the
        # call is not, so a rule reading imports alone would have been silent here.
        "machine-spawn-by-call",
        "machine-access-in-one-place",
        "tools/shell.py",
        "import asyncio\nasync def go() -> None:\n    await asyncio.create_subprocess_exec('ls')\n",
        "asyncio.create_subprocess_exec(...)",
    ),
    # --- perception-children-import-only-stdlib (rule 33, ADR 0028 §2; M10.3 dec. 6) ---
    Case(
        "probe-imports-the-domain",
        "perception-children-import-only-stdlib",
        "infrastructure/machine/probe.py",
        "from ela.domain import RawObservation\n"
        + "import sys\nif __name__ == '__main__':\n    sys.exit(0)\n",
        "ela.domain.RawObservation",
    ),
    Case(
        # The second child, and the reason the rule stopped naming one file. The subject is
        # derived from the ``__main__`` guard, so this file is covered without anybody adding it
        # to a list — which is the failure a hand-written tuple would have had.
        "the-vision-child-imports-the-domain",
        "perception-children-import-only-stdlib",
        "infrastructure/machine/vision.py",
        "from ela.domain import RawRecognition\n"
        "import sys\n"
        "if __name__ == '__main__':\n"
        "    sys.exit(0)\n",
        "ela.domain.RawRecognition",
    ),
    # --- perception-reads-no-window-titles (rule 36, M10.3 dec. 3) ---
    Case(
        # One string literal away, which is exactly why it is a rule.
        "the-probe-reaches-for-a-window-title",
        "perception-reads-no-window-titles",
        "infrastructure/machine/probe.py",
        'KEY = b"kCGWindowName"\n',
        "kCGWindowName",
    ),
    Case(
        "an-adapter-reaches-for-a-window-title-as-text",
        "perception-reads-no-window-titles",
        "infrastructure/machine/titles.py",
        'def key() -> str:\n    return "kCGWindowName"\n',
        "kCGWindowName",
    ),
    # --- machine-adapter-decides-nothing (rule 34, ADR 0028 §1) ---
    Case(
        "adapter-imports-a-state",
        "machine-adapter-decides-nothing",
        "infrastructure/machine/naming.py",
        "from ela.domain import SensorState\n",
        "ela.domain.SensorState",
    ),
    Case(
        # The long way round to the same words: no import to see, so the rule reads names too.
        "adapter-names-a-state-by-attribute",
        "machine-adapter-decides-nothing",
        "infrastructure/machine/sideways.py",
        "from ela import domain\ndef off():\n    return domain.SensorCause\n",
        "SensorCause",
    ),
    # --- context-writes-nothing (rule 38, ADR 0032 §6) ---
    Case(
        # The shape the rule exists for: a port arrives through the constructor, so there is no
        # import to see and every contract in pyproject.toml would let this through.
        "the-composer-saves-a-task",
        "context-writes-nothing",
        "context/writer.py",
        "class Composer:\n"
        "    def __init__(self, repository):\n"
        "        self._repository = repository\n"
        "    async def assemble(self, task):\n"
        "        await self._repository.save(task)\n",
        "save",
    ),
    Case(
        # The other half of "context is not action": appending to the audit is a decision, and
        # composing is not deciding (ADR 0028 §10).
        "the-composer-appends-to-the-audit",
        "context-writes-nothing",
        "context/recorder.py",
        "class Composer:\n"
        "    def __init__(self, audit):\n"
        "        self._audit = audit\n"
        "    async def assemble(self, event):\n"
        "        await self._audit.append(event)\n",
        "append",
    ),
    # --- context-is-not-recorded (rule 39, ADR 0032 §7) ---
    Case(
        "a-snapshot-reaches-a-provider",
        "context-is-not-recorded",
        "context/prompting.py",
        "from ela.domain import ContextSnapshot, ProviderRequest\n"
        "def prompt(snapshot: ContextSnapshot) -> ProviderRequest: ...\n",
        "ProviderRequest",
    ),
    Case(
        "a-snapshot-reaches-the-audit",
        "context-is-not-recorded",
        "context/recording.py",
        "from ela import domain\n"
        "def record(snapshot: domain.ContextSnapshot):\n"
        "    return domain.AuditEvent\n",
        "AuditEvent",
    ),
    # --- platform-choice-is-a-statement (rule 37, ADR 0031) ---
    Case(
        # The exact line M10.3 shipped, and the reason the rule exists: the gate reports nothing
        # here — the arm that does not run is not a missing arc — and fails one frame lower, in
        # ela.tools, on the runner that does not take it.
        "the-wiring-chooses-an-adapter-in-an-expression",
        "platform-choice-is-a-statement",
        "composition/wiring.py",
        "import platform\n"
        "from ela.infrastructure.machine import DarwinProbe, UnsupportedProbe\n"
        "def probe():\n"
        '    return DarwinProbe() if platform.system() == "Darwin" else UnsupportedProbe()\n',
        "platform.system() == 'Darwin'",
    ),
    Case(
        # Not a rule about the composition root: the next one will be written somewhere else, by
        # somebody wiring a Windows node in Fase 12, and it is the same hole there.
        "a-tool-picks-a-timeout-by-the-platform",
        "platform-choice-is-a-statement",
        "tools/patience.py",
        "import sys\n"
        "SLOW = 30.0\n"
        "FAST = 5.0\n"
        'TIMEOUT = SLOW if sys.platform == "win32" else FAST\n',
        "sys.platform == 'win32'",
    ),
    # --- content-stays-on-the-machine (rule 35, ADR 0029 §12) ---
    Case(
        # Exactly what M10.3 will be tempted to write, and the whole promise of M10.2 is that it
        # cannot be written here without somebody deciding it out loud.
        "the-capture-tool-reaches-a-router",
        "content-stays-on-the-machine",
        "tools/screen.py",
        "from ela.routing import ModelRouter\n",
        "ela.routing.ModelRouter",
    ),
    Case(
        "the-classification-reaches-an-http-client",
        "content-stays-on-the-machine",
        "tools/captures.py",
        "import httpx\n",
        "httpx",
    ),
    Case(
        # No import to see: the same reach, the long way round.
        "the-capture-tool-names-a-registry-by-attribute",
        "content-stays-on-the-machine",
        "tools/screen.py",
        "from ela import providers\ndef go():\n    return providers.ProviderRegistry\n",
        "ProviderRegistry",
    ),
    Case(
        # M10.3: the text is the easier thing to send away, so the rule reaches it too — and it
        # reached it one commit *before* this module existed (dec. 15).
        "the-ocr-tool-reaches-a-router",
        "content-stays-on-the-machine",
        "tools/screen_text.py",
        "from ela.routing import ModelRouter\n",
        "ela.routing.ModelRouter",
    ),
    Case(
        "the-vision-child-reaches-an-http-client",
        "content-stays-on-the-machine",
        "infrastructure/machine/vision.py",
        "import httpx\n",
        "httpx",
    ),
    # --- content-stays-on-the-machine extended to the voice (rule 35, M11.1 dec. H) ---
    Case(
        # The line M11.3 will want to write. It must find a closed door and not a note.
        "the-voice-tool-reaches-a-router",
        "content-stays-on-the-machine",
        "tools/voice.py",
        "from ela.routing import ModelRouter\n",
        "ela.routing.ModelRouter",
    ),
    Case(
        "the-speech-adapter-reaches-an-http-client",
        "content-stays-on-the-machine",
        "infrastructure/machine/speech.py",
        "import httpx\n",
        "httpx",
    ),
    Case(
        # No import to see: the same reach, the long way round.
        "the-voice-tool-names-a-registry-by-attribute",
        "content-stays-on-the-machine",
        "tools/voice.py",
        "from ela import providers\ndef go():\n    return providers.ProviderRegistry\n",
        "ProviderRegistry",
    ),
    # --- content-stays-on-the-machine extended to the listening (rule 35, M11.2) ---
    Case(
        # The shortest road from "ELA heard you" to "a stranger's voice left this machine": the
        # cloud STT that M11.2 refused, written into the tool that holds the words.
        "the-listening-tool-reaches-an-http-client",
        "content-stays-on-the-machine",
        "tools/listen.py",
        "import httpx\n",
        "httpx",
    ),
    Case(
        "the-listening-adapter-reaches-a-router",
        "content-stays-on-the-machine",
        "infrastructure/machine/listening.py",
        "from ela.routing import ModelRouter\n",
        "ela.routing.ModelRouter",
    ),
    Case(
        # No import to see: the same reach, the long way round.
        "the-microphone-child-names-a-registry-by-attribute",
        "content-stays-on-the-machine",
        "infrastructure/machine/microphone.py",
        "from ela import providers\ndef go():\n    return providers.ProviderRegistry\n",
        "ProviderRegistry",
    ),
    # --- the-voice-leaves-no-named-file (rule 41, M11.3 dec. F, G) ---
    Case(
        # The line that turns "ELA spoke" into "ELA kept a copy of everything it said" — and this
        # time it is not a flag, it is a forgotten deletion.
        "the-online-voice-keeps-the-audio",
        "the-voice-leaves-no-named-file",
        "infrastructure/machine/speech.py",
        "from pathlib import Path\n"
        "def keep(audio: bytes) -> None:\n"
        '    Path("/tmp/said.mp3").write_bytes(audio)\n',
        "write_bytes",
    ),
    Case(
        # The nameless file belongs to ``darwin.py``, with the rest of the door to the machine.
        # Here it would be a second place making one, and the second one is where the ``unlink``
        # goes missing.
        "the-adapter-makes-its-own-temporary-file",
        "the-voice-leaves-no-named-file",
        "providers/elevenlabs/provider.py",
        "import tempfile\n"
        "def render(audio: bytes) -> str:\n"
        "    fd, path = tempfile.mkstemp()\n"
        "    return path\n",
        "mkstemp",
    ),
    Case(
        "the-online-tool-opens-a-file-for-writing",
        "the-voice-leaves-no-named-file",
        "tools/voice_online.py",
        "def save(audio: bytes) -> None:\n"
        '    with open("said.mp3", "wb") as handle:\n'
        "        handle.write(audio)\n",
        "open",
    ),
    # --- what-ela-hears-leaves-no-named-file (rule 45, M11.2 dec. E) ---
    Case(
        # The line that turns "ELA listened" into a directory of every conversation held near this
        # machine — and unlike the voice's, this audio holds people who never agreed to be in it.
        "the-listening-adapter-keeps-the-recording",
        "what-ela-hears-leaves-no-named-file",
        "infrastructure/machine/listening.py",
        "from pathlib import Path\n"
        "def keep(audio: bytes) -> None:\n"
        '    Path("/tmp/heard.wav").write_bytes(audio)\n',
        "write_bytes",
    ),
    Case(
        # The nameless file belongs to ``darwin.py``. A second place making one is where the
        # ``unlink`` goes missing — the same failure rule 41 was written against, one direction
        # over.
        "the-microphone-child-makes-its-own-temporary-file",
        "what-ela-hears-leaves-no-named-file",
        "infrastructure/machine/microphone.py",
        "import tempfile\n"
        "def record() -> str:\n"
        "    fd, path = tempfile.mkstemp()\n"
        "    return path\n",
        "mkstemp",
    ),
    Case(
        "the-microphone-child-opens-a-file-for-writing",
        "what-ela-hears-leaves-no-named-file",
        "infrastructure/machine/microphone.py",
        "def save(samples: bytes) -> None:\n"
        '    with open("heard.wav", "wb") as handle:\n'
        "        handle.write(samples)\n",
        "open",
    ),
    # --- the-voice-goes-only-where-it-is-declared (rule 42, M11.3 dec. H) ---
    Case(
        "the-voice-adapter-talks-to-another-host",
        "the-voice-goes-only-where-it-is-declared",
        "providers/elevenlabs/provider.py",
        'MIRROR = "https://tts.example.com"\n',
        "https://tts.example.com",
    ),
    Case(
        # The same move, made respectable: an environment variable nobody reads in a diff.
        "the-voice-endpoint-becomes-a-setting",
        "the-voice-goes-only-where-it-is-declared",
        "providers/elevenlabs/settings.py",
        "class Settings:\n    base_url: str\n",
        "base_url",
    ),
    Case(
        "the-voice-adapter-reads-the-environment",
        "the-voice-goes-only-where-it-is-declared",
        "providers/elevenlabs/provider.py",
        'import os\ndef host() -> str:\n    return os.environ["ELEVEN"]\n',
        "environ",
    ),
    Case(
        # It may reach the network; it may not reach the thing that decides where words go.
        "the-voice-adapter-reaches-a-router",
        "the-voice-goes-only-where-it-is-declared",
        "providers/elevenlabs/provider.py",
        "from ela.routing import ModelRouter\n",
        "ela.routing.ModelRouter",
    ),
    # --- the-audition-speaks-only-the-repositorys-words (rule 43, M11.3 dec. I, J) ---
    Case(
        # The feature of tomorrow: "let me try my own sentence". It would be a way to say anything
        # aloud, and send it out, with no capability anywhere in sight.
        "the-audition-accepts-a-sentence",
        "the-audition-speaks-only-the-repositorys-words",
        "infrastructure/machine/audition.py",
        "async def run(voice_id: str, text: str) -> None:\n    return None\n",
        "text",
    ),
    # --- the-voice-writes-no-file (rule 40, M11.1 dec. 7) ---
    Case(
        # One flag away, which is exactly why it is a rule: `say -o` renders instead of speaking.
        "the-speech-adapter-renders-to-a-file",
        "the-voice-writes-no-file",
        "infrastructure/machine/speech.py",
        'SAY = "/usr/bin/say"\ndef argv(text, path):\n    return [SAY, "-o", path, text]\n',
        "-o",
    ),
    Case(
        "the-speech-adapter-names-a-file-format",
        "the-voice-writes-no-file",
        "infrastructure/machine/speech.py",
        'FLAGS = ["--file-format", "AIFF"]\n',
        "--file-format",
    ),
    Case(
        "the-voice-tool-asks-for-an-output-file",
        "the-voice-writes-no-file",
        "tools/voice.py",
        'def extra() -> list[str]:\n    return ["--output-file"]\n',
        "--output-file",
    ),
    # --- a-refresh-touches-only-what-is-declared (rule 44, M6.1b dec. H) ---
    Case(
        # The one somebody will really write: ``local_device`` already builds a row from a
        # declaration, so reusing it looks like reuse. It is a **birth** — ``UNKNOWN`` status,
        # ``None`` last_seen_at — and using it here would make the node unavailable until the
        # next heartbeat, at the start-up whose whole point was to keep it usable.
        "the-refresh-rebuilds-the-row-from-a-birth",
        "a-refresh-touches-only-what-is-declared",
        "devices/refresh.py",
        "from ela.devices.local import local_device\n"
        "def refreshed(now, tools):\n"
        "    return local_device(now, available_tools=tools)\n",
        "local_device",
    ),
    Case(
        # The same reset written by hand, one field at a time: a payload key.
        "the-refresh-writes-the-availability",
        "a-refresh-touches-only-what-is-declared",
        "devices/refresh.py",
        "def refreshed(current):\n"
        '    return current.model_copy(update={"availability": "UNKNOWN"})\n',
        "availability",
    ),
    Case(
        "the-refresh-passes-the-workload-along",
        "a-refresh-touches-only-what-is-declared",
        "devices/refresh.py",
        "def refreshed(current):\n    return current.model_copy(current_workload=0.0)\n",
        "current_workload",
    ),
    Case(
        # Reading it is banned too, and deliberately: the moment this module *looks* at the
        # heartbeat's half is the moment somebody decides the refresh should depend on it.
        "the-refresh-reads-the-last-sign-of-life",
        "a-refresh-touches-only-what-is-declared",
        "devices/refresh.py",
        "def stale(current) -> bool:\n    return current.last_seen_at is None\n",
        "last_seen_at",
    ),
    Case(
        # M12.1 (criterion 13): the level the user imposed, restated by the builder that is also
        # the road of a remote announcement — a node that raised its own ceiling.
        "the-refresh-writes-the-privacy",
        "a-refresh-touches-only-what-is-declared",
        "devices/refresh.py",
        "def refreshed(current):\n"
        '    return current.model_copy(update={"privacy": "LOCAL_ONLY"})\n',
        "privacy",
    ),
    Case(
        # The network is the registry's since M12.1: a node that declared ``LOCAL`` would take
        # this machine's points (ADR 0037 §10).
        "the-refresh-writes-the-network",
        "a-refresh-touches-only-what-is-declared",
        "devices/refresh.py",
        'def refreshed(current):\n    return current.model_copy(update={"network": "LOCAL"})\n',
        "network",
    ),
    Case(
        # The revision is the identity's, moved only by the conditional announcement (§9).
        "the-refresh-moves-the-revision",
        "a-refresh-touches-only-what-is-declared",
        "devices/refresh.py",
        "def next_revision(current):\n    return current.revision + 1\n",
        "revision",
    ),
    # --- constant-time-token, extended (rule 31, M12.1 dec. E) ---
    Case(
        # The second place that compares a secret: a helper beside the registry, which reads well
        # and is exactly the variable-time comparison the rule exists for.
        "a-node-secret-compared-outside-the-middleware",
        "constant-time-token",
        "devices/credentials.py",
        "def valid(presented_hash, secret_hash):\n    return presented_hash == secret_hash\n",
        "== on a node's secret",
    ),
    Case(
        # Inside the middleware too: the node's secret is a token, and ``==`` on it is ``==``.
        "a-node-secret-compared-with-equals-in-the-middleware",
        "constant-time-token",
        "api/security.py",
        "import secrets\n"
        "def token_ok(presented, token):\n"
        "    return secrets.compare_digest(presented, token)\n"
        "def node_ok(presented_hash, stored):\n"
        "    return presented_hash == stored\n",
        "== on the token",
    ),
    Case(
        # A node's hash found by value in SQL is the comparison in variable time moved into the
        # database: a node is found by its id, and its hash is compared in the middleware.
        "the-secret-hash-looked-up-in-sql",
        "constant-time-token",
        "infrastructure/persistence/device_registry.py",
        "def by_secret(presented_hash):\n    return DeviceRow.secret_hash == presented_hash\n",
        "== on a node's secret",
    ),
    # --- a-nodes-secret-crosses-no-readable-boundary (rule 46, M12.1) ---
    Case(
        # The one somebody will write first: a readable summary of a failed attempt.
        "the-secret-in-an-audit-event",
        "a-nodes-secret-crosses-no-readable-boundary",
        "devices/enrollment.py",
        "from ela.domain import AuditEvent\n"
        "def rejected(node_secret):\n"
        "    return AuditEvent(summary=node_secret)\n",
        "node_secret",
    ),
    Case(
        "the-hash-on-a-wire-shape",
        "a-nodes-secret-crosses-no-readable-boundary",
        "api/schemas.py",
        "class DeviceOut:\n    secret_hash: str\n",
        "secret_hash",
    ),
    Case(
        # The name the wire gives the node's secret (ADR 0037 §5), on a shape that is not one of
        # the two answers allowed to carry it once.
        "the-secret-on-a-wire-shape-by-its-wire-name",
        "a-nodes-secret-crosses-no-readable-boundary",
        "api/schemas.py",
        "class NodeOut:\n    secret: str\n",
        "secret",
    ),
    Case(
        "the-code-on-a-wire-shape-by-its-wire-name",
        "a-nodes-secret-crosses-no-readable-boundary",
        "api/schemas.py",
        "class DeviceOut:\n    code: str\n",
        "code",
    ),
    Case(
        # On the entity, every reader of the registry would carry it: the orchestrator, /devices,
        # the context. The row may keep it; the entity may not.
        "the-hash-as-a-field-of-the-device",
        "a-nodes-secret-crosses-no-readable-boundary",
        "domain.py",
        "class Device:\n    secret_hash: str\n",
        "secret_hash",
    ),
    # --- identity-resolved-in-one-place (rule 47, M12.1) ---
    Case(
        # The shortest way a route learns who called — and the second place that forgets a
        # revocation.
        "a-route-reads-the-header",
        "identity-resolved-in-one-place",
        "api/approvals.py",
        "def responder(request):\n    return request.headers.get('Authorization')\n",
        "authorization",
    ),
    # --- assignment-port-readers (rule 48, M12.2) ---
    Case(
        # The route that takes work, reading the row as written: an OFFERED row an hour past its
        # expiry would still be handed out, and a claim written here has no heartbeat before it.
        "the-work-route-reads-the-port",
        "assignment-port-readers",
        "api/nodes.py",
        "from ela.ports import AssignmentStore\n",
        "ela.ports.AssignmentStore",
    ),
    # --- assignments-built-only-by-the-assigner (rule 49, M12.2) ---
    Case(
        # A route that hands work to whoever asked: no placement, no check on the decision.
        "an-assignment-forged-by-a-route",
        "assignments-built-only-by-the-assigner",
        "api/nodes.py",
        "from ela.domain import Assignment\n"
        "def forge(**fields):\n"
        "    return Assignment(**fields)\n",
        "Assignment(...)",
    ),
    Case(
        # The same forgery through the door pydantic leaves open beside the call.
        "an-assignment-validated-into-being",
        "assignments-built-only-by-the-assigner",
        "executive/runner.py",
        "from ela.domain import Assignment\n"
        "def forge(row):\n"
        "    return Assignment.model_validate(row)\n",
        "Assignment.model_validate(...)",
    ),
    # --- release-step-has-one-caller (rule 50, M12.2) ---
    Case(
        # The runner cannot see the store: it would release a step whose tool may have acted.
        "the-runner-releases-a-step",
        "release-step-has-one-caller",
        "executive/runner.py",
        "async def go(engine, task_id, step_id, key):\n"
        "    await engine.release_step(task_id, step_id, key=key)\n",
        ".release_step(",
    ),
    # --- a-work-order-goes-only-to-its-node (rule 51, M12.2) ---
    Case(
        # A second composer: an order built where nobody compares the node that asked with the
        # node the assignment names.
        "a-second-module-composes-an-order",
        "a-work-order-goes-only-to-its-node",
        "api/tasks.py",
        "from ela.api.schemas import WorkOrderOut\n"
        "def order(**fields):\n"
        "    return WorkOrderOut(**fields)\n",
        "WorkOrderOut(...)",
    ),
    Case(
        # The composer with a way out other than the answer: the user's arguments could be sent
        # to whoever it pleased.
        "the-composer-reaches-the-network",
        "a-work-order-goes-only-to-its-node",
        "api/nodes.py",
        "import httpx\n"
        "from ela.api.schemas import WorkOrderOut\n"
        "def order(**fields):\n"
        "    return WorkOrderOut(**fields)\n",
        "httpx",
    ),
    # --- results-are-minted-by-the-core (rule 52, M12.2) ---
    Case(
        # A route that turns the envelope into the entity: the node's id and the node's clock in
        # the store, and the node's clock in the chain.
        "a-route-mints-a-result",
        "results-are-minted-by-the-core",
        "api/nodes.py",
        "from ela.domain import ExecutionResult\n"
        "def mint(**fields):\n"
        "    return ExecutionResult(**fields)\n",
        "ExecutionResult(...)",
    ),
)
ALLOWED: tuple[Case, ...] = (
    Case(
        # The enrollment code is found by its hash, in the conditional UPDATE that spends it
        # (M12.1 dec. D; ADR 0037 §5): rule 31 is about the node's secret (ADR 0037 §16), and a
        # lookup by the hash of a 256-bit value can leak at most the hash, which is not the code.
        "the-code-looked-up-by-its-hash",
        "constant-time-token",
        "infrastructure/persistence/enrollment_store.py",
        "def unspent(code_hash):\n    return EnrollmentRow.code_hash == code_hash\n",
        "",
    ),
    Case(
        # Asking whether a hash exists says nothing about it: ``is None`` is not a comparison by
        # value, and the registry will need it for a node that was never enrolled.
        "a-hash-asked-whether-it-exists",
        "constant-time-token",
        "devices/credentials.py",
        "def enrolled(secret_hash):\n    return secret_hash is not None\n",
        "",
    ),
    Case(
        # The vault is not a boundary: the ORM row keeps the hash (M12.1 dec. G), and nobody reads
        # the row but the adapter.
        "the-hash-kept-by-the-row",
        "a-nodes-secret-crosses-no-readable-boundary",
        "infrastructure/persistence/orm.py",
        "class DeviceRow:\n    secret_hash: str\n",
        "",
    ),
    Case(
        # The one reader the rule allows, and the one that exists today.
        "the-middleware-reads-the-header",
        "identity-resolved-in-one-place",
        "api/security.py",
        "def guard(request):\n    return request.headers.get('authorization')\n",
        "",
    ),
    Case(
        # Declaring the operation is not calling it: the engine owns the move, the service asks.
        "the-engine-defines-the-release",
        "release-step-has-one-caller",
        "tasks/engine.py",
        "class Engine:\n    async def release_step(self, task_id, step_id, *, key):\n"
        "        return None\n",
        "",
    ),
    Case(
        # The one composer the rule admits, answering only its caller: the door rule 51 opens.
        "the-composer-builds-the-order",
        "a-work-order-goes-only-to-its-node",
        "api/nodes.py",
        "from ela.api.schemas import WorkOrderOut\n"
        "def order(**fields):\n"
        "    return WorkOrderOut(**fields)\n",
        "",
    ),
    Case(
        # The executor mints results, and rule 52 is about ``ela.api`` only.
        "the-executor-mints-the-result",
        "results-are-minted-by-the-core",
        "executive/executor.py",
        "from ela.domain import ExecutionResult\n"
        "def mint(**fields):\n"
        "    return ExecutionResult(**fields)\n",
        "",
    ),
    Case(
        # Naming the class is not building it: an annotation carries no assignment anywhere.
        "an-assignment-only-named",
        "assignments-built-only-by-the-assigner",
        "executive/runner.py",
        "from ela.domain import Assignment\ndef out(held: Assignment) -> Assignment:\n"
        "    return held\n",
        "",
    ),
    Case(
        # The shape M6.1b actually uses: the stored row, with the declared half replaced and
        # nothing else named — so the four fields the heartbeat owns travel through untouched
        # without this module ever mentioning one of them.
        "the-refresh-replaces-only-the-declared-half",
        "a-refresh-touches-only-what-is-declared",
        "devices/refresh.py",
        "from ela.domain import Device\n"
        "def refreshed(current: Device, change: dict[str, object]) -> Device:\n"
        "    return Device.model_validate({**current.model_dump(), **change})\n",
        "",
    ),
    Case(
        # The shape M11.3 actually uses: the voice holds the bytes for as long as it takes to hand
        # them over, and the file — the one with no name — is made on the other side of the door.
        "the-voice-hands-the-audio-to-the-spawner",
        "the-voice-leaves-no-named-file",
        "infrastructure/machine/speech.py",
        "from ela.infrastructure.machine.darwin import spawn_with_audio\n"
        "async def play(audio: bytes) -> int:\n"
        '    code, _ = await spawn_with_audio(["/usr/bin/afplay"], audio, 60.0)\n'
        "    return code\n",
        "",
    ),
    Case(
        "the-voice-may-read-a-file",
        "the-voice-leaves-no-named-file",
        "tools/voice_online.py",
        'def read() -> bytes:\n    with open("/etc/hostname", "rb") as handle:\n'
        "        return handle.read()\n",
        "",
    ),
    Case(
        # The door, open exactly as wide as it was opened: an HTTP client aimed at the one host
        # that was declared. Anything else about this module is still shut.
        "the-voice-adapter-may-hold-an-http-client",
        "the-voice-goes-only-where-it-is-declared",
        "providers/elevenlabs/provider.py",
        "import httpx\n"
        'ELEVENLABS_API = "https://api.elevenlabs.io"\n'
        "async def speak(voice_id: str) -> bytes:\n"
        "    async with httpx.AsyncClient() as client:\n"
        '        answer = await client.post(f"{ELEVENLABS_API}/v1/text-to-speech/{voice_id}")\n'
        "    return answer.content\n",
        "",
    ),
    Case(
        "the-audition-chooses-a-voice-and-a-model",
        "the-audition-speaks-only-the-repositorys-words",
        "infrastructure/machine/audition.py",
        'PHRASES = ("No, questa non è una buona idea.",)\n'
        "async def run(voice_id: str, model: str) -> tuple[str, ...]:\n"
        "    return PHRASES\n",
        "",
    ),
    Case(
        "a-placement-that-names-nobody",
        "placement-builders",
        "executive/waiting.py",
        "from ela.devices import PlacementDecision\n"
        "def go(req):\n"
        "    return PlacementDecision(created_at=None, task_id=None, step_id=None,\n"
        "                             requirements=req, device=None, scores=(), reason='wait')\n",
        "",
    ),
    Case(
        "the-orchestrator-names-a-device",
        "placement-builders",
        "devices/second.py",
        "from ela.devices.orchestrator import PlacementDecision\n"
        "def go(node, req):\n"
        "    return PlacementDecision(created_at=None, task_id=None, step_id=None,\n"
        "                             requirements=req, device=node, scores=(), reason='ok')\n",
        "",
    ),
    Case(
        "the-scheme-may-be-compared-in-plain-sight",
        "constant-time-token",
        "api/security.py",
        "import secrets\n"
        "SCHEME = 'bearer'\n"
        "def authorized(header, token):\n"
        "    scheme, _, presented = header.partition(' ')\n"
        "    if scheme.lower() != SCHEME:\n        return False\n"
        "    return secrets.compare_digest(presented.strip().encode(), token.encode())\n",
        "",
    ),
    Case(
        "cli-serve-imports-the-api",
        "cli-over-the-api",
        "cli/serve.py",
        "from ela.api import server\n",
        "",
    ),
    Case(
        "cli-reads-the-settings",
        "cli-over-the-api",
        "cli/client.py",
        "from ela.composition.settings import ApiSettings\n",
        "",
    ),
    Case(
        "cli-imports-a-sibling",
        "cli-over-the-api",
        "cli/output.py",
        "from ela.cli.client import connect\n",
        "",
    ),
    Case(
        "tools-import-the-router-port",
        "tools-routing-isolation",
        "tools/model.py",
        "from ela.ports import ModelRouterPort\n",
        "",
    ),
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
        "the-composition-root-names-the-concretes",
        "concrete-names",
        "composition/wiring.py",
        "from ela.infrastructure.persistence import SqlAuditLog\n"
        "from ela.providers.anthropic import anthropic_provider\n",
        "",
    ),
    Case(
        "an-adapter-may-import-its-neighbours",
        "concrete-names",
        "infrastructure/persistence/extra.py",
        "from ela.infrastructure.persistence import make_engine\n",
        "",
    ),
    Case(
        "the-api-answers-approvals",
        "approval-responders",
        "api/approvals.py",
        "async def yes(store, a):\n"
        "    return await store.respond(a, status=1, responded_by='x', now=0)\n",
        "",
    ),
    Case(
        "engine-complete-is-not-a-provider",
        "provider-complete-callers",
        "executive/closer.py",
        "class R:\n"
        "    async def close(self, t, r):\n"
        "        return await self._engine.complete(t, r)\n",
        "",
    ),
    Case(
        "defining-complete-is-not-calling-it",
        "provider-complete-callers",
        "providers/echo.py",
        "class P:\n    async def complete(self, request):\n        return request\n",
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
        "import asyncio\nfrom ela.domain import Task\nfrom ela.ports import Clock\n",
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
        "async def head(session, cursor):\n"
        "    await session.execute(select(1))\n"
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
        "the-one-model-that-carries-the-output",
        "tool-output-readers",
        "api/schemas.py",
        "from pydantic import BaseModel\n"
        "class ExecutionResultOut(BaseModel):\n"
        "    output: dict\n"
        "    @classmethod\n"
        "    def of(cls, result):\n"
        "        return cls(output=result.output)\n",
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
    Case(
        "the-adapter-may-reach-the-machine",
        "machine-access-in-one-place",
        "infrastructure/machine/extra.py",
        "import ctypes\n",
        "",
    ),
    Case(
        # The guard is not decoration: it is what makes this file a *child*, so without it the
        # rule would have nothing to read and this case would pass for the wrong reason.
        "the-probe-may-use-the-standard-library",
        "perception-children-import-only-stdlib",
        "infrastructure/machine/probe.py",
        "import ctypes\nimport json\n"
        + "import sys\nif __name__ == '__main__':\n    sys.exit(0)\n",
        "",
    ),
    Case(
        # The same choice as a statement: two arcs the gate measures, and a direction nobody
        # proves is a direction the gate refuses. This is the shape the rule pushes you into.
        "the-wiring-may-choose-in-an-if",
        "platform-choice-is-a-statement",
        "composition/wiring.py",
        "import platform\n"
        "from ela.infrastructure.machine import DarwinProbe, UnsupportedProbe\n"
        "def probe():\n"
        '    if platform.system() == "Darwin":\n'
        "        return DarwinProbe()\n"
        "    return UnsupportedProbe()\n",
        "",
    ),
    Case(
        # The rule reads the *condition*, not the branches: this ternary answers "was an argument
        # given", which every runner takes both ways, and it is what ela.devices.local really
        # writes. A rule that flagged it would be a rule about ternaries.
        "a-default-that-happens-to-be-the-platform-is-not-a-platform-choice",
        "platform-choice-is-a-statement",
        "devices/defaulting.py",
        "import platform\n"
        "def system(given: str | None) -> str:\n"
        "    return platform.system() if given is None else given\n",
        "",
    ),
    Case(
        "the-adapter-may-name-the-primitives",
        "machine-adapter-decides-nothing",
        "infrastructure/machine/plain.py",
        "from ela.domain import ProbeFamily, RawObservation\n",
        "",
    ),
    Case(
        # Rule 35 is not a rule about tools: ``ela.tools.model`` names the router on purpose and
        # must. It is a rule about the two modules that have the user's screen in their hands.
        "another-tool-may-still-reach-the-router",
        "content-stays-on-the-machine",
        "tools/model.py",
        "from ela.routing import ModelRouter\n",
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
