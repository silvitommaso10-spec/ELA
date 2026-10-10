"""Starting ELA (ADR 0023 §7, §16): ``python -m ela.api``.

The address is not a command-line argument, so this is where the settings and the socket meet.
No socket is opened here: what is under test is that ``serve`` hands uvicorn what the settings
say, and that a configuration ELA cannot use is a sentence on stderr rather than a traceback.
"""

from __future__ import annotations

import asyncio
import errno
import os
import runpy
import signal
import socket
import sys
import threading
from collections.abc import (
    Awaitable,
    Callable,
    Iterator,
)
from typing import Any, cast

import pytest
import uvicorn
from httpx import AsyncClient

from ela.api import server
from ela.composition import Ela, Settings, build
from ela.composition.settings import (
    ApiSettings,
)
from ela.testing.fakes import FakeBrowser, FakePower
from tests.api.test_nodes import enrolled
from tests.composition.support import create_schema


class Uvicorn:
    """Enough of uvicorn to record what it was asked for, and to answer ``serve``."""

    def __init__(self) -> None:
        self.app: Any = None
        self.sockets: list[socket.socket] = []
        self.served = False
        self.should_exit = False
        self.force_exit = False
        self.during: Callable[[], Awaitable[None]] | None = None

    def Config(self, app: Any, *, log_level: str) -> Uvicorn:  # noqa: N802
        self.app = app
        return self

    def stopping(self, config: Uvicorn, **wired: object) -> Uvicorn:
        """What ``_serve`` builds: the server ELA serves with. Until M13.4e's second part it was
        handed the stop and the loop, for uvicorn's own handler to raise it (ADR 0038 §11); since
        then the signals are ELA's, and the server is handed nothing."""
        self.wired = wired
        return config

    async def serve(self, sockets: list[socket.socket]) -> None:
        self.sockets = list(sockets)
        self.served = True
        if self.during is not None:
            await self.during()


def fake_server(monkeypatch: pytest.MonkeyPatch) -> Uvicorn:
    """Both halves of the seam: the module ``serve`` reads, and the server class it builds."""
    fake = Uvicorn()
    monkeypatch.setattr(server, "uvicorn", fake)
    monkeypatch.setattr(server, "Stopping", fake.stopping)
    return fake


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
    uvicorn = fake_server(monkeypatch)

    server.serve(settings)

    assert asked == [(settings.api.api_host, settings.api.api_port, None)]
    assert settings.api.api_host == "127.0.0.1"
    assert uvicorn.served
    assert uvicorn.app is not None  # the application ELA serves
    (listener,) = uvicorn.sockets
    (address,) = uvicorn.app.state.addresses
    assert address.startswith("127.0.0.1:")
    assert listener.fileno() == -1  # closed when the server stopped


