"""The CLI tests read text, so the text must be the same everywhere (CI fix, runs #72 and #73).

On GitHub Actions Typer decides that it is writing to a terminal — ``FORCE_TERMINAL`` is true as
soon as ``GITHUB_ACTIONS`` is set — and Rich then colours the error panel. Its option highlighter
carries two patterns that both match a long option, ``switch`` (``-\\w+``) and ``option``
(``--[\\w-]+``), so ``--approval`` leaves as two styled spans with an escape sequence between the
dashes. ``"--approval" in result.stderr`` is then false on a CLI that behaved perfectly.

Three tests: that the guard holds when the environment says CI, that without it the option really
does come apart (the failure this fixes, kept as a test rather than as a memory), and that the
whole CLI suite passes with ``GITHUB_ACTIONS=true`` — which is the claim that matters.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from typer import rich_utils
from typer.testing import CliRunner

from ela.cli.app import app
from tests.cli.support import ANSI, WIDTH, plain

REPO_ROOT = Path(__file__).resolve().parents[2]
ESCAPE = "\x1b"
MISSING_APPROVAL = ("task", "approve", "01912d3f-0000-7000-8000-000000000000")
"""A usage error, and the one that failed in CI: it never reaches the API, only the formatter."""


def _stderr_of_a_missing_option() -> str:
    return CliRunner().invoke(app, list(MISSING_APPROVAL)).stderr


def _environment() -> dict[str, str]:
    """The current environment, minus what would tell the inner run to measure coverage again."""
    return {name: value for name, value in os.environ.items() if not name.startswith("COV_CORE")}


def test_the_guard_holds_when_the_environment_says_github_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Set after the fixture ran, the variable changes nothing: the decision is no longer read
    from the environment."""
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("FORCE_COLOR", "1")

    stderr = _stderr_of_a_missing_option()

    assert ESCAPE not in stderr
    assert "--approval" in stderr


def test_the_width_is_the_one_the_suite_fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A wrapped panel is a different string; the column it wraps at belongs to the suite."""
    monkeypatch.setenv("COLUMNS", "40")  # a terminal narrower than the panel, ignored

    assert max(len(line) for line in _stderr_of_a_missing_option().splitlines()) == WIDTH


def test_without_the_guard_the_option_comes_apart_and_plain_puts_it_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The negative case: what CI saw, and what :func:`~tests.cli.support.plain` survives."""
    monkeypatch.setattr(rich_utils, "FORCE_TERMINAL", True)

    stderr = _stderr_of_a_missing_option()

    assert ESCAPE in stderr
    assert "--approval" not in stderr
    assert ANSI.sub("", "-\x1b[0m\x1b[1;36m-approval") == "--approval"
    assert "--approval" in plain(stderr)


def test_the_cli_suite_passes_when_github_actions_says_it_is_a_terminal() -> None:
    """The claim itself, made the only way it can be made honestly: run the suite that way.

    This module is left out of the inner run — it is the one running it — and coverage with it:
    the outer run is already measuring.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/cli",
            f"--ignore={Path(__file__).relative_to(REPO_ROOT).as_posix()}",
            "-q",
            "--no-cov",
            "-p",
            "no:cacheprovider",
        ],
        cwd=REPO_ROOT,
        env={**_environment(), "GITHUB_ACTIONS": "true"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
