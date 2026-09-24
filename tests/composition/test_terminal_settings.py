"""``ELA_TERMINAL_*``: the programs ELA may run, declared by the user, and nothing chosen for them.

Decision 16 of M13.2 (ADR 0047), with the answer to Domanda 3 given at the resumption. Without
``ELA_TERMINAL_PROGRAMS`` ELA does not start, and the message says the line to write and that
``[]`` is an admitted answer. At start-up only three things stop it, each named with the entry:
an entry the grammar does not admit (a leading slash, a ``..``), a folder — which would admit
everything in it —, a file that does not execute. **Nothing else**: not an entry inside ELA's own
tree or its ``.venv/bin`` — any interpreter admitted reaches the same things, and the defence is
the question at every use —, and not an entry that is not there, whose every call is refused
before the question.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from ela.composition import ConfigurationError, Settings
from tests.composition.support import declare

PROGRAMS = "ELA_TERMINAL_PROGRAMS"
TIMEOUT = "ELA_TERMINAL_TIMEOUT_SECONDS"
OUTPUT = "ELA_TERMINAL_OUTPUT_MAX_BYTES"


def load(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **extra: str) -> Settings:
    declare(monkeypatch, tmp_path, **extra)
    return Settings.load()


def refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **extra: str) -> str:
    with pytest.raises(ConfigurationError) as caught:
        load(monkeypatch, tmp_path, **extra)
    return str(caught.value)


def entry(path: Path | str) -> str:
    return str(path).lstrip("/")


def test_without_the_programs_ela_does_not_start_and_says_what_to_write(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    declare(monkeypatch, tmp_path)
    monkeypatch.delenv(PROGRAMS)

    with pytest.raises(ConfigurationError) as caught:
        Settings.load()

    message = str(caught.value)
    assert PROGRAMS in message
    assert f"{PROGRAMS}=[" in message, "the line to write, not only the name"
    assert "[]" in message, "and that no program at all is an answer"


def test_the_fixtures_declare_no_program_unless_a_test_asks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``declare`` writes ``[]``: a suite that launched programs by default would read the Mac."""
    assert load(monkeypatch, tmp_path).terminal.programs == ()


def test_the_programs_are_read_as_one_line_of_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = load(monkeypatch, tmp_path, **{PROGRAMS: '["bin/echo","usr/bin/env"]'})

    assert settings.terminal.programs == ("bin/echo", "usr/bin/env")


def test_the_line_is_read_from_the_env_file_as_the_guide_writes_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    declare(monkeypatch, tmp_path)
    monkeypatch.delenv(PROGRAMS)
    (tmp_path / ".env").write_text(f'{PROGRAMS}=["bin/echo","usr/bin/seq"]\n', encoding="utf-8")

    assert Settings.load().terminal.programs == ("bin/echo", "usr/bin/seq")


@pytest.mark.parametrize("written", ["/bin/echo", "usr/bin/../bin/echo", "bin//echo", "bin\\echo"])
def test_an_entry_the_grammar_does_not_admit_stops_ela_and_is_named(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, written: str
) -> None:
    message = refused(
        monkeypatch, tmp_path, **{PROGRAMS: f'["{written.replace(chr(92), chr(92) * 2)}"]'}
    )

    assert PROGRAMS in message
    assert repr(written) in message or written in message
    assert "relative to /" in message, "and it says how to write one"


def test_a_leading_slash_is_answered_with_the_entry_written_right(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    message = refused(monkeypatch, tmp_path, **{PROGRAMS: '["/bin/echo"]'})

    assert "'bin/echo'" in message


def test_a_folder_stops_ela_because_it_would_admit_everything_in_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    folder = tmp_path.resolve() / "programmi"
    folder.mkdir()

    message = refused(monkeypatch, tmp_path, **{PROGRAMS: f'["{entry(folder)}"]'})

    assert entry(folder) in message
    assert "folder" in message


def test_a_file_that_does_not_execute_stops_ela(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    text = tmp_path.resolve() / "nota.txt"
    text.write_text("x", encoding="utf-8")
    text.chmod(0o644)

    message = refused(monkeypatch, tmp_path, **{PROGRAMS: f'["{entry(text)}"]'})

    assert entry(text) in message
    assert "execut" in message


def test_the_python_of_ela_itself_is_not_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Domanda 3, decisa: no refusal of what ELA uses to exist — the tree, its ``.venv/bin``.

    Any interpreter admitted reaches the same things; a defence that shuts one door of many teaches
    that the others are safe. The defence is the question at every use (decision 2).
    """
    python = entry(Path(sys.executable).absolute())

    assert load(monkeypatch, tmp_path, **{PROGRAMS: f'["{python}"]'}).terminal.programs == (python,)


def test_an_entry_that_is_not_there_does_not_stop_ela(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Every call of it is refused before the question, with ``terminal.no_program``."""
    missing = entry(tmp_path.resolve() / "assente")

    assert load(monkeypatch, tmp_path, **{PROGRAMS: f'["{missing}"]'}).terminal.programs == (
        missing,
    )


def test_the_timeout_and_the_output_have_the_defaults_of_the_spec(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    terminal = load(monkeypatch, tmp_path).terminal

    assert terminal.timeout_seconds == 120
    assert terminal.output_max_bytes == 65536


@pytest.mark.parametrize(("name", "value"), [(TIMEOUT, "900"), (OUTPUT, "1048576")])
def test_a_ceiling_may_be_reached(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str, value: str
) -> None:
    load(monkeypatch, tmp_path, **{name: value})


@pytest.mark.parametrize(
    ("name", "value"), [(TIMEOUT, "901"), (TIMEOUT, "0"), (OUTPUT, "1048577"), (OUTPUT, "0")]
)
def test_past_a_ceiling_or_at_nothing_ela_does_not_start(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str, value: str
) -> None:
    assert name in refused(monkeypatch, tmp_path, **{name: value})
