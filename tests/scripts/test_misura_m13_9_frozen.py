"""The script of the measure of M13.9 is the one its tests last ran on (M13.9, decision 76).

``scripts/misura_m13_9.py`` is a script of the workshop whose measure is done: it stands at
``d110bc3`` and is not touched. Its tests — half a minute of every round — prove a file that
does not change, so **they are out of ``make check``**, in
``tests/scripts/misura_m13_9_checks.py``, a name the collection does not pick, and have a target
of their own: ``make misura-m13.9``.

What stays in the round is this: the digest of the script, compared with the one written beside
its tests (``misura_m13_9.sha256``). **A script that changed fails the round, and the failure
says which target to run** — so the tests that left cannot be forgotten on the day they matter.
"""

from __future__ import annotations

import fnmatch
import hashlib
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "misura_m13_9.py"
CHECKS = Path(__file__).with_name("misura_m13_9_checks.py")
WRITTEN = Path(__file__).with_name("misura_m13_9.sha256")
TARGET = "misura-m13.9"
COLLECTED_BY_DEFAULT = ("test_*.py", "*_test.py")
"""What pytest collects in a folder when nobody names a file, unless ``python_files`` says
otherwise — and ``pyproject.toml`` is read below to see that it does not."""


def changed(script: bytes, written: str) -> str | None:
    """``None`` if ``script`` is the one whose digest is ``written`` — the form of ``shasum``:
    the digest, then the name —; else what to do about it."""
    found = hashlib.sha256(script).hexdigest()
    if written.split()[:1] == [found]:
        return None
    return (
        f"scripts/{SCRIPT.name} is not the script its tests last ran on (sha256 {found}). Its "
        f"tests are out of `make check`: run `make {TARGET}`, and when they pass write the new "
        f"digest — `shasum -a 256 scripts/{SCRIPT.name} > tests/scripts/{WRITTEN.name}`"
    )


def test_the_script_of_the_measure_is_the_one_its_tests_last_ran_on() -> None:
    said = changed(SCRIPT.read_bytes(), WRITTEN.read_text(encoding="utf-8"))

    assert said is None, said


def test_a_script_that_changed_fails_the_round_and_says_which_target_to_run() -> None:
    """The negative case: one byte more, and the sentence names the target and the file where
    the digest is written. So does a file of the digest that holds nothing."""
    written = WRITTEN.read_text(encoding="utf-8")

    said = changed(SCRIPT.read_bytes() + b"\n", written)

    assert said is not None
    assert f"make {TARGET}" in said and WRITTEN.name in said and SCRIPT.name in said
    assert changed(SCRIPT.read_bytes(), "") is not None
    assert changed(SCRIPT.read_bytes(), written.split()[0][:-1]) is not None, "a digest cut short"


def test_the_tests_that_left_the_round_are_there_and_the_target_runs_them() -> None:
    """They left the round, not the repository: the file holds its tests, no round collects it
    by itself, and the target of the Makefile names it."""
    relative = CHECKS.relative_to(ROOT).as_posix()
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    recipe = makefile.split(f"\n{TARGET}:", 1)[1].split("\n\n", 1)[0]
    configured = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    options = configured["tool"]["pytest"]["ini_options"]

    assert CHECKS.read_text(encoding="utf-8").count("\ndef test_") > 0
    assert "python_files" not in options, "the patterns below are pytest's own"
    assert not any(fnmatch.fnmatch(CHECKS.name, pattern) for pattern in COLLECTED_BY_DEFAULT)
    assert relative in recipe and "pytest" in recipe
    assert TARGET in makefile.split(".PHONY:", 1)[1].split("\n", 1)[0]
    assert f" {TARGET}" not in makefile.split("\ncheck:", 1)[1].split("\n", 1)[0], (
        "and `make check` does not run it"
    )
