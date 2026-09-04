"""Architecture rules of ELA as pure functions over a source tree (CLAUDE.md, spec §52).

Every rule takes the root directory of the ``ela`` package (``src/ela``) and returns the
violations it finds; an empty list means the rule holds. The rules read source files with
``ast`` and never import the modules they check, so they run unchanged on a temporary copy
of the tree (see ``test_rules_detect_violations.py``).
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

ROOT_PACKAGE = "ela"
STDLIB = frozenset(sys.stdlib_module_names)

#: The only third-party package the domain model may use.
DOMAIN_ALLOWED_EXTERNAL = frozenset({"pydantic"})
#: The only internal module the ports may use.
PORTS_ALLOWED_INTERNAL = f"{ROOT_PACKAGE}.domain"
#: Infrastructure libraries the Core must never import.
INFRA_LIBRARIES = frozenset({"anthropic", "openai", "httpx", "sqlalchemy", "fastapi", "typer"})
#: Top-level packages of ``ela`` allowed to import INFRA_LIBRARIES.
INFRA_PACKAGES = frozenset({"providers", "infrastructure", "api"})
#: Core packages that must stay independent from providers and infrastructure.
CORE_PACKAGES = ("executive", "tasks", "permissions", "audit")
CORE_FORBIDDEN = tuple(f"{ROOT_PACKAGE}.{name}" for name in ("providers", "infrastructure"))


@dataclass(frozen=True)
class Violation:
    rule: str
    module: str
    imported: str
    line: int

    def __str__(self) -> str:
        return f"[{self.rule}] {self.module}:{self.line} imports {self.imported}"


def top_level_modules(pkg_root: Path) -> set[str]:
    """Dotted names of the packages and modules directly under ``pkg_root``."""
    names: set[str] = set()
    for path in pkg_root.iterdir():
        if path.is_dir() and (path / "__init__.py").is_file():
            names.add(f"{ROOT_PACKAGE}.{path.name}")
        elif path.suffix == ".py" and path.name != "__init__.py":
            names.add(f"{ROOT_PACKAGE}.{path.stem}")
    return names


def module_name(path: Path, pkg_root: Path) -> str:
    parts = list(path.relative_to(pkg_root).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join([ROOT_PACKAGE, *parts])


def _source_files(directory: Path) -> Iterator[Path]:
    yield from sorted(p for p in directory.rglob("*.py") if "__pycache__" not in p.parts)


def imported_modules(path: Path, pkg_root: Path) -> list[tuple[str, int]]:
    """Absolute dotted names imported by ``path`` (relative imports resolved), with lines.

    ``from pkg import name`` yields ``pkg.name``: whether ``name`` is a submodule or an
    attribute, the dependency on ``pkg`` is captured by prefix matching in the rules.
    """
    current = module_name(path, pkg_root)
    package = current if path.name == "__init__.py" else current.rpartition(".")[0]
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_base(node, package)
            if any(alias.name == "*" for alias in node.names):
                found.append((base, node.lineno))
            else:
                found.extend((f"{base}.{alias.name}", node.lineno) for alias in node.names)
    return found


def _resolve_base(node: ast.ImportFrom, package: str) -> str:
    if node.level == 0:
        assert node.module is not None
        return node.module
    parts = package.split(".")
    ancestor = ".".join(parts[: len(parts) - (node.level - 1)])
    return f"{ancestor}.{node.module}" if node.module else ancestor


def _is_within(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(prefix + ".")


def _top_level(module: str) -> str:
    return module.partition(".")[0]


def _violations(
    rule: str,
    files: Iterator[Path],
    pkg_root: Path,
    is_forbidden: Callable[[str], bool],
) -> list[Violation]:
    found: list[Violation] = []
    for path in files:
        name = module_name(path, pkg_root)
        found.extend(
            Violation(rule, name, imported, line)
            for imported, line in imported_modules(path, pkg_root)
            if is_forbidden(imported)
        )
    return found


def check_domain(pkg_root: Path) -> list[Violation]:
    """Rule 1: ``ela.domain`` imports only the standard library and pydantic."""
    allowed = STDLIB | DOMAIN_ALLOWED_EXTERNAL
    return _violations(
        "domain-imports-only-stdlib-and-pydantic",
        iter([pkg_root / "domain.py"]),
        pkg_root,
        lambda imported: _top_level(imported) not in allowed,
    )


def check_ports(pkg_root: Path) -> list[Violation]:
    """Rule 2: ``ela.ports`` imports only the standard library and ``ela.domain``."""
    return _violations(
        "ports-import-only-stdlib-and-domain",
        iter([pkg_root / "ports.py"]),
        pkg_root,
        lambda imported: (
            _top_level(imported) not in STDLIB and not _is_within(imported, PORTS_ALLOWED_INTERNAL)
        ),
    )


def check_infra_libraries(pkg_root: Path) -> list[Violation]:
    """Rule 3: only providers/, infrastructure/ and api/ import infrastructure libraries."""
    files = (
        path
        for path in _source_files(pkg_root)
        if path.relative_to(pkg_root).parts[0] not in INFRA_PACKAGES
    )
    return _violations(
        "core-does-not-import-infra-libraries",
        files,
        pkg_root,
        lambda imported: _top_level(imported) in INFRA_LIBRARIES,
    )


def check_core_isolation(pkg_root: Path) -> list[Violation]:
    """Rule 4: executive/, tasks/, permissions/, audit/ import neither providers nor infra."""
    files = (path for name in CORE_PACKAGES for path in _source_files(pkg_root / name))
    return _violations(
        "core-packages-do-not-import-providers-or-infrastructure",
        files,
        pkg_root,
        lambda imported: any(_is_within(imported, prefix) for prefix in CORE_FORBIDDEN),
    )


Rule = Callable[[Path], list[Violation]]

RULES: dict[str, Rule] = {
    "domain": check_domain,
    "ports": check_ports,
    "infra-libraries": check_infra_libraries,
    "core-isolation": check_core_isolation,
}
