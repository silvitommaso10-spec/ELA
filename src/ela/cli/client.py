"""How the CLI reaches the ELA that is running (ADR 0024 §2, §3).

One HTTP client, built from the three variables a *client* needs — the token, the host, the port
— and nothing else: ``ela health`` must not refuse to answer because ``ELA_MODEL_ROUTES`` has a
typo in it, since that line is not about the question being asked. The seven settings are read by
:meth:`~ela.composition.Settings.load`, which is what ``ela serve`` uses, because building ELA is
the one thing that needs all of them.

The token comes from the environment (or the ``.env``) and never from a flag: a secret typed on a
command line ends up in the shell history and in ``ps``.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any, Final, Self

import httpx
from pydantic import ValidationError

from ela.composition import ConfigurationError
from ela.composition.settings import ApiSettings, explain

__all__ = [
    "CONNECT_TIMEOUT",
    "ApiRefusal",
    "ElaClient",
    "Unreachable",
    "api_settings",
    "base_url",
    "connect",
    "open_client",
    "query",
]

CONNECT_TIMEOUT: Final = 5.0
"""Seconds to wait for the connection, and **no timeout on the answer**.

``POST /tasks/{id}/run`` walks the plan inside the request (ADR 0023 §9), so an answer may
legitimately take as long as a model call; connecting to a process on this same machine may not.
"""
BEARER: Final = "Bearer"


class Unreachable(Exception):
    """Nothing answered at that address: ELA is not running, or not there (exit code 3)."""

    def __init__(self, url: str, reason: Exception) -> None:
        super().__init__(f"ELA does not answer at {url} ({reason}): start it with `ela serve`")
        self.url = url


class ApiRefusal(Exception):
    """ELA answered, and the answer was no (exit code 1).

    The ``code`` and the ``message`` are the API's own (ADR 0023 §10): a CLI that reworded them
    would give the user a second vocabulary to learn for the same failures.
    """

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.status = status
        self.code = code
        self.message = message

    @classmethod
    def of(cls, response: httpx.Response) -> ApiRefusal:
        """The refusal an error response carries, whatever shape it arrived in.

        Every failure ELA produces is ``{"error": {"code", "message"}}``. Anything else — a body
        that is not JSON, a JSON body of another shape — is reported as the status code itself
        rather than guessed at: it did not come from ELA's own error handling.
        """
        try:
            body = response.json()
            error = body["error"]
            return cls(response.status_code, str(error["code"]), str(error["message"]))
        except (ValueError, KeyError, TypeError):
            return cls(response.status_code, f"http_{response.status_code}", response.text.strip())


def query(**values: Any) -> dict[str, Any]:
    """The query parameters actually asked for: an absent option is not a filter."""
    return {name: value for name, value in values.items() if value not in (None, (), [])}


def api_settings() -> ApiSettings:
    """The token and the address, or a :class:`ConfigurationError` that names the variable."""
    try:
        return ApiSettings()
    except ValidationError as invalid:
        raise ConfigurationError(explain(invalid)) from invalid


def base_url(settings: ApiSettings) -> str:
    """Where ELA listens, as a URL. A numeric IPv6 address is bracketed, as URLs require."""
    host = f"[{settings.api_host}]" if ":" in settings.api_host else settings.api_host
    return f"http://{host}:{settings.api_port}"


class ElaClient:
    """The API, as the commands see it: a path in, parsed JSON out, a raised failure otherwise."""

    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._call("GET", path, params=params)

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        return self._call("POST", path, body=body)

    def _call(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        try:
            response = self._client.request(method, path, params=params, json=body)
        except httpx.TransportError as away:
            raise Unreachable(str(self._client.base_url), away) from away
        if response.is_error:
            raise ApiRefusal.of(response)
        return response.json()

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def open_client(settings: ApiSettings, transport: httpx.BaseTransport | None = None) -> ElaClient:
    """A client carrying the token, pointed at the address the settings declare.

    ``transport`` is the seam: the tests pass one that reaches the application in this process,
    so every command is exercised against the real API without a socket ever being opened.
    """
    return ElaClient(
        httpx.Client(
            base_url=base_url(settings),
            headers={"Authorization": f"{BEARER} {settings.token}"},
            timeout=httpx.Timeout(None, connect=CONNECT_TIMEOUT),
            transport=transport,
        )
    )


def connect() -> ElaClient:
    """The client a command talks through. Called by name, so a test can replace it."""
    return open_client(api_settings())
