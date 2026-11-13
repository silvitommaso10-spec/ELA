"""What ELA uses to exist, on the Core: the places its root may not touch and no write reaches
(M13.1 dec. F; M13.14, ADR 0068 — decision 9, answers 26, 27 and 32 of the review of its SPEC).

What M13.14 adds, each red before its code:

- **ELA's home**, one function — :func:`ela.domain.ela_home` — that the four defaults which wrote
  ``~/.ela`` by themselves read, and that the list names whatever they say;
- the places of the list that had no test on the Core: **the database, the ``.env`` read, the
  source tree**; and the new ones: **ELA's home, the Python ELA runs on — ``sys.prefix`` and
  ``sys.base_prefix`` —, the program of the vault**, each stopping ELA with its own name;
- **where a place is, is asked of the volume**: a root written with other capitals than ``~/.ela``
  passed on a Mac, which ignores the case of a name (the defect 6 of the SPEC);
- ``ELA_BROWSER_SITES`` with a name that ends in ``.localhost``, which the pattern admits and a
  browser sends to this machine, stops the start-up.

Every place is injected: a test never names one of the machine it runs on.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

import ela
from ela import domain
from ela.composition import Ela, Settings
from ela.composition import settings as composition_settings
from ela.composition.settings import (
    ELA_S_HOME,
    PYTHON_ENVIRONMENT,
    PYTHON_INSTALLATION,
    VAULT_PROGRAM_PLACE,
    VAULT_PROGRAM_TARGET,
    NodeSettings,
)
from ela.domain import ela_home
from ela.infrastructure.persistence import settings as persistence_settings
from ela.permissions import BROWSER_DOWNLOAD, BROWSER_DOWNLOAD_AS_YOU
from ela.tools import FS_WRITE
from ela.tools import paths as paths_module
from ela.tools import settings as tools_settings
from tests.composition.support import database_url, declare
from tests.composition.test_account_settings import IGNORES_CASE, ONE_SPELLING

SRC = Path(ela.__file__).resolve().parent
TOUCH = "contain one another"


def refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **extra: str) -> str:
    from ela.composition import ConfigurationError

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


# ----------------------------------------------------------------------------------------
# ELA's home: one definition
# ----------------------------------------------------------------------------------------


def test_ela_s_home_is_the_user_s_home_read_at_the_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    assert ela_home() == tmp_path / ".ela"
    assert not (tmp_path / ".ela").exists(), "a path, never a folder made"


def test_the_four_defaults_go_through_ela_s_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The workspace, the captures, the database and the node's secret: each default reads the
    one function, and a home moved there moves all four."""
    house = tmp_path / "house"
    for module in (tools_settings, persistence_settings, composition_settings):
        monkeypatch.setattr(module, "ela_home", lambda: house)

    assert tools_settings.default_workspace_dir() == house / "workspace"
    assert tools_settings.default_capture_dir() == house / "captures"
    assert persistence_settings.default_db_url() == f"sqlite:///{(house / 'ela.db').as_posix()}"
    assert NodeSettings(_env_file=None).node_state_dir == house


def test_each_of_them_takes_it_from_the_domain_and_nobody_writes_the_home_by_itself() -> None:
    """One definition: the three modules hold the domain's function, and no other module of ELA
    spells ``.ela`` — a fifth default written by hand would be the second answer to «where»."""
    for module in (tools_settings, persistence_settings, composition_settings):
        assert module.ela_home is domain.ela_home
    spelled = re.compile(r"""["']\.ela["'/]""")
    writers = sorted(
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if spelled.search(path.read_text(encoding="utf-8"))
    )

    assert writers == ["domain.py"]


