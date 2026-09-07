"""Architecture rules of ELA as pure functions over a source tree (CLAUDE.md, spec §52).

Every rule takes the root directory of the ``ela`` package (``src/ela``) and returns the
violations it finds; an empty list means the rule holds. The rules read source files with
``ast`` and never import the modules they check, so they run unchanged on a temporary copy
of the tree (see ``test_rules_detect_violations.py``).
"""

from __future__ import annotations

import ast
import re
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
#: Rule 10 (ADR 0008): only the ``tasks`` package may import the state machine.
STATE_MACHINE_MODULE = f"{ROOT_PACKAGE}.tasks.state_machine"
TASKS_DIR = "tasks"
#: Rule 11 (ADR 0009): the ``TaskEvent`` types that move a step, written only by ``ela.tasks``.
STEP_EVENT_PREFIX = "STEP_"
#: The mapper rehydrates a Task in the state the database holds: exempt from rule 5 (ADR 0006).
PERSISTENCE_MAPPERS = Path("infrastructure") / "persistence" / "mappers.py"
STATE_EXEMPT = frozenset({STATE_MACHINE, PERSISTENCE_MAPPERS})
#: Rule 8 (ADR 0006): the ORM and the domain never meet in one module.
ORM_PACKAGE = "sqlalchemy.orm"
DOMAIN_MODULE = f"{ROOT_PACKAGE}.domain"
#: Rule 9 (ADR 0007): the audit adapter has no way to update or delete, not even raw SQL.
AUDIT_ADAPTER = Path("infrastructure") / "persistence" / "audit_log.py"
MUTATING_NAMES = frozenset({"update", "delete", "merge"})
MUTATING_SQL = re.compile(r"\b(update|delete|replace|drop)\b", re.IGNORECASE)
#: Rule 20 (ADR 0016 §3, ADR 0017 §7): the availability of a node is *derived* from its last
#: heartbeat, never read from the row. Outside ``ela.devices`` — which derives it — and the mapper
#: — which stores and rehydrates it — nobody touches the field at all.
DEVICES_DIR = "devices"
AVAILABILITY_FIELD = "availability"
#: Rule 21 (ADR 0017 §9): whoever decides goes through ``DeviceRegistry``, not the raw port. Three
#: exemptions, one per module that names it today: the ports that declare it, the package that
#: holds it, the adapter that implements it. The composition root of M8.1 will probably need a
#: fourth, and it is deliberately not here yet: an exemption with no code behind it is a door
#: opened before anyone knocks (review of M6.2).
DEVICE_REGISTRY_PORT = f"{ROOT_PACKAGE}.ports.DeviceRegistryPort"
DEVICE_PORT_ALLOWED = (
    f"{ROOT_PACKAGE}.ports",
    f"{ROOT_PACKAGE}.{DEVICES_DIR}",
    f"{ROOT_PACKAGE}.infrastructure.persistence.device_registry",
)
#: Rule 22 (ADR 0017 §6): the orchestrator advises and never commands. A package that cannot
#: reach the Task Engine cannot fail a task because it found no node.
DEVICES_PACKAGE = f"{ROOT_PACKAGE}.{DEVICES_DIR}"
DEVICES_FORBIDDEN = (f"{ROOT_PACKAGE}.{TASKS_DIR}",)
#: Rule 23 (ADR 0018 §5): the arguments of a step are the user's content (§57). They live in the
#: plan and in the private database; the audit log records the *targets* of a call, never what was
#: passed. With ADR 0018 the arguments became a persisted field read in three places, so the
#: convention of the executor's docstring becomes a rule.
AUDIT_EVENT = "AuditEvent"
ARGUMENTS_NAME = "arguments"

