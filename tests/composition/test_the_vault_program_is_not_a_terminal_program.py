"""The vault's program is not one of the terminal's (M13.9c, ADR 0066 §3).

The adapter of the vault launches its program with a closed list of commands (ADR 0063 §2). **A
program of the terminal is launched with the arguments of a plan** (ADR 0047): declared there too,
the vault's program would run with arguments the closed list does not know — a defence the terminal
steps around. So a configuration in which **the vault's program is one of the terminal's** does not
start ELA, and the sentence names both lines.

**By identity, not by name** (answer 18 of the review at ``5808ae5``): the resolved path, and the
file itself — the same device and the same inode. A path through a link and a second name of the
same file are the same program; **a copy, byte for byte, in another file is another program**, and
is not recognised — declared in ADR 0066. A program that is not there is compared as a path.

Files of the test's, in its own folder: no ``bw`` is ever launched.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from ela.composition import ConfigurationError, Settings
from tests.composition.support import declare

PROGRAM = "ELA_VAULT_PROGRAM"
TERMINAL = "ELA_TERMINAL_PROGRAMS"


def made(folder: Path, name: str = "bw") -> Path:
    """A file that executes and is not a program anybody runs: its bytes say nothing."""
    folder.mkdir(parents=True, exist_ok=True)
    program = folder / name
    program.write_bytes(b"\xcf\xfa\xed\xfe a file of the test, never launched")
    program.chmod(program.stat().st_mode | stat.S_IXUSR)
    return program


def entry(path: Path) -> str:
    """An entry of ``ELA_TERMINAL_PROGRAMS``: the path written from ``/``, without it."""
    return str(path).lstrip("/")


def loaded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, vault: Path, *terminal: Path
) -> Settings:
    declare(monkeypatch, tmp_path)
    monkeypatch.setenv(PROGRAM, str(vault))
    monkeypatch.setenv(TERMINAL, json.dumps([entry(one) for one in terminal]))
    return Settings.load()


def refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, vault: Path, *terminal: Path) -> str:
    with pytest.raises(ConfigurationError) as raised:
        loaded(monkeypatch, tmp_path, vault, *terminal)
    return str(raised.value)


def test_the_vault_s_program_declared_as_the_terminal_s_does_not_start_ela(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    vault = made(tmp_path / "bin")

    said = refused(monkeypatch, tmp_path, vault, vault)

    assert PROGRAM in said and TERMINAL in said


def test_a_path_through_a_link_to_the_same_file_is_the_same_program(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    vault = made(tmp_path / "bin")
    link = tmp_path / "elsewhere" / "tool"
    link.parent.mkdir()
    link.symlink_to(vault)

    said = refused(monkeypatch, tmp_path, vault, link)

    assert PROGRAM in said and TERMINAL in said


def test_a_second_name_of_the_same_file_is_the_same_program(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A hard link: two paths that resolve to two places, and one file — the same inode."""
    vault = made(tmp_path / "bin")
    second = tmp_path / "other" / "tool"
    second.parent.mkdir()
    os.link(vault, second)

    said = refused(monkeypatch, tmp_path, vault, second)

    assert PROGRAM in said and TERMINAL in said


def test_a_program_that_is_not_there_is_the_same_by_its_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    vault = tmp_path / "bin" / "bw"

    said = refused(monkeypatch, tmp_path, vault, vault)

    assert PROGRAM in said and TERMINAL in said


def test_a_copy_of_the_vault_s_program_in_another_file_is_another_program(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The negative case: the same bytes, another file — not recognised, and declared so."""
    vault = made(tmp_path / "bin")
    copy = made(tmp_path / "other", "tool")
    copy.write_bytes(vault.read_bytes())

    settings = loaded(monkeypatch, tmp_path, vault, copy)

    assert settings.accounts.vault_program == str(vault)


def test_without_a_vault_s_program_every_terminal_program_is_one_of_the_terminal_s(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    program = made(tmp_path / "bin")
    declare(monkeypatch, tmp_path)
    monkeypatch.setenv(TERMINAL, json.dumps([entry(program)]))

    assert Settings.load().terminal.programs == (entry(program),)


def test_a_program_that_is_not_there_written_through_a_link_is_the_same_by_where_it_leads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Two spellings of one path that leads nowhere yet — one through a link to a folder —: no file
    to compare, and the resolved path says they are one. Found by a mutant that compared names."""
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "through").symlink_to(real)

    said = refused(monkeypatch, tmp_path, tmp_path / "through" / "bw", real / "bw")

    assert PROGRAM in said and TERMINAL in said
