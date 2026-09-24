"""``make lint`` asks ruff without its cache: the cache remembers a module that did not exist.

ruff sorts an import as first-party only if the module is there, and caches its verdict per file
without looking at the other files again. The order of every milestone — the failing tests in a
commit of their own, the code after — writes a test that imports a module before the module
exists: ruff sorts it as third-party, and after the module arrives the cached verdict still says
the file is clean. On 2026-09-24 ``make check`` was green here and ruff was red on both runners of
the CI, which have no cache, on the three test files of M13.2 written before ``ela.tools.terminal``.

Both halves are asserted on a throwaway project, with the command read from the real Makefile: the
cache really does keep the stale verdict — the precondition, built and not assumed —, and the
command of ``make lint`` does not. If ruff one day learns to forget, the first assertion goes red,
and the flag can be weighed again.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
from pathlib import Path

import pytest
from ruff.__main__ import find_ruff_bin

from tests.scripts.test_critical_packages import MAKEFILE

pytestmark = pytest.mark.skipif(
    shutil.which("make") is None,
    reason="the Makefile is the thing under test, and reading it is not running it",
)

PYPROJECT = '[tool.ruff]\nsrc = ["src", "tests"]\n[tool.ruff.lint]\nselect = ["I"]\n'
BEFORE_THE_MODULE = (
    "from __future__ import annotations\n\n"
    "import pytest\n"
    "from pkg.later import LATER\n\n"
    "from pkg.now import NOW\n"
)
"""A test as ruff sorts it while ``pkg.later`` does not exist yet: third-party, beside pytest."""


def lint_check() -> list[str]:
    """The arguments of the ruff line of ``make lint``, as ``make`` would run it."""
    recipe = subprocess.run(
        ["make", "-n", "-f", str(MAKEFILE), "lint", "UV=uv"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    (line,) = [one for one in recipe if one.startswith("uv run ruff check")]
    return shlex.split(line)[3:]


def ruff(project: Path, *arguments: str) -> int:
    return subprocess.run(
        [find_ruff_bin(), *arguments], cwd=project, capture_output=True, check=False
    ).returncode


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A test written before its module, checked once — the cache warmed — and then the module."""
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "src" / "pkg" / "now.py").write_text("NOW = 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_later.py").write_text(BEFORE_THE_MODULE, encoding="utf-8")
    assert ruff(tmp_path, "check", ".") == 0, "while the module is missing, the order is right"
    (tmp_path / "src" / "pkg" / "later.py").write_text("LATER = 2\n", encoding="utf-8")
    return tmp_path


def test_the_cache_keeps_the_verdict_of_a_module_that_did_not_exist(project: Path) -> None:
    assert ruff(project, "check", ".") == 0


def test_the_ruff_of_make_lint_sees_the_module_that_arrived(project: Path) -> None:
    assert "--no-cache" in lint_check()
    assert ruff(project, *lint_check()) == 1
