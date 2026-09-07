"""Starting ELA (ADR 0023 §7, §16): ``python -m ela.api``.

The address is not a command-line argument, so this is where the settings and the socket meet.
No socket is opened here: what is under test is that ``serve`` hands uvicorn what the settings
say, and that a configuration ELA cannot use is a sentence on stderr rather than a traceback.
"""

from __future__ import annotations

import asyncio
import runpy
from typing import Any

import pytest

from ela.api import server
from ela.composition import Settings
from tests.composition.support import create_schema


class Uvicorn:
    """Enough of uvicorn to record what it was asked for, and to answer ``serve``."""

    def __init__(self) -> None:
        self.host: str | None = None
        self.port: int | None = None
        self.app: Any = None
        self.served = False

    def Config(self, app: Any, *, host: str, port: int, log_level: str) -> Uvicorn:  # noqa: N802
        self.app, self.host, self.port = app, host, port
        return self

    def Server(self, config: Uvicorn) -> Uvicorn:  # noqa: N802
        return config

    async def serve(self) -> None:
        self.served = True


def test_serve_binds_what_the_settings_say(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    asyncio.run(create_schema(settings.persistence.db_url))
    uvicorn = Uvicorn()
    monkeypatch.setattr(server, "uvicorn", uvicorn)

    server.serve(settings)

    assert uvicorn.host == settings.api.api_host == "127.0.0.1"
    assert uvicorn.port == settings.api.api_port
    assert uvicorn.served
    assert uvicorn.app is not None  # the application ELA serves


def test_main_returns_zero_when_the_server_stops(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    asyncio.run(create_schema(settings.persistence.db_url))
    monkeypatch.setattr(server, "uvicorn", Uvicorn())

    assert server.main() == 0


def test_main_says_what_is_wrong_and_does_not_start(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No ``ELA_API_TOKEN`` on this machine: ELA does not open an unauthenticated API."""
    monkeypatch.setattr(server, "uvicorn", Uvicorn())

    code = server.main()

    assert code == 2
    error = capsys.readouterr().err
    assert "ELA_API_TOKEN" in error
    assert "Traceback" not in error


def test_main_reports_a_configuration_that_only_build_can_see(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The database nobody migrated is found by ``build``, after ``Settings.load`` was happy."""
    monkeypatch.setattr(server, "uvicorn", Uvicorn())

    assert server.main() == 2
    assert "alembic upgrade head" in capsys.readouterr().err


def test_python_m_ela_api_runs_main(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "main", lambda: 7)

    with pytest.raises(SystemExit) as raised:
        runpy.run_module("ela.api.__main__", run_name="__main__")

    assert raised.value.code == 7
