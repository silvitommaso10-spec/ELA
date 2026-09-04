"""Each rule reports the module that violates it and stays quiet on allowed imports.

Without these tests the rules in ``rules.py`` could silently pass "a vuoto" forever.
"""

from pathlib import Path

import pytest

from tests.architecture.rules import RULES, Rule
from tests.architecture.violations import ALLOWED, VIOLATIONS, Case, apply


@pytest.mark.parametrize("rule", RULES.values(), ids=list(RULES))
def test_clean_copy_passes(package_copy: Path, rule: Rule) -> None:
    assert rule(package_copy) == []


@pytest.mark.parametrize("case", VIOLATIONS, ids=[c.id for c in VIOLATIONS])
def test_violation_is_reported(package_copy: Path, case: Case) -> None:
    apply(case, package_copy)
    violations = RULES[case.rule](package_copy)
    assert [(v.module, v.imported) for v in violations] == [(case.module, case.imported)]


@pytest.mark.parametrize("case", ALLOWED, ids=[c.id for c in ALLOWED])
def test_allowed_import_is_not_reported(package_copy: Path, case: Case) -> None:
    apply(case, package_copy)
    assert RULES[case.rule](package_copy) == []


def test_violation_is_only_reported_by_its_rule(package_copy: Path) -> None:
    """executive/ importing ela.providers breaks rule 4 only: providers is not a library."""
    apply(VIOLATIONS[-1], package_copy)  # executive/loop.py -> ela.providers.claude
    assert RULES["infra-libraries"](package_copy) == []
    assert len(RULES["core-isolation"](package_copy)) == 1
