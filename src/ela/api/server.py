"""Where ELA starts listening (ADR 0023 §7, §16; ADR 0037 §2).

The addresses are **not** command-line arguments: ``ELA_API_HOST`` is validated as loopback and
``ELA_API_TAILNET_HOST`` as an address of the tailnet, in the settings, and a bind that lives only
in a shell line is not a constraint but a habit. What this module adds is the loop — build ELA,
bind, serve it, and release the database when the server stops.

**One server, two sockets** (ADR 0037 §2): the same application, behind the same middleware,
served from loopback — for the CLI — and from the tailnet — for the nodes — through
``uvicorn.Server.serve(sockets=[…])``. Loopback is always bound, and a failure there stops the start
— with a message that says the address, the port, why, and who holds it when the machine can say,
and exit code 2 like every configuration ELA cannot use; never a traceback (the live failure of
2026-09-11: 8351 held by a ``python3`` left over from a trial). The tailnet is bound when it is
declared **and** present: if its address does not exist on this machine now — the tailnet is down
— ELA listens on loopback alone, because local use does not depend on a third party's daemon, and
``/diagnostics`` says on which addresses it listens.

**The stop signals are ELA's** (M13.4e, decisions 55 and 56; the measure is in
``docs/milestones/M13.4e.md``). From the moment there is an ELA to close to the moment its close
has ended, ``SIGINT``, ``SIGTERM`` and ``SIGHUP`` reach :class:`Signalled` and nobody else: the
first raises the stop, the second the hurry, and none of them raises an exception or cancels a
task — so the close always runs whole, and the loop is never torn down with a call of the
browser's in flight. Only when ``_serve`` has returned does the process end, **as it ended
before**: the signals it received are raised again, with the handlers ELA had found back in place.

**And a signal wakes the loop, whichever thread the system hands it to** (M13.4e, the third
part: decision 141 of the review of 2026-10-13): for the same span a descriptor of ELA's is where
the system writes when a signal arrives, and the loop reads it (:func:`_woken`).
"""

from __future__ import annotations

import asyncio
import errno
import signal
import socket
import sys
import threading
from collections import Counter
from collections.abc import Iterator, Sequence
from contextlib import contextmanager, suppress
from types import FrameType
from typing import Final

import uvicorn

from ela.api.app import create_app
from ela.composition import ConfigurationError, Settings, build, port_holder
from ela.composition.root import BROWSER_CLOSE_GRACE_SECONDS
from ela.composition.settings import ApiSettings

__all__ = [
    "STOP_SIGNALS",
    "Signalled",
    "Stopping",
    "bound",
    "killed",
    "listening_sockets",
    "main",
    "serve",
    "shown",
    "unavailable",
]


STOP_SIGNALS: Final[tuple[int, ...]] = tuple(
    int(getattr(signal, name))
    for name in ("SIGHUP", "SIGTERM", "SIGBREAK", "SIGINT")
    if hasattr(signal, name)
)
"""The signals that stop ``ela serve`` — the ones this system has —, **in the order that decides
how it ends**: the one that used to kill first comes first. Measured on the code before M13.4e's
second part: a ``SIGHUP`` killed at once, a ``SIGTERM`` when the server had stopped, and a
``SIGINT`` was the only one that reached the close."""


class Stopping(uvicorn.Server):
    """The server ELA serves with: it leaves the signals to ELA (M13.4e, decision 56).

    **Measured before it was written** (uvicorn 0.52.4): while it serves, uvicorn replaces
    whatever handler it finds for ``SIGINT`` and ``SIGTERM``; at the end it puts that handler back
    **and raises every signal it captured again, into it**. A handler of ELA's installed before
    ``serve`` would therefore not see a signal when it arrives, but only raised again when the
    server has finished stopping: **the stop would be raised late** — after the connections in
    flight were waited for, which is the long poll ADR 0038 §11 exists to wake —, and a
    ``SIGHUP``, which uvicorn does not capture, would be the only signal ELA saw in time. So this
    server captures nothing: the handlers ELA installed stay where they are for as long as it
    serves, and :class:`Signalled` tells it to exit.

    ADR 0038 §11 is kept by that handler and not here any more: the stop is still raised at the
    instant of the signal, which is what wakes whoever is waiting.
    """

    @contextmanager
    def capture_signals(self) -> Iterator[None]:
        yield


