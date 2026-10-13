"""``ELA_BROWSER_PROFILE_DIR`` and ``ELA_VAULT_PROGRAM``: the two lines of the browser with the
user's accounts, and only the Core's (M13.9, ADR 0063; decisions 16d and 35).

**Both are optional and neither has a default**: ELA does not invent a place for credentials, nor
a program to hand a key to. Without them ELA starts the same — the capabilities are there and every
call of them says, before the question, which line to write.

**What stops the start-up** is a line ELA cannot honour. A profile folder that is not written as an
absolute path, that is a link, that sits — resolved — inside ELA's own source tree or inside one of
the two folders macOS copies elsewhere, or that holds or sits inside what ``fs.read`` may read, the
workspace or the capture store. A vault program that is not an absolute path: ELA never looks one
up in the ``PATH``.

**The settings create nothing**: the folder is made the first time its adapter looks at it — a use
of the browser, or a look at who holds it —, and a program that is not there is said then, with
its own code.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

import ela
from ela.composition import ConfigurationError, NodeConfig, Settings
from ela.composition.settings import AccountSettings
from ela.testing.fakes import FakeClock
from ela.tools.vault import UNDECLARED, VaultDoor, VaultProblem
from tests.composition.support import CAPTURES, FS_ROOT, WORKSPACE, declare

PROFILE = "ELA_BROWSER_PROFILE_DIR"
PROGRAM = "ELA_VAULT_PROGRAM"
STATE = "ELA_NODE_STATE_DIR"


def _ignores_case() -> bool:
    """Whether the volume these tests build their folders on holds one folder under two
    spellings: asked of the volume, by making a folder and looking for it in capitals."""
    with tempfile.TemporaryDirectory() as made:
        (Path(made) / "a-name").mkdir()
        return (Path(made) / "A-NAME").is_dir()


IGNORES_CASE = _ignores_case()
ONE_SPELLING = "this volume tells the cases of a name apart: a folder has one spelling on it"


def loaded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **extra: str) -> Settings:
    declare(monkeypatch, tmp_path, **extra)
    return Settings.load()


def refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **extra: str) -> str:
    declare(monkeypatch, tmp_path, **extra)
    with pytest.raises(ConfigurationError) as raised:
        Settings.load()
    return str(raised.value)


@pytest.fixture
def home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A home that is not the one of whoever runs the suite: the two folders macOS copies
    elsewhere are asked of it when the settings are read, not when the module was imported."""
    place = tmp_path / "home"
    place.mkdir()
    monkeypatch.setenv("HOME", str(place))
    return place


# ----------------------------------------------------------------------------------------
# The section
# ----------------------------------------------------------------------------------------


def test_the_two_lines_are_the_section_s_and_nothing_else_is() -> None:
    prefix = AccountSettings.model_config.get("env_prefix", "")
    named = {f"{prefix}{field}".upper() for field in AccountSettings.model_fields}

    assert named == {PROFILE, PROGRAM}