#: The in-memory fakes: used by tests only, never by production code (ADR 0005).
TESTING_PACKAGE = f"{ROOT_PACKAGE}.testing"
TESTING_DIR = "testing"
#: What the fakes may import besides the standard library.
TESTING_ALLOWED_INTERNAL = (f"{ROOT_PACKAGE}.domain", f"{ROOT_PACKAGE}.ports", TESTING_PACKAGE)
#: The only state a Task may be *born* in outside the state machine.
INITIAL_STATE = ("TaskState", "CREATED")
#: Rule 13 (ADR 0010): the permissions package imports the standard library, the domain, the
#: ports, itself and the JSON Schema validator — never a tool, a provider, the engine, the audit.
PERMISSIONS_DIR = "permissions"
PERMISSIONS_PACKAGE = f"{ROOT_PACKAGE}.permissions"
PERMISSIONS_ALLOWED_INTERNAL = (DOMAIN_MODULE, f"{ROOT_PACKAGE}.ports", PERMISSIONS_PACKAGE)
PERMISSIONS_ALLOWED_EXTERNAL = frozenset({"jsonschema"})
#: Rule 12 (ADR 0011): outside the Guardian nobody builds an allowing decision. The fakes may:
#: rule 6 keeps them out of production, and a table-driven fake must be able to answer ALLOWED.
DECISION_MODEL = "PermissionDecision"
DENIED_OUTCOME = ("PermissionOutcome", "DENIED")
DECISION_BUILDERS_EXEMPT = frozenset({PERMISSIONS_DIR, TESTING_DIR})
#: Rule 14 (ADR 0011): outside ``ela.permissions`` nobody calls ``decide`` — only ``authorize``,
#: which writes the audit event. No exemption: the fake *defines* ``decide``, it never calls it.
DECIDE_METHOD = "decide"
#: Rule 15 (ADR 0012): outside ``ela.permissions`` nobody builds an ``Authorization`` or widens one
#: by ``model_copy`` — every production grant is born from ``authorization_from_approval``. The
#: fakes may (rule 6 keeps them out of production); the persistence mapper reads grants back from
#: rows, it does not coin them, and is the one exact-path exemption.
AUTHORIZATION_MODEL = "Authorization"
AUTHORIZATION_WIDENING_FIELDS = frozenset(
    {"approval_id", "task_id", "step_id", "scope", "expires_at", "max_uses", "capability_id"}
)
AUTHORIZATION_BUILDERS_EXEMPT = frozenset({PERMISSIONS_DIR, TESTING_DIR})
AUTHORIZATION_READER = PERSISTENCE_MAPPERS
#: Rule 16 (ADR 0013): only the executor calls ``Tool.execute``. The exemption is one exact path;
#: a receiver named like a SQLAlchemy session, connection or cursor is SQL's ``execute``, not a
#: tool's — an exemption by name, closed and tested.
EXECUTOR_MODULE = Path("executive") / "executor.py"
EXECUTE_METHOD = "execute"
#: Rule 16 (ADR 0019 §3): ``self._executor.execute(...)`` is the runner driving the executor, not
#: a second place where a tool runs. One receiver name **in one module**: the exemption belongs to
#: the runner, not to the name, so an attribute called ``_executor`` anywhere else does not
#: inherit it (review of M6.3). Everything else called ``.execute(...)`` outside the executor is
#: still reported.
RUNNER_MODULE = Path("executive") / "runner.py"
EXECUTOR_RECEIVERS = frozenset({"_executor"})
SQL_EXECUTORS = frozenset({"session", "connection", "cursor"})
# Rule 17 (ADR 0014 §9): only the executor completes a step, and only after verification.
COMPLETE_STEP_METHOD = "complete_step"
RESPOND_METHOD = "respond"
# Rule 18 (ADR 0014 §10): the module of the verifiers, and the shared path classification the
# tool and the verifier both use, have no path that writes.
VERIFIERS_MODULE = Path("tools") / "verifiers.py"
PATHS_MODULE = Path("tools") / "paths.py"
READ_ONLY_MODULES = (VERIFIERS_MODULE, PATHS_MODULE)
OPENERS = frozenset({"open", "fdopen"})
WRITING_OPEN_MODES = frozenset("wax+")
WRITING_OPEN_FLAGS = frozenset({"O_WRONLY", "O_RDWR", "O_CREAT", "O_TRUNC", "O_APPEND", "O_EXCL"})
WRITING_CALLS = frozenset(
    {
        "write",
        "writelines",
        "unlink",
        "remove",
        "removedirs",
        "rename",
        "replace",
        "rmdir",
        "mkdir",
        "makedirs",
        "write_text",
        "write_bytes",
        "touch",
        "chmod",
        "chown",
        "symlink",
        "link",
        "truncate",
        "ftruncate",
        "utime",
        "rmtree",
        "copy",
        "copyfile",
        "copytree",
        "move",
    }
)
SHUTIL = "shutil"


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
    return _copies_field(call, "state")


