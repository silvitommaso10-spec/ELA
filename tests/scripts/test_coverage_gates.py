"""``make check`` runs the suite once, and both of its gates read that one measurement.

Until 2026-09-12 ``make check`` ran the whole suite twice: once as ``test``, and once more inside
``cov-critical`` with a narrower ``--cov``. The second run measured the same lines as the first —
four minutes bought a filter. Now the suite runs once with coverage over all of ``ela`` and the
critical gate is a ``coverage report --include=…`` over the data it left behind.

The saving is only worth having if the two gates still fire, so both negative cases are here:

* **the suite gate** — a red suite must fail ``make check`` *and* stop before the coverage gate,
  which is the ordering ``cov-critical: test`` buys. Tested against the real Makefile with ``uv``
  replaced by a stub, so the wiring is the thing under test and no real command runs;
* **the critical gate** — a branch left untaken inside the measured packages must turn
  ``coverage report --fail-under=100`` red when it reads a *shared* data file. Tested against
  coverage.py itself on a throwaway project, because that mechanism is the part that changed.

A third failure is new and belongs to the filter: a package named wrongly in ``CRITICAL_PACKAGES``
would make the gate measure no file at all. That is not a silent 100% — ``coverage report`` says
"No data to report." and exits non-zero — and the test below is what keeps it that way.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.scripts.test_critical_packages import MAKEFILE, REPO_ROOT, critical_packages

pytestmark = pytest.mark.skipif(
    shutil.which("make") is None,
    reason="the Makefile is the thing under test, and reading it is not running it",
)

STUB = """#!/bin/sh
printf '%s\\n' "$*" >> "$UV_LOG"
case "$*" in
  "run pytest"*) exit "$PYTEST_EXIT" ;;
  "run coverage report"*) exit "$COVERAGE_EXIT" ;;
esac
exit 0
"""
"""A ``uv`` that runs nothing, records what it was asked for, and fails where told to."""


# ------------------------------------------------------------------------------------------
# What `make` says it will do: one suite, two gates, one definition of the second one
# ------------------------------------------------------------------------------------------


def dry_run(target: str) -> list[str]:
    """The recipe lines ``make`` would execute for ``target``, without executing them."""
    result = subprocess.run(
        ["make", "-n", target],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def suite_runs(lines: list[str]) -> list[str]:
    return [line for line in lines if " pytest" in line]


def gate_runs(lines: list[str]) -> list[str]:
    return [line for line in lines if "coverage report" in line]


def test_make_check_runs_the_suite_once() -> None:
    """The whole point: one execution, not two."""
    assert len(suite_runs(dry_run("check"))) == 1


def test_make_check_runs_both_gates_and_the_suite_before_them() -> None:
    lines = dry_run("check")
    (suite,) = suite_runs(lines)
    (gate,) = gate_runs(lines)
    assert "--fail-under=100" in gate
    assert lines.index(suite) < lines.index(gate)


def test_the_critical_gate_never_reads_yesterdays_measurement() -> None:
    """``make cov-critical`` on its own runs the suite: ``.coverage`` is not an input it trusts."""
    lines = dry_run("cov-critical")
    assert len(suite_runs(lines)) == 1
    assert lines.index(suite_runs(lines)[0]) < lines.index(gate_runs(lines)[0])


def test_check_linux_runs_the_suite_once_too() -> None:
    """The other machine pays for one run as well, and gets the same two gates."""
    lines = dry_run("check-linux")
    assert len(suite_runs(lines)) == 1
    assert len(gate_runs(lines)) == 1


def test_the_gate_is_written_once() -> None:
    """Two copies of a gate drift; ``cov-critical`` and ``check-linux`` must run the same words."""
    assert gate_runs(dry_run("cov-critical")) == gate_runs(dry_run("check-linux"))


def included_paths(gate: str) -> frozenset[str]:
    """The ``--include`` patterns of the gate command, as written."""
    prefix = "--include='"
    start = gate.index(prefix) + len(prefix)
    return frozenset(gate[start : gate.index("'", start)].split(","))


def test_the_gate_measures_exactly_the_critical_packages() -> None:
    """The patterns are derived from ``CRITICAL_PACKAGES``, so they cannot name anything else."""
    (gate,) = gate_runs(dry_run("cov-critical"))
    packages = critical_packages(MAKEFILE.read_text(encoding="utf-8"))
    assert included_paths(gate) == {f"src/{p.replace('.', '/')}/*" for p in packages}


def test_every_pattern_the_gate_uses_points_at_a_directory_that_exists() -> None:
    """A pattern matching no file would make the gate measure nothing (see the last test)."""
    (gate,) = gate_runs(dry_run("cov-critical"))
    for pattern in included_paths(gate):
        assert (REPO_ROOT / pattern.removesuffix("/*")).is_dir(), pattern


# ------------------------------------------------------------------------------------------
# Negative case of the suite gate: the real Makefile, with a `uv` that fails where told to
# ------------------------------------------------------------------------------------------


def make_check_with_a_stubbed_uv(
    tmp_path: Path, *, pytest_exit: int, coverage_exit: int
) -> tuple[int, list[str]]:
    """``make check`` against a ``uv`` that runs nothing. Returns its status and what was asked."""
    stub, log = tmp_path / "uv", tmp_path / "uv.log"
    stub.write_text(STUB, encoding="utf-8")
    stub.chmod(0o755)
    log.write_text("", encoding="utf-8")
    status = subprocess.run(
        ["make", "check", f"UV={stub}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "UV_LOG": str(log),
            "PYTEST_EXIT": str(pytest_exit),
            "COVERAGE_EXIT": str(coverage_exit),
        },
    ).returncode
    return status, log.read_text(encoding="utf-8").splitlines()


def test_every_step_green_makes_check_green(tmp_path: Path) -> None:
    """The positive control, without which the two below would pass on a broken Makefile."""
    status, asked = make_check_with_a_stubbed_uv(tmp_path, pytest_exit=0, coverage_exit=0)
    assert status == 0
    assert len(suite_runs(asked)) == 1
    assert len(gate_runs(asked)) == 1


def test_a_red_suite_fails_check_and_stops_before_the_coverage_gate(tmp_path: Path) -> None:
    status, asked = make_check_with_a_stubbed_uv(tmp_path, pytest_exit=1, coverage_exit=0)
    assert status != 0
    assert gate_runs(asked) == [], "the gate must not report on a suite that did not finish"


def test_a_red_coverage_gate_fails_check(tmp_path: Path) -> None:
    status, asked = make_check_with_a_stubbed_uv(tmp_path, pytest_exit=0, coverage_exit=2)
    assert status != 0
    assert len(gate_runs(asked)) == 1


# ------------------------------------------------------------------------------------------
# Negative case of the critical gate: coverage.py, a shared data file, and a branch left out
# ------------------------------------------------------------------------------------------

SOURCE = 'def decide(flag):\n    if flag:\n        return "yes"\n    return "no"\n'
TEST = """
from app.measured.decide import decide
from app.spare.decide import decide as spare


