"""``make check`` names every skip with its reason, and still names every failure (M13.2).

With ``-q`` alone a skip is a number in the last line, and a number nobody reads is how a test
stops proving what it exists for without anybody noticing — the review of M13.2 found the run of a
test on Linux deduced from counts. So the options of the suite carry ``-ra``: every skip is a line
with its file and its reason. **Not ``-rs``**: ``-r`` replaces pytest's default ``fE`` instead of
adding to it, and ``-rs`` alone would take the failures out of the short summary.

Asserted on the options the suite really runs with, and then on pytest itself, on a throwaway
project: the reporting characters of the suite name a skip's reason and a failure, and without
them the reason is gone — the negative case the option exists for.

**And the job of Windows shows no less than the suite** (M9.5, decision 74 of the review at
``ad1826c``): its ``pytest`` line has a ``-r`` of its own, which replaces the suite's — until
2026-11-17 ``-rs``, a short summary that named the skips and not the failures. The letters are
derived from ``addopts``, not written here; and no ``-q`` of its own: with two, pytest drops the
line of counts criterion 17 of M12.4 reads.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

from tests.scripts.test_critical_packages import REPO_ROOT

SKIPPED = (
    "import pytest\n"
    "\n"
    "\n"
    "@pytest.mark.skipif(True, reason='la ragione dichiarata')\n"
    "def test_saltato():\n"
    "    pass\n"
    "\n"
    "\n"
    "def test_rotto():\n"
    "    assert False\n"
)
"""A skip with its reason and a failure: the two lines the summary of the suite has to carry."""


def reporting() -> list[str]:
    """The ``-q`` and ``-r`` options of the suite, as ``pyproject.toml`` gives them to pytest."""
    options = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    addopts: str = options["tool"]["pytest"]["ini_options"]["addopts"]
    return [one for one in addopts.split() if one == "-q" or one.startswith("-r")]


def summary(project: Path, *options: str) -> str:
    (project / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (project / "test_uno.py").write_text(SKIPPED, encoding="utf-8")
    ran = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *options],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    return ran.stdout


def test_the_suite_reports_every_skip_and_every_failure() -> None:
    assert "-ra" in reporting()


def test_with_the_options_of_the_suite_a_skip_is_a_line_with_its_reason(tmp_path: Path) -> None:
    shown = summary(tmp_path, *reporting())

    assert "SKIPPED [1] test_uno.py:4: la ragione dichiarata" in shown
    assert "FAILED test_uno.py::test_rotto" in shown


def test_without_them_the_reason_of_a_skip_is_gone(tmp_path: Path) -> None:
    shown = summary(tmp_path, "-q")

    assert "la ragione dichiarata" not in shown
    assert "1 skipped" in shown


EVERY = frozenset("fEsxX")
"""What ``a`` stands for: everything but the passes (``p``, ``P``)."""


def letters(options: list[str]) -> frozenset[str]:
    """What the short summary shows with ``options``, as pytest reads them: the last ``-r`` wins,
    and ``a`` and ``A`` stand for their letters."""
    chosen = [one[2:] for one in options if one.startswith("-r")]
    if not chosen:
        return frozenset("fE")
    shown = set(chosen[-1]) - {"a", "A", "N"}
    if "a" in chosen[-1]:
        shown |= EVERY
    if "A" in chosen[-1]:
        shown |= EVERY | {"p", "P"}
    return frozenset(shown)


def windows_job() -> list[str]:
    """The ``pytest`` line of the job of Windows, as ``.github/workflows/ci.yml`` has it."""
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    (line,) = [one for one in workflow.splitlines() if "pytest" in one and "tests/node" in one]
    return line.split()


def less_than_the_suite(job: list[str], suite: list[str]) -> list[str]:
    """What is wrong with the options of a job that runs after ``suite``'s: letters of the suite it
    does not show, or a ``-q`` of its own."""
    problems = []
    missing = letters(suite) - letters([*suite, *job])
    if missing:
        problems.append(f"the job does not show {''.join(sorted(missing))}")
    if "-q" in job:
        problems.append("a -q of its own: pytest drops the line of counts")
    return problems


def test_the_job_of_windows_shows_no_less_than_the_suite() -> None:
    assert less_than_the_suite(windows_job(), reporting()) == []


def test_a_job_that_shows_less_or_says_q_is_seen() -> None:
    """The negative cases, on lines built here: the ``-rs`` that stood until M9.5, and a ``-q``."""
    suite = ["-q", "-ra"]

    assert less_than_the_suite(["pytest", "-rs", "tests/node"], suite) == [
        "the job does not show EXfx"
    ]
    assert less_than_the_suite(["pytest", "-q", "-ra", "tests/node"], suite) == [
        "a -q of its own: pytest drops the line of counts"
    ]
    assert less_than_the_suite(["pytest", "-ra", "tests/node"], suite) == []
    assert less_than_the_suite(["pytest", "tests/node"], suite) == []
