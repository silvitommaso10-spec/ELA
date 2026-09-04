"""The architecture rules hold on the real source tree (CLAUDE.md "Architettura", spec §52)."""

import importlib

import pytest

from tests.architecture.rules import CORE_PACKAGES, RULES, Rule
from tests.architecture.violations import PACKAGE_ROOT


def test_required_modules_exist() -> None:
    """A rule about a file that does not exist would hold vacuously."""
    assert (PACKAGE_ROOT / "domain.py").is_file()
    assert (PACKAGE_ROOT / "ports.py").is_file()
    for name in CORE_PACKAGES:
        assert (PACKAGE_ROOT / name / "__init__.py").is_file(), f"missing package ela.{name}"


@pytest.mark.parametrize("rule", RULES.values(), ids=list(RULES))
def test_rule_holds(rule: Rule) -> None:
    violations = rule(PACKAGE_ROOT)
    assert not violations, "\n".join(str(v) for v in violations)


@pytest.mark.parametrize("module", ["ela.domain", "ela.ports"])
def test_module_is_importable(module: str) -> None:
    importlib.import_module(module)
