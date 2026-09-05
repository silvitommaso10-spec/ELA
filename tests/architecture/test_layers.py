"""The architecture rules hold on the real source tree (CLAUDE.md "Architettura", spec §52)."""

import importlib

import pytest
from pydantic import BaseModel

from ela.domain import TaskEventType
from ela.infrastructure.persistence.orm import Base
from ela.tasks.graph import STEP_EVENTS
from tests.architecture.rules import (
    AUDIT_ADAPTER,
    CORE_PACKAGES,
    ORM_PACKAGE,
    PERMISSIONS_ALLOWED_EXTERNAL,
    PERMISSIONS_DIR,
    PERSISTENCE_MAPPERS,
    PORTS_ALLOWED_INTERNAL,
    RULES,
    STATE_MACHINE_MODULE,
    STEP_EVENT_PREFIX,
    TESTING_DIR,
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
    assert len(mapped) == 5
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
