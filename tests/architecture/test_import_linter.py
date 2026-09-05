"""The import-linter contracts in pyproject.toml mirror the rules and actually bite.

``make lint`` runs ``lint-imports``; these tests prove the contracts cover every current
package of ``ela`` and that each one breaks on a violating module.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

from tests.architecture.rules import (
    CORE_FORBIDDEN,
    CORE_PACKAGES,
    INFRA_LIBRARIES,
    INFRA_PACKAGES,
    PORTS_ALLOWED_INTERNAL,
    STATE_MACHINE_MODULE,
    TESTING_ALLOWED_INTERNAL,
    TESTING_PACKAGE,
    check_domain,
    top_level_modules,
)
from tests.architecture.violations import PACKAGE_ROOT, REPO_ROOT, VIOLATIONS, Case, apply

PYPROJECT = REPO_ROOT / "pyproject.toml"
LINT_IMPORTS = Path(sys.executable).parent / "lint-imports"

Contract = dict[str, Any]


def _contracts() -> list[Contract]:
    with PYPROJECT.open("rb") as fh:
        config = tomllib.load(fh)
    contracts: list[Contract] = config["tool"]["importlinter"]["contracts"]
    assert all(c["type"] == "forbidden" for c in contracts)
    return contracts


def _contract_for(rule: str) -> Contract:
    """The contract implementing a rule, found by its structure rather than its name."""
    for contract in _contracts():
        sources, forbidden = set(contract["source_modules"]), set(contract["forbidden_modules"])
        if rule == "domain" and sources == {"ela.domain"}:
            return contract
        if rule == "ports" and sources == {"ela.ports"}:
            return contract
        if rule == "infra-libraries" and forbidden == INFRA_LIBRARIES:
            return contract
        if rule == "core-isolation" and forbidden == set(CORE_FORBIDDEN):
            return contract
        if rule == "testing-isolation" and forbidden == {TESTING_PACKAGE}:
            return contract
        if rule == "testing-imports" and sources == {TESTING_PACKAGE}:
            return contract
        if rule == "state-machine-callers" and forbidden == {STATE_MACHINE_MODULE}:
            return contract
    raise AssertionError(f"pyproject.toml has no import-linter contract for rule {rule!r}")


def test_contracts_cover_current_packages() -> None:
    """Adding a package under src/ela without updating the contracts fails here."""
    modules = top_level_modules(PACKAGE_ROOT) | {"ela.infrastructure"}

    domain = _contract_for("domain")
    assert set(domain["forbidden_modules"]) >= (modules - {"ela.domain"}) | INFRA_LIBRARIES

    ports = _contract_for("ports")
    assert set(ports["forbidden_modules"]) >= (
        (modules - {"ela.ports", PORTS_ALLOWED_INTERNAL}) | INFRA_LIBRARIES | {"pydantic"}
    )

    infra = _contract_for("infra-libraries")
    exempt = {f"ela.{name}" for name in INFRA_PACKAGES}
    assert set(infra["source_modules"]) == modules - exempt

    core = _contract_for("core-isolation")
    assert set(core["source_modules"]) == {f"ela.{name}" for name in CORE_PACKAGES}

    isolation = _contract_for("testing-isolation")
    assert set(isolation["source_modules"]) == top_level_modules(PACKAGE_ROOT) - {TESTING_PACKAGE}

    testing = _contract_for("testing-imports")
    assert set(testing["forbidden_modules"]) >= (
        (modules - set(TESTING_ALLOWED_INTERNAL)) | INFRA_LIBRARIES | {"pydantic"}
    )

    callers = _contract_for("state-machine-callers")
    assert set(callers["source_modules"]) == modules - {"ela.tasks"}


def test_direct_only_contracts_are_the_ones_whose_source_imports_the_domain() -> None:
    """Contracts 2 and 6 check direct imports only: ports and fakes reach pydantic via the domain.

    Every other contract keeps the import-linter default and follows indirect chains too.
    """
    direct_only = {
        c["name"] for c in _contracts() if c.get("allow_indirect_imports") in ("True", True)
    }
    expected = {_contract_for("ports")["name"], _contract_for("testing-imports")["name"]}
    assert direct_only == expected


ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _run_lint_imports(project_root: Path) -> subprocess.CompletedProcess[str]:
    """``lint-imports`` on a project root, with colour off: the assertions read its text.

    A terminal that forces colour (``FORCE_COLOR``) would otherwise slip escape codes between
    a contract's name and ``BROKEN``; the codes are stripped from the output as well.
    """
    env = {**os.environ, "PYTHONPATH": str(project_root / "src"), "NO_COLOR": "1"}
    env.pop("FORCE_COLOR", None)
    env.pop("CLICOLOR_FORCE", None)
    result = subprocess.run(
        [str(LINT_IMPORTS), "--config", str(project_root / "pyproject.toml"), "--no-cache"],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    result.stdout = ANSI.sub("", result.stdout)
    return result


def test_lint_imports_keeps_all_contracts_on_repo() -> None:
    result = _run_lint_imports(REPO_ROOT)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"Contracts: {len(_contracts())} kept, 0 broken." in result.stdout


_BY_ID = {case.id: case for case in VIOLATIONS}
# One case per contract keeps the subprocess runs cheap; the pytest rules cover the rest.
LINTER_CASES = [
    _BY_ID[case_id]
    for case_id in (
        "domain-infra-library",
        "ports-pydantic",
        "infra-tasks",
        "infra-alembic-in-tasks",
        "core-tasks-providers",
        "testing-imported-by-executive",
        "testing-imports-tasks",
        "state-machine-imported-by-executive",
    )
]


@pytest.mark.parametrize("case", LINTER_CASES, ids=[c.id for c in LINTER_CASES])
def test_lint_imports_breaks_contract(tmp_path: Path, package_copy: Path, case: Case) -> None:
    shutil.copy(PYPROJECT, tmp_path / "pyproject.toml")
    apply(case, package_copy)

    result = _run_lint_imports(tmp_path)

    contract = _contract_for(case.rule)
    output = " ".join(result.stdout.split())  # import-linter wraps long contract names
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"{contract['name']} BROKEN" in output
    assert case.module in output


def test_lint_imports_cannot_close_the_world(tmp_path: Path, package_copy: Path) -> None:
    """A forbidden contract only bans listed modules: ``import yaml`` in domain slips through.

    This is why every rule also exists as a closed-world pytest rule in ``rules.py``.
    """
    case = _BY_ID["domain-third-party"]
    shutil.copy(PYPROJECT, tmp_path / "pyproject.toml")
    apply(case, package_copy)

    assert _run_lint_imports(tmp_path).returncode == 0
    assert [v.imported for v in check_domain(package_copy)] == [case.imported]