class Signalled:
    """What ``ela serve`` does with a stop signal, for as long as there is an ELA to close.

    It is called by Python in the main thread, between two instructions of whatever the loop is
    running: it writes the signal down and **hands the rest to the loop** — a signal handler is
    not the loop —, and it never raises and never cancels a task. That is the whole of how the
    loop is not torn down with something in flight (decision 55).

    **The first signal** raises ELA's stop — at the instant of the signal: a node holding a long
    poll is answered then, not at the end of its window (ADR 0038 §11) — and tells the server to
    exit; for a ``SIGHUP`` too, which uvicorn never looked at. **The second, whichever it is**,
    raises the hurry — the grace of ELA's close is over at once — and tells the server not to
    wait for its connections any longer, as uvicorn did at a second Ctrl-C. **From the third on**
    nothing is left to raise.
    """

    def __init__(
        self, loop: asyncio.AbstractEventLoop, stopping: asyncio.Event, received: list[int]
    ) -> None:
        self.received = received
        self.hurry = asyncio.Event()
        self.serving: uvicorn.Server | None = None
        self.loop = loop
        self._stopping = stopping

    def __call__(self, number: int, frame: FrameType | None) -> None:
        self.received.append(number)
        again = len(self.received) > 1
        self.loop.call_soon_threadsafe(self.hurry.set if again else self._stopping.set)
        if self.serving is not None:
            self.serving.should_exit = True
            self.serving.force_exit = again


def _drained(reading: socket.socket) -> None:
    """Take away what a signal wrote: the loop has woken, and that was the whole of its use."""
    with suppress(OSError):
        reading.recv(64)


@contextmanager
def _woken(loop: asyncio.AbstractEventLoop) -> Iterator[None]:
    """A signal wakes ``loop`` from here to the end of the block, **whichever thread the system
    hands it to**; then whatever woke it before (M13.4e, the third part: decision 141).

    A handler installed with ``signal.signal`` runs in the main thread, when the main thread next
    runs Python — and the system hands a signal sent to a process to any of its threads. Handed
    to another one while the loop sleeps in its selector, nothing ran the handler until something
    else woke the loop: measured on 2026-10-13 with these handlers, a second signal during the
    close — when nothing else does — was not heard, and a first one waited for the next tick of
    the server. With a descriptor the system writes into at every signal
    (``signal.set_wakeup_fd``), and that the loop reads, the loop wakes at once: it is what
    ``loop.add_signal_handler`` rests on, without what made ELA not use it (:func:`_held`).

    **A loop that cannot be asked to read a descriptor is given none**: the one Python gives on
    Windows sets a wake-up of its own when it is made (read in ``asyncio``; not measured there).
    **And where no descriptor is left for the pair, ELA goes on without the wake-up** — as it
    did before it had one —: this is entered when there is an ELA built and not yet closed, and
    nothing here may keep its close from running.
    Called from the main thread only, like everything that touches the signals."""
    try:
        reading, writing = socket.socketpair()
    except OSError:
        yield
        return
    try:
        reading.setblocking(False)
        writing.setblocking(False)
        try:
            loop.add_reader(reading, _drained, reading)
        except NotImplementedError:
            read = False
        else:
            read = True
        if not read:
            yield
            return
        try:
            found = signal.set_wakeup_fd(writing.fileno(), warn_on_full_buffer=False)
            try:
                yield
            finally:
                signal.set_wakeup_fd(found)
        finally:
            # Whatever happened — the system refusing the descriptor included —, the loop is
            # not left reading a socket that is about to be closed.
            loop.remove_reader(reading)
    finally:
        reading.close()
        writing.close()


