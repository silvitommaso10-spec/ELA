"""Turning an HTTP answer into the failure the port promises (ADR 0034 §5, ADR 0020 §7).

Two things happen here, and only here.

**Classification, on the body and not on the status code.** ADR 0020 could read the *class* of an
SDK exception; this provider has no SDK, and its status codes do not partition its failures — a
refused credential arrives as **400**, and the same missing voice is a 404 on one endpoint and a
400 on another. Both measured on 2026-09-08. So the vocabulary is keyed on ``detail.type`` and
``detail.status``, which are the provider's own closed words, with the status code as the
fallback for everything they do not name.

**Redaction.** What ELA keeps of a failure is a status code, the provider's error *type*, and a
request id — never the ``message``, which quotes the request that was sent, and never a byte of
the text. It is the convention every tool already follows (ADR 0013 §7, ADR 0020 §10): a code, a
type name, a status; never content (§57).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Final

from ela.ports import (
    SPEECH_AUTHENTICATION_ERROR,
    SPEECH_MALFORMED_RESPONSE,
    SPEECH_QUOTA_EXCEEDED,
    SPEECH_RATE_LIMITED,
    SPEECH_REJECTED,
    SPEECH_SERVER_ERROR,
    SPEECH_TIMEOUT,
    SPEECH_UNKNOWN_MODEL,
    SPEECH_UNKNOWN_VOICE,
    SPEECH_UNREACHABLE,
)

__all__ = [
    "AUTHENTICATION_TYPE",
    "STATUS_CODES",
    "Failure",
    "classify_answer",
    "retry_after_of",
    "transport_failure",
    "unusable_answer",
]

SERVER_ERROR_FROM: Final = 500
RATE_LIMIT_STATUS: Final = 429

AUTHENTICATION_TYPE: Final = "authentication_error"
"""The provider's own word for a credential it will not accept. **Read from the body**, because
the status beside it is a 400 (measured) and a 400 read alone says "your request was malformed",
which sends whoever is investigating to the wrong half of the problem."""

STATUS_CODES: Final = {
    "voice_not_found": SPEECH_UNKNOWN_VOICE,
    "model_not_found": SPEECH_UNKNOWN_MODEL,
    "quota_exceeded": SPEECH_QUOTA_EXCEEDED,
    "max_character_limit_exceeded": SPEECH_REJECTED,
}
"""``detail.status`` values ELA has a name for. Everything else falls back to the HTTP code —
a vocabulary that grows only when somebody needs a name that is not there (ADR 0020 §7)."""


@dataclass(frozen=True, slots=True)
class Failure:
    """One failed call, in ELA's terms: what went wrong, and whether it is worth trying again."""

    code: str
    message: str
    retryable: bool
    status_code: int | None = None
    request_id: str | None = None
    retry_after: float | None = None


def _detail(body: bytes) -> dict[str, object]:
    """The ``detail`` object of an error body, or an empty one.

    A body that is not JSON, or whose ``detail`` is a plain string, is not an error in itself:
    it only means the provider is not telling us which failure this is, and the status code is
    then all there is.
    """
    try:
        parsed = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    detail = parsed.get("detail")
    return detail if isinstance(detail, dict) else {}


def _named(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def retry_after_of(raw: str | None) -> float | None:
    """The ``retry-after`` header in seconds, when it is there and is a number.

    The header may also be an HTTP date; ELA does not parse that (ADR 0020 §8) — a hint it cannot
    read simply leaves the exponential backoff in charge, which is always a safe answer.
    """
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def classify_answer(
    status: int, body: bytes, *, request_id: str | None, retry_after: float | None = None
) -> Failure:
    """Which failure an error response is. Never reads the provider's free text."""
    detail = _detail(body)
    kind = _named(detail.get("type"))
    named_status = _named(detail.get("status"))
    message = f"{status} {named_status or kind or 'error'}"
    if kind == AUTHENTICATION_TYPE:
        return Failure(
            SPEECH_AUTHENTICATION_ERROR,
            message,
            retryable=False,
            status_code=status,
            request_id=request_id,
        )
    if named_status in STATUS_CODES:
        return Failure(
            STATUS_CODES[named_status],
            message,
            retryable=False,
            status_code=status,
            request_id=request_id,
        )
    if status == RATE_LIMIT_STATUS:
        return Failure(
            SPEECH_RATE_LIMITED,
            message,
            retryable=True,
            status_code=status,
            request_id=request_id,
            retry_after=retry_after,
        )
    if status >= SERVER_ERROR_FROM:
        return Failure(
            SPEECH_SERVER_ERROR,
            message,
            retryable=True,
            status_code=status,
            request_id=request_id,
        )
    return Failure(
        SPEECH_REJECTED, message, retryable=False, status_code=status, request_id=request_id
    )


def transport_failure(*, timed_out: bool) -> Failure:
    """Nothing arrived: the request timed out, or the provider could not be reached.

    Two codes and not one, for the reason of ADR 0030 §8: "I waited and it never came" and "there
    is no network here" are different things to read at three in the morning, and the second one
    is not about ElevenLabs at all.
    """
    if timed_out:
        return Failure(SPEECH_TIMEOUT, "the voice did not answer in time", retryable=True)
    return Failure(SPEECH_UNREACHABLE, "the voice could not be reached", retryable=True)


def unusable_answer(reason: str) -> Failure:
    """A 200 that cannot be used: no audio, or more of it than ELA agreed to hold.

    Kept apart from :data:`~ela.ports.SPEECH_REJECTED` for ADR 0020 §7's reason — a broken channel
    and a refused request send whoever is investigating in opposite directions.
    """
    return Failure(SPEECH_MALFORMED_RESPONSE, reason, retryable=False)
