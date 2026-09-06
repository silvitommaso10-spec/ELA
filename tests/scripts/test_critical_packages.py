"""The ``cov-critical`` gate covers the packages CLAUDE.md calls security-critical.

The gate itself is pytest-cov's ``--cov-fail-under=100``; what can silently drift is the *list*
it is pointed at. CLAUDE.md requires a package to join ``CRITICAL_PACKAGES`` in the same milestone
in which it receives code, and a package that quietly stays out is a rule enforced on nothing —
exactly the failure this test exists to make loud.
"""

from __future__ import annotations

import re

from tests.architecture.violations import REPO_ROOT

MAKEFILE = REPO_ROOT / "Makefile"
ASSIGNMENT = re.compile(r"^CRITICAL_PACKAGES = (.+)$", re.MULTILINE)
REQUIRED = {
    "ela.tasks",  # CLAUDE.md, "Qualità": tasks/
    "ela.permissions",  # CLAUDE.md: permissions/
    "ela.audit",  # CLAUDE.md: audit/
    "ela.infrastructure.persistence",  # M2.1: it keeps the grants and the audit trail
    "ela.executive",  # M5.1: the only caller of a tool
    "ela.tools",  # M5.1: it guards the workspace
    "ela.devices",  # M6.1: it decides whether a node may be used (ADR 0016)
}


def critical_packages(text: str) -> frozenset[str]:
    """The packages of the ``CRITICAL_PACKAGES`` assignment, line continuations joined."""
    match = ASSIGNMENT.search(text.replace("\\\n", " "))
    assert match is not None, "the Makefile must assign CRITICAL_PACKAGES"
    return frozenset(match.group(1).split())


def test_every_security_critical_package_is_in_the_gate() -> None:
    assert critical_packages(MAKEFILE.read_text(encoding="utf-8")) >= REQUIRED


def test_every_package_in_the_gate_exists() -> None:
    """A typo in the list would make the gate measure nothing and still pass."""
    for package in critical_packages(MAKEFILE.read_text(encoding="utf-8")):
        path = REPO_ROOT / "src" / package.replace(".", "/")
        assert (path / "__init__.py").is_file(), package


def test_a_package_left_out_of_the_gate_is_detected() -> None:
    """Negative case: the Makefile of the milestone before this one."""
    text = MAKEFILE.read_text(encoding="utf-8").replace(" ela.devices", "")
    assert "ela.devices" not in critical_packages(text)
    assert not critical_packages(text) >= REQUIRED