def test_without_the_two_lines_ela_starts_and_has_neither(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    accounts = loaded(monkeypatch, tmp_path).accounts

    assert accounts.browser_profile_dir is None
    assert accounts.vault_program is None


def test_an_empty_line_is_a_line_nobody_wrote(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """As ``ELA_SPENDING_CAP_USD=`` is no cap: the lines of ``.env.example``, left blank."""
    accounts = loaded(monkeypatch, tmp_path, **{PROFILE: "", PROGRAM: ""}).accounts

    assert accounts.browser_profile_dir is None
    assert accounts.vault_program is None


def test_the_two_lines_are_read_from_the_env_file_as_the_guide_writes_them(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    declare(monkeypatch, tmp_path)
    profile, program = tmp_path / "state" / "browser-profile", tmp_path / "state" / "bin" / "bw"
    (tmp_path / ".env").write_text(f"{PROFILE}={profile}\n{PROGRAM}={program}\n", encoding="utf-8")

    accounts = Settings.load().accounts

    assert accounts.browser_profile_dir == profile
    assert accounts.vault_program == str(program)


def test_a_node_reads_neither(monkeypatch: pytest.MonkeyPatch) -> None:
    """The profile and the vault are the Core's: a node is not asked for them, and a line of
    theirs that the Core would refuse does not stop ``ela node run``."""
    assert "accounts" not in NodeConfig.model_fields
    assert all(
        not set(AccountSettings.model_fields) & set(section.annotation.model_fields)  # type: ignore[union-attr]
        for section in NodeConfig.model_fields.values()
    )

    monkeypatch.setenv(PROFILE, "not/absolute")
    monkeypatch.setenv(PROGRAM, "bw")

    assert NodeConfig.load() is not None


# ----------------------------------------------------------------------------------------
# The folder of the profile (decision 35)
# ----------------------------------------------------------------------------------------


def test_a_declared_folder_is_read_and_not_created(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The place the guide proposes — beside the node's secret — is accepted, and reading the
    settings makes nothing: the folder is created, ``0700``, the first time its adapter looks at
    it."""
    profile = tmp_path / "state" / "browser-profile"

    settings = loaded(monkeypatch, tmp_path, **{PROFILE: str(profile), STATE: str(profile.parent)})

    assert settings.accounts.browser_profile_dir == profile
    assert not profile.exists() and not profile.parent.exists()


def test_a_folder_that_is_already_there_is_accepted_as_it_is(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Whether it is narrow enough and the user's own is asked when it is used, with its own code
    (``browser.profile_unsafe``): the settings do not look, and do not narrow it."""
    profile = tmp_path / "profile"
    profile.mkdir()
    profile.chmod(0o755)  # set, and not left to the umask of whoever runs the suite

    assert loaded(monkeypatch, tmp_path, **{PROFILE: str(profile)}).accounts.browser_profile_dir
    assert profile.stat().st_mode & 0o777 == 0o755


@pytest.mark.parametrize(
    "written", ["browser-profile", "./browser-profile", "~/.ela/browser-profile", "ela/profile"]
)
def test_a_folder_that_is_not_an_absolute_path_stops_the_start_up(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, written: str
) -> None:
    message = refused(monkeypatch, tmp_path, **{PROFILE: written})

    assert PROFILE in message
    assert "absolute path" in message
    assert not (tmp_path / written).exists()


def test_a_folder_that_is_a_link_stops_the_start_up_and_says_which_link(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    real = tmp_path / "vera"
    real.mkdir()
    link = tmp_path / "collegata"
    link.symlink_to(real)

    message = refused(monkeypatch, tmp_path, **{PROFILE: str(link)})

    assert PROFILE in message
    assert "symbolic link" in message and str(real) in message


@pytest.mark.parametrize("how", ["inside", "is"])
def test_a_folder_inside_ela_s_own_source_tree_stops_the_start_up(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, how: str
) -> None:
    """A checkout is something git reads, an editor indexes and a backup copies: cookies do not
    live there. The tree is asked of the module, as for ``ELA_FS_ROOT``."""
    installed = tmp_path / "site-packages" / "ela"
    installed.mkdir(parents=True)
    monkeypatch.setattr(ela, "__file__", str(installed / "__init__.py"))
    profile = {"inside": installed.parent / "profile", "is": installed.parent}[how]

    message = refused(monkeypatch, tmp_path, **{PROFILE: str(profile)})

    assert PROFILE in message
    assert "ELA's own source tree" in message


def test_the_checkout_this_suite_runs_from_is_refused_too(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The same refusal on the real tree, without a module moved by the test."""
    checkout = Path(ela.__file__).resolve().parent.parent.parent
    inside = checkout / ".browser-profile-of-a-test"

    message = refused(monkeypatch, tmp_path, **{PROFILE: str(inside)})

    assert "ELA's own source tree" in message
    assert not inside.exists()


@pytest.mark.parametrize("copied", ["Mobile Documents", "CloudStorage"])
@pytest.mark.parametrize("how", ["inside", "is"])
def test_a_folder_macos_copies_elsewhere_stops_the_start_up(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, home: Path, copied: str, how: str
) -> None:
    """iCloud Drive and the providers of File Provider: what is under them leaves the machine."""
    place = home / "Library" / copied
    profile = {"inside": place / "ela" / "profile", "is": place}[how]

    message = refused(monkeypatch, tmp_path, **{PROFILE: str(profile)})

    assert PROFILE in message
    assert f"Library/{copied}" in message
    assert "leaves this machine" in message


def test_a_folder_beside_the_two_that_are_copied_is_accepted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, home: Path
) -> None:
    """The positive case of the refusal above: ``~/Library`` is not copied, two folders in it
    are."""
    beside = home / "Library" / "Application Support" / "ela-profile"

    assert loaded(monkeypatch, tmp_path, **{PROFILE: str(beside)}).accounts.browser_profile_dir


@pytest.mark.skipif(not IGNORES_CASE, reason=ONE_SPELLING)
@pytest.mark.parametrize("where", ["the-tree", "copied-elsewhere", "the-captures", "the-workspace"])
def test_a_folder_written_in_another_case_is_where_it_is_and_not_where_it_is_spelled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, home: Path, where: str
) -> None:
    """The volume of a Mac ignores the case of a name, and resolving a path leaves its spelling as
    it was written: a profile typed in lower case inside ELA's own tree, a folder that leaves the
    machine or one of ELA's stores **is inside it**, whatever the comparison of two spellings
    says. Where a folder is, is asked of the volume."""
    extra: dict[str, str] = {}
    if where == "the-tree":
        installed = tmp_path / "Site-Packages" / "ela"
        installed.mkdir(parents=True)
        monkeypatch.setattr(ela, "__file__", str(installed / "__init__.py"))
        profile, expected = tmp_path / "site-packages" / "profile", "ELA's own source tree"
    elif where == "copied-elsewhere":
        (home / "Library" / "Mobile Documents").mkdir(parents=True)
        profile = home / "library" / "mobile documents" / "ela" / "profile"
        expected = "leaves this machine"
    else:
        which = {"the-captures": CAPTURES, "the-workspace": WORKSPACE}[where]
        store = tmp_path / "Stores" / "Theirs"
        store.mkdir(parents=True)
        extra[which] = str(store)
        profile, expected = tmp_path / "stores" / "theirs" / "profile", "contain one another"

    message = refused(monkeypatch, tmp_path, **extra, **{PROFILE: str(profile)})

    assert PROFILE in message and expected in message


def test_what_the_volume_says_of_two_spellings_is_believed_on_every_system(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The same refusal with **the volume's answer handed by the test**: on a volume that tells
    the cases of a name apart — the runner's — the test above has nothing to confuse and does not
    run, and the line that believes the volume would be one no test of that system reaches (the
    CI of 2026-10-11, where the gate of the coverage said so)."""
    from ela.composition import settings as module

    installed = tmp_path / "Site-Packages" / "ela"
    installed.mkdir(parents=True)
    monkeypatch.setattr(ela, "__file__", str(installed / "__init__.py"))
    monkeypatch.setattr(
        module, "_same_folder", lambda one, other: str(one).casefold() == str(other).casefold()
    )

    message = refused(
        monkeypatch, tmp_path, **{PROFILE: str(tmp_path / "site-packages" / "profile")}
    )

    assert PROFILE in message and "ELA's own source tree" in message


def test_two_paths_are_one_folder_when_the_volume_says_so_and_never_when_one_names_nothing(
    tmp_path: Path,
) -> None:
    from ela.composition.settings import _same_folder

    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "link").symlink_to(real)

    assert _same_folder(real, tmp_path / "link") is True, "one folder, reached two ways"
    assert _same_folder(real, tmp_path) is False
    assert _same_folder(tmp_path / "nothing", real) is False
    assert _same_folder(real, tmp_path / "nothing") is False


def test_on_a_mac_the_two_spellings_are_one_folder_and_the_test_above_ran() -> None:
    """A skip on the system a test covers turns the suite red: the browser with the profile runs
    on the Mac, whose volume ignores case, and there the test of the two spellings on the real
    volume is not one a count of skips may hide."""
    assert sys.platform != "darwin" or IGNORES_CASE, ONE_SPELLING


def test_where_the_folder_is_is_asked_of_the_path_resolved(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, home: Path
) -> None:
    """A folder reached **through** a link is where the link leads: the path as written is beside
    everything, and what it names is inside a folder that leaves the machine."""
    copied = home / "Library" / "CloudStorage" / "provider"
    copied.mkdir(parents=True)
    door = tmp_path / "porta"
    door.symlink_to(copied)

    message = refused(monkeypatch, tmp_path, **{PROFILE: str(door / "profile")})

    assert PROFILE in message
    assert "Library/CloudStorage" in message


def test_a_home_that_is_reached_through_a_link_is_where_the_link_leads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, home: Path
) -> None:
    """The other side of the same comparison: the two folders are resolved too. A home that is
    a link — a home on another volume — does not make its copied folders invisible to a profile
    written with the path they really have."""
    door = tmp_path / "casa"
    door.symlink_to(home)
    monkeypatch.setenv("HOME", str(door))

    message = refused(
        monkeypatch, tmp_path, **{PROFILE: str(home / "Library" / "Mobile Documents" / "profile")}
    )

    assert "Library/Mobile Documents" in message


@pytest.mark.parametrize("which", [WORKSPACE, CAPTURES], ids=["workspace", "captures"])
@pytest.mark.parametrize("how", ["inside", "holds", "is"])
def test_a_folder_that_touches_the_workspace_or_the_captures_stops_the_start_up(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, which: str, how: str
) -> None:
    """The workspace is what §23 calls synchronised, and the capture store is swept by ELA: the
    profile neither sits in one of them nor holds one."""
    theirs = tmp_path / "a" / "theirs"
    profile = {"inside": theirs / "profile", "holds": theirs.parent, "is": theirs}[how]

    message = refused(monkeypatch, tmp_path, **{which: str(theirs), PROFILE: str(profile)})

    assert PROFILE in message
    assert "contain one another" in message
    assert {WORKSPACE: "the workspace", CAPTURES: "the capture store"}[which] in message


@pytest.mark.parametrize("how", ["inside", "holds", "is"])
def test_a_folder_that_touches_the_root_fs_read_may_read_stops_the_start_up(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, how: str
) -> None:
    """``fs.read`` is ``MEDIUM`` over ``ELA_FS_ROOT``, and would read the cookies: the profile is
    among what ELA uses to exist, so the root's own refusal names it."""
    root = tmp_path / "b" / "files"
    root.mkdir(parents=True)
    profile = {"inside": root / "profile", "holds": root.parent, "is": root}[how]

    message = refused(monkeypatch, tmp_path, **{FS_ROOT: str(root), PROFILE: str(profile)})

    assert "ELA_FS_ROOT" in message and PROFILE in message
    assert "contain one another" in message


def test_the_profile_is_among_what_ela_uses_to_exist_only_when_it_is_declared(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    profile = tmp_path / "profile"

    without = loaded(monkeypatch, tmp_path)._ela_s_own()
    declared = loaded(monkeypatch, tmp_path, **{PROFILE: str(profile)})._ela_s_own()

    assert profile.resolve() not in without.values()
    assert set(declared) - set(without) == {f"the profile of ELA's browser ({PROFILE})"}
    assert profile.resolve() in declared.values()


# ----------------------------------------------------------------------------------------
# The program of the vault (decision 16d)
# ----------------------------------------------------------------------------------------


def test_a_declared_program_is_read_as_it_was_written_and_nothing_is_looked_at(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A program that is not there does not stop ELA: every ``browser.login`` says so before the
    question, with ``vault.no_program``. The identity is fixed by the tools, not here."""
    absent = tmp_path / "bin" / "bw"

    settings = loaded(monkeypatch, tmp_path, **{PROGRAM: str(absent)})

    assert settings.accounts.vault_program == str(absent)
    assert not absent.parent.exists()


@pytest.mark.parametrize("written", ["bw", "./bw", "bin/bw", "~/.ela/bin/bw"])
def test_a_program_that_is_not_an_absolute_path_stops_the_start_up(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, written: str
) -> None:
    """Never looked up in the ``PATH``: a bare name is the first ``bw`` somebody else put there."""
    message = refused(monkeypatch, tmp_path, **{PROGRAM: written})

    assert PROGRAM in message
    assert "absolute path" in message
    assert "PATH" in message


async def test_the_variable_is_the_one_the_door_names_when_nobody_wrote_it() -> None:
    """One name: the line the settings read is the line ``vault.undeclared`` tells to write."""
    door = await VaultDoor.fixed(None, None, clock=FakeClock())

    problem = await door.find("example.com")

    assert isinstance(problem, VaultProblem) and problem.code == UNDECLARED
    assert PROGRAM in problem.message


def test_two_lines_that_are_both_wrong_are_said_together(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Every section is read before anything is refused (M13.2), and so is every line of one."""
    message = refused(monkeypatch, tmp_path, **{PROFILE: "profile", PROGRAM: "bw"})

    assert PROFILE in message and PROGRAM in message