@contextmanager
def _held(told: Signalled) -> Iterator[None]:
    """ELA's handler for the stop signals, from here to the end of the block; then the ones found.

    Installed with ``signal.signal``, as uvicorn installs its own, and only from the main thread —
    Python allows no other. Not with ``loop.add_signal_handler``: measured, a signal is then
    delivered once to the loop's callback and once more to whoever raises it again. **What that
    call would have given and this one does not is the wake-up of the loop**, and it is added
    here, for the same span (:func:`_woken`).

    **A ``SIGHUP`` found ignored stays ignored**: that is ``nohup ela serve``, which survives its
    terminal today. ``SIGINT`` and ``SIGTERM`` are taken whatever was found, because uvicorn took
    them so."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    hangup = getattr(signal, "SIGHUP", None)
    found = {
        number: signal.signal(number, told)
        for number in STOP_SIGNALS
        if number != hangup or signal.getsignal(number) is not signal.SIG_IGN
    }
    try:
        with _woken(told.loop):
            yield
    finally:
        for number, handler in found.items():
            # ``None`` is what Python answers for a handler it did not install itself, and it
            # refuses to install ``None``: what cannot be named is put back as the default.
            signal.signal(number, signal.SIG_DFL if handler is None else handler)


def bound(host: str, port: int) -> socket.socket:
    """A TCP socket bound to ``host:port``, for the server to listen on.

    :raises OSError: if it cannot be bound — the address is not on this machine, or taken.
    """
    family, kind, protocol, _, address = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)[0]
    listener = socket.socket(family, kind, protocol)
    try:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(address)
    except OSError:
        listener.close()
        raise
    return listener


def listening_sockets(api: ApiSettings) -> list[socket.socket]:
    """Loopback always; the tailnet too, when it is declared and exists on this machine now.

    A tailnet that is down is not a reason not to start: what was bound is what ``/diagnostics``
    reports, so the difference is visible rather than silent.
    """
    sockets = [bound(api.api_host, api.api_port)]
    if api.api_tailnet_host is not None:
        with suppress(OSError):
            sockets.append(bound(api.api_tailnet_host, api.api_port))
    return sockets


def shown(listener: socket.socket) -> str:
    """Where ``listener`` is bound, as a URL writes it: a numeric IPv6 address in brackets."""
    host, port = listener.getsockname()[:2]
    return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"


def unavailable(api: ApiSettings, refused: OSError, holder: str | None) -> str:
    """What to tell whoever started ELA when loopback cannot be bound: where, why, what to do."""
    host = f"[{api.api_host}]" if ":" in api.api_host else api.api_host
    reason = refused.strerror or str(refused)
    if refused.errno == errno.EADDRINUSE:
        held = f" — it is held by {holder}" if holder is not None else ""
        return (
            f"ELA cannot listen on {host}:{api.api_port}: {reason}{held}. Stop what holds it, "
            "or set ELA_API_PORT to a free port."
        )
    return (
        f"ELA cannot listen on {host}:{api.api_port}: {reason}. Set ELA_API_HOST and "
        "ELA_API_PORT to an address this machine can listen on."
    )


async def _claimed(api: ApiSettings) -> list[socket.socket]:
    """The sockets to serve on, or a :class:`ConfigurationError` that says why there are none.

    Who holds the port is asked only when it is taken — the one case where the answer is what to
    stop — and through ``port_holder``, which answers ``None`` rather than guess.
    """
    try:
        return listening_sockets(api)
    except OSError as refused:
        taken = refused.errno == errno.EADDRINUSE
        holder = await port_holder(api.api_port) if taken else None
        raise ConfigurationError(unavailable(api, refused, holder)) from None


def killed(names: Sequence[str], hurried: bool = False) -> str:
    """What ELA says when its close had to kill the browser (M13.4e): **why the grace was over**
    — its time ran out, or a second signal ended it — and **the names of the processes with how
    many of each**; never a command line, a path or an address. A name is enough to know what
    happened; a value may be somebody's."""
    counted = ", ".join(f"{count} {name}" for name, count in sorted(Counter(names).items()))
    why = (
        "had not closed when a second signal arrived"
        if hurried
        else f"did not close within {BROWSER_CLOSE_GRACE_SECONDS} s of the stop"
    )
    return f"ela: the browser {why}: ELA killed what it had started — {counted}"


