"""Where ELA starts listening (ADR 0023 §7, §16).

The address is **not** a command-line argument: ``ELA_API_HOST`` is validated as loopback in the
settings, and a bind that lives only in a shell line is not a constraint but a habit. What this
module adds is the loop — build ELA, serve it, and release the database when the server stops.
"""

from __future__ import annotations

import asyncio
import sys

import uvicorn

from ela.api.app import create_app
from ela.composition import ConfigurationError, Settings, build

__all__ = ["main", "serve"]


async def _serve(settings: Settings) -> None:
    ela = await build(settings)
    try:
        server = uvicorn.Server(
            uvicorn.Config(
                create_app(ela),
                host=settings.api.api_host,
                port=settings.api.api_port,
                log_level="info",
            )
        )
        await server.serve()
    finally:
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
