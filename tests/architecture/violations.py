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
