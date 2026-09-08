"""The settings of the tools: the workspace (ADR 0013 §12) and the capture store (ADR 0029 §1).

One variable each, a sensible default, nothing computed at import — and, for the captures, a
ceiling on the retention and a floor under every other knob.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from ela.tools import CaptureSettings, WorkspaceSettings, default_workspace_dir
from ela.tools.settings import MAX_CAPTURE_TTL, default_capture_dir


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


# --------------------------------------------------------------------------------------
# CaptureSettings (M10.2, ADR 0029 §1, §14)
# --------------------------------------------------------------------------------------


def test_the_capture_store_is_a_sibling_of_the_database_and_not_of_the_notes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """ADR 0029 §1, a permanent constraint: the workspace is what §23 calls synchronised, and
    content in a folder something may one day sync leaves the machine without anybody deciding
    it."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    settings = CaptureSettings()

    assert settings.capture_dir == tmp_path / ".ela" / "captures"
    assert default_capture_dir() == tmp_path / ".ela" / "captures"
    assert not settings.capture_dir.is_relative_to(default_workspace_dir())


def test_the_defaults_are_the_ones_the_milestone_approved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ELA_CAPTURE_TTL_SECONDS", raising=False)
    settings = CaptureSettings()

    assert settings.capture_ttl == timedelta(seconds=300)
    assert settings.capture_max_count == 20
    assert settings.capture_max_bytes == 200 * 1024 * 1024
    assert settings.capture_timeout == timedelta(seconds=10)


def test_a_retention_above_the_ceiling_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """Past an hour a capture stops being a working file and becomes a record of what the user
    had on screen — the same shape as ``MAX_DECISION_TTL``, and for a related reason."""
    monkeypatch.setenv("ELA_CAPTURE_TTL_SECONDS", str(MAX_CAPTURE_TTL.total_seconds() + 1))

    with pytest.raises(ValidationError):
        CaptureSettings()


def test_the_ceiling_itself_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ELA_CAPTURE_TTL_SECONDS", str(int(MAX_CAPTURE_TTL.total_seconds())))

    assert CaptureSettings().capture_ttl == MAX_CAPTURE_TTL


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("ELA_CAPTURE_TTL_SECONDS", "0"),
        ("ELA_CAPTURE_MAX_COUNT", "0"),
        ("ELA_CAPTURE_MAX_BYTES", "0"),
        ("ELA_CAPTURE_TIMEOUT_SECONDS", "0"),
    ],
)
def test_a_knob_that_would_switch_the_feature_off_by_accident_is_refused(
    monkeypatch: pytest.MonkeyPatch, variable: str, value: str
) -> None:
    """Zero here is not "off", it is "every capture fails" — a knob that reads as a setting and
    behaves as a breakage. ``ELA_PERCEPTION_LOOP_INTERVAL_SECONDS`` accepts zero because there
    zero *means* off, and it is documented as such."""
    monkeypatch.setenv(variable, value)

    with pytest.raises(ValidationError):
        CaptureSettings()
