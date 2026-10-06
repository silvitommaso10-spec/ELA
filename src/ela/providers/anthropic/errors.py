"""Turning an SDK exception into the vendor-independent failure the port promises (ADR 0020 §7).

Two things happen here, and only here:

* **Classification.** Which of :data:`~ela.ports.PROVIDER_ERROR_CODES` an exception is, whether
  trying again could ever change the answer, and **whether the API ran the request** (M14.1,
  ADR 0057). A ``4xx`` — the ``429`` included — and the ``529`` of an overloaded API are turned
  down before anything runs: they cost nothing, and only the ``429`` and the ``529`` are worth
  trying again. A timeout, a dropped connection, any other ``5xx`` and an answer that cannot be
  read may come after the work was done and paid: nobody knows, so they are not tried again —
  one unknown outcome is not paid twice (ADR 0021 §2, a level further down). An answer that is not
  an answer is neither: a 409 or a 422 is the API turning a request down, an unreadable body is
  the channel breaking, and the two get different codes so that a serialisation bug never reads
  as "your request was rejected" (review of M7.1).
* **Redaction.** The message ELA keeps is built from the status code and the API's own error
  *type* — a closed vocabulary (``invalid_request_error``, ``rate_limit_error``, …) — never from
  the server's free text, which describes the request that was sent. It is the convention the
  tools already follow (ADR 0013 §7): a code, a type name, a status; never content (§57).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import anthropic

from ela.ports import (
    PROVIDER_AUTHENTICATION_ERROR,
    PROVIDER_BAD_REQUEST,
    PROVIDER_MALFORMED_RESPONSE,
    PROVIDER_RATE_LIMITED,
    PROVIDER_REJECTED,
    PROVIDER_SERVER_ERROR,
    PROVIDER_TIMEOUT,
    PROVIDER_UNKNOWN_MODEL,
    PROVIDER_UNREACHABLE,
    PROVIDER_WORKSPACE_LIMIT,
)

__all__ = ["WORKSPACE_LIMIT_PREFIX", "Failure", "UnsupportedRequestError", "classify"]

SERVER_ERROR_FROM: Final = 500
AUTHENTICATION_STATUS: Final = frozenset({401, 403})
RATE_LIMIT_STATUS: Final = 429
OVERLOADED_STATUS: Final = 529
BAD_REQUEST_STATUS: Final = 400
NOT_FOUND_STATUS: Final = 404

WORKSPACE_LIMIT_PREFIX: Final = "You have reached your specified workspace API usage limits"
"""How the API begins the ``400`` of a workspace that reached its monthly spending limit — the
documentation's words (``api/rate-limits``, read on 2026-10-06). **Read and never kept**
(ADR 0020 §10): it decides the code, and the message ELA keeps is its own. If the sentence ever
changes the answer falls back to :data:`~ela.ports.PROVIDER_BAD_REQUEST`, which is what it was
before M14.1: no harm (review decision 10)."""

WORKSPACE_LIMIT_MESSAGE: Final = (
    "the workspace of this key reached its monthly spending limit: look at the workspace's "
    "limit in the console, and at `ela spend`"
)


@dataclass(frozen=True, slots=True)
class Failure:
    """One failed call, in ELA's terms: what went wrong, and whether it is worth trying again."""

    code: str
    message: str
    retryable: bool
    status_code: int | None = None
    request_id: str | None = None
    retry_after: float | None = None
    """What the provider asked us to wait, in seconds, when it said so (429)."""
    unrun: bool = False
    """The API turned the request down before running it: it cost nothing, and trying again does
    not pay twice. ``False`` where nobody knows — the safe answer (§33; M14.1, ADR 0057)."""


class UnsupportedRequestError(Exception):
    """A request this provider cannot express — raised and caught *inside* the adapter.

    It never escapes :meth:`~ela.providers.anthropic.provider.AnthropicProvider.complete`: the
    port promises a result, not an exception. It exists so that the two checks that happen before
    the network (the model hint, the parameters) can report what they found from where they found
    it, instead of returning a sentinel through three layers.
    """

    def __init__(self, failure: Failure, model: str = "") -> None:
        super().__init__(failure.message)
        self.failure = failure
        self.model = model


def _retry_after(exc: anthropic.APIStatusError) -> float | None:
    """The ``retry-after`` header in seconds, if it is there and is a number.

    The header may also be an HTTP date; ELA does not parse that — an unreadable hint simply
    leaves the exponential backoff in charge, which is always a safe answer.
    """
    raw = exc.response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _workspace_limit(exc: anthropic.APIStatusError) -> bool:
    """Whether the server's own words begin the way a workspace's spending limit does.

    The only place ELA reads the server's text, and it keeps none of it: the answer is a bool.
    """
    body = exc.body
    error = body.get("error") if isinstance(body, dict) else None
    words = error.get("message") if isinstance(error, dict) else None
    return isinstance(words, str) and words.startswith(WORKSPACE_LIMIT_PREFIX)


def _status_failure(exc: anthropic.APIStatusError) -> Failure:
    status = exc.status_code
    message = f"{status} {exc.type or 'error'}"
    request_id = exc.request_id
    if status == RATE_LIMIT_STATUS:
        return Failure(
            PROVIDER_RATE_LIMITED,
            message,
            retryable=True,
            status_code=status,
            request_id=request_id,
            retry_after=_retry_after(exc),
            unrun=True,
        )
    if status >= SERVER_ERROR_FROM:
        code, retryable = PROVIDER_SERVER_ERROR, True
    elif status in AUTHENTICATION_STATUS:
        code, retryable = PROVIDER_AUTHENTICATION_ERROR, False
    elif status == BAD_REQUEST_STATUS and _workspace_limit(exc):
        code, retryable = PROVIDER_WORKSPACE_LIMIT, False
        message = f"{message}: {WORKSPACE_LIMIT_MESSAGE}"
    elif status == BAD_REQUEST_STATUS:
        code, retryable = PROVIDER_BAD_REQUEST, False
    elif status == NOT_FOUND_STATUS:
        code, retryable = PROVIDER_UNKNOWN_MODEL, False
    else:
        code, retryable = PROVIDER_REJECTED, False
    return Failure(
        code,
        message,
        retryable=retryable,
        status_code=status,
        request_id=request_id,
        unrun=status < SERVER_ERROR_FROM or status == OVERLOADED_STATUS,
    )


def classify(exc: anthropic.APIError) -> Failure:
    """Which failure this exception is: retryable by nature for 429, 5xx and transport; unrun —
    turned down before anything ran — for a ``4xx`` and the ``529``."""
    if isinstance(exc, anthropic.APITimeoutError):
        return Failure(PROVIDER_TIMEOUT, "the call did not answer in time", retryable=True)
    if isinstance(exc, anthropic.APIConnectionError):
        return Failure(PROVIDER_UNREACHABLE, "the provider could not be reached", retryable=True)
    if isinstance(exc, anthropic.APIStatusError):
        return _status_failure(exc)
    return Failure(
        PROVIDER_MALFORMED_RESPONSE, f"unusable answer: {type(exc).__name__}", retryable=False
    )
