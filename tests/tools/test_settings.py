"""``WorkspaceSettings`` (ADR 0013 §12): one variable, a sensible default, nothing at import."""

from __future__ import annotations

from pathlib import Path

import pytest

from ela.tools import WorkspaceSettings, default_workspace_dir


def test_default_is_a_folder_under_the_home_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ELA_WORKSPACE_DIR", raising=False)
    settings = WorkspaceSettings(_env_file=None)
    assert settings.workspace_dir == Path.home() / ".ela" / "workspace" == default_workspace_dir()
    assert settings.workspace_dir.is_absolute()


def test_default_follows_the_home_at_call_time(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert default_workspace_dir() == tmp_path / ".ela" / "workspace"


def test_environment_overrides_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ELA_WORKSPACE_DIR", "/elsewhere/workspace")
    assert WorkspaceSettings(_env_file=None).workspace_dir == Path("/elsewhere/workspace")


def test_unknown_variables_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ELA_SOMETHING_ELSE", "1")
    WorkspaceSettings(_env_file=None)


def test_dotenv_file_is_read_when_asked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ELA_WORKSPACE_DIR", raising=False)
    dotenv = tmp_path / ".env"
    workspace = "/tmp/ela-test-workspace"
    dotenv.write_text(f"ELA_WORKSPACE_DIR={workspace}\n", encoding="utf-8")
    assert WorkspaceSettings(_env_file=dotenv).workspace_dir == Path(workspace)
