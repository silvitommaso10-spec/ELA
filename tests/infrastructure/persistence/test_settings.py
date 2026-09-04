"""``PersistenceSettings`` (ADR 0006 §3): one variable, a sensible default, nothing at import."""

from __future__ import annotations

from pathlib import Path

import pytest

from ela.infrastructure.persistence import PersistenceSettings, default_db_url


def test_default_is_a_file_under_the_home_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ELA_DB_URL", raising=False)
    settings = PersistenceSettings(_env_file=None)
    expected = f"sqlite:///{(Path.home() / '.ela' / 'ela.db').as_posix()}"
    assert settings.db_url == expected == default_db_url()
    assert Path(settings.db_url.removeprefix("sqlite:///")).is_absolute()


def test_default_follows_the_home_at_call_time(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert default_db_url() == f"sqlite:///{(tmp_path / '.ela' / 'ela.db').as_posix()}"


def test_environment_overrides_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ELA_DB_URL", "sqlite:///elsewhere.db")
    assert PersistenceSettings(_env_file=None).db_url == "sqlite:///elsewhere.db"


def test_unknown_variables_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ELA_SOMETHING_ELSE", "1")
    PersistenceSettings(_env_file=None)


def test_dotenv_file_is_read_when_asked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ELA_DB_URL", raising=False)
    dotenv = tmp_path / ".env"
    dotenv.write_text("ELA_DB_URL=sqlite:///from-dotenv.db\n", encoding="utf-8")
    assert PersistenceSettings(_env_file=dotenv).db_url == "sqlite:///from-dotenv.db"
