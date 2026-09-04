"""The architecture rules hold on the real source tree (CLAUDE.md "Architettura", spec §52)."""

import importlib

import pytest

from tests.architecture.rules import (
    CORE_PACKAGES,
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


def test_ports_really_import_the_domain() -> None:
    """Rule 2 held vacuously while ports.py was empty; now it has something to check."""
    imported = [name for name, _ in imported_modules(PACKAGE_ROOT / "ports.py", PACKAGE_ROOT)]
    assert any(name.startswith(PORTS_ALLOWED_INTERNAL) for name in imported)
    assert any(name.startswith("typing") for name in imported)


@pytest.mark.parametrize("rule", RULES.values(), ids=list(RULES))
def test_rule_holds(rule: Rule) -> None:
    violations = rule(PACKAGE_ROOT)
    assert not violations, "\n".join(str(v) for v in violations)


@pytest.mark.parametrize("module", ["ela.domain", "ela.ports", "ela.testing.fakes"])
def test_module_is_importable(module: str) -> None:
    importlib.import_module(module)
