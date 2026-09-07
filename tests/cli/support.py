"""Driving the CLI in a test, against the real API, without opening a socket.

The CLI is synchronous and the application is ASGI, so the two live on different sides of a
thread: the test's event loop holds ELA and the app, ``CliRunner`` runs in a worker thread, and
:class:`LoopTransport` carries each request across — ``run_coroutine_threadsafe`` onto the loop
that owns the database, the answer back to the thread that asked.

It costs these thirty lines and it buys the thing the milestone is about: every command is
exercised against the API it will really talk to, so a CLI and an API that disagree fail here
rather than on a user's machine. And ``tests/conftest.py``'s "no test talks to the network" stays
true — ``ASGITransport`` opens nothing, and this class is not one of the transports it disables.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest
from click.testing import Result
from fastapi import FastAPI
from httpx import ASGITransport
from typer import Typer
from typer.testing import CliRunner

from ela.api import create_app
from ela.cli import client
from ela.cli.app import app as ela_app
from ela.composition import Ela

__all__ = ["Cli", "LoopTransport", "cli", "refusing", "unreachable"]


class LoopTransport(httpx.BaseTransport):
    """A synchronous transport that hands the request to an ASGI app on another event loop."""

    def __init__(self, application: FastAPI, loop: asyncio.AbstractEventLoop) -> None:
        self._asgi = ASGITransport(app=application)
        self._loop = loop
        self.requests: list[httpx.Request] = []
        """Every request that went through, so a test can assert what the CLI *asked* and not
        only what it printed (M8.3: ``audit tail`` must ask for ``n`` rows, not for all of them)."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.requests.append(request)

        async def call() -> httpx.Response:
            answer = await self._asgi.handle_async_request(
                httpx.Request(
                    request.method,
                    request.url,
                    headers=request.headers,
                    content=request.content,
                )
            )
            await answer.aread()
            return httpx.Response(
                answer.status_code, headers=answer.headers, content=answer.content
            )

        return asyncio.run_coroutine_threadsafe(call(), self._loop).result()


class Cli:
    """``await cli("task", "list")``: the command line, run in a thread, with its result.

    ``transport`` is the one it talks through, kept here so that a test which needs a client of
    its own — one carrying the wrong token — can reach the same application.
    """

    def __init__(self, transport: httpx.BaseTransport, application: Typer = ela_app) -> None:
        self.transport = transport
        self._runner = CliRunner()
        self._app = application

    async def __call__(self, *arguments: str) -> Result:
        return await asyncio.to_thread(self._runner.invoke, self._app, list(arguments))


def unreachable(request: httpx.Request) -> httpx.Response:
    """What a transport does when nothing is listening at the other end."""
    raise httpx.ConnectError("connection refused", request=request)


def refusing(status: int, body: str, content_type: str = "text/plain") -> httpx.MockTransport:
    """A transport that answers an error whose body is not ELA's own error shape."""

    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=body, headers={"content-type": content_type})

    return httpx.MockTransport(answer)


@pytest.fixture
async def cli(ela: Ela, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Cli]:
    """The CLI, pointed at a real ELA served in this process.

    ``connect`` is the seam (ADR 0024 §3): the commands call it by name, so replacing it here
    replaces the transport for every one of them and for nothing else.
    """
    application = create_app(ela)
    transport = LoopTransport(application, asyncio.get_running_loop())
    monkeypatch.setattr(
        client, "connect", lambda: client.open_client(ela.settings.api, transport=transport)
    )
    async with application.router.lifespan_context(application):
        yield Cli(transport)
