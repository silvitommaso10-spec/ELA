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
INFRA_LIBRARIES = frozenset(
    {"anthropic", "openai", "httpx", "sqlalchemy", "alembic", "aiosqlite", "fastapi", "typer"}
)
#: Top-level packages of ``ela`` allowed to import INFRA_LIBRARIES.
INFRA_PACKAGES = frozenset({"providers", "infrastructure", "api"})
#: Core packages that must stay independent from providers and infrastructure.
CORE_PACKAGES = ("executive", "tasks", "permissions", "audit")
CORE_FORBIDDEN = tuple(f"{ROOT_PACKAGE}.{name}" for name in ("providers", "infrastructure"))
#: The only module allowed to change the state of a Task (ADR 0004).
STATE_MACHINE = Path("tasks") / "state_machine.py"
#: The mapper rehydrates a Task in the state the database holds: exempt from rule 5 (ADR 0006).
PERSISTENCE_MAPPERS = Path("infrastructure") / "persistence" / "mappers.py"
STATE_EXEMPT = frozenset({STATE_MACHINE, PERSISTENCE_MAPPERS})
#: Rule 8 (ADR 0006): the ORM and the domain never meet in one module.
ORM_PACKAGE = "sqlalchemy.orm"
DOMAIN_MODULE = f"{ROOT_PACKAGE}.domain"
#: The in-memory fakes: used by tests only, never by production code (ADR 0005).
TESTING_PACKAGE = f"{ROOT_PACKAGE}.testing"
TESTING_DIR = "testing"
#: What the fakes may import besides the standard library.
TESTING_ALLOWED_INTERNAL = (f"{ROOT_PACKAGE}.domain", f"{ROOT_PACKAGE}.ports", TESTING_PACKAGE)
#: The only state a Task may be *born* in outside the state machine.
INITIAL_STATE = ("TaskState", "CREATED")


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


def check_state_changes(pkg_root: Path) -> list[Violation]:
    """Rule 5: outside ``ela.tasks.state_machine`` nobody changes the state of a Task (ADR 0004).

    Reported: ``x.model_copy(update={... "state": ...})`` with a literal dict, and
    ``Task(..., state=<anything but TaskState.CREATED>)``. A heuristic on names, not on types:
    it catches the obvious bypass, the review catches the rest.
    """
    rule = "task-state-changes-only-in-the-state-machine"
    found: list[Violation] = []
    for path in _source_files(pkg_root):
        if path.relative_to(pkg_root) in STATE_EXEMPT:
            continue
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _copies_state(node):
                found.append(
                    Violation(rule, name, 'model_copy(update={"state": ...})', node.lineno)
                )
            elif _builds_task_in_a_state(node):
                found.append(Violation(rule, name, "Task(state=...)", node.lineno))
    return found


def _copies_state(call: ast.Call) -> bool:
    if not (isinstance(call.func, ast.Attribute) and call.func.attr == "model_copy"):
        return False
    for keyword in call.keywords:
        if keyword.arg == "update" and isinstance(keyword.value, ast.Dict):
            return any(
                isinstance(key, ast.Constant) and key.value == "state" for key in keyword.value.keys
            )
    return False


def _builds_task_in_a_state(call: ast.Call) -> bool:
    callee = call.func
    callee_name = callee.id if isinstance(callee, ast.Name) else getattr(callee, "attr", None)
    if callee_name != "Task":
        return False
    for keyword in call.keywords:
        if keyword.arg == "state":
            return not _is_initial_state(keyword.value)
    return False


def _is_initial_state(value: ast.expr) -> bool:
    enum_name, member = INITIAL_STATE
    return (
        isinstance(value, ast.Attribute)
        and value.attr == member
        and isinstance(value.value, ast.Name)
        and value.value.id == enum_name
    )


def _is_testing(path: Path, pkg_root: Path) -> bool:
    return path.relative_to(pkg_root).parts[0] == TESTING_DIR


def check_testing_isolation(pkg_root: Path) -> list[Violation]:
    """Rule 6: no production module imports ``ela.testing`` (ADR 0005).

    A fake that reaches production code is a security bug, not a style issue: a ``FakeGuardian``
    that allows everything must never be one import away from the real pipeline.
    """
    files = (path for path in _source_files(pkg_root) if not _is_testing(path, pkg_root))
    return _violations(
        "production-does-not-import-testing",
        files,
        pkg_root,
        lambda imported: _is_within(imported, TESTING_PACKAGE),
    )


def check_testing_imports(pkg_root: Path) -> list[Violation]:
    """Rule 7: ``ela.testing`` imports only the standard library, the domain and the ports."""
    files = (path for path in _source_files(pkg_root) if _is_testing(path, pkg_root))
    return _violations(
        "testing-imports-only-stdlib-domain-and-ports",
        files,
        pkg_root,
        lambda imported: (
            _top_level(imported) not in STDLIB
            and not any(_is_within(imported, prefix) for prefix in TESTING_ALLOWED_INTERNAL)
        ),
    )


def check_orm_separation(pkg_root: Path) -> list[Violation]:
    """Rule 8: no module imports both ``sqlalchemy.orm`` and ``ela.domain`` (ADR 0006).

    An ORM row that could see the domain could subclass it, or a domain model could be mapped
    imperatively; keeping the two imports in different modules makes the explicit mapper the only
    bridge. Reported: the domain import, in a module that also imports ``sqlalchemy.orm``.
    """
    rule = "orm-and-domain-never-meet"
    found: list[Violation] = []
    for path in _source_files(pkg_root):
        imports = imported_modules(path, pkg_root)
        if not any(_is_within(name, ORM_PACKAGE) for name, _ in imports):
            continue
        name = module_name(path, pkg_root)
        found.extend(
            Violation(rule, name, imported, line)
            for imported, line in imports
            if _is_within(imported, DOMAIN_MODULE)
        )
    return found


Rule = Callable[[Path], list[Violation]]

RULES: dict[str, Rule] = {
    "domain": check_domain,
    "ports": check_ports,
    "infra-libraries": check_infra_libraries,
    "core-isolation": check_core_isolation,
    "state-changes": check_state_changes,
    "testing-isolation": check_testing_isolation,
    "testing-imports": check_testing_imports,
    "orm-separation": check_orm_separation,
}