# ----------------------------------------------------------------------------------------
# A root that touches one of the places stops ELA, each with its name
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("where", "what"),
    [
        ("the database", "the database"),
        ("the .env", "the .env ELA read"),
        ("the source tree", "ELA's own source tree"),
        ("the home, held", ELA_S_HOME),
        ("the home, around", ELA_S_HOME),
        ("sys.prefix", PYTHON_ENVIRONMENT),
        ("sys.base_prefix", PYTHON_INSTALLATION),
        ("the vault's program", VAULT_PROGRAM_PLACE),
    ],
)
def test_a_root_that_touches_what_ela_uses_to_exist_stops_ela_with_its_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, where: str, what: str
) -> None:
    """The places of the Core that had no test (the database, the ``.env``, the source tree) and
    the ones M13.14 adds: the root holds them, or — for the home — lies inside it."""
    chosen = tmp_path / "chosen"
    extra: dict[str, str] = {}
    if where == "the database":
        extra["ELA_DB_URL"] = database_url(a_folder(chosen))
    elif where == "the .env":
        a_folder(chosen)
        (chosen / ".env").write_text("", encoding="utf-8")
        monkeypatch.chdir(chosen)
    elif where == "the source tree":
        installed = a_folder(chosen, "site-packages", "ela")
        monkeypatch.setattr(ela, "__file__", str(installed / "__init__.py"))
    elif where.startswith("the home"):
        # The node's secret elsewhere, as a .env may put it: the home is a place of its own.
        extra["ELA_NODE_STATE_DIR"] = str(tmp_path / "state")
        monkeypatch.setattr(composition_settings, "ela_home", lambda: chosen / ".ela")
        if where.endswith("around"):
            chosen = a_folder(chosen, ".ela", "files")
    elif where.startswith("sys."):
        monkeypatch.setattr(sys, where.removeprefix("sys."), str(a_folder(chosen, "python")))
    else:
        extra["ELA_VAULT_PROGRAM"] = str(chosen / "bin" / "bw")
    a_folder(chosen)

    message = refused(monkeypatch, tmp_path, ELA_FS_ROOT=str(chosen), **extra)

    assert "ELA_FS_ROOT" in message and TOUCH in message
    assert what in message