def _copies_field(call: ast.Call, field: str) -> bool:
    """``x.model_copy(update={... field: ...})`` with a literal dict."""
    if not (isinstance(call.func, ast.Attribute) and call.func.attr == "model_copy"):
        return False
    for keyword in call.keywords:
        if keyword.arg == "update" and isinstance(keyword.value, ast.Dict):
            return any(
                isinstance(key, ast.Constant) and key.value == field for key in keyword.value.keys
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


def check_audit_adapter_append_only(pkg_root: Path) -> list[Violation]:
    """Rule 9: ``audit_log.py`` never names ``update``, ``delete`` or ``merge`` (ADR 0007).

    Neither as an import, a name, an attribute (``session.delete``), nor as a word of a raw SQL
    string passed to ``text(...)``. The other adapters may update; the audit adapter has no such
    path at all, and the database and the ORM refuse one anyway.
    """
    rule = "audit-adapter-is-append-only"
    path = pkg_root / AUDIT_ADAPTER
    if not path.is_file():
        return []
    name = module_name(path, pkg_root)
    found: list[Violation] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            found.extend(
                Violation(rule, name, alias.name, node.lineno)
                for alias in node.names
                if alias.name in MUTATING_NAMES
            )
        elif isinstance(node, ast.Name) and node.id in MUTATING_NAMES:
            found.append(Violation(rule, name, node.id, node.lineno))
        elif isinstance(node, ast.Attribute) and node.attr in MUTATING_NAMES:
            found.append(Violation(rule, name, node.attr, node.lineno))
        elif isinstance(node, ast.Call) and _is_named(node.func, "text"):
            found.extend(
                Violation(rule, name, f"text: {match.group(1).upper()}", node.lineno)
                for argument in node.args
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
                for match in [MUTATING_SQL.search(argument.value)]
                if match is not None
            )
    return found


def _is_named(callee: ast.expr, function: str) -> bool:
    return (isinstance(callee, ast.Name) and callee.id == function) or (
        isinstance(callee, ast.Attribute) and callee.attr == function
    )


def check_state_machine_callers(pkg_root: Path) -> list[Violation]:
    """Rule 10: outside ``ela.tasks`` nobody imports ``ela.tasks.state_machine`` (ADR 0008).

    The Task Engine is the only caller of ``transition``: a module that moved a task itself and
    saved it would change state without a trail event and without an audit event. The rest of
    ``ela.tasks`` (errors) stays importable from anywhere.
    """
    files = (
        path for path in _source_files(pkg_root) if path.relative_to(pkg_root).parts[0] != TASKS_DIR
    )
    return _violations(
        "state-machine-called-only-by-the-task-engine",
        files,
        pkg_root,
        lambda imported: _is_within(imported, STATE_MACHINE_MODULE),
    )


def check_step_event_writers(pkg_root: Path) -> list[Violation]:
    """Rule 11: outside ``ela.tasks`` nobody builds a ``TaskEvent`` of a ``STEP_*`` type (ADR 0009).

    The state of a step is folded from those events: a module that wrote one itself would move
    a step without the graph's checks and without an audit event. Reported: a ``TaskEvent(...)``
    call whose ``event_type`` is an attribute or a string starting with ``STEP_``. A heuristic on
    names, like rule 5: it catches the obvious bypass, the review catches the rest.
    """
    rule = "step-events-written-only-by-the-task-engine"
    found: list[Violation] = []
    for path in _source_files(pkg_root):
        if path.relative_to(pkg_root).parts[0] == TASKS_DIR:
            continue
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_named(node.func, "TaskEvent"):
                found.extend(
                    Violation(rule, name, "TaskEvent(event_type=STEP_*)", node.lineno)
                    for keyword in node.keywords
                    if keyword.arg == "event_type" and _is_step_event(keyword.value)
                )
    return found


def _is_step_event(value: ast.expr) -> bool:
    if isinstance(value, ast.Attribute):
        return value.attr.startswith(STEP_EVENT_PREFIX)
    return (
        isinstance(value, ast.Constant)
        and isinstance(value.value, str)
        and value.value.startswith(STEP_EVENT_PREFIX)
    )


def check_permissions_imports(pkg_root: Path) -> list[Violation]:
    """Rule 13: ``ela.permissions`` imports stdlib, domain, ports and ``jsonschema`` (ADR 0010).

    The Guardian must be independent enough to block ELA (§47): the package that hosts it and
    its catalogue reaches no tool, provider, engine, audit or infrastructure, and no pydantic
    directly — the domain is its only way to a model. ``jsonschema`` is the one library it needs.
    """
    files = (path for path in _source_files(pkg_root / PERMISSIONS_DIR))
    return _violations(
        "permissions-import-only-stdlib-domain-ports-and-jsonschema",
        files,
        pkg_root,
        lambda imported: (
            _top_level(imported) not in STDLIB | PERMISSIONS_ALLOWED_EXTERNAL
            and not any(_is_within(imported, prefix) for prefix in PERMISSIONS_ALLOWED_INTERNAL)
        ),
    )


def check_decision_builders(pkg_root: Path) -> list[Violation]:
    """Rule 12: outside ``ela.permissions`` nobody builds a ``PermissionDecision`` that could allow.

    Reported: ``PermissionDecision(...)`` whose ``outcome`` is not the literal
    ``PermissionOutcome.DENIED`` / ``"DENIED"`` — a variable, another member, or no ``outcome``
    keyword at all (``**kwargs``) is a doubt — and ``x.model_copy(update={"outcome": ...})``. The
    Guardian is the only producer of ``ALLOWED`` (ADR 0011); ``ela.testing`` is exempt because the
    table-driven fake must answer ``ALLOWED`` in tests and rule 6 keeps it out of production.
    A heuristic on names, like rules 5 and 11.
    """
    rule = "allowing-decisions-built-only-by-the-guardian"
    found: list[Violation] = []
    for path in _source_files(pkg_root):
        if path.relative_to(pkg_root).parts[0] in DECISION_BUILDERS_EXEMPT:
            continue
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _is_named(node.func, DECISION_MODEL) and not _denies(node):
                found.append(Violation(rule, name, "PermissionDecision(outcome=...)", node.lineno))
            elif _copies_field(node, "outcome"):
                found.append(
                    Violation(rule, name, 'model_copy(update={"outcome": ...})', node.lineno)
                )
    return found


def _denies(call: ast.Call) -> bool:
    """The call names ``outcome`` and it is the literal DENIED; anything else is a doubt."""
    enum_name, member = DENIED_OUTCOME
    for keyword in call.keywords:
        if keyword.arg == "outcome":
            value = keyword.value
            if isinstance(value, ast.Attribute):
                return (
                    value.attr == member
                    and isinstance(value.value, ast.Name)
                    and value.value.id == enum_name
                )
            return isinstance(value, ast.Constant) and value.value == member
    return False


def check_decide_callers(pkg_root: Path) -> list[Violation]:
    """Rule 14: outside ``ela.permissions`` nobody calls ``<something>.decide(...)`` (ADR 0011).

    ``decide`` is the pure port; ``authorize`` decides *and* writes ``PERMISSION_DECIDED``. A
    module that called ``decide`` directly would obtain a decision the audit log never saw.
    Reported: any call whose callee is an attribute named ``decide``. No exemption: the fake
    defines ``decide`` and never calls it; the Guardian's own ``self.decide`` lives inside the
    package.
    """
    rule = "decide-called-only-inside-permissions"
    found: list[Violation] = []
    for path in _source_files(pkg_root):
        if path.relative_to(pkg_root).parts[0] == PERMISSIONS_DIR:
            continue
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found.extend(
            Violation(rule, name, f".{DECIDE_METHOD}(", node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == DECIDE_METHOD
        )
    return found


def check_authorization_builders(pkg_root: Path) -> list[Violation]:
    """Rule 15: outside ``ela.permissions`` nobody builds or widens an ``Authorization`` (ADR 0012).

    Reported: any call ``Authorization(...)`` — by name or as an attribute — and any
    ``x.model_copy(update={...})`` whose literal dict names a field that could widen a grant
    (``max_uses``, ``expires_at``, ``scope``, the bindings). ``model_copy`` does not run the
    validators, so a copy is the one way to hold a grant the type would refuse. ``ela.testing``
    is exempt (rule 6 keeps it out of production); ``persistence/mappers.py`` reads rows back
    and is exempt by exact path. A heuristic on names, like rules 5, 11 and 12.
    """
    rule = "authorizations-built-only-by-permissions"
    found: list[Violation] = []
    for path in _source_files(pkg_root):
        relative = path.relative_to(pkg_root)
        if relative.parts[0] in AUTHORIZATION_BUILDERS_EXEMPT or relative == AUTHORIZATION_READER:
            continue
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _is_named(node.func, AUTHORIZATION_MODEL):
                found.append(Violation(rule, name, f"{AUTHORIZATION_MODEL}(...)", node.lineno))
            else:
                widened = [
                    f for f in sorted(AUTHORIZATION_WIDENING_FIELDS) if _copies_field(node, f)
                ]
                if widened:
                    found.append(
                        Violation(
                            rule, name, f"model_copy(update={{{widened[0]!r}: ...}})", node.lineno
                        )
                    )
    return found


def check_tool_execute_callers(pkg_root: Path) -> list[Violation]:
    """Rule 16: outside ``executive/executor.py`` nobody calls ``<x>.execute(...)`` (ADR 0013).

    The executor is the only place where a tool runs, and it runs it only with an ``ALLOWED``
    decision in hand; a second caller would be a second place to get that wrong. Reported: any
    call whose callee is an attribute named ``execute``, unless the receiver is a bare name in
    :data:`SQL_EXECUTORS` (``session.execute(...)`` of SQLAlchemy in the persistence adapters) or
    an attribute in :data:`EXECUTOR_RECEIVERS` **inside** :data:`RUNNER_MODULE`
    (``self._executor.execute(...)``: the runner driving the executor, ADR 0019 §3 — one step
    still runs in one place, and this is that place being *called*, not a second tool call). The
    second exemption is bound to the module and not to the name: a field called ``_executor`` in
    any other module is reported like everything else (review of M6.3).
    A heuristic on names, like rules 5, 11, 12 and 15.
    """
    rule = "tool-execute-called-only-by-the-executor"
    found: list[Violation] = []
    for path in _source_files(pkg_root):
        relative = path.relative_to(pkg_root)
        if relative == EXECUTOR_MODULE:
            continue
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found.extend(
            Violation(rule, name, f".{EXECUTE_METHOD}(", node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == EXECUTE_METHOD
            and not _is_sql_executor(node.func.value)
            and not (relative == RUNNER_MODULE and _is_the_executor(node.func.value))
        )
    return found


def _is_sql_executor(receiver: ast.expr) -> bool:
    return isinstance(receiver, ast.Name) and receiver.id in SQL_EXECUTORS


def _is_the_executor(receiver: ast.expr) -> bool:
    return isinstance(receiver, ast.Attribute) and receiver.attr in EXECUTOR_RECEIVERS


def check_step_completers(pkg_root: Path) -> list[Violation]:
    """Rule 17: outside ``executive/executor.py`` nobody calls ``<x>.complete_step(...)`` (ADR
    0014 §9).

    A step is COMPLETED only after its result was verified (§63), and the verification happens
    in one place, the executor; a second caller of ``complete_step`` would be a second place to
    complete a step on the tool's word alone. The definition in ``tasks/engine.py`` is not a
    call and is not reported. A heuristic on names, like rule 16.
    """
    rule = "step-completed-only-by-the-executor"
    found: list[Violation] = []
    for path in _source_files(pkg_root):
        if path.relative_to(pkg_root) == EXECUTOR_MODULE:
            continue
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found.extend(
            Violation(rule, name, f".{COMPLETE_STEP_METHOD}(", node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == COMPLETE_STEP_METHOD
        )
    return found


def check_approval_responders(pkg_root: Path) -> list[Violation]:
    """Rule 19: no module of ``src/ela`` calls ``<x>.respond(...)`` (ADR 0015 §9).

    The Core never answers its own requests for approval: a "yes" is the user's (§30, §62), and
    it reaches the store through the API of M8.1, which will be the one exemption, by path,
    when it exists. The definitions in ``ports.py``, in the SQL store and in the fake are not
    calls and are not reported. A heuristic on names, like rules 16 and 17.
    """
    rule = "approval-answered-only-by-the-user"
    found: list[Violation] = []
    for path in _source_files(pkg_root):
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found.extend(
            Violation(rule, name, f".{RESPOND_METHOD}(", node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == RESPOND_METHOD
        )
    return found


def check_verifier_read_only(pkg_root: Path) -> list[Violation]:
    """Rule 18: ``tools/verifiers.py`` and ``tools/paths.py`` have no path that writes (ADR 0014
    §10, decision I; review of M5.2 for the shared classification).

    A verifier is read-only by construction: it looks at the world and changes nothing, and so
    is the path classification it shares with the tool. Reported in those modules:
    ``open``/``fdopen`` in a writing mode (``w``, ``a``, ``x``, ``+``) or with a mode that is not
    a literal; ``os.open`` with a writing flag (``O_WRONLY``, ``O_RDWR``, ``O_CREAT``, ``O_TRUNC``,
    ``O_APPEND``, ``O_EXCL``); any call named after a write — ``write``, ``unlink``, ``rename``,
    ``mkdir``, ``chmod``, ``write_text``… (:data:`WRITING_CALLS`) — and any call through
    ``shutil``. Closed-world on names, like rules 5, 11, 12, 15 and 16.
    """
    rule = "verifier-read-only"
    found: list[Violation] = []
    for relative in READ_ONLY_MODULES:
        path = pkg_root / relative
        if not path.is_file():
            continue
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found.extend(
            Violation(rule, name, f"{callee}(", node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            for callee in [_callee(node.func)]
            if _writes(node, callee)
        )
    return found


def _callee(function: ast.expr) -> str:
    if isinstance(function, ast.Name):
        return function.id
    if isinstance(function, ast.Attribute):
        return f".{function.attr}"
    return ""


def _writes(call: ast.Call, callee: str) -> bool:
    """Whether ``call`` may write, by the name of what it calls and its mode or flags."""
    bare = callee.lstrip(".")
    if bare in OPENERS:
        if callee == ".open":  # os.open(path, flags): the flags say
            return _has_writing_flag(_argument(call, 1, "flags"))
        return _is_writing_mode(_argument(call, 1, "mode"))
    if bare in WRITING_CALLS:
        return True
    receiver = call.func.value if isinstance(call.func, ast.Attribute) else None
    return isinstance(receiver, ast.Name) and receiver.id == SHUTIL


def _argument(call: ast.Call, position: int, keyword: str) -> ast.expr | None:
    for item in call.keywords:
        if item.arg == keyword:
            return item.value
    return call.args[position] if len(call.args) > position else None


def _is_writing_mode(mode: ast.expr | None) -> bool:
    if mode is None:
        return False  # the default mode of ``open`` reads
    if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
        return any(letter in WRITING_OPEN_MODES for letter in mode.value)
    return True  # a mode that is not a literal is a doubt


def _has_writing_flag(flags: ast.expr | None) -> bool:
    if flags is None:
        return True  # ``os.open`` without flags is not a call this module may make
    for node in ast.walk(flags):
        if isinstance(node, ast.Attribute) and node.attr in WRITING_OPEN_FLAGS:
            return True
        if isinstance(node, ast.Name) and node.id in WRITING_OPEN_FLAGS:
            return True
    return False


def check_audit_arguments(pkg_root: Path) -> list[Violation]:
    """Rule 23: no ``AuditEvent`` is built with the arguments of a call anywhere inside it.

    ADR 0018 §5. What a tool was called *with* can be the user's content — the body of a note, the
    text of a message — and §57 keeps that in the private database: the plan holds it, the
    ``ExecutionResult`` holds it, the audit log holds the *targets* the scope constrains and the
    decision that allowed them. Until M6.3 the arguments were a parameter and the rule was a
    sentence in a docstring; now they are a field of ``TaskStep`` that three modules read, and a
    sentence is not a guarantee.
    Reported, anywhere in the subtree of an ``AuditEvent(...)`` call: the name ``arguments`` as a
    variable, as an attribute, as a keyword or as a string literal (a payload key). Closed-world
    on names, like rules 5, 12, 15, 16 and 20: in a repository where the word has one meaning, a
    false positive costs less than a false negative.
    """
    rule = "arguments-never-enter-the-audit"
    found: list[Violation] = []
    for path in _source_files(pkg_root):
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for call in ast.walk(tree):
            if not (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == AUDIT_EVENT
            ):
                continue
            for node in ast.walk(call):
                mention = _mentions_arguments(node)
                if mention is not None:
                    found.append(Violation(rule, name, mention, node.lineno))
    return found


def _mentions_arguments(node: ast.AST) -> str | None:
    """How ``node`` names the arguments of a call, or ``None`` if it does not."""
    if isinstance(node, ast.Name) and node.id == ARGUMENTS_NAME:
        return ARGUMENTS_NAME
    if isinstance(node, ast.Attribute) and node.attr == ARGUMENTS_NAME:
        return f".{ARGUMENTS_NAME}"
    if isinstance(node, ast.keyword) and node.arg == ARGUMENTS_NAME:
        return f"{ARGUMENTS_NAME}="
    if isinstance(node, ast.Constant) and node.value == ARGUMENTS_NAME:
        return f'"{ARGUMENTS_NAME}"'
    return None


def check_device_availability_readers(pkg_root: Path) -> list[Violation]:
    """Rule 20: outside ``ela.devices`` and the mapper nobody touches ``availability``.

    ADR 0016 §3 and ADR 0017 §9. A stored ``availability`` says what was true when someone wrote
    it and keeps saying it after the node went quiet; the answer a decision needs comes from
    ``DeviceRegistry``, which derives it from the last heartbeat. The orchestrator (§17) is the
    first reader with a motive to trust the column — it is indexed and one ``SELECT`` away — so
    the convention becomes a rule here.
    Reported: any ``.availability`` attribute and any ``availability=`` keyword. Closed-world on
    names, like rules 5, 11, 12, 15 and 16: in a repository where the word has one meaning, a
    false positive costs less than a false negative.
    """
    rule = "availability-derived-not-read"
    found: list[Violation] = []
    for path in _source_files(pkg_root):
        relative = path.relative_to(pkg_root)
        if relative.parts[0] == DEVICES_DIR or relative == PERSISTENCE_MAPPERS:
            continue
        name = module_name(path, pkg_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == AVAILABILITY_FIELD:
                found.append(Violation(rule, name, f".{AVAILABILITY_FIELD}", node.lineno))
            elif isinstance(node, ast.keyword) and node.arg == AVAILABILITY_FIELD:
                found.append(Violation(rule, name, f"{AVAILABILITY_FIELD}=", node.lineno))
    return found


def check_device_port_readers(pkg_root: Path) -> list[Violation]:
    """Rule 21: outside three modules nobody names ``DeviceRegistryPort`` (ADR 0017 §9).

    Rule 20 forbids reading the stale field (ADR 0016 §3); this one removes the temptation, by
    keeping the raw port out of the hands of whoever decides. ``ela.ports`` declares it,
    ``ela.devices`` holds it and the SQL adapter implements it: everybody else asks
    ``DeviceRegistry``, and gets an availability that is already judged.
    """
    files = (
        path
        for path in _source_files(pkg_root)
        if not any(
            _is_within(module_name(path, pkg_root), prefix) for prefix in DEVICE_PORT_ALLOWED
        )
    )
    return _violations(
        "device-registry-port-reached-only-through-the-registry",
        files,
        pkg_root,
        lambda imported: _is_within(imported, DEVICE_REGISTRY_PORT),
    )


def check_devices_isolation(pkg_root: Path) -> list[Violation]:
    """Rule 22: ``ela.devices`` does not import ``ela.tasks`` (ADR 0017 §6).

    "The orchestrator only advises" is the property that makes a missing node an *attesa* and not
    a failure (§17, §33). Kept structurally rather than promised in a docstring: a package with no
    path to the Task Engine cannot move a task, whatever a future ``place`` decides to do.
    """
    files = _source_files(pkg_root / DEVICES_DIR)
    return _violations(
        "devices-advise-and-never-move-a-task",
        files,
        pkg_root,
        lambda imported: any(_is_within(imported, prefix) for prefix in DEVICES_FORBIDDEN),
    )


RULES: dict[str, Rule] = {
    "domain": check_domain,
    "ports": check_ports,
    "infra-libraries": check_infra_libraries,
    "core-isolation": check_core_isolation,
    "state-changes": check_state_changes,
    "testing-isolation": check_testing_isolation,
    "testing-imports": check_testing_imports,
    "orm-separation": check_orm_separation,
    "audit-append-only": check_audit_adapter_append_only,
    "state-machine-callers": check_state_machine_callers,
    "step-event-writers": check_step_event_writers,
    "permissions-imports": check_permissions_imports,
    "decision-builders": check_decision_builders,
    "decide-callers": check_decide_callers,
    "authorization-builders": check_authorization_builders,
    "tool-execute-callers": check_tool_execute_callers,
    "step-completers": check_step_completers,
    "verifier-read-only": check_verifier_read_only,
    "approval-responders": check_approval_responders,
    "device-availability-readers": check_device_availability_readers,
    "device-port-readers": check_device_port_readers,
    "devices-isolation": check_devices_isolation,
    "audit-arguments": check_audit_arguments,
}