def test_the_start_names_the_node_variables_it_removed_and_never_their_values(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    asked: Asked,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Decision 4 of the review of 2026-09-30: the Core removes every ``NODE_`` variable from its
    environment before the browser's driver can inherit it, and the start says which — a name is
    what somebody needs to find the line in their shell; a value may be a path or a secret."""
    asyncio.run(create_schema(settings.persistence.db_url))
    fake_server(monkeypatch)
    monkeypatch.setenv("NODE_TLS_REJECT_UNAUTHORIZED", "0")
    monkeypatch.setenv("NODE_EXTRA_CA_CERTS", "/segreto/ca-7431.pem")

    server.serve(settings)

    error = capsys.readouterr().err
    assert "NODE_EXTRA_CA_CERTS" in error and "NODE_TLS_REJECT_UNAUTHORIZED" in error
    assert "7431" not in error and "=" not in error
    assert "ADR 0052" in error


def test_a_start_with_no_node_variable_says_nothing_about_them(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    asked: Asked,
    capsys: pytest.CaptureFixture[str],
) -> None:
    asyncio.run(create_schema(settings.persistence.db_url))
    fake_server(monkeypatch)
    for name in [name for name in os.environ if name.startswith("NODE_")]:
        monkeypatch.delenv(name)

    server.serve(settings)

    assert "NODE_" not in capsys.readouterr().err


async def test_a_stop_wakes_the_node_that_waits(app: Any, client: AsyncClient, ela: Ela) -> None:
    """Criterion 33 (dec. I): a node holding ``POST /nodes/work`` is answered at the instant of the
    stop, not at the end of its window.

    The measurement behind it: with the plain uvicorn server the lifespan fires **after** the
    requests in flight are awaited, so the handler finished its own wait (3.56 s against a three
    second handler) — the signal handler is the one place early enough. Here the event is raised
    while a request is genuinely in flight, and what is asserted is the *timing*: the answer comes
    back in a fraction of the window, which is the difference between being told and waiting it out.

    What this cannot show in one process is the signal itself; that half is
    ``test_the_first_signal_raises_the_stop_and_stops_the_server_and_the_second_the_hurry`` —
    since M13.4e's second part the handler is ELA's and not uvicorn's —, and the two together are
    the criterion.
    """
    _, headers = await enrolled(client, "TRUSTED", available_tools=["core-echo"])
    window = ela.settings.core.node_poll.total_seconds()
    loop = asyncio.get_running_loop()
    started = loop.time()
    waiting = asyncio.create_task(client.post("/nodes/work", headers=headers))
    await asyncio.sleep(0.05)
    assert not waiting.done()  # it is holding the request, with nothing to hand out

    app.state.stopping.set()
    answered = await asyncio.wait_for(waiting, timeout=window * 5)

    assert answered.status_code == 204
    assert loop.time() - started < window / 2


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
    fake_server(monkeypatch)
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
    fake_server(monkeypatch)
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
    fake_server(monkeypatch)
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
    fake_server(monkeypatch)
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


def with_a_browser(monkeypatch: pytest.MonkeyPatch, browser: FakeBrowser) -> None:
    """``_serve`` builds ELA itself: here with a browser the test holds."""

    async def built(settings: Settings) -> Ela:
        return await build(settings, power=FakePower(), browser=browser)

    monkeypatch.setattr(server, "build", built)


def test_a_browser_ela_had_to_kill_is_said_at_the_close_by_name_and_count(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    asked: Asked,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """M13.4e, decision 51: past the grace ELA kills what the browser's adapter had started, and
    writes it on stderr — the names of the processes and how many, never a command line."""
    from ela.composition.root import BROWSER_CLOSE_GRACE_SECONDS

    asyncio.run(create_schema(settings.persistence.db_url))
    fake_server(monkeypatch)
    browser = FakeBrowser()
    browser.killed = ("chrome-headless-shell", "chrome-headless-shell", "node")
    with_a_browser(monkeypatch, browser)

    server.serve(settings)

    error = capsys.readouterr().err
    assert (
        f"ela: the browser did not close within {BROWSER_CLOSE_GRACE_SECONDS} s of the stop: ELA "
        "killed what it had started — 2 chrome-headless-shell, 1 node" in error
    )


def test_a_browser_that_closed_by_itself_is_not_mentioned_at_the_close(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    asked: Asked,
    capsys: pytest.CaptureFixture[str],
) -> None:
    asyncio.run(create_schema(settings.persistence.db_url))
    fake_server(monkeypatch)
    browser = FakeBrowser()
    with_a_browser(monkeypatch, browser)

    server.serve(settings)

    assert len(browser.settled) == 1, "the close did ask the browser to settle"
    assert "killed" not in capsys.readouterr().err


# ----------------------------------------------------------------------------------------
# The stop signals are ELA's (M13.4e, the second part: decisions 55 and 56)
# ----------------------------------------------------------------------------------------

POSIX = pytest.mark.skipif(sys.platform == "win32", reason="SIGHUP is POSIX's")


def numbered(names: list[str]) -> list[int]:
    """The signals ``names`` name. Read inside a test, never when the module is imported: a
    system without ``SIGHUP`` skips these tests, and must be able to read the file to skip them."""
    return [int(getattr(signal, name)) for name in names]


def handled() -> list[int]:
    return numbered(["SIGINT", "SIGTERM", "SIGHUP"])


def dispositions() -> dict[int, Any]:
    return {number: signal.getsignal(number) for number in handled()}


@pytest.fixture
def found() -> Iterator[dict[int, Any]]:
    """The dispositions a process started from a terminal finds, whatever the suite's worker has
    — a worker ignores ``SIGINT`` —, and the worker's own back at the end."""
    worker = dispositions()
    signal.signal(signal.SIGINT, signal.default_int_handler)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.signal(signal.SIGHUP, signal.SIG_DFL)
    try:
        yield dispositions()
    finally:
        for number, handler in worker.items():
            signal.signal(number, handler)


@pytest.fixture
def raised(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Every signal ``serve`` raises again at its end, recorded instead of delivered: delivered,
    a ``SIGTERM`` would be the end of the worker that runs this test."""
    seen: list[int] = []
    monkeypatch.setattr(signal, "raise_signal", seen.append)
    return seen


def ours(number: int) -> Callable[[int, Any], None]:
    """ELA's handler of ``number``, or the failure that says it is not ELA's."""
    handler = signal.getsignal(number)
    assert isinstance(handler, server.Signalled), f"the handler of {number} is {handler!r}"
    return handler


class Waiting(FakeBrowser):
    """A browser that had not closed: it waits for the whole grace, then names what it killed."""

    async def settle(self, grace: Callable[[], Awaitable[None]]) -> tuple[str, ...]:
        await super().settle(grace)
        await grace()
        return ("node",)


@POSIX
def test_while_ela_serves_the_stop_signals_are_ela_s_and_afterwards_the_ones_it_found(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    asked: Asked,
    found: dict[int, Any],
    raised: list[int],
) -> None:
    """Decision 56: the handlers are ELA's for as long as there is an ELA to close — not the ones
    uvicorn installs while it serves, nor the ones it and ``asyncio.run`` put back."""
    asyncio.run(create_schema(settings.persistence.db_url))
    fake = fake_server(monkeypatch)
    during: dict[int, Any] = {}

    async def look() -> None:
        during.update(dispositions())

    fake.during = look

    server.serve(settings)

    assert fake.served
    assert all(isinstance(handler, server.Signalled) for handler in during.values()), during
    assert len({id(handler) for handler in during.values()}) == 1, "one handler, for the three"
    assert dispositions() == found
    assert raised == [], "the server stopped by itself: no signal, nothing to raise again"


class Looking(FakeBrowser):
    """A browser that looks at the handlers of the stop signals when ELA's close settles it."""

    def __init__(self) -> None:
        super().__init__()
        self.found: dict[int, Any] = {}

    async def settle(self, grace: Callable[[], Awaitable[None]]) -> tuple[str, ...]:
        self.found = dispositions()
        return await super().settle(grace)


@POSIX
def test_while_the_close_runs_the_stop_signals_are_still_ela_s(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    asked: Asked,
    found: dict[int, Any],
    raised: list[int],
) -> None:
    """Decision 55: **during the close ELA holds the handler** — that is what lets a second
    Ctrl-C end the grace instead of ending the process. Found by the review of the repair: with
    the handlers put back before the close, every test of this file stayed green."""
    asyncio.run(create_schema(settings.persistence.db_url))
    fake_server(monkeypatch)
    browser = Looking()
    with_a_browser(monkeypatch, browser)

    server.serve(settings)

    assert browser.found, "the close did settle the browser"
    assert all(isinstance(handler, server.Signalled) for handler in browser.found.values())
    assert dispositions() == found, "and only after the close are they the ones ELA found"


@POSIX
def test_while_ela_is_being_built_the_stop_signals_are_not_ela_s_yet(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    asked: Asked,
    found: dict[int, Any],
    raised: list[int],
) -> None:
    """Before ``build`` returns there is no ELA to close, so there is no close to run: a Ctrl-C
    there cancels the start, as it always did. A start nobody could interrupt would be a new
    defect — and the handlers installed too early are exactly that."""
    asyncio.run(create_schema(settings.persistence.db_url))
    fake_server(monkeypatch)
    during: dict[int, Any] = {}
    building = server.build

    async def built(settings: Settings) -> Ela:
        during.update(dispositions())
        return await building(settings, power=FakePower(), browser=FakeBrowser())

    monkeypatch.setattr(server, "build", built)

    server.serve(settings)

    assert during, "the control: build was reached"
    assert not any(isinstance(handler, server.Signalled) for handler in during.values())
    assert during[signal.SIGTERM] is signal.SIG_DFL and during[signal.SIGHUP] is signal.SIG_DFL


@POSIX
def test_a_sigint_and_a_sigterm_found_ignored_are_taken_all_the_same(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    asked: Asked,
    found: dict[int, Any],
    raised: list[int],
) -> None:
    """Measured: uvicorn took ``SIGINT`` and ``SIGTERM`` whatever it found — a background job of
    a script finds ``SIGINT`` ignored, and stopped all the same. «As it ended before» holds there
    too: only a ``SIGHUP`` found ignored is left ignored."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    asyncio.run(create_schema(settings.persistence.db_url))
    fake = fake_server(monkeypatch)
    during: dict[int, Any] = {}

    async def look() -> None:
        during.update(dispositions())

    fake.during = look

    server.serve(settings)

    assert isinstance(during[signal.SIGINT], server.Signalled)
    assert isinstance(during[signal.SIGTERM], server.Signalled)
    assert signal.getsignal(signal.SIGINT) is signal.SIG_IGN
    assert signal.getsignal(signal.SIGTERM) is signal.SIG_IGN


@POSIX
async def test_a_signal_that_arrives_while_the_loop_sleeps_wakes_it() -> None:
    """«At once» is this: a signal handler runs in the main thread while the loop sleeps in its
    selector, and what it hands to the loop must **wake** it — ``call_soon_threadsafe``. Handed
    over with ``call_soon`` the stop would be raised when something else woke the loop: for the
    hurry, at the end of the grace it was meant to end (the review of the repair). Built with a
    real signal, sent to this thread from another while nothing is scheduled; the guard is the
    test's, and is the only other thing that can wake the loop."""
    loop = asyncio.get_running_loop()
    stopping = asyncio.Event()
    guard = asyncio.Event()
    told = server.Signalled(loop, stopping, [])
    before = signal.signal(signal.SIGTERM, told)
    main = threading.main_thread().ident
    assert main is not None

    def send() -> None:
        signal.pthread_kill(main, signal.SIGTERM)

    sender = threading.Timer(0.05, send)
    watchdog = threading.Timer(5.0, loop.call_soon_threadsafe, [guard.set])
    try:
        sender.start()
        watchdog.start()
        waits = [asyncio.ensure_future(stopping.wait()), asyncio.ensure_future(guard.wait())]
        await asyncio.wait(waits, return_when=asyncio.FIRST_COMPLETED)
        for wait in waits:
            wait.cancel()
    finally:
        watchdog.cancel()
        sender.join()
        signal.signal(signal.SIGTERM, before)

    assert stopping.is_set(), "the signal reached the handler"
    assert not guard.is_set(), "and it woke the loop itself: nothing else had to"


@POSIX
def test_a_handler_python_cannot_name_is_put_back_as_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``signal.signal`` answers ``None`` for a handler that was not installed from Python, and
    refuses ``None`` when asked to install one: putting back «what was found» would raise after
    the close, leave the other handlers ELA's, and raise nothing again."""
    installed: list[tuple[int, Any]] = []

    def install(number: int, handler: Any) -> Any:
        installed.append((number, handler))
        return None

    monkeypatch.setattr(signal, "signal", install)
    monkeypatch.setattr(signal, "getsignal", lambda number: None)
    told = server.Signalled(asyncio.new_event_loop(), asyncio.Event(), [])

    with server._held(told):  # noqa: SLF001 — the one place that installs and puts back
        taken = list(installed)
        installed.clear()

    assert [handler for _, handler in taken] == [told] * len(server.STOP_SIGNALS)
    assert installed == [(number, signal.SIG_DFL) for number, _ in taken]


@POSIX
def test_a_start_whose_stderr_is_gone_still_closes_ela(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    asked: Asked,
) -> None:
    """The line that names the variables removed from the environment is written when ELA has
    just been built. A stderr that is not there must not leave an ELA built and never closed."""
    monkeypatch.setenv("NODE_OPTIONS", "--inspect")
    asyncio.run(create_schema(settings.persistence.db_url))
    fake = fake_server(monkeypatch)
    browser = FakeBrowser()
    made: list[Ela] = []

    async def built(settings: Settings) -> Ela:
        made.append(await build(settings, power=FakePower(), browser=browser))
        return made[0]

    monkeypatch.setattr(server, "build", built)
    gone = Gone(OSError(errno.EIO, "Input/output error"))
    monkeypatch.setattr(sys, "stderr", gone)

    server.serve(settings)

    assert made[0].removed_from_environment == ("NODE_OPTIONS",), "the control: there was a line"
    assert gone.asked >= 1 and fake.served, "it was lost, and ELA served all the same"
    assert len(browser.settled) == 1, "and was closed"


@POSIX
def test_a_sighup_found_ignored_is_left_ignored(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    asked: Asked,
    found: dict[int, Any],
    raised: list[int],
) -> None:
    """Measured, 2026-10-10: under ``nohup`` a process finds ``SIGHUP`` ignored. ``nohup ela
    serve`` survives its terminal today, and goes on doing so."""
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    asyncio.run(create_schema(settings.persistence.db_url))
    fake = fake_server(monkeypatch)
    during: dict[int, Any] = {}

    async def look() -> None:
        during.update(dispositions())

    fake.during = look

    server.serve(settings)

    assert during[signal.SIGHUP] is signal.SIG_IGN
    assert isinstance(during[signal.SIGINT], server.Signalled)
    assert isinstance(during[signal.SIGTERM], server.Signalled)
    assert signal.getsignal(signal.SIGHUP) is signal.SIG_IGN


@POSIX
async def test_the_first_signal_raises_the_stop_and_stops_the_server_and_the_second_the_hurry() -> (
    None
):
    """The handler runs in the main thread between two instructions, so what it does to the loop
    it hands to the loop. **The first** signal raises ELA's stop — at the instant of the signal, as
    ADR 0038 §11 wants — and tells the server to exit; **the second, whichever it is**, raises the
    hurry and tells the server not to wait for its connections; **from the third on** nothing
    changes (decision 55)."""
    stopping = asyncio.Event()
    received: list[int] = []
    told = server.Signalled(asyncio.get_running_loop(), stopping, received)
    serving = Uvicorn()
    told.serving = cast(Any, serving)

    told(signal.SIGTERM, None)
    assert not stopping.is_set(), "handed to the loop: a signal handler is not the loop"
    await asyncio.sleep(0)

    assert stopping.is_set() and serving.should_exit
    assert not told.hurry.is_set() and not serving.force_exit

    told(signal.SIGHUP, None)
    await asyncio.sleep(0)

    assert told.hurry.is_set() and serving.force_exit

    told(signal.SIGINT, None)
    told(signal.SIGINT, None)
    await asyncio.sleep(0)

    assert told.hurry.is_set() and stopping.is_set() and serving.should_exit and serving.force_exit
    assert received == [signal.SIGTERM, signal.SIGHUP, signal.SIGINT, signal.SIGINT]


@POSIX
async def test_a_signal_before_there_is_a_server_is_kept_and_still_raises_the_stop() -> None:
    stopping = asyncio.Event()
    received: list[int] = []
    told = server.Signalled(asyncio.get_running_loop(), stopping, received)

    told(signal.SIGINT, None)
    told(signal.SIGINT, None)
    await asyncio.sleep(0)

    assert stopping.is_set() and told.hurry.is_set() and received == [signal.SIGINT] * 2


@POSIX
def test_a_signal_between_the_build_and_the_serving_means_the_server_never_serves(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    asked: Asked,
    found: dict[int, Any],
    raised: list[int],
) -> None:
    """The handlers are ELA's from the moment ``build`` returns. A signal that arrives before the
    server serves is not lost and is not served through: the server never starts, the close runs,
    and the end is that signal's."""
    asyncio.run(create_schema(settings.persistence.db_url))
    fake = fake_server(monkeypatch)
    browser = FakeBrowser()
    with_a_browser(monkeypatch, browser)
    making = server.create_app

    def made(ela: Ela) -> Any:
        ours(signal.SIGTERM)(signal.SIGTERM, None)
        return making(ela)

    monkeypatch.setattr(server, "create_app", made)

    server.serve(settings)

    assert not fake.served
    assert len(browser.settled) == 1, "the close ran"
    assert raised == [signal.SIGTERM]


@POSIX
@pytest.mark.parametrize(
    ("sent", "again"),
    [
        (["SIGINT"], ["SIGINT"]),
        (["SIGTERM"], ["SIGTERM"]),
        (["SIGHUP"], ["SIGHUP"]),
        (["SIGINT", "SIGINT"], ["SIGINT"]),
        (["SIGINT", "SIGTERM"], ["SIGTERM", "SIGINT"]),
        (["SIGTERM", "SIGINT"], ["SIGTERM", "SIGINT"]),
        (["SIGINT", "SIGTERM", "SIGHUP", "SIGTERM"], ["SIGHUP", "SIGTERM", "SIGINT"]),
    ],
    ids="+".join,
)
def test_the_end_is_the_signal_s_own_raised_again_after_the_close(
    sent: list[str],
    again: list[str],
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    asked: Asked,
    found: dict[int, Any],
) -> None:
    """Decision 56: the close runs whole, **and only then** the process ends as it ended before —
    the way uvicorn gave that end: by raising the signal again once the handlers it had found are
    back. Each signal received once, in the order of what used to kill: ``SIGHUP``, which killed at
    once, then ``SIGTERM``, then ``SIGINT`` (measured)."""
    asyncio.run(create_schema(settings.persistence.db_url))
    fake = fake_server(monkeypatch)
    browser = FakeBrowser()
    with_a_browser(monkeypatch, browser)
    seen: list[tuple[int, int, bool]] = []

    def raise_again(number: int) -> None:
        back = dispositions() == found
        seen.append((number, len(browser.settled), back))

    monkeypatch.setattr(signal, "raise_signal", raise_again)

    async def signalled() -> None:
        for number in numbered(sent):
            ours(number)(number, None)

    fake.during = signalled

    server.serve(settings)

    assert [number for number, _, _ in seen] == numbered(again)
    assert all(settled == 1 for _, settled, _ in seen), "after the close, never before it"
    assert all(back for _, _, back in seen), "and with the handlers ELA had found back in place"


@POSIX
def test_a_second_signal_ends_the_grace_at_once_and_the_line_says_which_ended_it(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    asked: Asked,
    found: dict[int, Any],
    raised: list[int],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Decision 55: a second Ctrl-C ends the grace at once — ELA kills what the adapter had
    started, and writes it. The browser here waits for the whole grace: with one signal that is
    five seconds; with two, the hurry is what ends it, and the line says so."""
    asyncio.run(create_schema(settings.persistence.db_url))
    fake = fake_server(monkeypatch)
    with_a_browser(monkeypatch, Waiting())

    async def twice() -> None:
        ours(signal.SIGINT)(signal.SIGINT, None)
        ours(signal.SIGINT)(signal.SIGINT, None)

    fake.during = twice

    server.serve(settings)

    error = capsys.readouterr().err
    assert (
        "ela: the browser had not closed when a second signal arrived: ELA killed what it had "
        "started — 1 node" in error
    )
    assert "within" not in error
    assert fake.should_exit and fake.force_exit
    assert raised == [signal.SIGINT]


def test_the_line_says_whether_the_grace_ran_out_or_a_second_signal_ended_it() -> None:
    from ela.composition.root import BROWSER_CLOSE_GRACE_SECONDS

    names = ("node", "chrome-headless-shell", "chrome-headless-shell")

    assert server.killed(names, hurried=False) == (
        f"ela: the browser did not close within {BROWSER_CLOSE_GRACE_SECONDS} s of the stop: ELA "
        "killed what it had started — 2 chrome-headless-shell, 1 node"
    )
    assert server.killed(names, hurried=True) == (
        "ela: the browser had not closed when a second signal arrived: ELA killed what it had "
        "started — 2 chrome-headless-shell, 1 node"
    )


class Gone:
    """A stderr that is not there any more: what a ``SIGHUP`` from a closed terminal leaves."""

    def __init__(self, refusal: Exception) -> None:
        self._refusal = refusal
        self.asked = 0

    def write(self, text: str) -> int:
        self.asked += 1
        raise self._refusal

    def flush(self) -> None:
        raise self._refusal


@pytest.mark.parametrize(
    "refusal",
    [OSError(errno.EIO, "Input/output error"), ValueError("I/O operation on closed file")],
)
def test_a_line_that_cannot_be_written_does_not_break_the_close(
    refusal: Exception,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    asked: Asked,
) -> None:
    """Decision 56: after a ``SIGHUP`` the stderr may be gone. The line is lost; the close is not
    — the database is released as if it had been written."""
    asyncio.run(create_schema(settings.persistence.db_url))
    fake_server(monkeypatch)
    browser = FakeBrowser()
    browser.killed = ("node",)
    made: list[Ela] = []

    async def built(settings: Settings) -> Ela:
        made.append(await build(settings, power=FakePower(), browser=browser))
        return made[0]

    monkeypatch.setattr(server, "build", built)
    gone = Gone(refusal)
    monkeypatch.setattr(sys, "stderr", gone)

    server.serve(settings)

    assert gone.asked >= 1, "ELA did try to say it"
    assert int(made[0].database.pool.checkedin()) == 0, "and the database was released"  # type: ignore[attr-defined]


@POSIX
def test_off_the_main_thread_ela_serves_and_leaves_the_signals_alone(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    asked: Asked,
    found: dict[int, Any],
    raised: list[int],
) -> None:
    """A signal handler can only be installed from the main thread — uvicorn's own condition."""
    asyncio.run(create_schema(settings.persistence.db_url))
    fake = fake_server(monkeypatch)
    during: dict[int, Any] = {}
    failed: list[BaseException] = []

    async def look() -> None:
        during.update(dispositions())

    fake.during = look

    def elsewhere() -> None:
        try:
            server.serve(settings)
        except BaseException as error:  # noqa: BLE001 — whatever it is, the test says it
            failed.append(error)

    thread = threading.Thread(target=elsewhere)
    thread.start()
    thread.join(30)

    assert failed == [] and fake.served
    assert during == found and raised == []


@POSIX
async def test_the_server_does_not_capture_the_signals_and_raises_none_again(
    app: Any, raised: list[int]
) -> None:
    """Measured, 2026-10-10 (uvicorn 0.52.4): while it serves uvicorn replaces whatever handler it
    finds for ``SIGINT`` and ``SIGTERM``, puts it back at the end **and raises every signal it
    captured again, into that handler** — so whoever counts «a second signal» would count the
    first one twice. The server ELA serves with leaves the signals where it found them."""
    stopper = server.Stopping(uvicorn.Config(app))
    stopper._captured_signals.append(signal.SIGTERM)  # noqa: SLF001 — what uvicorn would raise
    before = dispositions()

    with stopper.capture_signals():
        assert dispositions() == before

    assert dispositions() == before
    assert raised == []


def test_main_returns_zero_when_the_server_stops(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, asked: Asked
) -> None:
    asyncio.run(create_schema(settings.persistence.db_url))
    fake_server(monkeypatch)

    assert server.main() == 0


def test_main_says_what_is_wrong_and_does_not_start(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No ``ELA_API_TOKEN`` on this machine: ELA does not open an unauthenticated API."""
    fake_server(monkeypatch)

    code = server.main()

    assert code == 2
    error = capsys.readouterr().err
    assert "ELA_API_TOKEN" in error
    assert "Traceback" not in error


def test_main_reports_a_configuration_that_only_build_can_see(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The database nobody migrated is found by ``build``, after ``Settings.load`` was happy."""
    fake_server(monkeypatch)

    assert server.main() == 2
    assert "alembic upgrade head" in capsys.readouterr().err


def test_python_m_ela_api_runs_main(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "main", lambda: 7)

    with pytest.raises(SystemExit) as raised:
        runpy.run_module("ela.api.__main__", run_name="__main__")

    assert raised.value.code == 7