def test_the_program_of_the_vault_is_two_places_when_its_name_is_a_link(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The name it is written with, and the file it leads to: a root that holds either one could
    change what ELA hands the vault's key to."""
    cellar = a_folder(tmp_path, "cellar")
    (cellar / "bw").write_text("", encoding="utf-8")
    a_folder(tmp_path, "bin")
    (tmp_path / "bin" / "bw").symlink_to(cellar / "bw")
    program = {"ELA_VAULT_PROGRAM": str(tmp_path / "bin" / "bw")}

    own = loaded(monkeypatch, tmp_path, **program).ela_s_own()
    around_the_name = refused(monkeypatch, tmp_path, ELA_FS_ROOT=str(tmp_path / "bin"), **program)
    around_the_file = refused(monkeypatch, tmp_path, ELA_FS_ROOT=str(cellar), **program)

    assert own[VAULT_PROGRAM_PLACE] == (tmp_path / "bin").resolve() / "bw"
    assert own[VAULT_PROGRAM_TARGET] == (cellar / "bw").resolve()
    assert VAULT_PROGRAM_PLACE in around_the_name
    assert VAULT_PROGRAM_TARGET in around_the_file


def test_the_list_of_the_core_names_every_place_and_the_program_only_when_declared(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Public since M13.14: the composition hands it to the tools that write. Without a vault,
    no place of the vault; a program that is no link is one place."""
    without = loaded(monkeypatch, tmp_path).ela_s_own()
    plain = loaded(monkeypatch, tmp_path, ELA_VAULT_PROGRAM=str(tmp_path / "bw")).ela_s_own()

    assert {
        "the workspace",
        "the capture store",
        "the audio ELA sweeps at start-up",
        "the folder a node keeps its secret in",
        ELA_S_HOME,
        PYTHON_ENVIRONMENT,
        PYTHON_INSTALLATION,
        "the database",
        "ELA's own source tree",
    } <= set(without)
    assert VAULT_PROGRAM_PLACE not in without and VAULT_PROGRAM_TARGET not in without
    assert plain[VAULT_PROGRAM_PLACE] == tmp_path.resolve() / "bw"
    assert VAULT_PROGRAM_TARGET not in plain
    assert without[PYTHON_ENVIRONMENT] == Path(sys.prefix).resolve()
    assert without[PYTHON_INSTALLATION] == Path(sys.base_prefix).resolve()
    assert without[ELA_S_HOME] == ela_home().absolute().resolve()


# ----------------------------------------------------------------------------------------
# Where a place is, is asked of the volume (the defect 6 of the SPEC)
# ----------------------------------------------------------------------------------------


@pytest.mark.skipif(not IGNORES_CASE, reason=ONE_SPELLING)
def test_a_root_spelt_with_other_capitals_inside_ela_s_home_stops_ela(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """On the volume of a Mac ``.ELA/files`` is ``.ela/files``, and resolving the path leaves the
    spelling as it was written: until M13.14 the comparison of spellings let this root through."""
    a_folder(tmp_path, "house", ".ela", "files")
    monkeypatch.setattr(composition_settings, "ela_home", lambda: tmp_path / "house" / ".ela")

    message = refused(
        monkeypatch,
        tmp_path,
        ELA_FS_ROOT=str(tmp_path / "house" / ".ELA" / "files"),
        ELA_NODE_STATE_DIR=str(tmp_path / "state"),
    )

    assert TOUCH in message and ELA_S_HOME in message


def test_what_the_volume_says_of_two_spellings_is_believed_for_the_root_on_every_system(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The same refusal with **the volume's answer handed by the test**, so the line that
    believes the volume runs on a volume that tells the cases apart too — the runner's."""
    a_folder(tmp_path, "house", ".ela")
    root = a_folder(tmp_path, "house", ".ELA", "files")
    monkeypatch.setattr(composition_settings, "ela_home", lambda: tmp_path / "house" / ".ela")
    monkeypatch.setattr(
        paths_module, "same_folder", lambda one, other: str(one).casefold() == str(other).casefold()
    )

    message = refused(
        monkeypatch, tmp_path, ELA_FS_ROOT=str(root), ELA_NODE_STATE_DIR=str(tmp_path / "state")
    )

    assert TOUCH in message and ELA_S_HOME in message


def test_a_root_beside_ela_s_home_is_accepted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The positive case: a folder whose name only begins like the home is another place."""
    a_folder(tmp_path, "house", ".ela")
    beside = a_folder(tmp_path, "house", ".elas-files")
    monkeypatch.setattr(composition_settings, "ela_home", lambda: tmp_path / "house" / ".ela")

    assert loaded(monkeypatch, tmp_path, ELA_FS_ROOT=str(beside)).filesystem.root == beside


# ----------------------------------------------------------------------------------------
# A site that is this machine (answer 26)
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("site", ["ela.localhost", "a.b.localhost"])
def test_a_site_that_ends_in_localhost_stops_ela(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, site: str
) -> None:
    message = refused(monkeypatch, tmp_path, ELA_BROWSER_SITES=f'["example.com", "{site}"]')

    assert "ELA_BROWSER_SITES" in message
    assert f"'{site}' ends in .localhost" in message


def test_a_site_whose_name_only_holds_localhost_is_a_site(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sites = '["localhost.example.com", "example.localhost.com"]'

    assert loaded(monkeypatch, tmp_path, ELA_BROWSER_SITES=sites).browser.sites == (
        "localhost.example.com",
        "example.localhost.com",
    )


# ----------------------------------------------------------------------------------------
# The list reaches the tools that write
# ----------------------------------------------------------------------------------------


async def test_the_tools_that_write_under_the_root_are_handed_the_list_of_the_core(
    ela: Ela, settings: Settings
) -> None:
    """``fs.write`` and the two downloads: the list the root was checked against at the start-up,
    and no write of ELA's reaches it — under a yes or under a policy."""
    own = settings.ela_s_own()

    for capability in (FS_WRITE, BROWSER_DOWNLOAD, BROWSER_DOWNLOAD_AS_YOU):
        assert dict(ela.tools.get(capability).protected) == own, capability  # type: ignore[attr-defined]
