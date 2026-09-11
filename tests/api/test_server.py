"""Starting ELA (ADR 0023 §7, §16): ``python -m ela.api``.

The address is not a command-line argument, so this is where the settings and the socket meet.
No socket is opened here: what is under test is that ``serve`` hands uvicorn what the settings
say, and that a configuration ELA cannot use is a sentence on stderr rather than a traceback.
"""

from __future__ import annotations

import asyncio
import errno
import runpy
import socket
from collections.abc import (
    Iterator,
)
from typing import Any, cast

import pytest

from ela.api import server
from ela.composition import Settings
from ela.composition.settings import (
    ApiSettings,
)
from tests.composition.support import create_schema


class Uvicorn:
    """Enough of uvicorn to record what it was asked for, and to answer ``serve``."""

    def __init__(self) -> None:
        self.app: Any = None
        self.sockets: list[socket.socket] = []
        self.served = False

    def Config(self, app: Any, *, log_level: str) -> Uvicorn:  # noqa: N802
        self.app = app
        return self

    def Server(self, config: Uvicorn) -> Uvicorn:  # noqa: N802
        return config

    async def serve(self, sockets: list[socket.socket]) -> None:
        self.sockets = list(sockets)
        self.served = True


Asked = list[tuple[str, int, str | None]]


@pytest.fixture
def asked(monkeypatch: pytest.MonkeyPatch) -> Asked:
    """``listening_sockets`` on an ephemeral loopback port, recording what it was asked for.

    Never the real ``ELA_API_PORT``: an ELA running on this machine already holds it, and a test
    that bound it would be testing whether the developer had left ELA on.
    """
    seen: Asked = []

    def listening(api: ApiSettings) -> list[socket.socket]:
        seen.append((api.api_host, api.api_port, api.api_tailnet_host))
        return [server.bound("127.0.0.1", 0)]

    monkeypatch.setattr(server, "listening_sockets", listening)
    return seen


def test_serve_binds_what_the_settings_say(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, asked: Asked
) -> None:
    asyncio.run(create_schema(settings.persistence.db_url))
    uvicorn = Uvicorn()
    monkeypatch.setattr(server, "uvicorn", uvicorn)

    server.serve(settings)

    assert asked == [(settings.api.api_host, settings.api.api_port, None)]
    assert settings.api.api_host == "127.0.0.1"
    assert uvicorn.served
    assert uvicorn.app is not None  # the application ELA serves
    (listener,) = uvicorn.sockets
    (address,) = uvicorn.app.state.addresses
    assert address.startswith("127.0.0.1:")
    assert listener.fileno() == -1  # closed when the server stopped


def test_a_socket_is_bound_where_it_is_asked_and_refused_where_the_address_is_not_here() -> None:
    listener = server.bound("127.0.0.1", 0)
    try:
        assert server.shown(listener).startswith("127.0.0.1:")
    finally:
        listener.close()
    with pytest.raises(OSError):
        server.bound("192.0.2.1", 0)  # TEST-NET-1: an address no machine has


class Listener:
    """Enough of a socket to be shown."""

    def __init__(self, *name: object) -> None:
        self._name = name

    def getsockname(self) -> tuple[object, ...]:
        return self._name


def test_an_address_is_shown_as_a_url_writes_it() -> None:
    v4 = cast(socket.socket, Listener("100.76.0.1", 8351))
    v6 = cast(socket.socket, Listener("fd7a:115c:a1e0::1", 8351, 0, 0))

    assert server.shown(v4) == "100.76.0.1:8351"
    assert server.shown(v6) == "[fd7a:115c:a1e0::1]:8351"


def api(tailnet: str | None) -> ApiSettings:
    return ApiSettings(_env_file=None, api_token="t" * 40, api_tailnet_host=tailnet)


def test_without_a_tailnet_only_loopback_is_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    binds: list[str] = []
    monkeypatch.setattr(server, "bound", lambda host, port: binds.append(host) or host)

    assert server.listening_sockets(api(None)) == ["127.0.0.1"]
    assert binds == ["127.0.0.1"]


def test_with_a_tailnet_both_addresses_are_bound_on_one_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binds: list[tuple[str, int]] = []
    monkeypatch.setattr(server, "bound", lambda host, port: binds.append((host, port)) or host)

    assert server.listening_sockets(api("100.76.0.1")) == ["127.0.0.1", "100.76.0.1"]
    assert {port for _, port in binds} == {8351}