def test_one_side_of_each():
    assert decide(True) == "yes"
    assert decide(False) == "no"
    assert spare(True) == "yes"
"""


@pytest.fixture(scope="module")
def shared_measurement(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A throwaway project measured **once**, exactly as ``make test`` measures ``ela``.

    ``app.measured`` has both sides of its branch taken and ``app.spare`` only one, so the same
    data file answers the gate differently depending on what the filter points it at.
    """
    project = tmp_path_factory.mktemp("shared_measurement")
    for package in ("app", "app/measured", "app/spare"):
        (project / package).mkdir(exist_ok=True)
        (project / package / "__init__.py").write_text("", encoding="utf-8")
    (project / "app/measured/decide.py").write_text(SOURCE, encoding="utf-8")
    (project / "app/spare/decide.py").write_text(SOURCE, encoding="utf-8")
    (project / "test_decide.py").write_text(TEST, encoding="utf-8")
    (project / "pytest.ini").write_text("[pytest]\naddopts =\n", encoding="utf-8")
    run_in(project, "pytest", "-q", "-p", "no:cacheprovider", "--cov=app", "--cov-branch")
    assert (project / ".coverage").is_file(), "the suite must leave the measurement behind"
    return project


def run_in(project: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """A tool of this virtualenv, run inside the throwaway project.

    ``COV_CORE_*`` is dropped: pytest-cov exports it to make *this* suite's subprocesses report
    into *this* suite's data file, and the child here is measuring a project of its own.
    """
    return subprocess.run(
        [sys.executable, "-m", *arguments],
        cwd=project,
        capture_output=True,
        text=True,
        env={k: v for k, v in os.environ.items() if not k.startswith("COV_CORE")},
    )


def gate_on(project: Path, include: str) -> subprocess.CompletedProcess[str]:
    """The gate of the Makefile, word for word, pointed at the throwaway project."""
    return run_in(
        project, "coverage", "report", f"--include={include}", "--fail-under=100", "--show-missing"
    )


def test_the_gate_is_green_on_a_package_whose_branches_were_all_taken(
    shared_measurement: Path,
) -> None:
    """The positive control: without it, a gate red for the wrong reason would look right."""
    assert gate_on(shared_measurement, "app/measured/*").returncode == 0


def test_a_branch_left_untaken_turns_the_gate_red(shared_measurement: Path) -> None:
    """The gate the milestone changed: same data file, narrower filter, still 100% or nothing."""
    result = gate_on(shared_measurement, "app/spare/*")
    assert result.returncode != 0
    assert "less than fail-under=100" in result.stdout


def test_the_filter_narrows_the_measurement_instead_of_widening_the_gate(
    shared_measurement: Path,
) -> None:
    """``app.spare`` is measured and red, and the gate on ``app.measured`` is green anyway.

    This is the property the old ``--cov=<package>`` flags had for free and the ``--include`` has
    to earn: measuring everything must not drag an uncovered package into the critical gate.
    """
    assert gate_on(shared_measurement, "app/*").returncode != 0
    assert gate_on(shared_measurement, "app/measured/*").returncode == 0


def test_a_gate_that_measures_nothing_is_not_green(shared_measurement: Path) -> None:
    """A package misspelled in ``CRITICAL_PACKAGES`` must be loud, not a 100% over zero files."""
    result = gate_on(shared_measurement, "app/nonesuch/*")
    assert result.returncode != 0
    assert "No data to report." in result.stdout + result.stderr
