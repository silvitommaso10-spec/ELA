"""Turning an SDK exception into the vendor-independent failure the port promises (ADR 0020 §7).

Two things happen here, and only here:

* **Classification.** Which of :data:`~ela.ports.PROVIDER_ERROR_CODES` an exception is, and
  whether trying again could ever change the answer. The rule the milestone asks for lives in one
  place: 429 and 5xx are retried, a 4xx never is — retrying a rejected request only rejects it
  again, and retrying an authentication failure cannot invent a credential.
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
    PROVIDER_RATE_LIMITED,
    PROVIDER_REJECTED,
    PROVIDER_SERVER_ERROR,
    PROVIDER_TIMEOUT,
    PROVIDER_UNKNOWN_MODEL,
    PROVIDER_UNREACHABLE,
)

__all__ = ["Failure", "UnsupportedRequestError", "classify"]

SERVER_ERROR_FROM: Final = 500
AUTHENTICATION_STATUS: Final = frozenset({401, 403})
RATE_LIMIT_STATUS: Final = 429
BAD_REQUEST_STATUS: Final = 400
NOT_FOUND_STATUS: Final = 404


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
        )
    if status >= SERVER_ERROR_FROM:
        code, retryable = PROVIDER_SERVER_ERROR, True
    elif status in AUTHENTICATION_STATUS:
        code, retryable = PROVIDER_AUTHENTICATION_ERROR, False
    elif status == BAD_REQUEST_STATUS:
        code, retryable = PROVIDER_BAD_REQUEST, False
    elif status == NOT_FOUND_STATUS:
        code, retryable = PROVIDER_UNKNOWN_MODEL, False
    else:
        code, retryable = PROVIDER_REJECTED, False
    return Failure(code, message, retryable=retryable, status_code=status, request_id=request_id)


def classify(exc: anthropic.APIError) -> Failure:
    """Which failure this exception is: retryable exactly for 429, 5xx and transport."""
    if isinstance(exc, anthropic.APITimeoutError):
        return Failure(PROVIDER_TIMEOUT, "the call did not answer in time", retryable=True)
    if isinstance(exc, anthropic.APIConnectionError):
        return Failure(PROVIDER_UNREACHABLE, "the provider could not be reached", retryable=True)
    if isinstance(exc, anthropic.APIStatusError):
        return _status_failure(exc)
    return Failure(PROVIDER_REJECTED, f"unusable answer: {type(exc).__name__}", retryable=False)
