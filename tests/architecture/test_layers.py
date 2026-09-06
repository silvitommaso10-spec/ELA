"""The architecture rules hold on the real source tree (CLAUDE.md "Architettura", spec §52)."""

import importlib

import pytest
from pydantic import BaseModel

from ela.domain import TaskEventType
from ela.infrastructure.persistence.orm import Base
from ela.tasks.graph import STEP_EVENTS
from tests.architecture.rules import (
    AUDIT_ADAPTER,
    AUTHORIZATION_BUILDERS_EXEMPT,
    AUTHORIZATION_MODEL,
    AUTHORIZATION_READER,
    COMPLETE_STEP_METHOD,
    CORE_PACKAGES,
    DECIDE_METHOD,
    DECISION_MODEL,
    EXECUTE_METHOD,
    EXECUTOR_MODULE,
    ORM_PACKAGE,
    PATHS_MODULE,
    PERMISSIONS_ALLOWED_EXTERNAL,
    PERMISSIONS_DIR,
    PERSISTENCE_MAPPERS,
    PORTS_ALLOWED_INTERNAL,
    RESPOND_METHOD,
    RULES,
    STATE_MACHINE_MODULE,
    STEP_EVENT_PREFIX,
    TESTING_DIR,
    VERIFIERS_MODULE,
    Rule,
    imported_modules,
)
from tests.architecture.violations import PACKAGE_ROOT


def test_required_modules_exist() -> None:
    """A rule about a file that does not exist would hold vacuously."""
    assert (PACKAGE_ROOT / "domain.py").is_file()
    assert (PACKAGE_ROOT / "ports.py").is_file()
    for name in CORE_PACKAGES:
        assert (PACKAGE_ROOT / name / "__init__.py").is_file(), f"missing package ela.{name}"
    assert (PACKAGE_ROOT / TESTING_DIR / "fakes.py").is_file()
    assert (PACKAGE_ROOT / PERSISTENCE_MAPPERS).is_file()
    assert (PACKAGE_ROOT / AUDIT_ADAPTER).is_file()
    assert (PACKAGE_ROOT / PERMISSIONS_DIR / "capabilities.py").is_file()
    assert (PACKAGE_ROOT / PERMISSIONS_DIR / "guardian.py").is_file()
    assert (PACKAGE_ROOT / EXECUTOR_MODULE).is_file()


def test_ports_really_import_the_domain() -> None:
    """Rule 2 held vacuously while ports.py was empty; now it has something to check."""
    imported = [name for name, _ in imported_modules(PACKAGE_ROOT / "ports.py", PACKAGE_ROOT)]
    assert any(name.startswith(PORTS_ALLOWED_INTERNAL) for name in imported)
    assert any(name.startswith("typing") for name in imported)


@pytest.mark.parametrize("rule", RULES.values(), ids=list(RULES))
def test_rule_holds(rule: Rule) -> None:
    violations = rule(PACKAGE_ROOT)
    assert not violations, "\n".join(str(v) for v in violations)


@pytest.mark.parametrize(
    "module",
    [
        "ela.domain",
        "ela.ports",
        "ela.testing.fakes",
        "ela.infrastructure.persistence",
        "ela.audit.chain",
        "ela.tasks.engine",
        "ela.tasks.graph",
        "ela.permissions.capabilities",
        "ela.permissions.guardian",
        "ela.executive.executor",
        "ela.tools.registry",
    ],
)
def test_module_is_importable(module: str) -> None:
    importlib.import_module(module)


def test_orm_module_really_imports_sqlalchemy_orm() -> None:
    """Rule 8 would hold vacuously if no module imported ``sqlalchemy.orm``."""
    orm = PACKAGE_ROOT / "infrastructure" / "persistence" / "orm.py"
    imported = [name for name, _ in imported_modules(orm, PACKAGE_ROOT)]
    assert any(name.startswith(ORM_PACKAGE) for name in imported)
    assert not any(name.startswith("ela.domain") for name in imported)


def test_mapped_rows_are_not_domain_models() -> None:
    """The static rule 8 at runtime: no ORM class is (or derives from) a pydantic model."""
    mapped = [mapper.class_ for mapper in Base.registry.mappers]
    assert len(mapped) == 8
    assert not any(issubclass(cls, BaseModel) for cls in mapped)


def test_the_audit_adapter_really_talks_to_the_database() -> None:
    """Rule 9 would hold vacuously on a module that issues no SQL at all."""
    imported = [name for name, _ in imported_modules(PACKAGE_ROOT / AUDIT_ADAPTER, PACKAGE_ROOT)]
    assert any(name.startswith("sqlalchemy") for name in imported)
    assert any(name.startswith("ela.audit.chain") for name in imported)


def test_the_engine_really_imports_the_state_machine() -> None:
    """Rule 10 would hold vacuously if nothing in ``ela.tasks`` used the state machine."""
    engine = PACKAGE_ROOT / "tasks" / "engine.py"
    imported = [name for name, _ in imported_modules(engine, PACKAGE_ROOT)]
    assert any(name.startswith(STATE_MACHINE_MODULE) for name in imported)


