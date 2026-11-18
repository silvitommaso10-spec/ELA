"""The root up to the home, and the list of the folders it opens (M13.17, ADR 0074; decisions 3–6,
13 and 51 of its blocks, answers 35, 36 and 41 of the review of its SPEC).

- **The form**: ``ELA_FS_SCOPE`` is one line of JSON, a list of entries in the grammar of every
  scope; the line of yesterday is refused with the line to write, the user's value inside it; a
  line that is no list of strings, and ``[]``, are refused with their sentences.
- **The root**: it may hold what ELA uses to exist — and every use refuses those places —, it may
  be the home, and it may not hold the home. **The home is injected** (decision 26): ``HOME`` for
  the settings, a parameter for :func:`refuse_the_root`.
- **Every folder at the start-up**: looked at with the look of every use, opened as a folder and
  closed without a name read, within the guard's limit; refused when it is not there, is a file or
  a link, when the system does not let ELA look or does not answer, or when it is a place of
  ELA's; admitted when it holds one.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

import pytest

from ela.composition import ConfigurationError, Settings
from ela.composition import settings as composition_settings
from ela.composition.settings import (
    PERMISSION_IS_THE_TERMINAL_S,
    refuse_the_folders,
    refuse_the_root,
)
from ela.permissions import fs_read, fs_write, production_catalogue
from ela.tools.paths import PATH_UNREACHABLE, PathProblem
from tests.composition.places_at_every_use import every_use_refuses
from tests.composition.support import declare


def refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **extra: str) -> str:
    declare(monkeypatch, tmp_path, **extra)
    with pytest.raises(ConfigurationError) as raised:
        Settings.load()
    return str(raised.value)


def loaded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **extra: str) -> Settings:
    declare(monkeypatch, tmp_path, **extra)
    return Settings.load()


def a_folder(*parts: Path | str) -> Path:
    made = Path(*parts)
    made.mkdir(parents=True, exist_ok=True)
    return made


def a_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """The home of who uses ELA, injected: ``HOME`` and ``USERPROFILE`` for ``Path.home()``."""
    home = a_folder(tmp_path, "casa")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


# ----------------------------------------------------------------------------------------
# The form: one line of JSON (answers 35 and 36)
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("written", "rewritten"),
    [
        ("ELA", '["ELA"]'),
        ("Documenti è miei", '["Documenti è miei"]'),
        ("null", '["null"]'),
    ],
)
def test_the_line_of_yesterday_is_refused_with_the_line_to_write(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, written: str, rewritten: str
) -> None:
    """Answer 35: ``ELA_FS_SCOPE=ELA`` and a folder named ``["ELA"]`` cannot be told apart without
    guessing; the line that is no list is refused, and the sentence prints the rewriting with the
    user's own value — ``null`` included, which the decoder of the programs would read as
    missing."""
    message = refused(monkeypatch, tmp_path, ELA_FS_SCOPE=written)

    assert "ELA_FS_SCOPE: since M13.17 the scope is a list of folders, one line of JSON" in message
    assert f"ELA_FS_SCOPE={rewritten}" in message


@pytest.mark.parametrize("written", ['["ELA", 1]', "[draft]", '["ELA"'])
def test_a_line_that_is_no_list_of_strings_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, written: str
) -> None:
    message = refused(monkeypatch, tmp_path, ELA_FS_SCOPE=written)

    assert "is not a list of folders in JSON" in message
    assert 'ELA_FS_SCOPE=["Documents", "Desktop"]' in message


def test_an_empty_list_is_refused_with_its_sentence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Answer 36: the scope opens at least one folder; «no folder» is a state nobody asked for."""
    message = refused(monkeypatch, tmp_path, ELA_FS_SCOPE="[]")

    assert "ELA_FS_SCOPE is [], and the scope opens at least one folder" in message
    assert "or [] for none" not in message


