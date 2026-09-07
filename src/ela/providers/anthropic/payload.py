"""From a ``ProviderRequest`` to the body of a Messages API call (ADR 0020 §5).

``ProviderRequest.parameters`` is an open mapping in the domain and a **closed allowlist** here:
two keys, ``max_output_tokens`` and ``effort``. Anything else stops the call before it is made.

That is not pedantry. ``temperature`` is the case that proves it: it was removed from every
current model and sending it is a guaranteed 400 — so a pass-through would pay a round trip, and
the user's text would have crossed the network, to learn something known in advance (§57, §33).
Silently dropping it would be worse: a request answered under settings nobody asked for, with no
trace of the difference.
"""

from __future__ import annotations

from typing import Any, Final

from ela.domain import ProviderRequest
from ela.ports import PROVIDER_UNSUPPORTED_PARAMETER
from ela.providers.anthropic.errors import Failure, UnsupportedRequestError
from ela.providers.anthropic.models import EFFORT_LEVELS, Model

__all__ = ["MAX_OUTPUT_TOKENS", "EFFORT", "ALLOWED_PARAMETERS", "build_payload"]

MAX_OUTPUT_TOKENS: Final = "max_output_tokens"
EFFORT: Final = "effort"
ALLOWED_PARAMETERS: Final = frozenset({MAX_OUTPUT_TOKENS, EFFORT})


def _refuse(model: Model, message: str) -> UnsupportedRequestError:
    """A parameter ELA will not send. The *name* of the key may be reported, never its value."""
    return UnsupportedRequestError(
        Failure(PROVIDER_UNSUPPORTED_PARAMETER, message, retryable=False), model.id
    )


def _output_tokens(value: object, model: Model, default: int) -> int:
    if value is None:
        return min(default, model.max_output_tokens)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise _refuse(model, f"{MAX_OUTPUT_TOKENS} must be a positive integer")
    if value > model.max_output_tokens:
        raise _refuse(
            model,
            f"{MAX_OUTPUT_TOKENS} exceeds the {model.max_output_tokens} tokens "
            f"{model.id} can produce",
        )
    return value


def _effort(value: object, model: Model) -> str:
    if not model.supports_effort:
        raise _refuse(model, f"{model.id} does not support {EFFORT}")
    if value not in EFFORT_LEVELS:
        raise _refuse(model, f"{EFFORT} must be one of {list(EFFORT_LEVELS)}")
    return str(value)


def build_payload(
    request: ProviderRequest, model: Model, default_output_tokens: int
) -> dict[str, Any]:
    """The body of ``messages.create`` for this request, or :class:`UnsupportedRequestError`.

    What is sent, and nothing else: the model, the output budget, one user message, the
    instructions as ``system`` when there are any, and ``effort`` only when asked for. No
    ``temperature`` (removed on current models), no ``thinking`` (adaptive is what omitting it
    gives), no tools, no streaming, no caching: v0.1 asks a model to complete a text.
    """
    unknown = sorted(set(request.parameters) - ALLOWED_PARAMETERS)
    if unknown:
        raise _refuse(model, f"unsupported parameter(s): {unknown}")

    payload: dict[str, Any] = {
        "model": model.id,
        "max_tokens": _output_tokens(
            request.parameters.get(MAX_OUTPUT_TOKENS), model, default_output_tokens
        ),
        "messages": [{"role": "user", "content": request.input}],
    }
    if request.instructions is not None:
        payload["system"] = request.instructions
    if EFFORT in request.parameters:
        payload["output_config"] = {"effort": _effort(request.parameters[EFFORT], model)}
    return payload