def test_rule_11_names_exactly_the_event_types_that_move_a_step() -> None:
    """Rule 11 matches on the ``STEP_`` prefix: it must be the fold's set, no more, no less."""
    assert {t for t in TaskEventType if t.name.startswith(STEP_EVENT_PREFIX)} == set(STEP_EVENTS)
    engine = PACKAGE_ROOT / "tasks" / "engine.py"
    imported = [name for name, _ in imported_modules(engine, PACKAGE_ROOT)]
    assert any(name.startswith("ela.tasks.graph") for name in imported)


def test_the_catalogue_really_imports_jsonschema_and_the_domain() -> None:
    """Rule 13 would hold vacuously on a permissions package that imported nothing."""
    catalogue = PACKAGE_ROOT / PERMISSIONS_DIR / "capabilities.py"
    imported = [name for name, _ in imported_modules(catalogue, PACKAGE_ROOT)]
    assert any(name.partition(".")[0] in PERMISSIONS_ALLOWED_EXTERNAL for name in imported)
    assert any(name.startswith("ela.domain") for name in imported)
    assert any(name.startswith("ela.ports") for name in imported)


def test_the_guardian_really_builds_decisions_and_calls_decide() -> None:
    """Rules 12 and 14 would hold vacuously if nothing built a decision or called ``decide``.

    The Guardian does both, inside the package the rules exempt: it constructs every
    ``PermissionDecision`` and ``authorize`` calls ``self.decide``.
    """
    source = (PACKAGE_ROOT / PERMISSIONS_DIR / "guardian.py").read_text(encoding="utf-8")
    assert f"{DECISION_MODEL}(" in source
    assert f"self.{DECIDE_METHOD}(" in source


def test_the_authorizations_module_really_builds_grants_and_the_mapper_really_reads_them() -> None:
    """Rule 15 would hold vacuously if nothing built an ``Authorization``; two places do, both
    exempt: the factory in ``permissions`` and the persistence mapper (read side)."""
    factory = (PACKAGE_ROOT / PERMISSIONS_DIR / "authorizations.py").read_text(encoding="utf-8")
    assert f"{AUTHORIZATION_MODEL}(" in factory
    mapper = (PACKAGE_ROOT / AUTHORIZATION_READER).read_text(encoding="utf-8")
    assert f"{AUTHORIZATION_MODEL}(" in mapper
    assert {PERMISSIONS_DIR, TESTING_DIR} == AUTHORIZATION_BUILDERS_EXEMPT


def test_the_executor_really_calls_a_tool_and_never_imports_the_tools() -> None:
    """Rule 16 would hold vacuously if the executor called no ``execute``; and the executor
    depends on ``ToolRegistryPort``, never on ``ela.tools`` (ADR 0013 §10): the day a tool imports
    a provider, contract 4 must not break through the executive package."""
    source = (PACKAGE_ROOT / EXECUTOR_MODULE).read_text(encoding="utf-8")
    assert f".{EXECUTE_METHOD}(" in source
    for path in sorted((PACKAGE_ROOT / "executive").rglob("*.py")):
        imported = [name for name, _ in imported_modules(path, PACKAGE_ROOT)]
        assert not any(name.startswith("ela.tools") for name in imported), path.name


def test_the_executor_really_completes_steps_and_the_verifiers_really_read() -> None:
    """Rule 17 would hold vacuously if the executor never called ``complete_step``; rule 18 if
    the verifiers' module did not exist or never opened a file (ADR 0014 §9, §10)."""
    executor = (PACKAGE_ROOT / EXECUTOR_MODULE).read_text(encoding="utf-8")
    assert f".{COMPLETE_STEP_METHOD}(" in executor
    verifiers = PACKAGE_ROOT / VERIFIERS_MODULE
    assert verifiers.is_file()
    source = verifiers.read_text(encoding="utf-8")
    assert "os.open(" in source
    assert "O_RDONLY" in source
    assert "O_NOFOLLOW" in source
    paths = PACKAGE_ROOT / PATHS_MODULE
    assert paths.is_file()
    classification = paths.read_text(encoding="utf-8")
    assert ".resolve()" in classification
    assert ".lstat()" in classification
    assert ".is_symlink()" in classification


def test_the_ports_and_the_store_really_define_respond_and_the_executor_never_calls_it() -> None:
    """Rule 19 would hold vacuously if nothing defined ``respond``; the executor, the one Core
    module that handles requests for approval, must not answer them (ADR 0015 §9)."""
    definers = ("ports.py", "infrastructure/persistence/approval_store.py", "testing/fakes.py")
    for relative in definers:
        source = (PACKAGE_ROOT / relative).read_text(encoding="utf-8")
        assert f"def {RESPOND_METHOD}(" in source, relative
    executor = (PACKAGE_ROOT / EXECUTOR_MODULE).read_text(encoding="utf-8")
    assert f".{RESPOND_METHOD}(" not in executor
    assert "_approvals.add(" in executor and "_results.add(" in executor