def test_a_tailnet_that_is_down_leaves_loopback_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    """ADR 0037 §2: ELA starts on loopback, and ``/diagnostics`` says so — it does not stay down."""

    def bind(host: str, port: int) -> str:
        if host != "127.0.0.1":
            raise OSError(49, "Can't assign requested address")
        return host

    monkeypatch.setattr(server, "bound", bind)

    assert server.listening_sockets(api("100.76.0.1")) == ["127.0.0.1"]


def test_loopback_that_cannot_be_bound_stops_the_start(monkeypatch: pytest.MonkeyPatch) -> None:
    def bind(host: str, port: int) -> str:
        raise OSError(48, "Address already in use")

    monkeypatch.setattr(server, "bound", bind)

    with pytest.raises(OSError):
        server.listening_sockets(api("100.76.0.1"))


@pytest.fixture
def occupied() -> Iterator[int]:
    """A loopback port something else is already listening on — the live failure of 2026-09-11, a
    ``python3`` left over from a trial holding 8351. An ephemeral port here, never 8351 itself."""
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(("127.0.0.1", 0))
    holder.listen()
    try:
        yield int(holder.getsockname()[1])
    finally:
        holder.close()


def on_port(settings: Settings, port: int) -> Settings:
    return settings.model_copy(update={"api": settings.api.model_copy(update={"api_port": port})})


def test_a_port_that_is_taken_stops_the_start_with_a_message_and_not_a_traceback(
    settings: Settings,
    occupied: int,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The docstring of ``api/server.py`` promised it and did not keep it: a configuration ELA
    cannot use is a message and exit code 2, never a traceback. A taken port is one."""
    asyncio.run(create_schema(settings.persistence.db_url))
    monkeypatch.setattr(server, "uvicorn", Uvicorn())
    monkeypatch.setattr(server.Settings, "load", lambda: on_port(settings, occupied))

    assert server.main() == 2
    error = capsys.readouterr().err
    assert f"127.0.0.1:{occupied}" in error
    assert "in use" in error
    assert "ELA_API_PORT" in error
    assert "Traceback" not in error


def test_the_message_names_who_holds_the_port_when_the_machine_can_say(
    settings: Settings,
    occupied: int,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    asyncio.run(create_schema(settings.persistence.db_url))
    monkeypatch.setattr(server, "uvicorn", Uvicorn())
    monkeypatch.setattr(server.Settings, "load", lambda: on_port(settings, occupied))
    asked: list[int] = []

    async def holder(port: int) -> str:
        asked.append(port)
        return "python3 (pid 4242)"

    monkeypatch.setattr(server, "port_holder", holder)

    assert server.main() == 2
    assert asked == [occupied]
    assert "it is held by python3 (pid 4242)" in capsys.readouterr().err


def test_a_holder_nobody_can_name_is_not_guessed(
    settings: Settings,
    occupied: int,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    asyncio.run(create_schema(settings.persistence.db_url))
    monkeypatch.setattr(server, "uvicorn", Uvicorn())
    monkeypatch.setattr(server.Settings, "load", lambda: on_port(settings, occupied))

    async def nobody(port: int) -> None:
        return None

    monkeypatch.setattr(server, "port_holder", nobody)

    assert server.main() == 2
    error = capsys.readouterr().err
    assert "held by" not in error
    assert "Stop what holds it, or set ELA_API_PORT" in error


def test_a_loopback_this_machine_refuses_for_another_reason_says_what_to_change(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Not a taken port — a port below 1024 without the right, say — so nobody is looked up."""
    asyncio.run(create_schema(settings.persistence.db_url))
    monkeypatch.setattr(server, "uvicorn", Uvicorn())
    monkeypatch.setattr(server.Settings, "load", lambda: settings)

    def refused(api: ApiSettings) -> list[socket.socket]:
        raise OSError(errno.EACCES, "Permission denied")

    async def never(port: int) -> str:
        raise AssertionError("nobody holds a port that was refused for another reason")

    monkeypatch.setattr(server, "listening_sockets", refused)
    monkeypatch.setattr(server, "port_holder", never)

    assert server.main() == 2
    error = capsys.readouterr().err
    assert f"127.0.0.1:{settings.api.api_port}: Permission denied" in error
    assert "Set ELA_API_HOST and ELA_API_PORT" in error
    assert "Traceback" not in error


def test_an_ipv6_loopback_is_written_as_a_url_writes_it() -> None:
    api = ApiSettings(_env_file=None, api_token="t" * 40, api_host="::1", api_port=8351)

    message = server.unavailable(api, OSError(errno.EADDRINUSE, "Address already in use"), None)

    assert message.startswith("ELA cannot listen on [::1]:8351: Address already in use.")


def test_main_returns_zero_when_the_server_stops(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, asked: Asked
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
