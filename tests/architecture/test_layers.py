"""The architecture rules hold on the real source tree (CLAUDE.md "Architettura", spec §52)."""

import importlib

import pytest
from pydantic import BaseModel

from ela.infrastructure.persistence.orm import Base
from tests.architecture.rules import (
    AUDIT_ADAPTER,
    CORE_PACKAGES,
    ORM_PACKAGE,
    PERSISTENCE_MAPPERS,
    PORTS_ALLOWED_INTERNAL,
    RULES,
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
    assert len(mapped) == 4
    assert not any(issubclass(cls, BaseModel) for cls in mapped)


def test_the_audit_adapter_really_talks_to_the_database() -> None:
    """Rule 9 would hold vacuously on a module that issues no SQL at all."""
    imported = [name for name, _ in imported_modules(PACKAGE_ROOT / AUDIT_ADAPTER, PACKAGE_ROOT)]
    assert any(name.startswith("sqlalchemy") for name in imported)
    assert any(name.startswith("ela.audit.chain") for name in imported)
