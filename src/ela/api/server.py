"""Where ELA starts listening (ADR 0023 §7, §16; ADR 0037 §2).

The addresses are **not** command-line arguments: ``ELA_API_HOST`` is validated as loopback and
``ELA_API_TAILNET_HOST`` as an address of the tailnet, in the settings, and a bind that lives only
in a shell line is not a constraint but a habit. What this module adds is the loop — build ELA,
bind, serve it, and release the database when the server stops.

**One server, two sockets** (ADR 0037 §2): the same application, behind the same middleware,
served from loopback — for the CLI — and from the tailnet — for the nodes — through
``uvicorn.Server.serve(sockets=[…])``. Loopback is always bound, and a failure there stops the start
as it always did. The tailnet is bound when it is declared **and** present: if its address does not
exist on this machine now — the tailnet is down — ELA listens on loopback alone, because local use
does not depend on a third party's daemon, and ``/diagnostics`` says on which addresses it listens.
"""

from __future__ import annotations

import asyncio
import socket
import sys
from contextlib import suppress

import uvicorn

from ela.api.app import create_app
from ela.composition import ConfigurationError, Settings, build
from ela.composition.settings import ApiSettings

__all__ = ["bound", "listening_sockets", "main", "serve", "shown"]


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


async def _serve(settings: Settings) -> None:
    ela = await build(settings)
    sockets: list[socket.socket] = []
    try:
        sockets = listening_sockets(settings.api)
        app = create_app(ela)
        app.state.addresses = tuple(shown(listener) for listener in sockets)
        server = uvicorn.Server(uvicorn.Config(app, log_level="info"))
        await server.serve(sockets=sockets)
    finally:
        for listener in sockets:
            listener.close()
        await ela.aclose()


def serve(settings: Settings) -> None:
    """Build ELA and serve it until the server stops."""
    asyncio.run(_serve(settings))


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