def _say(line: str) -> None:
    """A line on stderr, **which may not be there**: after a ``SIGHUP`` the terminal is gone, and
    ELA may have been started with no stderr at all. A line that cannot be written is lost, and
    whatever was saying it goes on — the close to release the database (decision 56), the start
    to serve."""
    with suppress(OSError, ValueError):
        print(line, file=sys.stderr)


def _say_killed(names: Sequence[str], hurried: bool) -> None:
    _say(killed(names, hurried))


async def _serve(settings: Settings, received: list[int]) -> None:
    ela = await build(settings)
    told = Signalled(asyncio.get_running_loop(), ela.stopping, received)
    # From here there is an ELA to close, and the stop signals are ELA's until it is closed.
    # Before, there is none: a Ctrl-C during the start cancels the start, as it always did.
    with _held(told):
        if ela.removed_from_environment:
            # The names and never the values (M13.4, decision 4 of the review of 2026-09-30): a
            # name is what somebody needs to find the line in their shell.
            _say(
                f"ela: removed {', '.join(ela.removed_from_environment)} from ELA's environment: "
                "the browser's driver must not inherit what turns its checks off (ADR 0052 §14)"
            )
        sockets: list[socket.socket] = []
        try:
            sockets = await _claimed(settings.api)
            app = create_app(ela)
            app.state.addresses = tuple(shown(listener) for listener in sockets)
            # After the bind and before serving: the bell's tap opens the address this process
            # ended up on, not the one the settings asked for. If the tailnet was not there, ELA
            # is on loopback only and the bell is not ready — which ``/diagnostics`` says (M12.5
            # dec. E).
            ela.serving_at(app.state.addresses)
            server = Stopping(uvicorn.Config(app, log_level="info"))
            told.serving = server
            if not received:  # a signal that came before the server serves: it never does
                await server.serve(sockets=sockets)
        finally:
            for listener in sockets:
                listener.close()
            # The close waits for the browser, and past its grace — or at a second signal —
            # kills what the browser's adapter had started (M13.4e): said here, inside the
            # close, because it is the close that knows which of the two it was.
            await ela.aclose(killed=_say_killed, hurry=told.hurry)


def serve(settings: Settings) -> None:
    """Build ELA and serve it until the server stops — and then end as the signal ended it.

    ``_serve`` returns normally whatever stopped it: the close has run whole. **Only then** the
    signals it received are raised again, each once, in the order of :data:`STOP_SIGNALS` — the
    way uvicorn gave a process its end, moved after the close. By now the handlers ELA had found
    are back: a ``SIGINT`` is Python's ``KeyboardInterrupt``, from which come the 130 of ``ela
    serve`` and the death by ``SIGINT`` of ``python -m ela.api``; a ``SIGTERM`` or a ``SIGHUP``
    kills, as it did; and one that had been found ignored is raised into nothing."""
    received: list[int] = []
    asyncio.run(_serve(settings, received))
    for number in STOP_SIGNALS:
        if number in received:
            signal.raise_signal(number)


def main() -> int:
    """``python -m ela.api``: read the configuration, build, serve.

    A configuration ELA cannot use is a message on stderr and exit code 2 — never a traceback:
    whoever reads it wrote the ``.env``, and what they need is the name of the variable.
    """
    try:
        serve(Settings.load())
    except ConfigurationError as wrong:
        print(f"ela: {wrong}", file=sys.stderr)
        return 2
    return 0