def test_a_list_of_folders_is_read_in_its_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The order is the user's: the first folder is the one a command of the terminal starts
    from (answer 41)."""
    root = a_folder(tmp_path, "files")
    for name in ("Desktop", "Documents"):
        a_folder(root, name)

    settings = loaded(monkeypatch, tmp_path, ELA_FS_SCOPE='["Desktop", "Documents"]')

    assert settings.filesystem.scope == ("Desktop", "Documents")


def test_the_catalogue_takes_the_list_and_refuses_one_string() -> None:
    """A string is a sequence of its characters: ``"ELA"`` would be the scope ``('E','L','A')``."""
    assert fs_read(("Documents", "Desktop")).scope == ("Documents", "Desktop")
    assert production_catalogue(fs_scope=("ELA",)).get(fs_write().id).scope == ("ELA",)
    with pytest.raises(TypeError, match="not one string"):
        fs_read("ELA")  # type: ignore[arg-type]


# ----------------------------------------------------------------------------------------
# The root: up to the home (decision 5)
# ----------------------------------------------------------------------------------------


def test_the_home_itself_may_be_the_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = a_home(monkeypatch, tmp_path)
    a_folder(home, "ELA")

    assert loaded(monkeypatch, tmp_path, ELA_FS_ROOT=str(home)).filesystem.root == home


def test_a_root_above_the_home_stops_ela_with_a_sentence_of_its_own(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Until M13.17 this was refused because the root held ``~/.ela``; since M13.17 a root may hold
    it, and a root above the home is refused for what it is."""
    above = a_folder(tmp_path, "sopra")
    a_folder(above, "ELA")
    inside = a_folder(above, "dentro")
    monkeypatch.setenv("HOME", str(inside))
    monkeypatch.setenv("USERPROFILE", str(inside))

    message = refused(monkeypatch, tmp_path, ELA_FS_ROOT=str(above))

    assert f"holds your home ({inside.resolve()})" in message
    assert "reach at most up to your home" in message


def test_the_rule_of_the_home_reads_the_home_it_is_handed(tmp_path: Path) -> None:
    """The home is a parameter: a root that holds it and is not it is refused; the home and a
    folder that does not hold it are not."""
    home = a_folder(tmp_path, "u", "casa")
    elsewhere = a_folder(tmp_path, "altrove")

    refuse_the_root(home, {}, home=home)
    refuse_the_root(elsewhere, {}, home=home)
    with pytest.raises(ValueError, match="holds your home"):
        refuse_the_root(tmp_path / "u", {}, home=home)


async def test_a_root_that_holds_everything_of_ela_s_is_admitted_and_every_use_refuses_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Decision 8 (iii) and (iv): the root of the test **holds** the database, the workspace, the
    captures, the node's secret and the ``.env`` — the case that stood for ``~`` until M13.17. It is
    admitted, and each place is refused at every use, by its name."""
    root = tmp_path
    a_folder(root, "ELA")
    (root / ".env").write_text("", encoding="utf-8")

    settings = loaded(
        monkeypatch, tmp_path, ELA_FS_ROOT=str(root), ELA_NODE_STATE_DIR=str(tmp_path / "state")
    )
    own = settings.ela_s_own()

    for what in (
        "the database",
        "the workspace",
        "the capture store",
        "the folder a node keeps its secret in",
        "the .env ELA read",
    ):
        place = own[what]
        if what == "the database":
            place.touch()
        await every_use_refuses(root, own, place, what)


def test_the_list_names_the_journal_of_the_database_the_sessions_and_an_env_not_there(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Answer 39: paths ELA's settings already have — the journal beside the database, the folders
    of the guided sessions —, and the ``.env`` of the folder ELA starts from even when there is
    none: the next start reads the one written meanwhile."""
    own = loaded(monkeypatch, tmp_path).ela_s_own()
    database = own["the database"]

    assert not (tmp_path / ".env").exists(), "the precondition: no .env here"
    assert own["the .env ELA read"] == (tmp_path / ".env").resolve()
    for suffix in ("-wal", "-shm", "-journal"):
        assert own[f"the journal of the database ({suffix})"] == database.with_name(
            database.name + suffix
        )
    assert own["the folders of the guided sessions"] == (tmp_path / "sessions").resolve()


# ----------------------------------------------------------------------------------------
# Every folder of the scope, at the start-up (decisions 6, 13 and 51)
# ----------------------------------------------------------------------------------------


