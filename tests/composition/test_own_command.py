"""ELA's own command, named with certainty or not named at all (M13.9, decision 98).

The line ELA prints for a locked vault pipes the key of the vault into ``ela vault open``. Until
the review at ``1666739`` its right half was the bare name ``ela`` — looked for in the ``PATH``
of whoever pasted it, which is what ADR 0063 refuses for the left half, and it is the program
that receives the key. On the machine of the proof ``ela`` is in no ``PATH``: ELA is started
with ``uv run ela``, and the line did not work.

**Where the command is, measured** (2026-10-11, with ``ps`` on a running ELA): the Core runs as
``<venv>/bin/python3 <venv>/bin/ela serve`` — the command stands **beside the interpreter that
runs the Core**, as that interpreter is named: the interpreter of a virtual environment is a link
to the one it was made from, and the command is beside the link, not where it leads.

This file runs on the three systems of the CI — it is named on the Windows job's line too —, so
that «beside the interpreter» is measured on each: ``ela`` on a POSIX system, ``ela.exe`` on
Windows.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from ela.composition.system import own_command

WINDOWS = sys.platform == "win32"
NAME = "ela.exe" if WINDOWS else "ela"


def closed() -> dict[str, str]:
    """An environment with no environment activated and no ``ela`` in its ``PATH``: the system's
    own folders, and what a process needs to start at all."""
    if WINDOWS:
        root = os.environ["SYSTEMROOT"]
        return {"SYSTEMROOT": root, "PATH": str(Path(root) / "System32"), "PYTHONUTF8": "1"}
    return {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}


def test_the_command_is_the_one_beside_the_interpreter_that_runs_this_process() -> None:
    found = own_command()

    assert found is not None, "the suite runs from an environment ELA is installed in"
    assert found.is_absolute() and found.is_file()
    assert found.parent == Path(sys.executable).parent and found.name == NAME


def test_launched_where_no_ela_is_in_the_path_it_is_the_command_of_ela(tmp_path: Path) -> None:
    """The test that was missing: until now the tests asserted a string, never that what it
    names runs. Here it is launched for real — from a folder that is not ELA's, in an environment
    that has no ``ela`` to find — and it is ELA's own command line."""
    found = own_command()
    assert found is not None
    environment = closed()
    assert shutil.which("ela", path=environment["PATH"]) is None, "the precondition, built"

    ran = subprocess.run(  # noqa: S603 — the command under test, with arguments of the test's
        [str(found), "vault", "open", "--help"],
        env=environment,
        cwd=tmp_path,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )

    assert ran.returncode == 0, ran.stderr
    assert "vault open" in " ".join(ran.stdout.split()), ran.stdout


# ----------------------------------------------------------------------------------------
# The rule, on layouts the test builds: it runs wherever the suite runs
# ----------------------------------------------------------------------------------------


def installed(folder: Path, *names: str) -> Path:
    """A folder of programs as an environment keeps one: files that execute."""
    folder.mkdir(parents=True)
    for name in names:
        (folder / name).write_text("a file where a program would be", encoding="utf-8")
        (folder / name).chmod(0o755)
    return folder


def test_it_is_looked_for_beside_the_interpreter_and_nowhere_else(tmp_path: Path) -> None:
    here = installed(tmp_path / "venv" / "bin", "python3", "ela")
    installed(tmp_path / "elsewhere", "ela")

    assert own_command(str(here / "python3"), "Darwin") == here / "ela"
    assert own_command(str(here / "python3"), "Linux") == here / "ela"


def test_on_windows_the_command_is_the_one_with_its_extension(tmp_path: Path) -> None:
    here = installed(tmp_path / "venv" / "Scripts", "python.exe", "ela.exe", "ela")

    assert own_command(str(here / "python.exe"), "Windows") == here / "ela.exe"


@pytest.mark.skipif(WINDOWS, reason="a link to a file wants a privilege on Windows")
def test_the_interpreter_is_taken_as_it_is_named_and_never_where_its_link_leads(
    tmp_path: Path,
) -> None:
    """The interpreter of a virtual environment is a link to the one it was made from: the
    command is beside the link. Followed, the link would lead to a folder with no ``ela`` — or
    with somebody else's."""
    base = installed(tmp_path / "base" / "bin", "python3", "ela")
    venv = installed(tmp_path / "venv" / "bin", "ela")
    (venv / "python3").symlink_to(base / "python3")

    assert own_command(str(venv / "python3"), "Darwin") == venv / "ela"


@pytest.mark.parametrize("missing", ["no-command", "a-folder", "not-executable"])
def test_an_interpreter_with_no_command_of_ela_beside_it_names_none(
    tmp_path: Path, missing: str
) -> None:
    """ELA started some other way — ``python -m ela.cli`` from an interpreter nobody installed a
    command beside —: there is nothing to name with certainty, and nothing is named."""
    here = installed(tmp_path / "bin", "python3")
    if missing == "a-folder":
        (here / "ela").mkdir()
    if missing == "not-executable" and not WINDOWS:
        (here / "ela").write_text("not a program", encoding="utf-8")
        (here / "ela").chmod(0o644)
    if missing == "not-executable" and WINDOWS:
        pytest.skip("Windows has no bit that says a file executes")

    assert own_command(str(here / "python3"), "Darwin") is None


@pytest.mark.parametrize("named", ["", "python3", "bin/python3", "./python3"])
def test_an_interpreter_that_is_not_named_from_the_root_names_no_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, named: str
) -> None:
    """A path that does not begin at the root would be read from wherever the line is pasted."""
    installed(tmp_path / "bin", "python3", "ela")
    (tmp_path / "python3").write_text("x", encoding="utf-8")
    (tmp_path / "ela").write_text("x", encoding="utf-8")
    (tmp_path / "ela").chmod(0o755)
    monkeypatch.chdir(tmp_path)

    assert own_command(named, "Darwin") is None
