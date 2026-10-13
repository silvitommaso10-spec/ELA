"""The script of the measure of M13.9 is the one its tests last ran on (M13.9, decision 76).

``scripts/misura_m13_9.py`` is a script of the workshop whose measure is done: it stands at
``d110bc3`` and is not touched. Its tests — half a minute of every round — prove a file that
does not change, so **they are out of ``make check``**, in
``tests/scripts/misura_m13_9_checks.py``, a name the collection does not pick, and have a target
of their own: ``make misura-m13.9``.

What stays in the round is this: the digest of the script, compared with the one written beside
its tests (``misura_m13_9.sha256``). **A script that changed fails the round, and the failure
says which target to run** — so the tests that left cannot be forgotten on the day they matter.
**So does a change to what those tests are made of** — the file of the tests itself, the program
that stands where ``bw`` would be, and the recorded answers it gives —: nothing in the round
imports them any more, and a change to them would otherwise be tried by nobody (the re-read of
the round).
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
RECIPE = "$(UV) run pytest tests/scripts/misura_m13_9_checks.py --no-cov"
"""The whole line of the target: the tests that left, all of them, and nothing that narrows
them."""
COLLECTED_BY_DEFAULT = ("test_*.py", "*_test.py")
"""What pytest collects in a folder when nobody names a file, unless ``python_files`` says
otherwise — and ``pyproject.toml`` is read below to see that it does not."""


def frozen() -> list[Path]:
    """The files the digests are of, in the order they are written: the script, then the tests
    that left the round and what they are made of."""
    data = Path(__file__).with_name("data")
    return [
        SCRIPT,
        CHECKS,
        Path(__file__).with_name("fake_bw.py"),
        *sorted(
            found
            for found in data.rglob("*")
            if found.is_file() and found.suffix in {".txt", ".md", ".json"}
        ),
    ]


def digests(files: list[Path]) -> str:
    """What ``shasum -a 256`` prints of ``files``, named from the root of the repository."""
    return "".join(
        f"{hashlib.sha256(file.read_bytes()).hexdigest()}  {file.relative_to(ROOT).as_posix()}\n"
        for file in files
    )


def changed(found: str, written: str) -> str | None:
    """``None`` if ``found`` — the digests of the files as they are — is what is ``written``;
    else which file differs, and what to do about it."""
    if found == written:
        return None
    was = dict(line.split()[::-1] for line in written.splitlines() if len(line.split()) == 2)
    now = dict(line.split()[::-1] for line in found.splitlines())
    differ = sorted(name for name in now.keys() | was.keys() if now.get(name) != was.get(name))
    return (
        f"{', '.join(differ) or 'the file of the digests'} is not what the tests of the "
        f"measure's script last ran on. Those tests are out of `make check`: run `make "
        f"{TARGET}`, and when they pass write the digests again in tests/scripts/{WRITTEN.name} "
        "— the lines `shasum -a 256` prints of those files, in the order "
        "tests/scripts/test_misura_m13_9_frozen.py lists them"
    )


def test_the_script_of_the_measure_and_its_tests_are_the_ones_that_last_ran() -> None:
    said = changed(digests(frozen()), WRITTEN.read_text(encoding="utf-8"))

    assert said is None, said


def test_the_script_is_the_first_of_the_files_and_its_tests_and_their_program_are_among_them() -> (
    None
):
    names = [file.relative_to(ROOT).as_posix() for file in frozen()]

    assert names[0] == "scripts/misura_m13_9.py"
    assert "tests/scripts/misura_m13_9_checks.py" in names
    assert "tests/scripts/fake_bw.py" in names
    assert any(name.startswith("tests/scripts/data/") for name in names)
    assert len(set(names)) == len(names)


def test_a_file_that_changed_fails_the_round_and_says_which_and_which_target_to_run(
    tmp_path: Path,
) -> None:
    """The negative case, on copies: one byte more in the script, and the sentence names the
    script, the target and the file where the digests are written. So does a change to the tests
    that left, a file of the digests that holds nothing, and a line of it cut short."""
    written = WRITTEN.read_text(encoding="utf-8")
    script, checks = frozen()[0], frozen()[1]
    lines = written.splitlines(keepends=True)
    one_more = hashlib.sha256(script.read_bytes() + b"\n").hexdigest()

    said = changed(written.replace(lines[0].split()[0], one_more), written)
    assert said is not None and said.startswith("scripts/misura_m13_9.py is not")
    assert f"make {TARGET}" in said and WRITTEN.name in said

    other = hashlib.sha256(checks.read_bytes() + b"#").hexdigest()
    said = changed(written.replace(lines[1].split()[0], other), written)
    assert said is not None and said.startswith("tests/scripts/misura_m13_9_checks.py is not")

    assert changed(written, "") is not None
    assert changed(written, written[:-2]) is not None, "a line cut short"
    assert changed(written, "".join(lines[:-1])) is not None, "a file that is not listed any more"


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
    assert [line.strip() for line in recipe.splitlines() if line.strip()] == [RECIPE], (
        "the whole file, and no option that leaves a test out"
    )
    assert TARGET in makefile.split(".PHONY:", 1)[1].split("\n", 1)[0]
    assert f" {TARGET}" not in makefile.split("\ncheck:", 1)[1].split("\n", 1)[0], (
        "and `make check` does not run it"
    )