def test_a_folder_that_is_not_there_stops_ela_and_is_named(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    message = refused(monkeypatch, tmp_path, ELA_FS_SCOPE='["ELA", "Scrivania"]')

    assert "ELA_FS_SCOPE: 'Scrivania' is not under ELA_FS_ROOT" in message
    assert "ELA never creates a folder you open" in message


def test_a_file_or_a_link_in_the_list_stops_ela(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = a_folder(tmp_path, "files")
    (root / "un-file").write_text("", encoding="utf-8")
    (root / "un-link").symlink_to(a_folder(tmp_path, "altrove"))

    as_a_file = refused(monkeypatch, tmp_path, ELA_FS_SCOPE='["un-file"]')
    as_a_link = refused(monkeypatch, tmp_path, ELA_FS_SCOPE='["un-link"]')

    assert "'un-file' is a file, not a folder" in as_a_file
    assert "'un-link'" in as_a_link and "never through a link" in as_a_link


def test_a_folder_that_is_a_place_of_ela_s_stops_ela_and_one_that_holds_it_does_not(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An entry that is ELA's home would open nothing; one that holds it opens the rest, and every
    use refuses the home."""
    home = a_home(monkeypatch, tmp_path)
    a_folder(home, ".ela")
    a_folder(home, "ELA")

    message = refused(monkeypatch, tmp_path, ELA_FS_ROOT=str(home), ELA_FS_SCOPE='[".ela"]')
    settings = loaded(monkeypatch, tmp_path, ELA_FS_ROOT=str(home), ELA_FS_SCOPE='["ELA"]')

    assert "ELA_FS_SCOPE: '.ela' is, or lies inside," in message
    assert str((home / ".ela").resolve()) in message
    assert "it would open nothing" in message
    assert settings.filesystem.scope == ("ELA",)


def test_a_folder_the_system_does_not_let_ela_look_at_stops_ela_and_says_whose_permission(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Decision 13: what the system answered, with the error's type, and where the permission is
    given — the terminal's, not ELA's. Built by injection: on this machine no folder of the test
    is closed to ELA."""

    def closed(path: Any) -> Any:
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(composition_settings.os, "scandir", closed)

    message = refused(monkeypatch, tmp_path)

    assert "ELA_FS_SCOPE: 'ELA' cannot be opened (PermissionError)" in message
    assert PERMISSION_IS_THE_TERMINAL_S.replace("\n", " ")[:40] in message.replace("\n  ", " ")


def test_a_folder_the_look_cannot_reach_says_the_error_and_the_permission(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        composition_settings,
        "classify",
        lambda root, path: PathProblem(PATH_UNREACHABLE, "cannot be reached: PermissionError"),
    )

    message = refused(monkeypatch, tmp_path)

    assert "'ELA' cannot be reached: PermissionError: the system did not let ELA look" in message


def test_a_folder_that_cannot_be_opened_for_another_reason_says_its_type(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def broken(path: Any) -> Any:
        raise OSError(5, "I/O error")

    monkeypatch.setattr(composition_settings.os, "scandir", broken)

    assert "cannot be opened as a folder (OSError)" in refused(monkeypatch, tmp_path)


def test_the_folder_is_opened_and_closed_and_no_name_is_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Decision 51: the look opens the folder — where macOS asks — and reads no name."""
    opened: list[str] = []
    real = os.scandir

    class Opened:
        def __init__(self, path: Any) -> None:
            self._inner = real(path)
            opened.append(os.fspath(path))

        def __enter__(self) -> Opened:
            return self

        def __exit__(self, *_: object) -> None:
            self._inner.close()

        def __iter__(self) -> Any:
            raise AssertionError("a name of the folder was read")

    monkeypatch.setattr(composition_settings.os, "scandir", Opened)

    loaded(monkeypatch, tmp_path)

    assert [Path(one).name for one in opened] == ["ELA"]


def test_a_folder_the_system_does_not_answer_for_stops_ela_at_the_limit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Decision 12, at the start-up: a look that does not answer is given up at the guard's limit,
    and the sentence says what to do. The limit is the test's, and the silence is injected."""
    released = threading.Event()
    root = a_folder(tmp_path, "files")
    a_folder(root, "Documents")
    real = os.scandir

    def silent(path: Any) -> Any:
        released.wait()
        return real(path)

    monkeypatch.setattr(composition_settings.os, "scandir", silent)
    try:
        with pytest.raises(ValueError, match="did not answer within 0.2 s") as raised:
            refuse_the_folders(root, ("Documents",), {}, limit=0.2)
    finally:
        released.set()

    assert "ELA_FS_SCOPE: 'Documents'" in str(raised.value)
    assert "If a window asked for a permission, answer it and start ELA again" in str(raised.value)
