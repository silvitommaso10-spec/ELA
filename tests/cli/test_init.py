"""``ela init``: the one command that writes on this machine, and what it refuses to write."""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path

import pytest

from ela.cli import setup
from ela.cli.errors import CONFIGURATION
from ela.cli.setup import ENV_FILE, TOKEN_VARIABLE, VARIABLES, assigned, template
from ela.composition import MIN_TOKEN_LENGTH, ApiSettings, ConfigurationError, Settings
from tests.cli.support import Cli, plain


def env_file(tmp_path: Path) -> Path:
    return tmp_path / ENV_FILE


def required() -> list[str]:
    """What ``ela init`` calls required: no default, and ELA does not start without them."""
    return [name for name, _ in setup.REQUIRED]


def required_lines(value: str = "x") -> str:
    return "".join(f"{name}={value}\n" for name in required())


async def test_it_writes_an_env_with_a_token_of_its_own(cli: Cli, tmp_path: Path) -> None:
    result = await cli("init")

    written = env_file(tmp_path).read_text(encoding="utf-8")
    token = re.search(rf"^{TOKEN_VARIABLE}=(\S+)$", written, re.MULTILINE)
    assert result.exit_code == 0
    assert token is not None
    assert len(token.group(1)) >= MIN_TOKEN_LENGTH


async def test_the_token_it_generates_is_never_printed(cli: Cli, tmp_path: Path) -> None:
    """A secret echoed to a terminal is a secret in the scrollback and in the history."""
    result = await cli("init")

    token = assigned_token(env_file(tmp_path))
    assert token not in result.stdout
    assert token not in plain(result.stderr)
    assert "read it from the file" in result.stdout


def assigned_token(path: Path) -> str:
    found = re.search(rf"^{TOKEN_VARIABLE}=(\S+)$", path.read_text(encoding="utf-8"), re.MULTILINE)
    assert found is not None
    return found.group(1)


async def test_the_file_is_readable_by_nobody_else(cli: Cli, tmp_path: Path) -> None:
    await cli("init")

    mode = stat.S_IMODE(os.stat(env_file(tmp_path)).st_mode)
    assert mode == 0o600


async def test_what_it_writes_is_a_configuration_ela_accepts(
    cli: Cli, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The end of the loop: what ``init`` writes is what ``ApiSettings`` reads.

    The environment of the test declares a token of its own, and an environment variable wins
    over the file: it goes, so that what is read is what ``init`` wrote.
    """
    await cli("init")
    monkeypatch.delenv(TOKEN_VARIABLE, raising=False)

    settings = ApiSettings(_env_file=str(env_file(tmp_path)))  # type: ignore[call-arg]

    assert settings.token == assigned_token(env_file(tmp_path))
    assert settings.api_host == "127.0.0.1"


async def test_it_never_overwrites_an_env_that_is_already_there(cli: Cli, tmp_path: Path) -> None:
    """Overwriting one is losing a token and leaving an ELA that does not restart (§33)."""
    env_file(tmp_path).write_text(
        f"{TOKEN_VARIABLE}=" + "k" * 40 + "\n" + required_lines(), encoding="utf-8"
    )

    result = await cli("init")

    assert result.exit_code == 0
    assert assigned_token(env_file(tmp_path)) == "k" * 40
    assert "left untouched" in result.stdout


async def test_it_says_which_variables_the_file_does_not_set(cli: Cli, tmp_path: Path) -> None:
    """The user's note on decision 6a: report what is missing, touch what is present."""
    env_file(tmp_path).write_text(
        f"{TOKEN_VARIABLE}=" + "k" * 40 + "\nELA_API_PORT=9000\n" + required_lines(),
        encoding="utf-8",
    )

    result = await cli("init")

    assert "ELA_API_PORT" not in result.stdout.partition("not set")[2]
    assert "ELA_API_HOST" in result.stdout
    assert "nothing required is missing" in result.stdout


async def test_an_env_without_a_token_is_a_configuration_failure(cli: Cli, tmp_path: Path) -> None:
    """ELA does not open an unauthenticated API, so an ``.env`` without a token is not usable."""
    env_file(tmp_path).write_text("ELA_API_PORT=9000\n", encoding="utf-8")

    result = await cli("init")

    assert result.exit_code == CONFIGURATION
    assert TOKEN_VARIABLE in plain(result.stderr)
    assert "token_urlsafe" in plain(result.stderr)


async def test_an_env_that_sets_everything_reports_nothing_missing(
    cli: Cli, tmp_path: Path
) -> None:
    lines = [f"{TOKEN_VARIABLE}=" + "k" * 40]
    lines.extend(f"{name}=x" for name in required())
    lines.extend(f"{name}={default or 'x'}" for name, default in VARIABLES)
    env_file(tmp_path).write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = await cli("init")

    assert "not set" not in result.stdout
    assert result.exit_code == 0


def test_a_commented_variable_is_not_set() -> None:
    """What the template writes is commented out: reading it back must find only the token."""
    assert assigned(template("t" * 43)) == {TOKEN_VARIABLE}


async def test_the_file_is_readable_by_nobody_else_not_even_for_an_instant(
    cli: Cli, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``0o600`` from its first byte, not ``0o600`` after a ``chmod`` (M12.1, criterio 16).

    Written with ``write_text`` and narrowed afterwards, the file carries the process umask for an
    instant — with ``umask(0)``, ``0o666``: readable by anybody, with the token already inside. The
    test widens the umask to make that instant visible, and records the file's mode at the moment
    anybody narrows it: a file born private is never narrowed at all, or is narrowed from ``0o600``.
    """
    seen: list[int] = []
    original = Path.chmod

    def spying(self: Path, mode: int, *args: object, **kwargs: object) -> None:
        seen.append(stat.S_IMODE(os.stat(self).st_mode))
        original(self, mode, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "chmod", spying)
    previous = os.umask(0)
    try:
        await cli("init")
    finally:
        os.umask(previous)

    assert all(mode == 0o600 for mode in seen), [oct(mode) for mode in seen]
    assert stat.S_IMODE(os.stat(env_file(tmp_path)).st_mode) == 0o600


# ----------------------------------------------------------------------------------------
# What ELA cannot start without (M13.1b, decision 4)
# ----------------------------------------------------------------------------------------
# Since M13.1 the token is not the only one: ELA_FS_ROOT and ELA_FS_SCOPE have no default and stop
# the start-up, and until M13.1b `ela init` called them optional and said «nothing required is
# missing» about an .env ELA would refuse.


async def test_the_env_it_writes_puts_the_required_lines_above_the_optional_ones(
    cli: Cli, tmp_path: Path
) -> None:
    await cli("init")

    written = env_file(tmp_path).read_text(encoding="utf-8")

    assert "only variable" not in written
    assert required(), "a list of what ELA cannot start without that is empty would say nothing"
    first_optional = written.index(f"# {VARIABLES[0][0]}=")
    for name in required():
        assert name not in {optional for optional, _ in VARIABLES}, f"{name} is not optional"
        assert -1 < written.find(f"# {name}=") < first_optional, name


async def test_its_message_names_the_required_lines_before_ela_serve(cli: Cli) -> None:
    result = await cli("init")

    serve = result.stdout.index("ela serve")
    for name in required():
        assert -1 < result.stdout.find(name) < serve, f"{name} must be written before ela serve"


async def test_an_env_without_the_required_lines_exits_2_and_names_them(
    cli: Cli, tmp_path: Path
) -> None:
    env_file(tmp_path).write_text(f"{TOKEN_VARIABLE}=" + "k" * 40 + "\n", encoding="utf-8")

    result = await cli("init")

    assert result.exit_code == CONFIGURATION
    defaults = result.stdout.partition("its own default")[2]
    for name in required():
        assert name in plain(result.stderr), name
        assert name not in defaults, f"{name} has no default: listing it there is the old lie"
    assert "nothing required is missing" not in result.stdout


async def test_what_it_writes_plus_the_required_lines_is_what_ela_starts_with(
    cli: Cli, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The loop the old test closed only for ``ApiSettings``, closed for ``Settings.load()``.

    Three conditions keep it from being empty (M13.1b). **The environment is emptied of every
    ``ELA_``**: the fixtures declared the two lines already, and with them in the environment an
    ``.env`` without them is accepted. **The values are the ones the fixtures declared**, read
    before emptying it — the commented example names a folder that does not exist, and a table of
    values here would be a second list written by hand. **The root is a subfolder** of the folder
    the ``.env`` is in: a root that contains the ``.env`` ELA reads is refused, rightly.

    The day a variable becomes required in the settings and not in ``REQUIRED``, the file with the
    required lines is refused, and this fails.
    """
    declared = {name: os.environ[name] for name in required()}
    await cli("init")
    for name in list(os.environ):
        if name.startswith("ELA_"):
            monkeypatch.delenv(name)
    env = env_file(tmp_path)
    written = env.read_text(encoding="utf-8")

    def with_lines(*names: str) -> None:
        env.write_text(written + "".join(f"{n}={declared[n]}\n" for n in names), encoding="utf-8")

    with pytest.raises(ConfigurationError) as refused:
        Settings.load()
    for name in required():
        assert name in str(refused.value)

    with_lines(*required())
    assert Settings.load().filesystem.root == Path(declared["ELA_FS_ROOT"])

    for missing in required():
        with_lines(*(name for name in required() if name != missing))
        with pytest.raises(ConfigurationError) as one:
            Settings.load()
        assert missing in str(one.value)
